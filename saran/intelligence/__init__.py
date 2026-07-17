"""Intelligence backends and a factory that picks one."""

from __future__ import annotations

import os

from ..core.config import Config
from .base import Intelligence
from .rule_based import RuleBasedIntelligence


def build_intelligence(config: Config) -> Intelligence:
    """Return the configured intelligence backend.

    "auto" (the default) uses Claude when credentials are present and the SDK is
    installed, otherwise the deterministic rule-based backend. "claude" and
    "rules" force a specific backend.
    """
    choice = config.intelligence.lower()

    if choice in ("claude", "auto"):
        have_creds = bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )
        if choice == "claude" or have_creds:
            try:
                from .claude import ClaudeIntelligence, IntelligenceUnavailable

                try:
                    return ClaudeIntelligence(model=config.model, effort=config.effort)
                except IntelligenceUnavailable:
                    if choice == "claude":
                        raise
            except ImportError:
                if choice == "claude":
                    raise

    return RuleBasedIntelligence()


__all__ = ["Intelligence", "RuleBasedIntelligence", "build_intelligence"]
