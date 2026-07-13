from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from manim_cli.jsonio import load_json
from manim_cli.qa.engine import run_qa


def run_qa_eval(eval_dir: Path, fail_on_false_positive: bool = True) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    true_positive = 0
    false_positive = 0
    false_negative = 0
    unknown_static = 0
    severity_drifts = 0
    for scene_path in sorted(eval_dir.glob("*/scene.json")):
        expected_path = scene_path.parent / "expected_qa.json"
        if not expected_path.exists():
            continue
        actual = run_qa(scene_path, profile="strict")
        expected = load_json(expected_path)
        comparison = compare_issue_sets(actual, expected)
        cases.append({"name": scene_path.parent.name, **comparison})
        true_positive += comparison["true_positive"]
        false_positive += comparison["false_positive"]
        false_negative += comparison["false_negative"]
        unknown_static += comparison["unknown_static"]
        severity_drifts += len(comparison["severity_changed"])
    if not cases:
        return {"ok": False, "error": "no_eval_cases", "cases": [], "metrics": {}}
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    ok = false_negative == 0 and severity_drifts == 0 and (not fail_on_false_positive or false_positive == 0)
    return {
        "ok": ok,
        "cases": cases,
        "metrics": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "false_positive_rate": round(false_positive / max(1, true_positive + false_positive), 4),
            "unknown_static": unknown_static,
            "severity_drifts": severity_drifts,
        },
    }


def compare_issue_sets(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    type_only = "issue_types" in expected and "fingerprints" not in expected and "issues" not in expected
    expected_keys = set(expected_issue_keys(expected))
    known_false_positives = set(expected.get("known_false_positives", []))
    actual_issues = actual.get("issues", [])
    if type_only:
        actual_keys = {str(issue.get("type")) for issue in actual_issues}
    else:
        actual_keys = {issue_key(issue) for issue in actual_issues}
    actual_keys -= known_false_positives
    matched = actual_keys & expected_keys
    missing = expected_keys - actual_keys
    unexpected = actual_keys - expected_keys
    unknown_static = sum(1 for issue in actual_issues if issue.get("confidence") == "unknown_static")
    severity_changed = severity_drift(actual_issues, expected, type_only)
    return {
        "ok": not missing and not severity_changed,
        "matched": sorted(matched),
        "missing": sorted(missing),
        "unexpected": sorted(unexpected),
        "severity_changed": severity_changed,
        "true_positive": len(matched),
        "false_positive": len(unexpected),
        "false_negative": len(missing),
        "unknown_static": unknown_static,
    }


def severity_drift(actual_issues: List[Dict[str, Any]], expected: Dict[str, Any], type_only: bool) -> List[Dict[str, str]]:
    if type_only or "issues" not in expected:
        return []
    expected_severity: Dict[str, str] = {}
    for issue in expected["issues"]:
        if isinstance(issue, dict) and "severity" in issue:
            expected_severity[issue_key(issue)] = str(issue["severity"])
    if not expected_severity:
        return []
    actual_severity = {issue_key(issue): str(issue.get("severity", "")) for issue in actual_issues}
    changed: List[Dict[str, str]] = []
    for key, expected_sev in expected_severity.items():
        actual_sev = actual_severity.get(key)
        if actual_sev and actual_sev != expected_sev:
            changed.append({"issue": key, "expected": expected_sev, "actual": actual_sev})
    return changed


def expected_issue_keys(expected: Dict[str, Any]) -> List[str]:
    if "fingerprints" in expected:
        return [str(item) for item in expected["fingerprints"]]
    if "issues" in expected:
        return [issue_key(issue) if isinstance(issue, dict) else str(issue) for issue in expected["issues"]]
    return [str(item) for item in expected.get("issue_types", [])]


def issue_key(issue: Dict[str, Any]) -> str:
    return str(issue.get("fingerprint") or issue.get("type"))
