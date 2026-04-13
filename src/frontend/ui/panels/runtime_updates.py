import asyncio
import time


def _runtime_broker_name(terminal):
    broker = getattr(getattr(terminal, "controller", None), "broker", None)
    return str(getattr(broker, "exchange_name", "") or "").strip().lower()


def _positions_refresh_interval_seconds(terminal):
    broker_name = _runtime_broker_name(terminal)
    if broker_name == "coinbase":
        return 6.0
    if broker_name == "alpaca":
        return 5.0
    return 0.0


def _open_orders_refresh_interval_seconds(terminal):
    broker_name = _runtime_broker_name(terminal)
    if broker_name == "coinbase":
        return 5.0
    if broker_name == "alpaca":
        return 5.0
    return 0.0


def _assets_refresh_interval_seconds(terminal):
    broker_name = _runtime_broker_name(terminal)
    if broker_name in {"coinbase", "alpaca"}:
        return 8.0
    return 10.0


def _history_refresh_interval_seconds(terminal):
    broker_name = _runtime_broker_name(terminal)
    if broker_name in {"coinbase", "alpaca"}:
        return 12.0
    return 15.0


async def refresh_positions_async(terminal):
    if terminal._ui_shutting_down:
        return
    broker = getattr(terminal.controller, "broker", None)
    positions = []
    if broker is not None and hasattr(broker, "fetch_positions"):
        try:
            positions = await broker.fetch_positions()
        except Exception as exc:
            terminal.logger.debug("Positions refresh failed: %s", exc)

    if not positions:
        positions = terminal._portfolio_positions_snapshot()

    terminal._latest_positions_snapshot = positions or []
    positions_snapshot = terminal._latest_positions_snapshot
    active_positions_snapshot = getattr(terminal, "_active_positions_snapshot", None)
    if callable(active_positions_snapshot):
        positions_snapshot = active_positions_snapshot()
    terminal._populate_positions_table(positions_snapshot)
    terminal._refresh_position_analysis_window()
    review_queue = getattr(getattr(terminal, "controller", None), "queue_pending_user_trade_position_reviews", None)
    if callable(review_queue):
        try:
            review_queue(positions_snapshot)
        except Exception as exc:
            terminal.logger.debug("Pending user trade review scheduling failed: %s", exc)
    terminal._last_positions_refresh_at = time.monotonic()


def schedule_positions_refresh(terminal):
    task = getattr(terminal, "_positions_refresh_task", None)
    if task is not None and not task.done():
        return

    interval_seconds = _positions_refresh_interval_seconds(terminal)
    if interval_seconds > 0:
        last_refresh_at = float(getattr(terminal, "_last_positions_refresh_at", 0.0) or 0.0)
        if (time.monotonic() - last_refresh_at) < interval_seconds:
            return

    try:
        terminal._positions_refresh_task = asyncio.get_event_loop().create_task(terminal._refresh_positions_async())
    except Exception as exc:
        terminal.logger.debug("Unable to schedule positions refresh: %s", exc)


async def refresh_open_orders_async(terminal):
    if terminal._ui_shutting_down:
        return
    broker = getattr(terminal.controller, "broker", None)
    orders = []
    if broker is not None and hasattr(broker, "fetch_open_orders"):
        try:
            snapshot = getattr(broker, "fetch_open_orders_snapshot", None)
            if callable(snapshot):
                orders = await snapshot(symbols=getattr(terminal.controller, "symbols", []), limit=200)
            else:
                active_symbol = str(terminal._current_chart_symbol() or "").strip()
                request = {"limit": 200}
                if active_symbol:
                    request["symbol"] = active_symbol
                orders = await broker.fetch_open_orders(**request)
        except TypeError:
            active_symbol = str(terminal._current_chart_symbol() or "").strip()
            if active_symbol:
                orders = await broker.fetch_open_orders(active_symbol, 200)
            else:
                orders = await broker.fetch_open_orders()
        except Exception as exc:
            terminal.logger.debug("Open orders refresh failed: %s", exc)

    terminal._latest_open_orders_snapshot = orders or []
    orders_snapshot = terminal._latest_open_orders_snapshot
    active_open_orders_snapshot = getattr(terminal, "_active_open_orders_snapshot", None)
    if callable(active_open_orders_snapshot):
        orders_snapshot = active_open_orders_snapshot()
    terminal._populate_open_orders_table(orders_snapshot)
    terminal._last_open_orders_refresh_at = time.monotonic()


async def refresh_assets_async(terminal):
    if terminal._ui_shutting_down:
        return
    controller = getattr(terminal, "controller", None)
    broker = getattr(controller, "broker", None)
    balances = dict(getattr(controller, "balances", {}) or {})
    if broker is not None and hasattr(broker, "fetch_balance"):
        try:
            fetch_balances = getattr(controller, "_fetch_balances", None)
            if callable(fetch_balances):
                balances = await fetch_balances(broker)
            else:
                payload = await broker.fetch_balance()
                balances = dict(payload or {}) if isinstance(payload, dict) else {"raw": payload}
            if controller is not None:
                controller.balances = dict(balances or {})
                if hasattr(controller, "balance"):
                    controller.balance = dict(balances or {})
        except Exception as exc:
            terminal.logger.debug("Assets refresh failed: %s", exc)

    terminal._latest_assets_snapshot = dict(balances or {})
    terminal._populate_assets_table(terminal._latest_assets_snapshot)
    terminal._last_assets_refresh_at = time.monotonic()


async def refresh_order_history_async(terminal):
    if terminal._ui_shutting_down:
        return
    controller = getattr(terminal, "controller", None)
    broker = getattr(controller, "broker", None)
    rows = []

    fetcher = getattr(controller, "fetch_order_history", None)
    if callable(fetcher):
        try:
            rows = list(await fetcher(limit=200) or [])
        except Exception as exc:
            terminal.logger.debug("Order-history refresh via controller failed: %s", exc)

    if not rows and broker is not None:
        try:
            if hasattr(broker, "fetch_orders"):
                rows = list(await broker.fetch_orders(limit=200) or [])
        except TypeError:
            try:
                rows = list(await broker.fetch_orders() or [])
            except Exception as exc:
                terminal.logger.debug("Order-history refresh failed: %s", exc)
        except Exception as exc:
            terminal.logger.debug("Order-history refresh failed: %s", exc)

        if not rows:
            try:
                if hasattr(broker, "fetch_closed_orders"):
                    rows = list(await broker.fetch_closed_orders(limit=200) or [])
            except TypeError:
                try:
                    rows = list(await broker.fetch_closed_orders() or [])
                except Exception as exc:
                    terminal.logger.debug("Closed-order history refresh failed: %s", exc)
            except Exception as exc:
                terminal.logger.debug("Closed-order history refresh failed: %s", exc)

    terminal._latest_order_history_snapshot = list(rows or [])
    terminal._populate_order_history_table(terminal._latest_order_history_snapshot)
    terminal._last_order_history_refresh_at = time.monotonic()


async def refresh_trade_history_async(terminal):
    if terminal._ui_shutting_down:
        return
    controller = getattr(terminal, "controller", None)
    rows = []

    fetcher = getattr(controller, "fetch_trade_history", None)
    if callable(fetcher):
        try:
            rows = list(await fetcher(limit=200) or [])
        except Exception as exc:
            terminal.logger.debug("Trade-history refresh via controller failed: %s", exc)

    if not rows:
        loader = getattr(controller, "_load_recent_trades", None)
        if callable(loader):
            try:
                rows = list(await loader(limit=200) or [])
            except Exception as exc:
                terminal.logger.debug("Trade-history refresh from repository failed: %s", exc)

    terminal._latest_trade_history_snapshot = list(rows or [])
    terminal._populate_trade_history_table(terminal._latest_trade_history_snapshot)
    terminal._last_trade_history_refresh_at = time.monotonic()


def schedule_open_orders_refresh(terminal):
    task = getattr(terminal, "_open_orders_refresh_task", None)
    if task is not None and not task.done():
        return

    interval_seconds = _open_orders_refresh_interval_seconds(terminal)
    if interval_seconds > 0:
        last_refresh_at = float(getattr(terminal, "_last_open_orders_refresh_at", 0.0) or 0.0)
        if (time.monotonic() - last_refresh_at) < interval_seconds:
            return

    try:
        terminal._open_orders_refresh_task = asyncio.get_event_loop().create_task(terminal._refresh_open_orders_async())
    except Exception as exc:
        terminal.logger.debug("Unable to schedule open-orders refresh: %s", exc)


def schedule_assets_refresh(terminal):
    task = getattr(terminal, "_assets_refresh_task", None)
    if task is not None and not task.done():
        return

    interval_seconds = _assets_refresh_interval_seconds(terminal)
    if interval_seconds > 0:
        last_refresh_at = float(getattr(terminal, "_last_assets_refresh_at", 0.0) or 0.0)
        if (time.monotonic() - last_refresh_at) < interval_seconds:
            return

    try:
        terminal._assets_refresh_task = asyncio.get_event_loop().create_task(terminal._refresh_assets_async())
    except Exception as exc:
        terminal.logger.debug("Unable to schedule assets refresh: %s", exc)


def schedule_order_history_refresh(terminal):
    task = getattr(terminal, "_order_history_refresh_task", None)
    if task is not None and not task.done():
        return

    interval_seconds = _history_refresh_interval_seconds(terminal)
    if interval_seconds > 0:
        last_refresh_at = float(getattr(terminal, "_last_order_history_refresh_at", 0.0) or 0.0)
        if (time.monotonic() - last_refresh_at) < interval_seconds:
            return

    try:
        terminal._order_history_refresh_task = asyncio.get_event_loop().create_task(terminal._refresh_order_history_async())
    except Exception as exc:
        terminal.logger.debug("Unable to schedule order-history refresh: %s", exc)


def schedule_trade_history_refresh(terminal):
    task = getattr(terminal, "_trade_history_refresh_task", None)
    if task is not None and not task.done():
        return

    interval_seconds = _history_refresh_interval_seconds(terminal)
    if interval_seconds > 0:
        last_refresh_at = float(getattr(terminal, "_last_trade_history_refresh_at", 0.0) or 0.0)
        if (time.monotonic() - last_refresh_at) < interval_seconds:
            return

    try:
        terminal._trade_history_refresh_task = asyncio.get_event_loop().create_task(terminal._refresh_trade_history_async())
    except Exception as exc:
        terminal.logger.debug("Unable to schedule trade-history refresh: %s", exc)


async def load_persisted_runtime_data(terminal):
    loader = getattr(terminal.controller, "_load_recent_trades", None)
    if loader is None:
        return

    try:
        trades = await loader(limit=min(int(terminal.MAX_LOG_ROWS or 200), 200))
    except Exception:
        terminal.logger.exception("Failed to load persisted trade history")
        return

    batch_size = max(1, int(getattr(terminal, "STARTUP_TRADE_REPLAY_BATCH_SIZE", 25) or 25))
    total = len(trades or [])

    for index, trade in enumerate(trades, start=1):
        if getattr(terminal, "_ui_shutting_down", False):
            break
        terminal._update_trade_log(trade)
        if index < total and (index % batch_size) == 0:
            await asyncio.sleep(0)


async def load_initial_terminal_data(terminal):
    def _set_loading(title, detail=None, *, visible=True):
        updater = getattr(terminal, "_set_workspace_loading_state", None)
        if callable(updater):
            updater(title, detail, visible=visible)

    async def _run_stage(title, detail, operation, *, continue_on_error=True):
        if getattr(terminal, "_ui_shutting_down", False):
            return None
        _set_loading(title, detail)
        await asyncio.sleep(0)
        try:
            return await operation()
        except Exception as exc:
            logger = getattr(terminal, "logger", None)
            if logger is not None:
                logger.debug("Initial runtime stage failed: %s", exc, exc_info=True)
            if continue_on_error:
                return None
            raise
        finally:
            await asyncio.sleep(0)

    account_sync_steps = []
    for attr_name in (
        "_refresh_assets_async",
        "_refresh_positions_async",
        "_refresh_open_orders_async",
        "_refresh_order_history_async",
        "_refresh_trade_history_async",
    ):
        operation = getattr(terminal, attr_name, None)
        if callable(operation):
            account_sync_steps.append(operation())

    try:
        _set_loading(
            "Loading trading workspace...",
            "Syncing balances, positions, open orders, and recent account activity.",
        )
        await asyncio.sleep(0)
        if account_sync_steps:
            results = await asyncio.gather(*account_sync_steps, return_exceptions=True)
            logger = getattr(terminal, "logger", None)
            if logger is not None:
                for result in results:
                    if isinstance(result, Exception):
                        logger.debug("Initial account sync stage failed: %s", result, exc_info=True)
        await asyncio.sleep(0)

        await _run_stage(
            "Restoring trade activity...",
            "Replaying recent executions into the terminal journal.",
            lambda: load_persisted_runtime_data(terminal),
        )

        chart_loader = getattr(terminal, "_load_active_chart_bootstrap_async", None)
        if callable(chart_loader):
            await _run_stage(
                "Loading market data...",
                "Fetching the active chart so the workspace opens with live context.",
                chart_loader,
            )

        refresher = getattr(terminal, "_refresh_terminal", None)
        if callable(refresher):
            refresher()
    finally:
        _set_loading(None, None, visible=False)
