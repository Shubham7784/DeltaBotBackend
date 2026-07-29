import sys
import types

# The focused analysis tests do not need dotenv, which is installed in normal
# application deployments but not in this bare test interpreter.
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from core.market_analysis import market_analyzer


def _candles():
    return [
        {
            "time": index,
            "open": 1000 + index,
            "high": 1000.5 + index,
            "low": 999.5 + index,
            "close": 1000 + index,
            "volume": 1000,
        }
        for index in range(30)
    ]


def test_candles_are_analyzed_in_time_order():
    candles = _candles()
    forward = market_analyzer.analyze(1029, candles)
    reversed_input = market_analyzer.analyze(1029, list(reversed(candles)))
    assert forward.ema20 == reversed_input.ema20
    assert forward.rsi == reversed_input.rsi


def test_funding_alone_does_not_trigger_high_volatility():
    analysis = market_analyzer.analyze(
        1029,
        _candles(),
        tickers=[{"symbol": "BTCUSD", "funding_rate": "0.30"}],
        options=[{"contract_type": "call_options", "mark_vol": "0.176"}],
    )
    assert round(analysis.iv, 1) == 17.6
    assert analysis.regime != "HIGH_VOLATILITY_EVENT"


def test_high_normalized_option_iv_triggers_high_volatility():
    analysis = market_analyzer.analyze(
        1029,
        _candles(),
        options=[{"contract_type": "call_options", "mark_vol": "0.80"}],
    )
    assert analysis.iv == 80.0
    assert analysis.regime == "HIGH_VOLATILITY_EVENT"
