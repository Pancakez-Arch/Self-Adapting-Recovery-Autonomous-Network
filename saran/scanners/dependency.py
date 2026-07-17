"""Dependency hygiene scanner.

Flags unpinned requirements (an "upgrade/fix it can improve by itself" case)
and dependencies matching a small local advisory list. Real deployments should
point `advisory_source` at an up-to-date feed (OSV, GitHub Advisory, pip-audit).
"""

from __future__ import annotations

import os
import re

from ..core.models import Category, Finding, Severity
from .base import Scanner

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)?\s*([0-9][\w.\-]*)?")

# Minimal illustrative advisory table: {package: (max_bad_version, note)}.
# Anything at or below the version is flagged. Swap for a live feed in prod.
_LOCAL_ADVISORIES: dict[str, tuple[str, str]] = {
    "pyyaml": ("5.3", "CVE-2020-1747: unsafe full_load default; upgrade to >=5.4."),
    "requests": ("2.19.1", "CVE-2018-18074: credential leak on redirect; upgrade >=2.20."),
    "jinja2": ("2.10", "CVE-2019-10906: sandbox escape; upgrade to >=2.10.1."),
}


def _version_le(a: str, b: str) -> bool:
    """Return True if version a <= version b using tuple comparison."""

    def parts(v: str) -> tuple[int, ...]:
        out = []
        for chunk in v.split("."):
            m = re.match(r"\d+", chunk)
            out.append(int(m.group()) if m else 0)
        return tuple(out)

    return parts(a) <= parts(b)


class DependencyScanner(Scanner):
    name = "dependency"

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for path in self._requirement_files():
            findings.extend(self._scan_requirements(path))
        return findings

    def _requirement_files(self) -> list[str]:
        out = []
        for root, dirs, files in os.walk(self.config.target_dir):
            dirs[:] = [d for d in dirs if d not in set(self.config.exclude)]
            for fname in files:
                if fname == "requirements.txt" or fname.endswith(".requirements.txt"):
                    out.append(os.path.join(root, fname))
        return out

    def _scan_requirements(self, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for lineno, raw in enumerate(self.read(path).splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = _REQ_LINE.match(line)
            if not m:
                continue
            name, op, version = m.group(1).lower(), m.group(2), m.group(3)

            if not op or not version:
                findings.append(
                    Finding(
                        category=Category.DEPENDENCY,
                        severity=Severity.LOW,
                        title=f"Unpinned dependency '{name}'",
                        detail="Unpinned dependencies make builds non-reproducible.",
                        file_path=path,
                        line=lineno,
                        snippet=line,
                        rule_id="DEP.UNPINNED",
                        suggestion=f"Pin an explicit version, e.g. {name}==<version>.",
                    )
                )
                continue

            advisory = _LOCAL_ADVISORIES.get(name)
            if advisory and version and _version_le(version, advisory[0]):
                findings.append(
                    Finding(
                        category=Category.DEPENDENCY,
                        severity=Severity.HIGH,
                        title=f"Vulnerable dependency '{name}=={version}'",
                        detail=advisory[1],
                        file_path=path,
                        line=lineno,
                        snippet=line,
                        rule_id="DEP.VULNERABLE",
                        suggestion=advisory[1],
                        metadata={"package": name, "version": version},
                    )
                )
        return findings
