from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from manim_cli.dsl.models import SceneDef
from manim_cli.planning.models import TeachingPlan


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|[α-ωΑ-Ω]")


def math_warnings(scene: SceneDef, plan: Optional[TeachingPlan]) -> List[Dict[str, object]]:
    warnings: List[Dict[str, object]] = []
    warnings.extend(denominator_zero_warnings(scene))
    warnings.extend(undefined_symbol_warnings(scene, plan))
    warnings.extend(symbol_type_drift_warnings(plan))
    warnings.extend(transform_without_relation_warnings(scene))
    return warnings


def transform_without_relation_warnings(scene: SceneDef) -> List[Dict[str, object]]:
    # P0 math lint (PRD §8.4.3): a Tex/MathTex transform without semantic_relation
    # or reason is structurally unexplained and a common source of teaching errors.
    # Relaxed profile warns; strict/final may escalate via the issue adapter.
    tex_types = {"Tex"}
    warnings: List[Dict[str, object]] = []
    tex_ids = {mob.id for mob in scene.mobjects if mob.type in tex_types}
    for step_index, step in enumerate(scene.steps):
        for action_index, action in enumerate(step.actions):
            if action.type != "transform":
                continue
            target = action.target if not isinstance(action.target, list) else None
            if target not in tex_ids and action.to not in tex_ids:
                continue
            if action.semantic_relation or action.reason:
                continue
            warnings.append(
                {
                    "type": "math_transform_without_relation",
                    "step": step.id or f"step_{step_index}",
                    "step_index": step_index,
                    "action_index": action_index,
                    "target": target,
                    "to": action.to,
                    "path": f"$.steps[{step_index}].actions[{action_index}]",
                }
            )
    return warnings


def denominator_zero_warnings(scene: SceneDef) -> List[Dict[str, object]]:
    assignments = collect_assignments(scene)
    warnings: List[Dict[str, object]] = []
    frac_pattern = re.compile(r"\\frac\{[^{}]+\}\{\s*([A-Za-z])\s*([-+])\s*([0-9]+)\s*\}")
    for mob in scene.mobjects:
        text = str(mob.args.get("tex") or mob.args.get("text") or "")
        for symbol, op, raw_number in frac_pattern.findall(text):
            number = float(raw_number)
            zero_value = number if op == "-" else -number
            if assignments.get(symbol) == zero_value:
                warnings.append(
                    {
                        "type": "math_denominator_zero",
                        "object": mob.id,
                        "symbol": symbol,
                        "value": zero_value,
                        "path": f"$.mobjects[{scene.mobjects.index(mob)}].args",
                    }
                )
    return warnings


def collect_assignments(scene: SceneDef) -> Dict[str, float]:
    assignments: Dict[str, float] = {}
    pattern = re.compile(r"\b([A-Za-z])\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\b")
    for mob in scene.mobjects:
        text = str(mob.args.get("tex") or mob.args.get("text") or "")
        for symbol, value in pattern.findall(text):
            assignments[symbol] = float(value)
    return assignments


def undefined_symbol_warnings(scene: SceneDef, plan: Optional[TeachingPlan]) -> List[Dict[str, object]]:
    if not plan or not plan.symbol_ledger:
        return []
    ledger_symbols = {item.symbol for item in plan.symbol_ledger}
    aliases = {alias for item in plan.symbol_ledger for alias in item.aliases}
    canonical = {item.canonical_tex for item in plan.symbol_ledger if item.canonical_tex}
    allowed = ledger_symbols | aliases | canonical
    introduced: Set[str] = set()
    warnings: List[Dict[str, object]] = []
    for step_index, step in enumerate(scene.steps):
        step_objects = {action.target for action in step.actions if action.target and not isinstance(action.target, list)}
        for mob in scene.mobjects:
            if mob.id not in step_objects:
                continue
            for token in TOKEN_RE.findall(str(mob.args.get("tex") or mob.args.get("text") or "")):
                if len(token) != 1:
                    continue
                if token not in allowed and token not in introduced:
                    warnings.append({"type": "math_undefined_symbol", "symbol": token, "object": mob.id, "step": step.id or f"step_{step_index}", "path": f"$.steps[{step_index}]"})
                introduced.add(token)
    return warnings


def symbol_type_drift_warnings(plan: Optional[TeachingPlan]) -> List[Dict[str, object]]:
    if not plan:
        return []
    seen: Dict[str, tuple[Optional[str], Optional[str], Optional[str]]] = {}
    warnings: List[Dict[str, object]] = []
    for item in plan.symbol_ledger:
        signature = (item.symbol_type, item.domain, item.shape)
        if item.symbol in seen and seen[item.symbol] != signature:
            warnings.append({"type": "math_symbol_type_drift", "symbol": item.symbol, "previous": seen[item.symbol], "current": signature})
        seen[item.symbol] = signature
    return warnings
