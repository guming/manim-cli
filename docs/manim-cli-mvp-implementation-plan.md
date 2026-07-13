# manim-cli MVP 实施范围与落地技术方案

## 1. MVP 目标

`manim-cli` MVP 的目标不是覆盖 Manim，也不是让用户学习 JSON DSL，而是先验证一条稳定的 Agent 工作链路：

```text
User brief
  -> Agent skill workflow
  -> TeachingPlan
  -> Storyboard
  -> Scene DSL
  -> manim-cli validate
  -> manim-cli compile
  -> manim-cli render low
  -> diagnostic / repair
  -> manim-cli render high
  -> video
```

MVP 的交付标准：

- Agent 不直接写 Python。
- 普通用户不直接写 Python 或 JSON。
- Scene DSL 可以表达 2-3 类常见数学短视频。
- `scene.json -> scene.py -> video` 跑通。
- validate / compile / render 都返回结构化 JSON。
- 渲染失败能尽量映射回 DSL path。
- Skill workflow 固化文件、命令和失败处理规则。

## 2. MVP 明确取舍

### 2.1 做什么

MVP 只做端到端闭环和高频教学场景：

- 公式书写和推导。
- 基础几何对象展示和变换。
- 坐标系中的点、线、箭头向量。
- 标题、标签、旁白 cue、分镜事件引用。
- 低清预览、高清交付和基础错误诊断。

### 2.2 暂不做什么

以下内容推迟到 Phase 1：

- `Graph` 函数绘图。
- 安全表达式 AST 解析。
- `NumberPlane`、`Brace`、`SurroundingRectangle` 等扩展对象。
- 复杂 camera movement。
- 复杂 3D。
- updater、lambda、自定义 animation class。
- LLM 内置调用。CLI 保持纯工具，不直接调用模型。
- 自动视觉审美判断。MVP 只做空白帧、越界、基础截图抽取的预留接口。

`Graph` 虽然对函数可视化重要，但它会引入表达式安全、函数采样、坐标轴绑定和渲染稳定性问题。MVP 先用 `Axes + Dot + Line + Arrow + Tex` 覆盖向量和基础坐标讲解。

## 3. MVP 对象与动作范围

### 3.1 Mobject MVP

MVP 支持 8 个对象：

| 类型 | 用途 | MVP args |
|------|------|----------|
| `Tex` | 公式、数学符号 | `tex`, `font_size`, `alignment` |
| `Text` | 中文/英文标题和说明 | `text`, `font`, `font_size` |
| `Circle` | 基础几何 | `radius` |
| `Square` | 基础几何 | `side_length` |
| `Line` | 线段、辅助线 | `start`, `end`, `coordinate_space`, `axes` |
| `Arrow` | 向量、方向提示 | `start`, `end`, `coordinate_space`, `axes`, `buff`, `tip_length` |
| `Dot` | 点、顶点、标记 | `point`, `coordinate_space`, `axes`, `radius` |
| `Axes` | 坐标系 | `x_range`, `y_range`, `width`, `height` |

`VGroup` 不进第一版核心对象。MVP 可以先通过多个 action 顺序处理对象，避免 ownership、重复 add、group transform 生命周期问题。Phase 1 再加入 `VGroup`。

### 3.2 Style MVP

通用 `style`：

```json
{
  "color": "WHITE",
  "fill_color": "BLUE",
  "fill_opacity": 0.4,
  "stroke_color": "WHITE",
  "stroke_width": 3,
  "opacity": 1
}
```

颜色支持：

- 命名颜色：`WHITE`, `BLACK`, `BLUE`, `YELLOW`, `RED`, `GREEN`, `GOLD`, `PURPLE`, `TEAL`
- Hex：`#RRGGBB`

样式合并优先级：

```text
explicit mobject.style
  > type default
  > visual_theme default
  > hardcoded fallback
```

MVP 只实现 `casual_3b1b` 主题，避免主题矩阵拉大测试面。

### 3.3 Position MVP

MVP 支持 4 种 position：

| 模式 | 字段 |
|------|------|
| `absolute` | `point` |
| `edge` | `edge`, `buff` |
| `relative` | `target`, `direction`, `buff` |
| `align_to` | `target`, `edge` |

`corner` 可以由 `edge` 和后续扩展覆盖，MVP 暂缓。

方向 enum：

```text
UP, DOWN, LEFT, RIGHT, UL, UR, DL, DR, ORIGIN
```

### 3.4 Action MVP

Action 统一采用扁平 schema，不再使用 `params` 包裹。

```json
{
  "type": "transform",
  "target": "eq_1",
  "to": "eq_2",
  "run_time": 1.2,
  "match_by": "tex"
}
```

MVP 支持 9 个动作：

| 类型 | 编译目标 | 字段 |
|------|----------|------|
| `add` | `self.add(...)` | `target` |
| `remove` | `self.remove(...)` | `target` |
| `write` | `self.play(Write(...))` | `target`, `run_time`, `rate_func` |
| `fade_in` | `self.play(FadeIn(...))` | `target`, `run_time`, `rate_func` |
| `fade_out` | `self.play(FadeOut(...))` | `target`, `run_time`, `rate_func` |
| `show_creation` | `self.play(Create(...))` | `target`, `run_time`, `rate_func` |
| `transform` | `Transform` / `TransformMatchingTex` | `target`, `to`, `run_time`, `match_by` |
| `highlight` | `Indicate` 或临时变色 | `target`, `color`, `run_time` |
| `wait` | `self.wait(...)` | `duration` |

约束：

- `add` / `remove` 不接受 `run_time`。
- `wait` 只接受 `duration`。
- `target` MVP 只接受单个 id，不接受数组。多对象动画由多个 action 表达。
- `rate_func` 只允许 `smooth`, `linear`, `there_and_back`。
- `match_by` 只允许 `none`, `tex`，默认 `none`。

## 4. Scene DSL MVP

顶层结构：

```json
{
  "$schema": "https://manim-cli/schema/v1/scene.json",
  "version": "1.0",
  "name": "linear_algebra_vectors",
  "description": "Explain vectors as arrows.",
  "plan_ref": "plan.json",
  "storyboard_ref": "storyboard.json",
  "config": {
    "resolution": [1920, 1080],
    "frame_height": 8,
    "background_color": "#1e1e1e",
    "fps": 30,
    "visual_theme": "casual_3b1b"
  },
  "mobjects": [],
  "steps": []
}
```

关键决定：

- `version` 必填，MVP 固定为 `"1.0"`。
- `plan_ref` / `storyboard_ref` 是 artifact 路径，不是自由文本 id。
- `mobjects` 中 id 全局唯一。
- 所有 `args` 使用类型专属 schema，禁止未知字段。
- 所有 action 使用类型专属 schema，禁止未知字段。
- DSL 不允许 Python 表达式、import、任意 kwargs、任意 Manim 类名。

## 5. Agent Skill Workflow MVP

MVP 先实现 Mode B：Codex / Claude Code 通过 skill 调用 `manim-cli`。

### 5.1 项目目录

Agent 每次创建一个 lesson project：

```text
lesson-project/
├── project.json
├── brief.md
├── plan.json
├── storyboard.json
├── scene.json
├── generated/
│   ├── scene.py
│   └── scene.py.map.json
├── renders/
│   ├── preview.mp4
│   └── final.mp4
├── diagnostics/
│   ├── validate.json
│   ├── compile.json
│   └── render.json
└── feedback/
    └── latest.md
```

### 5.2 project.json

```json
{
  "id": "linear_algebra_vectors",
  "created_by": "agent",
  "manim_cli_version": "0.1.0",
  "status": "draft|preview|final|failed",
  "artifacts": {
    "brief": "brief.md",
    "plan": "plan.json",
    "storyboard": "storyboard.json",
    "scene": "scene.json",
    "generated_scene": "generated/scene.py",
    "source_map": "generated/scene.py.map.json",
    "preview": "renders/preview.mp4",
    "final": "renders/final.mp4"
  }
}
```

### 5.3 固定流程

```text
1. 写入 brief.md
2. 生成 plan.json
3. manim-cli plan validate plan.json
4. 生成 storyboard.json
5. manim-cli storyboard validate storyboard.json
6. 生成 scene.json
7. manim-cli validate scene.json
8. manim-cli compile scene.json --out generated
9. manim-cli render scene.json --quality low --output renders/preview.mp4
10. 如失败，manim-cli diagnose diagnostics/render.json --source-map generated/scene.py.map.json
11. Agent 修改最近上游 artifact，不修改 generated/scene.py
12. 用户确认后，manim-cli render scene.json --quality high --output renders/final.mp4
```

失败修复规则：

| 失败阶段 | Agent 修改对象 |
|----------|----------------|
| `plan validate` | `plan.json` |
| `storyboard validate` | `storyboard.json` |
| `scene validate` | `scene.json` |
| `compile` | `scene.json`，如果是 compiler bug 则停止 |
| `render` | 优先 `scene.json`，LaTeX/依赖错误则诊断后提示用户 |
| `visual_review` | `storyboard.json` 或 `scene.json` |

Agent 禁止：

- 直接编辑 `generated/scene.py`。
- 绕过 `manim-cli compile` 手写 Python。
- 拼接任意 shell 命令作为渲染入口。
- 在 DSL 中放 Python 表达式或未声明 API。

## 6. CLI MVP

### 6.1 命令矩阵

| 命令 | 输入 | 输出 |
|------|------|------|
| `manim-cli init <project-dir>` | 目录 | lesson project 骨架 |
| `manim-cli plan validate <plan.json>` | TeachingPlan | JSON diagnostic |
| `manim-cli storyboard validate <storyboard.json>` | Storyboard | JSON diagnostic |
| `manim-cli validate <scene.json>` | Scene DSL | JSON diagnostic |
| `manim-cli compile <scene.json> --out <dir>` | Scene DSL | `scene.py`, `scene.py.map.json`, JSON result |
| `manim-cli render <scene.json> --quality low --output <mp4>` | Scene DSL | video + JSON result |
| `manim-cli render <scene.py> --quality low --output <mp4>` | Generated Python | video + JSON result |
| `manim-cli diagnose <diagnostic.json> --source-map <map>` | 失败记录 | JSON diagnostic |
| `manim-cli manifest` | 无 | API manifest JSON |

### 6.2 render 行为

`render` 接受 `scene.json` 时，必须显式执行：

```text
validate -> compile -> subprocess manim
```

输出仍然落到固定位置或 `--output` 指定路径。

质量参数：

| quality | 用途 | 参数策略 |
|---------|------|----------|
| `low` | 快速预览 | 低分辨率、低 fps、短 timeout |
| `high` | 最终交付 | 使用 DSL config 中 resolution/fps |

MVP 默认：

```text
low: 854x480, fps=15, timeout=120s
high: scene.config.resolution, scene.config.fps, timeout=600s
```

`render` 使用 subprocess 调用 `manim`，不在同一进程复用 Manim 内部入口。

## 7. 技术实现方案

### 7.1 包结构

```text
manim_cli/
├── cli.py
├── commands/
│   ├── init_cmd.py
│   ├── plan_cmd.py
│   ├── storyboard_cmd.py
│   ├── validate_cmd.py
│   ├── compile_cmd.py
│   ├── render_cmd.py
│   ├── diagnose_cmd.py
│   └── manifest_cmd.py
├── dsl/
│   ├── models.py
│   ├── registry.py
│   ├── validators.py
│   ├── compiler.py
│   ├── writer.py
│   ├── names.py
│   └── encoders.py
├── planning/
│   ├── teaching_plan.py
│   └── storyboard.py
├── render/
│   ├── runner.py
│   └── diagnose.py
├── agent/
│   ├── manifest.py
│   └── skill/
│       ├── SKILL.md
│       ├── workflow.md
│       └── examples/
└── tests/
    ├── fixtures/
    ├── test_validate.py
    ├── test_compile_snapshot.py
    ├── test_source_map.py
    └── test_diagnose.py
```

### 7.2 依赖选择

MVP 依赖：

- `click`：CLI。
- `pydantic<2`：兼容目标 Python / Manim 环境。
- `typing-extensions`：兼容类型注解。

MVP 不把 `black` / `ruff` 作为运行依赖。原因是格式化会影响 source map 行号，且对第一版价值不高。

建议运行环境：

```text
Python: 3.9 - 3.11
Pydantic: v1
Manim: 当前环境可用版本
```

### 7.3 Validator

Schema validation：

- 缺少必填字段。
- 类型错误。
- enum 非法。
- 未知字段。
- args/action 字段不匹配。

Semantic validation：

- mobject id 唯一。
- action target 存在。
- transform `to` 存在。
- position target 存在。
- plane 坐标必须引用 `Axes`。
- 坐标必须是 2 或 3 维数字数组。
- `add/remove/wait` 不接受非法参数。
- `plan_ref` / `storyboard_ref` 文件存在时可校验引用。

### 7.4 Compiler

编译器是确定性函数：

```text
SceneDef
  -> validate
  -> CompileContext(id_to_var)
  -> collect imports
  -> emit header
  -> emit mobjects
  -> emit style
  -> emit position
  -> emit steps
  -> write scene.py
  -> write scene.py.map.json
  -> py_compile
```

关键规则：

- 所有外部值必须走 encoder。
- 字符串使用 `repr()`。
- 数字限制为 finite number。
- 坐标输出为 `np.array([...], dtype=float)` 或 `axes.c2p(x, y)`。
- 方向和 rate function 只允许白名单常量。
- Python 变量名由 compiler 从 DSL id 稳定生成。
- 同一 DSL 多次编译输出必须一致。

### 7.5 Source Map

MVP source map 至少记录 action 和 mobject 粒度，推荐字段级 path：

```json
{
  "generated_file": "scene.py",
  "scene_name": "GeneratedScene",
  "mappings": [
    {
      "json_path": "$.mobjects[2].args.end",
      "python_lines": [18, 18],
      "symbol": "mobj_vector_v"
    },
    {
      "json_path": "$.steps[3].actions[0]",
      "python_lines": [31, 31],
      "symbol": "Create(mobj_x_component)"
    }
  ]
}
```

### 7.6 Diagnostic

统一输出：

```json
{
  "ok": false,
  "phase": "render",
  "error_type": "latex_error",
  "message": "LaTeX failed while rendering Tex object.",
  "location": {
    "file": "scene.json",
    "path": "$.mobjects[0].args.tex",
    "line_in_generated_code": 18,
    "source_map": "generated/scene.py.map.json"
  },
  "suggestions": [
    "Simplify the Tex string.",
    "Check whether LaTeX is installed."
  ]
}
```

MVP 错误类型：

- `missing_required_field`
- `invalid_type`
- `invalid_enum`
- `unknown_field`
- `undefined_target`
- `unsupported_type`
- `unsupported_action`
- `python_syntax_error`
- `latex_error`
- `missing_dependency`
- `render_timeout`
- `manim_runtime_error`
- `compile_internal_error`

## 8. MVP 示例场景

至少保留 3 个 fixtures：

| fixture | 覆盖点 |
|---------|--------|
| `simple_transform.json` | `Circle`, `Square`, `show_creation`, `transform` |
| `equation_intro.json` | `Tex`, `Text`, `write`, `fade_in`, `wait` |
| `vector_intro.json` | `Axes`, `Arrow`, `Line`, `Dot`, plane 坐标 |

这 3 个例子同时作为：

- Agent skill examples。
- compile snapshot 测试。
- render smoke 测试候选。
- manifest 示例。

## 9. 测试策略

### 9.1 必做测试

- Pydantic unknown field 拒绝。
- 每种 Mobject args schema。
- 每种 Action schema。
- id 引用检查。
- plane 坐标 axes 检查。
- id 到 Python var 映射稳定性。
- compile snapshot。
- source map 行号。
- `py_compile`。
- diagnostic 分类。

### 9.2 可选测试

真实 render smoke test 标记为 optional，避免 CI 被 OpenGL、LaTeX、ffmpeg 环境拖垮。

## 10. 实施顺序

### Step 1: CLI 骨架和项目初始化

- `manim_cli/` 包。
- `manim-cli init`。
- JSON 输出协议。
- `project.json` 和 lesson project 目录。

### Step 2: DSL schema 和 validator

- Pydantic v1 models。
- 8 个 Mobject。
- 9 个 Action。
- Style / Position / Config。
- semantic validators。

### Step 3: compiler

- `CodeWriter`。
- `SourceMap`。
- `names.py`。
- `encoders.py`。
- registry emit。
- `py_compile`。

### Step 4: render runner

- subprocess 调用 `manim`。
- low/high quality。
- timeout。
- stdout/stderr 捕获。
- JSON result。

### Step 5: diagnose

- traceback 行号提取。
- source map lookup。
- LaTeX / missing dependency / timeout 分类。
- 修复建议。

### Step 6: agent skill 包

- `SKILL.md`。
- `workflow.md`。
- manifest。
- 3 个 examples。
- 修复规则和禁止事项。

### Step 7: smoke fixtures

- `simple_transform.json`。
- `equation_intro.json`。
- `vector_intro.json`。
- compile snapshot。
- optional render smoke。

## 11. MVP 完成定义

MVP 完成需要满足：

- 3 个 fixture 均可 validate。
- 3 个 fixture 均可 compile，且 `scene.py` 通过 `py_compile`。
- 至少 2 个 fixture 能在本地低清 render 成功。
- render 失败时返回结构化 JSON，不只抛 traceback。
- source map 能把至少 action 行映射回 DSL path。
- Agent skill workflow 文档能指导 Codex / Claude Code 从 brief 产出 preview。
- 生成的 Python 文件只来自 compiler，不需要手写修改。
