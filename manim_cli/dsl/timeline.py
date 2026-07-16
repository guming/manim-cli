from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Set

from manim_cli.dsl.models import SceneDef


VISIBLE_ACTIONS = {"add", "write", "fade_in", "show_creation"}
HIDDEN_ACTIONS = {"remove", "fade_out"}


@dataclass
class TimelineStep:
    step_index: int
    step_id: str
    step_name: str
    visible_before: Set[str]
    visible_after: Set[str]
    entered: Set[str]
    exited: Set[str]
    transformed: Set[str]
    duration_seconds: float


def build_timeline(scene: SceneDef) -> List[TimelineStep]:
    visible: Set[str] = set()
    result: List[TimelineStep] = []
    for index, step in enumerate(scene.steps):
        before = set(visible)
        entered: Set[str] = set()
        exited: Set[str] = set()
        transformed: Set[str] = set()
        for action in step.actions:
            if isinstance(action.target, list) or not action.target:
                continue
            target = action.target
            if action.type in VISIBLE_ACTIONS:
                if target not in visible:
                    entered.add(target)
                visible.add(target)
            elif action.type in HIDDEN_ACTIONS:
                if target in visible:
                    exited.add(target)
                visible.discard(target)
            elif action.type == "transform":
                transformed.add(target)
                visible.add(target)
        result.append(
            TimelineStep(
                step_index=index,
                step_id=step.id or f"step_{index}",
                step_name=step.name,
                visible_before=before,
                visible_after=set(visible),
                entered=entered,
                exited=exited,
                transformed=transformed,
                duration_seconds=step_duration(step),
            )
        )
    return result


def action_duration(action: object) -> float:
    action_type = getattr(action, "type", None)
    if action_type == "wait":
        return float(getattr(action, "duration", None) or 0.0)
    if action_type in {"write", "fade_in", "fade_out", "show_creation", "transform", "highlight", "layout"}:
        return float(getattr(action, "run_time", None) or 1.0)
    return 0.0


def step_duration(step: object) -> float:
    actions = getattr(step, "actions", []) or []
    duration = sum(max((action_duration(action) for action in group), default=0.0) for group in action_groups(actions))
    wait_after = getattr(step, "wait_after", None)
    if wait_after is not None:
        duration += float(wait_after)
    return duration


def action_groups(actions: List[Any]) -> List[List[Any]]:
    groups: List[List[Any]] = []
    index = 0
    mergeable = {"write", "fade_in", "fade_out", "show_creation"}
    while index < len(actions):
        first = actions[index]
        group = [first]
        if (
            getattr(first, "type", None) in mergeable
            and getattr(first, "target", None)
            and not isinstance(getattr(first, "target", None), list)
        ):
            for candidate in actions[index + 1 :]:
                if (
                    getattr(candidate, "type", None) == getattr(first, "type", None)
                    and getattr(candidate, "run_time", None) == getattr(first, "run_time", None)
                    and getattr(candidate, "rate_func", None) == getattr(first, "rate_func", None)
                    and getattr(candidate, "target", None)
                    and not isinstance(getattr(candidate, "target", None), list)
                ):
                    group.append(candidate)
                else:
                    break
        groups.append(group)
        index += len(group)
    return groups
