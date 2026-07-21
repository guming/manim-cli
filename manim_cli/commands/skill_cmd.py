from __future__ import annotations

import shutil
from pathlib import Path

import click

from manim_cli.jsonio import error_result, ok_result, print_json


DEFAULT_SKILL_NAME = "manim-video"


def bundled_skill_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "agent" / "skill"


def install_skill(
    target_dir: Path,
    *,
    name: str = DEFAULT_SKILL_NAME,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    source_dir = bundled_skill_dir()
    destination = target_dir.expanduser() / name

    if not source_dir.exists():
        return error_result(
            "skill_install",
            "missing_bundled_skill",
            f"Bundled skill directory was not found: {source_dir}",
        )

    if destination.exists() and not force:
        return error_result(
            "skill_install",
            "destination_exists",
            f"Skill already exists at {destination}",
            suggestions=["Pass --force to replace the existing installed skill."],
            details={"destination": str(destination)},
        )

    copied_files = sorted(
        str(path.relative_to(source_dir))
        for path in source_dir.rglob("*")
        if path.is_file()
    )

    if not dry_run:
        target_dir.expanduser().mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_dir, destination)

    return ok_result(
        "skill_install",
        source=str(source_dir),
        destination=str(destination),
        installed=not dry_run,
        files=copied_files,
    )


@click.group("skill")
def skill_group() -> None:
    """Install and inspect bundled agent skills."""


@skill_group.command("install")
@click.option(
    "--target-dir",
    type=click.Path(path_type=Path),
    default=Path("~/.codex/skills"),
    show_default=True,
    help="Directory that contains installed skills.",
)
@click.option("--name", default=DEFAULT_SKILL_NAME, show_default=True, help="Installed skill directory name.")
@click.option("--force", is_flag=True, help="Replace an existing installed skill.")
@click.option("--dry-run", is_flag=True, help="Report what would be installed without writing files.")
def install_cmd(target_dir: Path, name: str, force: bool, dry_run: bool) -> None:
    result = install_skill(target_dir, name=name, force=force, dry_run=dry_run)
    print_json(result)
    if not result.get("ok"):
        raise SystemExit(1)
