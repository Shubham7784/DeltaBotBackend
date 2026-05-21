from ..paper_trading.engine import paper_engine
from ..core.config import config

class RiskManager:
    def __init__(self):
        self.max_daily_drawdown = 0.02 # 2%
        self.max_margin_usage = 0.8 # 80%
        self.client = paper_engine.client

    async def check_safety(self):
        wallet = await paper_engine.get_wallet()
        margin_usage = wallet["usedMargin"] / wallet["balance"] if wallet["balance"] > 0 else 0
        
        if margin_usage > self.max_margin_usage:
            return False, "Max margin threshold exceeded"
        
        return True, "Safe"

    async def get_greeks(self):
        # Move logic from paper engine to here if needed, or query engine
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        positions = await paper_engine.get_positions()
        for pos in positions:
            ticker = await self.client.get_ticker(pos["symbol"])
            greeks = ticker.get("result", {}).get("greeks", {})
            delta = float(greeks.get("delta", 0))
            gamma = float(greeks.get("gamma", 0))
            theta = float(greeks.get("theta", 0))
            size = pos["size"]*paper_engine.size_map["BTC"] if("BTC" in pos["symbol"]) else pos["size"]*paper_engine.size_map[pos["ETH"]] # Adjust size for BTC if needed
            total_delta += delta/size
            total_gamma += gamma/size
            total_theta += theta/size
        return {"delta": total_delta, "gamma": total_gamma, "theta": total_theta}

risk_manager = RiskManager()
