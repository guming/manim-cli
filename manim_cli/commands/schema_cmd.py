from __future__ import annotations

import click

from manim_cli.dsl.models import SceneDef
from manim_cli.jsonio import ok_result, print_json
from manim_cli.planning.models import Storyboard, TeachingPlan


SCHEMAS = {
    "plan": TeachingPlan,
    "storyboard": Storyboard,
    "scene": SceneDef,
}


@click.command("schema")
@click.argument("artifact", type=click.Choice(tuple(SCHEMAS)))
def schema_cmd(artifact: str) -> None:
    """Print the current JSON Schema for an authorable artifact."""
    model = SCHEMAS[artifact]
    print_json(ok_result("schema", artifact=artifact, schema=model.model_json_schema(by_alias=True)))
