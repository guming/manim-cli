# Troubleshooting

## Artifact Error

Examples include invalid JSON shape, missing required fields, unknown IDs, unsupported capabilities, and layout or timing QA failures.

Repair the closest editable artifact, rerun the failed gate, then rerun affected downstream gates.

## Environment or Dependency Error

Examples include a missing CLI entry point, incompatible Pydantic, missing PyYAML, Manim, LaTeX, ffmpeg, or an unwritable output directory.

Repair the environment only when authorized. Otherwise return the exact command, exit status, and diagnostic message. Do not change `scene.json` to guess around an environment failure.

## Probable Compiler Defect

When a validated scene reliably triggers a compiler exception:

1. Preserve the smallest reproducing artifact.
2. Preserve structured output and diagnostics.
3. Record CLI, Python, and Manim versions.
4. Report a probable compiler defect.
5. Do not edit generated Python as a workaround.
