# Authoring Guide

## Teaching

- Give each scene one clear learning goal.
- Establish symbols and context before derivation.
- Make each visual change serve one teaching intent.
- Introduce few new symbols or focal points at once.
- Give the conclusion stronger hierarchy than intermediate work.

## Layout

- Prefer layout templates, roles, and slots over absolute coordinates.
- Keep formula anchors stable across transformations.
- Separate the main formula, diagram, annotation, and conclusion spatially.
- Reduce content before reducing text or formula size.

## Timing

- Mark reasoning with `timing_role: derivation`.
- Mark final results with `timing_role: conclusion`.
- Keep important formulas and conclusions visible long enough to read.
- Treat render quality and pacing as independent controls.

## Review

Agent or human review must check legibility, clipping, overlap, continuity, hierarchy, symbol consistency, valid algebraic transformations, and alignment with the brief. These are not automatic gates unless a CLI command explicitly reports them as such.

Use available evidence when relevant:

```bash
manim-cli visual-qa keyframe <pixels.json>
manim-cli visual-qa bbox-probe "<formula>"
manim-cli visual-qa render-smoke scene.json --out smoke.mp4
manim-cli qa-eval <regression-dir>
```
