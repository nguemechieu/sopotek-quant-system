from threading import Lock


class SymbolsBuffer:

    def __init__(self):

        self.symbols = []
        self.lock = Lock()

    # ==========================================
    # SET SYMBOLS
    # ==========================================

    def set(self, symbols):

        with self.lock:
            self.symbols = list(set(symbols))

    # ==========================================
    # ADD SYMBOL
    # ==========================================

    def add(self, symbol):

        with self.lock:
            if symbol not in self.symbols:
                self.symbols.append(symbol)

    # ==========================================
    # REMOVE SYMBOL
    # ==========================================

    def remove(self, symbol):

        with self.lock:
            if symbol in self.symbols:
                self.symbols.remove(symbol)

    # ==========================================
    # GET SYMBOLS
    # ==========================================

    def get(self):

        with self.lock:
            return list(self.symbols)

    # ==========================================
    # CHECK SYMBOL
    # ==========================================

    def contains(self, symbol):

        with self.lock:
            return symbol in self.symbols

    # ==========================================
    # CLEAR
    # ==========================================

    def clear(self):

        with self.lock:
            self.symbols.clear()

    # ==========================================
    # SIZE
    # ==========================================

    def size(self):

        with self.lock:
            return len(self.symbols)

    # ==========================================
    # ITERATOR
    # ==========================================

    def __iter__(self):

        return iter(self.get())

    # ==========================================
    # STRING
    # ==========================================

    def __repr__(self):

        return f"<SymbolsBuffer {len(self.symbols)} symbols>"