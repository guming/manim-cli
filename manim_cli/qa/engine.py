from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from manim_cli.dsl.analysis import analyze_scene
from manim_cli.dsl.knowledge import policy_warnings
from manim_cli.dsl.layout import layout_warnings
from manim_cli.dsl.splitting import storyboard_split_plans
from manim_cli.dsl.templates import unresolved_layout_role_warnings
from manim_cli.dsl.validators import parse_and_validate_scene_data
from manim_cli.jsonio import Diagnostic, error_result, load_json, ok_result
from manim_cli.planning.alignment import alignment_warnings
from manim_cli.planning.pedagogy import load_plan, load_storyboard, pedagogy_warnings
from manim_cli.planning.models import Storyboard, TeachingPlan
from manim_cli.qa.adapters import warnings_to_issues
from manim_cli.qa.feedback import write_feedback
from manim_cli.qa.math_lint import math_warnings
from manim_cli.qa.timing import timing_warnings


def run_qa(
    scene_path: Path,
    profile: str = "relaxed",
    plan_path: Optional[Path] = None,
    storyboard_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    repair_context: Optional[Dict[str, Any]] = None,
) -> Diagnostic:
    if profile not in ("relaxed", "strict", "final"):
        return error_result("qa", "invalid_enum", "profile must be relaxed, strict, or final")
    try:
        data = load_json(scene_path)
    except Exception as exc:
        return error_result("qa", "invalid_json", str(exc), location={"file": str(scene_path)})

    parsed = parse_and_validate_scene_data(data, file=str(scene_path), base_dir=scene_path.parent, quality_gate="off")
    if not parsed.diagnostic.get("ok"):
        return parsed.diagnostic
    scene = parsed.scene
    analysis = analyze_scene(scene)
    plan = load_direct_plan(plan_path) if plan_path else load_plan(scene_path.parent, scene.plan_ref)
    storyboard = load_direct_storyboard(storyboard_path) if storyboard_path else load_storyboard(scene_path.parent, scene.storyboard_ref)

    warnings = []
    warnings.extend(unresolved_layout_role_warnings(scene))
    warnings.extend(storyboard_split_plans(scene))
    warnings.extend(policy_warnings(scene, scene_path.parent))
    warnings.extend(layout_warnings(scene))
    warnings.extend(pedagogy_warnings(scene, plan, storyboard))
    warnings.extend(alignment_warnings(scene, plan, storyboard))
    warnings.extend(timing_warnings(scene, analysis, storyboard, plan))
    warnings.extend(math_warnings(scene, plan))

    issues = warnings_to_issues(warnings, profile=profile, file=str(scene_path))
    issue_dicts = [issue.to_dict() for issue in issues]
    report: Diagnostic = ok_result(
        "qa",
        profile=profile,
        score=score_issues(issue_dicts),
        issues=issue_dicts,
        summary=summarize_issues(issue_dicts),
        repair_context=repair_context or {},
    )
    report["ok"] = not any(issue.get("severity") == "error" for issue in issue_dicts)
    report.update(repair_diagnostics(issue_dicts, repair_context))
    if out_dir:
        report["feedback"] = write_feedback(out_dir, report)
    return report


def load_direct_plan(path: Path) -> TeachingPlan:
    return TeachingPlan.model_validate(load_json(path))


def load_direct_storyboard(path: Path) -> Storyboard:
    return Storyboard.model_validate(load_json(path))


def summarize_issues(issues: list[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"error": 0, "warning": 0, "info": 0, "total": len(issues)}
    for issue in issues:
        severity = issue.get("severity", "warning")
        if severity in summary:
            summary[severity] += 1
    return summary


def score_issues(issues: list[Dict[str, Any]]) -> int:
    penalty = 0
    for issue in issues:
        penalty += 25 if issue.get("severity") == "error" else 8
    return max(0, 100 - penalty)


def repair_diagnostics(issues: list[Dict[str, Any]], repair_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not repair_context:
        return {"repaired_issues": [], "regression_reintroduced": [], "new_issues_after_repair": [], "repair_loop_risk": "none"}
    previous = issue_identity_set(repair_context.get("previous_issues", []))
    current = issue_identity_set(issues)
    repaired = set(repair_context.get("repaired_issue_fingerprints", []))
    if not repaired:
        repaired = set(repair_context.get("repaired_issue_types", []))
    reintroduced = sorted(current & repaired)
    new_issues = sorted(current - previous)
    repaired_now = sorted(previous - current)
    risk = "high" if reintroduced else ("medium" if new_issues else "none")
    return {
        "repaired_issues": repaired_now,
        "regression_reintroduced": reintroduced,
        "new_issues_after_repair": new_issues,
        "repair_loop_risk": risk,
    }


def issue_identity_set(issues: Any) -> set[str]:
    result: set[str] = set()
    if not isinstance(issues, list):
        return result
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        identity = issue.get("fingerprint") or issue.get("issue_id") or issue.get("type")
        if identity:
            result.add(str(identity))
    return result
