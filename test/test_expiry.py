import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from core.expiry import IST, is_expiry_close_due, option_expiry_from_symbol
from paper_trading.engine import PaperTradingEngine


def test_reads_expiry_from_delta_option_symbol():
    assert option_expiry_from_symbol("C-BTC-70000-300726") == datetime(2026, 7, 30)
    assert option_expiry_from_symbol("BTCUSD") is None


def test_expiry_cutoff_is_520_pm_ist():
    expiry = datetime(2026, 7, 30)
    assert not is_expiry_close_due(expiry, datetime(2026, 7, 30, 17, 19, tzinfo=IST))
    assert is_expiry_close_due(expiry, datetime(2026, 7, 30, 17, 20, tzinfo=IST))


def test_expiry_cutoff_closes_due_positions_without_strategy(monkeypatch):
    engine = PaperTradingEngine()
    due_positions = [{
        "id": "pos-1",
        "symbol": "C-BTC-70000-300726",
        "strategy": None,
        "side": "LONG",
        "entryprice": 1000.0,
        "currentprice": 1000.0,
        "size": 1.0,
        "unrealized_pnl": 0.0,
    }]
    closed = []

    async def fake_get_positions_from_db():
        return due_positions

    async def fake_close_position(position_key, suppress_missing=False):
        closed.append(position_key)
        return True

    monkeypatch.setattr(engine, "get_positions_from_db", fake_get_positions_from_db)
    monkeypatch.setattr(engine, "close_position", fake_close_position)

    asyncio.run(engine.close_positions_at_expiry_cutoff(now=datetime(2026, 7, 30, 17, 20, tzinfo=IST)))

    assert closed == ["pos-1"]
