from __future__ import annotations

from typing import Any, Dict, Iterable, List

from manim_cli.qa.issues import Issue, IssueLocation, RepairHint, Severity


ERROR_IN_STRICT = {
    "layout_out_of_bounds",
    "layout_overlap",
    "layout_custom_region_overflow",
    "math_denominator_zero",
    "math_symbol_type_drift",
    "step_frame_timing_drift",
    "cue_event_timing_drift",
}


def warning_to_issue(warning: Dict[str, Any], profile: str = "relaxed", file: str | None = None) -> Issue:
    warning_type = warning.get("type", "quality_warning")
    severity: Severity = "warning"
    if profile in ("strict", "final") and warning_type in ERROR_IN_STRICT:
        severity = "error"
    if warning_type == "layout_needs_visual_qa":
        severity = "warning"
    objects = warning.get("objects") or ([warning["object"]] if warning.get("object") else [])
    path = warning.get("path")
    repair_scope = "visual_action" if warning_type.startswith("layout_") else "artifact_reference"
    if "timing" in warning_type:
        repair_scope = "cross_track_alignment"
    if warning_type == "math_transform_without_relation":
        repair_scope = "single_action"
    confidence = confidence_for_warning(warning)
    return Issue(
        type=warning_type,
        severity=severity,
        message=message_for_warning(warning),
        location=IssueLocation(
            file=file,
            dsl_path=path,
            step_id=warning.get("step") or warning.get("step_id"),
            object_ids=list(objects),
            narration_cue_id=warning.get("cue_id") or warning.get("narration_cue_id"),
            storyboard_event_id=warning.get("storyboard_event_id") or warning.get("event_id"),
            storyboard_frame_id=warning.get("frame_id"),
        ),
        repair_scope=repair_scope,  # type: ignore[arg-type]
        repair_hints=[RepairHint(repair_hint_for_warning(warning), repair_scope=repair_scope, dsl_path=path, target=target_for_warning(warning))],  # type: ignore[arg-type]
        details={key: value for key, value in warning.items() if key not in {"type", "path"}},
        confidence=confidence,
        source=source_for_warning(warning_type),
    )


def warnings_to_issues(warnings: Iterable[Dict[str, Any]], profile: str = "relaxed", file: str | None = None) -> List[Issue]:
    return [warning_to_issue(warning, profile=profile, file=file) for warning in warnings]


def message_for_warning(warning: Dict[str, Any]) -> str:
    warning_type = warning.get("type", "quality_warning")
    if warning_type == "layout_overlap":
        return f"Visible objects overlap: {', '.join(warning.get('objects', []))}"
    if warning_type == "layout_needs_visual_qa":
        return f"Static bbox is uncertain for possible overlap: {', '.join(warning.get('objects', []))}"
    if warning_type == "layout_out_of_bounds":
        return f"Object is outside the safe frame: {warning.get('object')}"
    if warning_type == "layout_density":
        return f"Too many objects visible in {warning.get('step')}"
    if warning_type == "layout_font_too_small":
        return f"Font size {warning.get('font_size')} is below readability threshold for {warning.get('object')}"
    if warning_type == "step_frame_timing_drift":
        return "Scene step duration drifts from storyboard frame duration"
    if warning_type == "cue_event_timing_drift":
        return "Scene step duration drifts from its narration cue or visual event duration"
    return warning_type.replace("_", " ")


def repair_hint_for_warning(warning: Dict[str, Any]) -> str:
    warning_type = warning.get("type", "quality_warning")
    if warning_type in {"layout_overlap", "layout_needs_visual_qa"}:
        objects = warning.get("objects", [])
        if objects:
            return f"Move one of {objects} to a different layout slot/position, or split the overlapping writes into separate steps."
        return "Move one object to a different layout slot/position, or split the step."
    if warning_type == "layout_out_of_bounds":
        return "Move the object inside the frame safe area, reduce font_size/scale, or assign it to a safer layout slot."
    if warning_type == "layout_custom_region_overflow":
        return "Move the object inside its custom region or enlarge the custom region bounds."
    if warning_type == "layout_density":
        return "Split this step into smaller steps or fade out nonessential objects before adding new ones."
    if warning_type == "layout_font_too_small":
        return "Increase font_size to at least 20 for video readability."
    if warning_type == "step_frame_timing_drift":
        return "Adjust action run_time, wait_after, or the storyboard frame duration for this visual event."
    if warning_type == "cue_event_timing_drift":
        return "Adjust action run_time, wait_after, or the narration cue / visual event duration_seconds so they match."
    if warning_type == "math_denominator_zero":
        return "Change the denominator expression or add a domain restriction before showing this equation."
    if warning_type == "math_undefined_symbol":
        return "Introduce this symbol in an earlier step or add it to the symbol ledger."
    if warning_type == "math_symbol_type_drift":
        return "Make the symbol metadata consistent in the symbol ledger, or use distinct symbols for different types."
    if warning_type == "math_transform_without_relation":
        return "Add a semantic_relation/reason to this transform, or downgrade it to fade_out + write if the two formulas are not logically connected."
    if warning_type.startswith("math_"):
        return "Fix the mathematical expression or symbol metadata at the reported step."
    return "Inspect the reported DSL path and adjust the scene artifact."


def confidence_for_warning(warning: Dict[str, Any]) -> str:
    if warning.get("bbox_confidence"):
        return str(warning["bbox_confidence"])
    warning_type = warning.get("type", "")
    if warning_type in ERROR_IN_STRICT:
        return "high"
    if warning_type == "layout_needs_visual_qa":
        return "unknown_static"
    return "medium"


def source_for_warning(warning_type: str) -> str:
    if warning_type.startswith("layout_"):
        return "layout_static"
    if warning_type.startswith("math_"):
        return "math_lint"
    if "timing" in warning_type:
        return "timing_static"
    if warning_type.startswith(("cue_", "event_", "visual_", "learning_", "symbol_")):
        return "pedagogy_alignment"
    return "qa"


def target_for_warning(warning: Dict[str, Any]) -> str | None:
    if warning.get("object"):
        return str(warning["object"])
    if warning.get("objects"):
        return ",".join(str(item) for item in warning["objects"])
    if warning.get("step") or warning.get("step_id"):
        return str(warning.get("step") or warning.get("step_id"))
    if warning.get("symbol"):
        return str(warning["symbol"])
    return None
