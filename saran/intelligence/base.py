"""The intelligence layer interface.

This is the pluggable "brain" of the framework. Given a finding and the source
around it, an intelligence backend does two things:

  1. diagnose()  -> is this real, what's the root cause, is it safe to auto-fix?
  2. propose_fix() -> the exact new file content that resolves it.

Two implementations ship:  ClaudeIntelligence (LLM-driven) and
RuleBasedIntelligence (deterministic, no API key needed). Both obey the same
contract so the orchestrator never cares which is in use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..core.models import Diagnosis, Finding, Patch


class Intelligence(ABC):
    name: str = "intelligence"

    @abstractmethod
    def diagnose(self, finding: Finding, source: str) -> Diagnosis:
        """Assess a finding against the full source of its file."""

    @abstractmethod
    def propose_fix(self, diagnosis: Diagnosis, source: str) -> Optional[Patch]:
        """Return a Patch that resolves the diagnosis, or None if it can't."""
