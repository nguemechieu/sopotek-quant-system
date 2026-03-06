import time
from threading import Lock


class OrderBookBuffer:

    def __init__(self, depth=20):

        self.depth = depth
        self.order_books = {}
        self.lock = Lock()

    # ======================================
    # UPDATE ORDERBOOK
    # ======================================

    def update(self, symbol, bids, asks):

        """
        bids = [[price, size], ...]
        asks = [[price, size], ...]
        """

        with self.lock:

            self.order_books[symbol] = {
                "bids": bids[:self.depth],
                "asks": asks[:self.depth],
                "timestamp": time.time()
            }

    # ======================================
    # GET ORDERBOOK
    # ======================================

    def get(self, symbol):

        with self.lock:

            return self.order_books.get(symbol)

    # ======================================
    # BEST BID / ASK
    # ======================================

    def best_bid(self, symbol):

        book = self.get(symbol)

        if not book or not book["bids"]:
            return None

        return book["bids"][0][0]

    def best_ask(self, symbol):

        book = self.get(symbol)

        if not book or not book["asks"]:
            return None

        return book["asks"][0][0]

    # ======================================
    # SPREAD
    # ======================================

    def spread(self, symbol):

        bid = self.best_bid(symbol)
        ask = self.best_ask(symbol)

        if bid and ask:
            return ask - bid

        return None

    # ======================================
    # MID PRICE
    # ======================================

    def mid_price(self, symbol):

        bid = self.best_bid(symbol)
        ask = self.best_ask(symbol)

        if bid and ask:
            return (bid + ask) / 2

        return None

    # ======================================
    # LIQUIDITY
    # ======================================

    def liquidity(self, symbol):

        book = self.get(symbol)

        if not book:
            return None

        bid_liq = sum([b[1] for b in book["bids"]])
        ask_liq = sum([a[1] for a in book["asks"]])

        return {
            "bid_liquidity": bid_liq,
            "ask_liquidity": ask_liq
        }

    # ======================================
    # CLEAR
    # ======================================

    def clear(self, symbol=None):

        with self.lock:

            if symbol:
                self.order_books.pop(symbol, None)
            else:
                self.order_books.clear()

    # ======================================
    # SYMBOLS
    # ======================================

    def symbols(self):

        return list(self.order_books.keys())