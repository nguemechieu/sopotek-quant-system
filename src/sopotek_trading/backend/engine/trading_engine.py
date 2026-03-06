import traceback
import pandas as pd

from sopotek_trading.backend.analytics.performance_engine import PerformanceEngine
from sopotek_trading.backend.market.candle_buffer import CandleBuffer
from sopotek_trading.backend.engine.strategy_engine import StrategyEngine
from sopotek_trading.backend.portfolio.portfolio import Portfolio
from sopotek_trading.backend.portfolio.portfolio_manager import PortfolioManager
from sopotek_trading.backend.quant.regime_detector import MarkovRegimeDetector
from sopotek_trading.backend.strategy.strategy import Strategy
from sopotek_trading.backend.utils.utils import candles_to_df


class TradingEngine:

    # ==========================================================
    # INIT
    # ==========================================================

    def __init__(self, controller):

        self.controller = controller
        self.logger = controller.logger

        # Shared infrastructure
        self.execution_manager = controller.execution_manager
        self.broker = controller.broker
        self.trade_signal = getattr(controller, "trade_signal", None)

        self.symbols = controller.symbols
        self.timeframe = controller.timeframe

        self.order_type = controller.order_type
        self.slippage = controller.slippage

        self.running = False
        self.tasks = []

        # Models
        self.ml_models = controller.ml_models

        # Regime detection
        self.regime_detector = MarkovRegimeDetector(n_regimes=4)

        # Strategy layer
        self.strategy = Strategy(controller)
        self.strategy_engine = StrategyEngine(controller)

        # Portfolio system
        self.portfolio = Portfolio(broker=self.broker)

        self.portfolio_manager = PortfolioManager(
            self.broker,
            self.portfolio,
            controller.risk_engine
        )

        # Performance tracking
        self.performance_engine = PerformanceEngine(controller)

        self.logger.info("TradingEngine initialized")

    # ==========================================================
    # START
    # ==========================================================

    async def start(self):

        if self.running:
            return

        self.running = True

        self.logger.info("TradingEngine started")
        await self.broker.connect()


    # ==========================================================
    # STOP
    # ==========================================================

    async def stop(self):

        self.running = False

        for task in self.tasks:
            task.cancel()

        self.tasks.clear()

        self.logger.info("TradingEngine stopped")

    # ======================================================
    # MAIN TRADE EXECUTION
    # ======================================================

    async def run_trade(self, symbol: str, data:CandleBuffer):

        df=candles_to_df(candles=data)
        try:

            if df is None or df.empty:
                return

            model = self.ml_models.get(symbol)

            if not model:
                return

            # ===============================
            # ML SIGNAL
            # ===============================

            analysis = model.predict(df)

            signal = analysis.get("signal", "HOLD")

            if signal not in ["BUY", "SELL"]:
                self.logger.info(
                    "Waiting ...."
                )
                return

            entry_price = float(analysis.get("current_price", 0))
            confidence = float(analysis.get("confidence", 0.5))

            if entry_price <= 0:
                self.logger.info(
                    "Entry price is lower than 0"
                )
                return

            # ===============================
            # REGIME FILTER
            # ===============================

            if not self.regime_detector.fitted:
                self.regime_detector.fit(df)

            regime_data = self.regime_detector.predict(df)

            regime = regime_data.get("regime")
            prob = regime_data.get("probability", 0)

            if prob < 0.55:
                return

            if regime == "HIGH_VOL":
                confidence *= 0.5

            if regime == "TREND_UP" and signal == "SELL":
                return

            if regime == "TREND_DOWN" and signal == "BUY":
                return

            # ===============================
            # VOLATILITY
            # ===============================

            vol = df["close"].pct_change().rolling(20).std().iloc[-1]

            if pd.isna(vol) or vol <= 0:
                vol = 0.01

            # ===============================
            # RISK CALCULATION
            # ===============================

            stop_distance = entry_price * vol * 2

            if signal == "BUY":
                stop_price = entry_price - stop_distance
                take_profit = entry_price + stop_distance
            else:
                stop_price = entry_price + stop_distance
                take_profit = entry_price - stop_distance

            size = self.controller.risk_engine.position_size(
                entry_price=entry_price,
                stop_price=stop_price,
                confidence=confidence,
                volatility=vol
            )

            if size <= 0:
                return

            # ===============================
            # PORTFOLIO CHECK
            # ===============================

            if self.portfolio.has_position(symbol):
                return

            # ===============================
            # EXECUTE ORDER
            # ===============================

            result = await self.execution_manager.execute_trade(
                symbol=symbol,
                side=signal.lower(),
                amount=size,
                order_type=self.order_type,
                price=entry_price,
                stop_loss=stop_price,
                take_profit=take_profit,
                slippage=self.slippage,
            )

            if not result:
                return

            # ===============================
            # PORTFOLIO UPDATE
            # ===============================

            self.portfolio_manager.update_fill(
                symbol=symbol,
                side=signal,
                quantity=size,
                price=entry_price
            )

            trade_data = {
                "symbol": symbol,
                "side": signal,
                "price": entry_price,
                "size": size,
                "confidence": confidence,
                "volatility": vol,
                "regime": regime
            }

            if self.trade_signal:
                self.trade_signal.emit(trade_data)

            self.performance_engine.record_trade(trade_data)

            self.logger.info(
                f"TRADE EXECUTED | {symbol} | {signal} | size={size}"
            )

        except Exception as e:

            self.logger.error(f"run_trade error {symbol}: {e}")
            traceback.print_exc()