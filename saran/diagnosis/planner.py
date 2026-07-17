"""Turns a diagnosis + proposed patch into an executable remediation plan.

Thin by design: the intelligence layer does the hard thinking, the planner just
packages the result together with how it should be verified.
"""

from __future__ import annotations

from typing import Optional

from ..core.config import Config
from ..core.models import Diagnosis, Patch, RemediationPlan


class Planner:
    def __init__(self, config: Config) -> None:
        self.config = config

    def build(self, diagnosis: Diagnosis, patch: Optional[Patch]) -> Optional[RemediationPlan]:
        if patch is None or patch.is_noop:
            return None
        return RemediationPlan(
            diagnosis=diagnosis,
            patches=[patch],
            verify_command=self.config.verify_command,
        )
