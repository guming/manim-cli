"""Scene analysis: the lowered view over a SceneDef.

Design rule: the compiler has exactly two tiers.
- AST  = SceneDef (the Pydantic scene model, validated against the DSL schema).
- View = SceneAnalysis (timeline, step durations, object lifetimes, visible
  sets, bbox estimates, layout plan), derived deterministically from SceneDef.

Codegen emits directly from SceneDef in a single pass. Do NOT introduce a
parallel lowered IR layer. Any future optimization that needs per-object
scheduling (e.g. first-use delayed creation) must derive from
``SceneAnalysis.object_lifetimes`` rather than re-lowering the scene.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

from manim_cli.dsl.layout import BBoxEstimate, estimate_bboxes
from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.timeline import TimelineStep, build_timeline


@dataclass(frozen=True)
class ObjectLifetime:
    object_id: str
    first_step: int | None
    last_step: int | None
    visible_steps: List[int]


@dataclass(frozen=True)
class SceneAnalysis:
    scene: SceneDef
    timeline: List[TimelineStep]
    step_durations: Dict[str, float]
    object_lifetimes: Dict[str, ObjectLifetime]
    visible_sets: Dict[str, Set[str]]
    bbox_estimates: Dict[str, BBoxEstimate]
    layout_plan: Dict[str, str]


def analyze_scene(scene: SceneDef) -> SceneAnalysis:
    timeline = build_timeline(scene)
    step_durations = {step.step_id: step.duration_seconds for step in timeline}
    visible_sets = {step.step_id: set(step.visible_after) for step in timeline}
    bbox_estimates = estimate_bboxes(scene)
    layout_plan = {mob.id: mob.layout.slot for mob in scene.mobjects if mob.layout}
    return SceneAnalysis(
        scene=scene,
        timeline=timeline,
        step_durations=step_durations,
        object_lifetimes=object_lifetimes(scene, timeline),
        visible_sets=visible_sets,
        bbox_estimates=bbox_estimates,
        layout_plan=layout_plan,
    )


def object_lifetimes(scene: SceneDef, timeline: List[TimelineStep]) -> Dict[str, ObjectLifetime]:
    result: Dict[str, ObjectLifetime] = {}
    for mob in scene.mobjects:
        visible_steps = [step.step_index for step in timeline if mob.id in step.visible_after]
        first = visible_steps[0] if visible_steps else None
        last = visible_steps[-1] if visible_steps else None
        result[mob.id] = ObjectLifetime(mob.id, first, last, visible_steps)
    return result
