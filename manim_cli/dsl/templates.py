from __future__ import annotations

from typing import Any, Dict, Optional

from manim_cli.dsl.models import LayoutSpec, MobjectDef, SceneDef


TEMPLATE_ROLE_SLOTS: Dict[str, Dict[str, Optional[str]]] = {
    "plot_full": {
        "plot.axes": "main",
        "plot.primary": "main",
        "plot.annotation": "main",
        "title.primary": "title",
    },
    "plot_with_bottom_formula": {
        "plot.axes": "main",
        "plot.primary": "main",
        "plot.annotation": "main",
        "formula.primary": "bottom_formula",
        "caption.conclusion": "caption",
        "title.primary": "title",
    },
    "plot_with_side_formula": {
        "plot.axes": "left_panel",
        "plot.primary": "left_panel",
        "plot.annotation": "left_panel",
        "formula.primary": "right_panel",
        "formula.secondary": "right_panel",
        "caption.conclusion": "caption",
        "title.primary": "title",
    },
    "formula_then_caption": {
        "plot.axes": "left_panel",
        "plot.primary": "left_panel",
        "plot.annotation": "left_panel",
        "formula.primary": "main",
        "formula.secondary": "main",
        "caption.conclusion": "caption",
        "title.primary": "title",
    },
    "plot_then_formula": {
        "plot.axes": "main",
        "plot.primary": "main",
        "plot.annotation": "main",
        "formula.primary": "bottom_formula",
        "formula.secondary": "bottom_formula",
        "caption.conclusion": "caption",
        "title.primary": "title",
    },
    "vertical_derivation": {
        "formula.primary": "main",
        "formula.secondary": "main",
        "caption.conclusion": "caption",
        "title.primary": "title",
    },
}

FALLBACK_ORDER: Dict[str, tuple[str, ...]] = {
    "plot_with_bottom_formula": ("formula_then_caption", "plot_with_side_formula", "plot_then_formula"),
}

DEFAULT_ROLE_SLOTS: Dict[str, str] = {
    "title.primary": "title",
    "formula.primary": "bottom_formula",
    "formula.secondary": "main",
    "caption.conclusion": "caption",
}

SLOT_TO_ROLE: Dict[str, str] = {
    "title": "title.primary",
    "bottom_formula": "formula.primary",
    "caption": "caption.conclusion",
}


def resolve_layout_roles(scene: SceneDef) -> SceneDef:
    scene = select_layout_fallback(scene)
    mobjects = [resolve_mobject_layout(scene, mob) for mob in scene.mobjects]
    if all(new is old for new, old in zip(mobjects, scene.mobjects)):
        return scene
    return scene.model_copy(update={"mobjects": mobjects})


def select_layout_fallback(scene: SceneDef) -> SceneDef:
    scene._requested_layout_template = scene.layout_template
    scene._layout_fallback_failure = None
    if not scene.layout_template or scene.layout_template not in FALLBACK_ORDER:
        return scene
    formula = primary_formula_for_fallback(scene)
    if not formula or not formula_overflows_slot(scene, formula, scene.layout_template):
        return scene
    attempted = []
    for fallback in FALLBACK_ORDER[scene.layout_template]:
        attempted.append(fallback)
        if not formula_overflows_slot(scene, formula, fallback):
            fallback_scene = scene.model_copy(update={"layout_template": fallback})
            fallback_scene._requested_layout_template = scene.layout_template
            fallback_scene._layout_fallback_failure = None
            return fallback_scene
    scene._layout_fallback_failure = {
        "type": "layout_template_fit_failed",
        "layout_template": scene.layout_template,
        "attempted_fallbacks": attempted,
        "object": formula.id,
        "layout_role": formula.layout_role,
        "reason": "formula_primary_overflow",
    }
    return scene


def primary_formula_for_fallback(scene: SceneDef) -> Optional[MobjectDef]:
    for mob in scene.mobjects:
        if mob.layout_role == "formula.primary" and not mob.layout and not mob.position and mob.type in ("Text", "Tex"):
            return mob
    return None


def formula_overflows_slot(scene: SceneDef, formula: MobjectDef, layout_template: str) -> bool:
    slot = slot_for_role(layout_template, formula.layout_role or "")
    if not slot:
        return True
    try:
        from manim_cli.dsl.layout import estimate_bbox, slot_region

        probe_formula = formula.model_copy(update={"layout": LayoutSpec(slot=slot)})
        box = estimate_bbox(scene, probe_formula, tex_probe_results={})
        region = slot_region(scene, slot)
    except Exception:
        return True
    if not box:
        return True
    return box.width > region.width or box.height > region.height


def resolve_mobject_layout(scene: SceneDef, mob: MobjectDef) -> MobjectDef:
    if mob.layout or mob.position or not mob.layout_role:
        return mob
    slot = slot_for_role(scene.layout_template, mob.layout_role)
    if not slot:
        return mob
    return mob.model_copy(update={"layout": LayoutSpec(slot=slot)})


def slot_for_role(layout_template: Optional[str], layout_role: str) -> Optional[str]:
    if layout_template:
        slot = TEMPLATE_ROLE_SLOTS.get(layout_template, {}).get(layout_role)
        if slot:
            return slot
    return DEFAULT_ROLE_SLOTS.get(layout_role)


def unresolved_layout_role_warnings(scene: SceneDef) -> list[Dict[str, Any]]:
    warnings: list[Dict[str, Any]] = []
    warnings.extend(layout_fallback_warnings(scene))
    for mob in scene.mobjects:
        if not mob.layout_role or mob.layout or mob.position:
            continue
        if slot_for_role(scene.layout_template, mob.layout_role):
            continue
        warnings.append(
            {
                "type": "layout_role_unmapped",
                "object": mob.id,
                "layout_role": mob.layout_role,
                "layout_template": scene.layout_template,
                "message": "layout_role has no deterministic slot mapping for this template",
            }
        )
    return warnings


def layout_fallback_warnings(scene: SceneDef) -> list[Dict[str, Any]]:
    failure = getattr(scene, "_layout_fallback_failure", None)
    if failure:
        return [
            {
                **failure,
                "message": "formula.primary could not fit in the requested template or fallback templates; split the content into separate storyboard steps",
            }
        ]
    requested = requested_layout_template(scene)
    if not requested or requested == scene.layout_template:
        return []
    return [
        {
            "type": "layout_fallback_selected",
            "from": requested,
            "to": scene.layout_template,
            "reason": "formula_primary_overflow",
            "message": "layout_template fallback changed role-derived object placement",
        }
    ]


def layout_template_diagnostics(scene: SceneDef) -> list[Dict[str, Any]]:
    diagnostics: list[Dict[str, Any]] = []
    if scene.layout_template:
        diagnostics.append(
            {
                "change": "layout_template_selected",
                "layout_template": scene.layout_template,
                "requested_layout_template": requested_layout_template(scene),
                "version": scene.version,
            }
        )
    if scene.layout_template and requested_layout_template(scene) != scene.layout_template:
        diagnostics.append(
            {
                "change": "layout_fallback_selected",
                "from": requested_layout_template(scene),
                "to": scene.layout_template,
                "reason": "formula_primary_overflow",
            }
        )
    failure = getattr(scene, "_layout_fallback_failure", None)
    if failure:
        diagnostics.append({"change": "layout_template_fit_failed", **failure})
    for mob in scene.mobjects:
        if not mob.layout_role:
            continue
        mapped_slot = slot_for_role(scene.layout_template, mob.layout_role)
        actual_slot = mob.layout.slot if mob.layout else None
        if mob.position:
            placement_source = "position"
        elif mob.layout:
            placement_source = "layout_slot"
        elif mapped_slot:
            placement_source = "role_mapping_available"
        else:
            placement_source = "unmapped"
        diagnostics.append(
            {
                "object": mob.id,
                "change": "layout_role_placement",
                "layout_template": scene.layout_template,
                "layout_role": mob.layout_role,
                "mapped_slot": mapped_slot,
                "actual_slot": actual_slot,
                "placement_source": placement_source,
            }
        )
    return diagnostics


def requested_layout_template(scene: SceneDef) -> Optional[str]:
    return getattr(scene, "_requested_layout_template", None) or scene.layout_template


def infer_layout_role(mobject: Dict[str, Any]) -> Optional[str]:
    slot = (mobject.get("layout") or {}).get("slot")
    if slot in SLOT_TO_ROLE:
        return SLOT_TO_ROLE[slot]
    if slot in ("main", "custom"):
        mob_type = mobject.get("type")
        if mob_type == "Axes":
            return "plot.axes"
        if mob_type in ("Line", "Dot", "Arrow"):
            return "plot.annotation"
    return None


def infer_layout_template(scene_data: Dict[str, Any]) -> Optional[str]:
    has_axes = any(mobject.get("type") == "Axes" for mobject in scene_data.get("mobjects", []))
    has_bottom_formula = any((mobject.get("layout") or {}).get("slot") == "bottom_formula" for mobject in scene_data.get("mobjects", []))
    if has_axes and has_bottom_formula:
        return "plot_with_bottom_formula"
    return None


def migrate_scene_layout_data(scene_data: Dict[str, Any], to_version: str = "1.1") -> Dict[str, Any]:
    migrated = dict(scene_data)
    migrated["version"] = to_version
    if not migrated.get("layout_template"):
        template = infer_layout_template(migrated)
        if template:
            migrated["layout_template"] = template
    migrated_mobjects = []
    for mobject in migrated.get("mobjects", []):
        migrated_mobject = dict(mobject)
        if not migrated_mobject.get("layout_role"):
            role = infer_layout_role(migrated_mobject)
            if role:
                migrated_mobject["layout_role"] = role
        migrated_mobjects.append(migrated_mobject)
    migrated["mobjects"] = migrated_mobjects
    return migrated
