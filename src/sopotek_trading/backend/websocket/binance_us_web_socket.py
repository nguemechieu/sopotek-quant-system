import asyncio
import json
import traceback
import websockets

from sopotek_trading.backend.websocket.candle_buffer import CandleBuffer


class BinanceWebSocketUs:

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

        if not symbols:
            raise ValueError("symbols cannot be empty")

        if not timeframe:
            raise ValueError("timeframe cannot be empty")

        self.symbols = self.controller.symbols
        self.timeframe = timeframe or "1d"

        self.base_url = "wss://stream.binance.us:9443/stream"

        self.on_candle_callback = candle_callback
        self.on_ticker_callback = ticker_callback
        self.order_book_callback = order_book_callback

        self.running = False
        self._ws = None

        # persistent candle buffer
        self.candle_buffer = CandleBuffer(self.controller.limit)

    # ======================================================
    # START
    # ======================================================

    async def start(self):

        self.running = True

        streams = []

        for symbol in self.symbols:

            sym = symbol.replace("/", "").lower()

            streams.append(f"{sym}@kline_{self.timeframe}")
            streams.append(f"{sym}@bookTicker")
            streams.append(f"{sym}@depth@100ms")

        url = f"{self.base_url}?streams={'/'.join(streams)}"

        while self.running:

            try:

                async with websockets.connect(
                        url,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=2**23
                ) as ws:

                    self._ws = ws

                    self.logger.info("BinanceUS WebSocket connected")

                    while self.running:

                        message = await ws.recv()

                        data = json.loads(message)

                        if "data" not in data:
                            continue

                        payload = data["data"]

                        await self._handle_payload(payload)

            except asyncio.CancelledError:
                break

            except Exception as e:

                self.logger.error(f"WebSocket error: {e}")
                traceback.print_exc()

                await asyncio.sleep(5)

        self.logger.info("WebSocket stopped")

    # ======================================================
    # HANDLE PAYLOAD
    # ======================================================

    async def _handle_payload(self, payload):

        try:

            event = payload.get("e")

            # --------------------------------------------------
            # CANDLE
            # --------------------------------------------------

            if event == "kline":

                k = payload["k"]

                if not k["x"]:
                    return

                symbol = payload["s"]

                if symbol.endswith("USDT"):
                    symbol = symbol[:-4] + "/USDT"

                candle = {
                    "timestamp": k["t"],
                    "open": float(k["o"]),
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "close": float(k["c"]),
                    "volume": float(k["v"]),
                }

                self.candle_buffer.update(symbol, candle)

                if self.on_candle_callback:
                    await self.on_candle_callback(symbol,self.timeframe, self.candle_buffer)

            # --------------------------------------------------
            # TICKER
            # --------------------------------------------------

            elif event == "bookTicker":

                symbol = payload["s"]

                if symbol.endswith("USDT"):
                    symbol = symbol[:-4] + "/USDT"

                bid = float(payload["b"])
                ask = float(payload["a"])

                if self.on_ticker_callback:
                    await self.on_ticker_callback(symbol, bid, ask)

            # --------------------------------------------------
            # ORDERBOOK
            # --------------------------------------------------

            elif event == "depthUpdate":

                symbol = payload["s"]

                if symbol.endswith("USDT"):
                    symbol = symbol[:-4] + "/USDT"

                bids = payload.get("b", [])
                asks = payload.get("a", [])

                if self.order_book_callback:
                    await self.order_book_callback(symbol, bids, asks)

        except Exception as e:

            self.logger.error(f"Payload processing error: {e}")
            traceback.print_exc()

    # ======================================================
    # STOP
    # ======================================================

    async def stop(self):

        self.running = False

        if self._ws:
            await self._ws.close()