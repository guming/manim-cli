from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Number = Union[float, int]
Point = List[Number]
SCENE_SCHEMA_VERSION = "1.1"
SUPPORTED_SCENE_VERSIONS = ("1.0", "1.1")
RESERVED_FUTURE_SCENE_FIELDS = ("layout_template",)
RESERVED_FUTURE_MOBJECT_FIELDS = ("layout_role",)
LayoutTemplateName = Literal[
    "plot_full",
    "plot_with_bottom_formula",
    "plot_with_side_formula",
    "plot_then_formula",
    "formula_then_caption",
    "vertical_derivation",
    "diagram_left_proof_right",
    "coordinate_plane_with_callouts",
    "chart_with_caption",
    "title_definition_examples",
]
LayoutRoleName = Literal[
    "plot.axes",
    "plot.primary",
    "plot.annotation",
    "formula.primary",
    "formula.secondary",
    "caption.conclusion",
    "title.primary",
    "diagram.primary",
    "proof.step",
    "chart.primary",
]
TimingRoleName = Literal["transition", "derivation", "conclusion"]


class SceneConfig(StrictBaseModel):
    resolution: List[int] = Field(default_factory=lambda: [1920, 1080])
    frame_height: float = 8.0
    background_color: str = "#1e1e1e"
    fps: int = 30
    visual_theme: str = "casual_3b1b"


class StyleSpec(StrictBaseModel):
    color: Optional[str] = None
    fill_color: Optional[str] = None
    fill_opacity: Optional[float] = None
    stroke_color: Optional[str] = None
    stroke_width: Optional[float] = None
    opacity: Optional[float] = None


class PositionSpec(StrictBaseModel):
    mode: Literal["absolute", "edge", "relative", "align_to"]
    point: Optional[Point] = None
    edge: Optional[str] = None
    target: Optional[str] = None
    direction: Optional[str] = None
    buff: float = 0.4


class LayoutSpec(StrictBaseModel):
    slot: Literal["title", "subtitle", "main", "left_panel", "right_panel", "bottom_formula", "caption", "callout", "custom"]
    align: Literal["center", "left", "right", "top", "bottom"] = "center"
    direction: Optional[Literal["horizontal", "vertical"]] = None
    buff: float = 0.35
    region: Optional[Dict[str, Number]] = None


class TexArgs(StrictBaseModel):
    tex: str
    font_size: int = 48


class TextArgs(StrictBaseModel):
    text: str
    font: Optional[str] = None
    font_size: int = 48


class CircleArgs(StrictBaseModel):
    radius: float = 1.0


class SquareArgs(StrictBaseModel):
    side_length: float = 2.0


class CoordinateArgs(StrictBaseModel):
    coordinate_space: Literal["screen", "plane"] = "screen"
    axes: Optional[str] = None


class LineArgs(CoordinateArgs):
    start: Point
    end: Point


class ArrowArgs(CoordinateArgs):
    start: Point
    end: Point
    buff: float = 0.0
    tip_length: Optional[float] = None


class DotArgs(CoordinateArgs):
    point: Point
    radius: float = 0.08


class AxesArgs(StrictBaseModel):
    x_range: List[Number]
    y_range: List[Number]
    width: float = 6.0
    height: float = 4.0


class MobjectDef(StrictBaseModel):
    id: str
    type: str
    args: Dict[str, Any] = Field(default_factory=dict)
    style: Optional[StyleSpec] = None
    position: Optional[PositionSpec] = None
    layout: Optional[LayoutSpec] = None
    layout_role: Optional[LayoutRoleName] = None
    render_role: Optional[Literal["static_background"]] = None


class ActionDef(StrictBaseModel):
    type: str
    target: Optional[Union[str, List[str]]] = None
    to: Optional[str] = None
    run_time: Optional[float] = None
    rate_func: Optional[str] = None
    match_by: Optional[Literal["none", "tex"]] = "none"
    color: Optional[str] = None
    duration: Optional[float] = None
    semantic_relation: Optional[str] = None
    reason: Optional[str] = None
    slot: Optional[Literal["title", "subtitle", "main", "left_panel", "right_panel", "bottom_formula", "caption", "callout", "custom"]] = None
    region: Optional[Dict[str, Number]] = None
    timing_role: Optional[TimingRoleName] = None


class StepDef(StrictBaseModel):
    id: Optional[str] = None
    name: str
    narration_cue_id: Optional[str] = None
    storyboard_event_id: Optional[str] = None
    actions: List[ActionDef]
    wait_after: Optional[float] = None
    comment: Optional[str] = None
    timing_role: Optional[TimingRoleName] = None


class SceneDef(StrictBaseModel):
    _requested_layout_template: Optional[str] = PrivateAttr(default=None)
    _layout_fallback_failure: Optional[Dict[str, Any]] = PrivateAttr(default=None)

    schema_: Optional[str] = Field(default=None, alias="$schema")
    version: Literal["1.0", "1.1"]
    name: str
    description: Optional[str] = None
    plan_ref: Optional[str] = None
    storyboard_ref: Optional[str] = None
    layout_template: Optional[LayoutTemplateName] = None
    config: SceneConfig
    mobjects: List[MobjectDef]
    steps: List[StepDef]


MOBJECT_ARG_MODELS = {
    "Tex": TexArgs,
    "Text": TextArgs,
    "Circle": CircleArgs,
    "Square": SquareArgs,
    "Line": LineArgs,
    "Arrow": ArrowArgs,
    "Dot": DotArgs,
    "Axes": AxesArgs,
}


SUPPORTED_MOBJECTS = tuple(MOBJECT_ARG_MODELS.keys())
SUPPORTED_ACTIONS = (
    "add",
    "remove",
    "write",
    "fade_in",
    "fade_out",
    "show_creation",
    "transform",
    "highlight",
    "wait",
    "layout",
)
COLORS = ("WHITE", "BLACK", "BLUE", "YELLOW", "RED", "GREEN", "GOLD", "PURPLE", "TEAL")
DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT", "UL", "UR", "DL", "DR", "ORIGIN")
RATE_FUNCS = ("smooth", "linear", "there_and_back")
