"""Runtime self-monitoring.

The healing loop is reactive to static analysis; the monitor is the piece that
watches the running system and decides *when* a healing cycle is warranted.
Register lightweight health checks; `assess()` aggregates them into a single
status the orchestrator (or a scheduler) can act on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Health(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class Check:
    name: str
    fn: Callable[[], bool]
    critical: bool = False


@dataclass
class HealthReport:
    status: Health
    failed: list[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)

    @property
    def needs_healing(self) -> bool:
        return self.status is not Health.HEALTHY


class HealthMonitor:
    def __init__(self) -> None:
        self._checks: list[Check] = []

    def register(self, name: str, fn: Callable[[], bool], critical: bool = False) -> None:
        self._checks.append(Check(name, fn, critical))

    def assess(self) -> HealthReport:
        failed: list[str] = []
        critical_failed = False
        for check in self._checks:
            try:
                ok = bool(check.fn())
            except Exception:  # noqa: BLE001 - a broken probe counts as a failure
                ok = False
            if not ok:
                failed.append(check.name)
                critical_failed = critical_failed or check.critical
        if critical_failed:
            status = Health.UNHEALTHY
        elif failed:
            status = Health.DEGRADED
        else:
            status = Health.HEALTHY
        return HealthReport(status=status, failed=failed)
