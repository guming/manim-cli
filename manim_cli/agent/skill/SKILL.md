---
name: manim-video
description: Create, validate, render, and repair Manim-based mathematical teaching videos through the manim-cli DSL. Use for equation derivations, theorem explanations, geometric constructions, mathematical graphs, animated notation or diagrams, and high-signal requests such as "Manim 视频", "数学教学视频", "勾股定理", "公式推导", or "几何证明". Do not use for general educational videos without meaningful mathematical visualization.
---

# Manim Video

Build through `manim-cli` artifacts. Do not hand-write Manim Python.

Read before acting:

- Read [workflow.md](workflow.md) for commands, modes, gates, and failure routing.
- Read [references/artifact-examples.md](references/artifact-examples.md) before authoring a new project.
- Read [references/authoring-guide.md](references/authoring-guide.md) when designing or reviewing a scene.
- Read [references/troubleshooting.md](references/troubleshooting.md) when a command fails.

## Start

1. Detect a working `manim-cli` entry point and run `manim-cli manifest`.
2. For new artifacts, inspect `manim-cli schema plan`, `schema storyboard`, and `schema scene`.
3. Use `manim-cli example project --output <dir>` when a concrete starting point is useful.
4. Select a mode:
   - `interactive`: run one gate at a time and pause for approval. Use this by default for compatibility.
   - `autonomous`: continue through passing gates when the user explicitly requests autonomous completion.
5. Select the requested output: preview, final, review-first, or CI smoke.

## Non-Negotiable Rules

- Edit only `brief.md`, `plan.json`, `storyboard.json`, and `scene.json`.
- Never edit generated Python, source maps, diagnostics, QA reports, or rendered media.
- Validate every artifact before using it downstream.
- Treat the current manifest and schema output as authoritative.
- Use `teaching` pacing for user-facing output and `accelerated` only for explicit CI smoke tests.
- Repair the closest editable upstream artifact; do not patch generated output.
- Classify failures as artifact, environment/dependency, or probable compiler defects before repairing.

## Deliver

Return the preview or final video path, changed source artifacts, passed gates, and unresolved warnings or exact dependency blockers.
