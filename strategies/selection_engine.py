"""Selects, validates and monitors exactly one adaptive options strategy."""
import logging
import time
from core.config import config
from core.market_analysis import market_analyzer
from exchange.market_data import market_data
from paper_trading.engine import paper_engine
from risk.manager import risk_manager
from strategies.adaptive_options import IronCondor, BrokenWingButterfly, DebitSpread, LongStraddle, LongStrangle

logger = logging.getLogger(__name__)


class StrategySelectionEngine:
    def __init__(self):
        self.enabled = config.ADAPTIVE_TRADING_ENABLED
        self.strategies = {
            'Iron Condor': IronCondor(), 'Bullish Broken Wing Butterfly': BrokenWingButterfly(True),
            'Bearish Broken Wing Butterfly': BrokenWingButterfly(False), 'Bull Call Debit Spread': DebitSpread(True),
            'Bear Put Debit Spread': DebitSpread(False), 'Long Straddle': LongStraddle(), 'Long Strangle': LongStrangle(),
        }
        self.enabled_strategies = set(self.strategies)
        self.last_decision = {'status': 'idle', 'selectedStrategy': None, 'confidence': 0.0, 'reason': ''}
        self.opened_at = {}

    def _scores(self, analysis):
        regime_map = {
            'SIDEWAYS': {'Iron Condor': .90}, 'MILD_BULLISH': {'Bullish Broken Wing Butterfly': .85, 'Bull Call Debit Spread': .65},
            'MILD_BEARISH': {'Bearish Broken Wing Butterfly': .85, 'Bear Put Debit Spread': .65},
            'STRONG_BULLISH': {'Bull Call Debit Spread': .92}, 'STRONG_BEARISH': {'Bear Put Debit Spread': .92},
            'HIGH_VOLATILITY_EVENT': {'Long Straddle': .82, 'Long Strangle': .76},
        }
        values = regime_map.get(analysis.regime, {})
        return {name: round(score * analysis.confidence, 3) for name, score in values.items() if name in self.enabled_strategies}

    async def run_cycle(self, price, tickers):
        candles = await market_data.get_historical_ohlc_candles('BTCUSD', '4h')
        analysis = market_analyzer.analyze(price, candles, tickers, market_data.btc_options)
        await self.monitor_positions()
        active = await paper_engine.get_adaptive_active_strategies()
        if active:
            self.last_decision = {'status': 'monitoring', 'selectedStrategy': active[0], 'confidence': analysis.confidence, 'reason': 'An options strategy is already active', 'analysis': analysis.to_dict()}
            return self.last_decision
        if not self.enabled:
            self.last_decision = {'status': 'disabled', 'selectedStrategy': None, 'confidence': analysis.confidence, 'reason': 'Adaptive trading is disabled', 'analysis': analysis.to_dict()}
            return self.last_decision
        scores = self._scores(analysis)
        if not scores:
            self.last_decision = {'status': 'no_trade', 'selectedStrategy': None, 'confidence': analysis.confidence, 'reason': 'No strategy received enough market confirmations', 'analysis': analysis.to_dict(), 'scores': scores}
            return self.last_decision
        name = max(scores, key=scores.get)
        safe, reason = await risk_manager.validate_new_strategy(name)
        if not safe:
            self.last_decision = {'status': 'risk_rejected', 'selectedStrategy': name, 'confidence': scores[name], 'reason': reason, 'analysis': analysis.to_dict(), 'scores': scores}
            return self.last_decision
        success, reason = await self.strategies[name].execute(price, await risk_manager.volatility_adjusted_size(analysis))
        if success: self.opened_at[name] = time.time()
        self.last_decision = {'status': 'executed' if success else 'entry_rejected', 'selectedStrategy': name, 'confidence': scores[name], 'reason': reason, 'analysis': analysis.to_dict(), 'scores': scores}
        return self.last_decision

    async def monitor_positions(self):
        positions = await paper_engine.get_positions()
        grouped = {}
        for position in positions:
            if position.get('strategy') in self.strategies: grouped.setdefault(position['strategy'], []).append(position)
        for name, legs in grouped.items():
            pnl = sum(leg['unrealizedPnL'] for leg in legs); entry_value = sum(abs(leg['entryPrice'] * leg['size']) for leg in legs) or 1
            rule = self.strategies[name]; elapsed = time.time() - self.opened_at.get(name, min(leg.get('timestamp', time.time()) for leg in legs))
            if pnl / entry_value >= rule.profit_target or pnl / entry_value <= -rule.stop_loss or elapsed >= rule.max_hold_hours * 3600:
                logger.info('Closing %s: strategy exit rule met', name)
                await paper_engine.close_position(name, suppress_missing=True)
                self.opened_at.pop(name, None)

    def position_summary(self, positions):
        """Frontend-ready aggregate while preserving each option leg."""
        adaptive_legs = [p for p in positions if p.get('strategy') in self.strategies]
        if not adaptive_legs:
            return None
        strategy = adaptive_legs[0].get('strategy')
        return {
            'strategy': strategy,
            'legs': adaptive_legs,
            'legCount': len(adaptive_legs),
            'unrealizedPnL': sum(float(p.get('unrealizedPnL') or 0) for p in adaptive_legs),
            'margin': sum(float(p.get('margin') or 0) for p in adaptive_legs),
            'openedAt': min(float(p.get('timestamp') or 0) for p in adaptive_legs),
        }

    def status(self, positions=None):
        analysis = self.last_decision.get('analysis') or {}
        # Keep these fields top-level as a stable WebSocket/API contract for
        # dashboards that do not consume the full nested analysis object.
        summary = self.position_summary(positions) if positions is not None else None
        return {
            **self.last_decision,
            'enabled': self.enabled,
            'enabledStrategies': sorted(self.enabled_strategies),
            'marketRegime': analysis.get('regime', 'UNKNOWN'),
            'marketRegimeConfidence': analysis.get('confidence', 0.0),
            'marketRegimeReasons': analysis.get('reasons', []),
            'activePosition': summary,
        }


strategy_selector = StrategySelectionEngine()
