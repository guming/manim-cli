# Manim CLI Workflow

## Modes

- `interactive`: execute one command, report its result, then wait for approval before the next command.
- `autonomous`: continue while gates pass. Pause only for material ambiguity, expensive optional work, missing authority, or a blocker.

Use `interactive` unless the user explicitly requests autonomous completion.

## Artifact Chain

```text
brief.md
  -> plan.json
  -> storyboard.json
  -> scene.json
  -> generated/scene.py
  -> renders/preview.mp4
  -> renders/final.mp4
```

## Authoring and Gate Sequence

```bash
manim-cli manifest
manim-cli schema plan
manim-cli schema storyboard
manim-cli schema scene
manim-cli plan validate plan.json
manim-cli storyboard validate storyboard.json
manim-cli validate scene.json
manim-cli compile scene.json --out generated --profile preview --pacing teaching
manim-cli render scene.json --quality low --pacing teaching --output renders/preview.mp4 --qa --pacing-qa
```

For an explicitly requested final, continue after the preview passes its gates. In interactive mode, preserve the approval boundary.

```bash
manim-cli render scene.json --quality high --pacing teaching --output renders/final.mp4 --qa --pacing-qa
```

For explicit CI smoke work only, use low-cost quality and `--pacing accelerated`.

## Gate Rules

- Do not use an artifact downstream until its validation returns `"ok": true`.
- After a repair, rerun the failed gate and every affected downstream gate.
- Compile must emit `generated/scene.py` and `generated/scene.py.map.json`.
- Preview and final acceptance require render QA and pacing QA.
- Treat visual and mathematical review as agent/human checks unless a command reports a deterministic gate result.

## Failure Routing

| Failure | Route |
| --- | --- |
| plan validation | Repair `plan.json` |
| storyboard validation | Repair `storyboard.json` |
| scene validation or QA | Repair `scene.json` |
| compile with valid scene | Preserve a minimal reproduction; report probable compiler defect |
| render preflight | Repair the environment or report the exact dependency blocker |
| render Manim error | Read diagnostics and source map, then repair the closest upstream artifact |

When present, read `feedback/agent_prompt.md` before full reports. Diagnose render failures with:

```bash
manim-cli diagnose diagnostics/render.json --source-map generated/scene.py.map.json
```

## Output Decision

| Request | Stop condition |
| --- | --- |
| preview | Preview gates and review complete |
| final | Final gates and review complete |
| review first | Preview delivered and user review requested |
| CI smoke | Requested smoke gate completes |
