from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Literal

from manim_cli.dsl.models import ActionDef, MobjectDef, SceneDef, StepDef
from manim_cli.dsl.timeline import build_timeline, step_duration

PacingProfile = Literal["preserve", "teaching", "accelerated"]
PACING_PROFILES = ("preserve", "teaching", "accelerated")

ACTION_MINIMUMS = {
    "write": 0.7,
    "transform": 0.8,
    "fade_in": 0.4,
    "fade_out": 0.4,
    "highlight": 0.6,
    "show_creation": 0.7,
    "layout": 0.6,
}


@dataclass(frozen=True)
class PacingResult:
    scene: SceneDef
    profile: PacingProfile
    source_duration: float
    effective_duration: float
    duration_scale: float
    timing_changes: list[Dict[str, Any]]
    effective_timeline: list[Dict[str, Any]]

    def diagnostic_fields(self) -> Dict[str, Any]:
        return {
            "pacing_profile": self.profile,
            "source_duration": round(self.source_duration, 3),
            "effective_duration": round(self.effective_duration, 3),
            "duration_scale": round(self.duration_scale, 4),
            "timing_changes": self.timing_changes,
            "effective_timeline": self.effective_timeline,
        }


def apply_pacing(
    scene: SceneDef,
    profile: PacingProfile = "teaching",
    step_duration_targets: Dict[str, Dict[str, Any]] | None = None,
) -> PacingResult:
    if profile not in PACING_PROFILES:
        raise ValueError(f"invalid pacing profile: {profile}")
    source_duration = scene_duration(scene)
    effective = scene.model_copy(deep=True)
    changes: list[Dict[str, Any]] = []
    if profile != "preserve":
        objects = {mob.id: mob for mob in effective.mobjects}
        for step_index, step in enumerate(effective.steps):
            role = inferred_step_role(step, step_index, len(effective.steps), objects)
            for action_index, action in enumerate(step.actions):
                apply_action_pacing(action, role, profile, step, step_index, action_index, objects, changes)
            apply_step_hold(step, role, profile, step_index, objects, changes)
            apply_external_duration_target(step, step_index, step_duration_targets or {}, changes)
    effective_duration = scene_duration(effective)
    scale = effective_duration / source_duration if source_duration else 1.0
    return PacingResult(
        scene=effective,
        profile=profile,
        source_duration=source_duration,
        effective_duration=effective_duration,
        duration_scale=scale,
        timing_changes=changes,
        effective_timeline=timeline_diagnostics(scene, effective),
    )


def scene_duration(scene: SceneDef) -> float:
    return sum(step.duration_seconds for step in build_timeline(scene))


def inferred_step_role(step: StepDef, index: int, count: int, objects: Dict[str, MobjectDef]) -> str:
    if step.timing_role:
        return step.timing_role
    targets = action_object_ids(step)
    if index == count - 1 or any(is_conclusion_object(objects.get(target)) for target in targets):
        return "conclusion"
    if any(is_formula_object(objects.get(target)) for target in targets):
        return "derivation"
    return "transition"


def apply_action_pacing(
    action: ActionDef,
    step_role: str,
    profile: PacingProfile,
    step: StepDef,
    step_index: int,
    action_index: int,
    objects: Dict[str, MobjectDef],
    changes: list[Dict[str, Any]],
) -> None:
    role = action.timing_role or step_role
    if action.type == "wait" and action.duration is not None:
        if profile == "accelerated" and role == "transition":
            set_timing(action, "duration", max(0.2, float(action.duration) * 0.3), step, step_index, action_index, changes, role)
        return
    if action.run_time is None:
        return
    original = float(action.run_time)
    minimum = ACTION_MINIMUMS.get(action.type, 0.0)
    if role == "derivation":
        minimum = max(minimum, 0.8)
    elif role == "conclusion":
        minimum = max(minimum, 0.8)
    if profile == "teaching":
        desired = max(original, minimum)
    elif role in {"derivation", "conclusion"}:
        desired = max(minimum, original * 0.65)
    else:
        desired = max(minimum, original * 0.3)
    set_timing(action, "run_time", desired, step, step_index, action_index, changes, role)


def apply_step_hold(
    step: StepDef,
    role: str,
    profile: PacingProfile,
    step_index: int,
    objects: Dict[str, MobjectDef],
    changes: list[Dict[str, Any]],
) -> None:
    current = float(step.wait_after or 0.0)
    minimum = 0.0
    targets = [objects.get(target) for target in action_object_ids(step)]
    if role == "conclusion":
        minimum = 2.0
    elif role == "derivation":
        minimum = max(0.8, max((reading_time(mob) for mob in targets if mob and is_formula_object(mob)), default=0.0))
    elif any(action.type in {"write", "transform", "fade_in"} for action in step.actions):
        minimum = max(0.8, max((reading_time(mob) for mob in targets if mob), default=0.0))
    if profile == "accelerated" and role == "transition":
        desired = min(current, 0.2)
    else:
        desired = max(current, minimum)
    if not math.isclose(current, desired):
        step.wait_after = round(desired, 3)
        changes.append(
            {
                "change": "pacing_step_hold",
                "step": step.id or f"step_{step_index}",
                "step_index": step_index,
                "timing_role": role,
                "field": "wait_after",
                "source": round(current, 3),
                "effective": round(desired, 3),
            }
        )


def reading_time(mob: MobjectDef) -> float:
    text = str(mob.args.get("tex") or mob.args.get("text") or "")
    if not text:
        return 0.0
    if is_conclusion_object(mob):
        return max(2.0, min(4.0, len(text) / 9.0))
    if is_formula_object(mob):
        tokens = len(re.findall(r"[A-Za-z0-9]+|\\[A-Za-z]+|[+\-−=±×÷]", text))
        fractions = text.count("\\frac")
        matrices = len(re.findall(r"\\begin\{(?:matrix|pmatrix|bmatrix|cases)\}", text))
        lines = text.count("\\\\") + text.count("\n")
        return min(3.5, max(0.8, 0.8 + max(0, tokens - 8) * 0.12 + fractions * 0.35 + matrices * 0.7 + lines * 0.3))
    return 0.8


def pacing_warnings(result: PacingResult) -> list[Dict[str, Any]]:
    compression = 1.0 - result.duration_scale
    if compression <= 0.2:
        return []
    return [
        {
            "type": "pacing_duration_compression",
            "source_duration": round(result.source_duration, 3),
            "effective_duration": round(result.effective_duration, 3),
            "duration_scale": round(result.duration_scale, 4),
            "compression_ratio": round(compression, 4),
            "blocking": compression > 0.4,
        }
    ]


def build_step_duration_targets(scene: SceneDef, plan: Any = None, storyboard: Any = None) -> Dict[str, Dict[str, Any]]:
    event_durations = {}
    if storyboard:
        event_durations = {
            event.id: float(event.duration_seconds)
            for frame in storyboard.frames
            for event in frame.visual_events
            if event.duration_seconds is not None
        }
    cue_durations = {}
    if plan:
        cue_durations = {cue.id: float(cue.duration_seconds) for cue in plan.narration_cues if cue.duration_seconds is not None}
    targets: Dict[str, Dict[str, Any]] = {}
    for index, step in enumerate(scene.steps):
        if has_explicit_timing(step):
            continue
        step_id = step.id or f"step_{index}"
        if step.storyboard_event_id in event_durations:
            targets[step_id] = {"duration": event_durations[step.storyboard_event_id], "source": "storyboard_event"}
        elif step.narration_cue_id in cue_durations:
            targets[step_id] = {"duration": cue_durations[step.narration_cue_id], "source": "narration_cue"}
    return targets


def timing_alignment_diagnostics(source: SceneDef, pacing: PacingResult, plan: Any = None, storyboard: Any = None) -> Dict[str, Any]:
    storyboard_duration = None
    if storyboard:
        durations = [float(frame.duration_seconds) for frame in storyboard.frames if frame.duration_seconds is not None]
        storyboard_duration = sum(durations) if durations else None
    narration_duration = None
    if plan:
        durations = [float(cue.duration_seconds) for cue in plan.narration_cues if cue.duration_seconds is not None]
        narration_duration = sum(durations) if durations else None
    return {
        "source_duration": round(scene_duration(source), 3),
        "storyboard_duration": round(storyboard_duration, 3) if storyboard_duration is not None else None,
        "narration_duration": round(narration_duration, 3) if narration_duration is not None else None,
        "plan_duration": float(plan.duration_seconds) if plan else None,
        "effective_duration": round(pacing.effective_duration, 3),
    }


def timeline_diagnostics(source: SceneDef, effective: SceneDef) -> list[Dict[str, Any]]:
    source_steps = build_timeline(source)
    effective_steps = build_timeline(effective)
    return [
        {
            "step": effective_step.step_id,
            "step_index": effective_step.step_index,
            "source_duration": round(source_step.duration_seconds, 3),
            "effective_duration": round(effective_step.duration_seconds, 3),
        }
        for source_step, effective_step in zip(source_steps, effective_steps)
    ]


def action_object_ids(step: StepDef) -> set[str]:
    ids: set[str] = set()
    for action in step.actions:
        if isinstance(action.target, str):
            ids.add(action.target)
        elif isinstance(action.target, list):
            ids.update(action.target)
        if action.to:
            ids.add(action.to)
    return ids


def is_formula_object(mob: MobjectDef | None) -> bool:
    return bool(mob and (mob.type == "Tex" or (mob.layout_role or "").startswith("formula.")))


def is_conclusion_object(mob: MobjectDef | None) -> bool:
    return bool(mob and mob.layout_role == "caption.conclusion")


def set_timing(
    action: ActionDef,
    field: str,
    desired: float,
    step: StepDef,
    step_index: int,
    action_index: int,
    changes: list[Dict[str, Any]],
    timing_role: str,
) -> None:
    original = float(getattr(action, field))
    desired = round(desired, 3)
    if math.isclose(original, desired):
        return
    setattr(action, field, desired)
    changes.append(
        {
            "change": "pacing_action_duration",
            "step": step.id or f"step_{step_index}",
            "step_index": step_index,
            "action_index": action_index,
            "action_type": action.type,
            "timing_role": timing_role,
            "field": field,
            "source": round(original, 3),
            "effective": desired,
        }
    )


def has_explicit_timing(step: StepDef) -> bool:
    return step.wait_after is not None or any(action.run_time is not None or action.duration is not None for action in step.actions)


def apply_external_duration_target(
    step: StepDef,
    step_index: int,
    targets: Dict[str, Dict[str, Any]],
    changes: list[Dict[str, Any]],
) -> None:
    step_id = step.id or f"step_{step_index}"
    target = targets.get(step_id)
    if not target:
        return
    current = step_duration(step)
    desired = float(target["duration"])
    if desired <= current:
        return
    extra = desired - current
    step.wait_after = round(float(step.wait_after or 0.0) + extra, 3)
    changes.append(
        {
            "change": "pacing_external_duration",
            "step": step_id,
            "step_index": step_index,
            "source_kind": target["source"],
            "source": round(current, 3),
            "effective": round(desired, 3),
        }
    )
