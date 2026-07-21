# Artifact Examples

## Canonical Project

Use the bundled `pythagorean_theorem` project as the canonical teaching example:

```bash
manim-cli example project --output <project-dir>
```

Inspect its files in this order:

1. `brief.md`: user intent and teaching constraints.
2. `plan.json`: learning goals, teaching sequence, symbol ledger, and narration cues.
3. `storyboard.json`: frames that reference the plan and group narration with visual events.
4. `scene.json`: renderable objects and actions linked back to plan/storyboard intent.

Use `manim-cli example plan`, `example storyboard`, or `example scene` to print one artifact as structured JSON.

## Reference Discipline

- Keep IDs stable and semantic across artifacts.
- Make every storyboard frame serve a teaching-sequence goal.
- Use `narration_cue_id` and `storyboard_event_id` where the schema supports them.
- Keep `plan_ref` and `storyboard_ref` accurate.
- Copy the structure, not the theorem-specific content.

Before editing, inspect the current contracts:

```bash
manim-cli schema plan
manim-cli schema storyboard
manim-cli schema scene
manim-cli manifest
```

The runtime schema overrides any stale detail in an example.
