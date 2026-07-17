"""Guardrails: the gate every proposed change must pass before it touches disk.

A self-modifying system is only as safe as the constraints around it. These
checks are intentionally boring and explicit — they are the difference between
"assistant that suggests fixes" and "process that edits its own code unattended".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from ..core.config import Config
from ..core.models import Diagnosis, Patch

# An approval callback is asked to confirm a patch. Return True to allow.
ApprovalCallback = Callable[[Patch, Diagnosis], bool]


@dataclass
class GateResult:
    allowed: bool
    reason: str


class Guardrails:
    def __init__(self, config: Config, approval: Optional[ApprovalCallback] = None) -> None:
        self.config = config
        self.approval = approval
        self._applied_this_cycle = 0

    def reset_cycle(self) -> None:
        self._applied_this_cycle = 0

    def check_diagnosis(self, diagnosis: Diagnosis) -> GateResult:
        if not diagnosis.auto_fixable:
            return GateResult(False, "diagnosis is not marked auto-fixable")
        if diagnosis.confidence < self.config.min_confidence:
            return GateResult(
                False,
                f"confidence {diagnosis.confidence:.2f} below threshold "
                f"{self.config.min_confidence:.2f}",
            )
        cat = diagnosis.finding.category.value
        if cat not in self.config.allowed_categories:
            return GateResult(False, f"category '{cat}' not in allowed_categories")
        return GateResult(True, "diagnosis cleared")

    def check_patch(self, patch: Patch, diagnosis: Diagnosis) -> GateResult:
        if patch.is_noop:
            return GateResult(False, "patch is a no-op")
        if self._applied_this_cycle >= self.config.max_patches_per_cycle:
            return GateResult(False, "max_patches_per_cycle reached")

        # Never allow edits to escape the target directory.
        target = os.path.realpath(self.config.target_dir)
        resolved = os.path.realpath(patch.file_path)
        if not (resolved == target or resolved.startswith(target + os.sep)):
            return GateResult(False, "patch targets a path outside target_dir")

        # A fix must not delete the file wholesale or truncate it drastically.
        if len(patch.new_content.strip()) < max(1, len(patch.original_content) // 5):
            return GateResult(False, "patch removes most of the file; refusing")

        # Approval gates writes to disk. In dry-run nothing is written, so a
        # dry-run always proceeds to sandbox verification without prompting.
        if self.config.require_approval and not self.config.dry_run:
            if self.approval is None:
                return GateResult(False, "approval required but no approver configured")
            if not self.approval(patch, diagnosis):
                return GateResult(False, "human approver rejected the patch")

        return GateResult(True, "patch cleared")

    def record_applied(self) -> None:
        self._applied_this_cycle += 1
