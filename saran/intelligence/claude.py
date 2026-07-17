"""Claude-backed intelligence.

Uses the official Anthropic SDK. Diagnosis is returned as validated JSON via
structured outputs; fixes are streamed (full-file rewrites can be large, and
streaming avoids HTTP timeouts).

The adapter degrades gracefully: if the SDK isn't installed or no credentials
are available, construction raises `IntelligenceUnavailable`, and the factory
falls back to the deterministic backend rather than crashing the loop.
"""

from __future__ import annotations

import json
from typing import Optional

from ..core.models import Diagnosis, Finding, Patch
from .base import Intelligence


class IntelligenceUnavailable(RuntimeError):
    """Raised when the Claude backend cannot be constructed."""


_DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "is_real": {"type": "boolean"},
        "root_cause": {"type": "string"},
        "confidence": {"type": "number"},
        "auto_fixable": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["is_real", "root_cause", "confidence", "auto_fixable", "reasoning"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are the analysis core of a self-healing software framework. You examine "
    "one static-analysis finding at a time and decide whether it is a genuine issue, "
    "what the root cause is, and whether it can be fixed automatically with high "
    "confidence and no behavioural change. Be conservative: only mark auto_fixable "
    "true when a minimal, local edit clearly resolves the issue without side effects."
)


class ClaudeIntelligence(Intelligence):
    name = "claude"

    def __init__(self, model: str = "claude-opus-4-8", effort: str = "high") -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env dependent
            raise IntelligenceUnavailable(
                "anthropic SDK not installed (pip install anthropic)"
            ) from exc
        try:
            # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant` profile.
            self._client = anthropic.Anthropic()
        except Exception as exc:  # noqa: BLE001 - surface as our own error type
            raise IntelligenceUnavailable(f"could not init Anthropic client: {exc}") from exc
        self._model = model
        self._effort = effort

    # -- diagnosis ----------------------------------------------------------

    def diagnose(self, finding: Finding, source: str) -> Diagnosis:
        context = _windowed_source(source, finding.line)
        prompt = (
            f"Finding: {finding.title}\n"
            f"Rule: {finding.rule_id}\n"
            f"Severity: {finding.severity.value}\n"
            f"File: {finding.file_path}:{finding.line}\n"
            f"Detail: {finding.detail}\n\n"
            f"Relevant source (line {finding.line} marked):\n{context}"
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=_SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": _DIAGNOSIS_SCHEMA},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
        return Diagnosis(
            finding=finding,
            root_cause=data["root_cause"],
            confidence=float(data["confidence"]) if data["is_real"] else 0.0,
            auto_fixable=bool(data["auto_fixable"]) and bool(data["is_real"]),
            reasoning=data["reasoning"],
        )

    # -- fix generation -----------------------------------------------------

    def propose_fix(self, diagnosis: Diagnosis, source: str) -> Optional[Patch]:
        finding = diagnosis.finding
        prompt = (
            "Rewrite the file below to resolve this issue, changing as little as "
            "possible and preserving all unrelated behaviour.\n\n"
            f"Issue: {finding.title} ({finding.rule_id}) at line {finding.line}\n"
            f"Root cause: {diagnosis.root_cause}\n"
            f"Suggested direction: {finding.suggestion}\n\n"
            "Return ONLY the complete corrected file contents, no markdown fences, "
            "no commentary.\n\n"
            f"=== FILE: {finding.file_path} ===\n{source}"
        )
        with self._client.messages.stream(
            model=self._model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={"effort": self._effort},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
        new_source = "".join(b.text for b in message.content if b.type == "text")
        new_source = _strip_fences(new_source)
        if not new_source.strip() or new_source == source:
            return None
        return Patch(
            file_path=finding.file_path,
            original_content=source,
            new_content=new_source,
            description=f"Claude fix for {finding.rule_id}: {finding.title}",
            diagnosis_id=diagnosis.id,
        )


def _windowed_source(source: str, line: int, radius: int = 25) -> str:
    lines = source.splitlines()
    start = max(0, line - radius)
    end = min(len(lines), line + radius)
    out = []
    for i in range(start, end):
        marker = ">>" if (i + 1) == line else "  "
        out.append(f"{marker}{i + 1:5d}| {lines[i]}")
    return "\n".join(out)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text
