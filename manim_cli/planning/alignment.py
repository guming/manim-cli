from __future__ import annotations

from typing import Any, Dict, List, Optional

from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.timeline import build_timeline
from manim_cli.planning.models import Storyboard, TeachingPlan


def alignment_warnings(scene: SceneDef, plan: Optional[TeachingPlan], storyboard: Optional[Storyboard]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    cue_ids = {cue.id for cue in plan.narration_cues} if plan else set()
    event_ids = {event.id for frame in storyboard.frames for event in frame.visual_events} if storyboard else set()
    step_cues = {step.narration_cue_id for step in scene.steps if step.narration_cue_id}
    step_events = {step.storyboard_event_id for step in scene.steps if step.storyboard_event_id}

    for cue_id in sorted(cue_ids - step_cues):
        warnings.append({"type": "cue_without_scene_step", "cue_id": cue_id})
    for event_id in sorted(event_ids - step_events):
        warnings.append({"type": "event_without_scene_step", "storyboard_event_id": event_id})
    for step_index, step in enumerate(scene.steps):
        if step.narration_cue_id and cue_ids and step.narration_cue_id not in cue_ids:
            warnings.append({"type": "undefined_narration_cue", "step": step.id or step.name, "cue_id": step.narration_cue_id, "path": f"$.steps[{step_index}].narration_cue_id"})
        if step.storyboard_event_id and event_ids and step.storyboard_event_id not in event_ids:
            warnings.append({"type": "undefined_storyboard_event", "step": step.id or step.name, "storyboard_event_id": step.storyboard_event_id, "path": f"$.steps[{step_index}].storyboard_event_id"})

    if storyboard:
        object_ids = {mob.id for mob in scene.mobjects}
        for frame in storyboard.frames:
            for event in frame.visual_events:
                for focus in event.focus:
                    if focus not in object_ids:
                        warnings.append({"type": "visual_focus_not_implemented", "frame_id": frame.id, "event_id": event.id, "focus": focus})

    timeline = build_timeline(scene)
    visible_by_event = {scene_step.storyboard_event_id: timeline_step.visible_after for timeline_step, scene_step in zip(timeline, scene.steps) if scene_step.storyboard_event_id}
    if storyboard:
        for frame in storyboard.frames:
            for event in frame.visual_events:
                visible = visible_by_event.get(event.id, set())
                for focus in event.focus:
                    if focus and focus not in visible:
                        warnings.append({"type": "visual_focus_not_visible", "event_id": event.id, "focus": focus})
    return warnings
