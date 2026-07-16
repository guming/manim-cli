from __future__ import annotations

import math
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Callable, Dict, Optional

from manim_cli.dsl.fingerprints import layout_fingerprint, memory_revision
from manim_cli.dsl.knowledge import build_repair_memory_context, policy_warnings, retrieve_typed_top_k, scene_features
from manim_cli.dsl.models import SceneDef


DEFAULT_TARGET_P95_MS = 50.0
DEFAULT_CI_HARD_LIMIT_P95_MS = 250.0


def benchmark_layout_memory(
    scene: SceneDef,
    base_dir: Optional[Path],
    iterations: int = 30,
    target_p95_ms: float = DEFAULT_TARGET_P95_MS,
    hard_limit_p95_ms: float = DEFAULT_CI_HARD_LIMIT_P95_MS,
) -> Dict[str, Any]:
    if iterations < 3:
        raise ValueError("iterations must be at least 3")
    operations: Dict[str, Callable[[], object]] = {
        "feature_extraction": lambda: scene_features(scene),
        "policy_matching": lambda: policy_warnings(scene, base_dir, profile="relaxed"),
        "typed_retrieval": lambda: retrieve_typed_top_k(scene, base_dir),
        "repair_context": lambda: build_repair_memory_context(scene, base_dir),
        "layout_fingerprint": lambda: layout_fingerprint(scene),
        "memory_revision": lambda: memory_revision(base_dir),
    }
    results = {
        name: benchmark_operation(operation, iterations=iterations, target_p95_ms=target_p95_ms, hard_limit_p95_ms=hard_limit_p95_ms)
        for name, operation in operations.items()
    }
    return {
        "iterations": iterations,
        "target_p95_ms": target_p95_ms,
        "hard_limit_p95_ms": hard_limit_p95_ms,
        "operations": results,
        "target_met": all(result["target_met"] for result in results.values()),
        "hard_gate_passed": all(result["hard_gate_passed"] for result in results.values()),
    }


def benchmark_operation(
    operation: Callable[[], object],
    iterations: int,
    target_p95_ms: float,
    hard_limit_p95_ms: float,
) -> Dict[str, Any]:
    operation()
    samples_ms = []
    for _ in range(iterations):
        started = perf_counter_ns()
        operation()
        samples_ms.append((perf_counter_ns() - started) / 1_000_000.0)
    samples_ms.sort()
    p50 = percentile(samples_ms, 0.50)
    p95 = percentile(samples_ms, 0.95)
    return {
        "p50_ms": round(p50, 4),
        "p95_ms": round(p95, 4),
        "max_ms": round(samples_ms[-1], 4),
        "target_met": p95 <= target_p95_ms,
        "hard_gate_passed": p95 <= hard_limit_p95_ms,
    }


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute percentile of empty values")
    index = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * quantile) - 1))
    return sorted_values[index]
