from paper_trading.engine import paper_engine
from core.config import config
import time

class RiskManager:
    def __init__(self):
        self.max_daily_drawdown = config.MAX_DAILY_LOSS_PCT
        self.max_margin_usage = config.MAX_MARGIN_USAGE_PCT
        self.client = paper_engine.client
        self.directional_enabled = False

    async def check_safety(self):
        wallet = await paper_engine.get_wallet()
        margin_usage = wallet["usedMargin"] / wallet["balance"] if wallet["balance"] > 0 else 0
        
        if margin_usage > self.max_margin_usage:
            return False, "Max margin threshold exceeded"
        
        return True, "Safe"

    async def validate_new_strategy(self, strategy_name: str):
        """Portfolio-level gate called immediately before every adaptive entry."""
        wallet = await paper_engine.get_wallet()
        balance = max(float(wallet['balance']), 0.0)
        if balance <= 0:
            return False, 'Wallet balance is unavailable or non-positive'
        history = paper_engine.get_trade_history()
        day_start = time.time() - (time.time() % 86400)
        daily_loss = -sum(min(0.0, float(t.get('pnl') or 0)) for t in history if float(t.get('timestamp') or 0) >= day_start)
        if daily_loss >= balance * self.max_daily_drawdown:
            return False, 'Maximum daily loss limit reached'
        active = await paper_engine.get_adaptive_active_strategies()
        if len(active) >= config.MAX_CONCURRENT_OPTIONS_POSITIONS:
            return False, 'Maximum concurrent options positions reached'
        margin_usage = float(wallet['usedMargin']) / balance
        if margin_usage >= self.max_margin_usage:
            return False, 'Maximum margin utilisation reached'
        if float(wallet['usedMargin']) >= balance * config.MAX_PORTFOLIO_EXPOSURE_PCT:
            return False, 'Maximum portfolio exposure reached'
        return True, 'Risk validation passed'

    async def volatility_adjusted_size(self, analysis):
        """Scale the configured lot down as ATR rises; never increase it."""
        atr_penalty = max(1.0, float(analysis.atr_pct) / 1.0)
        return max(0.1, min(1.0, config.ADAPTIVE_RISK_PER_TRADE_PCT / .005 / atr_penalty))

    async def get_greeks(self):
        # Move logic from paper engine to here if needed, or query engine
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        positions = await paper_engine.get_positions()
        for pos in positions:
            if("perpetual" in pos.get("contractType")):
                continue # Skip futures for greeks calculation
            ticker = await self.client.get_ticker(pos["symbol"])
            greeks = ticker.get("result", {}).get("greeks", {})
            if(greeks!=None):
                delta = float(greeks.get("delta", 0))
                gamma = float(greeks.get("gamma", 0))
                theta = float(greeks.get("theta", 0))
            else:
                delta = 0.0
                gamma = 0.0
                theta = 0.0
            size = pos["size"]*paper_engine.size_map["BTCUSD"] if("BTC" in pos["symbol"]) else pos["size"]*paper_engine.size_map["ETHUSD"] # Adjust size for BTC if needed
            total_delta += delta/size
            total_gamma += gamma/size
            total_theta += theta/size
        return {"delta": total_delta, "gamma": total_gamma, "theta": total_theta}

risk_manager = RiskManager()
