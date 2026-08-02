import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from paper_trading.engine import PaperTradingEngine
from strategies.selection_engine import StrategySelectionEngine


class DummyMarketAnalyzer:
    def __init__(self):
        self.regime = 'STRONG_BULLISH'
        self.confidence = 0.95
        self.reasons = []

    def to_dict(self):
        return {'regime': self.regime, 'confidence': self.confidence, 'reasons': self.reasons}


def test_cache_refresh_and_futures_fallback(monkeypatch):
    engine = PaperTradingEngine()
    engine._position_cache = []
    engine._position_cache_updated_at = 0

    async def fake_get_positions_from_db():
        return [{"id": "1", "symbol": "BTCUSD", "side": "LONG", "entryPrice": 100.0, "currentPrice": 101.0, "size": 1.0, "leverage": 10.0, "margin": 10.0, "unrealized_pnl": 1.0, "timestamp": 1.0, "strategy": "demo"}]

    monkeypatch.setattr(engine, "get_positions_from_db", fake_get_positions_from_db)

    async def fake_get_positions():
        return [{"id": "1", "symbol": "BTCUSD", "side": "LONG", "entryPrice": 100.0, "currentPrice": 101.0, "size": 1.0, "leverage": 10.0, "margin": 10.0, "unrealized_pnl": 1.0, "timestamp": 1.0, "strategy": "demo"}]

    monkeypatch.setattr(engine, "get_positions", fake_get_positions)

    async def fake_run_cycle(price, tickers):
        return None

    monkeypatch.setattr("strategies.selection_engine.market_analyzer.analyze", lambda *args, **kwargs: DummyMarketAnalyzer())
    monkeypatch.setattr("strategies.selection_engine.market_data.get_historical_ohlc_candles", lambda *args, **kwargs: [])
    monkeypatch.setattr(StrategySelectionEngine, "monitor_positions", lambda self: None)

    async def main():
        await engine.refresh_position_cache(force=True)
        cached = engine.get_cached_positions()
        assert cached[0]["id"] == "1"
        assert engine._position_cache_updated_at > 0

        selector = StrategySelectionEngine()
        selector.enabled = True
        selector.last_decision = {"status": "idle", "selectedStrategy": None, "confidence": 0.0, "reason": ""}
        selector.opened_at = {}
        selector.strategies = {"Futures Momentum": object()}
        selector.enabled_strategies = set(selector.strategies)

        async def fake_validate_new_strategy(name):
            return True, "ok"

        async def fake_volatility_adjusted_size(analysis):
            return 0.5

        class DummyStrategy:
            async def execute(self, price, size):
                return True, "opened"

        selector.strategies["Futures Momentum"] = DummyStrategy()
        monkeypatch.setattr("strategies.selection_engine.risk_manager.validate_new_strategy", fake_validate_new_strategy)
        monkeypatch.setattr("strategies.selection_engine.risk_manager.volatility_adjusted_size", fake_volatility_adjusted_size)

        result = await selector.run_cycle(100.0, [])
        assert result["selectedStrategy"] == "Futures Momentum"

    asyncio.run(main())
