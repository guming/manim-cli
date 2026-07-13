from __future__ import annotations

import click

from manim_cli.dsl.models import COLORS, DIRECTIONS, RATE_FUNCS
from manim_cli.dsl.registry import ACTION_REGISTRY, MOBJECT_REGISTRY
from manim_cli.jsonio import ok_result, print_json


@click.command("manifest")
def manifest_cmd() -> None:
    print_json(
        ok_result(
            "manifest",
            mobject_types={
                name: {"description": spec.description, "args_model": spec.args_model.__name__}
                for name, spec in MOBJECT_REGISTRY.items()
            },
            action_types={
                name: {"description": spec.description}
                for name, spec in ACTION_REGISTRY.items()
            },
            style_fields=["color", "fill_color", "fill_opacity", "stroke_color", "stroke_width", "opacity"],
            position_modes=["absolute", "edge", "relative", "align_to"],
            colors=list(COLORS),
            rate_functions=list(RATE_FUNCS),
            directions=list(DIRECTIONS),
            coordinate_spaces=["screen", "plane"],
            unsupported_mvp=["Graph", "VGroup", "multi-target actions", "params action schema", "safe_expression"],
        )
    )

