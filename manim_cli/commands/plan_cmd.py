from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import print_json
from manim_cli.planning.validators import validate_plan_file


@click.group("plan")
def plan_group() -> None:
    """TeachingPlan commands."""


@plan_group.command("validate")
@click.argument("plan_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def plan_validate(plan_json: Path) -> None:
    print_json(validate_plan_file(plan_json))

