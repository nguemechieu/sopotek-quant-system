import asyncio

from sopotek_trading.backend.engine.trading_engine import TradingEngine


class Orchestrator:

    def __init__(self, controller):

        self.controller = controller
        self.logger = controller.logger
        self.candles_buffer = controller.candles_buffer

        self.trading_engine = TradingEngine(controller=controller)

        self.running = False
        self.symbol_tasks = {}

    # ======================================================
    # START
    # ======================================================

    async def start(self):

        if self.running:
            self.logger.warning("Orchestrator already running")
            return

        self.running = True

        self.logger.info("Orchestrator started")

        try:

            await self.trading_engine.start()


            # Start symbol workers
            for symbol in self.controller.symbols:

                task = asyncio.create_task(
                    self._symbol_trading_worker(symbol),
                    name=f"symbol_trading_worker_{symbol}"
                )

                self.symbol_tasks[symbol] = task

            self.logger.info(
                f"Symbol workers started: {len(self.symbol_tasks)}"
            )

        except Exception as e:

            self.logger.error(f"Orchestrator start failed: {e}")

    # ======================================================
    # SYMBOL WORKER
    # ======================================================

    async def _symbol_trading_worker(self, symbol):

        self.logger.info(f"Worker started for {symbol}")

        while self.running:

            try:

                candle = self.candles_buffer.get(symbol)

                if candle:

                    await self.trading_engine.run_trade(
                        symbol,
                        candle
                    )

            except Exception as e:

                self.logger.error(
                    f"Worker error {symbol}: {e}"
                )

            await asyncio.sleep(0.05)

    # ======================================================
    # STOP
    # ======================================================

    async def shutdown(self):

        if not self.running:
            return

        self.logger.info("Stopping orchestrator")

        self.running = False

        # Cancel symbol tasks
        for symbol, task in self.symbol_tasks.items():

            try:
                task.cancel()
            except Exception:
                pass

        # Wait for tasks to finish
        if self.symbol_tasks:

            await asyncio.gather(
                *self.symbol_tasks.values(),
                return_exceptions=True
            )

        self.symbol_tasks.clear()

        await self.trading_engine.stop()

        self.logger.info("Orchestrator stopped")