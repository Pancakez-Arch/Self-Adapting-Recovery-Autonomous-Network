"""Deterministic intelligence backend.

No API key, no network. It encodes a handful of mechanical fixes keyed on the
scanner rule ids. This keeps the whole self-healing loop runnable and testable
offline, and serves as a safe default when no LLM is configured.

Every transformation here is intentionally narrow and line-local so that the
result is easy to verify and unlikely to change unrelated behaviour.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from ..core.models import Diagnosis, Finding, Patch
from .base import Intelligence

# A fixer takes the full source and the finding, and returns new source or None.
Fixer = Callable[[str, Finding], Optional[str]]


def _replace_on_line(source: str, line: int, pattern: re.Pattern, repl: str) -> Optional[str]:
    lines = source.splitlines(keepends=True)
    if not (1 <= line <= len(lines)):
        return None
    original = lines[line - 1]
    new = pattern.sub(repl, original, count=1)
    if new == original:
        return None
    lines[line - 1] = new
    return "".join(lines)


def _fix_yaml_load(source: str, finding: Finding) -> Optional[str]:
    return _replace_on_line(source, finding.line, re.compile(r"yaml\.load\("), "yaml.safe_load(")


def _fix_md5(source: str, finding: Finding) -> Optional[str]:
    return _replace_on_line(source, finding.line, re.compile(r"hashlib\.md5\("), "hashlib.sha256(")


def _fix_verify_false(source: str, finding: Finding) -> Optional[str]:
    return _replace_on_line(
        source, finding.line, re.compile(r"verify\s*=\s*False"), "verify=True"
    )


def _fix_bare_except(source: str, finding: Finding) -> Optional[str]:
    return _replace_on_line(
        source, finding.line, re.compile(r"except\s*:"), "except Exception:"
    )


_FIXERS: dict[str, Fixer] = {
    "PY.YAML_LOAD": _fix_yaml_load,
    "PY.MD5": _fix_md5,
    "PY.VERIFY_FALSE": _fix_verify_false,
    "QA.BARE_EXCEPT": _fix_bare_except,
}


class RuleBasedIntelligence(Intelligence):
    name = "rule_based"

    def diagnose(self, finding: Finding, source: str) -> Diagnosis:
        fixable = finding.rule_id in _FIXERS
        return Diagnosis(
            finding=finding,
            root_cause=finding.detail,
            confidence=0.9 if fixable else 0.4,
            auto_fixable=fixable,
            reasoning=(
                "Deterministic rule fixer available."
                if fixable
                else "No deterministic fixer; needs human or LLM review."
            ),
        )

    def propose_fix(self, diagnosis: Diagnosis, source: str) -> Optional[Patch]:
        finding = diagnosis.finding
        fixer = _FIXERS.get(finding.rule_id)
        if not fixer:
            return None
        new_source = fixer(source, finding)
        if new_source is None or new_source == source:
            return None
        return Patch(
            file_path=finding.file_path,
            original_content=source,
            new_content=new_source,
            description=f"Auto-fix {finding.rule_id}: {finding.title}",
            diagnosis_id=diagnosis.id,
        )
