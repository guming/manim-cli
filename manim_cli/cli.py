from __future__ import annotations

import sys
from pathlib import Path

import click

from manim_cli.commands.compile_cmd import compile_cmd
from manim_cli.commands.diagnose_cmd import diagnose_cmd
from manim_cli.commands.init_cmd import init_cmd
from manim_cli.commands.knowledge_cmd import knowledge_group
from manim_cli.commands.manifest_cmd import manifest_cmd
from manim_cli.commands.migrate_layout_cmd import migrate_layout_cmd
from manim_cli.commands.plan_cmd import plan_group
from manim_cli.commands.qa_cmd import qa_cmd
from manim_cli.commands.qa_eval_cmd import qa_eval_cmd
from manim_cli.commands.regression_cmd import regression_group
from manim_cli.commands.render_cmd import render_cmd
from manim_cli.commands.source_map_cmd import source_map_group
from manim_cli.commands.split_layout_cmd import split_layout_cmd
from manim_cli.commands.storyboard_cmd import storyboard_group
from manim_cli.commands.validate_cmd import validate_cmd
from manim_cli.commands.visual_qa_cmd import visual_qa_group
from manim_cli.jsonio import error_result, print_json


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Validate, compile, and render restricted Manim scene DSL files."""


main.add_command(init_cmd, "init")
main.add_command(knowledge_group, "knowledge")
main.add_command(plan_group, "plan")
main.add_command(storyboard_group, "storyboard")
main.add_command(validate_cmd, "validate")
main.add_command(compile_cmd, "compile")
main.add_command(qa_cmd, "qa")
main.add_command(qa_eval_cmd, "qa-eval")
main.add_command(render_cmd, "render")
main.add_command(diagnose_cmd, "diagnose")
main.add_command(manifest_cmd, "manifest")
main.add_command(migrate_layout_cmd, "migrate-layout")
main.add_command(visual_qa_group, "visual-qa")
main.add_command(regression_group, "regression")
main.add_command(source_map_group, "source-map")
main.add_command(split_layout_cmd, "split-layout")


def fail_cli(exc: Exception, phase: str = "cli") -> None:
    print_json(
        error_result(
            phase,
            "cli_error",
            str(exc),
            suggestions=["Run manim-cli --help to inspect the supported command shape."],
        )
    )
    raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - Click normally handles this.
        fail_cli(exc)
