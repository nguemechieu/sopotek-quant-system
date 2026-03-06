import asyncio
import traceback

import pandas as pd
from PySide6.QtCore import QObject

from sopotek_trading.backend.core.orchestrator import Orchestrator
from sopotek_trading.backend.managers.execution_manager import ExecutionManager
from sopotek_trading.backend.managers.web_socket_manager import WebSocketManager
from sopotek_trading.backend.market.symbol_selector import SymbolSelector
from sopotek_trading.backend.risk.institutional_risk import InstitutionalRiskEngine


class SopotekTrading(QObject):

    def __init__(self, controller):
        super().__init__()

        self.execution_manager = None
        self.broker_manager = None
        self.connected = None

        self.controller = controller
        self.MAX_TRADEABLE_SYMBOLS = 20
        self.controller = controller
        self.logger = controller.logger
        self.broker = controller.broker

        # ==============================
        # Signals
        # ==============================

        self.ticker_signal = controller.ticker_signal
        self.equity_signal = controller.equity_signal
        self.candle_signal = controller.candle_signal
        self.trade_signal = controller.trade_signal
        self.connection_signal = controller.connection_signal
        self.orderbook_signal = controller.orderbook_signal
        self.strategy_debug_signal = controller.strategy_debug_signal
        self.symbols_signal = controller.symbols_signal

        # ==============================
        # System state
        # ==============================

        self.time_frame = controller.time_frame
        self.limit = controller.limit

        self.running = False
        self.autotrading_enabled = False

        self.tickers = {}
        self.current_equity = 0
        self.spread_pct = 0

        # ==============================
        # Risk Engine
        # ==============================

        self.controller.risk_engine = InstitutionalRiskEngine(
            account_equity=controller.account_equity,
            max_portfolio_risk=controller.max_portfolio_risk,
            max_risk_per_trade=controller.max_risk_per_trade,
            max_position_size_pct=controller.max_position_size_pct,
            max_gross_exposure_pct=controller.max_gross_exposure_pct
        )

        # ==============================
        # Core components
        # ==============================

        self.orchestrator = Orchestrator(controller=self.controller)

        self.ws_manager = WebSocketManager(
            controller=self.controller,
            symbols=self.controller.symbols or ["ETH/USDT", "BTC/USDT"],
            timeframe=self.time_frame,
            candle_callback=self._on_ws_candle,
            ticker_callback=self._on_ticker_callback,
            order_book_callback=self._on_order_book_callback
        )

        self.logger.info("Sopotek Trading System Ready")

    # ======================================================
    # INITIALIZE SYSTEM
    # ======================================================

    async def initialize(self):

        try:

            asyncio.create_task(self.connector())

            self.connection_signal.emit("connecting")

            # connect broker
            await self.broker.connect()

            self.connected = True

            await self._load_symbols()

            self.logger.info("System initialization complete")

            ######################################
            # EXECUTION MANAGER
            ################################

            self.controller.execution_manager = ExecutionManager(self.controller)

            self.controller.execution_manager.start()

            self.running = True

            asyncio.create_task(self._balance_scheduler())

            self.ws_manager = WebSocketManager(symbols=self.symbols, timeframe=self.time_frame,
                                               ticker_callback=self._on_ticker_callback,
                                               order_book_callback=self._on_order_book_callback,
                                               candle_callback=self._on_ws_candle, controller=self.controller)

            await self.ws_manager.start()

            if self.ws_manager.running:
                self.connection_signal.emit("connected")

        except Exception as e:

            self.connection_signal.emit("disconnected")
            self.logger.error(e)

    # ======================================================
    # SHUTDOWN
    # ======================================================

    async def shutdown(self):

        self.logger.info("Shutting down Sopotek Trading System")

        self.running = False
        self.autotrading_enabled = False

        try:

            if self.ws_manager:
                await self.ws_manager.stop()

            if self.controller.execution_manager:
                await self.controller.execution_manager.stop()

            if self.controller.broker:
                await self.controller.broker.close()

        except Exception as e:
            self.logger.error(e)

        self.connection_signal.emit("disconnected")

        self.logger.info("Shutdown complete")

    # ======================================================
    # SYMBOL LOADING
    # ======================================================

    async def _load_symbols(self):

        symbols = await  self.broker.fetch_symbols()
        self.controller.symbols_buffer.set(symbols)

        if not symbols:
            raise Exception("No symbols returned from broker")
        # selector = SymbolSelector(controller=self.controller,
        #                           max_symbols=self.MAX_TRADEABLE_SYMBOLS)

        # ======================================
        # FILTER SYMBOLS
        # ======================================

        filtered = []

        for sym in symbols:

            # Normalize
            if "-" in sym:
                sym = sym.replace("-", "/")

            # Only crypto pairs
            if "/" not in sym:
                continue

            base, quote = sym.split("/")

            # Only USDT or USD pairs
            if quote not in ["USDT", "USD"]:
                continue

            # Avoid leveraged tokens
            banned = ["UP", "DOWN", "BULL", "BEAR"]

            if any(b in base for b in banned):
                continue

            filtered.append(sym)

        # Optional: limit number of symbols
        max_symbols = getattr(self.controller, "max_symbols", self.MAX_TRADEABLE_SYMBOLS)

        filtered = filtered[:max_symbols]

        # ======================================
        # STORE SYMBOLS
        # ======================================

        self.symbols = filtered
        self.symbols_list = filtered

        self.controller.symbols = filtered
        self.controller.symbols_list = filtered

        # UI update
        self.symbols_signal.emit(self.controller.exchange_name, filtered)

        self.logger.info(f"{len(filtered)} symbols loaded after filtering{filtered}")

    # ======================================================
    # BALANCE SCHEDULER
    # ======================================================

    async def _balance_scheduler(self):

        while self.running:

            try:

                balance = await self.broker.fetch_balance()

                equity = balance.get("equity", 0)
                free = balance.get("free", 0)
                used = balance.get("used", 0)
                currency = balance.get("currency", "")

                self.current_equity = equity

                self.equity_signal.emit(equity)

                df = pd.DataFrame([{
                    "equity": equity,
                    "free": free,
                    "used": used,
                    "currency": currency
                }])

                self.controller.balances = df

                df.to_csv("../../models/balance.csv", index=False)

            except Exception as e:

                self.logger.error(f"Balance scheduler error: {e}")
                traceback.print_exc()

            await asyncio.sleep(30)

    async def _load_order_book(self):
        try:
            while self.running:

                for s in self.symbols:
                    data = await self.broker.fetch_order_book(symbol=s, limit=100)
                    self.controller.order_book_buffer.update(s, data["bids"], data["asks"])

        except Exception as e:
            self.logger.error(f"Order book scheduler error: {e}")
            traceback.print_exc()
        await asyncio.sleep(30)

    # ======================================================
    # WEBSOCKET CANDLE
    # ======================================================

    async def _on_ws_candle(self, symbol: str, time_frame: str, candle_data):
        candle = self.controller.candles_buffer
        candle.update(symbol, time_frame, candle_data)
        try:

            if "/" not in symbol and symbol.endswith("USDT"):
                symbol = symbol[:-4] + "/USDT"

            required = {"timestamp", "open", "high", "low", "close", "volume"}

            if not required.issubset(candle.get(symbol, time_frame).keys()):
                self.logger.error(f"Invalid candle format for {symbol}")
                return

            self.candle_signal.emit(symbol, candle)

            if self.autotrading_enabled:
                asyncio.get_event_loop().create_task(
                    self.orchestrator.trading_engine.run_trade(symbol, candle)
                )

        except Exception as e:

            self.logger.error(f"Candle error {symbol}: {e}")
            traceback.print_exc()

    # ======================================================
    # TICKER CALLBACK
    # ======================================================

    async def _on_ticker_callback(self, symbol: str, bid: float, ask: float):

        try:

            if "/" not in symbol and symbol.endswith("USDT"):
                symbol = symbol[:-4] + "/USDT"

            bid = float(bid)
            ask = float(ask)

            if bid <= 0 or ask <= 0:
                return

            self.tickers[symbol] = {"bid": bid, "ask": ask}

            mid = (bid + ask) / 2
            spread = ask - bid

            self.spread_pct = (spread / mid) * 100 if mid else 0

            self.ticker_signal.emit(symbol, bid, ask)

        except Exception as e:

            self.logger.error(f"Ticker error {symbol}: {e}")

    # ======================================================
    # AUTOTRADING
    # ======================================================

    async def start(self):

        self.autotrading_enabled = True

        self.logger.info(f"AutoTrading enabled for {self.symbols}")

        if not self.orchestrator.running:
            asyncio.get_event_loop().create_task(self.orchestrator.start())
            await self.ws_manager.start()
            self.ws_manager.running = True
            self.connection_signal.emit("connected")

    async def stop(self):

        self.autotrading_enabled = False

        await self.orchestrator.shutdown()

        self.logger.info("AutoTrading disabled")

    async def _on_order_book_callback(self, symbol, bids, asks):

        try:

            if "/" not in symbol and symbol.endswith("USDT"):
                symbol = symbol[:-4] + "/USDT"

            if self.orderbook_signal:
                self.orderbook_signal.emit(symbol, bids, asks)

        except Exception as e:

            self.logger.error(f"Orderbook error {symbol}: {e}")
            traceback.print_exc()

    async def connector(self):
        if self.broker:
            await  self.broker.connect()
