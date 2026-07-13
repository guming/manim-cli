from __future__ import annotations

from typing import Any

from manim_cli.dsl.models import SceneDef


def optimize_scene(scene: SceneDef, profile: str) -> SceneDef:
    if profile not in ("preview", "fast"):
        return scene
    optimized = scene.model_copy(deep=True)
    for step in optimized.steps:
        step.actions = merge_wait_actions(step.actions)
        if step.wait_after is not None:
            step.wait_after = min(float(step.wait_after), 0.2)
        for action in step.actions:
            if action.run_time is not None:
                action.run_time = preview_duration(float(action.run_time))
            if action.type == "wait" and action.duration is not None:
                action.duration = min(float(action.duration), 0.2)
    return optimized


MERGEABLE_ACTIONS = {"write": "Write", "fade_in": "FadeIn", "fade_out": "FadeOut", "show_creation": "Create"}


def collect_mergeable_actions(actions: list[Any], start: int) -> list[Any]:
    first = actions[start]
    if first.type not in MERGEABLE_ACTIONS or not first.target or isinstance(first.target, list):
        return [first]
    group = [first]
    for action in actions[start + 1 :]:
        if (
            action.type == first.type
            and action.run_time == first.run_time
            and action.rate_func == first.rate_func
            and action.target
            and not isinstance(action.target, list)
        ):
            group.append(action)
        else:
            break
    return group


def merge_wait_actions(actions: list[Any]) -> list[Any]:
    merged: list[Any] = []
    for action in actions:
        if action.type == "wait" and merged and merged[-1].type == "wait":
            merged[-1].duration = float(merged[-1].duration or 0.0) + float(action.duration or 0.0)
        else:
            merged.append(action)
    return merged


def preview_duration(duration: float) -> float:
    return min(duration, max(0.5, duration * 0.3))
