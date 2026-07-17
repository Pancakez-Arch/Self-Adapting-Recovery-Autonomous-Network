"""SARAN — Self-Adapting Recovery Autonomous Network.

A framework for software that inspects its own code for vulnerabilities and
improvement opportunities, then repairs them autonomously behind hard safety
gates: sandboxed trials, verification, rollback, and an auditable trail.

Quick start::

    from saran import Orchestrator, Config

    cfg = Config(target_dir="my_project", dry_run=True)
    orch = Orchestrator(cfg)
    report = orch.heal_once()
    print(f"{report.healed} issues healed, {len(report.findings)} found")
"""

from __future__ import annotations

from .core.config import Config
from .core.models import (
    Category,
    Diagnosis,
    Finding,
    HealingResult,
    Outcome,
    Patch,
    RemediationPlan,
    Severity,
)
from .core.orchestrator import CycleReport, Orchestrator

__version__ = "0.1.0"

__all__ = [
    "Config",
    "Orchestrator",
    "CycleReport",
    "Finding",
    "Diagnosis",
    "Patch",
    "RemediationPlan",
    "HealingResult",
    "Outcome",
    "Severity",
    "Category",
    "__version__",
]
