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
```

Implemented Harness Core includes stable QA issues with fingerprints, source-map enrichment, bbox confidence, step-frame timing drift, static math lint, repair hints, no-render QA regression, render QA preflight, `slot_region`, and step-level `layout` actions.
