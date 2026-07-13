from __future__ import annotations

from typing import Any, Dict

from manim_cli.dsl.models import SceneDef


def scene_cost(scene: SceneDef) -> Dict[str, Any]:
    action_count = 0
    total_run_time = 0.0
    total_wait = 0.0
    tex_count = 0
    text_count = 0
    tex_complexity_warnings = []

    for mob in scene.mobjects:
        if mob.type == "Tex":
            tex_count += 1
            tex = str(mob.args.get("tex", ""))
            score = len(tex) + tex.count("\\") * 3 + tex.count("begin") * 10
            if score > 120:
                tex_complexity_warnings.append({"id": mob.id, "score": score})
        elif mob.type == "Text":
            text_count += 1

    for step in scene.steps:
        action_count += len(step.actions)
        if step.wait_after:
            total_wait += float(step.wait_after)
        for action in step.actions:
            if action.run_time:
                total_run_time += float(action.run_time)
            if action.type == "wait" and action.duration:
                total_wait += float(action.duration)

    render_cost_score = action_count + tex_count * 5 + text_count * 2 + int(total_run_time + total_wait)
    return {
        "mobject_count": len(scene.mobjects),
        "step_count": len(scene.steps),
        "action_count": action_count,
        "tex_count": tex_count,
        "text_count": text_count,
        "total_run_time": round(total_run_time, 3),
        "total_wait": round(total_wait, 3),
        "render_cost_score": render_cost_score,
        "tex_complexity_warnings": tex_complexity_warnings,
    }
