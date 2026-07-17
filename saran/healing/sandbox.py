"""Sandboxed patch application.

Patches are trialled against a throwaway copy of the target tree so a bad fix
can never leave the real code base in a broken state. Only after verification
passes in the sandbox does the orchestrator apply the same patch for real.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass

from ..core.config import Config
from ..core.models import Patch


@dataclass
class Sandbox:
    """A disposable mirror of the target directory."""

    root: str
    config: Config

    @classmethod
    def create(cls, config: Config) -> "Sandbox":
        tmp = tempfile.mkdtemp(prefix="saran_sandbox_")
        dest = os.path.join(tmp, "work")
        ignore = shutil.ignore_patterns(*config.exclude)
        shutil.copytree(config.target_dir, dest, ignore=ignore, symlinks=False)
        return cls(root=dest, config=config)

    def path_for(self, original_path: str) -> str:
        """Map a target-dir path onto the sandbox copy."""
        rel = os.path.relpath(original_path, self.config.target_dir)
        return os.path.join(self.root, rel)

    def apply(self, patch: Patch) -> str:
        """Write a patch's new content into the sandbox. Returns the sandbox path."""
        dest = self.path_for(patch.file_path)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(patch.new_content)
        return dest

    def cleanup(self) -> None:
        parent = os.path.dirname(self.root)
        shutil.rmtree(parent, ignore_errors=True)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()
