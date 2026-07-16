from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from manim_cli.build import file_hash, write_build_manifest
from manim_cli.dsl.compiler import compile_scene_file
from manim_cli.dsl.pacing import PACING_PROFILES, PacingProfile, PacingResult, apply_pacing, build_step_duration_targets
from manim_cli.dsl.validators import parse_scene_file
from manim_cli.jsonio import Diagnostic, error_result, ok_result, write_json
from manim_cli.qa.engine import run_qa
from manim_cli.render.diagnose import classify_output
from manim_cli.render.pacing_qa import run_render_pacing_qa
from manim_cli.planning.pedagogy import load_plan, load_storyboard


def output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def render_target(
    target: Path,
    quality: str,
    output: Path,
    qa_gate: bool = False,
    qa_profile: str = "strict",
    pacing_profile: PacingProfile = "teaching",
    pacing_qa: bool | None = None,
) -> Diagnostic:
    if pacing_profile not in PACING_PROFILES:
        return error_result("render", "invalid_enum", "pacing_profile must be preserve, teaching, or accelerated")
    pacing: PacingResult | None = None
    if target.suffix == ".json":
        source_scene = parse_scene_file(target)
        plan = load_plan(target.parent, source_scene.plan_ref)
        storyboard = load_storyboard(target.parent, source_scene.storyboard_ref)
        pacing = apply_pacing(
            source_scene,
            pacing_profile,
            step_duration_targets=build_step_duration_targets(source_scene, plan, storyboard),
        )
        if qa_gate:
            qa_result = run_qa(target, profile=qa_profile, pacing_profile=pacing_profile)
            if not qa_result.get("ok"):
                qa_result["phase"] = "render_qa_gate"
                qa_result["message"] = "render skipped because QA gate failed"
                return qa_result
        out_dir = target.parent / "generated"
        compile_profile = "final" if quality in ("high", "final") else "preview"
        compiled = compile_scene_file(target, out_dir, profile=compile_profile, pacing_profile=pacing_profile)
        if not compiled.get("ok"):
            return compiled
        scene_py = Path(compiled["scene_py"])
        source_map = Path(compiled["source_map"])
        scene_config = source_scene.config
    else:
        scene_py = target
        source_map = target.with_name("scene.py.map.json")
        scene_config = None
    enforce_pacing_qa = quality in ("high", "final") if pacing_qa is None else pacing_qa
    return run_manim(scene_py, source_map, quality, output, scene_config, pacing=pacing, enforce_pacing_qa=enforce_pacing_qa)


def run_manim(
    scene_py: Path,
    source_map: Path,
    quality: str,
    output: Path,
    scene_config: Optional[object],
    pacing: PacingResult | None = None,
    enforce_pacing_qa: bool = False,
) -> Diagnostic:
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
    pacing_result = run_render_pacing_qa(output, pacing) if pacing else None
    if pacing:
        manifest["pacing_profile"] = pacing.profile
        manifest["source_duration"] = round(pacing.source_duration, 3)
        manifest["effective_duration"] = round(pacing.effective_duration, 3)
        manifest["actual_video_duration"] = pacing_result.get("actual_video_duration") if pacing_result else None
        write_json(manifest_path, manifest)
    if enforce_pacing_qa and pacing_result and not pacing_result.get("ok"):
        return error_result(
            "render",
            "pacing_qa_failed",
            "rendered video failed pacing QA",
            location={"file": str(output), "source_map": str(source_map)},
            details={"pacing_qa": pacing_result, **pacing.diagnostic_fields()},
        )
    fields = pacing.diagnostic_fields() if pacing else {}
    return ok_result(
        "render",
        scene_py=str(scene_py),
        source_map=str(source_map),
        output=str(output),
        stdout=result.stdout[-4000:],
        build_manifest=str(manifest_path),
        manifest=manifest,
        pacing_qa=pacing_result,
        actual_video_duration=pacing_result.get("actual_video_duration") if pacing_result else None,
        **fields,
    )
