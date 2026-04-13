from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sopotek.core.event_bus import AsyncEventBus
from sopotek.core.event_types import EventType
from sopotek.core.models import Signal, SignalStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return _utc_now()


def _timeframe_to_seconds(value: Any, default: int = 0) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return int(default)
    try:
        amount = int(text[:-1] or 1)
    except Exception:
        return int(default)
    suffix = text[-1]
    if suffix == "s":
        return amount
    if suffix == "m":
        return amount * 60
    if suffix == "h":
        return amount * 3600
    if suffix == "d":
        return amount * 86400
    return int(default)


@dataclass(slots=True)
class SignalCollection:
    symbol: str
    signals: list[Signal]
    stale_strategies: list[str]


class SignalEngine:
    """Normalizes strategy output into tracked signals with lifecycle metadata."""

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus | None = None,
        signal_ttl_seconds: float = 900.0,
    ) -> None:
        self.bus = event_bus
        self.signal_ttl_seconds = max(30.0, float(signal_ttl_seconds))

    def attach(self, event_bus: AsyncEventBus) -> None:
        self.bus = event_bus

    async def ingest(self, signal: Signal | Mapping[str, Any], *, source: str = "signal_engine") -> Signal:
        normalized = self.normalize(signal)
        if self.bus is not None:
            await self.bus.publish(EventType.SIGNAL_CREATED, normalized, priority=58, source=source)
        return normalized

    def normalize(self, signal: Signal | Mapping[str, Any]) -> Signal:
        if not isinstance(signal, Signal):
            signal = Signal(**dict(signal or {}))
        metadata = dict(signal.metadata or {})
        metadata.setdefault("source_strategy", signal.source_strategy or signal.strategy_name)
        metadata.setdefault("signal_id", signal.id)
        return signal.transition(
            stage="normalized",
            status=SignalStatus.CREATED,
            metadata=metadata,
            note=f"Normalized signal from {signal.source_strategy or signal.strategy_name}",
            timestamp=signal.timestamp,
        )

    def collect(
        self,
        symbol: str,
        strategy_signals: Mapping[str, Mapping[str, Signal] | dict[str, Signal]],
        *,
        now: datetime | None = None,
    ) -> SignalCollection:
        reference_time = now or _utc_now()
        bucket = strategy_signals.get(symbol, {})
        fresh: list[Signal] = []
        stale_strategies: list[str] = []
        for strategy_name, signal in dict(bucket or {}).items():
            normalized = self.normalize(signal)
            timestamp = _coerce_datetime(getattr(normalized, "timestamp", None))
            freshness_window = timedelta(seconds=self.signal_ttl(normalized))
            if reference_time - timestamp > freshness_window:
                stale_strategies.append(str(strategy_name))
                continue
            fresh.append(normalized)
        return SignalCollection(symbol=str(symbol or "").strip(), signals=fresh, stale_strategies=stale_strategies)

    def signal_ttl(self, signal: Signal) -> float:
        metadata = dict(getattr(signal, "metadata", {}) or {})
        timeframe_seconds = _timeframe_to_seconds(metadata.get("timeframe"), default=0)
        if timeframe_seconds > 0:
            return max(self.signal_ttl_seconds, float(timeframe_seconds) * 1.5)
        return self.signal_ttl_seconds
