from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from manim_cli.build import file_hash, write_build_manifest
from manim_cli.dsl.compiler import compile_scene_file
from manim_cli.dsl.validators import parse_scene_file
from manim_cli.jsonio import Diagnostic, error_result, ok_result, write_json
from manim_cli.qa.engine import run_qa
from manim_cli.render.diagnose import classify_output


def output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def render_target(target: Path, quality: str, output: Path, qa_gate: bool = False, qa_profile: str = "strict") -> Diagnostic:
    if target.suffix == ".json":
        if qa_gate:
            qa_result = run_qa(target, profile=qa_profile)
            if not qa_result.get("ok"):
                qa_result["phase"] = "render_qa_gate"
                qa_result["message"] = "render skipped because QA gate failed"
                return qa_result
        out_dir = target.parent / "generated"
        compile_profile = "final" if quality in ("high", "final") else "preview"
        compiled = compile_scene_file(target, out_dir, profile=compile_profile)
        if not compiled.get("ok"):
            return compiled
        scene_py = Path(compiled["scene_py"])
        source_map = Path(compiled["source_map"])
        scene_config = parse_scene_file(target).config
    else:
        scene_py = target
        source_map = target.with_name("scene.py.map.json")
        scene_config = None
    return run_manim(scene_py, source_map, quality, output, scene_config)


def run_manim(scene_py: Path, source_map: Path, quality: str, output: Path, scene_config: Optional[object]) -> Diagnostic:
    if quality not in ("draft", "preview", "final", "low", "high"):
        return error_result("render", "invalid_enum", "quality must be draft, preview, final, low, or high")

    output = output.resolve()

    if quality in ("draft", "low"):
        resolution = "854,480"
        fps = 15
        timeout = 120
    elif quality == "preview":
        resolution = "1280,720"
        fps = 24
        timeout = 240
    else:
        resolution_list = getattr(scene_config, "resolution", [1920, 1080])
        resolution = f"{resolution_list[0]},{resolution_list[1]}"
        fps = getattr(scene_config, "fps", 30)
        timeout = 600

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "manim",
        str(scene_py),
        "GeneratedScene",
        "--resolution",
        resolution,
        "--fps",
        str(fps),
        "-o",
        str(output),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = output_text(exc.stdout)
        stderr = output_text(exc.stderr)
        payload = {
            "ok": False,
            "phase": "render",
            "error_type": "render_timeout",
            "message": f"Render timed out after {timeout}s",
            "stdout": stdout,
            "stderr": stderr,
        }
        write_json(output.parent / "render.json", payload)
        return error_result("render", "render_timeout", payload["message"], location={"source_map": str(source_map)}, suggestions=["Lower quality or simplify the scene."])
    except FileNotFoundError:
        return error_result("render", "missing_dependency", "manim executable was not found", suggestions=["Install Manim and ensure manim is on PATH."])

    payload = {
        "ok": result.returncode == 0,
        "phase": "render",
        "command": cmd,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
    write_json(output.parent / "render.json", payload)
    if result.returncode != 0:
        return error_result(
            "render",
            classify_output(result.stdout, result.stderr),
            "manim render failed",
            location={"file": str(scene_py), "source_map": str(source_map)},
            details={"stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]},
        )
    if not output.exists():
        return error_result(
            "render",
            classify_output(result.stdout, result.stderr),
            "manim render completed without creating the requested output file",
            location={"file": str(scene_py), "source_map": str(source_map)},
            details={"stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:], "output": str(output)},
            suggestions=["Check the manim -o output path behavior for this installed Manim version."],
        )
    manifest_path = output.parent / "build_manifest.json"
    manifest = write_build_manifest(manifest_path, file_hash(scene_py), "external" if scene_config is None else ("final" if quality in ("high", "final") else "preview"), quality)
    return ok_result("render", scene_py=str(scene_py), source_map=str(source_map), output=str(output), stdout=result.stdout[-4000:], build_manifest=str(manifest_path), manifest=manifest)
