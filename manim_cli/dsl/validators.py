from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import ValidationError

from manim_cli.dsl.encoders import HEX_RE
from manim_cli.dsl.cost import scene_cost
from manim_cli.dsl.knowledge import policy_warnings
from manim_cli.dsl.layout import layout_warnings
from manim_cli.dsl.models import (
    COLORS,
    DIRECTIONS,
    MOBJECT_ARG_MODELS,
    RATE_FUNCS,
    SUPPORTED_ACTIONS,
    SUPPORTED_MOBJECTS,
    ActionDef,
    SceneDef,
)
from manim_cli.dsl.splitting import storyboard_split_plans
from manim_cli.dsl.templates import resolve_layout_roles, unresolved_layout_role_warnings
from manim_cli.jsonio import Diagnostic, error_result, load_json, ok_result
from manim_cli.planning.alignment import alignment_warnings
from manim_cli.planning.pedagogy import load_plan, load_storyboard, pedagogy_warnings


@dataclass
class ParsedSceneValidation:
    diagnostic: Diagnostic
    scene: Optional[SceneDef] = None


def validate_scene_file(path: Path, quality_gate: str = "off") -> Diagnostic:
    try:
        data = load_json(path)
    except Exception as exc:
        return error_result("validate", "invalid_json", str(exc), location={"file": str(path)})
    return validate_scene_data(data, file=str(path), base_dir=path.parent, quality_gate=quality_gate)


def validate_scene_data(data: Any, file: str = "scene.json", base_dir: Optional[Path] = None, quality_gate: str = "off") -> Diagnostic:
    return parse_and_validate_scene_data(data, file=file, base_dir=base_dir, quality_gate=quality_gate).diagnostic


def parse_and_validate_scene_data(data: Any, file: str = "scene.json", base_dir: Optional[Path] = None, quality_gate: str = "off") -> ParsedSceneValidation:
    version_error = validate_versioned_schema_fields(data, file)
    if version_error:
        return ParsedSceneValidation(version_error)
    try:
        scene = SceneDef.model_validate(data)
    except ValidationError as exc:
        return ParsedSceneValidation(validation_error("validate", exc, file))

    semantic = semantic_validate(scene, file=file, base_dir=base_dir)
    if semantic:
        return ParsedSceneValidation(semantic, scene)
    scene = resolve_layout_roles(scene)
    warnings = quality_warnings(scene, base_dir=base_dir, profile=quality_gate) if quality_gate != "off" else []
    if quality_gate in ("strict", "final") and warnings:
        first = warnings[0]
        return ParsedSceneValidation(
            error_result(
                "validate",
                first.get("type", "quality_warning"),
                "Quality gate failed",
                location={"file": file, "warning": first},
                details={"warnings": warnings, "quality_gate": quality_gate},
            ),
            scene,
        )
    result = ok_result("validate", file=file, scene_name=scene.name, cost=scene_cost(scene))
    if quality_gate != "off":
        result["warnings"] = warnings
    return ParsedSceneValidation(result, scene)


def parse_scene_file(path: Path) -> SceneDef:
    return parse_scene_data(load_json(path))


def parse_scene_data(data: Any) -> SceneDef:
    version_error = validate_versioned_schema_fields(data)
    if version_error:
        raise ValueError(version_error["message"])
    return resolve_layout_roles(SceneDef.model_validate(data))


def quality_warnings(scene: SceneDef, base_dir: Optional[Path] = None, profile: str = "relaxed") -> list[Dict[str, Any]]:
    warnings: list[Dict[str, Any]] = []
    warnings.extend(unresolved_layout_role_warnings(scene))
    warnings.extend(storyboard_split_plans(scene))
    warnings.extend(policy_warnings(scene, base_dir, profile=profile))
    warnings.extend(layout_warnings(scene))
    plan = load_plan(base_dir, scene.plan_ref)
    storyboard = load_storyboard(base_dir, scene.storyboard_ref)
    warnings.extend(pedagogy_warnings(scene, plan, storyboard))
    warnings.extend(alignment_warnings(scene, plan, storyboard))
    return warnings


def validate_versioned_schema_fields(data: Any, file: str = "scene.json") -> Optional[Diagnostic]:
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if version == "1.0":
        if "layout_template" in data:
            return error_result(
                "validate",
                "unknown_field",
                "Extra inputs are not permitted",
                location={"file": file, "path": "$.layout_template"},
                details={"field": "layout_template", "version": version},
            )
        for index, mob in enumerate(data.get("mobjects", [])):
            if isinstance(mob, dict) and "layout_role" in mob:
                return error_result(
                    "validate",
                    "unknown_field",
                    "Extra inputs are not permitted",
                    location={"file": file, "path": f"$.mobjects[{index}].layout_role"},
                    details={"field": "layout_role", "version": version},
                )
    return None


def semantic_validate(scene: SceneDef, file: str = "scene.json", base_dir: Optional[Path] = None) -> Optional[Diagnostic]:
    ids: Dict[str, str] = {}
    errors: list[Dict[str, Any]] = []
    for index, mob in enumerate(scene.mobjects):
        path = f"$.mobjects[{index}]"
        if mob.id in ids:
            errors.append(error_item("duplicate_id", f"Duplicate mobject id {mob.id!r}", file, path))
            continue
        ids[mob.id] = mob.type
        if mob.type not in SUPPORTED_MOBJECTS:
            errors.append(error_item(
                "unsupported_type",
                f"Unsupported mobject type {mob.type!r}",
                file,
                f"{path}.type",
                suggestions=["Use one of the MVP mobject types from manim-cli manifest."],
            ))
            continue
        try:
            MOBJECT_ARG_MODELS[mob.type].model_validate(mob.args)
        except ValidationError as exc:
            errors.extend(validation_error_items(exc, file, prefix=f"{path}.args"))
        if mob.style:
            style_error = validate_style(mob.style.model_dump(exclude_none=True), file, f"{path}.style")
            if style_error:
                errors.append(diagnostic_to_error(style_error))
        if mob.position:
            pos_error = validate_position(mob.position, ids, file, f"{path}.position")
            if pos_error:
                errors.append(diagnostic_to_error(pos_error))
        if mob.layout and mob.position:
            errors.append(error_item(
                "unsupported_combination",
                "mobject cannot specify both position and layout",
                file,
                path,
            ))
        coord_error = validate_coordinate_args(mob.type, mob.args, ids, file, path)
        if coord_error:
            errors.append(diagnostic_to_error(coord_error))

    for step_index, step in enumerate(scene.steps):
        for action_index, action in enumerate(step.actions):
            path = f"$.steps[{step_index}].actions[{action_index}]"
            action_error = validate_action(action, ids, file, path)
            if action_error:
                errors.append(diagnostic_to_error(action_error))

    if base_dir:
        for attr in ("plan_ref", "storyboard_ref"):
            ref = getattr(scene, attr)
            if ref and not (base_dir / ref).exists():
                errors.append(error_item(
                    "missing_reference",
                    f"{attr} file does not exist: {ref}",
                    file,
                    f"$.{attr}",
                ))
    if errors:
        first = errors[0]
        return error_result(
            "validate",
            first["error_type"],
            first["message"],
            location=first.get("location"),
            suggestions=first.get("suggestions"),
            details={"errors": errors},
        )
    return None


def validation_error(phase: str, exc: ValidationError, file: str, prefix: str = "$") -> Diagnostic:
    errors = validation_error_items(exc, file, prefix)
    first = errors[0]
    return error_result(
        phase,
        first["error_type"],
        first["message"],
        location=first["location"],
        details={"errors": errors, "pydantic_errors": exc.errors()},
    )


def validation_error_items(exc: ValidationError, file: str, prefix: str = "$") -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        path = prefix if not loc else f"{prefix}.{loc}"
        error_type = "unknown_field" if error.get("type") in ("value_error.extra", "extra_forbidden") else "invalid_type"
        if error.get("type") in ("value_error.missing", "missing"):
            error_type = "missing_required_field"
        if "unexpected value" in error.get("msg", "") or error.get("type") == "literal_error":
            error_type = "invalid_enum"
        items.append(error_item(error_type, error.get("msg", str(exc)), file, path, details=error))
    return items


def error_item(error_type: str, message: str, file: str, path: str, suggestions: Optional[list[str]] = None, details: Optional[Any] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"error_type": error_type, "message": message, "location": {"file": file, "path": path}}
    if suggestions:
        item["suggestions"] = suggestions
    if details is not None:
        item["details"] = details
    return item


def diagnostic_to_error(diagnostic: Diagnostic) -> Dict[str, Any]:
    item = {
        "error_type": diagnostic.get("error_type", "validation_error"),
        "message": diagnostic.get("message", "Validation failed"),
        "location": diagnostic.get("location", {}),
    }
    if diagnostic.get("suggestions"):
        item["suggestions"] = diagnostic["suggestions"]
    if "details" in diagnostic:
        item["details"] = diagnostic["details"]
    return item


def validate_style(style: Dict[str, Any], file: str, path: str) -> Optional[Diagnostic]:
    for key in ("color", "fill_color", "stroke_color"):
        value = style.get(key)
        if value and not (value in COLORS or HEX_RE.match(value)):
            return error_result("validate", "invalid_enum", f"Unsupported color {value!r}", location={"file": file, "path": f"{path}.{key}"})
    return None


def validate_position(position: Any, ids: Dict[str, str], file: str, path: str) -> Optional[Diagnostic]:
    if position.mode == "absolute":
        return validate_point(position.point, file, f"{path}.point")
    if position.mode == "edge":
        if not position.edge or position.edge not in DIRECTIONS:
            return error_result("validate", "invalid_enum", "edge must be a supported direction", location={"file": file, "path": f"{path}.edge"})
    if position.mode == "relative":
        if not position.target or position.target not in ids:
            return error_result("validate", "undefined_target", f"Unknown position target {position.target!r}", location={"file": file, "path": f"{path}.target"})
        if not position.direction or position.direction not in DIRECTIONS:
            return error_result("validate", "invalid_enum", "direction must be a supported direction", location={"file": file, "path": f"{path}.direction"})
    if position.mode == "align_to":
        if not position.target or position.target not in ids:
            return error_result("validate", "undefined_target", f"Unknown align target {position.target!r}", location={"file": file, "path": f"{path}.target"})
        if not position.edge or position.edge not in DIRECTIONS:
            return error_result("validate", "invalid_enum", "edge must be a supported direction", location={"file": file, "path": f"{path}.edge"})
    return None


def validate_coordinate_args(mob_type: str, args: Dict[str, Any], ids: Dict[str, str], file: str, path: str) -> Optional[Diagnostic]:
    for field in ("start", "end", "point"):
        if field in args:
            point_error = validate_point(args[field], file, f"{path}.args.{field}")
            if point_error:
                return point_error
    if args.get("coordinate_space") == "plane":
        axes = args.get("axes")
        if not axes or axes not in ids:
            return error_result("validate", "undefined_target", "plane coordinate_space requires an existing axes id", location={"file": file, "path": f"{path}.args.axes"})
        if ids[axes] != "Axes":
            return error_result("validate", "invalid_type", "plane coordinate_space axes must reference an Axes mobject", location={"file": file, "path": f"{path}.args.axes"})
    return None


def validate_point(point: Any, file: str, path: str) -> Optional[Diagnostic]:
    if not isinstance(point, list) or len(point) not in (2, 3):
        return error_result("validate", "invalid_type", "Coordinate must be a 2D or 3D array", location={"file": file, "path": path})
    for value in point:
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return error_result("validate", "invalid_type", "Coordinate values must be finite numbers", location={"file": file, "path": path})
    return None


def validate_action(action: ActionDef, ids: Dict[str, str], file: str, path: str) -> Optional[Diagnostic]:
    if action.type not in SUPPORTED_ACTIONS:
        return error_result("validate", "unsupported_action", f"Unsupported action type {action.type!r}", location={"file": file, "path": f"{path}.type"})
    if isinstance(action.target, list):
        return error_result("validate", "unsupported_combination", "MVP actions only accept a single target id", location={"file": file, "path": f"{path}.target"})
    params_error = validate_action_params(action, file, path)
    if params_error:
        return params_error
    if action.type == "wait":
        if action.duration is None:
            return error_result("validate", "missing_required_field", "wait requires duration", location={"file": file, "path": f"{path}.duration"})
        return None
    if not action.target or action.target not in ids:
        return error_result("validate", "undefined_target", f"Unknown action target {action.target!r}", location={"file": file, "path": f"{path}.target"})
    if action.type in ("add", "remove") and action.run_time is not None:
        return error_result("validate", "unsupported_combination", f"{action.type} does not accept run_time", location={"file": file, "path": f"{path}.run_time"})
    if action.type == "transform" and (not action.to or action.to not in ids):
        return error_result("validate", "undefined_target", f"Unknown transform target {action.to!r}", location={"file": file, "path": f"{path}.to"})
    if action.type == "layout" and not action.slot:
        return error_result("validate", "missing_required_field", "layout requires slot", location={"file": file, "path": f"{path}.slot"})
    if action.type == "layout" and action.slot == "custom" and not action.region:
        return error_result("validate", "missing_required_field", "custom layout action requires region", location={"file": file, "path": f"{path}.region"})
    if action.rate_func is not None and action.rate_func not in RATE_FUNCS:
        return error_result("validate", "invalid_enum", f"Unsupported rate_func {action.rate_func!r}", location={"file": file, "path": f"{path}.rate_func"})
    if action.color and not (action.color in COLORS or HEX_RE.match(action.color)):
        return error_result("validate", "invalid_enum", f"Unsupported color {action.color!r}", location={"file": file, "path": f"{path}.color"})
    return None


def validate_action_params(action: ActionDef, file: str, path: str) -> Optional[Diagnostic]:
    populated = {
        key
        for key, value in action.model_dump(exclude_none=True).items()
        if not (key == "match_by" and value == "none")
    }
    allowed = {
        "add": {"type", "target"},
        "remove": {"type", "target"},
        "write": {"type", "target", "run_time", "rate_func"},
        "fade_in": {"type", "target", "run_time", "rate_func"},
        "fade_out": {"type", "target", "run_time", "rate_func"},
        "show_creation": {"type", "target", "run_time", "rate_func"},
        "transform": {"type", "target", "to", "run_time", "rate_func", "match_by", "semantic_relation", "reason"},
        "highlight": {"type", "target", "color", "run_time", "rate_func"},
        "wait": {"type", "duration"},
        "layout": {"type", "target", "slot", "region", "run_time", "rate_func"},
    }[action.type]
    allowed.add("timing_role")
    extra = sorted(populated - allowed)
    if extra:
        field = extra[0]
        return error_result(
            "validate",
            "unsupported_combination",
            f"{action.type} does not accept {field}",
            location={"file": file, "path": f"{path}.{field}"},
        )
    return None
