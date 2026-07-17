"""Verification: prove a patch is safe before it is accepted.

Two levels, tried in order of what's configured:

  1. A project-supplied command (e.g. ``pytest -q``) run inside the sandbox.
     This is the real safety net — behavioural tests catch behavioural breaks.
  2. If no command is given, every changed Python file is byte-compiled so that
     at minimum the patch is syntactically valid and importable.

A patch that fails verification is never applied to the real tree.
"""

from __future__ import annotations

import os
import py_compile
import subprocess
import tempfile
from dataclasses import dataclass

from ..core.config import Config
from ..core.models import Patch


@dataclass
class VerificationReport:
    passed: bool
    detail: str


class Verifier:
    def __init__(self, config: Config) -> None:
        self.config = config

    def verify(self, sandbox_root: str, patches: list[Patch]) -> VerificationReport:
        if self.config.verify_command:
            return self._run_command(sandbox_root)
        return self._compile_check(sandbox_root, patches)

    def _run_command(self, sandbox_root: str) -> VerificationReport:
        try:
            proc = subprocess.run(
                self.config.verify_command,
                shell=True,  # command comes from trusted local config, not model output
                cwd=sandbox_root,
                capture_output=True,
                text=True,
                timeout=self.config.verify_timeout_s,
            )
        except subprocess.TimeoutExpired:
            return VerificationReport(False, "verification command timed out")
        tail = (proc.stdout + proc.stderr)[-2000:]
        if proc.returncode == 0:
            return VerificationReport(True, "verification command passed")
        return VerificationReport(False, f"exit {proc.returncode}:\n{tail}")

    def _compile_check(self, sandbox_root: str, patches: list[Patch]) -> VerificationReport:
        errors: list[str] = []
        for patch in patches:
            if not patch.file_path.endswith(".py"):
                continue
            rel = os.path.relpath(patch.file_path, self.config.target_dir)
            candidate = os.path.join(sandbox_root, rel)
            if not os.path.exists(candidate):
                continue
            try:
                with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                    py_compile.compile(candidate, cfile=tmp.name, doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"{rel}: {exc.msg}")
        if errors:
            return VerificationReport(False, "compile errors:\n" + "\n".join(errors))
        return VerificationReport(True, "all changed files compile cleanly")
