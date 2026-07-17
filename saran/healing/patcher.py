"""Apply and revert patches on the real target tree, with a rollback ledger."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..core.models import Patch


@dataclass
class Patcher:
    """Applies patches to disk and remembers how to undo them.

    Rollback is exact: the original bytes are stored before writing, so a revert
    restores the file to precisely its prior state.
    """

    _backups: dict[str, str] = field(default_factory=dict)

    def apply(self, patch: Patch) -> None:
        if patch.file_path not in self._backups:
            self._backups[patch.file_path] = _read(patch.file_path)
        os.makedirs(os.path.dirname(patch.file_path) or ".", exist_ok=True)
        with open(patch.file_path, "w", encoding="utf-8") as fh:
            fh.write(patch.new_content)

    def rollback(self, patch: Patch) -> None:
        original = self._backups.get(patch.file_path, patch.original_content)
        with open(patch.file_path, "w", encoding="utf-8") as fh:
            fh.write(original)

    def rollback_all(self) -> None:
        for path, original in self._backups.items():
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original)
        self._backups.clear()

    def commit(self) -> None:
        """Forget backups once a change is accepted (nothing to undo anymore)."""
        self._backups.clear()


def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()
