from paper_trading.engine import paper_engine
from risk.manager import risk_manager
import time
from exchange.market_data import market_data
import pandas as pd

class DirectionalStrategy:
    def __init__(self):
        self.prices_history = []
        self.last_signal = "NEUTRAL"
        self.active_position_id = None
    
    async def generate_signal(self, btc_price: float):
        result = False
        if not btc_price or btc_price <= 0:
            return

        await market_data.get_historical_ohlc_candles("BTCUSD","1h") # Ensure we have candles for EMA calculation
        if(len(market_data.ohlc_candles)==0):
            print("Not enough candles to calculate EMA")
            return 

        ema_9 = self.calculate_ema(9)
        ema_20 = self.calculate_ema(20)
        # Determine signal based on EMA trend
        buffer = 5.0 # small noise filter
        ema_trend = ema_9 - ema_20
        if ema_trend > 0 and ema_9 + 300 <=btc_price:
            result = await self.run(btc_price,"BULLISH")
        elif ema_trend < 0 and ema_9 - 300 >= btc_price:
            result = await self.run(btc_price,"BEARISH")
        else:
            self.last_signal = "NEUTRAL"
            print("No trades are placed as the signal is NEUTRAL")
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
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=0.001, price=btc_price, leverage=100.0)
                        self.active_position_id = pos["id"]
                        print(f"[Directional Strategy] Opened LONG position at {btc_price}")
                    except Exception as e:
                        print(f"[Directional Strategy] Failed to open LONG: {e}")
                elif self.last_signal == "BEARISH":
                    try:
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=0.001, price=btc_price, leverage=100.0)
                        self.active_position_id = pos["id"]
                        print(f"[Directional Strategy] Opened SHORT position at {btc_price}")
                    except Exception as e:
                        print(f"[Directional Strategy] Failed to open SHORT: {e}")
            else:
                # Manage position reversal
                side = active_pos["side"]
                if side == "LONG" and self.last_signal == "BEARISH":
                    print(f"[Directional Strategy] Signal reversed. Reversing LONG position at {btc_price}")
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        
                        # Open short
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "SHORT", size=0.001, price=btc_price, leverage=100.0)
                        self.active_position_id = pos["id"]
                    except Exception as e:
                        print(f"[Directional Strategy] Failed to reverse LONG to SHORT: {e}")
                elif side == "SHORT" and self.last_signal == "BULLISH":
                    print(f"[Directional Strategy] Signal reversed. Reversing SHORT position at {btc_price}")
                    try:
                        await paper_engine.close_position(self.active_position_id, btc_price)
                        self.active_position_id = None
                        
                        # Open long
                        pos = await paper_engine.open_position(market_data.btc_futures[0], "LONG", size=0.001, price=btc_price, leverage=100.0)
                        self.active_position_id = pos["id"]
                    except Exception as e:
                        print(f"[Directional Strategy] Failed to reverse SHORT to LONG: {e}")
        else:
            # If strategy is disabled but we still have an active position we opened, close it
            if self.active_position_id and active_pos:
                print(f"[Directional Strategy] Strategy disabled. Closing active strategy position at {btc_price}")
                try:
                    await paper_engine.close_position(self.active_position_id, btc_price)
                except Exception as e:
                    print(f"[Directional Strategy] Error closing position on disable: {e}")
                self.active_position_id = None
        if(self.active_position_id):
            print(f"[Directional Strategy] Active position ID: {self.active_position_id}, Current Signal: {self.last_signal}")
            return True
        else:
            print(f"[Directional Strategy] No active position, Current Signal: {self.last_signal}")
            return False

    def reset(self):
        self.active_position_id = None
        self.last_signal = "NEUTRAL"

    def calculate_ema(self,ema_length:int):
        k = 2/(ema_length + 1)
        candles = [candle['close'] for candle in market_data.ohlc_candles]
        df = pd.DataFrame(candles, columns=['close'])
        df[f'EMA_{ema_length}'] = df['close'].ewm(span=ema_length, adjust=False).mean()
        return df[f'EMA_{ema_length}'].iloc[-1]
    
directional_strategy = DirectionalStrategy()
