import logging
from datetime import datetime, timedelta
import asyncio

from core.config import config
from exchange.client import DeltaClient
from exchange.market_data import market_data
from paper_trading.engine import paper_engine

logger = logging.getLogger(__name__)


class PoorMansCoveredStrategy:
    def __init__(self):
        self.client = DeltaClient()

    def _get_strike(self, option: dict) -> float:
        strike_value = option.get("strike_price") or option.get("strike")
        try:
            return float(strike_value)
        except (TypeError, ValueError):
            return 0.0

    def _parse_option_expiries(self):
        expiries = []
        for option in market_data.btc_options:
            symbol = option.get("symbol", "")
            if not symbol:
                continue
            try:
                expiry = datetime.strptime(symbol.split("-")[-1], "%d%m%y").date()
                expiries.append(expiry)
            except ValueError:
                continue
        expiries = sorted(set(expiries))
        return expiries

    def _choose_expiries(self):
        expiries = self._parse_option_expiries()
        if not expiries:
            return None, None

        today = datetime.now().date()
        expiries = [exp for exp in expiries if exp >= today]
        if not expiries:
            return None, None

        daily_expiry = expiries[0]
        monthly_expiry = None
        for exp in expiries:
            if (exp - today).days >= 18:
                monthly_expiry = exp
                break

        if monthly_expiry is None and len(expiries) > 1:
            monthly_expiry = expiries[-1]

        if monthly_expiry is None or monthly_expiry == daily_expiry:
            return None, None

        return daily_expiry, monthly_expiry

    def _find_atm_option(self, options: list[dict], contract_type: str, target_strike: float) -> dict | None:
        candidates = [o for o in options if o.get("contract_type") == contract_type]
        if not candidates:
            return None

        exact = [o for o in candidates if abs(self._get_strike(o) - target_strike) < 1e-6]
        if exact:
            return exact[0]

        return min(candidates, key=lambda o: abs(self._get_strike(o) - target_strike))

    def _find_itm_monthly_option(self, options: list[dict], contract_type: str, underlying_price: float, is_call: bool) -> dict | None:
        candidates = [o for o in options if o.get("contract_type") == contract_type]
        if not candidates:
            return None

        itm = [o for o in candidates if (self._get_strike(o) < underlying_price if is_call else self._get_strike(o) > underlying_price)]
        if not itm:
            return None

        if is_call:
            return max(itm, key=self._get_strike)
        return min(itm, key=self._get_strike)

    async def execute(self, side: str, current_price: float):
        if not current_price or current_price <= 0:
            return False, "Invalid current BTC price"

        side = side.strip().upper()
        if side not in {"CALL", "PUT"}:
            return False, "Invalid side. Use 'CALL' or 'PUT'"

        daily_expiry, monthly_expiry = self._choose_expiries()
        if not daily_expiry or not monthly_expiry:
            return False, "Could not resolve daily and monthly expiries from option chain"

        daily_options = market_data.get_options_by_expiry(daily_expiry)
        monthly_options = market_data.get_options_by_expiry(monthly_expiry)
        if not daily_options or not monthly_options:
            return False, "Could not load options for selected expiries"

        atm_strike = round(current_price / 100) * 100
        if atm_strike <= 0:
            return False, "Could not determine ATM strike"

        contract_type = "call_options" if side == "CALL" else "put_options"
        long_is_call = side == "CALL"

        daily_leg = self._find_atm_option(daily_options, contract_type, atm_strike)
        monthly_leg = self._find_itm_monthly_option(monthly_options, contract_type, current_price, long_is_call)

        if not daily_leg:
            return False, f"No ATM daily {side.lower()} option available for strike {atm_strike}"
        if not monthly_leg:
            return False, f"No ITM monthly {side.lower()} option available around underlying {current_price}"

        try:
            # Short the daily ATM leg and long the monthly ITM leg
            await self._open_leg(daily_leg, "SHORT", strategy=f"Poor Man's Covered {side.capitalize()} - Daily ATM")
            await asyncio.sleep(1)
            await self._open_leg(monthly_leg, "LONG", strategy=f"Poor Man's Covered {side.capitalize()} - Monthly ITM")
        except Exception as exc:
            logger.exception("Failed executing Poor Man's Covered %s", side)
            return False, f"Execution failed: {exc}"

        return True, f"Poor Man's Covered {side.capitalize()} executed with daily expiry {daily_expiry} and monthly expiry {monthly_expiry}"

    async def is_active(self, side: str | None = None) -> bool:
        positions = await paper_engine.get_positions()
        if side is None:
            return any("Poor Man's Covered" in (p.get("strategy") or "") for p in positions)

        side = side.strip().upper()
        if side == "CALL":
            return any("Poor Man's Covered Call" in (p.get("strategy") or "") for p in positions)
        if side == "PUT":
            return any("Poor Man's Covered Put" in (p.get("strategy") or "") for p in positions)

        return False

    async def _open_leg(self, option_inst: dict, side: str, strategy: str):
        price = await self.client.get_product_price(option_inst.get("symbol"))
        if price is None:
            raise Exception(f"Could not fetch live price for {option_inst.get('symbol')}")

        await paper_engine.open_position(option_inst, side, config.POOR_MANS_LOT_SIZE, price, config.OPTION_LEVERAGE, strategy)


poor_mans_covered_strategy = PoorMansCoveredStrategy()
