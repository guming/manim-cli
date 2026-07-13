from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, ValidationError

from manim_cli.dsl.validators import validation_error
from manim_cli.jsonio import Diagnostic, load_json, ok_result
from manim_cli.planning.alignment import alignment_warnings
from manim_cli.planning.models import Storyboard, TeachingPlan


def validate_plan_file(path: Path) -> Diagnostic:
    result = validate_model_file(path, TeachingPlan, "plan")
    if not result.get("ok"):
        return result
    plan = TeachingPlan.model_validate(load_json(path))
    return ok_result("plan", file=str(path), id=plan.id, warnings=[])


def validate_storyboard_file(path: Path) -> Diagnostic:
    result = validate_model_file(path, Storyboard, "storyboard")
    if not result.get("ok"):
        return result
    storyboard = Storyboard.model_validate(load_json(path))
    warnings = alignment_warnings(scene=_empty_scene(), plan=None, storyboard=storyboard)
    return ok_result("storyboard", file=str(path), id=storyboard.id, warnings=warnings)


def validate_model_file(path: Path, model: Type[BaseModel], phase: str) -> Diagnostic:
    try:
        data = load_json(path)
        parsed = model.model_validate(data)
    except ValidationError as exc:
        return validation_error(phase, exc, str(path))
    except Exception as exc:
        from manim_cli.jsonio import error_result

        return error_result(phase, "invalid_json", str(exc), location={"file": str(path)})
    return ok_result(phase, file=str(path), id=getattr(parsed, "id", None))


def _empty_scene():
    from manim_cli.dsl.models import SceneConfig, SceneDef

    return SceneDef(version="1.0", name="empty", config=SceneConfig(), mobjects=[], steps=[])
