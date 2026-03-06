import asyncio
import json
import traceback
from datetime import datetime

import websockets


class CoinbaseWebSocket:

    def __init__(
            self,
            controller,
            symbols,
            timeframe,
            candle_callback,
            ticker_callback,
            order_book_callback
    ):

        self.controller = controller
        self.logger = controller.logger

        # Convert BTC/USDT → BTC-USDT
        self.symbols = [s.replace("/", "-") for s in symbols]

        self.timeframe = self._parse_timeframe(timeframe)

        self.on_candle_callback = candle_callback
        self.on_ticker_callback = ticker_callback
        self.order_book_callback = order_book_callback

        self.base_url = "wss://ws-feed.exchange.coinbase.com"

        self.running = False
        self._ws = None

        # Candle builder
        self.current_candles = {}

    # ======================================================
    # START
    # ======================================================

    async def start(self):

        self.running = True

        while self.running:

            try:

                async with websockets.connect(
                        self.base_url,
                        ping_interval=20,
                        ping_timeout=20
                ) as ws:

                    self._ws = ws

                    self.logger.info("Coinbase WebSocket connected")

                    subscribe_msg = {
                        "type": "subscribe",
                        "product_ids": self.symbols,
                        "channels": [
                            "matches",
                            "ticker",
                            "level2"
                        ],
                    }

                    await ws.send(json.dumps(subscribe_msg))

                    while self.running:

                        message = await ws.recv()

                        data = json.loads(message)

                        await self._handle_message(data)

            except asyncio.CancelledError:
                break

            except Exception as e:

                self.logger.error(f"Coinbase WS error: {e}")
                traceback.print_exc()

                await asyncio.sleep(5)

        self.logger.info("Coinbase WebSocket stopped")

    # ======================================================
    # HANDLE MESSAGE
    # ======================================================

    async def _handle_message(self, data):

        msg_type = data.get("type")

        # --------------------------------------------------
        # TRADE (used to build candles)
        # --------------------------------------------------

        if msg_type == "match":

            symbol = data["product_id"]

            price = float(data["price"])
            size = float(data["size"])
            timestamp = data["time"]

            await self._build_candle(
                symbol,
                price,
                size,
                timestamp
            )

        # --------------------------------------------------
        # TICKER
        # --------------------------------------------------

        elif msg_type == "ticker":

            symbol = data["product_id"]

            bid = float(data.get("best_bid", 0))
            ask = float(data.get("best_ask", 0))

            if self.on_ticker_callback:

                await self.on_ticker_callback(
                    symbol.replace("-", "/"),
                    bid,
                    ask
                )

        # --------------------------------------------------
        # ORDERBOOK
        # --------------------------------------------------

        elif msg_type in ["snapshot", "l2update"]:

            symbol = data["product_id"]

            bids = []
            asks = []

            if msg_type == "snapshot":

                bids = data.get("bids", [])
                asks = data.get("asks", [])

            elif msg_type == "l2update":

                for change in data.get("changes", []):

                    side, price, size = change

                    if side == "buy":
                        bids.append((price, size))
                    else:
                        asks.append((price, size))

            if self.order_book_callback:

                await self.order_book_callback(
                    symbol.replace("-", "/"),
                    bids,
                    asks
                )

    # ======================================================
    # CANDLE BUILDER
    # ======================================================

    async def _build_candle(
            self,
            symbol,
            price,
            volume,
            timestamp
    ):

        ts = self._to_epoch(timestamp)

        bucket = ts - (ts % self.timeframe)

        candle = self.current_candles.get(symbol)

        if candle is None or candle["timestamp"] != bucket:

            # emit previous candle
            if candle and self.on_candle_callback:

                await self.on_candle_callback(
                    symbol.replace("-", "/"),
                    candle
                )

            candle = {
                "timestamp": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
            }

            self.current_candles[symbol] = candle

        else:

            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += volume

    # ======================================================
    # UTILS
    # ======================================================

    def _parse_timeframe(self, tf):

        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }

        return mapping.get(tf, 60)

    def _to_epoch(self, iso_time):

        return int(
            datetime.fromisoformat(
                iso_time.replace("Z", "")
            ).timestamp()
        )

    # ======================================================
    # STOP
    # ======================================================

    async def stop(self):

        self.running = False

        if self._ws:
            await self._ws.close()