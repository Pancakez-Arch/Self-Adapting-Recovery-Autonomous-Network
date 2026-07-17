"""End-to-end demo of the self-healing loop.

Copies the flawed sample into a scratch directory, runs a dry-run heal cycle
(safe: nothing is written), prints what SARAN found and would fix, then runs a
second cycle that actually applies and verifies the fixes on the copy.

Run:  python examples/demo.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

# Allow `python examples/demo.py` from the repo root without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saran import Config, Orchestrator
from saran.core.events import console_logger


def main() -> None:
    here = os.path.dirname(__file__)
    workdir = tempfile.mkdtemp(prefix="saran_demo_")
    shutil.copy(os.path.join(here, "vulnerable_sample.py"), workdir)

    print(f"Working copy: {workdir}\n")

    # --- Pass 1: dry-run. Observe and propose, write nothing. --------------
    print("=== DRY RUN (nothing is written) ===")
    cfg = Config(target_dir=workdir, dry_run=True, intelligence="rules")
    orch = Orchestrator(cfg)
    orch.events.subscribe(console_logger())
    report = orch.heal_once()
    print(f"\nfound={len(report.findings)}  would-heal={report.healed}\n")

    # --- Pass 2: apply for real (auto-approve, no LLM needed). -------------
    print("=== APPLY (auto-approved, sandbox-verified, rollback on failure) ===")
    cfg = Config(
        target_dir=workdir,
        dry_run=False,
        require_approval=False,
        intelligence="rules",
    )
    orch = Orchestrator(cfg)
    orch.events.subscribe(console_logger())
    report = orch.heal_once()
    print(f"\nhealed={report.healed}  rolled_back={report.rolled_back}\n")

    print("=== Result on disk ===")
    with open(os.path.join(workdir, "vulnerable_sample.py")) as fh:
        print(fh.read())


if __name__ == "__main__":
    main()
