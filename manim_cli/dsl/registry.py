from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

from manim_cli.dsl.encoders import emit_point, py_color, py_direction, py_num, py_rate_func, py_str, py_vec
from manim_cli.dsl.layout import slot_center
from manim_cli.dsl.models import (
    ActionDef,
    ArrowArgs,
    AxesArgs,
    CircleArgs,
    DotArgs,
    LineArgs,
    SquareArgs,
    TexArgs,
    TextArgs,
)
from manim_cli.dsl.writer import CodeWriter


@dataclass(frozen=True)
class MobjectSpec:
    type_name: str
    args_model: Type[BaseModel]
    imports: tuple[str, ...]
    emit: Callable[[str, BaseModel, Any, CodeWriter, str], None]
    description: str


@dataclass(frozen=True)
class ActionSpec:
    type_name: str
    imports: tuple[str, ...]
    emit: Callable[[ActionDef, Any, CodeWriter, str], None]
    description: str


def emit_tex(var_name: str, args: TexArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    writer.add(
        f"        {var_name} = Tex({py_str(args.tex)}, font_size={args.font_size}, tex_environment='align*')",
        path=f"{path}.args",
        symbol=f"{var_name}",
    )


def emit_text(var_name: str, args: TextArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    kwargs = [f"font_size={args.font_size}"]
    if args.font:
        kwargs.append(f"font={py_str(args.font)}")
    writer.add(
        f"        {var_name} = Text({py_str(args.text)}, {', '.join(kwargs)})",
        path=f"{path}.args.text",
        symbol=var_name,
        metadata=ctx.metadata_for_object(var_name),
    )


def emit_circle(var_name: str, args: CircleArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    writer.add(f"        {var_name} = Circle(radius={py_num(args.radius)})", path=path, symbol=var_name, metadata=ctx.metadata_for_object(var_name))


def emit_square(var_name: str, args: SquareArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    writer.add(f"        {var_name} = Square(side_length={py_num(args.side_length)})", path=path, symbol=var_name, metadata=ctx.metadata_for_object(var_name))


def emit_line(var_name: str, args: LineArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    start = emit_point(args.start, args.coordinate_space, args.axes, ctx)
    end = emit_point(args.end, args.coordinate_space, args.axes, ctx)
    writer.add(f"        {var_name} = Line({start}, {end})", path=path, symbol=var_name, metadata=ctx.metadata_for_object(var_name))


def emit_arrow(var_name: str, args: ArrowArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    start = emit_point(args.start, args.coordinate_space, args.axes, ctx)
    end = emit_point(args.end, args.coordinate_space, args.axes, ctx)
    kwargs = [f"buff={py_num(args.buff)}"]
    if args.tip_length is not None:
        kwargs.append(f"tip_length={py_num(args.tip_length)}")
    writer.add(f"        {var_name} = Arrow({start}, {end}, {', '.join(kwargs)})", path=path, symbol=var_name, metadata=ctx.metadata_for_object(var_name))


def emit_dot(var_name: str, args: DotArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    point = emit_point(args.point, args.coordinate_space, args.axes, ctx)
    writer.add(f"        {var_name} = Dot(point={point}, radius={py_num(args.radius)})", path=path, symbol=var_name, metadata=ctx.metadata_for_object(var_name))


def emit_axes(var_name: str, args: AxesArgs, ctx: Any, writer: CodeWriter, path: str) -> None:
    writer.add(
        "        "
        f"{var_name} = Axes(x_range={repr(args.x_range)}, y_range={repr(args.y_range)}, "
        f"x_length={py_num(args.width)}, y_length={py_num(args.height)})",
        path=path,
        symbol=var_name,
        metadata=ctx.metadata_for_object(var_name),
    )


MOBJECT_REGISTRY: Dict[str, MobjectSpec] = {
    "Tex": MobjectSpec("Tex", TexArgs, ("from manim import Tex",), emit_tex, "Mathematical TeX text"),
    "Text": MobjectSpec("Text", TextArgs, ("from manim import Text",), emit_text, "Plain text"),
    "Circle": MobjectSpec("Circle", CircleArgs, ("from manim import Circle",), emit_circle, "Circle geometry"),
    "Square": MobjectSpec("Square", SquareArgs, ("from manim import Square",), emit_square, "Square geometry"),
    "Line": MobjectSpec("Line", LineArgs, ("from manim import Line",), emit_line, "Line segment"),
    "Arrow": MobjectSpec("Arrow", ArrowArgs, ("from manim import Arrow",), emit_arrow, "Arrow vector"),
    "Dot": MobjectSpec("Dot", DotArgs, ("from manim import Dot",), emit_dot, "Point marker"),
    "Axes": MobjectSpec("Axes", AxesArgs, ("from manim import Axes",), emit_axes, "2D axes"),
}


def emit_style(var_name: str, style: Any, writer: CodeWriter, path: str) -> None:
    if not style:
        return
    if style.color:
        writer.add(f"        {var_name}.set_color({py_color(style.color)})", path=f"{path}.style.color", symbol=f"{var_name}.set_color")
    if style.opacity is not None:
        writer.add(f"        {var_name}.set_opacity({py_num(style.opacity)})", path=f"{path}.style.opacity", symbol=f"{var_name}.set_opacity")
    stroke_args = []
    if style.stroke_color:
        stroke_args.append(f"color={py_color(style.stroke_color)}")
    if style.stroke_width is not None:
        stroke_args.append(f"width={py_num(style.stroke_width)}")
    if stroke_args:
        writer.add(f"        {var_name}.set_stroke({', '.join(stroke_args)})", path=f"{path}.style", symbol=f"{var_name}.set_stroke")
    fill_args = []
    if style.fill_color:
        fill_args.append(f"color={py_color(style.fill_color)}")
    if style.fill_opacity is not None:
        fill_args.append(f"opacity={py_num(style.fill_opacity)}")
    if fill_args:
        writer.add(f"        {var_name}.set_fill({', '.join(fill_args)})", path=f"{path}.style", symbol=f"{var_name}.set_fill")


def emit_position(var_name: str, position: Any, ctx: Any, writer: CodeWriter, path: str) -> None:
    if not position:
        return
    if position.mode == "absolute":
        writer.add(f"        {var_name}.move_to({py_vec(position.point)})", path=f"{path}.position.point", symbol=f"{var_name}.move_to")
    elif position.mode == "edge":
        writer.add(f"        {var_name}.to_edge({py_direction(position.edge)}, buff={py_num(position.buff)})", path=f"{path}.position", symbol=f"{var_name}.to_edge")
    elif position.mode == "relative":
        target = ctx.var_for(position.target)
        writer.add(
            f"        {var_name}.next_to({target}, {py_direction(position.direction)}, buff={py_num(position.buff)})",
            path=f"{path}.position",
            symbol=f"{var_name}.next_to",
        )
    elif position.mode == "align_to":
        target = ctx.var_for(position.target)
        writer.add(f"        {var_name}.align_to({target}, {py_direction(position.edge)})", path=f"{path}.position", symbol=f"{var_name}.align_to")


def play_kwargs(action: ActionDef) -> str:
    kwargs = []
    if action.run_time is not None:
        kwargs.append(f"run_time={py_num(action.run_time)}")
    rate_func = py_rate_func(action.rate_func)
    if rate_func:
        kwargs.append(f"rate_func={rate_func}")
    return "" if not kwargs else ", " + ", ".join(kwargs)


def emit_add(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.add({target})", path=path, symbol=f"add({target})", metadata=ctx.metadata_for_action(action))


def emit_remove(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.remove({target})", path=path, symbol=f"remove({target})", metadata=ctx.metadata_for_action(action))


def emit_write_action(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.play(Write({target}){play_kwargs(action)})", path=path, symbol=f"Write({target})", metadata=ctx.metadata_for_action(action))


def emit_fade_in(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.play(FadeIn({target}){play_kwargs(action)})", path=path, symbol=f"FadeIn({target})", metadata=ctx.metadata_for_action(action))


def emit_fade_out(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.play(FadeOut({target}){play_kwargs(action)})", path=path, symbol=f"FadeOut({target})", metadata=ctx.metadata_for_action(action))


def emit_show_creation(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    writer.add(f"        self.play(Create({target}){play_kwargs(action)})", path=path, symbol=f"Create({target})", metadata=ctx.metadata_for_action(action))


def emit_transform(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    to = ctx.var_for(action.to)
    anim = "TransformMatchingTex" if action.match_by == "tex" else "Transform"
    writer.add(f"        self.play({anim}({target}, {to}){play_kwargs(action)})", path=path, symbol=f"{anim}({target}, {to})", metadata=ctx.metadata_for_action(action))


def emit_highlight(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    color = f", color={py_color(action.color)}" if action.color else ""
    writer.add(f"        self.play(Indicate({target}{color}){play_kwargs(action)})", path=path, symbol=f"Indicate({target})", metadata=ctx.metadata_for_action(action))


def emit_wait(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    writer.add(f"        self.wait({py_num(action.duration)})", path=path, symbol="wait", metadata=ctx.metadata_for_action(action))


def emit_layout_action(action: ActionDef, ctx: Any, writer: CodeWriter, path: str) -> None:
    target = ctx.var_for(action.target)
    center = custom_region_center(action.region) if action.slot == "custom" and action.region else slot_center(ctx.scene, action.slot)
    move_expr = f"{target}.animate.move_to(np.array({list(center)!r}))"
    if action.run_time is not None or action.rate_func:
        writer.add(f"        self.play({move_expr}{play_kwargs(action)})", path=path, symbol=f"{target}.layout", metadata=ctx.metadata_for_action(action))
    else:
        writer.add(f"        {target}.move_to(np.array({list(center)!r}))", path=path, symbol=f"{target}.layout", metadata=ctx.metadata_for_action(action))
    ctx.layout_changes.append(
        {
            "object": action.target,
            "change": "step_layout",
            "to_slot": action.slot,
            "to_center": [round(value, 3) for value in center],
            "reason": "layout action",
            "source_path": path,
        }
    )


def custom_region_center(region: dict[str, object]) -> tuple[float, float, float]:
    left = float(region.get("left", region.get("x_min", 0.0)))
    right = float(region.get("right", region.get("x_max", 0.0)))
    bottom = float(region.get("bottom", region.get("y_min", 0.0)))
    top = float(region.get("top", region.get("y_max", 0.0)))
    return ((left + right) / 2.0, (bottom + top) / 2.0, 0.0)


ACTION_REGISTRY: Dict[str, ActionSpec] = {
    "add": ActionSpec("add", tuple(), emit_add, "Instantly add target"),
    "remove": ActionSpec("remove", tuple(), emit_remove, "Instantly remove target"),
    "write": ActionSpec("write", ("from manim import Write",), emit_write_action, "Write text or formula"),
    "fade_in": ActionSpec("fade_in", ("from manim import FadeIn",), emit_fade_in, "Fade target in"),
    "fade_out": ActionSpec("fade_out", ("from manim import FadeOut",), emit_fade_out, "Fade target out"),
    "show_creation": ActionSpec("show_creation", ("from manim import Create",), emit_show_creation, "Draw target"),
    "transform": ActionSpec(
        "transform",
        (
            "from manim import Transform",
            "from manim import TransformMatchingTex",
        ),
        emit_transform,
        "Transform one target to another",
    ),
    "highlight": ActionSpec("highlight", ("from manim import Indicate",), emit_highlight, "Indicate target"),
    "wait": ActionSpec("wait", tuple(), emit_wait, "Pause scene"),
    "layout": ActionSpec("layout", tuple(), emit_layout_action, "Move target to a layout slot or custom region"),
}
