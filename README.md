# manim-cli

`manim-cli` is the execution layer for **Manim Harness**: a quality compiler and CI layer for agent-generated Manim videos.

It validates a restricted Scene DSL, compiles it to deterministic Manim Python, and drives preview/final renders from agent workflows. The product direction is to make AI-generated Manim reliable through QA gates, layout slots, source maps, visual QA, repair hints, and regression scenes.

## Current CLI surface

Core workflow:

```bash
manim-cli validate scene.json
manim-cli qa scene.json --profile strict --out feedback
manim-cli compile scene.json --out generated --profile preview
manim-cli render scene.json --quality low --output renders/preview.mp4 --qa
manim-cli render scene.json --quality draft --pacing teaching --output renders/preview.mp4 --qa
```

Diagnostics and regression:

```bash
manim-cli source-map lookup generated/scene.py.map.json --object-id eq_main
manim-cli diagnose diagnostics/render.json --source-map generated/scene.py.map.json
manim-cli regression run tests/regression --out regression-out
manim-cli qa-eval tests/regression
```

Visual QA helpers:

```bash
manim-cli visual-qa keyframe pixels.json
manim-cli visual-qa bbox-probe "\\frac{a}{b}"
manim-cli visual-qa toolchain-status
manim-cli visual-qa render-smoke scene.json --expect measured_safe --out smoke.mp4
```

Layout memory:

```bash
manim-cli knowledge retrieve scene.json --issue-type layout_overlap
manim-cli knowledge benchmark scene.json
manim-cli memory list --scope project --base-dir .manim-cli/layout_memory
manim-cli memory review <failure_id> --scope project --base-dir .manim-cli/layout_memory
manim-cli memory promote failures/reviewed/failure.json --scope project --base-dir .manim-cli/layout_memory
manim-cli memory activate <policy_id> --scope project --base-dir .manim-cli/layout_memory
manim-cli memory rebuild-index --scope project --base-dir .manim-cli/layout_memory
manim-cli memory clean --scope project --base-dir .manim-cli/layout_memory --inbox --older-than 90
```

`memory clean` is a dry run unless `--apply` is supplied. Promoted policies are candidates until explicitly activated.

Implemented Harness Core includes stable QA issues with fingerprints, source-map enrichment, bbox confidence, step-frame timing drift, static math lint, repair hints, no-render QA regression, render QA preflight, `slot_region`, step-level `layout` actions, YAML/JSON layout memory, active-policy diagnostics, budgeted repair context, canonical layout-analysis caching, and memory lifecycle commands.

Render quality and teaching pace are independent. `--quality` controls resolution/FPS; `--pacing preserve|teaching|accelerated` controls the effective timeline. The default render pacing is `teaching`, which preserves explicit durations and adds minimum reading/hold time for formulas and conclusions. Use `--pacing accelerated` only for CI smoke or deliberately fast previews.
