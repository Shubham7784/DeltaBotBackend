import logging
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

    def get_connection(self):
        if self.db_url:
            try:
                return psycopg2.connect(self.db_url)
            except Exception:
                logger.warning("Could not connect to Postgres at DATABASE_URL, falling back to local sqlite database")
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
        conn.close()

    def update_real_wallet(self, data: dict):
        # Data is list of assets from Delta
        self.real_wallet_data = data.get("result", {})

    async def get_wallet(self):
        # Use real balance from Delta if available (e.g. USDT or BTC)
        usdt_data = {}
        for asset in self.real_wallet_data:
            if asset.get("asset_symbol") == "USD":
                usdt_data = asset
        real_balance = float(usdt_data.get("balance", -1))
        
        positions = await self.get_positions()
        total_pnl = sum(p["unrealizedPnL"] for p in positions)
        used_margin = sum(p["margin"] for p in positions)
        
        equity = real_balance + total_pnl
        
        return {
            "balance": real_balance,
            "usedMargin": used_margin,
            "availableBalance": real_balance - used_margin,
            "totalEquity": equity,
            "totalUnrealizedPnL": total_pnl,
            "asset": "USDT"
        }

    async def get_positions(self):
        positions = []
        if(not config.IS_PAPER_TRADING):
            live_pos = await self.client.get_live_positions()
            self.client.user_id = live_pos.get("result", [{}])[0].get("user_id", 0) if live_pos.get("result") else 0
            for pos in live_pos.get("result", []):
                lot_size = self.size_map.get("BTCUSD") if("BTC" in pos.get("product_symbol", "")) else self.size_map.get("ETHUSD") if("ETH" in pos.get("product_symbol", "")) else 1
                positions.append({
                    "id": pos.get("product_id"),
                    "symbol": pos.get("product_symbol"),
                    "side": "LONG" if pos.get("size", 0) > 0 else "SHORT",
                    "entryPrice": float(pos.get("entry_price", 0)),
                    "currentPrice": float(pos.get("mark_price", 0)),
                    "size": float(pos.get("size", 0)),
                    "leverage": float(pos.get("leverage", 0)),
                    "margin": float(pos.get("margin", 0)),
                    "unrealizedPnL": (((float(pos.get("mark_price",0)) - float(pos.get("entry_price", 0)))* float(pos.get("size", 0)) / 1000)),
                    "contractType": pos.get("product", {}).get("contract_type"),
                    "timestamp": pos.get("timestamp")
                })
        else:
            conn = self.get_connection()
            if self.db_url:
                # Postgres: use RealDictCursor for dict-like rows
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
            cursor.execute('SELECT * FROM positions')
            rows = cursor.fetchall()
            for row in rows:
                d = {k.lower(): v for k, v in dict(row).items()}
                # Frontend expects camelCase but we also provide snake_case/lowercase for fallbacks
                pos = {
                    "id": d.get("id"),
                    "symbol": d.get("symbol", ""),
                    "side": d.get("side", ""),
                    "entryPrice": float(d.get("entryprice") or d.get("entry_price") or 0),
                    "currentPrice": float(d.get("currentprice") or d.get("current_price") or 0),
                    "size": float(d.get("size") or 0),
                    "leverage": float(d.get("leverage") or 0),
                    "margin": float(d.get("margin") or 0),
                    "unrealizedPnL": float(d.get("unrealized_pnl") or 0),
                    "timestamp": d.get("timestamp"),
                    "strategy": d.get("strategy")
                }
            # For extreme resilience, duplicate fields if needed
            pos["entryprice"] = pos["entryPrice"]
            pos["currentprice"] = pos["currentPrice"]
            positions.append(pos)
            conn.close()
        return positions

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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if self.db_url else conn.cursor()
        cursor.execute('SELECT * FROM trade_history ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        history = [dict(row) for row in rows]
        conn.close()
        return history


    async def update_prices(self, price_map: Dict[str, float]):
        """Updates unrealized PnL for all positions based on a symbol->price map."""
        if "BTCUSD" in price_map:
            self.btc_price = price_map["BTCUSD"]
            
        conn = self.get_connection()
        cursor = conn.cursor()
        
        positions = await self.get_positions()
        for pos in positions:
            symbol = pos["symbol"]
            current_price = price_map.get(symbol)
            
            if current_price is not None and config.IS_PAPER_TRADING:
                # Basic PnL: (Current - Entry) * Size * Multiplier
                # For Inverse products (like BTC/USD on Delta) the calculation is more complex,
                # but for Paper Trading V1 we'll stick to Linear simulation.
                diff = current_price - pos["entryPrice"]
                multiplier = 1 if pos["side"] == "LONG" else -1
                new_pnl = diff * pos["size"] * multiplier
                cursor.execute('UPDATE positions SET unrealized_pnl = %s, currentprice = %s WHERE id = %s', (new_pnl, current_price, pos["id"]))
        
        conn.commit()
        conn.close()

    async def update_positions_with_live_price(self):
        # This can be called after fetching live price to update PnL
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        positions = await self.get_positions()
        for pos in positions:
            live_pos = await self.client.get_product_price(pos["symbol"])
            diff = live_pos - pos["entryprice"]
            multiplier = 1 if pos["side"] == "LONG" else -1
            new_pnl = diff * pos["size"] * multiplier
            cursor.execute(f'UPDATE positions SET currentPrice = %s, unrealized_pnl = %s WHERE id = %s', (live_pos, new_pnl, pos["id"]))
        
        conn.commit()
        conn.close()
        
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
        if(not config.IS_PAPER_TRADING):
            if("BTC" in order.get("symbol")):
                size = size * self.size_map["BTCUSD"] # Convert to contract size for BTC
            elif("ETH" in order.get("symbol")):
                size = size * self.size_map["ETHUSD"] # Convert to contract size for ETH
            await self.client.open_live_position(order, side, size, price, leverage) # Placeholder for live trading logic
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            INSERT INTO positions (id, symbol, side, entryPrice, currentPrice, size, leverage, margin, unrealized_pnl, timestamp,strategy)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
            ''', (pos_id, order.get("symbol"), side, price, price, size, leverage, margin_req, 0.0, time.time(),strategy))
        conn.commit()    
        conn.close()
        
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # 1. Archive current positions to trade_history
        positions = await self.get_positions()
        for pos in positions:
            # We assume current price for BTCUSD is the mark price we know
            # For complex multi-symbol we'd need the price map, but for now we'll use btc_price or entryPrice as fallback
            # In a real engine we'd pass the prices here.
            # For now let's just use the unrealized_pnl they have.
            cursor.execute('''
                INSERT INTO trade_history (id, symbol, side, entryPrice, closePrice, size, pnl, timestamp, strategy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
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

    async def close_position(self, strategy_name: str):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM positions WHERE strategy = %s', (strategy_name,))
        db_pos = cursor.fetchall()
        if not db_pos:
            conn.close()
            raise Exception("Position not found")
        live_pos = await self.client.get_live_positions()
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
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
        cursor.execute('DELETE FROM positions WHERE strategy = %s', (strategy_name,))
        conn.commit()
        conn.close()
        
        

    async def is_broken_wing_butterfly_active(self):
        positions = await self.get_positions_from_db()
        active_pos = [pos for pos in positions if pos.get("strategy") == "Broken Wing Butterfly"]
        return len(active_pos) == 4
    
    async def is_directional_active(self):
        positions = await self.get_positions_from_db()
        return any(pos.get("strategy") == "Broken Wing Butterfly" for pos in positions)


paper_engine = PaperTradingEngine()
