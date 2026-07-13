from __future__ import annotations

import re
from typing import Dict, List, Optional

from manim_cli.dsl.analysis import SceneAnalysis
from manim_cli.dsl.models import SceneDef
from manim_cli.planning.models import Storyboard, TeachingPlan


def timing_warnings(scene: SceneDef, analysis: SceneAnalysis, storyboard: Storyboard | None, plan: Optional[TeachingPlan] = None) -> List[Dict[str, object]]:
    warnings: List[Dict[str, object]] = []
    if storyboard:
        warnings.extend(step_frame_timing_warnings(scene, analysis, storyboard))
    if storyboard and plan:
        warnings.extend(event_timing_warnings(scene, analysis, storyboard, plan))
    if plan:
        warnings.extend(cue_timing_warnings(scene, analysis, plan))
    return warnings


def step_frame_timing_warnings(scene: SceneDef, analysis: SceneAnalysis, storyboard: Storyboard) -> List[Dict[str, object]]:
    event_to_frame = {event.id: frame for frame in storyboard.frames for event in frame.visual_events}
    warnings: List[Dict[str, object]] = []
    for step, timeline_step in zip(scene.steps, analysis.timeline):
        if not step.storyboard_event_id:
            continue
        frame = event_to_frame.get(step.storyboard_event_id)
        if not frame or frame.duration_seconds is None:
            continue
        frame_duration = float(frame.duration_seconds)
        step_duration = timeline_step.duration_seconds
        allowed = allowed_drift_seconds(scene, timeline_step.step_index, frame_duration)
        drift = abs(step_duration - frame_duration)
        if drift > allowed:
            warnings.append(
                {
                    "type": "step_frame_timing_drift",
                    "step": timeline_step.step_id,
                    "step_index": timeline_step.step_index,
                    "storyboard_event_id": step.storyboard_event_id,
                    "frame_id": frame.id,
                    "step_duration": round(step_duration, 3),
                    "frame_duration": round(frame_duration, 3),
                    "allowed_drift": round(allowed, 3),
                    "drift": round(drift, 3),
                }
            )
    return warnings


def event_timing_warnings(scene: SceneDef, analysis: SceneAnalysis, storyboard: Storyboard, plan: TeachingPlan) -> List[Dict[str, object]]:
    # Cue-event alignment (PRD §5.3 / §13.7 P1): a VisualEvent with an explicit
    # duration_seconds should match its linked scene step's animation duration.
    event_map = {event.id: (frame, event) for frame in storyboard.frames for event in frame.visual_events}
    warnings: List[Dict[str, object]] = []
    for step, timeline_step in zip(scene.steps, analysis.timeline):
        if not step.storyboard_event_id:
            continue
        pair = event_map.get(step.storyboard_event_id)
        if not pair:
            continue
        frame, event = pair
        if event.duration_seconds is None:
            continue
        event_duration = float(event.duration_seconds)
        step_duration = timeline_step.duration_seconds
        allowed = allowed_drift_seconds(scene, timeline_step.step_index, event_duration)
        drift = abs(step_duration - event_duration)
        if drift > allowed:
            warnings.append(
                {
                    "type": "cue_event_timing_drift",
                    "step": timeline_step.step_id,
                    "step_index": timeline_step.step_index,
                    "storyboard_event_id": step.storyboard_event_id,
                    "frame_id": frame.id,
                    "step_duration": round(step_duration, 3),
                    "event_duration": round(event_duration, 3),
                    "allowed_drift": round(allowed, 3),
                    "drift": round(drift, 3),
                }
            )
    return warnings


def cue_timing_warnings(scene: SceneDef, analysis: SceneAnalysis, plan: TeachingPlan) -> List[Dict[str, object]]:
    # Narration cue alignment (PRD §13.7 P1): a NarrationCue with an explicit
    # duration_seconds should match its linked scene step's animation duration.
    cue_map = {cue.id: cue for cue in plan.narration_cues}
    warnings: List[Dict[str, object]] = []
    for step, timeline_step in zip(scene.steps, analysis.timeline):
        if not step.narration_cue_id:
            continue
        cue = cue_map.get(step.narration_cue_id)
        if cue is None or cue.duration_seconds is None:
            continue
        cue_duration = float(cue.duration_seconds)
        step_duration = timeline_step.duration_seconds
        allowed = allowed_drift_seconds(scene, timeline_step.step_index, cue_duration)
        drift = abs(step_duration - cue_duration)
        if drift > allowed:
            warnings.append(
                {
                    "type": "cue_event_timing_drift",
                    "step": timeline_step.step_id,
                    "step_index": timeline_step.step_index,
                    "narration_cue_id": step.narration_cue_id,
                    "step_duration": round(step_duration, 3),
                    "cue_duration": round(cue_duration, 3),
                    "allowed_drift": round(allowed, 3),
                    "drift": round(drift, 3),
                }
            )
    return warnings


def allowed_drift_seconds(scene: SceneDef, step_index: int, frame_duration: float) -> float:
    complexity = step_math_complexity(scene, step_index)
    if complexity <= 12:
        ratio = 0.35
    elif complexity <= 30:
        ratio = 0.5
    else:
        ratio = 0.7
    return max(1.0, frame_duration * ratio)


def step_math_complexity(scene: SceneDef, step_index: int) -> int:
    if step_index >= len(scene.steps):
        return 0
    object_ids = {action.target for action in scene.steps[step_index].actions if action.target and not isinstance(action.target, list)}
    texts = []
    for mob in scene.mobjects:
        if mob.id in object_ids:
            texts.append(str(mob.args.get("tex") or mob.args.get("text") or ""))
    text = "\n".join(texts)
    tokens = len(re.findall(r"[A-Za-z0-9_]+|\\[A-Za-z]+", text))
    fractions = text.count("\\frac")
    lines = text.count("\\\\") + text.count("\n")
    matrix_blocks = len(re.findall(r"\\begin\{(?:matrix|pmatrix|bmatrix|cases)\}", text))
    return tokens + 3 * fractions + 2 * lines + 2 * matrix_blocks
