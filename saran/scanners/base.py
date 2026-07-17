"""Scanner interface and a shared file-walking helper.

A scanner's only job is to turn source files into `Finding` objects. Scanners
must be side-effect free — they read, they never write.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Iterable, Iterator

from ..core.config import Config
from ..core.models import Finding


class Scanner(ABC):
    """Base class for all scanners."""

    name: str = "scanner"

    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    def scan(self) -> list[Finding]:
        """Return every finding this scanner can detect in the target dir."""

    # -- helpers shared by concrete scanners --------------------------------

    def iter_files(self, suffixes: Iterable[str] = (".py",)) -> Iterator[str]:
        suffixes = tuple(suffixes)
        exclude = set(self.config.exclude)
        for root, dirs, files in os.walk(self.config.target_dir):
            dirs[:] = [d for d in dirs if d not in exclude]
            for fname in files:
                if fname.endswith(suffixes):
                    yield os.path.join(root, fname)

    @staticmethod
    def read(path: str) -> str:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""
