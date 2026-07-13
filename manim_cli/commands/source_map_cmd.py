from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import ok_result, print_json
from manim_cli.source_map import lookup_source_map


@click.group("source-map")
def source_map_group() -> None:
    """Inspect generated scene.py source maps."""


@source_map_group.command("lookup")
@click.argument("source_map_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--line", "line_no", type=int, default=None)
@click.option("--dsl-path", default=None)
@click.option("--object-id", default=None)
@click.option("--step-id", default=None)
def source_map_lookup_cmd(source_map_json: Path, line_no: int | None, dsl_path: str | None, object_id: str | None, step_id: str | None) -> None:
    selectors = [line_no is not None, dsl_path is not None, object_id is not None, step_id is not None]
    if sum(selectors) != 1:
        print_json({"ok": False, "phase": "source_map", "error_type": "invalid_selector", "message": "Provide exactly one of --line, --dsl-path, --object-id, or --step-id."})
        return
    matches = lookup_source_map(source_map_json, line_no=line_no, dsl_path=dsl_path, object_id=object_id, step_id=step_id)
    print_json(ok_result("source_map", source_map=str(source_map_json), matches=matches))
