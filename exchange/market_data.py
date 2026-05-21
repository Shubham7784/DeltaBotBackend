from .client import DeltaClient
from ..core.config import config
import asyncio

class MarketDataService:
    def __init__(self):
        self.client = DeltaClient()
        self.instruments = []
        self.btc_options = []
        self.btc_futures = []

    async def initialize(self):
        try:
            products = await self.client.get_products()
            self.instruments = products.get("result", [])
            self.btc_futures = [i for i in self.instruments if i.get("underlying_asset") == "BTC" and i.get("asset_type") == "futures"]
            self.btc_options = [i for i in self.instruments if "BTC" in i.get("symbol")]
        except Exception as e:
            print(f"Error initializing market data: {e}")

    async def fetch_option_chain(self, settlement_time: str = None):
        try:
            chain = await self.client.get_option_chain("BTC", settlement_time)
            return chain
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return []

    def get_nearest_expiry(self):
        expiries = sorted(list(set([o.get("settlement_time") for o in self.btc_options if o.get("settlement_time")])))
        return expiries[0] if expiries else None

    def get_options_by_expiry(self, expiry: str):
        return [o for o in self.btc_options if o.get("settlement_time") == expiry]

    async def get_live_price(self, symbol: str = "BTCUSD"):
        try:
            ticker = await self.client.get_ticker(symbol)
            # Delta V2 ticker usually has 'mark_price' or 'last_price'
            return float(ticker.get("result").get("mark_price") or ticker.get("result").get("last_price") or 0)
        except Exception as e:
            print(f"Error fetching live price for {symbol}: {e}")
            return None
        
    async def get_all_tickers(self):
        try:
            tickers = await self.client.request("GET", "/v2/tickers")
            return tickers.get("result", [])
        except Exception as e:
            print(f"Error fetching all tickers: {e}")
            return []

market_data = MarketDataService()
