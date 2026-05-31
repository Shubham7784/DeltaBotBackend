from core.config import config
from paper_trading.engine import paper_engine

class HedgeManager:
    def __init__(self):
        self.active_hedge = []

    async def rebalance(self, net_delta: float, current_price: float):
        try:
            if abs(net_delta) < -0.20:
                needed_size = paper_engine.size
                side = "buy"
                pos = await paper_engine.open_position("BTCUSD", side, needed_size, current_price,config.FUTURE_LEVERAGE,"Strategy 1 Hedge")
                self.active_hedge.append(pos["id"])
            elif abs(net_delta) > 0.20:
                needed_size = paper_engine.size
                side = "sell"
                pos = await paper_engine.open_position("BTCUSD", side, needed_size, current_price, config.FUTURE_LEVERAGE,"Strategy 1 Hedge")
                self.active_hedge.append(pos["id"])
            else:
            # Close existing hedge
                if self.active_hedge:
                    # Simplified check if id still exists
                    active_positions = await paper_engine.get_positions()
                    for ah in self.active_hedge:
                        for ap in active_positions:
                            if ah == ap["id"]:
                                await paper_engine.close_position(self.active_hedge)
                                self.active_hedge.pop(ah)
        except Exception as e:
            print(f"Hedge rebalance error: {e}")

    def reset(self):
        self.active_hedge.clear()

hedge_manager = HedgeManager()
