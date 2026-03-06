from collections import deque
from threading import Lock


class TickerBuffer:

    def __init__(self, max_length=200):

        self.max_length = max_length
        self.buffers = {}
        self.lock = Lock()

    # ==========================================
    # UPDATE TICKER
    # ==========================================

    def update(self, symbol, ticker):

        """
        ticker example:
        {
            "bid": 65000,
            "ask": 65005,
            "last": 65002,
            "volume": 100,
            "timestamp": 171000000
        }
        """

        with self.lock:

            if symbol not in self.buffers:
                self.buffers[symbol] = deque(maxlen=self.max_length)

            self.buffers[symbol].append(ticker)

    # ==========================================
    # GET LAST TICKER
    # ==========================================

    def get_latest(self, symbol):

        with self.lock:

            if symbol not in self.buffers:
                return None

            if not self.buffers[symbol]:
                return None

            return self.buffers[symbol][-1]

    # ==========================================
    # GET HISTORY
    # ==========================================

    def get_history(self, symbol):

        with self.lock:

            if symbol not in self.buffers:
                return []

            return list(self.buffers[symbol])

    # ==========================================
    # GET MID PRICE
    # ==========================================

    def get_mid_price(self, symbol):

        ticker = self.get_latest(symbol)

        if not ticker:
            return None

        bid = ticker.get("bid", 0)
        ask = ticker.get("ask", 0)

        if bid and ask:
            return (bid + ask) / 2

        return ticker.get("last")

    # ==========================================
    # CLEAR BUFFER
    # ==========================================

    def clear(self, symbol=None):

        with self.lock:

            if symbol:
                self.buffers.pop(symbol, None)
            else:
                self.buffers.clear()

    # ==========================================
    # AVAILABLE SYMBOLS
    # ==========================================

    def symbols(self):

        return list(self.buffers.keys())