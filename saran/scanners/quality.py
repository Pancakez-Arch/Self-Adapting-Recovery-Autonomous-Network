"""Code-quality / self-improvement scanner.

These findings are the "things it can upgrade and fix by itself" bucket:
low-risk, mechanically fixable smells. They compile-check cleanly, so the
verification stage can confirm a fix without a full test suite.
"""

from __future__ import annotations

import ast

from ..core.models import Category, Finding, Severity
from .base import Scanner


class QualityScanner(Scanner):
    name = "quality"

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for path in self.iter_files((".py",)):
            source = self.read(path)
            if not source:
                continue
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as exc:
                findings.append(
                    Finding(
                        category=Category.QUALITY,
                        severity=Severity.CRITICAL,
                        title="Syntax error",
                        detail=f"File does not parse: {exc.msg}",
                        file_path=path,
                        line=exc.lineno or 0,
                        rule_id="QA.SYNTAX",
                        suggestion="Fix the syntax error before other analysis can proceed.",
                    )
                )
                continue
            findings.extend(self._scan_tree(path, tree))
        return findings

    def _scan_tree(self, path: str, tree: ast.AST) -> list[Finding]:
        out: list[Finding] = []
        for node in ast.walk(tree):
            # Bare `except:` swallows everything, including KeyboardInterrupt.
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                out.append(
                    Finding(
                        category=Category.QUALITY,
                        severity=Severity.MEDIUM,
                        title="Bare except clause",
                        detail="`except:` catches all exceptions, hiding bugs.",
                        file_path=path,
                        line=node.lineno,
                        rule_id="QA.BARE_EXCEPT",
                        suggestion="Catch a specific exception type, e.g. `except Exception:`.",
                    )
                )
            # Mutable default arguments are a classic Python footgun.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        out.append(
                            Finding(
                                category=Category.QUALITY,
                                severity=Severity.MEDIUM,
                                title=f"Mutable default argument in '{node.name}'",
                                detail="Mutable defaults are shared across calls.",
                                file_path=path,
                                line=node.lineno,
                                rule_id="QA.MUTABLE_DEFAULT",
                                suggestion="Use None as the default and create the object inside.",
                            )
                        )
                        break
        return out
