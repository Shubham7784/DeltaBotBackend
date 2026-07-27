"""Option strategy implementations used by the adaptive selector.

All strategies share one atomic multi-leg executor so paper and live paths stay
identical.  Quotes are collected before an order is submitted to avoid a
partially opened structure.
"""
from dataclasses import dataclass
from core.config import config
from core.expiry_selection import expiry_selector
from exchange.client import DeltaClient
from exchange.market_data import market_data
from paper_trading.engine import paper_engine


@dataclass
class Leg:
    option: dict; side: str; quantity: float


class OptionStrategy:
    strategy_name = 'Option Strategy'; family = 'default'; profit_target = .30; stop_loss = .50; max_hold_hours = 24
    def __init__(self): self.client = DeltaClient()
    def eligible(self, analysis): return True
    def select_legs(self, calls, puts, price): raise NotImplementedError

    @staticmethod
    def _nearest(options, target): return min(options, key=lambda x: abs(float(x['strike_price']) - target))

    async def build(self, price):
        expiry = expiry_selector.select(market_data.get_option_expiries(), self.family)
        if not expiry: return None, 'No eligible option expiry'
        options = market_data.get_options_by_expiry(expiry)
        calls = sorted([x for x in options if x.get('contract_type') == 'call_options'], key=lambda x: float(x['strike_price']))
        puts = sorted([x for x in options if x.get('contract_type') == 'put_options'], key=lambda x: float(x['strike_price']))
        legs = self.select_legs(calls, puts, price)
        return legs, 'No valid listed strikes for strategy' if not legs else ''

    async def execute(self, price, risk_fraction=1.0):
        if await self.is_active(): return False, 'An adaptive option position is already active'
        legs, reason = await self.build(price)
        if not legs: return False, reason
        quotes = [await self.client.get_product_price(leg.option['symbol']) for leg in legs]
        if any(q is None or float(q) <= 0 for q in quotes): return False, 'One or more option legs could not be priced'
        size = max(config.LOT_SIZE * risk_fraction, config.LOT_SIZE * .1)
        margin = sum(size * leg.quantity * float(q) / config.OPTION_LEVERAGE for leg, q in zip(legs, quotes))
        wallet = await paper_engine.get_wallet()
        if margin > wallet['availableBalance']: return False, 'Insufficient available margin'
        try:
            for leg, quote in zip(legs, quotes):
                await paper_engine.open_position(leg.option, leg.side, size * leg.quantity, float(quote), config.OPTION_LEVERAGE, self.strategy_name)
        except Exception:
            await paper_engine.close_position(self.strategy_name, suppress_missing=True)
            raise
        return True, f'{self.strategy_name} executed with {len(legs)} legs'

    async def is_active(self):
        return any(p.get('strategy') == self.strategy_name for p in await paper_engine.get_positions_from_db())


class IronCondor(OptionStrategy):
    strategy_name = 'Iron Condor'; family = 'premium_selling'; profit_target = .50; stop_loss = .75; max_hold_hours = 12
    def select_legs(self, calls, puts, price):
        if len(calls) < 4 or len(puts) < 4: return []
        step = abs(float(calls[min(1, len(calls)-1)]['strike_price']) - float(calls[0]['strike_price']))
        return [Leg(self._nearest(puts, price-2*step), 'LONG', 1), Leg(self._nearest(puts, price-step), 'SHORT', 1), Leg(self._nearest(calls, price+step), 'SHORT', 1), Leg(self._nearest(calls, price+2*step), 'LONG', 1)]


class BrokenWingButterfly(OptionStrategy):
    family = 'butterfly'; max_hold_hours = 30
    def __init__(self, bullish): super().__init__(); self.bullish = bullish; self.strategy_name = 'Bullish Broken Wing Butterfly' if bullish else 'Bearish Broken Wing Butterfly'
    def select_legs(self, calls, puts, price):
        options = calls if self.bullish else puts
        if len(options) < 3: return []
        step = abs(float(options[min(1, len(options)-1)]['strike_price']) - float(options[0]['strike_price']))
        # Call/put wings are selected from actual listed strikes, never fixed offsets.
        direction = 1 if self.bullish else -1
        return [Leg(self._nearest(options, price), 'LONG', 1), Leg(self._nearest(options, price+direction*step), 'SHORT', 2), Leg(self._nearest(options, price+direction*3*step), 'LONG', 1)]


class DebitSpread(OptionStrategy):
    family = 'default'; profit_target = .45; stop_loss = .45; max_hold_hours = 36
    def __init__(self, bullish): super().__init__(); self.bullish = bullish; self.strategy_name = 'Bull Call Debit Spread' if bullish else 'Bear Put Debit Spread'
    def select_legs(self, calls, puts, price):
        options = calls if self.bullish else puts
        if len(options) < 2: return []
        step = abs(float(options[min(1, len(options)-1)]['strike_price']) - float(options[0]['strike_price']))
        target = price + step if self.bullish else price - step
        return [Leg(self._nearest(options, price), 'LONG', 1), Leg(self._nearest(options, target), 'SHORT', 1)]


class LongStraddle(OptionStrategy):
    strategy_name = 'Long Straddle'; family = 'long_volatility'; profit_target = .40; stop_loss = .40; max_hold_hours = 24
    def select_legs(self, calls, puts, price):
        return [Leg(self._nearest(calls, price), 'LONG', 1), Leg(self._nearest(puts, price), 'LONG', 1)] if calls and puts else []


class LongStrangle(OptionStrategy):
    strategy_name = 'Long Strangle'; family = 'long_volatility'; profit_target = .50; stop_loss = .45; max_hold_hours = 48
    def select_legs(self, calls, puts, price):
        if not calls or not puts: return []
        step = abs(float(calls[min(1, len(calls)-1)]['strike_price']) - float(calls[0]['strike_price']))
        return [Leg(self._nearest(calls, price+step), 'LONG', 1), Leg(self._nearest(puts, price-step), 'LONG', 1)]
