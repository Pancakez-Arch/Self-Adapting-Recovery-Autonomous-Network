"""Event bus and append-only audit log.

Everything the framework does is emitted as an event. This is the memory of
a self-modifying system: without a durable record of what it changed and why,
autonomous edits are impossible to trust or reverse. The audit log is JSONL so
it survives restarts and is trivial to grep.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Callable


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return obj


class EventBus:
    """Fan-out for lifecycle events plus a persistent audit trail.

    Subscribers are simple callables ``(event_type, payload) -> None``. Failures
    in a subscriber are swallowed so one bad listener can't halt healing.
    """

    def __init__(self, audit_log_path: str | None = None) -> None:
        self.audit_log_path = audit_log_path
        self._subscribers: list[Callable[[str, dict], None]] = []
        if audit_log_path:
            os.makedirs(os.path.dirname(audit_log_path) or ".", exist_ok=True)

    def subscribe(self, callback: Callable[[str, dict], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, event_type: str, **payload: Any) -> None:
        record = {
            "ts": time.time(),
            "event": event_type,
            "payload": _jsonable(payload),
        }
        if self.audit_log_path:
            with open(self.audit_log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        for sub in self._subscribers:
            try:
                sub(event_type, record["payload"])
            except Exception:  # noqa: BLE001 - a listener must never break the loop
                pass


def console_logger(prefix: str = "SARAN") -> Callable[[str, dict], None]:
    """A ready-made subscriber that prints a readable one-liner per event."""

    def _log(event_type: str, payload: dict) -> None:
        summary = payload.get("summary") or payload.get("message") or ""
        print(f"[{prefix}] {event_type}: {summary}".rstrip(": "))

    return _log
