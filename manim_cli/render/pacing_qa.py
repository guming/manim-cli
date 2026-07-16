from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.pacing import PacingResult, is_conclusion_object
from manim_cli.dsl.timeline import action_duration, action_groups, build_timeline
from manim_cli.render.frames import probe_video


def run_render_pacing_qa(video_path: Path, pacing: PacingResult) -> Dict[str, Any]:
    info = probe_video(video_path)
    issues: list[Dict[str, Any]] = []
    actual = float(info.get("duration", 0.0)) if info.get("ok") else 0.0
    expected = pacing.effective_duration
    tolerance = max(0.5, expected * 0.05)
    if not info.get("ok"):
        issues.append({"type": "pacing_video_probe_failed", "message": info.get("error", "ffprobe failed")})
    elif abs(actual - expected) > tolerance:
        issues.append(
            {
                "type": "pacing_actual_duration_drift",
                "expected_duration": round(expected, 3),
                "actual_duration": round(actual, 3),
                "allowed_drift": round(tolerance, 3),
            }
        )
    conclusion_hold = conclusion_visible_duration(pacing.scene)
    if conclusion_hold is not None and conclusion_hold < 2.0:
        issues.append(
            {
                "type": "pacing_conclusion_hold_too_short",
                "visible_duration": round(conclusion_hold, 3),
                "minimum_duration": 2.0,
            }
        )
    for index, step in enumerate(pacing.scene.steps):
        if any(action.type == "transform" for action in step.actions) and float(step.wait_after or 0.0) < 0.4:
            issues.append(
                {
                    "type": "pacing_transform_hold_too_short",
                    "step": step.id or f"step_{index}",
                    "visible_duration": round(float(step.wait_after or 0.0), 3),
                    "minimum_duration": 0.4,
                }
            )
    return {
        "ok": not issues,
        "actual_video_duration": round(actual, 3) if actual else None,
        "expected_duration": round(expected, 3),
        "issues": issues,
    }


def conclusion_visible_duration(scene: SceneDef) -> float | None:
    conclusion_ids = {mob.id for mob in scene.mobjects if is_conclusion_object(mob)}
    if not conclusion_ids:
        return None
    elapsed = 0.0
    completed_at: float | None = None
    for step in scene.steps:
        for group in action_groups(step.actions):
            duration = max((action_duration(action) for action in group), default=0.0)
            if completed_at is None and any(action.target in conclusion_ids and action.type in {"add", "write", "fade_in", "show_creation"} for action in group):
                completed_at = elapsed + duration
            elapsed += duration
        elapsed += float(step.wait_after or 0.0)
    return elapsed - completed_at if completed_at is not None else 0.0
