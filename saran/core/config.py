"""Runtime configuration for a SARAN instance.

Defaults are deliberately conservative: the framework observes and proposes,
but does not modify code on disk or commit anything unless explicitly told to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # The directory SARAN inspects and heals. Defaults to the current repo.
    target_dir: str = "."

    # Files/dirs never touched, even for scanning.
    exclude: tuple[str, ...] = (
        ".git", ".venv", "venv", "node_modules", "__pycache__",
        ".mypy_cache", ".pytest_cache", "build", "dist",
    )

    # --- Safety gates (all default to the safe choice) ---------------------
    # dry_run: propose only, never write patches to disk.
    dry_run: bool = True
    # require_approval: even outside dry_run, wait for a human/callback yes.
    require_approval: bool = True
    # auto_commit: create a git commit after a verified heal.
    auto_commit: bool = False
    # max_patches_per_cycle: blast-radius cap for a single run.
    max_patches_per_cycle: int = 5
    # min_confidence: diagnoses below this are never auto-applied.
    min_confidence: float = 0.7
    # allowed_categories: only heal these kinds of findings automatically.
    allowed_categories: tuple[str, ...] = ("vulnerability", "secret", "quality")

    # --- Verification ------------------------------------------------------
    # Command run to prove a patch didn't break anything. If None, SARAN
    # falls back to a Python syntax/compile check on changed files.
    verify_command: Optional[str] = None
    verify_timeout_s: int = 300

    # --- Intelligence layer ------------------------------------------------
    # "auto" picks Claude when ANTHROPIC_API_KEY is available, else rules.
    intelligence: str = "auto"
    model: str = "claude-opus-4-8"
    effort: str = "high"

    # Where the audit trail is written.
    audit_log_path: str = ".saran/audit.jsonl"

    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Build a config, letting SARAN_* environment variables override."""

        def _bool(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            if raw is None:
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        cfg = cls(
            target_dir=os.environ.get("SARAN_TARGET_DIR", cls.target_dir),
            dry_run=_bool("SARAN_DRY_RUN", cls.dry_run),
            require_approval=_bool("SARAN_REQUIRE_APPROVAL", cls.require_approval),
            auto_commit=_bool("SARAN_AUTO_COMMIT", cls.auto_commit),
            intelligence=os.environ.get("SARAN_INTELLIGENCE", cls.intelligence),
            model=os.environ.get("SARAN_MODEL", cls.model),
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg
