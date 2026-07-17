from saran.core.config import Config
from saran.core.models import Category, Diagnosis, Finding, Patch, Severity
from saran.safety.guardrails import Guardrails


def _finding(category=Category.QUALITY):
    return Finding(
        category=category,
        severity=Severity.MEDIUM,
        title="t",
        detail="d",
        file_path="/repo/x.py",
        rule_id="R1",
    )


def _diag(conf=0.9, fixable=True, category=Category.QUALITY):
    return Diagnosis(
        finding=_finding(category),
        root_cause="rc",
        confidence=conf,
        auto_fixable=fixable,
    )


def test_low_confidence_blocked():
    g = Guardrails(Config(min_confidence=0.7))
    assert not g.check_diagnosis(_diag(conf=0.5)).allowed


def test_disallowed_category_blocked():
    g = Guardrails(Config(allowed_categories=("vulnerability",)))
    assert not g.check_diagnosis(_diag(category=Category.QUALITY)).allowed


def test_patch_outside_target_blocked():
    g = Guardrails(Config(target_dir="/repo", require_approval=False))
    patch = Patch(
        file_path="/etc/passwd",
        original_content="a" * 100,
        new_content="b" * 100,
        description="d",
    )
    assert not g.check_patch(patch, _diag()).allowed


def test_patch_truncation_blocked():
    g = Guardrails(Config(target_dir="/repo", require_approval=False))
    patch = Patch(
        file_path="/repo/x.py",
        original_content="a" * 100,
        new_content="b",  # too small relative to original
        description="d",
    )
    assert not g.check_patch(patch, _diag()).allowed


def test_approval_required_but_missing():
    # Approval only gates real writes, so dry_run must be off to exercise it.
    g = Guardrails(
        Config(target_dir="/repo", require_approval=True, dry_run=False), approval=None
    )
    patch = Patch(
        file_path="/repo/x.py",
        original_content="a" * 100,
        new_content="a" * 100 + "\nfixed",
        description="d",
    )
    assert not g.check_patch(patch, _diag()).allowed


def test_blast_radius_cap():
    g = Guardrails(Config(target_dir="/repo", require_approval=False, max_patches_per_cycle=1))
    patch = Patch(
        file_path="/repo/x.py",
        original_content="a" * 100,
        new_content="a" * 100 + "x",
        description="d",
    )
    assert g.check_patch(patch, _diag()).allowed
    g.record_applied()
    assert not g.check_patch(patch, _diag()).allowed
