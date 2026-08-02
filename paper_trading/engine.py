import logging
import re
import time
import json
import uuid
import sqlite3
import psycopg2
import psycopg2.extras
from typing import List, Dict, Optional
from core.config import config
from exchange.client import DeltaClient
from core.telegram_bot import telegram_bot
from core.expiry import is_expiry_close_due, option_expiry_from_symbol

logger = logging.getLogger(__name__)

class PaperTradingEngine:
    def __init__(self):
        self.db_url = config.DATABASE_URL
        self._init_db()
        self.btc_price = 65000.0
        self.real_wallet_data = {}
        self.client = DeltaClient()
        self.size_map = {"BTCUSD":1000,
                         "ETHUSD":100}
        self.size = 0
        self._position_cache = []
        self._position_cache_updated_at = 0.0
        self._position_cache_ttl_seconds = config.POSITION_CACHE_TTL_SECONDS
        self._last_db_sync_at = 0.0

    def get_connection(self):
        if self.db_url:
            try:
                return psycopg2.connect(self.db_url)
            except Exception:
                logger.warning("Could not connect to Postgres at DATABASE_URL, falling back to local sqlite database")
                # All query paths must use sqlite placeholders/cursors after a
                # fallback; retaining the URL made the fallback unusable.
                self.db_url = ""
        return sqlite3.connect("paper_trading.db")

    def _init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Postgres uses slightly different types and syntax
        if self.db_url:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entryPrice DOUBLE PRECISION,
                    currentPrice DOUBLE PRECISION,
                    size DOUBLE PRECISION,
                    leverage DOUBLE PRECISION,
                    margin DOUBLE PRECISION,
                    unrealized_pnl DOUBLE PRECISION,
                    timestamp DOUBLE PRECISION,
                    strategy TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entryPrice REAL,
                    closePrice REAL,
                    size REAL,
                    pnl REAL,
                    timestamp REAL,
                    strategy TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_states (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entryPrice REAL,
                    size REAL,
                    leverage REAL,
                    margin REAL,
                    unrealized_pnl REAL,
                    timestamp REAL,
                    strategy TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entryPrice REAL,
                    closePrice REAL,
                    size REAL,
                    pnl REAL,
                    timestamp REAL,
                    strategy TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_states (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
        
        conn.commit()
        # Existing sqlite installations predate currentPrice.  Keep migrations
        # local and idempotent instead of requiring a new database.
        if not self.db_url:
            columns = [row[1].lower() for row in cursor.execute('PRAGMA table_info(positions)').fetchall()]
            if 'currentprice' not in columns:
                cursor.execute('ALTER TABLE positions ADD COLUMN currentPrice REAL')
                conn.commit()
        conn.close()

    def update_real_wallet(self, data: dict):
        # Data is list of assets from Delta
        self.real_wallet_data = data.get("result", {})

    async def get_wallet(self):
        balance = float(getattr(config, "PAPER_WALLET_BALANCE", 1000000.0))

        positions = await self.get_positions()
        total_pnl = sum(p["unrealizedPnL"] for p in positions)
        used_margin = sum(p["margin"] for p in positions)

        equity = balance + total_pnl

        return {
            "balance": balance,
            "usedMargin": used_margin,
            "availableBalance": balance - used_margin,
            "totalEquity": equity,
            "totalUnrealizedPnL": total_pnl,
            "asset": "USDT"
        }

    def _normalize_db_position(self, row) -> Dict:
        if hasattr(row, 'keys'):
            data = dict(row)
        elif isinstance(row, dict):
            data = row
        else:
            data = {}
        d = {str(k).lower(): v for k, v in data.items()}
        current_price = None
        for key in ("currentprice", "current_price", "currentPrice"):
            if key in d:
                current_price = d.get(key)
                break
        pos = {
            "id": d.get("id"),
            "symbol": d.get("symbol", ""),
            "side": d.get("side", ""),
            "entryPrice": float(d.get("entryprice") or d.get("entry_price") or 0),
            "currentPrice": float(current_price or 0),
            "size": float(d.get("size") or 0),
            "leverage": float(d.get("leverage") or 0),
            "margin": float(d.get("margin") or 0),
            "unrealizedPnL": float(d.get("unrealized_pnl") or 0),
            "timestamp": d.get("timestamp"),
            "strategy": d.get("strategy"),
            "contractType": d.get("contracttype") or d.get("contract_type"),
        }
        pos["entryprice"] = pos["entryPrice"]
        pos["currentprice"] = pos["currentPrice"]
        return pos

    def _normalize_live_position(self, pos: Dict) -> Dict:
        return {
            "id": pos.get("product_id"),
            "symbol": pos.get("product_symbol"),
            "side": "LONG" if pos.get("size", 0) > 0 else "SHORT",
            "entryPrice": float(pos.get("entry_price", 0)),
            "currentPrice": float(pos.get("mark_price", 0)),
            "size": float(pos.get("size", 0)),
            "leverage": float(pos.get("leverage", 0)),
            "margin": float(pos.get("margin", 0)),
            "unrealizedPnL": (((float(pos.get("mark_price", 0)) - float(pos.get("entry_price", 0))) * float(pos.get("size", 0)) / 1000)),
            "contractType": pos.get("product", {}).get("contract_type"),
            "timestamp": pos.get("timestamp"),
        }

    @staticmethod
    def _normalize_symbol(symbol) -> str:
        if symbol is None:
            return ""
        return re.sub(r"[^a-z0-9]+", "", str(symbol).strip().lower())

    def _resolve_price_for_symbol(self, price_map: Dict[str, float], symbol: Optional[str]) -> Optional[float]:
        if symbol is None:
            return None

        direct_price = price_map.get(symbol)
        if direct_price is not None:
            return float(direct_price)

        normalized_symbol = self._normalize_symbol(symbol)
        for candidate_symbol, candidate_price in price_map.items():
            if self._normalize_symbol(candidate_symbol) == normalized_symbol and candidate_price is not None:
                return float(candidate_price)
        return None

    def _get_db_placeholder(self) -> str:
        return "%s" if self.db_url else "?"

    def get_cached_positions(self):
        return [dict(position) for position in self._position_cache]

    async def refresh_position_cache(self, force: bool = False):
        cache_age = time.time() - self._position_cache_updated_at
        if not force and self._position_cache and cache_age < self._position_cache_ttl_seconds:
            return self.get_cached_positions()

        positions = []
        try:
            if config.IS_PAPER_TRADING or not config.ALLOW_REAL_ORDER_EXECUTION:
                positions = [self._normalize_db_position(row) for row in await self.get_positions_from_db()]
            else:
                live_pos = await self.client.get_live_positions()
                self.client.user_id = live_pos.get("result", [{}])[0].get("user_id", 0) if live_pos.get("result") else 0
                positions = [self._normalize_live_position(pos) for pos in live_pos.get("result", [])]
        except Exception as exc:
            logger.warning("Falling back to cached database positions because live position refresh failed: %s", exc)
            positions = [self._normalize_db_position(row) for row in await self.get_positions_from_db()]

        self._position_cache = [dict(position) for position in positions]
        self._position_cache_updated_at = time.time()
        return self.get_cached_positions()

    async def get_positions(self):
        return await self.refresh_position_cache(force=False)

    async def get_positions_from_db(self):
        conn = self.get_connection()
        if self.db_url:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        cursor.execute('SELECT * FROM positions')
        rows = cursor.fetchall()
        positions = [dict(row) for row in rows]
        conn.close()
        return positions
    def get_trade_history(self):
        conn = self.get_connection()
        if self.db_url:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        cursor.execute('SELECT * FROM trade_history ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        history = [dict(row) for row in rows]
        conn.close()
        return history


    async def update_prices(self, price_map: Dict[str, float]):
        """Updates unrealized PnL for all positions based on a symbol->price map."""
        btc_price_key = None
        for symbol in ["BTCUSD", "BTC-USD", "BTC/USD", "BTCUSDT"]:
            if symbol in price_map:
                btc_price_key = symbol
                break
        if btc_price_key is not None:
            self.btc_price = float(price_map[btc_price_key])

        positions = await self.get_positions_from_db()
        if not positions:
            await self.refresh_position_cache(force=True)
            return

        conn = self.get_connection()
        cursor = conn.cursor()

        for pos in positions:
            symbol = pos.get("symbol")
            current_price = self._resolve_price_for_symbol(price_map, symbol)

            if current_price is not None:
                # Basic PnL: (Current - Entry) * Size * Multiplier
                # For Inverse products (like BTC/USD on Delta) the calculation is more complex,
                # but for Paper Trading V1 we'll stick to Linear simulation.
                diff = current_price - float(pos.get("entryprice") or pos.get("entryPrice") or 0)
                multiplier = 1 if str(pos.get("side", "")).upper() == "LONG" else -1
                new_pnl = diff * float(pos.get("size") or 0) * multiplier
                if self.db_url:
                    cursor.execute(
                        'UPDATE positions SET unrealized_pnl = %s, currentprice = %s WHERE id = %s',
                        (new_pnl, current_price, pos.get("id")),
                    )
                else:
                    cursor.execute(
                        'UPDATE positions SET unrealized_pnl = ?, currentPrice = ? WHERE id = ?',
                        (new_pnl, current_price, pos.get("id")),
                    )

        conn.commit()
        conn.close()
        await self.refresh_position_cache(force=True)

    async def update_positions_with_live_price(self):
        # This can be called after fetching live price to update PnL
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) if self.db_url else conn.cursor()

        positions = await self.get_positions()
        for pos in positions:
            live_pos = await self.client.get_product_price(pos["symbol"])
            diff = live_pos - pos["entryprice"]
            multiplier = 1 if pos["side"] == "LONG" else -1
            new_pnl = diff * pos["size"] * multiplier
            if self.db_url:
                cursor.execute(
                    'UPDATE positions SET currentprice = %s, unrealized_pnl = %s WHERE id = %s',
                    (live_pos, new_pnl, pos["id"]),
                )
            else:
                cursor.execute(
                    'UPDATE positions SET currentPrice = ?, unrealized_pnl = ? WHERE id = ?',
                    (live_pos, new_pnl, pos["id"]),
                )

        conn.commit()
        conn.close()
        await self.refresh_position_cache(force=True)
        
    async def open_position(self, order:dict, side: str, size: float, price: float, leverage: float, strategy: str):
        wallet = await self.get_wallet()
        margin_req = (size * price) / leverage
        
        if margin_req > wallet["availableBalance"]:
            raise Exception(f"Insufficient paper margin: Need {margin_req}, Have {wallet['availableBalance']}")
        
        pos_id = str(uuid.uuid4())
        position = {
            "id": pos_id,
            "symbol": order.get("symbol"),
            "side": side,
            "entryPrice": price,
            "currentPrice": price,
            "size": size,
            "leverage": leverage,
            "margin": margin_req,
            "unrealized_pnl": 0.0,
            "timestamp": time.time()
        }
        
        conn = self.get_connection()
        should_execute_live_order = (not config.IS_PAPER_TRADING) and config.ALLOW_REAL_ORDER_EXECUTION
        if should_execute_live_order:
            if("BTC" in order.get("symbol")):
                size = size * self.size_map["BTCUSD"] # Convert to contract size for BTC
            elif("ETH" in order.get("symbol")):
                size = size * self.size_map["ETHUSD"] # Convert to contract size for ETH
            await self.client.open_live_position(order, side, size, price, leverage) # Placeholder for live trading logic
        elif not config.IS_PAPER_TRADING:
            logger.info("Live order execution is disabled; recording a paper position in the database instead")
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) if self.db_url else conn.cursor()
        token = '%s' if self.db_url else '?'
        cursor.execute('''
            INSERT INTO positions (id, symbol, side, entryPrice, currentPrice, size, leverage, margin, unrealized_pnl, timestamp,strategy)
            VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0},{0})
            '''.format(token), (pos_id, order.get("symbol"), side, price, price, size, leverage, margin_req, 0.0, time.time(),strategy))
        conn.commit()    
        conn.close()
        await self.refresh_position_cache(force=True)
        
        # Send Telegram alert
        await telegram_bot.send_position_opened(
            symbol=order.get("symbol"),
            side=side,
            size=size,
            price=price,
            leverage=leverage,
            strategy=strategy
        )
        
        logger.info("Position opened: %s %s %.4f @ %.2f", order.get("symbol"), side, size, price)
        
        return position

    async def close_all(self):
        if not config.IS_PAPER_TRADING:
            # For live trading, we would need to fetch all positions and close them via API
            # This is a placeholder for that logic
            response = await self.client.close_all_live_positions()
            if response.get("success"):
                logger.info("Closing all live positions")
            else:
                logger.warning("Error closing live positions: %s", response.get("success"))
        conn = self.get_connection()
        if self.db_url:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        # 1. Archive current positions to trade_history
        positions = await self.get_positions()
        for pos in positions:
            # We assume current price for BTCUSD is the mark price we know
            # For complex multi-symbol we'd need the price map, but for now we'll use btc_price or entryPrice as fallback
            # In a real engine we'd pass the prices here.
            # For now let's just use the unrealized_pnl they have.
            token = '%s' if self.db_url else '?'
            cursor.execute('''
                INSERT INTO trade_history (id, symbol, side, entryPrice, closePrice, size, pnl, timestamp, strategy)
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
            '''.format(token), (
                pos["id"], 
                pos["symbol"], 
                pos["side"], 
                pos["entryPrice"], 
                pos["currentPrice"], # Simplified: using current engine price
                pos["size"], 
                pos["unrealizedPnL"], 
                time.time(),
                pos["strategy"]
            ))
            
            # Send Telegram alert for each closed position
            await telegram_bot.send_position_closed(
                symbol=pos["symbol"],
                side=pos["side"],
                size=pos["size"],
                entry_price=pos["entryPrice"],
                close_price=pos["currentPrice"],
                pnl=pos["unrealizedPnL"],
                strategy=pos.get("strategy", "N/A")
            )
            logger.info("Position closed: %s %s PnL: %.2f", pos["symbol"], pos["side"], pos["unrealizedPnL"])
        
        cursor.execute('DELETE FROM positions')
        conn.commit()
        conn.close()
        self._position_cache = []
        self._position_cache_updated_at = time.time()

    async def get_adaptive_active_strategies(self):
        names = {
            'Iron Condor', 'Bullish Broken Wing Butterfly', 'Bearish Broken Wing Butterfly',
            'Bull Call Debit Spread', 'Bear Put Debit Spread', 'Long Straddle', 'Long Strangle',
            'Futures Momentum',
        }
        positions = await self.get_positions()
        return sorted({position.get('strategy') for position in positions if position.get('strategy') in names})

    async def close_positions_at_expiry_cutoff(self):
        """Close option positions at 5:20 PM IST on their expiry date.

        Positions are closed by strategy so every leg of a multi-leg option
        structure is exited together.  Non-option instruments are ignored.
        """
        strategy_names = set()
        for position in await self.get_positions_from_db():
            expiry = option_expiry_from_symbol(position.get("symbol"))
            strategy = position.get("strategy")
            if expiry and strategy and is_expiry_close_due(expiry):
                strategy_names.add(strategy)

        closed = []
        for strategy_name in sorted(strategy_names):
            if await self.close_position(strategy_name, suppress_missing=True):
                closed.append(strategy_name)
                logger.info(
                    "Closed %s at the 5:20 PM IST expiry cutoff",
                    strategy_name,
                )
        return closed

    async def close_position(self, strategy_name: str, suppress_missing: bool = False):
        conn = self.get_connection()
        if self.db_url:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        token = '%s' if self.db_url else '?'
        cursor.execute(f'SELECT * FROM positions WHERE strategy = {token}', (strategy_name,))
        db_pos = [dict(row) for row in cursor.fetchall()]
        if not db_pos:
            conn.close()
            if suppress_missing:
                return False
            raise Exception("Position not found")
        live_pos = await self.client.get_live_positions() if not config.IS_PAPER_TRADING else {}
        if live_pos and "result" in live_pos:
            for p in live_pos["result"]:
                for db in db_pos:
                    if p.get("product_symbol") == db.get("symbol"):
                        logger.info("Closing live position for %s", p.get("product_symbol"),"live pos",p.get("size"))
                        await self.client.close_live_position(p)
        else:
            live_pos = []
        # Archive to trade_history
        for db in db_pos:
            cursor.execute('''
                INSERT INTO trade_history (id, symbol, side, entryPrice, closePrice, size, pnl, timestamp, strategy)
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
            '''.format(token), (
                db["id"], 
                db["symbol"], 
                db["side"], 
                db["entryprice"], 
                db["currentprice"], # Simplified: using current engine price
                db["size"], 
                db["unrealized_pnl"], 
                time.time(),
                db["strategy"]
            ))
            # Send Telegram alert
            await telegram_bot.send_position_closed(
                symbol=db["symbol"],
                side=db["side"],
                size=db["size"],
                entry_price=db["entryprice"],
                close_price=db["currentprice"],
                pnl=db["unrealized_pnl"],
                strategy=db.get("strategy", "N/A")
            )
            logger.info("Position closed: %s %s PnL: %.2f", db["symbol"], db["side"], db["unrealized_pnl"])
        cursor.execute(f'DELETE FROM positions WHERE strategy = {token}', (strategy_name,))
        conn.commit()
        conn.close()
        await self.refresh_position_cache(force=True)
        return True
        
        

    async def is_broken_wing_butterfly_active(self):
        positions = await self.get_positions()
        active_pos = [pos for pos in positions if pos.get("strategy") == "Broken Wing Butterfly"]
        return len(active_pos) == 4
    
    async def is_directional_active(self):
        positions = await self.get_positions()
        return any(pos.get("strategy") == "Broken Wing Butterfly" for pos in positions)


paper_engine = PaperTradingEngine()
