import time
import hmac
import hashlib
import aiohttp
import asyncio

from urllib.parse import urlencode
from sopotek_trading.backend.broker.base_broker import BaseBroker


class BinanceUsBroker(BaseBroker):

    BASE_URL = "https://api.binance.us"

    def __init__(self, controller):

        self.api_key = controller.api_key
        self.secret = controller.secret.encode()

        self.session: aiohttp.ClientSession | None = None
        self.timeout = aiohttp.ClientTimeout(total=10)

    # =========================================================
    # CONNECTION
    # =========================================================

    async def connect(self):

        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self):

        if self.session:
            await self.session.close()
            self.session = None

    # =========================================================
    # INTERNAL REQUEST
    # =========================================================

    async def _request(self, method, path, params=None, signed=False):

        if self.session is None:
            await self.connect()

        url = f"{self.BASE_URL}{path}"
        headers = {}

        params = params or {}

        if signed:

            params["timestamp"] = int(time.time() * 1000)

            query = urlencode(params)

            signature = hmac.new(
                self.secret,
                query.encode(),
                hashlib.sha256
            ).hexdigest()

            params["signature"] = signature

            headers["X-MBX-APIKEY"] = self.api_key

        try:

            async with self.session.request(
                    method,
                    url,
                    params=params,
                    headers=headers
            ) as r:

                data = await r.json()

                if r.status != 200:
                    raise RuntimeError(
                        f"Binance API error {r.status}: {data}"
                    )

                return data

        except asyncio.TimeoutError:
            raise RuntimeError("Binance request timeout")

        except aiohttp.ClientError as e:
            raise RuntimeError(f"Binance connection error: {e}")

    # =========================================================
    # SYMBOLS
    # =========================================================

    async def fetch_symbols(self):

        data = await self._request("GET", "/api/v3/exchangeInfo")

        symbols = []

        for s in data["symbols"]:

            if s["status"] != "TRADING":
                continue

            base = s["baseAsset"]
            quote = s["quoteAsset"]

            symbols.append(f"{base}/{quote}")

        return symbols

    # =========================================================
    # BALANCE
    # =========================================================

    async def fetch_balance(self):

        data = await self._request(
            "GET",
            "/api/v3/account",
            signed=True
        )

        balances = {}

        for b in data["balances"]:

            free = float(b["free"])
            locked = float(b["locked"])

            if free > 0 or locked > 0:

                balances[b["asset"]] = {
                    "free": free,
                    "used": locked,
                    "total": free + locked
                }

        return balances

    # =========================================================
    # PLACE ORDER
    # =========================================================

    async def place_order(
            self,
            symbol: str,
            side: str,
            order_type: str,
            amount: float,
            price: float | None = None
    ):

        symbol = symbol.replace("/", "")

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": amount
        }

        if order_type.upper() == "LIMIT":

            params["price"] = price
            params["timeInForce"] = "GTC"

        return await self._request(
            "POST",
            "/api/v3/order",
            params=params,
            signed=True
        )

    # =========================================================
    # CANCEL ORDER
    # =========================================================

    async def cancel_order(self, symbol: str, order_id: str):

        symbol = symbol.replace("/", "")

        params = {
            "symbol": symbol,
            "orderId": order_id
        }

        return await self._request(
            "DELETE",
            "/api/v3/order",
            params=params,
            signed=True
        )

    async def cancel_all_orders(self, symbol):

        symbol = symbol.replace("/", "")

        return await self._request(
            "DELETE",
            "/api/v3/openOrders",
            params={"symbol": symbol},
            signed=True
        )

    # =========================================================
    # TICKERS
    # =========================================================

    async def fetch_ticker(self, symbol):

        symbol = symbol.replace("/", "")

        return await self._request(
            "GET",
            "/api/v3/ticker/bookTicker",
            params={"symbol": symbol}
        )

    async def fetch_all_tickers(self):

        return await self._request(
            "GET",
            "/api/v3/ticker/24hr"
        )

    # =========================================================
    # ORDER BOOK
    # =========================================================

    async def fetch_order_book(self, symbol, limit=20):

        symbol = symbol.replace("/", "")

        return await self._request(
            "GET",
            "/api/v3/depth",
            params={
                "symbol": symbol,
                "limit": limit
            }
        )