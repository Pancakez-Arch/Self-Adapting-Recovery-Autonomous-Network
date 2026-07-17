"""End-to-end tests of the orchestrator using the deterministic backend."""

import os

from saran.core.config import Config
from saran.core.models import Outcome
from saran.core.orchestrator import Orchestrator

SAMPLE = (
    "import yaml, hashlib\n"
    "def load(raw):\n"
    "    return yaml.load(raw)\n"
    "def h(d):\n"
    "    return hashlib.md5(d).hexdigest()\n"
    "def p(t):\n"
    "    try:\n"
    "        return int(t)\n"
    "    except:\n"
    "        return None\n"
)


def _repo(tmp_path):
    (tmp_path / "mod.py").write_text(SAMPLE)
    return str(tmp_path)


def test_dry_run_writes_nothing(tmp_path):
    repo = _repo(tmp_path)
    cfg = Config(target_dir=repo, dry_run=True, intelligence="rules")
    report = Orchestrator(cfg).heal_once()
    assert report.healed > 0  # verified in sandbox
    # File on disk is untouched.
    assert (tmp_path / "mod.py").read_text() == SAMPLE


def test_apply_fixes_and_verifies(tmp_path):
    repo = _repo(tmp_path)
    cfg = Config(
        target_dir=repo,
        dry_run=False,
        require_approval=False,
        intelligence="rules",
        allowed_categories=("vulnerability", "quality"),
    )
    Orchestrator(cfg).heal_once()
    result = (tmp_path / "mod.py").read_text()
    assert "yaml.safe_load(" in result
    assert "hashlib.sha256(" in result
    assert "except Exception:" in result
    assert "yaml.load(" not in result


def test_rollback_on_verification_failure(tmp_path):
    """A verify command that always fails must leave the tree untouched."""
    repo = _repo(tmp_path)
    cfg = Config(
        target_dir=repo,
        dry_run=False,
        require_approval=False,
        intelligence="rules",
        allowed_categories=("vulnerability", "quality"),
        verify_command="exit 1",  # verification always fails
    )
    report = Orchestrator(cfg).heal_once()
    # Nothing should have survived; sandbox verification fails before any write.
    assert all(r.outcome is not Outcome.VERIFIED for r in report.results)
    assert (tmp_path / "mod.py").read_text() == SAMPLE


def test_audit_log_written(tmp_path):
    repo = _repo(tmp_path)
    audit = str(tmp_path / ".saran" / "audit.jsonl")
    cfg = Config(target_dir=repo, dry_run=True, intelligence="rules", audit_log_path=audit)
    Orchestrator(cfg).heal_once()
    assert os.path.exists(audit)
    assert "cycle.start" in open(audit).read()
