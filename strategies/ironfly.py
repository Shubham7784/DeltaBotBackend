from core.config import config
from exchange.market_data import market_data
from paper_trading.engine import paper_engine
import math
from exchange.client import DeltaClient
import time
class IronFlyStrategy:
    def __init__(self):
        self.active_legs = [] # Load any existing legs from paper engine on startup
        self.client = DeltaClient()

    async def execute(self, current_price: float, wing_width: float = 400.0):
        if self.active_legs:
            return False, "Strategy already active"

        expiry = market_data.get_nearest_expiry()
        if not expiry:
            return False, "No expiry found"

        options = market_data.get_options_by_expiry(expiry)
        
        # Center Strike with 200-400 point bias as requested
        center_strike = round((current_price + 200) / 100) * 100
        call_strike = center_strike + wing_width
        put_strike = center_strike - wing_width

        legs = [
            {"type": "call", "strike": center_strike, "side": "SHORT"},
            {"type": "put", "strike": center_strike, "side": "SHORT"},
            {"type": "call", "strike": call_strike, "side": "LONG"},
            {"type": "put", "strike": put_strike, "side": "LONG"},
        ]

        # Find specific instruments
        found_legs = []
        for leg in legs:
            inst = []
            for o in options:
                if leg["type"] == "call" and (o.get("contract_type")=="call_options") and (abs(leg["strike"]-float(o.get("strike_price")))<= 100) : # Allow some tolerance for strike matching
                    inst = o
                    break
                elif leg["type"] == "put" and (o.get("contract_type")=="put_options") and (abs(leg["strike"]-float(o.get("strike_price")))<= 100) : # Allow some tolerance for strike matching
                    inst = o
                    break
            if inst:
                found_legs.append(inst)

        if len(found_legs) < 4:
            return False, "Could not find all required option legs"

        # Open in paper engine
        for inst in found_legs:
            side = "SHORT" if abs(float(inst.get("strike_price"))-center_strike)<=100 else "LONG" # Logic check
            # For simplicity in V1 Python port:
            live_price = await self.client.get_product_price(inst.get("symbol"))
            await paper_engine.open_position(inst, side, 0.001, live_price,config.OPTION_LEVERAGE,"Strategy 1") # Use config for leverage
            time.sleep(7)
        
        self.active_legs = [i.get("symbol") for i in found_legs]
        return True, "Executed"

    def reset(self):
        self.active_legs = []

iron_fly = IronFlyStrategy()
