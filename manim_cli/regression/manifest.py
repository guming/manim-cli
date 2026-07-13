from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from manim_cli.dsl.compiler import compile_scene_file, scene_canonical_json
from manim_cli.dsl.validators import parse_and_validate_scene_data, validate_scene_file
from manim_cli.jsonio import load_json
from manim_cli.qa.engine import run_qa


def run_regression_dir(fixtures_dir: Path, out_dir: Path, render: bool = False) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for scene_path in sorted(fixtures_dir.glob("*/scene.json")):
        name = scene_path.parent.name
        validation = validate_scene_file(scene_path)
        compile_result = None
        qa_result = None
        qa_baseline = None
        manifest_baseline = None
        cost = None
        manifest = None
        if validation.get("ok"):
            start = time.perf_counter()
            compile_result = compile_scene_file(scene_path, out_dir / name, profile="fast")
            compile_seconds = time.perf_counter() - start
            start = time.perf_counter()
            qa_result = run_qa(scene_path, profile="strict")
            qa_seconds = time.perf_counter() - start
            cost = render_cost_proxy(scene_path, out_dir / name, compile_seconds, qa_seconds)
            manifest = build_manifest(scene_path, qa_result, cost)
            baseline_path = scene_path.parent / "expected_qa.json"
            if baseline_path.exists():
                qa_baseline = compare_expected_qa(qa_result, load_json(baseline_path))
            manifest_baseline_path = scene_path.parent / "expected_manifest.json"
            if manifest_baseline_path.exists():
                manifest_baseline = compare_manifest(manifest, load_json(manifest_baseline_path))
        results.append({"name": name, "scene": str(scene_path), "validate": validation, "compile": compile_result, "qa": qa_result, "qa_baseline": qa_baseline, "manifest": manifest, "manifest_baseline": manifest_baseline, "render_cost": cost, "render_skipped": not render})
    ok = all(item["validate"].get("ok") and (not item["compile"] or item["compile"].get("ok")) and (not item["qa_baseline"] or item["qa_baseline"].get("ok")) and (not item["manifest_baseline"] or item["manifest_baseline"].get("ok")) for item in results)
    return {"ok": ok, "results": results}


def compare_expected_qa(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    known_false_positives = set(expected.get("known_false_positives", []))
    actual_issues = actual.get("issues", [])
    actual_map = actual_issue_map(actual_issues, by_type="issue_types" in expected and "fingerprints" not in expected)
    expected_map = expected_issue_map(expected)
    actual_keys = set(actual_map) - known_false_positives
    expected_keys = set(expected_map)
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    severity_changed = []
    for key in sorted(actual_keys & expected_keys):
        expected_severity = expected_map[key].get("severity")
        actual_severity = actual_map[key].get("severity")
        if expected_severity and actual_severity and expected_severity != actual_severity:
            severity_changed.append({"issue": key, "expected": expected_severity, "actual": actual_severity})
    return {
        "ok": not missing and not unexpected and not severity_changed,
        "missing": missing,
        "unexpected": unexpected,
        "severity_changed": severity_changed,
        "actual_issues": sorted(actual_keys),
        "expected_issues": sorted(expected_keys),
    }


def issue_identity(issue: Dict[str, Any]) -> str:
    return str(issue.get("fingerprint") or issue.get("type"))


def actual_issue_map(issues: List[Dict[str, Any]], by_type: bool = False) -> Dict[str, Dict[str, Any]]:
    if by_type:
        return {str(issue.get("type")): issue for issue in issues}
    return {issue_identity(issue): issue for issue in issues}


def expected_issue_map(expected: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if "fingerprints" in expected:
        return {str(item): {} for item in expected["fingerprints"]}
    if "issue_types" in expected:
        return {str(item): {} for item in expected["issue_types"]}
    result: Dict[str, Dict[str, Any]] = {}
    for item in expected.get("issues", []):
        if isinstance(item, dict):
            result[issue_identity(item)] = item
        else:
            result[str(item)] = {}
    return result


def render_cost_proxy(scene_path: Path, generated_dir: Path, compile_seconds: float, qa_seconds: float) -> Dict[str, Any]:
    scene = load_json(scene_path)
    scene_py = generated_dir / "scene.py"
    actions = sum(len(step.get("actions", [])) for step in scene.get("steps", []))
    return {
        "compile_seconds": round(compile_seconds, 4),
        "qa_seconds": round(qa_seconds, 4),
        "scene_py_bytes": scene_py.stat().st_size if scene_py.exists() else 0,
        "mobject_count": len(scene.get("mobjects", [])),
        "action_count": actions,
    }


def build_manifest(scene_path: Path, qa_result: Dict[str, Any], cost: Dict[str, Any]) -> Dict[str, Any]:
    scene_data = load_json(scene_path)
    parsed = parse_and_validate_scene_data(scene_data, file=str(scene_path), quality_gate="off")
    canonical = scene_canonical_json(parsed.scene) if parsed.diagnostic.get("ok") else ""
    slots_used = sorted({mob.get("layout", {}).get("slot") for mob in scene_data.get("mobjects", []) if mob.get("layout", {}).get("slot")})
    return {
        "scene_hash": _short_hash(canonical),
        "mobject_count": cost["mobject_count"],
        "action_count": cost["action_count"],
        "step_count": len(scene_data.get("steps", [])),
        "layout_slots": slots_used,
        "qa_score": qa_result.get("score"),
        "qa_issue_types": sorted({issue.get("type", "") for issue in qa_result.get("issues", [])}),
        "scene_py_bytes": cost["scene_py_bytes"],
    }


def compare_manifest(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    keys = sorted(set(actual) | set(expected))
    changed: List[Dict[str, Any]] = []
    for key in keys:
        actual_val = actual.get(key)
        expected_val = expected.get(key)
        if actual_val != expected_val:
            changed.append({"key": key, "expected": expected_val, "actual": actual_val})
    return {"ok": not changed, "changed": changed}


def _short_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else ""
