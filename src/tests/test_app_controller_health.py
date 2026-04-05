import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.app_controller import AppController
from broker.paper_broker import PaperBroker


class _CleanupTask:
    def __init__(self, sink, name):
        self._sink = sink
        self._name = name
        self._done = False

    def done(self):
        return self._done

    def cancel(self):
        self._done = True
        self._sink.append(self._name)


class _ExecutorRecorder:
    def __init__(self, sink):
        self._sink = sink

    def shutdown(self, wait=False, cancel_futures=True):
        self._sink.append((bool(wait), bool(cancel_futures)))


class _FakeTerminal:
    def __init__(self, calls):
        self.detached_tool_windows = {}
        self._calls = calls
        self._ui_shutting_down = False
        self.logout_requested = SimpleNamespace(connect=lambda handler: self._calls["terminal"].append(("logout_connect", handler)))

    def _disconnect_controller_signals(self):
        self._calls["terminal"].append("disconnect")

    def show(self):
        self._calls["terminal"].append("show")

    def showNormal(self):
        self._calls["terminal"].append("show_normal")

    def raise_(self):
        self._calls["terminal"].append("raise")

    def activateWindow(self):
        self._calls["terminal"].append("activate")

    def close(self):
        self._calls["terminal"].append("close")

    def deleteLater(self):
        self._calls["terminal"].append("delete")


class _FakeTradingSystem:
    def __init__(self, calls):
        self._calls = calls
        self._signal_selection_executor = _ExecutorRecorder(self._calls["signal_shutdown"])

    async def stop(self, wait_for_background_workers=False):
        self._calls["trading_stop"].append(bool(wait_for_background_workers))
        self._shutdown_signal_selection_executor(wait=wait_for_background_workers)

    def _shutdown_signal_selection_executor(self, wait=False):
        executor = getattr(self, "_signal_selection_executor", None)
        if executor is None:
            return
        self._signal_selection_executor = None
        executor.shutdown(wait=wait, cancel_futures=True)


def _make_cleanup_controller(*, telegram_error=None):
    calls = {
        "telegram": [],
        "news": [],
        "cancelled": [],
        "ranking_shutdown": [],
        "signal_shutdown": [],
        "trading_stop": [],
        "progress": [],
        "terminal": [],
        "stack_removed": [],
        "broker": [],
        "emitted": [],
    }
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.shutdown")
    controller.connected = True
    controller.connection_signal = SimpleNamespace(
        emit=lambda state: calls["emitted"].append(state)
    )

    async def stop_telegram_service():
        calls["telegram"].append("stop")
        if telegram_error is not None:
            raise telegram_error

    async def close_news_service():
        calls["news"].append("close")

    async def close_broker():
        calls["broker"].append("close")

    controller._stop_telegram_service = stop_telegram_service
    controller.news_service = SimpleNamespace(close=close_news_service)
    controller._news_cache = {"cached": 1}
    controller._news_inflight = {"inflight": 1}
    controller._strategy_auto_assignment_task = _CleanupTask(calls["cancelled"], "auto")
    controller._strategy_auto_assignment_deferred_task = _CleanupTask(calls["cancelled"], "deferred")
    controller._strategy_ranking_executor = _ExecutorRecorder(calls["ranking_shutdown"])
    controller._terminal_runtime_restore_task = _CleanupTask(calls["cancelled"], "restore")
    controller.strategy_auto_assignment_enabled = True
    controller.time_frame = "1h"
    controller._update_strategy_auto_assignment_progress = lambda **changes: calls["progress"].append(changes)
    controller._ticker_task = _CleanupTask(calls["cancelled"], "ticker")
    controller._ws_task = _CleanupTask(calls["cancelled"], "ws")
    controller._ws_bus_task = _CleanupTask(calls["cancelled"], "ws_bus")
    controller.ws_bus = object()
    controller.ws_manager = object()
    controller.trading_system = _FakeTradingSystem(calls)
    controller.behavior_guard = object()
    controller._live_agent_decision_events = {"live": 1}
    controller._live_agent_runtime_feed = ["event"]
    controller.terminal = _FakeTerminal(calls)
    controller.stack = SimpleNamespace(removeWidget=lambda widget: calls["stack_removed"].append(widget))
    controller.broker = SimpleNamespace(close=close_broker)
    return controller, calls


def test_run_startup_health_check_pushes_notification_once_for_same_result():
    notifications = []
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.health")
    controller.symbols = ["BTC/USDT"]
    controller.time_frame = "1h"
    controller.health_check_report = []
    controller.health_check_summary = "Not run"
    controller._startup_health_notification_signature = None
    controller.terminal = SimpleNamespace(
        _push_notification=lambda *args, **kwargs: notifications.append((args, kwargs))
    )

    async def fetch_status():
        return {"broker": "paper", "status": "ok"}

    async def fetch_orderbook(_symbol, limit=10):
        return {"bids": [[1.0, 1.0]], "asks": [[1.1, 1.0]]}

    async def fetch_positions():
        return []

    async def fetch_open_orders(symbol=None, limit=10):
        return []

    async def fetch_ohlcv(symbol, timeframe="1h", limit=50):
        return [[1, 1, 1, 1, 1, 1]]

    controller.broker = SimpleNamespace(
        fetch_status=fetch_status,
        fetch_ohlcv=fetch_ohlcv,
        fetch_orderbook=fetch_orderbook,
        fetch_positions=fetch_positions,
        fetch_open_orders=fetch_open_orders,
    )
    controller.get_broker_capabilities = lambda: {
        "connectivity": True,
        "ticker": True,
        "candles": True,
        "orderbook": True,
        "open_orders": True,
        "positions": True,
        "trading": True,
        "order_tracking": True,
    }
    controller._broker_is_connected = lambda broker=None: True

    async def fetch_balances(_broker=None):
        return {"free": {"USD": 1000.0}}

    async def fetch_ticker(symbol):
        return {"symbol": symbol, "last": 100.0}

    controller._fetch_balances = fetch_balances
    controller._safe_fetch_ticker = fetch_ticker

    asyncio.run(controller.run_startup_health_check())
    asyncio.run(controller.run_startup_health_check())

    assert "pass" in controller.health_check_summary
    assert len(notifications) == 1
    assert notifications[0][0][0] == "Startup health check"


def test_shutdown_for_exit_waits_for_background_workers():
    controller, calls = _make_cleanup_controller()

    asyncio.run(controller.shutdown_for_exit())

    assert calls["ranking_shutdown"] == [(True, True)]
    assert calls["trading_stop"] == [True]
    assert calls["signal_shutdown"] == [(True, True)]
    assert calls["broker"] == ["close"]
    assert calls["emitted"] == ["disconnected"]
    assert calls["terminal"] == ["disconnect", "delete"]
    assert len(calls["stack_removed"]) == 1


def test_cleanup_session_continues_after_step_failure():
    controller, calls = _make_cleanup_controller(telegram_error=RuntimeError("boom"))

    asyncio.run(controller._cleanup_session(stop_trading=True, close_broker=True))

    assert calls["telegram"] == ["stop"]
    assert calls["news"] == ["close"]
    assert calls["ranking_shutdown"] == [(False, True)]
    assert calls["trading_stop"] == [False]
    assert calls["signal_shutdown"] == [(False, True)]
    assert calls["broker"] == ["close"]
    assert calls["terminal"] == ["disconnect", "delete"]
    assert len(calls["stack_removed"]) == 1
    assert controller.trading_system is None
    assert controller.terminal is None
    assert controller.broker is None
    assert controller.ws_bus is None
    assert controller.ws_manager is None


def test_initialize_trading_keeps_dashboard_visible(monkeypatch):
    calls = {"terminal": [], "stack_set": [], "stack_add": [], "created_tasks": []}

    class _FakeTerminalWindow(_FakeTerminal):
        def __init__(self, controller):
            super().__init__(calls)
            self.controller = controller

        def load_persisted_runtime_data(self):
            return asyncio.sleep(0)

    monkeypatch.setattr("frontend.ui.app_controller.Terminal", _FakeTerminalWindow)

    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.dashboard_visible")
    controller.terminal = None
    controller.dashboard = SimpleNamespace()
    controller.stack = SimpleNamespace(
        addWidget=lambda widget: calls["stack_add"].append(widget),
        setCurrentWidget=lambda widget: calls["stack_set"].append(widget),
    )
    controller._fit_window_to_available_screen = lambda *args, **kwargs: calls["terminal"].append("fit")
    controller._handle_session_registry_changed = lambda: calls["terminal"].append("refresh_registry")
    def _record_task(coro, name):
        calls["created_tasks"].append(name)
        close_coro = getattr(coro, "close", None)
        if callable(close_coro):
            close_coro()
        return None

    controller._create_task = _record_task
    controller._extract_balance_equity_value = lambda balances: 1000.0
    controller.balances = {"total": {"USD": 1000.0}}
    controller.equity_signal = SimpleNamespace(emit=lambda value: calls["terminal"].append(("equity", value)))
    controller.run_startup_health_check = lambda: asyncio.sleep(0)
    controller._terminal_runtime_restore_task = None
    controller._on_logout_requested = lambda: None

    asyncio.run(controller.initialize_trading())

    assert controller.terminal is not None
    assert "show" in calls["terminal"]
    assert "raise" in calls["terminal"]
    assert "activate" in calls["terminal"]
    assert calls["stack_add"] == []
    assert calls["stack_set"] == []
    assert "terminal_runtime_restore" in calls["created_tasks"]
    assert "startup_health_check" in calls["created_tasks"]


def test_resolve_initial_storage_preferences_prefers_remote_env_when_unset(monkeypatch):
    class _FakeSettings:
        def contains(self, _key):
            return False

        def value(self, _key, default=None):
            return default

    monkeypatch.setenv(
        "SOPOTEK_DATABASE_URL",
        "mysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?chartset=utf8mb4",
    )

    mode, url = AppController._resolve_initial_storage_preferences(_FakeSettings())

    assert mode == "remote"
    assert url == (
        "mysql+pymysql://sopotek:sopotek_local@mysql:3306/"
        "sopotek_trading?charset=utf8mb4"
    )


def test_resolve_initial_storage_preferences_respects_saved_local_mode(monkeypatch):
    class _FakeSettings:
        def contains(self, key):
            return key in {"storage/database_mode", "storage/database_url"}

        def value(self, key, default=None):
            if key == "storage/database_mode":
                return "local"
            if key == "storage/database_url":
                return ""
            return default

    monkeypatch.setenv(
        "SOPOTEK_DATABASE_URL",
        "mysql+pymysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?charset=utf8mb4",
    )

    mode, url = AppController._resolve_initial_storage_preferences(_FakeSettings())

    assert mode == "local"
    assert url == ""


def test_resolve_initial_storage_preferences_env_mode_overrides_saved_local(monkeypatch):
    class _FakeSettings:
        def contains(self, key):
            return key in {"storage/database_mode", "storage/database_url"}

        def value(self, key, default=None):
            if key == "storage/database_mode":
                return "local"
            if key == "storage/database_url":
                return ""
            return default

    monkeypatch.setenv("SOPOTEK_DATABASE_MODE", "remote")
    monkeypatch.setenv(
        "SOPOTEK_DATABASE_URL",
        "mysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?chartset=utf8mb4",
    )

    mode, url = AppController._resolve_initial_storage_preferences(_FakeSettings())

    assert mode == "remote"
    assert url == (
        "mysql+pymysql://sopotek:sopotek_local@mysql:3306/"
        "sopotek_trading?charset=utf8mb4"
    )


def test_setup_data_requires_remote_storage_when_env_forces_remote(monkeypatch):
    controller = AppController.__new__(AppController)
    captured = {}

    controller.database_mode = "remote"
    controller.database_url = "mysql+pymysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?charset=utf8mb4"
    controller.configure_storage_database = lambda **kwargs: captured.update(kwargs)
    controller._restore_performance_state = lambda: None

    monkeypatch.setenv("SOPOTEK_DATABASE_MODE", "remote")
    monkeypatch.setenv("SOPOTEK_DATABASE_URL", controller.database_url)

    AppController._setup_data(controller)

    assert captured["database_mode"] == "remote"
    assert captured["database_url"] == controller.database_url
    assert captured["persist"] is False
    assert captured["raise_on_error"] is True


def test_build_broker_for_login_routes_crypto_paper_sessions_to_paper_broker():
    controller = AppController.__new__(AppController)
    controller.logger = logging.getLogger("test.app_controller.paper_routing")
    controller.initial_capital = 25000.0
    controller.paper_data_exchange = None
    controller.paper_data_exchanges = []
    config = SimpleNamespace(
        broker=SimpleNamespace(
            type="crypto",
            exchange="binanceus",
            mode="paper",
            params={},
            options={},
        )
    )
    controller.config = config

    broker = controller._build_broker_for_login(config)

    assert isinstance(broker, PaperBroker)
    assert config.broker.params["paper_data_exchange"] == "binanceus"
    assert config.broker.params["paper_data_exchanges"][0] == "binanceus"
    assert controller.paper_data_exchange == "binanceus"


def test_friendly_initialization_error_explains_binanceus_testnet_restriction():
    controller = AppController.__new__(AppController)
    message = controller._friendly_initialization_error(
        "binanceus GET https://testnet.binance.vision/api/v3/time 451 restricted location"
    )

    assert "PaperBroker" not in message
    assert "PAPER mode" in message
    assert "LIVE mode" in message
    assert "Binance US sandbox routing" in message


def test_friendly_startup_error_explains_local_mysql_volume_credential_drift():
    controller = AppController.__new__(AppController)
    controller.database_url = "mysql+pymysql://sopotek:sopotek_local@mysql:3306/sopotek_trading?charset=utf8mb4"

    message = controller._friendly_startup_error(
        "sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError) "
        "(1045, \"Access denied for user 'sopotek'@'172.18.0.3' (using password: YES)\")"
    )

    assert "server rejected the username or password" in message
    assert "mysql_data" in message
    assert "docker compose down -v" in message
    assert "mysql+pymysql://sopotek:***@mysql:3306/sopotek_trading?charset=utf8mb4" in message
