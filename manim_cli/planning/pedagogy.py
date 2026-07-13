from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.models import COLORS
from manim_cli.jsonio import load_json
from manim_cli.planning.models import Storyboard, TeachingPlan


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|[α-ωΑ-Ω]")


def load_plan(base_dir: Optional[Path], ref: Optional[str]) -> Optional[TeachingPlan]:
    if not base_dir or not ref:
        return None
    path = base_dir / ref
    if not path.exists():
        return None
    return TeachingPlan.model_validate(load_json(path))


def load_storyboard(base_dir: Optional[Path], ref: Optional[str]) -> Optional[Storyboard]:
    if not base_dir or not ref:
        return None
    path = base_dir / ref
    if not path.exists():
        return None
    return Storyboard.model_validate(load_json(path))


def pedagogy_warnings(scene: SceneDef, plan: Optional[TeachingPlan], storyboard: Optional[Storyboard]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    if plan:
        warnings.extend(symbol_warnings(scene, plan))
    if plan and storyboard:
        warnings.extend(goal_coverage_warnings(plan, storyboard, scene))
    return warnings


def symbol_warnings(scene: SceneDef, plan: TeachingPlan) -> List[Dict[str, Any]]:
    ledger = {item.symbol: item for item in plan.symbol_ledger}
    canonical = {item.canonical_tex: item.symbol for item in plan.symbol_ledger if item.canonical_tex}
    color_roles = {item.symbol: item.color_role for item in plan.symbol_ledger if item.color_role}
    warnings: List[Dict[str, Any]] = []

    scene_symbols: Dict[str, List[str]] = {}
    for mob in scene.mobjects:
        text = str(mob.args.get("tex") or mob.args.get("text") or "")
        for token in TOKEN_RE.findall(text):
            if len(token) == 1 or token in ledger or token in canonical:
                scene_symbols.setdefault(token, []).append(mob.id)
        if mob.style and mob.style.color:
            for token in TOKEN_RE.findall(text):
                symbol = canonical.get(token, token)
                expected_role = color_roles.get(symbol)
                if expected_role and (expected_role in COLORS or expected_role.startswith("#")) and mob.style.color != expected_role:
                    warnings.append({"type": "symbol_color_role_mismatch", "symbol": symbol, "object": mob.id, "color": mob.style.color, "expected": expected_role})

    for token, object_ids in sorted(scene_symbols.items()):
        if token not in ledger and token not in canonical:
            warnings.append({"type": "symbol_not_in_ledger", "symbol": token, "objects": object_ids})

    for symbol, item in ledger.items():
        if item.canonical_tex and symbol in scene_symbols and item.canonical_tex != symbol:
            warnings.append({"type": "symbol_canonical_tex_mismatch", "symbol": symbol, "canonical_tex": item.canonical_tex, "objects": scene_symbols[symbol]})
    return warnings


def goal_coverage_warnings(plan: TeachingPlan, storyboard: Storyboard, scene: SceneDef) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    searchable_frames = " ".join(
        [
            " ".join(
                [
                    frame.section or "",
                    frame.input_goal or "",
                    " ".join(event.intent for event in frame.visual_events),
                    " ".join(frame.mathematical_derivation),
                ]
            )
            for frame in storyboard.frames
        ]
    ).lower()
    searchable_steps = " ".join([step.name + " " + (step.comment or "") for step in scene.steps]).lower()
    for goal in plan.learning_goals:
        terms = [term.lower() for term in TOKEN_RE.findall(goal) if len(term) > 3]
        if terms and not any(term in searchable_frames or term in searchable_steps for term in terms):
            warnings.append({"type": "learning_goal_not_covered", "goal": goal})
    return warnings
