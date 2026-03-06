import asyncio
import logging
import os
import sys
import traceback

import pandas as pd
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from sopotek_trading.backend.analytics.performance_engine import PerformanceEngine
from sopotek_trading.backend.broker.broker_factory import BrokerFactory
from sopotek_trading.backend.broker.rate_limiter import RateLimiter
from sopotek_trading.backend.market.candle_buffer import CandleBuffer
from sopotek_trading.backend.managers.broker_manager import BrokerManager
from sopotek_trading.backend.market.order_book_buffer import OrderBookBuffer
from sopotek_trading.backend.market.symbols_buffer import SymbolsBuffer
from sopotek_trading.backend.market.ticker_buffer import TickerBuffer
from sopotek_trading.backend.sopotek_trading import SopotekTrading
from sopotek_trading.backend.strategy.breakout_strategy import BreakoutStrategy
from sopotek_trading.backend.strategy.macd_strategy import MACDStrategy
from sopotek_trading.backend.strategy.mean_reversion_strategy import MeanReversionStrategy
from sopotek_trading.backend.strategy.strategy_orchestrator import StrategyOrchestrator
from sopotek_trading.backend.strategy.trend_strategy import TrendStrategy
from sopotek_trading.frontend.ui.dashboard import Dashboard
from sopotek_trading.frontend.ui.terminal import Terminal


class AppController(QMainWindow):
    # ================================
    # Signals
    # ================================
    symbols_signal = Signal(str, list)

    candle_signal = Signal(str, object)
    equity_signal = Signal(float)

    trade_signal = Signal(dict)
    ticker_signal = Signal(str, float, float)
    connection_signal = Signal(str)
    orderbook_signal = Signal(str, list, list)
    strategy_debug_signal = Signal(dict)
    autotrade_toggle = Signal(bool)

    logout_requested = Signal(str)
    training_status_signal = Signal(str, str)

    # ================================
    # INIT
    # ================================

    def __init__(self):

        super().__init__()
        self.broker = None
        self.broker_manager = BrokerManager()
        self.trading_system = None
        self.controller = self

        self.type = "crypto"
        self.trading_app = None
        self.terminal = None
        self.initial_capital = 10000
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.addHandler(logging.FileHandler("logs/app.log"))
        self.rate_limiter = RateLimiter()
        self.rate_limit = 5
        self.trading_engine = None
        self.ws_manager = None
        self.current_equity = 0.0
        self.candle_buffer=CandleBuffer() ## use symbol and timeframe for filter


        self.ml_models= None

        self.slippage = 3
        self.order_type = "market"
        self.stop_loss = 100
        self.take_profit = 100
        self.amount = 0.01
        self.price = 1.2
        self.commission = 0.003
        self.account_equity = 0.0


        self.orderbook = []
        self.candles = []
        self.tickers = []

        self.limit = 1000

        self.symbols_buffer=SymbolsBuffer()

        self.candles_buffer=CandleBuffer(self.limit) #Candles Buffer not pd.Dataframe
        self.ticker_buffer=TickerBuffer(self.limit)
        self.order_book_buffer=OrderBookBuffer(self.limit)



        self.symbols=[]
        self.balances=pd.DataFrame()
        self.practice=False




        self.regime_detector=None


        self.risk_engine = None
        self.portfolio = None
        self.execution_manager = None

        self.symbols = ["BTC/USDT", "ETH/USDT", "XLM/USDT"]
        self.timeframe = "1h"
        self.time_frame=self.timeframe
        self.running = False
        self.account_equity = 0.0
        self.max_portfolio_risk = 1000
        self.max_risk_per_trade = 3
        self.max_daily_drawdown = 13
        self.max_position_size_pct = 1
        self.max_gross_exposure_pct = 500
        self.paper_balance = 10000
        self.paper_positions = {}
        self.paper_order_id = 1
        self.account_id = "wer"
        self.config = {
            "exchange_type": "crypto",
            "broker": {
                "exchange": "binanceus",
                "mode": "paper",
                "api_key": "...",
                "secret": "..."
            },
            "strategy": "LSTM",
            "risk": {
                "risk_percent": 2
            },
            "system": {
                "limit": 1000,
                "equity_refresh": 60,
                "rate_limit": 3
            }
        }
        self.confidence=0
        self.symbols_table=None
        self.ai_signal=None
        self.connected=False
        self.exchange_type="crypto"

        try:

            self.strategy = None

            self._setup_paths()
            self._setup_config()
            self._setup_data()
            self._setup_strategies()
            self._setup_ui()
            self.strategy_engine = None

        except Exception as e:
            traceback.print_exc()
            self.logger.error(e)

    # ================================
    # Setup Paths
    # ================================

    def _setup_paths(self):

        self.data_dir = "data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)




    # ================================
    # Setup Config
    # ================================

    def _setup_config(self):

        self.exchange_name = "binanceus"

        self.api_key = "jhk"
        self.secret = "jkl"

        self.mode = "live"
        self.order_type = "market"

        self.time_frame = "1d"
        self.limit = 1000

        self.type=None
        self.broker=None

        self.balance = 0.0
        self.equity = 0.0
        self.daily_loss = 0.0
        self.daily_gains = 0.0
        self.account_equity = 0
        self.max_risk_per_trade = 10
        self.max_position_size_pct = 12
        self.max_gross_exposure_pct = 4
        self.max_daily_drawdown = 50
        self.max_portfolio_risk = 500

        self.time_frame = "1d"
        self.metrics = {'total_trades': 120, 'win_rate': 0.55, 'profit': 2400, 'balance': 12400}
        self.strategies = [TrendStrategy(),MACDStrategy(), MeanReversionStrategy(), BreakoutStrategy()]
        self.weights = {"trend": 0.5, "mean_reversion": 0.2, "breakout": 0.2, "ml": 0.1}
        self.strategy_weight = 1
        self.orchestrator = StrategyOrchestrator(self.strategies, self.metrics)

        self.symbols_list=[]

    # ================================
    # Setup Data
    # ================================

    def _setup_data(self):

        self.historical_data = pd.DataFrame(
            columns=[
                "symbol",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        self.historical_returns = pd.DataFrame(
            columns=[
                "symbol",
                "trades",
                "returns"
            ]
        )

        self.historical_data.to_csv(
            f"{self.data_dir}\\historical_data.csv",
            index=False
        )

        self.historical_returns.to_csv(
            f"{self.data_dir}\\historical_returns.csv",
            index=False
        )

    # ================================
    # Setup Strategies
    # ================================

    def _setup_strategies(self):

        self.metrics = {
            "total_trades": 0,
            "win_rate": 0,
            "profit": 0,
            "balance": 0
        }

        self.strategies = None

        self.weights = {
            "trend": 0.5,
            "mean_reversion": 0.2,
            "breakout": 0.2,
            "ml": 0.1
        }



        self.performance_engine = PerformanceEngine(
            controller=self.controller
        )
        self.orchestrator = StrategyOrchestrator(
            self.strategies,
            self.metrics
        )

    # ================================
    # Setup UI
    # ================================

    def _setup_ui(self):

        self.setWindowTitle("Sopotek Trading Platform")
        self.resize(1600, 900)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = Dashboard(self.controller)
        self.stack.addWidget(self.dashboard)

        self.terminal = None

        self.dashboard.login_success.connect(
            lambda config: asyncio.create_task(self.handle_login(config))
        )
    # ================================
    # Login Handler
    ##################################
    async def handle_login(self, config):

     try:

        self.dashboard.show_loading()

        # -------------------------
        # Store configuration
        # -------------------------
        self.config = config

        self.exchange_type = config["exchange_type"]
        self.exchange_name = config["broker"]["exchange"]
        self.mode = config["broker"]["mode"]

        self.api_key = config["broker"].get("api_key")
        self.secret = config["broker"].get("secret")
        self.account_id = config["broker"].get("account_id")

        # -------------------------
        # Create broker
        # -------------------------
        broker = BrokerFactory.create(self)

        if broker is None:
            raise RuntimeError("Broker creation failed")

        self.broker = broker

        # -------------------------
        # Connect broker
        # -------------------------
        await broker.connect()

        self.logger.info("Broker connected")

        # -------------------------
        # Start trading system
        # -------------------------
        self.trading_system = SopotekTrading(controller=self)

        await self.trading_system.initialize()

        await self.initialize_trading()

        self.dashboard.hide_loading()

     except Exception as e:

        self.dashboard.hide_loading()

        QMessageBox.critical(self, "Initialization Failed", str(e))

        self.logger.error(e)
    # ================================
    # Initialize Trading
    # ================================

    async def initialize_trading(self):

     try:

        await self._cleanup_session()

        self.terminal = Terminal(controller=self)

        self.stack.addWidget(self.terminal)
        self.stack.setCurrentWidget(self.terminal)

        self.terminal.logout_requested.connect(
            lambda: asyncio.create_task(self.logout())
        )

     except Exception as e:

        QMessageBox.critical(self, "Initialization Failed", str(e))

    # ================================
    # Cleanup Session
    # ================================

    async def _cleanup_session(self):

     if self.trading_system:

        await self.trading_system.shutdown()

        self.trading_system = None

     if self.terminal:

        self.stack.removeWidget(self.terminal)
        self.terminal.deleteLater()
        self.terminal = None

    # ================================
    # Logout
    # ================================

    async def logout(self):

        try:

            await self._cleanup_session()

        finally:

            self.stack.setCurrentWidget(self.dashboard)
            self.dashboard.setEnabled(True)
            self.dashboard.connect_button.setText("Connect")
