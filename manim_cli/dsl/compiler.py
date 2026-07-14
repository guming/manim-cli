from __future__ import annotations

import json
import py_compile
import traceback
from pathlib import Path
from typing import Any, Dict, Set

from manim_cli import __version__ as manim_cli_version
from manim_cli.build import build_manifest, content_hash, write_build_manifest
from manim_cli.dsl.cost import scene_cost
from manim_cli.dsl.layout import estimate_bbox, slot_center, slot_region
from manim_cli.dsl.models import COLORS, DIRECTIONS, RATE_FUNCS, SceneDef
from manim_cli.dsl.names import safe_var_name
from manim_cli.dsl.optimizer import MERGEABLE_ACTIONS, collect_mergeable_actions, optimize_scene
from manim_cli.dsl.registry import ACTION_REGISTRY, MOBJECT_REGISTRY, emit_position, emit_style
from manim_cli.dsl.splitting import storyboard_split_plans
from manim_cli.dsl.templates import layout_template_diagnostics
from manim_cli.dsl.validators import parse_and_validate_scene_data
from manim_cli.dsl.writer import CodeWriter
from manim_cli.jsonio import Diagnostic, error_result, load_json, ok_result, write_json
from manim_cli.render.bbox_probe import probe_scene_tex_bboxes

MATERIAL_LAYOUT_SCALE_THRESHOLD = 0.9


class CompileContext:
    def __init__(self, scene: SceneDef) -> None:
        self.scene = scene
        self.id_to_var: Dict[str, str] = {}
        self.var_to_id: Dict[str, str] = {}
        self.layout_changes: list[Dict[str, Any]] = layout_template_diagnostics(scene)
        self.layout_changes.extend({"change": "storyboard_split_plan", **plan} for plan in storyboard_split_plans(scene))
        self.compile_warnings: list[Dict[str, Any]] = []
        self.current_step_metadata: Dict[str, Any] = {}
        self.template_by_signature: Dict[str, str] = {}
        self.tex_probe_results = probe_scene_tex_bboxes(scene)
        used: Set[str] = set()
        for mob in scene.mobjects:
            var_name = safe_var_name(mob.id, used)
            self.id_to_var[mob.id] = var_name
            self.var_to_id[var_name] = mob.id

    def var_for(self, dsl_id: str) -> str:
        return self.id_to_var[dsl_id]

    def metadata_for_object(self, var_name: str) -> Dict[str, Any]:
        dsl_id = self.var_to_id.get(var_name)
        return {"object_ids": [dsl_id]} if dsl_id else {}

    def metadata_for_action(self, action: Any) -> Dict[str, Any]:
        metadata = dict(self.current_step_metadata)
        object_ids = []
        if action.target and not isinstance(action.target, list):
            object_ids.append(action.target)
        if action.to:
            object_ids.append(action.to)
        if object_ids:
            metadata["object_ids"] = object_ids
        return metadata


def compile_scene_file(scene_path: Path, out_dir: Path, profile: str = "strict", use_cache: bool = True) -> Diagnostic:
    if profile not in ("strict", "fast", "preview", "final", "debug"):
        return error_result("compile", "invalid_enum", "profile must be strict, fast, preview, final, or debug")
    try:
        raw = scene_path.read_bytes()
        scene_hash = content_hash(raw)
        data = load_json(scene_path)
    except Exception as exc:
        return error_result("compile", "invalid_json", str(exc), location={"file": str(scene_path)})

    parsed = parse_and_validate_scene_data(data, file=str(scene_path), base_dir=scene_path.parent, quality_gate="strict" if profile == "final" else "relaxed")
    validation = parsed.diagnostic
    if not validation.get("ok"):
        return validation
    try:
        return compile_scene(parsed.scene, out_dir, profile=profile, use_cache=use_cache, scene_hash=scene_hash)
    except Exception as exc:
        details = {"traceback": traceback.format_exc()} if profile == "debug" else None
        return error_result("compile", "compile_internal_error", str(exc), location={"file": str(scene_path)}, details=details)


def compile_scene(scene: SceneDef, out_dir: Path, profile: str = "strict", use_cache: bool = True, scene_hash: str | None = None) -> Diagnostic:
    if scene is None:
        return error_result("compile", "invalid_scene", "Scene did not parse successfully")
    scene = optimize_scene(scene, profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_py_path = out_dir / "scene.py"
    source_map_path = out_dir / "scene.py.map.json"
    cache_path = out_dir / ".compile-cache.json"
    manifest_path = out_dir / "build_manifest.json"
    scene_hash = scene_hash or content_hash(scene_canonical_json(scene).encode("utf-8"))
    manifest = build_manifest(scene_hash, profile)
    manim_version = manifest.get("manim_version") or "unknown"
    generator_hash = compiler_generator_hash()
    manifest["generator_hash"] = generator_hash
    cache_key = content_hash(f"{scene_hash}:{profile}:{manim_cli_version}:{manim_version}:{generator_hash}".encode("utf-8"))

    if use_cache and cache_path.exists() and scene_py_path.exists() and source_map_path.exists():
        cached = load_json(cache_path)
        if cached.get("cache_key") == cache_key:
            manifest = write_build_manifest(manifest_path, scene_hash, profile)
            manifest["generator_hash"] = generator_hash
            write_json(manifest_path, manifest)
            return ok_result(
                "compile",
                scene_py=str(scene_py_path),
                source_map=str(source_map_path),
                scene_name="GeneratedScene",
                cached=True,
                profile=profile,
                cache_key=cache_key,
                cost=scene_cost(scene),
                layout_changes=[],
                warnings=cached.get("compile_warnings", []),
                build_manifest=str(manifest_path),
                manifest=manifest,
            )

    ctx = CompileContext(scene)
    writer = CodeWriter()
    imports = collect_imports(scene)
    emit_header(writer, imports, scene)
    emit_mobjects(writer, ctx, scene)
    emit_steps(writer, ctx, scene)

    scene_py_path.write_text(writer.render(), encoding="utf-8")
    write_json(source_map_path, writer.source_map(scene_py_path.name))

    if profile not in ("fast", "preview"):
        try:
            py_compile.compile(str(scene_py_path), doraise=True)
        except py_compile.PyCompileError as exc:
            return error_result(
                "compile",
                "python_syntax_error",
                str(exc),
                location={"file": str(scene_py_path), "source_map": str(source_map_path)},
            )

    write_json(
        cache_path,
        {
            "cache_key": cache_key,
            "scene_hash": scene_hash,
            "profile": profile,
            "manim_cli_version": manim_cli_version,
            "manim_version": manim_version,
            "generator_hash": generator_hash,
            "compile_warnings": ctx.compile_warnings,
            "scene_py": str(scene_py_path),
            "source_map": str(source_map_path),
        },
    )
    manifest = write_build_manifest(manifest_path, scene_hash, profile)
    manifest["generator_hash"] = generator_hash
    write_json(manifest_path, manifest)

    return ok_result(
        "compile",
        scene_py=str(scene_py_path),
        source_map=str(source_map_path),
        scene_name="GeneratedScene",
        cached=False,
        profile=profile,
        cache_key=cache_key,
        cost=scene_cost(scene),
        layout_changes=ctx.layout_changes,
        warnings=ctx.compile_warnings,
        build_manifest=str(manifest_path),
        manifest=manifest,
    )


def compiler_generator_hash() -> str:
    paths = [
        Path(__file__),
        Path(__file__).with_name("layout.py"),
        Path(__file__).with_name("registry.py"),
        Path(__file__).with_name("templates.py"),
    ]
    payload = b"".join(path.read_bytes() for path in paths)
    return content_hash(payload)


def collect_imports(scene: SceneDef) -> Set[str]:
    imports: Set[str] = set()
    manim_names = used_manim_constants(scene)
    if manim_names:
        imports.add("from manim import " + ", ".join(sorted(manim_names)))
    for mob in scene.mobjects:
        imports.update(MOBJECT_REGISTRY[mob.type].imports)
    for step in scene.steps:
        for action in step.actions:
            imports.update(ACTION_REGISTRY[action.type].imports)
    return imports


def used_manim_constants(scene: SceneDef) -> Set[str]:
    names: Set[str] = set()
    for color in collect_colors(scene):
        if color in COLORS:
            names.add(color)
    for direction in collect_directions(scene):
        if direction in DIRECTIONS:
            names.add(direction)
    for rate_func in collect_rate_funcs(scene):
        if rate_func in RATE_FUNCS:
            names.add(rate_func)
    return names


def collect_colors(scene: SceneDef) -> Set[str]:
    colors: Set[str] = set()
    for mob in scene.mobjects:
        if mob.style:
            for value in (mob.style.color, mob.style.fill_color, mob.style.stroke_color):
                if value:
                    colors.add(value)
    for step in scene.steps:
        for action in step.actions:
            if action.color:
                colors.add(action.color)
    return colors


def collect_directions(scene: SceneDef) -> Set[str]:
    directions: Set[str] = set()
    for mob in scene.mobjects:
        if not mob.position:
            continue
        if mob.position.edge:
            directions.add(mob.position.edge)
        if mob.position.direction:
            directions.add(mob.position.direction)
    return directions


def collect_rate_funcs(scene: SceneDef) -> Set[str]:
    return {action.rate_func for step in scene.steps for action in step.actions if action.rate_func}


def emit_header(writer: CodeWriter, imports: Set[str], scene: SceneDef) -> None:
    writer.add("# Auto-generated by manim-cli. Do not edit manually.")
    writer.add("import numpy as np")
    writer.add("from manim import Scene, config")
    for imp in sorted(imports):
        writer.add(imp)
    writer.add()
    writer.add(f"config.background_color = {scene.config.background_color!r}")
    writer.add(f"config.frame_height = {scene.config.frame_height!r}")
    writer.add()
    writer.add("class GeneratedScene(Scene):")
    writer.add("    def construct(self):")


def emit_mobjects(writer: CodeWriter, ctx: CompileContext, scene: SceneDef) -> None:
    if not scene.mobjects and not scene.steps:
        writer.add("        pass")
        return
    writer.add("        # Mobjects")
    for index, mob in enumerate(scene.mobjects):
        path = f"$.mobjects[{index}]"
        spec = MOBJECT_REGISTRY[mob.type]
        var_name = ctx.var_for(mob.id)
        signature = mobject_signature(mob)
        template_var = ctx.template_by_signature.get(signature)
        if template_var:
            writer.add(f"        {var_name} = {template_var}.copy()", path=path, symbol=var_name, metadata={"object_ids": [mob.id], "template_object": ctx.var_to_id.get(template_var)})
            ctx.layout_changes.append({"object": mob.id, "change": "copy_from_template", "template_object": ctx.var_to_id.get(template_var), "reason": "identical type/args/style"})
        else:
            args = spec.args_model.model_validate(mob.args)
            spec.emit(var_name, args, ctx, writer, path)
            ctx.template_by_signature[signature] = var_name
        emit_style(var_name, mob.style, writer, path)
        emit_position(var_name, mob.position, ctx, writer, path)
        emit_layout(var_name, mob, ctx, scene, writer, path)
        if mob.render_role == "static_background":
            writer.add(f"        self.add({var_name})", path=f"{path}.render_role", symbol=f"add({var_name})", metadata={"object_ids": [mob.id]})
    writer.add()


def mobject_signature(mob: Any) -> str:
    style = mob.style.model_dump(exclude_none=True) if mob.style else {}
    payload = {"type": mob.type, "args": mob.args, "style": style}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def scene_canonical_json(scene: SceneDef) -> str:
    # Deterministic serialization used for the scene_hash fallback. Pydantic v2's
    # model_dump_json has no sort_keys option, so dump to a json-mode dict and let
    # stdlib json sort every key (top-level and nested). by_alias keeps the $schema
    # alias stable. Output is order-independent: two scenes built from dicts with
    # different insertion order produce identical bytes.
    return json.dumps(scene.model_dump(mode="json", by_alias=True), ensure_ascii=False, sort_keys=True)


def emit_layout(var_name: str, mob: Any, ctx: CompileContext, scene: SceneDef, writer: CodeWriter, path: str) -> None:
    if not mob.layout:
        return
    center = slot_center(scene, mob.layout.slot)
    writer.add(f"        {var_name}.move_to(np.array({list(center)!r}))", path=f"{path}.layout.slot", symbol=f"{var_name}.move_to")
    box = estimate_bbox(scene, mob, tex_probe_results=ctx.tex_probe_results)
    if mob.type in ("Text", "Tex") and box:
        region = slot_region(scene, mob.layout.slot)
        max_width = region.width
        max_height = region.height
        width_scale = max_width / box.width if box.width > max_width else 1.0
        height_scale = max_height / box.height if box.height > max_height else 1.0
        scale = min(width_scale, height_scale)
        if scale < 1.0:
            fit_dimensions = []
            if width_scale < 1.0:
                fit_dimensions.append("width")
            if height_scale < 1.0:
                fit_dimensions.append("height")
            writer.add(f"        {var_name}.scale({scale!r})", path=f"{path}.layout", symbol=f"{var_name}.scale")
            change = {
                "object": mob.id,
                "change": "fit_to_region",
                "slot": mob.layout.slot,
                "region": {"left": round(region.left, 3), "bottom": round(region.bottom, 3), "right": round(region.right, 3), "top": round(region.top, 3)},
                "fit_dimensions": fit_dimensions,
                "from": {"width": round(box.width, 3), "height": round(box.height, 3)},
                "to": {"width": round(max_width, 3), "height": round(max_height, 3)},
                "scale": round(scale, 3),
                "width_scale": round(width_scale, 3),
                "height_scale": round(height_scale, 3),
                "reason": f"{mob.layout.slot} slot region exceeded",
                "bbox_confidence": box.confidence,
                "bbox_method": box.method,
            }
            ctx.layout_changes.append(change)
            if "height" in fit_dimensions and scale < MATERIAL_LAYOUT_SCALE_THRESHOLD:
                ctx.compile_warnings.append(
                    {
                        "type": "layout_material_scale_down",
                        "object": mob.id,
                        "slot": mob.layout.slot,
                        "fit_dimensions": fit_dimensions,
                        "scale": round(scale, 3),
                        "threshold": MATERIAL_LAYOUT_SCALE_THRESHOLD,
                        "bbox_confidence": box.confidence,
                        "bbox_method": box.method,
                        "message": "Layout fitting reduced object scale materially; consider a larger region or splitting the content.",
                    }
                )


def slot_max_width(scene: SceneDef, slot: str) -> float:
    region = slot_region(scene, slot)
    return region.width


def emit_steps(writer: CodeWriter, ctx: CompileContext, scene: SceneDef) -> None:
    writer.add("        # Steps")
    for step_index, step in enumerate(scene.steps):
        writer.add(f"        # Step: {step.name}")
        action_index = 0
        while action_index < len(step.actions):
            group = collect_mergeable_actions(step.actions, action_index)
            path = f"$.steps[{step_index}].actions[{action_index}]"
            ctx.current_step_metadata = {
                "step_id": step.id or f"step_{step_index}",
                "step_index": step_index,
                "action_index": action_index,
                "narration_cue_id": step.narration_cue_id,
                "storyboard_event_id": step.storyboard_event_id,
            }
            if len(group) > 1:
                emit_merged_actions(group, ctx, writer, path)
                action_index += len(group)
                continue
            action = step.actions[action_index]
            ACTION_REGISTRY[action.type].emit(action, ctx, writer, path)
            action_index += 1
        if step.wait_after is not None:
            writer.add(f"        self.wait({step.wait_after!r})", path=f"$.steps[{step_index}].wait_after", symbol="wait_after", metadata={"step_id": step.id or f"step_{step_index}", "step_index": step_index, "narration_cue_id": step.narration_cue_id, "storyboard_event_id": step.storyboard_event_id})


def emit_merged_actions(actions: list[Any], ctx: CompileContext, writer: CodeWriter, path: str) -> None:
    animation = MERGEABLE_ACTIONS[actions[0].type]
    targets = ", ".join(f"{animation}({ctx.var_for(action.target)})" for action in actions)
    kwargs = []
    if actions[0].run_time is not None:
        kwargs.append(f"run_time={actions[0].run_time!r}")
    if actions[0].rate_func:
        kwargs.append(f"rate_func={actions[0].rate_func}")
    suffix = "" if not kwargs else ", " + ", ".join(kwargs)
    metadata = dict(ctx.current_step_metadata)
    metadata["object_ids"] = [action.target for action in actions if action.target and not isinstance(action.target, list)]
    writer.add(f"        self.play({targets}{suffix})", path=path, symbol=f"merged_{actions[0].type}", metadata=metadata)
