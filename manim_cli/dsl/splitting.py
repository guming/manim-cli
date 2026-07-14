from __future__ import annotations

from typing import Any, Dict, List, Optional

from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.timeline import build_timeline


def storyboard_split_plans(scene: SceneDef) -> List[Dict[str, Any]]:
    failure = getattr(scene, "_layout_fallback_failure", None)
    if not failure:
        return []
    target = failure.get("object")
    if not target:
        return []
    caption_ids = [mob.id for mob in scene.mobjects if mob.layout_role == "caption.conclusion"]
    formula_ids = [mob.id for mob in scene.mobjects if mob.layout_role in ("formula.primary", "formula.secondary")]
    moved_ids = sorted(set(caption_ids or formula_ids))
    if target not in moved_ids:
        moved_ids.append(target)
        moved_ids = sorted(set(moved_ids))
    plans: List[Dict[str, Any]] = []
    for step in build_timeline(scene):
        if target not in step.visible_after and target not in step.entered:
            continue
        plans.append(
            {
                "type": "storyboard_split_required",
                "step": step.step_id,
                "step_index": step.step_index,
                "reason": failure.get("reason", "layout_template_fit_failed"),
                "source_layout_template": failure.get("layout_template"),
                "attempted_fallbacks": failure.get("attempted_fallbacks", []),
                "moved_object_ids": moved_ids,
                "timing_policy": "preserve_original_step_duration_until_explicit_split",
                "message": "Split formula/caption content into a separate storyboard step before rendering.",
            }
        )
        break
    return plans


def apply_first_storyboard_split(scene_data: Dict[str, Any], plans: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not plans:
        return None
    plan = plans[0]
    steps = list(scene_data.get("steps", []))
    step_index = plan.get("step_index")
    if not isinstance(step_index, int) or step_index < 0 or step_index >= len(steps):
        return None
    source_step = dict(steps[step_index])
    actions = list(source_step.get("actions", []))
    if not actions:
        return None
    split_targets = split_target_ids(scene_data, plan)
    if not split_targets:
        return None
    kept_actions = []
    moved_actions = []
    for action in actions:
        target = action.get("target") if isinstance(action, dict) else None
        if target in split_targets:
            moved_actions.append(action)
        else:
            kept_actions.append(action)
    if not moved_actions or not kept_actions:
        return None
    original_wait_after = source_step.pop("wait_after", None)
    source_step["actions"] = kept_actions
    source_step["comment"] = append_comment(source_step.get("comment"), "layout split applied: kept non-caption actions in original step")
    new_step = {
        "id": f"{source_step.get('id') or plan.get('step')}_layout_split",
        "name": f"{source_step.get('name', 'step')} layout split",
        "actions": moved_actions,
        "comment": "layout split applied: moved caption/formula overflow actions from previous step",
    }
    if original_wait_after is not None:
        new_step["wait_after"] = original_wait_after
    for key in ("narration_cue_id", "storyboard_event_id"):
        if source_step.get(key):
            new_step[key] = source_step[key]
    new_steps = steps[:step_index] + [source_step, new_step] + steps[step_index + 1 :]
    result = dict(scene_data)
    result["steps"] = new_steps
    return result


def split_target_ids(scene_data: Dict[str, Any], plan: Dict[str, Any]) -> set[str]:
    mobjects = scene_data.get("mobjects", [])
    caption_ids = {mob.get("id") for mob in mobjects if isinstance(mob, dict) and mob.get("layout_role") == "caption.conclusion"}
    caption_ids = {mob_id for mob_id in caption_ids if isinstance(mob_id, str)}
    plan_ids = {mob_id for mob_id in plan.get("moved_object_ids", []) if isinstance(mob_id, str)}
    return caption_ids & plan_ids or plan_ids


def append_comment(existing: Any, extra: str) -> str:
    if not existing:
        return extra
    return f"{existing}; {extra}"
