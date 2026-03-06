from sopotek_trading.backend.market.ticker_buffer import TickerBuffer


class SymbolSelector:

    def __init__(self, controller, quote_assets=None, max_symbols=10):

        self.controller = controller
        self.broker = controller.broker
        self.quote_assets = quote_assets or ["USDT", "USD"]
        self.max_symbols = max_symbols
        self.ticker_buffer = TickerBuffer()

    async def select_symbols(self):

        try:

            if self.controller.broker is None:
                return []

            # --------------------------------------
            # Get all exchange symbols
            # --------------------------------------
            self.controller.logger.info("SymbolSelector starting")


            symbols =self.controller.symbols

            self.controller.symbols_buffer.set(symbols)

            # --------------------------------------
            # Get all tickers (single request)
            # --------------------------------------

            tickers = await self.controller.broker.fetch_tickers(symbols=symbols)

            candidates = []

            for ticker in tickers:

                symbol = ticker.get("symbol")

                if not symbol:
                    continue

                # Convert BTCUSDT → BTC/USDT
                if symbol.endswith("USDT"):
                    symbol = symbol.replace("USDT", "/USDT")

                elif symbol.endswith("USD"):
                    symbol = symbol.replace("USD", "/USD")

                else:
                    continue

                base, quote = symbol.split("/")

                if quote not in self.quote_assets:
                    continue

                volume = float(ticker.get("quoteVolume", 0))
                change = abs(float(ticker.get("priceChangePercent", 0)))

                score = volume * (1 + change)

                candidates.append((symbol, score))

                # store ticker in buffer
                self.ticker_buffer.update(symbol, ticker)

            # --------------------------------------
            # Rank symbols
            # --------------------------------------

            candidates.sort(key=lambda x: x[1], reverse=True)

            best = [s[0] for s in candidates[:self.max_symbols]]

            return best

        except Exception as e:

            self.controller.logger.error(f"SymbolSelector error: {e}")
            return []