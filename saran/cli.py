"""Command-line interface for SARAN.

    saran scan               # report findings only
    saran heal               # dry-run heal cycle (default: safe, no writes)
    saran heal --apply       # actually write verified fixes
    saran heal --apply --yes # skip interactive approval prompt

Run ``python -m saran.cli --help`` for the full option list.
"""

from __future__ import annotations

import argparse
import sys

from .core.config import Config
from .core.events import console_logger
from .core.models import Diagnosis, Patch
from .core.orchestrator import Orchestrator


def _interactive_approval(patch: Patch, diagnosis: Diagnosis) -> bool:
    print("\n--- Proposed fix ---------------------------------------------")
    print(f"file : {patch.file_path}")
    print(f"why  : {patch.description}")
    print(f"conf : {diagnosis.confidence:.2f}  reason: {diagnosis.reasoning[:200]}")
    print("--------------------------------------------------------------")
    try:
        answer = input("Apply this fix? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _build_config(args: argparse.Namespace) -> Config:
    cfg = Config.from_env(target_dir=args.path)
    if args.command == "heal":
        cfg.dry_run = not args.apply
        cfg.require_approval = args.apply and not args.yes
        cfg.auto_commit = args.commit
    if args.intelligence:
        cfg.intelligence = args.intelligence
    if args.verify:
        cfg.verify_command = args.verify
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saran", description=__doc__)
    parser.add_argument("--path", default=".", help="target directory (default: .)")
    parser.add_argument("--intelligence", choices=["auto", "claude", "rules"], default=None)
    parser.add_argument("--verify", default=None, help="verification command, e.g. 'pytest -q'")
    parser.add_argument("--quiet", action="store_true", help="suppress event log")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="report findings without changing anything")

    heal = sub.add_parser("heal", help="run a scan-and-heal cycle")
    heal.add_argument("--apply", action="store_true", help="write fixes (default: dry-run)")
    heal.add_argument("--yes", action="store_true", help="skip approval prompt")
    heal.add_argument("--commit", action="store_true", help="git commit each verified fix")
    heal.add_argument("--cycles", type=int, default=1, help="max heal cycles")
    heal.add_argument("--until-clean", action="store_true", help="loop until nothing heals")

    args = parser.parse_args(argv)
    cfg = _build_config(args)
    orch = Orchestrator(cfg, approval=_interactive_approval)
    if not args.quiet:
        orch.events.subscribe(console_logger())

    if args.command == "scan":
        findings = orch.scan()
        for f in findings:
            print(f"[{f.severity.value.upper():8}] {f.file_path}:{f.line} {f.title} ({f.rule_id})")
        print(f"\n{len(findings)} finding(s).")
        return 1 if findings else 0

    if args.command == "heal":
        reports = orch.run(max_cycles=args.cycles, until_clean=args.until_clean)
        total_healed = sum(r.healed for r in reports)
        total_found = sum(len(r.findings) for r in reports[:1])
        mode = "dry-run" if cfg.dry_run else "applied"
        print(f"\n{mode}: {total_healed} healed / {total_found} found in first cycle.")
        for r in reports:
            for res in r.results:
                print(f"  - {res.outcome.value:12} {res.plan.diagnosis.finding.title}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
