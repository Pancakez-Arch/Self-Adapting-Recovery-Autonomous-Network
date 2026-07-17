"""Core data structures shared across the SARAN pipeline.

Every stage of the self-healing loop speaks in these small, immutable-ish
dataclasses. Keeping them in one place makes the flow easy to trace:

    Finding  ->  Diagnosis  ->  RemediationPlan  ->  Patch  ->  HealingResult
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    """How urgent a finding is. Ordering matters for prioritisation."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self)


class Category(str, Enum):
    """What kind of issue a finding represents."""

    VULNERABILITY = "vulnerability"
    SECRET = "secret"
    DEPENDENCY = "dependency"
    QUALITY = "quality"
    UPGRADE = "upgrade"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Finding:
    """A single issue discovered by a scanner.

    A finding is an observation, not yet a fix. It carries enough location
    information for a later stage to propose and verify a remediation.
    """

    category: Category
    severity: Severity
    title: str
    detail: str
    file_path: str
    line: int = 0
    snippet: str = ""
    rule_id: str = ""
    suggestion: str = ""
    id: str = field(default_factory=lambda: _new_id("find"))
    discovered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Stable identity so the same issue isn't re-reported every cycle."""
        raw = f"{self.rule_id}:{self.file_path}:{self.line}:{self.title}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Diagnosis:
    """An interpretation of one or more findings.

    Produced by the intelligence layer. It explains root cause and states
    whether an automated fix is believed to be safe.
    """

    finding: Finding
    root_cause: str
    confidence: float  # 0.0 - 1.0
    auto_fixable: bool
    reasoning: str = ""
    id: str = field(default_factory=lambda: _new_id("diag"))


@dataclass
class Patch:
    """A concrete, reviewable change to a single file.

    Patches are full-file replacements rather than diffs so they can be
    applied and reverted without a patch engine. The original content is
    retained for rollback.
    """

    file_path: str
    original_content: str
    new_content: str
    description: str
    diagnosis_id: str = ""
    id: str = field(default_factory=lambda: _new_id("patch"))

    @property
    def is_noop(self) -> bool:
        return self.original_content == self.new_content


class Outcome(str, Enum):
    APPLIED = "applied"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class RemediationPlan:
    """An ordered set of patches addressing a diagnosis, plus how to check it."""

    diagnosis: Diagnosis
    patches: list[Patch] = field(default_factory=list)
    verify_command: Optional[str] = None
    id: str = field(default_factory=lambda: _new_id("plan"))


@dataclass
class HealingResult:
    """The record of what happened to one plan. This is what gets audited."""

    plan: RemediationPlan
    outcome: Outcome
    message: str = ""
    verification_passed: Optional[bool] = None
    duration_s: float = 0.0
    id: str = field(default_factory=lambda: _new_id("result"))
    finished_at: float = field(default_factory=time.time)
