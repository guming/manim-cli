from __future__ import annotations

from typing import Any

from manim_cli.dsl.models import SceneDef


def optimize_scene(scene: SceneDef, profile: str) -> SceneDef:
    if profile not in ("preview", "fast"):
        return scene
    optimized = scene.model_copy(deep=True)
    for step in optimized.steps:
        step.actions = merge_wait_actions(step.actions)
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
