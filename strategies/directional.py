import logging
from core.config import config
from paper_trading.engine import paper_engine
from risk.manager import risk_manager
import time
from exchange.market_data import market_data
import pandas as pd

logger = logging.getLogger(__name__)

class DirectionalStrategy:
    def __init__(self):
        self.prices_history = []
        self.last_signal = "NEUTRAL"
        self.active_position_id = None
        self.pending_signal = None  # Stores "BULLISH" or "BEARISH" when 30min crossover detected
        self.pending_ema9_5min = None  # Stores the EMA9 value from 5min when signal detected
        self.crossover_threshold_lower = 2  # Small threshold to confirm crossover
        self.crossover_threshold_upper = 100  # Small threshold to confirm crossover
    
    async def generate_signal(self, btc_price: float):
        result = False
        if not btc_price or btc_price <= 0:
            return

        # Get 30min candles for EMA9/EMA20 crossover detection
        await market_data.get_historical_ohlc_candles("BTCUSD", "30m")
        if len(market_data.ohlc_candles) == 0:
            logger.warning("Not enough candles to calculate EMA on 30min")
            return

        # Stage 1: Check for EMA9/EMA20 crossover on 30min candle (if no pending signal)
        if self.pending_signal is None:
            ema_9_30m = self.calculate_ema(9, market_data.ohlc_candles)
            ema_20_30m = self.calculate_ema(20, market_data.ohlc_candles)
            ema_trend = ema_9_30m - ema_20_30m
            
            logger.debug("[Directional Strategy] 30min - EMA9: %.2f, EMA20: %.2f, Trend: %.2f", ema_9_30m, ema_20_30m, ema_trend)
            
            # Detect crossover (EMA9 crosses above/below EMA20)
            if (self.crossover_threshold_lower <= ema_trend <= self.crossover_threshold_upper) and btc_price <= ema_9_30m + 100:
                logger.info("[Directional Strategy] BULLISH crossover detected on 30min at price %s", btc_price)
                self.pending_signal = "BULLISH"
                # Get 5min EMA9 to track for price crossing
                await market_data.get_historical_ohlc_candles("BTCUSD", "5m")
                if len(market_data.ohlc_candles) > 0:
                    self.pending_ema9_5min = self.calculate_ema(9, market_data.ohlc_candles)
                    logger.info("[Directional Strategy] Waiting for price to cross above EMA9(5min): %.2f", self.pending_ema9_5min)
                    
            elif (-self.crossover_threshold_upper <= ema_trend <= -self.crossover_threshold_lower) and btc_price >= ema_9_30m - 100:
                logger.info("[Directional Strategy] BEARISH crossover detected on 30min at price %s", btc_price)
                self.pending_signal = "BEARISH"
                # Get 5min EMA9 to track for price crossing
                await market_data.get_historical_ohlc_candles("BTCUSD", "5m")
                if len(market_data.ohlc_candles) > 0:
                    self.pending_ema9_5min = self.calculate_ema(9, market_data.ohlc_candles)
                    logger.info("[Directional Strategy] Waiting for price to cross below EMA9(5min): %.2f", self.pending_ema9_5min)
            else:
                self.last_signal = "NEUTRAL"
                logger.debug("[Directional Strategy] No crossover detected: %s", self.last_signal)
        
        # Stage 2: Wait for price to cross EMA9 on 5min candle
        elif self.pending_signal is not None and self.pending_ema9_5min is not None:
            # Get fresh 5min candles
            await market_data.get_historical_ohlc_candles("BTCUSD", "5m")
            
            price_crossed = False
            if self.pending_signal == "BULLISH" and btc_price > self.pending_ema9_5min:
                logger.info("[Directional Strategy] Price crossed above 5min EMA9. Current: %s, EMA9: %.2f", btc_price, self.pending_ema9_5min)
                price_crossed = True
                self.last_signal = "BULLISH"
            elif self.pending_signal == "BEARISH" and btc_price < self.pending_ema9_5min:
                logger.info("[Directional Strategy] Price crossed below 5min EMA9. Current: %s, EMA9: %.2f", btc_price, self.pending_ema9_5min)
                price_crossed = True
                self.last_signal = "BEARISH"
            
            # If price crossed, execute trade
            if price_crossed:
                self.pending_signal = None
                self.pending_ema9_5min = None
                risk_manager.directional_enabled = True  # Enable strategy to allow trade execution in run()
                result = await self.run(btc_price, self.last_signal)
                return result
            else:
                logger.debug("[Directional Strategy] Price has not yet crossed the 5min EMA9. Waiting...")
        
        return result

    async def run(self, btc_price: float,trend_signal:str):
        # Check existing positions database to see if we have an active position
        positions = await paper_engine.get_positions()
        active_pos = None
        if self.active_position_id:
            active_pos = next((p for p in positions if p["id"] == self.active_position_id), None)
            if not active_pos:
                # Disappeared/Closed externally (like via Close All)
                self.active_position_id = None

        if risk_manager.directional_enabled:
            # If no active position, deploy in the direction of the signal
            if not self.active_position_id:
                if self.last_signal == "BULLISH":
                    try:
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=0.001, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                        logger.info("[Directional Strategy] Opened LONG position at %s", btc_price)
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to open LONG")
                elif self.last_signal == "BEARISH":
                    try:
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=0.001, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                        logger.info("[Directional Strategy] Opened SHORT position at %s", btc_price)
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to open SHORT")
            else:
                # Manage position reversal
                side = active_pos["side"]
                if side == "LONG" and self.last_signal == "BEARISH":
                    logger.info("[Directional Strategy] Signal reversed. Reversing LONG position at %s", btc_price)
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        
                        # Open short
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=0.001, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to reverse LONG to SHORT")
                elif side == "SHORT" and self.last_signal == "BULLISH":
                    logger.info("[Directional Strategy] Signal reversed. Reversing SHORT position at %s", btc_price)
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        
                        # Open long
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=0.001, price=btc_price, leverage=config.FUTURE_LEVERAGE,strategy ="Strategy 2")
                        self.active_position_id = [i.get("product_id") for i in market_data.instruments if i.get("symbol") == pos.get("symbol")][0]
                    except Exception as e:
                        logger.exception("[Directional Strategy] Failed to reverse SHORT to LONG")
        else:
            # If strategy is disabled but we still have an active position we opened, close it
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
        self.pending_ema9_5min = None

    def calculate_ema(self, ema_length: int, candles=None):
        """Calculate EMA for given candles. If candles not provided, uses global market_data.ohlc_candles"""
        if candles is None:
            candles = market_data.ohlc_candles
        
        k = 2 / (ema_length + 1)
        prices = [candle['close'] for candle in candles]
        df = pd.DataFrame(prices[::-1], columns=['close'])
        df[f'EMA_{ema_length}'] = df['close'].ewm(span=ema_length, adjust=False).mean()
        return df[f'EMA_{ema_length}'].iloc[-1]
    
directional_strategy = DirectionalStrategy()
