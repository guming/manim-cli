# manim-video MVP Skill

Use this skill when a user asks an agent to create a Manim math teaching video.

## Workflow

1. Create a lesson project with `manim-cli init <project-dir>`.
2. Write the user brief to `brief.md`.
3. Generate `plan.json`, then run `manim-cli plan validate plan.json`.
4. Generate `storyboard.json`, then run `manim-cli storyboard validate storyboard.json`.
5. Generate `scene.json` using only `manim-cli manifest` capabilities.
6. Run `manim-cli validate scene.json`.
7. Run `manim-cli compile scene.json --out generated --profile preview --pacing teaching`.
8. Run `manim-cli render scene.json --quality low --pacing teaching --output renders/preview.mp4 --qa --pacing-qa`.
9. On failure, run `manim-cli diagnose diagnostics/render.json --source-map generated/scene.py.map.json`.
10. Modify the nearest upstream artifact. Do not edit `generated/scene.py`.
11. After user review, run `manim-cli render scene.json --quality high --pacing teaching --output renders/final.mp4 --qa`.

## Hard Rules

- Do not write Python scene code by hand.
- Do not edit `generated/scene.py`.
- Do not use unsupported MVP DSL features: Graph, VGroup, multi-target actions, params action schema, safe_expression.
- Prefer small scenes that validate and render before adding complexity.
- Treat render quality and pacing as independent. Never use `draft`, `low`, or `preview` to imply faster teaching pace.
- Use `teaching` for user-facing previews/finals, `preserve` for exact DSL timing, and `accelerated` only for explicit CI smoke tests.
- Mark important steps with `timing_role: derivation` or `timing_role: conclusion`; final answers and captions must remain visible for at least 2 seconds.
- Inspect `source_duration`, `effective_duration`, `effective_timeline`, `timing_changes`, and `pacing_qa` before accepting a video.
