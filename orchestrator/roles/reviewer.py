"""
HIVE v4.1 — REVIEWER 审查员

四层审查。

L1: 语法检查 - 自动阻断 (pass/fail)
L2: 是否符合 brief - pass/warn/fail
L3: 安全检查 - pass/warn
L4: 一致性 - pass/warn
"""

import ast
import re
from pathlib import Path
from typing import Optional

from orchestrator.hermes_bridge import run_agent


class Reviewer:
    """
    四层审查。不与交付管线互斥 (L1 除外)。
    """

    async def review(
        self,
        workspace_path: Path,
        brief: dict,
        version: int,
    ) -> dict:
        """
        执行全部四层审查。
        """
        src_dir = workspace_path / "src"
        layers = {}

        # L1: 语法检查
        layers["L1_syntax"] = self._check_syntax(src_dir)
        overall = layers["L1_syntax"]["status"]

        # L2: 是否符合 brief
        layers["L2_brief_alignment"] = self._check_alignment(brief, src_dir)
        if overall == "pass" and layers["L2_brief_alignment"]["status"] == "fail":
            overall = "fail"

        # L3: 安全检查
        layers["L3_security"] = self._check_security(src_dir)

        # L4: 一致性
        layers["L4_consistency"] = self._check_consistency(
            brief,
            brief.get("description", brief.get("_raw_description", "")),
        )

        summary_parts = []
        for name, data in layers.items():
            s = data.get("status", "?")
            summary_parts.append(f"{name}: {s}")
            if data.get("errors"):
                summary_parts.extend(f"  - {e}" for e in data["errors"][:3])
            if data.get("suggestions"):
                summary_parts.extend(f"  -> {s}" for s in data["suggestions"][:2])

        return {
            "layers": layers,
            "overall": overall,
            "summary": " | ".join(summary_parts),
        }

    def _check_syntax(self, src_dir: Path) -> dict:
        """L1: syntax check."""
        errors = []
        if not src_dir.exists():
            return {"status": "pass", "errors": [], "note": "no src dir"}

        for py_file in src_dir.rglob("*.py"):
            try:
                ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError as e:
                errors.append(f"{py_file.relative_to(src_dir.parent)}: {e}")

        return {
            "status": "fail" if errors else "pass",
            "errors": errors,
        }

    def _check_alignment(self, brief: dict, src_dir: Path) -> dict:
        """L2: check alignment with brief."""
        issues = []
        suggestions = []

        if not src_dir.exists():
            return {"status": "pass", "issues": [], "suggestions": []}

        features = brief.get("features", [])
        feature_names = [f.get("name", "") for f in features] if features else []

        # Check if feature names appear in code comments or function names
        for fname in feature_names:
            found = False
            for py_file in src_dir.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                if fname.lower() in content.lower():
                    found = True
                    break
            if not found:
                suggestions.append(f"Feature '{fname}' not found in code")

        tech_stack = brief.get("tech_stack", {})
        lang = tech_stack.get("language", "")
        if lang:
            ext_map = {"Python": ".py", "Rust": ".rs", "Go": ".go", "Node.js": ".js"}
            expected_ext = ext_map.get(lang, ".py")
            found_files = list(src_dir.rglob(f"*{expected_ext}"))
            if not found_files:
                issues.append(f"No {expected_ext} files found for {lang}")

        return {
            "status": "warn" if suggestions else "pass",
            "issues": issues,
            "suggestions": suggestions,
        }

    def _check_security(self, src_dir: Path) -> dict:
        """L3: security check."""
        findings = []
        if not src_dir.exists():
            return {"status": "pass", "findings": []}

        patterns = [
            (r"(?:api_key|apikey|secret|password)\s*=\s*['\"]['\"]", "Empty api key/secret placeholder"),
            (r"(?:eval|exec)\s*\(", "Use of eval/exec"),
            (r"(?:os\.system|subprocess\.call)\s*\(", "Shell execution"),
            (r"(?:SELECT|INSERT|UPDATE|DELETE).*FROM", "SQL query (may be OK if using ORM)"),
        ]

        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for pattern, msg in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    findings.append(f"{py_file.name}: {msg}")

        return {
            "status": "warn" if findings else "pass",
            "findings": findings,
        }

    def _check_consistency(self, brief: dict, original_request: str) -> dict:
        """L4: consistency check."""
        notes = []
        features = brief.get("features", [])
        description = brief.get("description", "")

        if features and isinstance(features, list):
            notes.append(f"defined {len(features)} features")
        else:
            notes.append("no features defined")

        tech_stack = brief.get("tech_stack", {})
        if tech_stack.get("language"):
            notes.append(f"tech: {tech_stack['language']}")

        return {
            "status": "pass",
            "score": 0.8 if notes else 0.5,
            "notes": notes,
        }
