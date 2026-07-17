from saran.core.config import Config
from saran.core.models import Category, Finding, Severity
from saran.intelligence import build_intelligence
from saran.intelligence.rule_based import RuleBasedIntelligence


def _finding(rule_id, line, category=Category.VULNERABILITY):
    return Finding(
        category=category,
        severity=Severity.HIGH,
        title=rule_id,
        detail="d",
        file_path="x.py",
        line=line,
        rule_id=rule_id,
    )


def test_rule_based_fix_yaml():
    src = "import yaml\nx = yaml.load(raw)\n"
    intel = RuleBasedIntelligence()
    diag = intel.diagnose(_finding("PY.YAML_LOAD", 2), src)
    assert diag.auto_fixable
    patch = intel.propose_fix(diag, src)
    assert patch is not None
    assert "yaml.safe_load(" in patch.new_content


def test_rule_based_no_fixer_returns_none():
    src = "eval('1+1')\n"
    intel = RuleBasedIntelligence()
    diag = intel.diagnose(_finding("PY.EVAL", 1), src)
    assert not diag.auto_fixable
    assert intel.propose_fix(diag, src) is None


def test_factory_defaults_to_rules_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    intel = build_intelligence(Config(intelligence="auto"))
    assert isinstance(intel, RuleBasedIntelligence)
