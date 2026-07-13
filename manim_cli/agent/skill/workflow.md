# manim-cli MVP Agent Workflow

The MVP artifact chain is:

```text
brief.md -> plan.json -> storyboard.json -> scene.json -> generated/scene.py -> renders/preview.mp4
```

When a command fails, repair the closest upstream artifact:

| Failure | Repair |
| --- | --- |
| plan validate | `plan.json` |
| storyboard validate | `storyboard.json` |
| scene validate | `scene.json` |
| compile | `scene.json` unless it is a compiler bug |
| render | `scene.json`, unless dependency diagnostics require user action |

