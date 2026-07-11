import logging
from core.config import config
from paper_trading.engine import paper_engine
from risk.manager import risk_manager
from exchange.market_data import market_data

logger = logging.getLogger(__name__)

class DirectionalStrategy:
    def __init__(self):
        self.prices_history = []
        self.last_signal = "NEUTRAL"
        self.active_position_id = None
        self.pending_signal = None  # Stores "BULLISH" or "BEARISH" when 30m crossover detected
        self.pending_ema9_15min = None  # Stores the most recent EMA9 value for 15m
        self.last_ema9_15min = None
        self.last_ema20_1h = None
        self.last_ema9_1h = None
        self.crossover_threshold_lower = 2  # Small threshold to confirm crossover
        self.crossover_threshold_upper = 100  # Small threshold to confirm crossover
        self.ema_cache = {
            "1h": {},
            "15m": {}
        }

    async def generate_signal(self, btc_price: float):
        result = False
        if not btc_price or btc_price <= 0:
            return result

        # Load 1h candles once per caching interval
        candles_1h = await market_data.get_historical_ohlc_candles("BTCUSD", "1h")
        if not candles_1h:
            logger.warning("Not enough 1h candles to calculate EMA")
            return result

        ema_9_1h = self.calculate_ema(9, candles_1h, "1h")
        ema_20_1h = self.calculate_ema(20, candles_1h, "1h")
        ema_trend = ema_9_1h - ema_20_1h

        logger.info("[Directional Strategy] 1h - EMA9: %.2f, EMA20: %.2f, Trend: %.2f", ema_9_1h, ema_20_1h, ema_trend)

        if self.pending_signal is None:
            if (self.crossover_threshold_lower <= ema_trend <= self.crossover_threshold_upper) and btc_price <= ema_9_1h + 100:
                logger.info("[Directional Strategy] BULLISH crossover detected on 1h at price %s", btc_price)
                self.pending_signal = "BULLISH"
            elif (-self.crossover_threshold_upper <= ema_trend <= -self.crossover_threshold_lower) and btc_price >= ema_9_1h - 100:
                logger.info("[Directional Strategy] BEARISH crossover detected on 1h at price %s", btc_price)
                self.pending_signal = "BEARISH"
            else:
                self.last_signal = "NEUTRAL"
                logger.debug("[Directional Strategy] No crossover detected: %s", self.last_signal)

            if self.pending_signal:
                candles_15m = await market_data.get_historical_ohlc_candles("BTCUSD", "15m")
                if candles_15m:
                    self.pending_ema9_15min = self.calculate_ema(9, candles_15m, "15m")
                    logger.info("[Directional Strategy] Waiting for price to cross %s EMA9(15m): %.2f", self.pending_signal, self.pending_ema9_15min)
                else:
                    logger.warning("Not enough 15m candles to calculate EMA9 for pending signal")

        elif self.pending_signal and self.pending_ema9_15min is not None:
            candles_15m = await market_data.get_historical_ohlc_candles("BTCUSD", "15m")
            if candles_15m:
                self.pending_ema9_15min = self.calculate_ema(9, candles_15m, "15m")
            else:
                logger.warning("Not enough 15m candles to calculate EMA9 while waiting for crossover")

            price_crossed = False
            if self.pending_signal == "BULLISH" and btc_price > self.pending_ema9_15min:
                logger.info("[Directional Strategy] Price crossed above 15min EMA9. Current: %s, EMA9: %.2f", btc_price, self.pending_ema9_15min)
                price_crossed = True
                self.last_signal = "BULLISH"
            elif self.pending_signal == "BEARISH" and btc_price < self.pending_ema9_15min:
                logger.info("[Directional Strategy] Price crossed below 15min EMA9. Current: %s, EMA9: %.2f", btc_price, self.pending_ema9_15min)
                price_crossed = True
                self.last_signal = "BEARISH"

            if price_crossed:
                self.pending_signal = None
                self.pending_ema9_15min = None
                risk_manager.directional_enabled = True
                result = await self.run(btc_price, self.last_signal)
                return result
            else:
                logger.debug("[Directional Strategy] Price has not yet crossed the 15min EMA9. Waiting...")

        return result

    async def run(self, btc_price: float,trend_signal:str):
        # Check existing positions database to see if we have an active position
        positions = await paper_engine.get_positions()
        active_pos = None
        if self.active_position_id:
            active_pos = next((p for p in positions if p["id"] == self.active_position_id), None)
            if not active_pos:
                self.active_position_id = None

        if risk_manager.directional_enabled:
            if not self.active_position_id:
                if self.last_signal == "BULLISH":
                    try:
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=config.LOT_SIZE, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                        logger.info("[Directional Strategy] Opened LONG position at %s", btc_price)
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to open LONG")
                elif self.last_signal == "BEARISH":
                    try:
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=config.LOT_SIZE, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                        logger.info("[Directional Strategy] Opened SHORT position at %s", btc_price)
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to open SHORT")
            else:
                side = active_pos["side"]
                if side == "LONG" and self.last_signal == "BEARISH":
                    logger.info("[Directional Strategy] Signal reversed. Reversing LONG position at %s", btc_price)
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=config.LOT_SIZE, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to reverse LONG to SHORT")
                elif side == "SHORT" and self.last_signal == "BULLISH":
                    logger.info("[Directional Strategy] Signal reversed. Reversing SHORT position at %s", btc_price)
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=config.LOT_SIZE, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to reverse SHORT to LONG")
        else:
            if self.active_position_id and active_pos:
                logger.info("[Directional Strategy] Strategy disabled. Closing active strategy position at %s", btc_price)
                try:
                    await paper_engine.close_position(self.active_position_id, btc_price)
                except Exception as e:
                    logger.exception("[Directional Strategy] Error closing position on disable")
                self.active_position_id = None
        if self.active_position_id:
            logger.debug("[Directional Strategy] Active position ID: %s, Current Signal: %s", self.active_position_id, self.last_signal)
            return True
        else:
            logger.debug("[Directional Strategy] No active position, Current Signal: %s", self.last_signal)
            return False

    def reset(self):
        self.active_position_id = None
        self.last_signal = "NEUTRAL"
        self.pending_signal = None
        self.pending_ema9_15min = None

    def calculate_ema(self, ema_length: int, candles=None, timeframe: str = "30m"):
        if candles is None:
            candles = market_data.ohlc_candles
        prices = [float(candle['close']) for candle in candles]

        cache_key = f"EMA_{ema_length}"
        cached = self.ema_cache.get(timeframe, {}).get(cache_key)
        if cached and len(cached.get("prices", [])) == len(prices):
            return cached["value"]

        k = 2 / (ema_length + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = price * k + ema * (1 - k)

        self.ema_cache.setdefault(timeframe, {})[cache_key] = {
            "value": ema,
            "prices": prices
        }
        return ema
    

directional_strategy = DirectionalStrategy()
