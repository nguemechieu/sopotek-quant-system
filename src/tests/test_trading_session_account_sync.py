import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sessions.trading_session import TradingSession


class _FakeTradingRuntime:
    def __init__(self, controller):
        self.controller = controller
        self.event_bus = None
        self.portfolio = None

    async def start(self):
        return None

    async def stop(self, wait_for_background_workers=False):
        _ = wait_for_background_workers
        return None


class _FakeBroker:
    def __init__(self):
        self.account_id = None
        self.account_hash = None
        self.options = {}
        self.params = {}
        self.connect_calls = 0
        self.account_requests = 0

    async def connect(self):
        self.connect_calls += 1
        return True

    async def close(self):
        return True

    async def get_accounts(self):
        self.account_requests += 1
        return [{"account_id": "DU123456", "account_hash": "hash-abc"}]

    async def fetch_balance(self):
        return {"equity": 1000.0}

    async def fetch_positions(self):
        return []

    async def fetch_open_orders(self, limit=100):
        _ = limit
        return []


def test_initialize_syncs_discovered_account_to_session_and_config(monkeypatch):
    monkeypatch.setattr("sessions.trading_session.SopotekTrading", _FakeTradingRuntime)

    broker = _FakeBroker()
    broker_config = SimpleNamespace(
        exchange="schwab",
        mode="live",
        type="stocks",
        account_id=None,
        options={},
        params={},
    )
    config = SimpleNamespace(
        broker=broker_config,
        risk=None,
        strategy="Trend Following",
    )
    parent_controller = SimpleNamespace(
        _build_broker_for_login=lambda _config: broker,
        symbols=["AAPL"],
    )

    async def _exercise():
        session = TradingSession(
            session_id="schwab-live-001",
            config=config,
            parent_controller=parent_controller,
            logger=logging.getLogger("test.trading_session.account_sync"),
        )
        await session.initialize()

        assert broker.connect_calls == 1
        assert broker.account_requests >= 1
        assert broker.account_id == "DU123456"
        assert broker.account_hash == "hash-abc"
        assert config.broker.account_id == "DU123456"
        assert config.broker.options["account_id"] == "DU123456"
        assert config.broker.options["account_hash"] == "hash-abc"
        assert config.broker.params["account_id"] == "DU123456"
        assert config.broker.params["account_hash"] == "hash-abc"
        assert session.session_controller.current_account_label() == "DU123456"
        assert session.snapshot().account_label == "DU123456"

        await session.close()

    asyncio.run(_exercise())
