from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from manim_cli.dsl.models import MobjectDef, SceneDef
from manim_cli.dsl.timeline import build_timeline


@dataclass(frozen=True)
class BBox:
    left: float
    bottom: float
    right: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


Confidence = Literal["high", "medium", "unknown_static"]


@dataclass(frozen=True)
class BBoxEstimate:
    bbox: BBox
    confidence: Confidence
    method: str

    @property
    def width(self) -> float:
        return self.bbox.width

    @property
    def height(self) -> float:
        return self.bbox.height


def frame_bounds(scene: SceneDef, margin: float = 0.25) -> BBox:
    height = float(scene.config.frame_height)
    width = height * 16.0 / 9.0
    return BBox(-width / 2 + margin, -height / 2 + margin, width / 2 - margin, height / 2 - margin)


def estimate_bboxes(scene: SceneDef, tex_probe_results: Optional[Dict[str, Any]] = None) -> Dict[str, BBoxEstimate]:
    if tex_probe_results is None:
        tex_probe_results = probe_tex_bboxes(scene)
    boxes: Dict[str, BBoxEstimate] = {}
    for mob in scene.mobjects:
        box = estimate_bbox(scene, mob, tex_probe_results=tex_probe_results)
        if box:
            boxes[mob.id] = box
    return boxes


def estimate_bbox(scene: SceneDef, mob: MobjectDef, tex_probe_results: Optional[Dict[str, Any]] = None) -> Optional[BBoxEstimate]:
    center = center_for(scene, mob)
    if mob.type == "Circle":
        radius = float(mob.args.get("radius", 1.0))
        return BBoxEstimate(around(center, radius * 2, radius * 2), "high", "circle_radius")
    if mob.type == "Square":
        side = float(mob.args.get("side_length", 2.0))
        return BBoxEstimate(around(center, side, side), "high", "square_side_length")
    if mob.type == "Dot":
        point = point3(mob.args.get("point", center))
        radius = float(mob.args.get("radius", 0.08))
        return BBoxEstimate(around(point, radius * 2, radius * 2), "high", "dot_radius")
    if mob.type in ("Line", "Arrow"):
        start = point3(mob.args.get("start", [0, 0, 0]))
        end = point3(mob.args.get("end", [0, 0, 0]))
        pad = max(float((mob.style.stroke_width if mob.style and mob.style.stroke_width else 2.0)) / 32.0, 0.08)
        return BBoxEstimate(BBox(min(start[0], end[0]) - pad, min(start[1], end[1]) - pad, max(start[0], end[0]) + pad, max(start[1], end[1]) + pad), "high", "line_endpoints")
    if mob.type == "Axes":
        return BBoxEstimate(around(center, float(mob.args.get("width", 6.0)), float(mob.args.get("height", 4.0))), "high", "axes_dimensions")
    if mob.type in ("Text", "Tex"):
        text = str(mob.args.get("text") or mob.args.get("tex") or "")
        font_size = float(mob.args.get("font_size", 48))
        if mob.type == "Tex" and tex_probe_results:
            measured = measured_tex_bbox(mob.id, center, tex_probe_results)
            if measured:
                return measured
        scale = 0.012 if mob.type == "Text" else 0.014
        width = max(0.4, len(text) * font_size * scale)
        height = max(0.25, font_size * 0.018)
        if mob.type == "Tex":
            height = conservative_tex_height(text, height)
        confidence: Confidence = "medium" if mob.type == "Text" else "unknown_static"
        method = "text_len_font_heuristic" if mob.type == "Text" else "tex_conservative_unknown_heuristic"
        return BBoxEstimate(around(center, width, height), confidence, method)
    return None


def measured_tex_bbox(mob_id: str, center: Tuple[float, float, float], tex_probe_results: Dict[str, Any]) -> Optional[BBoxEstimate]:
    result = tex_probe_results.get(mob_id)
    if not result or getattr(result, "status", None) != "measured" or getattr(result, "bbox", None) is None:
        return None
    measured_box = result.bbox
    return BBoxEstimate(around(center, measured_box.width, measured_box.height), "high", getattr(result, "method", "latex_dvisvgm"))


def probe_tex_bboxes(scene: SceneDef) -> Dict[str, Any]:
    try:
        from manim_cli.render.bbox_probe import probe_scene_tex_bboxes

        return probe_scene_tex_bboxes(scene)
    except Exception:
        return {}


def conservative_tex_height(tex: str, base_height: float) -> float:
    multiplier = 1.0
    if r"\frac" in tex:
        multiplier *= 1.8
        depth = max(0, tex.count(r"\frac") - 1)
        multiplier *= 1.25**depth
    if any(token in tex for token in (r"\lim", r"\sum", r"\prod", r"\int")):
        multiplier *= 1.4
    if any(token in tex for token in ("matrix", "cases", "aligned")):
        line_count = max(1, tex.count(r"\\") + 1, tex.count("&") // 2 + 1)
        multiplier *= max(1.5, line_count * 0.9)
    return base_height * multiplier


def center_for(scene: SceneDef, mob: MobjectDef) -> Tuple[float, float, float]:
    if mob.position and mob.position.mode == "absolute" and mob.position.point:
        return point3(mob.position.point)
    if mob.layout:
        if mob.layout.slot == "custom" and mob.layout.region:
            region = mob.layout.region
            left = float(region.get("left", region.get("x_min", 0.0)))
            right = float(region.get("right", region.get("x_max", 0.0)))
            bottom = float(region.get("bottom", region.get("y_min", 0.0)))
            top = float(region.get("top", region.get("y_max", 0.0)))
            return ((left + right) / 2.0, (bottom + top) / 2.0, 0.0)
        slot = slot_center(scene, mob.layout.slot)
        return slot
    if mob.position and mob.position.mode == "edge":
        bounds = frame_bounds(scene, margin=mob.position.buff)
        edge = mob.position.edge
        x = 0.0
        y = 0.0
        if edge and "L" in edge:
            x = bounds.left
        elif edge and "R" in edge:
            x = bounds.right
        if edge and "U" in edge:
            y = bounds.top
        elif edge and "D" in edge:
            y = bounds.bottom
        elif edge == "UP":
            y = bounds.top
        elif edge == "DOWN":
            y = bounds.bottom
        elif edge == "LEFT":
            x = bounds.left
        elif edge == "RIGHT":
            x = bounds.right
        return (x, y, 0.0)
    return (0.0, 0.0, 0.0)


def slot_center(scene: SceneDef, slot: str) -> Tuple[float, float, float]:
    region = slot_region(scene, slot)
    return ((region.left + region.right) / 2.0, (region.bottom + region.top) / 2.0, 0.0)


def slot_region(scene: SceneDef, slot: str) -> BBox:
    height = float(scene.config.frame_height)
    width = height * 16.0 / 9.0
    regions = {
        "title": BBox(-width * 0.39, height * 0.36, width * 0.39, height * 0.48),
        "subtitle": BBox(-width * 0.39, height * 0.26, width * 0.39, height * 0.38),
        "main": BBox(-width * 0.32, -height * 0.24, width * 0.32, height * 0.24),
        "left_panel": BBox(-width * 0.43, -height * 0.25, -width * 0.03, height * 0.25),
        "right_panel": BBox(width * 0.03, -height * 0.25, width * 0.43, height * 0.25),
        "bottom_formula": BBox(-width * 0.39, -height * 0.36, width * 0.39, -height * 0.21),
        "caption": BBox(-width * 0.39, -height * 0.46, width * 0.39, -height * 0.38),
        "callout": BBox(width * 0.1, height * 0.1, width * 0.46, height * 0.34),
    }
    return regions.get(slot, BBox(-width * 0.35, -height * 0.28, width * 0.35, height * 0.28))


def around(center: Tuple[float, float, float], width: float, height: float) -> BBox:
    x, y, _ = center
    return BBox(x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def point3(value: Any) -> Tuple[float, float, float]:
    if not isinstance(value, list):
        return (0.0, 0.0, 0.0)
    padded = list(value) + [0, 0, 0]
    return (float(padded[0]), float(padded[1]), float(padded[2]))


def layout_warnings(scene: SceneDef, tex_probe_results: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    boxes = estimate_bboxes(scene, tex_probe_results=tex_probe_results)
    bounds = frame_bounds(scene)
    warnings: List[Dict[str, Any]] = []
    mob_by_id = {mob.id: mob for mob in scene.mobjects}
    for mob_id, estimate in boxes.items():
        box = estimate.bbox
        mob = mob_by_id[mob_id]
        if mob.position and mob.position.mode == "edge":
            continue
        if box.left < bounds.left or box.right > bounds.right or box.bottom < bounds.bottom or box.top > bounds.top:
            warnings.append({"type": "layout_out_of_bounds", "object": mob_id, "bbox": bbox_dict(box), "bbox_confidence": estimate.confidence, "bbox_method": estimate.method})
        if mob.type in ("Text", "Tex") and box.width > bounds.width * 0.75:
            warnings.append({"type": "layout_text_too_wide", "object": mob_id, "bbox": bbox_dict(box), "bbox_confidence": estimate.confidence, "bbox_method": estimate.method})
        if mob.type in ("Text", "Tex") and float(mob.args.get("font_size", 48)) < 20:
            warnings.append({"type": "layout_font_too_small", "object": mob_id, "font_size": float(mob.args.get("font_size", 48)), "bbox_confidence": estimate.confidence, "bbox_method": estimate.method})
        if mob.layout and mob.layout.slot == "custom" and mob.layout.region:
            region_box = bbox_from_region(mob.layout.region)
            if region_box and not contains(region_box, box):
                warnings.append({"type": "layout_custom_region_overflow", "object": mob_id, "bbox": bbox_dict(box), "region": bbox_dict(region_box), "bbox_confidence": estimate.confidence, "bbox_method": estimate.method})
    for step in build_timeline(scene):
        visible = sorted(step.visible_after)
        if len(visible) > 12:
            warnings.append({"type": "layout_density", "step": step.step_id, "visible_count": len(visible)})
        for left_id, right_id in pairs(visible):
            left = boxes.get(left_id)
            right = boxes.get(right_id)
            left_mob = mob_by_id.get(left_id)
            right_mob = mob_by_id.get(right_id)
            if not left_mob or not right_mob or not should_check_overlap(left_mob, right_mob):
                continue
            if not left or not right or not overlaps(left.bbox, right.bbox):
                continue
            pair_conf = min_confidence(left.confidence, right.confidence)
            if is_text_plot_overlap(left_mob, right_mob):
                warnings.append({"type": "layout_overlap", "step": step.step_id, "objects": [left_id, right_id], "bbox_confidence": pair_conf, "bbox_methods": [left.method, right.method], "reason": "text_inside_plot_region"})
                continue
            if pair_conf == "unknown_static":
                warning_type = "layout_overlap" if is_risky_unknown_overlap(left_mob, right_mob) else "layout_needs_visual_qa"
                warnings.append({"type": warning_type, "step": step.step_id, "objects": [left_id, right_id], "bbox_confidence": pair_conf, "bbox_methods": [left.method, right.method], "reason": "unknown_static_overlap"})
            elif pair_conf == "high":
                warnings.append({"type": "layout_overlap", "step": step.step_id, "objects": [left_id, right_id], "bbox_confidence": pair_conf, "bbox_methods": [left.method, right.method]})
            else:
                ratio = overlap_area_ratio(left.bbox, right.bbox)
                if ratio >= 0.5:
                    warnings.append({"type": "layout_overlap", "step": step.step_id, "objects": [left_id, right_id], "bbox_confidence": pair_conf, "overlap_ratio": round(ratio, 3), "bbox_methods": [left.method, right.method]})
    return warnings


def should_check_overlap(left: MobjectDef, right: MobjectDef) -> bool:
    text_types = {"Text", "Tex"}
    solid_types = {"Circle", "Square", "Dot", "Line", "Arrow", "Axes"}
    if is_plot_geometry_overlap(left, right):
        return False
    if left.type in text_types and right.type in text_types:
        return True
    if left.type in solid_types and right.type in solid_types:
        return True
    if (left.type in text_types and right.type in solid_types) or (left.type in solid_types and right.type in text_types):
        return True
    return False


def is_plot_geometry_overlap(left: MobjectDef, right: MobjectDef) -> bool:
    plot_geometry_types = {"Dot", "Line", "Arrow"}
    if left.type == "Axes" and right.type in plot_geometry_types:
        return right.args.get("coordinate_space") == "plane" and right.args.get("axes") == left.id
    if right.type == "Axes" and left.type in plot_geometry_types:
        return left.args.get("coordinate_space") == "plane" and left.args.get("axes") == right.id
    if left.type in plot_geometry_types and right.type in plot_geometry_types:
        return (
            left.args.get("coordinate_space") == "plane"
            and right.args.get("coordinate_space") == "plane"
            and left.args.get("axes")
            and left.args.get("axes") == right.args.get("axes")
        )
    return False


def is_text_plot_overlap(left: MobjectDef, right: MobjectDef) -> bool:
    text_types = {"Text", "Tex"}
    plot_types = {"Axes", "Dot", "Line", "Arrow"}
    if left.type in text_types and right.type in plot_types:
        return left.position is None or left.position.mode != "relative"
    if right.type in text_types and left.type in plot_types:
        return right.position is None or right.position.mode != "relative"
    return False


def is_risky_unknown_overlap(left: MobjectDef, right: MobjectDef) -> bool:
    text_types = {"Text", "Tex"}
    protected_types = {"Text", "Tex", "Axes", "Dot", "Line", "Arrow"}
    if is_relative_annotation(left) or is_relative_annotation(right):
        return False
    return (left.type in text_types and right.type in protected_types) or (right.type in text_types and left.type in protected_types)


def is_relative_annotation(mob: MobjectDef) -> bool:
    return mob.type in {"Text", "Tex"} and mob.position is not None and mob.position.mode == "relative"


def overlaps(left: BBox, right: BBox) -> bool:
    return left.left < right.right and left.right > right.left and left.bottom < right.top and left.top > right.bottom


def overlap_area_ratio(left: BBox, right: BBox) -> float:
    iw = min(left.right, right.right) - max(left.left, right.left)
    ih = min(left.top, right.top) - max(left.bottom, right.bottom)
    if iw <= 0 or ih <= 0:
        return 0.0
    intersection = iw * ih
    smaller = min(left.width * left.height, right.width * right.height)
    return intersection / smaller if smaller > 0 else 0.0


def contains(outer: BBox, inner: BBox) -> bool:
    return inner.left >= outer.left and inner.right <= outer.right and inner.bottom >= outer.bottom and inner.top <= outer.top


def pairs(values: Iterable[str]) -> Iterable[Tuple[str, str]]:
    items = list(values)
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            yield left, right


def bbox_dict(box: BBox) -> Dict[str, float]:
    return {"left": round(box.left, 3), "bottom": round(box.bottom, 3), "right": round(box.right, 3), "top": round(box.top, 3)}


def bbox_from_region(region: Dict[str, Any]) -> Optional[BBox]:
    try:
        left = float(region.get("left", region.get("x_min", 0.0)))
        bottom = float(region.get("bottom", region.get("y_min", 0.0)))
        if "right" in region or "x_max" in region:
            right = float(region.get("right", region.get("x_max")))
        elif "max_width" in region:
            right = left + float(region["max_width"])
        else:
            right = left
        if "top" in region or "y_max" in region:
            top = float(region.get("top", region.get("y_max")))
        elif "max_height" in region:
            top = bottom + float(region["max_height"])
        else:
            top = bottom
    except (TypeError, ValueError):
        return None
    return BBox(left, bottom, right, top)


def min_confidence(left: Confidence, right: Confidence) -> Confidence:
    order = {"unknown_static": 0, "medium": 1, "high": 2}
    return left if order[left] <= order[right] else right
