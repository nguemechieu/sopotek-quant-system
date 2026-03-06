from sopotek_trading.backend.websocket.alphaca_web_socket import AlpacaWebSocket
from sopotek_trading.backend.websocket.binance_us_web_socket import BinanceWebSocketUs
from sopotek_trading.backend.websocket.oanda_web_socket import OandaWebSocket


class WebSocketManager:

    def __init__(
            self,
            controller,
            symbols,
            timeframe,
            candle_callback,  #GET CANDLES
            ticker_callback,  # GET TICKER
            order_book_callback,  # Get orderbook
    ):

        self.controller = controller
        self.logger = controller.logger

        self.symbols = symbols
        self.timeframe = timeframe

        # 🔥 Proper dependency injection
        self.candle_callback = candle_callback
        self.ticker_callback = ticker_callback
        self.order_book_callback = order_book_callback

        self.ws = None
        self.running = False

    # ======================================================
    # START
    # ======================================================

    async def start(self):

        broker_type = self.controller.exchange_type

        if broker_type == "crypto":

            self.ws = BinanceWebSocketUs(
                controller=self.controller,
                symbols=self.symbols or ["BTC/USDT", "ETH/USDT"],
                timeframe=self.timeframe or "1d",
                candle_callback=self.candle_callback,
                ticker_callback=self.ticker_callback,
                order_book_callback=self.order_book_callback
            )

        elif broker_type == "forex":

            self.ws = OandaWebSocket(
                controller=self.controller,
                symbols=self.symbols,
                timeframe=self.timeframe,
                candle_callback=self.candle_callback,
                ticker_callback=self.ticker_callback,
                order_book_callback=self.order_book_callback
            )

        elif broker_type == "stocks":

            self.ws = AlpacaWebSocket(controller=self.controller, symbols=self.symbols,
                                      callback=self.order_book_callback, candle_callback=self.candle_callback,
                                      ticker_callback=self.ticker_callback,
                                      order_book_callback=self.order_book_callback)

        elif broker_type == "paper":
            self.ws = AlpacaWebSocket(self.controller,self.symbols,self.timeframe,self.candle_callback,self.ticker_callback,self.order_book_callback)


        else:
            raise RuntimeWarning( f"Unsupported broker type {broker_type}")

        await self.ws.start()

        self.running = True

    # ======================================================
    # STOP
    # ======================================================

    async def stop(self):

        self.running = False

        if self.ws:
            await self.ws.stop()
