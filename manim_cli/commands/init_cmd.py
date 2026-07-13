from __future__ import annotations

from pathlib import Path

import click

from manim_cli import __version__
from manim_cli.jsonio import ok_result, print_json, write_json


@click.command("init")
@click.argument("project_dir", type=click.Path(path_type=Path))
def init_cmd(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    for directory in ("generated", "renders", "diagnostics", "feedback"):
        (project_dir / directory).mkdir(exist_ok=True)

    project_id = project_dir.name
    project = {
        "id": project_id,
        "created_by": "agent",
        "manim_cli_version": __version__,
        "status": "draft",
        "artifacts": {
            "brief": "brief.md",
            "plan": "plan.json",
            "storyboard": "storyboard.json",
            "scene": "scene.json",
            "generated_scene": "generated/scene.py",
            "source_map": "generated/scene.py.map.json",
            "preview": "renders/preview.mp4",
            "final": "renders/final.mp4",
        },
    }
    write_json(project_dir / "project.json", project)
    write_text_if_missing(project_dir / "brief.md", "")
    write_json(project_dir / "plan.json", {})
    write_json(project_dir / "storyboard.json", {})
    write_json(project_dir / "scene.json", {})
    write_text_if_missing(project_dir / "feedback" / "latest.md", "")
    print_json(ok_result("init", project_dir=str(project_dir), project=str(project_dir / "project.json")))


def write_text_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")

