import os

from saran.core.config import Config
from saran.core.models import Category, Severity
from saran.scanners.dependency import DependencyScanner
from saran.scanners.quality import QualityScanner
from saran.scanners.vulnerability import VulnerabilityScanner


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return str(p)


def test_vulnerability_scanner_flags_yaml_and_secret(tmp_path):
    _write(
        tmp_path,
        "app.py",
        "import yaml\n"
        "cfg = yaml.load(raw)\n"
        "API_KEY = 'abcdef0123456789abcdef'\n",
    )
    findings = VulnerabilityScanner(Config(target_dir=str(tmp_path))).scan()
    rule_ids = {f.rule_id for f in findings}
    assert "PY.YAML_LOAD" in rule_ids
    assert any(f.category is Category.SECRET for f in findings)
    # Secret value is never leaked into the finding.
    secret = next(f for f in findings if f.category is Category.SECRET)
    assert secret.snippet == "<redacted>"
    assert secret.severity is Severity.CRITICAL


def test_quality_scanner_flags_bare_except_and_mutable_default(tmp_path):
    _write(
        tmp_path,
        "q.py",
        "def f(x=[]):\n"
        "    try:\n"
        "        return x\n"
        "    except:\n"
        "        return None\n",
    )
    findings = QualityScanner(Config(target_dir=str(tmp_path))).scan()
    rule_ids = {f.rule_id for f in findings}
    assert "QA.BARE_EXCEPT" in rule_ids
    assert "QA.MUTABLE_DEFAULT" in rule_ids


def test_dependency_scanner_flags_unpinned_and_vulnerable(tmp_path):
    _write(tmp_path, "requirements.txt", "requests\npyyaml==5.1\n")
    findings = DependencyScanner(Config(target_dir=str(tmp_path))).scan()
    rule_ids = {f.rule_id for f in findings}
    assert "DEP.UNPINNED" in rule_ids
    assert "DEP.VULNERABLE" in rule_ids


def test_scanner_respects_exclude(tmp_path):
    os.makedirs(tmp_path / "node_modules")
    _write(tmp_path / "node_modules", "bad.py", "eval('x')\n")
    findings = VulnerabilityScanner(Config(target_dir=str(tmp_path))).scan()
    assert findings == []
