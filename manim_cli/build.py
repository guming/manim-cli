from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from manim_cli import __version__
from manim_cli.jsonio import write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def command_version(command: str, *args: str) -> Optional[str]:
    if not shutil.which(command):
        return None
    try:
        result = subprocess.run([command, *args], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    text = (result.stdout or result.stderr or "").strip()
    return text.splitlines()[0] if text else None


def build_manifest(scene_hash: str, compile_profile: str, render_profile: Optional[str] = None) -> Dict[str, Any]:
    return {
        "manim_cli_version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "manim_version": command_version("manim", "--version"),
        "latex_version": command_version("latex", "--version"),
        "ffmpeg_version": command_version("ffmpeg", "-version"),
        "scene_hash": scene_hash,
        "compile_profile": compile_profile,
        "render_profile": render_profile,
    }


def write_build_manifest(path: Path, scene_hash: str, compile_profile: str, render_profile: Optional[str] = None) -> Dict[str, Any]:
    manifest = build_manifest(scene_hash, compile_profile, render_profile)
    write_json(path, manifest)
    return manifest
