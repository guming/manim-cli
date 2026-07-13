# QA Issue Schema

`manim-cli qa` emits a stable machine-readable report:

```json
{
  "ok": false,
  "phase": "qa",
  "profile": "strict",
  "score": 75,
  "summary": {"error": 1, "warning": 0, "info": 0, "total": 1},
  "issues": []
}
```

Each issue uses this contract:

```json
{
  "issue_id": "qa-<first 12 chars of fingerprint>",
  "fingerprint": "<sha256 stable identity>",
  "type": "layout_overlap",
  "severity": "error",
  "confidence": "high",
  "source": "layout_static",
  "message": "Visible objects overlap: a, b",
  "repair_scope": "visual_action",
  "location": {
    "file": "scene.json",
    "dsl_path": "$.steps[0].actions[1]",
    "step_id": "intro",
    "step_index": 0,
    "action_index": 1,
    "object_ids": ["a", "b"],
    "narration_cue_id": "cue_intro",
    "storyboard_event_id": "event_intro",
    "storyboard_frame_id": "frame_intro"
  },
  "repair_hints": [
    {
      "message": "Move one object to a different layout slot/position, or split the step.",
      "repair_scope": "visual_action",
      "dsl_path": "$.steps[0].actions[1]",
      "target": "a,b"
    }
  ],
  "details": {}
}
```

Stable identity rules:

- `fingerprint` is derived from issue type, structured location, object ids, and stable details.
- `issue_id` is presentation-friendly and derived from the fingerprint.
- Baselines and repair loops should compare `fingerprint` first, then `issue_id`, then `type`.
- `message` is not stable and must not be used for regression comparison.

Confidence values:

- `high`: deterministic static check, suitable for strict/final failure.
- `medium`: heuristic static check.
- `unknown_static`: static analysis cannot know the truth; usually requires preview Visual QA or quick LaTeX probe.

Source values:

- `layout_static`
- `math_lint`
- `timing_static`
- `pedagogy_alignment`
- `qa`

## Related Commands

```bash
manim-cli qa scene.json --profile strict --out feedback
manim-cli qa-eval tests/regression
manim-cli regression run tests/regression --out regression-out
manim-cli source-map lookup generated/scene.py.map.json --line 42
```

## Baseline Files

`expected_qa.json` supports three levels of precision:

```json
{
  "fingerprints": ["<stable issue fingerprint>"],
  "known_false_positives": ["<fingerprint or issue type>"]
}
```

For coarse early baselines, issue type matching is also accepted:

```json
{
  "issue_types": ["layout_overlap", "math_denominator_zero"]
}
```

When possible, prefer fingerprints over issue types. Type-only baselines are useful for seed eval scenes, but they cannot detect severity or location regressions precisely.
