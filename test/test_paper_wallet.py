import asyncio

from core.config import config
from paper_trading.engine import PaperTradingEngine


def test_get_wallet_uses_configured_paper_balance(monkeypatch):
    engine = PaperTradingEngine.__new__(PaperTradingEngine)
    engine.real_wallet_data = {}

    async def fake_get_positions():
        return []

    monkeypatch.setattr(config, "PAPER_WALLET_BALANCE", 250000.0, raising=False)
    engine.get_positions = fake_get_positions

    wallet = asyncio.run(engine.get_wallet())

    assert wallet["balance"] == 250000.0
    assert wallet["availableBalance"] == 250000.0
    assert wallet["totalEquity"] == 250000.0
