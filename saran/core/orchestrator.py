"""The self-healing orchestrator.

This is the loop that makes the framework "self-adapting": it scans its own
code, diagnoses issues with the intelligence layer, and — behind the safety
gates — repairs them, verifying each change in a sandbox and rolling back
anything that fails.

    scan -> diagnose -> plan -> gate -> sandbox-apply -> verify
                                              |               |
                                          pass                fail
                                              v               v
                                     apply for real       discard
                                              |
                                        verify again
                                          |      |
                                       pass    fail -> rollback
                                          |
                                    commit (optional)

Nothing is written to the real tree in dry-run mode; nothing at all is written
without passing every guardrail.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from ..diagnosis.planner import Planner
from ..healing.patcher import Patcher
from ..healing.sandbox import Sandbox
from ..intelligence import Intelligence, build_intelligence
from ..monitor.health import HealthMonitor, HealthReport
from ..safety.guardrails import ApprovalCallback, Guardrails
from ..scanners.base import Scanner
from ..scanners.dependency import DependencyScanner
from ..scanners.quality import QualityScanner
from ..scanners.vulnerability import VulnerabilityScanner
from ..verification.verifier import Verifier
from .config import Config
from .events import EventBus
from .models import Finding, HealingResult, Outcome, RemediationPlan, Severity


@dataclass
class CycleReport:
    """Summary of a single scan-and-heal pass."""

    findings: list[Finding] = field(default_factory=list)
    results: list[HealingResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    duration_s: float = 0.0

    @property
    def healed(self) -> int:
        return sum(1 for r in self.results if r.outcome is Outcome.VERIFIED)

    @property
    def rolled_back(self) -> int:
        return sum(1 for r in self.results if r.outcome is Outcome.ROLLED_BACK)


class Orchestrator:
    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        intelligence: Optional[Intelligence] = None,
        approval: Optional[ApprovalCallback] = None,
        scanners: Optional[list[Scanner]] = None,
        monitor: Optional[HealthMonitor] = None,
    ) -> None:
        self.config = config or Config()
        self.events = EventBus(self.config.audit_log_path)
        self.intelligence = intelligence or build_intelligence(self.config)
        self.guardrails = Guardrails(self.config, approval=approval)
        self.planner = Planner(self.config)
        self.verifier = Verifier(self.config)
        self.monitor = monitor or HealthMonitor()
        self.scanners = scanners or [
            VulnerabilityScanner(self.config),
            DependencyScanner(self.config),
            QualityScanner(self.config),
        ]
        self._known_fingerprints: set[str] = set()

    # -- public API ---------------------------------------------------------

    def scan(self) -> list[Finding]:
        """Run all scanners and return findings, most severe first."""
        findings: list[Finding] = []
        for scanner in self.scanners:
            try:
                found = scanner.scan()
            except Exception as exc:  # noqa: BLE001 - a broken scanner shouldn't halt others
                self.events.emit("scanner.error", scanner=scanner.name, message=str(exc))
                continue
            findings.extend(found)
            self.events.emit("scanner.done", scanner=scanner.name, summary=f"{len(found)} findings")
        findings.sort(key=lambda f: f.severity.rank, reverse=True)
        self.events.emit("scan.complete", summary=f"{len(findings)} findings total")
        return findings

    def heal_once(self) -> CycleReport:
        """One full scan-and-heal cycle."""
        report = CycleReport()
        self.guardrails.reset_cycle()
        self.events.emit("cycle.start", summary=self._mode_summary())

        findings = self.scan()
        report.findings = findings

        for finding in findings:
            if finding.fingerprint in self._known_fingerprints:
                continue
            result = self._handle_finding(finding)
            if result is not None:
                report.results.append(result)
                if result.outcome in (Outcome.VERIFIED, Outcome.REJECTED, Outcome.SKIPPED):
                    self._known_fingerprints.add(finding.fingerprint)

        report.duration_s = time.time() - report.started_at
        self.events.emit(
            "cycle.complete",
            summary=f"healed={report.healed} rolled_back={report.rolled_back}",
        )
        return report

    def run(self, max_cycles: int = 1, until_clean: bool = False) -> list[CycleReport]:
        """Run one or more cycles. Stops early if a cycle heals nothing."""
        reports: list[CycleReport] = []
        for _ in range(max_cycles):
            report = self.heal_once()
            reports.append(report)
            if until_clean and report.healed == 0:
                break
        return reports

    def watch(self) -> Optional[HealthReport]:
        """Assess health; heal if degraded. Returns the health report."""
        health = self.monitor.assess()
        self.events.emit("health.assess", summary=health.status.value, failed=health.failed)
        if health.needs_healing:
            self.heal_once()
        return health

    # -- internals ----------------------------------------------------------

    def _handle_finding(self, finding: Finding) -> Optional[HealingResult]:
        source = _read(finding.file_path)
        if not source and finding.category.value != "dependency":
            return None

        diagnosis = self.intelligence.diagnose(finding, source)
        self.events.emit(
            "diagnose",
            finding=finding.title,
            summary=f"auto_fixable={diagnosis.auto_fixable} conf={diagnosis.confidence:.2f}",
        )

        gate = self.guardrails.check_diagnosis(diagnosis)
        if not gate.allowed:
            self.events.emit("gate.diagnosis.blocked", summary=gate.reason, finding=finding.title)
            return HealingResult(
                plan=RemediationPlan(diagnosis=diagnosis),
                outcome=Outcome.SKIPPED,
                message=gate.reason,
            )

        patch = self.intelligence.propose_fix(diagnosis, source)
        plan = self.planner.build(diagnosis, patch)
        if plan is None or patch is None:
            self.events.emit("plan.empty", finding=finding.title)
            return HealingResult(
                plan=RemediationPlan(diagnosis=diagnosis),
                outcome=Outcome.SKIPPED,
                message="no actionable patch produced",
            )

        patch_gate = self.guardrails.check_patch(patch, diagnosis)
        if not patch_gate.allowed:
            self.events.emit("gate.patch.blocked", summary=patch_gate.reason, finding=finding.title)
            return HealingResult(plan=plan, outcome=Outcome.REJECTED, message=patch_gate.reason)

        return self._execute(plan)

    def _execute(self, plan: RemediationPlan) -> HealingResult:
        started = time.time()

        # 1) Prove the fix in a sandbox first.
        with Sandbox.create(self.config) as sandbox:
            for patch in plan.patches:
                sandbox.apply(patch)
            report = self.verifier.verify(sandbox.root, plan.patches)

        if not report.passed:
            self.events.emit("verify.sandbox.failed", summary=report.detail[:200])
            return HealingResult(
                plan=plan,
                outcome=Outcome.FAILED,
                verification_passed=False,
                message=f"sandbox verification failed: {report.detail}",
                duration_s=time.time() - started,
            )

        # 2) Dry-run stops here: sandbox verified, nothing written to real tree.
        if self.config.dry_run:
            self.events.emit("dry_run.verified", summary=plan.diagnosis.finding.title)
            return HealingResult(
                plan=plan,
                outcome=Outcome.VERIFIED,
                verification_passed=True,
                message="dry-run: verified in sandbox, not applied to disk",
                duration_s=time.time() - started,
            )

        # 3) Apply for real, then verify again against the live tree.
        patcher = Patcher()
        for patch in plan.patches:
            patcher.apply(patch)
        self.guardrails.record_applied()

        with Sandbox.create(self.config) as live_check:
            live_report = self.verifier.verify(live_check.root, plan.patches)

        if not live_report.passed:
            patcher.rollback_all()
            self.events.emit("rollback", summary=live_report.detail[:200])
            return HealingResult(
                plan=plan,
                outcome=Outcome.ROLLED_BACK,
                verification_passed=False,
                message=f"rolled back after post-apply failure: {live_report.detail}",
                duration_s=time.time() - started,
            )

        patcher.commit()
        if self.config.auto_commit:
            self._git_commit(plan)

        self.events.emit("heal.success", summary=plan.diagnosis.finding.title)
        return HealingResult(
            plan=plan,
            outcome=Outcome.VERIFIED,
            verification_passed=True,
            message="applied and verified",
            duration_s=time.time() - started,
        )

    def _git_commit(self, plan: RemediationPlan) -> None:
        title = plan.diagnosis.finding.title
        message = f"SARAN self-heal: {title}\n\n{plan.diagnosis.reasoning}".strip()
        files = [p.file_path for p in plan.patches]
        try:
            subprocess.run(["git", "add", *files], cwd=self.config.target_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", message], cwd=self.config.target_dir, check=True
            )
            self.events.emit("git.commit", summary=title)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.events.emit("git.commit.failed", summary=str(exc))

    def _mode_summary(self) -> str:
        mode = "dry-run" if self.config.dry_run else "live"
        approval = "approval-required" if self.config.require_approval else "auto-approve"
        return f"{mode}/{approval}/intel={self.intelligence.name}"


def _read(path: str) -> str:
    import os

    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()
