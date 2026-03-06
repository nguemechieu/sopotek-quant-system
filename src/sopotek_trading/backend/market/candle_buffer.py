import pandas as pd


class CandleBuffer:

    def __init__(self, max_length=500):

        self.max_length = max_length

        # Structure
        # buffers[symbol][timeframe] = [candles]
        self.buffers = {}

    # ======================================================
    # UPDATE
    # ======================================================

    def update(self, symbol, timeframe, candle):

        """
        candle format:
        {
            "timestamp": int,
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float
        }
        """

        if symbol not in self.buffers:
            self.buffers[symbol] = {}

        if timeframe not in self.buffers[symbol]:
            self.buffers[symbol][timeframe] = []

        buffer = self.buffers[symbol][timeframe]

        buffer.append(candle)

        # keep max length
        if len(buffer) > self.max_length:
            buffer.pop(0)

    # ======================================================
    # GET DATAFRAME
    # ======================================================

    def get(self, symbol, timeframe):

        if symbol not in self.buffers:
            return None

        if timeframe not in self.buffers[symbol]:
            return None

        data = self.buffers[symbol][timeframe]

        if not data:
            return None

        df = pd.DataFrame(data)

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        return df.copy()

    # ======================================================
    # CLEAR SYMBOL
    # ======================================================

    def clear_symbol(self, symbol):

        if symbol in self.buffers:
            del self.buffers[symbol]

    # ======================================================
    # CLEAR TIMEFRAME
    # ======================================================

    def clear_timeframe(self, symbol, timeframe):

        if symbol in self.buffers and timeframe in self.buffers[symbol]:
            del self.buffers[symbol][timeframe]

    # ======================================================
    # GET LAST CANDLE
    # ======================================================

    def last(self, symbol, timeframe):

        if symbol not in self.buffers:
            return None

        if timeframe not in self.buffers[symbol]:
            return None

        buffer = self.buffers[symbol][timeframe]

        if not buffer:
            return None

        return buffer[-1]