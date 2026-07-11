import hmac
import hashlib
import logging
import time
import json
import httpx
from core.config import config
import random

logger = logging.getLogger(__name__)

class DeltaClient:
    def __init__(self):
        self.api_key = config.DELTA_API_KEY
        self.api_secret = config.DELTA_API_SECRET
        self.base_url = config.BASE_URL
        self.user_id = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.aclose()

    def _generate_signature(self,secret, message):
        message = bytes(message, 'utf-8')
        secret = bytes(secret, 'utf-8')
        hash = hmac.new(secret, message, hashlib.sha256)
        return hash.hexdigest()

    async def request(self, method: str, path: str, params: dict = None, data: dict = None, sign: bool = False):
        timestamp = str(int(time.time())-8)
        
        # Proper query string generation for signing
        query_str = ""
        if params:
            # Sort params for consistency
            query_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        
        body_str = json.dumps(data) if data else ""
        headers = {}
        if(sign):
            signature = self._generate_signature(self.api_secret, f"{method.upper()}{timestamp}{path}{query_str}{body_str}")
            headers = {
                'api-key': self.api_key,
                'timestamp': timestamp,
                'signature': signature,
                'User-Agent': 'python-rest-client',
                'Content-Type': 'application/json'
}
        else:
            headers = {
                'Accept': 'application/json'
            }
        url = f"{self.base_url}{path}"
        if query_str:
            url += f"?{query_str}"

        try:
            response = await self._client.request(
                method.upper(),
                url,
                content=body_str if data else None,
                headers=headers
            )
            #print(response.text)
            response.raise_for_status()            
            res_json = response.json()
            # Delta V2 responses are usually wrapped: {"success": true, "data": ...}
            if isinstance(res_json, dict) and "data" in res_json:
                return res_json["data"]
            return res_json
        except Exception as e:
            logger.exception("API request error")
            raise

    async def get_all_tickers(self):
        return await self.request("GET", "/v2/tickers")
    
    async def get_product_price(self, symbol: str):
        ticker = await self.get_ticker(symbol)
        return float(ticker.get("result").get("mark_price"))
    async def get_ticker(self, symbol: str):
        # Delta API V2 ticker endpoint: GET /v2/tickers/:symbol
        return await self.request("GET", f"/v2/tickers/{symbol}")

    async def get_wallet_balances(self):
        # Delta API V2: GET /v2/wallet/balances
        return await self.request("GET", "/v2/wallet/balances",sign=True)

    async def get_option_chain(self, underlying_asset: str = "BTC", settlement_time: str = None):
        # Delta API V2: GET /v2/products/option_chain
        params = {"underlying_asset": underlying_asset}
        if settlement_time:
            params["settlement_time"] = settlement_time
        return await self.request("GET", "/v2/products/option_chain", params=params)
    
    async def open_live_position(self, order: dict, side: str, size: float, price: float, leverage: int):
        # Placeholder for live trading logic
        logger.info("Opening live position: %s %s %s @ %s with %sx leverage", order.get('symbol'), side, size, price, leverage)
        client_order_id = f"deltaBot-{random.randint(1000,9999)}-{int(time.time())}"
        stop_price = 0 
        target_price = 0
        stop_limit = 0
        target_limit = 0
        contract_type = order.get("product", {}).get("contractType", "") or order.get("contract_type","")
        if("perpetual" in contract_type):
            if side == "LONG":
                stop_price = price * 0.98 # 2% stop loss
                stop_limit = stop_price - 200 # 3% stop loss limit
                target_price = price * 1.04 # 4% take profit
                target_limit = target_price - 200
                
            else:
                stop_price = price * 1.02 # 2% stop loss
                stop_limit = stop_price + 200 # 3% stop loss limit
                target_price = price * 0.96 # 4% take profit
                target_limit = target_price + 200
        else:
            if side == "LONG":
                stop_price = 0  # 5% stop loss for options
                target_price = price*2 # 10% take profit for options
            else:
                stop_price = price * 2 # 100% stop loss for options
                target_price = 0 # 10% take profit for options
        data = {
            "product_id": order.get("id") or order.get("product_id"),
            "product_symbol": order.get("symbol"),
            "size": int(size),
            "side": "buy" if side == "LONG" else "sell",
            "order_type": "market_order",
            "stop_price": stop_price, # Simplified stop loss logic
            "stop_trigger_method": "last_traded_price",
            "bracket_stop_trigger_method": "last_traded_price",
            "bracket_stop_loss_limit_price": stop_limit, # Simplified stop loss limit logic
            "bracket_stop_loss_price":stop_price, # Simplified stop loss logic
            "bracket_take_profit_limit_price": target_limit, # Simplified take profit limit logic
            "bracket_take_profit_price": target_price, # Simplified take profit logic
            "time_in_force": "gtc",
            "mmp": "disabled",
            "post_only": False,
            "reduce_only": False,
            "client_order_id": client_order_id,
            "cancel_orders_accepted":False
        }
        await self.request("POST", "/v2/orders",data=data, sign=True)

    async def get_live_positions(self):
        # Delta API V2: GET /v2/positions/margined
        return await self.request("GET", "/v2/positions/margined", sign=True)

    async def close_all_live_positions(self):
        body = {
            "close_all_portfolio": True,
            "close_all_isolated": True,
            "user_id": self.user_id
        }
        return await self.request("POST", "/v2/positions/close_all", data=body, sign=True)
