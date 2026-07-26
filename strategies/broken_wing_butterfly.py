import logging

from core.config import config
from exchange.client import DeltaClient
from exchange.market_data import market_data
from paper_trading.engine import paper_engine


logger = logging.getLogger(__name__)


class BrokenWingButterflyStrategy:
    """Directional, same-expiry broken wing butterfly.

    A bullish signal uses calls and a bearish signal uses puts.  The strikes are
    measured from the actual available ATM strike so the offsets remain exact.
    """

    strategy_name = "Broken Wing Butterfly"

    def __init__(self):
        self.active_legs = []
        self.client = DeltaClient()

    @staticmethod
    def _contract_type(signal: str) -> str | None:
        if signal == "BULLISH":
            return "call_options"
        if signal == "BEARISH":
            return "put_options"
        return None

    @staticmethod
    def _strike(option: dict) -> float:
        return float(option["strike_price"])

    def _select_legs(self, options: list[dict], contract_type: str, current_price: float):
        typed_options = [option for option in options if option.get("contract_type") == contract_type]
        if not typed_options:
            return None

        # Use the chain's closest listed strike as ATM, rather than assuming a
        # fixed strike interval.
        atm_option = min(typed_options, key=lambda option: abs(self._strike(option) - current_price))
        atm_strike = self._strike(atm_option)
        by_strike = {self._strike(option): option for option in typed_options}
        required = (
            (atm_strike, "LONG", 1),
            (atm_strike + 1000, "SHORT", 2),
            (atm_strike + 2500, "LONG", 1),
        )
        legs = []
        for strike, side, multiplier in required:
            option = by_strike.get(strike)
            if option is None:
                return None
            legs.append((option, side, multiplier))
        return atm_strike, legs

    async def execute(self, current_price: float, signal: str):
        if signal not in {"BULLISH", "BEARISH"}:
            return False, "A bullish or bearish directional signal is required"
        if await self.is_active():
            return False, "Broken Wing Butterfly is already active"

        expiry = market_data.get_nearest_expiry()
        if not expiry:
            return False, "No option expiry found"
        options = market_data.get_options_by_expiry(expiry)
        selected = self._select_legs(options, self._contract_type(signal), current_price)
        if selected is None:
            return False, "Could not find all Broken Wing Butterfly option legs"

        atm_strike, legs = selected
        # Fetch every quote before opening any leg, so unavailable pricing cannot
        # leave a partially constructed butterfly.
        prices = [await self.client.get_product_price(option["symbol"]) for option, _, _ in legs]
        if any(price is None or float(price) <= 0 for price in prices):
            return False, "Could not price all Broken Wing Butterfly option legs"

        required_margin = sum(
            config.LOT_SIZE * multiplier * float(price) / config.OPTION_LEVERAGE
            for (_, _, multiplier), price in zip(legs, prices)
        )
        wallet = await paper_engine.get_wallet()
        if required_margin > wallet["availableBalance"]:
            return False, "Insufficient margin for the complete Broken Wing Butterfly"

        try:
            for (option, side, multiplier), price in zip(legs, prices):
                await paper_engine.open_position(
                    option,
                    side,
                    config.LOT_SIZE * multiplier,
                    float(price),
                    config.OPTION_LEVERAGE,
                    self.strategy_name,
                )
        except Exception:
            # Do not leave a partial butterfly open if a leg fails to submit.
            try:
                await paper_engine.close_position(self.strategy_name)
            except Exception:
                logger.exception("Unable to roll back partial Broken Wing Butterfly")
            raise

        self.active_legs = [option["symbol"] for option, _, _ in legs]
        option_kind = "calls" if signal == "BULLISH" else "puts"
        logger.info(
            "Opened %s Broken Wing Butterfly: %s %s / %s / %s",
            signal,
            option_kind,
            atm_strike,
            atm_strike + 1000,
            atm_strike + 2500,
        )
        return True, "Broken Wing Butterfly executed"

    async def is_active(self) -> bool:
        positions = await paper_engine.get_positions_from_db()
        return any(position.get("strategy") == self.strategy_name for position in positions)

    async def reset(self):
        self.active_legs = []

    async def get_active_legs(self):
        positions = await paper_engine.get_positions_from_db()
        self.active_legs = [position for position in positions if position.get("strategy") == self.strategy_name]


broken_wing_butterfly = BrokenWingButterflyStrategy()
