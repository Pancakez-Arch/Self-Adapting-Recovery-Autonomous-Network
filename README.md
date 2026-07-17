# SARAN — Self-Adapting Recovery Autonomous Network

A framework for software that **inspects its own code for vulnerabilities and
improvement opportunities, then repairs them autonomously** — behind hard safety
gates: every fix is trialled in a sandbox, verified, and rolled back if it fails,
with a complete audit trail.

SARAN is not a magic "AI that rewrites itself unattended." It's the *disciplined
loop* that makes autonomous self-repair trustworthy: detection → diagnosis →
planning → guardrails → sandboxed trial → verification → rollback. The
"intelligence" that reasons about issues is pluggable — it uses **Claude** when
credentials are available, and a deterministic rule engine otherwise (so the
whole system runs offline with zero dependencies).

```
 ┌──────────┐   ┌───────────┐   ┌────────┐   ┌────────────┐   ┌──────────────┐
 │  SCAN    │──▶│ DIAGNOSE  │──▶│  PLAN  │──▶│ GUARDRAILS │──▶│  SANDBOX +   │
 │ (self)   │   │ (Claude / │   │        │   │  (gates)   │   │  VERIFY      │
 └──────────┘   │  rules)   │   └────────┘   └────────────┘   └──────┬───────┘
                └───────────┘                                        │
        ┌────────────────────────────────────────────────┬─────────┘
        ▼ pass                                            ▼ fail
   APPLY to real tree → verify again → commit        discard (nothing written)
        │                    │
        │                    ▼ fail
        │               ROLLBACK (exact restore)
        ▼ pass
     DONE  (audit log records everything)
```

## Why this shape

Anything that edits its own source is one bad patch away from breaking itself.
SARAN's design answers three questions a self-modifying system must answer:

| Question | Mechanism |
| --- | --- |
| *Is this change safe?* | Guardrails: confidence threshold, category allow-list, blast-radius cap, path confinement, truncation guard, human/callback approval. |
| *Will it break anything?* | Every patch is applied to a throwaway **sandbox** copy and **verified** (your test command, or a compile check) before it ever touches real code. |
| *Can I undo it and prove what happened?* | An exact **rollback** ledger reverts files byte-for-byte; an append-only **JSONL audit log** records every scan, diagnosis, gate decision, apply, and rollback. |

## Install

```bash
pip install -e .            # core framework, zero runtime deps
pip install -e ".[claude]"  # + Claude-backed intelligence
pip install -e ".[dev]"     # + pytest
```

## Quick start

```python
from saran import Orchestrator, Config

# Safe by default: dry-run, nothing is written to disk.
orch = Orchestrator(Config(target_dir="my_project"))
report = orch.heal_once()
print(f"{len(report.findings)} findings, {report.healed} would be healed")
```

Apply real fixes (auto-approve, sandbox-verified, rollback on failure):

```python
cfg = Config(
    target_dir="my_project",
    dry_run=False,
    require_approval=False,
    verify_command="pytest -q",   # your real safety net
)
Orchestrator(cfg).run(until_clean=True, max_cycles=5)
```

## Command line

```bash
saran scan                    # report findings, change nothing
saran heal                    # dry-run heal cycle (safe default)
saran heal --apply            # write verified fixes (prompts for approval)
saran heal --apply --yes      # skip the prompt
saran heal --apply --commit   # git-commit each verified fix
saran heal --verify "pytest -q" --apply
```

Or run the self-contained demo:

```bash
python examples/demo.py
```

## Using Claude as the intelligence layer

The intelligence backend decides whether a finding is real, its root cause,
whether it's safely auto-fixable, and generates the corrected file. With
`intelligence="auto"` (the default), SARAN uses Claude when credentials are
present and falls back to deterministic rules otherwise.

```bash
export ANTHROPIC_API_KEY=...        # or run `ant auth login`
python -c "from saran import *; Orchestrator(Config(intelligence='claude')).scan()"
```

Diagnosis uses structured outputs (validated JSON); fixes are streamed full-file
rewrites. Model and effort are configurable (`Config(model=..., effort=...)`,
default `claude-opus-4-8` at `high` effort). The Claude adapter degrades
gracefully — if the SDK or credentials are missing, it falls back rather than
crashing the loop.

## What it detects today

- **Vulnerabilities** — `eval`/`exec`, `shell=True`, `os.system`, unsafe
  `yaml.load`, `pickle`, weak MD5, disabled TLS verification.
- **Secrets** — hardcoded credentials, AWS keys, private keys (values are
  redacted from the audit trail).
- **Dependencies** — unpinned requirements and versions matching a local
  advisory table (point it at OSV / `pip-audit` for production).
- **Quality / self-upgrade** — bare `except:`, mutable default arguments,
  syntax errors.

Deterministic auto-fixers exist for the mechanically-safe subset
(`yaml.load`→`safe_load`, `md5`→`sha256`, `verify=False`→`True`, bare
`except`→`except Exception`). Everything else is deferred to the Claude backend
or a human.

## Extending

Everything is a small, swappable interface:

- **Scanners** (`saran/scanners/base.py`) — subclass `Scanner`, emit `Finding`s.
  Wrap bandit, semgrep, or CodeQL here.
- **Intelligence** (`saran/intelligence/base.py`) — implement `diagnose()` and
  `propose_fix()`.
- **Verifier** (`saran/verification/verifier.py`) — plug in any check command.
- **Monitor** (`saran/monitor/health.py`) — register runtime health probes;
  `Orchestrator.watch()` heals only when the system is degraded.

```python
orch = Orchestrator(cfg)
orch.monitor.register("db_reachable", lambda: ping_db(), critical=True)
orch.watch()   # assess health, heal if unhealthy
```

## Safety defaults (all conservative)

| Setting | Default | Meaning |
| --- | --- | --- |
| `dry_run` | `True` | Propose only; never write to disk. |
| `require_approval` | `True` | Real writes need a yes (callback or CLI prompt). |
| `auto_commit` | `False` | Never commits unless asked. |
| `min_confidence` | `0.7` | Low-confidence diagnoses are never auto-applied. |
| `max_patches_per_cycle` | `5` | Blast-radius cap per run. |
| `allowed_categories` | vuln/secret/quality | Only these are auto-healed. |

## Tests

```bash
python -m pytest -q
```

Covers scanners, guardrails, the intelligence factory/fallback, and the full
scan→heal→verify→rollback loop end-to-end.

## License

MIT.
