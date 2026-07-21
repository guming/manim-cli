from __future__ import annotations

import shutil
from pathlib import Path

import click

from manim_cli.jsonio import error_result, load_json, ok_result, print_json


EXAMPLE_NAME = "pythagorean_theorem"
JSON_ARTIFACTS = ("plan", "storyboard", "scene")


def bundled_example_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "agent" / "skill" / "examples" / EXAMPLE_NAME


@click.command("example")
@click.argument("artifact", type=click.Choice((*JSON_ARTIFACTS, "project")))
@click.option("--output", type=click.Path(path_type=Path), help="Write the example project or JSON artifact to this path.")
def example_cmd(artifact: str, output: Path | None) -> None:
    """Print or copy the canonical teaching example."""
    source_dir = bundled_example_dir()
    if not source_dir.exists():
        print_json(error_result("example", "missing_bundled_example", f"Bundled example was not found: {source_dir}"))
        raise SystemExit(1)

    if artifact == "project":
        if output is None:
            print_json(ok_result("example", artifact=artifact, name=EXAMPLE_NAME, source=str(source_dir), files=example_files(source_dir)))
            return
        if output.exists():
            print_json(error_result("example", "destination_exists", f"Destination already exists: {output}"))
            raise SystemExit(1)
        shutil.copytree(source_dir, output)
        print_json(ok_result("example", artifact=artifact, name=EXAMPLE_NAME, output=str(output), files=example_files(output)))
        return

    source = source_dir / f"{artifact}.json"
    data = load_json(source)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        print_json(ok_result("example", artifact=artifact, name=EXAMPLE_NAME, output=str(output), example=data))
        return
    print_json(ok_result("example", artifact=artifact, name=EXAMPLE_NAME, example=data))


def example_files(directory: Path) -> list[str]:
    return sorted(str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file())
