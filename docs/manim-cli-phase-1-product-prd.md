# Manim Harness 产品 PRD

## 1. 一句话定位

**Manim Harness 是面向 Agent 生成 Manim 视频的质量基础设施。它通过 QA gate、layout slots、source map、visual regression 和 repair hints，把生成质量从模型运气变成工程约束。**

英文定位：

```text
Manim Harness is the quality compiler and CI layer for agent-generated Manim videos.
```

产品主张：

```text
We do not replace Manim. We make AI-generated Manim reliable.
```

## 2. 背景

`manim-cli` MVP 已经验证了一条 Agent 生成 Manim 教学视频的基础链路：

```text
brief.md
  -> plan.json
  -> storyboard.json
  -> scene.json
  -> validate
  -> compile
  -> render
  -> diagnose / repair
```

当前市场上的 Manim wrapper 或 AI Manim 工具，大多聚焦在：

- 自然语言或论文到 Manim Python。
- 调用 Manim 渲染并做失败重试。
- 给 Manim 增加 voiceover、slides、editor 等能力。
- 用多轮 Agent reflection 提高 render success rate。

这些方向解决的是“如何生成 Manim 代码”或“如何调用 Manim”。但 Agent 生成 Manim 的真实瓶颈往往不是能否调用 Manim，而是生成结果是否稳定可用：

- 渲染成功但画面不可读。
- 公式、标签、图形重叠。
- 对象越界或贴边。
- 字号过小、单屏信息过密。
- 旧对象没有清理，画面越来越乱。
- 旁白 cue 和视觉事件不同步。
- 失败后 Agent 只拿到 Python traceback，不知道该改哪个上游 artifact。

Manim Harness 的机会是避开“再做一个端到端 AI Manim 生成器”的红海，专注成为所有 Agent 生成 Manim 工作流中的质量约束层。

## 3. 用户价值

### 3.1 对创作者

用户买到的不是一个 Manim wrapper，而是一个能让 AI 稳定产出教学动画的质量控制系统。

核心价值：

- 更少生成“能渲染但不能用”的视频。
- 更快得到可读 preview。
- 不需要理解 Manim 坐标、Tex 编译、动画生命周期或 Python traceback。
- 修改需求后，Agent 能局部修复，而不是整段重写。
- 批量生成课程视频时，可以用质量门禁筛掉明显问题。

### 3.2 对 Agent

Agent 需要的不是更自由地写 Python，而是更可靠的反馈回路。

Manim Harness 为 Agent 提供：

- 结构化错误。
- 可定位 DSL path。
- object id / step id / storyboard frame 的 source map。
- 可执行 repair hints。
- render 前质量 gate。
- preview 后视觉反馈。
- 可复用的 layout slots，减少坐标猜测。

### 3.3 对维护者

维护者需要知道 DSL、compiler、prompt 或模型版本变化是否造成质量退化。

Manim Harness 提供：

- regression scene suite。
- keyframe baseline。
- QA score baseline。
- render cost report。
- deterministic compiler output。

## 4. 产品边界

### 4.1 做什么

Manim Harness 做 Agent 生成 Manim 的质量基础设施：

- DSL 合法性检查。
- 渲染前 QA gate。
- Agent-friendly layout slots。
- source map 和 diagnostic。
- preview visual QA。
- visual regression。
- repair hints。
- render cost profiling。
- 教学准确性约束。

### 4.2 不做什么

下一阶段不把产品定位成通用 Manim wrapper，也不把 LLM 调用内置到 CLI。

暂不优先做：

- 完整覆盖 Manim API。
- 任意 Python passthrough。
- 复杂 3D。
- updater / lambda / custom animation class。
- 复杂 camera movement。
- 大而全的 Web editor。
- 端到端 paper-to-video 产品。

`Graph`、`Brace`、`NumberPlane`、voiceover、slides 都有价值，但它们是表达能力扩展，不是核心差异化。下一阶段应先把“可读、可诊断、可修复、可回归”做实。

## 5. 产品形态

项目名可以继续叫 `manim-cli`，但产品定位采用 **Manim Harness**。

```text
Manim Harness
  ├── Scene DSL
  ├── QA Gate
  ├── Layout Compiler
  ├── Source Map
  ├── Visual QA
  ├── Repair Hints
  └── Regression Suite
```

典型工作流：

```text
Brief
  -> Plan
  -> Storyboard
  -> Scene DSL
  -> Validate
  -> QA Gate
  -> Layout Compile
  -> Preview Render
  -> Visual QA
  -> Repair Hints
  -> Final Render
```

对外表达：

```text
Prompt / JSON / Python -> Manim -> Video
```

是普通 wrapper 的路径。

```text
Brief -> Scene DSL -> QA Gate -> Layout Compiler -> Visual QA -> Repair -> Final Video
```

是 Manim Harness 的路径。

## 6. 核心差异化 Feature

### 6.1 QA Gate

QA Gate 是 Manim Harness 的第一核心能力。它像 ESLint / TypeScript 一样，在 render 前检查 Agent 生成的视频质量风险。

检查项：

- 高置信对象重叠。
- Tex/Tex 重叠在 quick LaTeX probe 或 Visual QA 后判断。
- 对象越界。
- 内容贴边。
- 字号过小。
- 公式过长。
- 单屏对象过多。
- 旧对象未清理。
- step 节奏过挤。
- scene step 与 storyboard frame 的估算时长漂移。
- transform 生命周期不清晰。
- 数学硬错误 lint：显式分母零、未定义符号引用、带 metadata 的符号类型漂移。
- 可选教学检查：symbol ledger、learning goal coverage、storyboard event coverage。

命令形态：

```bash
manim-cli qa scene.json
manim-cli qa scene.json --profile relaxed
manim-cli qa scene.json --profile strict --json
```

输出示例：

```json
{
  "ok": false,
  "phase": "qa",
  "score": 72,
  "issues": [
    {
      "severity": "error",
      "type": "layout_overlap",
      "message": "Visible objects overlap in step_show_formula.",
      "repair_scope": "visual_action",
      "location": {
        "path": "$.steps[3]",
        "objects": ["eq_main", "caption"]
      },
      "suggestions": [
        "Move caption to the caption slot.",
        "Reduce eq_main font_size or use bottom_formula slot."
      ]
    }
  ]
}
```

用户价值：

- 在耗时 render 前发现明显问题。
- 把“看视频才知道坏了”前置为“跑 QA 就知道坏了”。
- Agent 可以根据结构化结果局部修复。

### 6.2 Source Map

Source Map 把生成的 Manim Python、render error、QA issue、visual QA finding 回溯到上游 artifact。

需要回溯到：

- `scene.json` path。
- object id。
- step id。
- action index。
- storyboard frame。
- plan learning goal。
- narration cue。
- generated Python line。

Source Map 示例：

```json
{
  "generated_line": 84,
  "scene_path": "$.steps[3].actions[1]",
  "step_id": "step_show_formula",
  "action_index": 1,
  "object_ids": ["eq_main"],
  "storyboard_frame": "frame_2",
  "narration_cue_id": "cue_2",
  "plan_goal": "goal_pythagorean_relation"
}
```

用户价值：

- Agent 不需要从 Python traceback 反推 JSON。
- 修复位置明确，减少整段重写。
- 支持 explainable repair。

### 6.3 Layout Slots

Layout Slots 让 Agent 表达布局意图，而不是猜 Manim 坐标。

DSL 示例：

```json
{
  "id": "eq_final",
  "type": "Tex",
  "args": {
    "tex": "a^2 + b^2 = c^2",
    "font_size": 56
  },
  "layout": {
    "slot": "bottom_formula",
    "align": "center"
  }
}
```

内置 slot：

- `title`
- `subtitle`
- `main`
- `left_panel`
- `right_panel`
- `bottom_formula`
- `caption`
- `callout`

编译器职责：

- slot 到 Manim 坐标映射。
- 安全区域约束。
- 同槽位 arrange。
- 长文本缩放。
- 公式 `scale_to_fit_width`。
- 标题、主体、底部公式间距保护。
- 输出 `layout_changes`。

用户价值：

- 大幅减少 Agent 坐标猜测。
- 同一 lesson 在不同内容长度下更稳定。
- 布局问题变成可解释的编译约束。

### 6.4 Visual QA

Visual QA 在 preview render 后抽取关键帧，检查真实画面问题。

检查项：

- 空白帧。
- 近似黑屏。
- 内容贴边。
- 内容密度过高。
- 大面积遮挡。
- 关键对象缺失。

命令形态：

```bash
manim-cli render scene.json --quality low --output renders/preview.mp4 --qa
manim-cli qa renders/preview.mp4 --scene scene.json --source-map generated/scene.py.map.json
```

输出：

- `feedback/latest.json`
- `feedback/latest.md`
- `feedback/agent_prompt.md`
- keyframe screenshots

用户价值：

- render 成功不再等于质量合格。
- Agent 可以根据 preview 真实画面反馈修复。
- final render 前有最后一道质量门禁。

### 6.5 Visual Regression

Visual Regression 让 Manim Harness 可以作为 CI 层使用。

能力：

- curated STEM regression scenes。
- expected diagnostics baseline。
- preview keyframe baseline。
- QA score baseline。
- render cost baseline。
- build manifest comparison。

命令形态：

```bash
manim-cli manifest build examples/pythagorean_theorem
manim-cli regression run tests/regression
```

用户价值：

- prompt、DSL、compiler、Manim 版本变化后，可以发现隐性质量退化。
- 支持批量课程生成前的质量验收。
- 让 Manim 生成从 demo 走向工程生产。

### 6.6 Repair Hints

Repair Hints 把 QA 和 render 失败转成 Agent 可执行修改建议。

每条 hint 必须带 `repair_scope`，用于表达最小修复单元：

- `narration_cue`：只需要改旁白 cue、文本或估算时长。
- `single_action`：只需要改一个具体 action，必须带 `action_index`。
- `visual_action`：需要改一个或多个视觉 action、step 或 layout。
- `cross_track_alignment`：旁白 cue 和视觉动作都要调整。
- `artifact_reference`：plan/storyboard/scene 的引用关系需要修正。

示例：

```text
$.steps[4]: eq_main overlaps caption.
Suggested repair: move caption to layout.slot = "caption", or fade_out eq_main before writing caption.
```

```text
$.mobjects[6]: title text is likely wider than the title safe area.
Suggested repair: reduce font_size from 60 to 44, or split title into subtitle.
```

用户价值：

- Agent 不需要猜如何修复。
- 修复可以局部发生。
- 错误体验从 traceback 变成 actionable diagnostic。

## 7. P0/P1/P2 范围

### P0: Static QA Gate

目标：不运行 Manim 渲染，也能发现明显质量问题。

交付：

- `SceneTimeline`。
- bbox estimator。
- bbox confidence / measurement method。
- `manim-cli qa scene.json`。
- safe area check。
- high-confidence overlap check。
- custom layout region boundary check（只校验 region 安全边界，不做复杂 arrange）。
- density check。
- text width / font size warning。
- step-frame timing drift check（当 storyboard frame 提供 `duration_seconds` 时启用）。
- static math lint（只覆盖显式可判定的硬错误）。
- Tex/Tex overlap 不作为 P0 阻断项。
- relaxed / strict profile。

验收：

- 现有示例项目能输出 QA report。
- 至少能发现越界、高置信 bbox 重叠、密度过高三类问题。
- custom region 能被解析并参与越界检查，Agent 不必为非标准布局退回 absolute 坐标。
- 数学 lint 至少覆盖三条规则：显式分母零、未定义符号引用、带 metadata 的符号类型漂移。
- Tex/Tex overlap 不计入 P0 阻断验收，除非已经通过 quick LaTeX probe 或 Visual QA 得到真实 bbox。
- 每个 issue 都包含 object id 或 DSL path。
- 每个 action 级 issue 都包含 `action_index`。
- `validate` 默认行为保持兼容。
- Release 1 尾声建立 10-20 个 scene 的 QA eval 标注集，输出 precision / recall / false positive rate。

### P1: Source Map + Repair Hints

目标：让所有问题都能回到可修复位置。

交付：

- source map schema。
- compile 输出 `scene.py.map.json`。
- QA issue 关联 source map。
- render error 关联 source map。
- repair hint model。
- `repair_scope = "single_action"` 与 `action_index`。
- repair loop diagnostics。
- `feedback/agent_prompt.md`。

验收：

- Manim Python 行号可以回溯到 `scene.json` step/action。
- QA issue 可以给出最近修复位置。
- Agent 可以根据 repair hints 修改上游 artifact。

### P2: Layout Slots

目标：让 Agent 少猜坐标。

交付：

- DSL 支持 `layout`。
- 核心 slot。
- custom slot + explicit region 的 arrange / fit 策略。
- slot 到坐标映射。
- 基础自动缩放和 arrange。
- `layout_changes`。

验收：

- 新示例可以不用大面积 absolute position 完成布局。
- 长公式可自动缩放或被 QA 拦截。
- 自动布局修改可追踪。

### P3: Preview Visual QA

目标：把真实预览画面转成结构化反馈。

交付：

- `render --qa`。
- keyframe extraction。
- blank / edge / density checks。
- `feedback/latest.json`。
- `feedback/latest.md`。
- `feedback/agent_prompt.md`。

验收：

- 空白视频或明显空白片段能被识别。
- 抽帧截图路径写入报告。
- 报告能关联 scene step。

### P4: Regression Suite

目标：支持持续迭代和批量生产。

交付：

- regression scene manifest。
- QA baseline。
- keyframe baseline。
- render cost baseline。
- 一键 regression command。

验收：

- compiler 改动后可以发现诊断退化或视觉退化。
- 核心示例可以作为 CI smoke suite。

## 8. 把质量工程化的实现方案

本节回答“怎么把质量从模型运气变成工程约束”。核心方法是：Agent 只负责生成候选 artifact，Manim Harness 负责用确定性规则、编译器约束和回归基线决定候选是否合格。

### 8.1 质量标准先结构化

不要先写视觉模型，也不要先扩 Manim primitive。第一步是把“视频可用”拆成可检查规则。

画面质量规则：

- 对象不能越界。
- 高置信 bbox 的核心文字和图形不能重叠。
- `Tex` / `MathTex` 的静态重叠不在 P0 下最终裁决，必须交给 quick LaTeX probe 或 Visual QA。
- 字号不能过小。
- 单屏对象不能过多。
- 内容不能贴边。
- 旧对象要及时清理。

布局质量规则：

- title 进入 `title` 安全区。
- 公式进入 `bottom_formula` 安全区。
- caption 进入 `caption` 安全区。
- 主体图形进入 `main` / `left_panel` / `right_panel`。
- 同 slot 多对象需要 arrange，而不是堆叠。

教学质量规则：

- narration cue 提到的对象必须在对应 step 可见或被 highlight。
- symbol ledger 中的符号含义不能漂移。
- learning goal 必须被 storyboard frame 和 scene step 覆盖。
- storyboard visual event 必须有 scene step 实现。
- scene step 的视觉动作时长与 storyboard frame 的估算时长不能明显漂移。

工程质量规则：

- render 失败能定位到 scene step/action/object。
- QA issue 必须包含 DSL path 或 object id。
- compiler 输出 deterministic、可 diff。
- regression scenes 可以比较 QA baseline、keyframe baseline 和 render cost baseline。

### 8.2 QA Gate 实现路径

QA Gate 的最小流水线：

```text
scene.json
  -> parse / validate
  -> build SceneTimeline
  -> estimate object bbox
  -> run quality rules
  -> emit issues + repair hints
  -> pass / fail
```

现有基础：

- `manim_cli/dsl/timeline.py` 已有 `build_timeline(scene)`。
- `manim_cli/dsl/layout.py` 已有 `estimate_bbox(...)`、`layout_warnings(...)`。
- `validate_scene_data(..., quality_gate="strict")` 已经能用 strict gate 阻断 warning。

下一步产品化：

- 新增独立 `manim-cli qa scene.json` 命令。
- 新增统一 `Issue` schema，替代零散 warning dict。
- `qa` 输出 `ok`、`score`、`issues`、`summary`、`repair_hints`。
- `validate` 默认只管 DSL 合法性，`qa` 管视频质量风险。
- `compile --profile final` 可以调用 strict QA gate，但不把 QA 逻辑塞回 validate。

建议 Issue schema：

```json
{
  "type": "layout_overlap",
  "severity": "error",
  "phase": "qa",
  "path": "$.steps[3]",
  "step_id": "step_show_formula",
  "objects": ["eq_main", "caption"],
  "message": "eq_main overlaps caption after step_show_formula.",
  "repair_scope": "visual_action",
  "repair_hints": [
    "Move caption to layout.slot = \"caption\".",
    "Fade out eq_main before writing caption."
  ]
}
```

P0 必做规则：

- `layout_out_of_bounds`
- `layout_overlap`
- `layout_density`
- `layout_text_too_wide`
- `layout_font_too_small`
- `timeline_missing_cleanup`
- `step_frame_timing_drift`
- `math_symbol_type_drift`
- `math_denominator_zero`
- `math_undefined_symbol`

P0 不做：

- 不用静态估算阻断 `Tex` / `MathTex` 之间的重叠。
- 不做通用代数等价证明或定理证明。
- 不把所有公式 transform 判为错误，只要求可解释的语义关系或显式降级为 fade/write。

### 8.3 Layout Slots 实现路径

Layout Slots 的目标不是做复杂排版引擎，而是让 Agent 避免低质量坐标猜测。

最小流水线：

```text
mobject.layout.slot
  -> resolve slot safe region
  -> estimate mobject bbox
  -> fit / scale / arrange
  -> emit Manim move_to / scale_to_fit_width
  -> record layout_changes
```

现有基础：

- `LayoutSpec` 已存在。
- `slot_center(scene, slot)` 已存在。
- `emit_layout(...)` 已支持 `move_to` 和文本 `scale_to_fit_width`。
- `layout_changes` 已作为 compile result 输出。

下一步产品化：

- 把 `slot_center` 升级成 `slot_region`，返回安全矩形而不是单点。
- 支持同 slot 多对象的 deterministic arrange。
- QA 检查 slot 之间的互斥区域，例如 title 和 main 不能冲突。
- layout compiler 所有自动修正都写入 `layout_changes`。
- Agent skill 要优先产出 `layout`，只有特殊场景才使用 absolute position。
- 对交换图、树形证明、矩阵变换箭头等非标准布局，允许 `layout.slot = "custom"` 搭配 `layout.region` 表达安全区域。

### 8.3.1 bbox 置信度与 LaTeX 不可知边界

Static QA 不能承诺像素级布局真值，尤其不能把 `Tex` / `MathTex` 的静态宽度估算当成真实渲染宽度。LaTeX bbox 对静态 QA 是结构性不可知：宽高取决于 LaTeX 编译、字体、模板、DVI/SVG 转换、运行环境和缓存状态。bbox estimator 必须输出置信度和测量方法：

| 对象类型 | 估算策略 | `bbox_confidence` | P0 overlap 行为 |
|---|---|---|
| `Circle` / `Square` / `Dot` / `Line` / `Arrow` / `Axes` | 几何解析估算 | `high` | 可阻断 |
| `Text` | 字符数、font_size、经验宽度系数 | `medium` | 只在明显越界或高置信重叠时阻断 |
| `Tex` / `MathTex` | 静态占位估算，仅用于提示需要真实测量 | `unknown_static` | 不做 Tex/Tex 静态重叠阻断 |

规则：

- P0 overlap check 默认只对 `high/high` 几何对象阻断。
- `high/medium` 或 `medium/medium` 只在大幅交叠时 warning 或 strict error。
- `Tex/Tex`、`Tex/Text` 的静态重叠输出 `bbox_unmeasured` 或 `layout_needs_visual_qa`，不作为 P0 fail 条件。
- final profile 如需阻断 Tex 重叠，必须先跑 quick LaTeX probe 或 preview Visual QA 回填真实 bbox。
- QA 有效性指标必须单独统计 `unknown_static` issue，避免让 LaTeX 误报污染整体 precision。

slot region 示例：

```json
{
  "slot": "bottom_formula",
  "region": {
    "left": -5.2,
    "bottom": -3.1,
    "right": 5.2,
    "top": -2.2
  },
  "max_width": 10.4,
  "max_height": 0.9
}
```

custom slot 示例：

```json
{
  "slot": "custom",
  "region": {
    "left": -4.8,
    "bottom": -2.6,
    "right": 4.8,
    "top": 2.4
  },
  "arrange": "manual"
}
```

### 8.4 Source Map 与 Repair Hints 实现路径

Source Map 是让 Agent 局部修复的关键。没有 source map，QA 和 render 失败仍然会退化成“重新生成整个 scene”。

最小流水线：

```text
compiler writer.add(line, path, symbol)
  -> scene.py.map.json
  -> diagnose render traceback line
  -> map to scene path / step / object
  -> attach repair hints
```

现有基础：

- `CodeWriter.source_map(...)` 已存在。
- `compile_scene(...)` 已输出 `generated/scene.py.map.json`。
- `render/diagnose.py` 已能把 Python line 映射回 source map。

下一步产品化：

- source map mapping 增加 `step_id`、`action_index`、`object_ids`。
- source map mapping 增加 `narration_cue_id`、`storyboard_event_id`。
- QA issue 也使用同一套 location schema。
- render diagnostic 和 QA diagnostic 使用同一种 `repair_hints` 字段。
- repair hint 不追求自动修改，先提供 Agent 可执行建议。
- repair hint 必须标明 `repair_scope`，避免 Agent 因局部问题整段重写。
- action 级 repair hint 必须包含 `action_index`，优先使用 `repair_scope = "single_action"`。

### 8.4.1 Repair loop 防震荡

Agent 修复常见失败模式是 A/B 循环：修复 issue A 引入 issue B，修复 issue B 又重新引入 issue A。QA Gate 需要支持最小的修复历史输入。

建议 QA 输入可选 `repair_context`：

```json
{
  "attempt": 3,
  "target_issue_ids": ["qa-001"],
  "previous_issue_ids": ["qa-001", "qa-004"],
  "previous_repairs": [
    {
      "issue_id": "qa-001",
      "path": "$.steps[3].actions[2]",
      "repair_scope": "single_action",
      "summary": "Moved arrow_tip from main to callout region."
    }
  ]
}
```

QA 输出增加：

- `repaired_issues`：本轮已消失的问题。
- `regression_reintroduced`：历史问题重新出现，提示 Agent 不要重复同一修复方向。
- `new_issues_after_repair`：修复目标之外新出现的问题。

这不是自动修复，只是把 repair loop 的状态结构化，避免 Agent 无限震荡。

### 8.4.2 Agent 反馈格式

QA 输出必须同时服务程序和 Agent prompt。结构化 JSON 保留完整机器可读信息，但复杂 scene 的 JSON report 会消耗大量 token。

输出文件：

- `feedback/latest.json`：完整结构化报告。
- `feedback/agent_prompt.md`：面向 Agent 的短摘要，按 severity 排序，每条不超过 2 行。

`agent_prompt.md` 示例：

```md
# QA repair summary

1. ERROR `math_denominator_zero` at `$.steps[2]`: `1/(x-1)` is shown while `x=1` is active. Change the example value or guard the domain.
2. WARNING `layout_needs_visual_qa` at `$.steps[4]`: Tex objects `eq_main` and `caption` may overlap, but static bbox is unavailable. Run preview Visual QA before final.
3. WARNING `step_frame_timing_drift` at `frame_3`: visual duration 2.0s vs frame duration 6.0s. Add wait, split the frame, or shorten narration.
```

Agent 默认消费 `agent_prompt.md`，工具和 CI 消费 `latest.json`。

### 8.4.3 P0 数学语义 lint

数学准确性比布局更影响教学可信度，但 P0 不能做通用数学证明。P0 只做显式可判定的硬错误和语义缺口：

| 检查项 | P0 条件 | 行为 |
|---|---|---|
| `math_denominator_zero` | 表达式含显式分母 `1/(x-a)` 或 metadata `denominators`，且同一 step/frame 出现 `x=a` | error |
| `math_undefined_symbol` | step 使用符号，但前序 step、symbol ledger、mobject math metadata 均未引入 | error |
| `math_symbol_type_drift` | symbol ledger 或 mobject metadata 声明同一符号的 type/shape/domain 前后冲突；例如 `x` 从 scalar 变为 vector 并参与 inner product | error |

P1/P2 再补：

- `math_transform_without_relation`：Tex/MathTex 之间的 `transform` 没有 `semantic_relation`、`reason` 或 storyboard event 解释时 warning；strict/final 可 error。
- 更完整的公式 relation metadata，但不做通用代数等价证明。

为支持这些检查，Phase 1 可扩展可选 metadata：

```json
{
  "symbol_ledger": [
    {
      "symbol": "x",
      "meaning": "input scalar",
      "kind": "scalar",
      "domain": "real",
      "shape": []
    }
  ],
  "mobjects": [
    {
      "id": "eq_step_2",
      "type": "Tex",
      "args": {"tex": "y = \\frac{1}{x - 1}"},
      "math": {
        "symbols": ["x", "y"],
        "introduced_symbols": ["y"],
        "used_symbols": ["x"],
        "denominators": ["x - 1"]
      }
    }
  ],
  "steps": [
    {
      "id": "derive_step",
      "actions": [
        {
          "type": "transform",
          "target": "eq_1",
          "to": "eq_2",
          "semantic_relation": "apply_distributive_law"
        }
      ]
    }
  ]
}
```

没有 metadata 时，P0 只做低风险文本模式检测，不把无法证明的数学关系判为错误。

### 8.5 Visual Regression 实现路径

Visual Regression 的目标是防止 DSL、compiler、prompt、模型或依赖版本变化造成隐性退化。

最小目录结构：

```text
tests/regression/
  pythagorean_theorem/
    scene.json
    expected_qa.json
    expected_manifest.json
    keyframes/
      frame_001.png
      frame_002.png
```

最小流水线：

```text
regression run
  -> validate
  -> qa
  -> compile fast
  -> optional preview render
  -> optional keyframe extraction
  -> compare baseline
  -> report pass/fail/diff
```

现有基础：

- `manim_cli/regression/manifest.py` 已有 `run_regression_dir(...)`。
- 现在只做 validate/compile，不比较 baseline。

下一步产品化：

- regression runner 加入 QA report。
- 支持 `expected_qa.json` baseline。
- 支持 render cost baseline。
- P3 之后再加入 keyframe baseline。
- CI 默认跑 no-render regression，本地或 release 前跑 render regression。

### 8.6 推荐实现顺序

下一阶段不要同时做所有 Harness 能力。推荐按依赖关系推进：

```text
1. compiler correctness fixes: cache key, single parse, multi-error reporting
2. shared Analysis pass: step_durations, object_lifetimes, layout_plan
3. qa Issue schema
4. manim-cli qa command
5. SceneTimeline + high-confidence bbox rules 产品化
6. Source map enrichment
7. static math lint
8. Repair hints + repair loop diagnostics
9. feedback/agent_prompt.md
10. slot_region / custom region + layout_changes 完整化
11. regression baseline without render
12. preview Visual QA / quick LaTeX probe
13. keyframe visual regression
```

### 8.7 Compiler Foundation Backlog

GLM 和 Deepseek 的 compiler review 指向同一个结论：当前 compiler 是干净的 MVP，但 Harness Core 不能直接建立在 `SceneDef -> Python string` 的单跳发射上。下一阶段必须先补 compiler foundation，否则 QA Gate、source map、repair hints 和 step-frame timing drift 会各自重复分析 scene，并产生不一致。

#### P0: 正确性 / 阻断

| Task | 落点文件 | 验收标准 |
|------|----------|----------|
| 缓存 key 纳入编译器版本和 Manim 版本 | `manim_cli/dsl/compiler.py`, `manim_cli/__init__.py` 或版本来源文件 | CLI 或 Manim 版本变化后不命中旧 `scene.py`；`.compile-cache.json` 记录版本元数据 |
| 消除双重 parse | `manim_cli/dsl/compiler.py`, `manim_cli/dsl/validators.py` | `compile_scene_file` 只把 JSON 解析成一次 `SceneDef`；validate、quality warnings、compile 共用同一对象 |
| 多错误上报 | `manim_cli/dsl/validators.py`, `manim_cli/jsonio.py` | Pydantic `ValidationError.errors()` 全量进入 diagnostic；semantic validation 累积错误列表而不是首个错误 return |
| Debug profile 保留 traceback | `manim_cli/dsl/compiler.py` | debug/strict-debug 下 `compile_internal_error` 带 `details.traceback`；默认 profile 仍输出简洁错误 |
| 共享 Analysis pass | 新增 `manim_cli/dsl/analysis.py`, 修改 `compiler.py`, `layout.py`, 后续 `qa` 模块 | 生成 `SceneAnalysis(step_durations, object_lifetimes, visible_sets, layout_plan, bbox_estimates)`；compiler 和 QA Gate 不再各自重建 timeline |
| Source map 结构化 metadata | `manim_cli/dsl/writer.py`, `manim_cli/dsl/compiler.py` | `scene.py.map.json` 每条映射可包含 `step_id`, `step_index`, `action_index`, `object_ids`, `json_path`, `symbol` |

#### P1: 中端 / 优化器

| Task | 落点文件 | 验收标准 |
|------|----------|----------|
| ~~Pydantic v1 -> v2 迁移~~（已实现） | `manim_cli/dsl/models.py`, `validators.py`, `compiler.py`, `optimizer.py` | `model_validate`/`model_dump`/`model_dump_json`/`model_copy`/`model_config = ConfigDict` 全量落地；`scene_canonical_json` 替代 `scene.json(sort_keys=True)`；确定性测试 3 项通过 |
| 精确 import 收集 | `manim_cli/dsl/compiler.py`, `manim_cli/dsl/registry.py` | 只导入实际使用的 color、direction、rate function、mobject/action imports |
| 优化器职责下沉 | `manim_cli/dsl/optimizer.py`, `compiler.py` | `collect_mergeable_actions` 从 compiler 移入 optimizer 或 IR lowering；compiler 只消费优化结果 |
| Preview run_time 缩放策略修正 | `manim_cli/dsl/optimizer.py` | 不再把长动画硬截断为 `0.5s`；采用比例缩放并保留下限 |
| 对象复用和延迟创建 | `optimizer.py`, `analysis.py` | 同 `type + args + style` 可生成 template 并 `.copy()`；对象可按 `first_use_step` 延迟 emit，直接派生自 `SceneAnalysis.object_lifetimes` |

#### P2: 静态分析 / 诊断 / 测试

| Task | 落点文件 | 验收标准 |
|------|----------|----------|
| overlap 覆盖盲点 | `manim_cli/dsl/layout.py`, `tests/test_mvp.py` | `Text/Tex x Circle/Square` 和 label/geometry 重叠进入检查；Tex 低置信问题不作为 P0 阻断 |
| bbox 估算返回 confidence | `manim_cli/dsl/layout.py` | `estimate_bbox` 返回 `BBoxEstimate(bbox, confidence, method)`；Tex/MathTex 标记 `unknown_static` 或 low confidence |
| bbox 魔数配置化 | `layout.py`, `models.py` | `0.012/0.014/0.018` 抽为配置；预留 Manim dry-run 回填真实 bbox 的字段 |
| Step-level layout | `models.py`, `compiler.py`, `analysis.py` | 支持 step/action 声明布局变化，不只在 mobject 创建时 `move_to(slot_center)` |
| Codegen 稳定性测试 | `tests/test_mvp.py`, 新增 `tests/golden/` | 同一输入两次 compile 输出字节级一致；source map 有 snapshot 测试 |
| Transform 语义文档与测试 | `docs/`, `registry.py`, `tests/test_mvp.py` | 固化 `transform.to` 可见性策略、target/to 生命周期和 source map 映射 |

推荐执行顺序：

```text
cache key
  -> single parse
  -> multi-error reporting
  -> debug traceback
  -> shared Analysis pass
  -> source map metadata
  -> Pydantic v2
  -> precise imports
  -> optimizer cleanup
  -> bbox confidence / overlap coverage / golden tests
  -> explicit IR
  -> step-level layout
```

这组任务不替代 QA Gate，而是 QA Gate 的工程前置条件。尤其是 `SceneAnalysis` 和 source map metadata 必须在 repair hints 之前完成，否则 Agent 拿到 QA issue 后仍无法稳定定位到应修改的 step/action/object。

### 8.8 与生成 Agent 的契约

Manim Harness 不内置 LLM，也不负责保证同一个 prompt 在不同模型版本下生成同一个 `scene.json`。它负责验证、编译、诊断和回归已经生成的 artifact。

上层 Agent 应提供可追溯 manifest：

```json
{
  "generator": {
    "agent": "codex",
    "model": "model-id",
    "prompt_version": "manim-skill-v1",
    "temperature": 0.2
  },
  "artifacts": {
    "brief": "brief.md",
    "plan": "plan.json",
    "storyboard": "storyboard.json",
    "scene": "scene.json"
  }
}
```

边界：

- Harness regression 默认覆盖 DSL、compiler、Manim 版本和依赖变化。
- 如果 manifest 提供 model/prompt 版本，regression report 可以记录生成来源，但不把 LLM drift 归因给 CLI。
- parallel narration/code tracks 不作为 Phase 1 的硬性 artifact 拆分；Phase 1 通过 `repair_scope` 和 source map 把最小修复单元表达清楚，达到错误隔离的工程目的。

第一阶段完成后，Agent 工作流应该变成：

```text
generate scene.json
  -> manim-cli validate scene.json
  -> manim-cli qa scene.json --profile relaxed
  -> fix if needed
  -> manim-cli compile scene.json --profile preview
  -> manim-cli render scene.json --quality low
  -> optional visual qa
```

## 9. 教学准确性约束

教学准确性是 Manim Harness 的长期护城河，但不应完全推迟。当前代码已经有 symbol ledger、goal coverage、alignment warnings 的基础能力，Phase 1 应把它们接入统一 Issue schema，作为 QA Gate 的可选输入规则。

Phase 1 立即纳入：

- symbol ledger consistency。
- explicit math safety lint：显式分母零、未定义符号引用、带 metadata 的符号类型漂移。
- learning goal coverage。
- cue-event structural alignment。
- storyboard frame 到 scene step 的覆盖。
- step-frame timing drift（依赖 `StoryboardFrame.duration_seconds`，不依赖 cue/event duration）。

P1/P2 纳入：

- `NarrationCue.duration_seconds` 和 `VisualEvent.duration_seconds`。
- cue-event timing drift（cue/event 级 drift 检查，依赖上述字段）。
- narration cue 提到的核心对象在对应 step 是否可见。
- 公式符号是否前后一致。

命令形态：

```bash
manim-cli qa scene.json --plan plan.json --storyboard storyboard.json
```

价值：

- 从“渲染成功”升级到“教学表达可信”。
- 对课程批量生产尤其重要。
- 区分普通动画 wrapper 和教育场景 quality compiler。

## 10. 成功指标

### 10.1 质量指标

- 高置信 bbox 的明显重叠问题能在 render 前发现。
- Tex/Tex overlap 必须在 quick LaTeX probe 或 preview Visual QA 后判断。
- final gate 下没有对象越界。
- 单屏可见对象数量可统计。
- QA issue 100% 包含 object id 或 DSL path。

### 10.2 Agent 效率指标

- preview 平均修复轮次下降。
- render 失败后能定位到上游 artifact。
- Agent 不再需要整段重写来修复局部布局问题。
- 使用 layout slots 的场景中 absolute position 比例下降。

### 10.3 工程指标

- 所有新增命令输出结构化 JSON。
- 生成的 Manim Python 仍然确定性、可 diff。
- source map 与 generated Python 同步。
- regression scenes 可在本地一键运行。

### 10.4 QA 有效性指标

- 建立 10-20 个 scene 的人工标注集，覆盖重叠、越界、密度、字体过小、cue-event drift。
- Release 1 尾声必须至少覆盖越界、高置信重叠、密度、字体过小、显式分母零、未定义符号、符号类型漂移。
- 统计 QA Gate 的 precision、recall 和 false positive rate。
- relaxed profile 以低误杀为目标；strict/final profile 以高召回为目标。
- bbox `unknown_static` issue 必须单独统计，避免把 LaTeX 静态不可知问题伪装成确定性结论。
- Tex/Tex overlap 不计入 P0 layout recall，除非使用 quick LaTeX probe 或 Visual QA 得到真实 bbox。
- 数学 lint 单独统计，不与 layout precision 混在一起。

### 10.5 产品指标

- 用户能把 Harness 作为 Agent 工作流中的默认质量门禁。
- 批量生成时，明显不可用视频进入 final render 的比例下降。
- 用户对失败原因的理解从“Manim 报错了”变成“第几步哪个对象有什么问题”。

## 11. 发布切片

### 当前实现进度（2026-07-07）

已实现并有测试覆盖：

- `manim-cli qa scene.json --profile relaxed|strict|final`。
- 统一 QA `Issue` / `RepairHint` schema，包含 `issue_id`、`fingerprint`、`confidence`、`source`、`repair_scope`。
- `SceneAnalysis`：timeline、step duration、object lifetime、visible set、bbox estimate、layout plan。
- compiler foundation：cache key 包含 CLI/Manim 版本、compile 单次 parse、多错误上报、debug traceback。
- source map enrichment：`step_id`、`step_index`、`action_index`、`object_ids`、`narration_cue_id`、`storyboard_event_id`。
- `manim-cli source-map lookup`：按 generated line、DSL path、object id、step id 反查 source map。
- bbox confidence：geometry high、Text medium、Tex/MathTex `unknown_static`。
- Static QA：safe area、high-confidence overlap、density、custom region boundary、step-frame timing drift、explicit math lint。
- validate / qa 分层：`validate` 默认只做 DSL 合法性；`--quality-gate` 保留兼容入口。
- `feedback/agent_prompt.md`，repair loop diagnostics，issue fingerprint baseline。
- no-render regression：`manim-cli regression run`，包含 validate、compile、qa、expected QA baseline、render cost proxy。
- QA eval：`manim-cli qa-eval` 输出 precision、recall、false positive rate。
- Layout Compiler foundation：`slot_region`、custom region、step-level `layout` action、`layout_changes`。
- compiler optimizer foundation：精确 Manim import、preview runtime 比例缩放、wait merge、重复 mobject `.copy()`。
- Visual QA foundation：`manim-cli visual-qa keyframe`、keyframe hash、pixel checks、`visual-qa bbox-probe` placeholder。
- Render preflight gate：`manim-cli render scene.json --qa --qa-profile strict` 可在 render 前阻断 QA failure。

当前测试状态：`python -m pytest -q` 为 32 个测试通过；`python -m compileall -q manim_cli` 通过。

仍未实现或保持占位：

- 真实视频文件抽帧 / 解码。
- 真实 Manim/LaTeX dry-run bbox 测量。
- first-use delayed object creation 的实际发射重排（未来直接基于 `SceneAnalysis.object_lifetimes`，不重建独立 IR）。

已完成的 compiler foundation 追加项（2026-07-08）：

- Pydantic v1 -> v2 迁移：`model_validate` / `model_dump` / `model_dump_json` / `model_copy` / `model_config = ConfigDict`；`scene_canonical_json` 取代 `scene.json(sort_keys=True)` 用于 scene_hash fallback，递归排序保证确定性；错误类型映射双兼容（`value_error.extra`/`extra_forbidden` 等）。
- LoweredSceneIR 死代码已移除：codegen 保持直接从 `SceneDef` 单 pass 发射，`SceneAnalysis` 为唯一 lowered view（详见 `dsl/analysis.py` 模块 docstring）。

### Release 1: Harness Core

包含：

- compiler correctness fixes：cache key、single parse、multi-error reporting、debug traceback（已实现）
- compiler foundation 追加：Pydantic v1->v2 迁移、确定性序列化（`scene_canonical_json`）、LoweredSceneIR 死代码移除（已实现）
- shared `SceneAnalysis`（已实现）
- source map metadata：step/action/object/cue/event 粒度（已实现）
- `SceneTimeline` 和 step duration（已实现）
- bbox estimator / bbox confidence（已实现）
- static math lint（已实现）
- custom layout region boundary check（已实现）
- `qa` command（已实现）
- safe area / high-confidence overlap / density checks（已实现）
- step-frame timing drift check（已实现）
- QA eval seed set runner（已实现；人工标注集仍需扩充到 10-20 个 scene）
- relaxed / strict / final profile（已实现）

目标：

- 建立“render 前质量门禁”的产品心智。

### Release 2: Explainable Repair

包含：

- source map schema（已实现并文档化：`docs/qa-issue-schema.md`）
- `scene.py.map.json` enrichment（已实现）
- QA issue path enrichment（已实现）
- render error path enrichment（已接入 source map lookup）
- repair hints（已实现基础版）
- repair loop diagnostics（已实现 fingerprint 版本）
- `feedback/agent_prompt.md`（已实现）

目标：

- 让 Agent 可以局部修复，而不是盲目重写。

### Release 3: Layout Compiler

包含：

- layout slots（已实现）
- safety regions / `slot_region`（已实现基础版）
- step-level `layout` action（已实现）
- auto scale（已实现宽度 fit；复杂 arrange 未实现）
- `layout_changes`（已实现基础记录）
- slot-based examples（仍需扩充）

目标：

- 把布局质量从坐标猜测变成编译约束。

### Release 4: Preview Visual QA

包含：

- keyframe extraction（仅支持 JSON pixel/keyframe fixture；真实视频抽帧未实现）
- blank frame check
- edge pressure check
- `feedback/latest.json`
- `feedback/latest.md`
- `feedback/agent_prompt.md`

目标：

- render 成功后继续检查真实画面质量。

### Release 5: Regression Harness

包含：

- regression scene suite command（已实现 `manim-cli regression run`）
- keyframe baseline（pixel hash API 已实现；真实视频 baseline 未实现）
- QA score baseline（已实现 expected QA baseline）
- render cost report（已实现 no-render proxy）
- manifest comparison（仍待实现）

目标：

- 支持 compiler、prompt、模型和依赖版本持续迭代。

## 12. 关键产品决策

### 12.1 Harness 优先于 Wrapper

不要把下一阶段做成“支持更多 Manim 类”的 wrapper。更多 primitive 会扩大表达能力，但不会解决 Agent 生成结果不稳定的问题。优先建设质量门禁、source map、layout compiler 和 regression。

### 12.2 QA 独立于 Validate

`validate` 表示 DSL 合法；`qa` 表示视频质量风险。二者分开可以保持 MVP 兼容性，也方便 Agent 在不同阶段做不同修复。

### 12.3 自动修正必须可追踪

layout compiler 可以自动缩放、arrange 或调整 buff，但所有修改必须写入 `layout_changes`。否则质量提升会变成不可解释行为。

### 12.4 Visual QA 不做主观审美

P3 只做空白、越界、贴边、密度等基础检查。不要在第一阶段判断“好不好看”。审美判断不稳定，难以形成工程约束。

### 12.5 CLI 不内置 LLM

Manim Harness 服务 Agent，但不内置 Agent。CLI 保持 deterministic tool，便于测试、复现和接入不同上层系统。

因此 Phase 1 的可靠性边界是“已生成 artifact 的质量门禁”，不是“LLM 生成过程的稳定性”。上层 Agent 可以把 model id、prompt version、temperature 写入 manifest，Harness 负责保存和展示这些元数据，但不把 LLM drift 作为 CLI 自身的回归失败。

## 13. 冲突与取舍

### 13.1 `validate` 当前包含 quality warnings

现状：`validate_scene_data(...)` 默认 `quality_gate="off"`，只表达 DSL schema / semantic legality。`validate --quality-gate relaxed|strict|final` 保留兼容入口，会调用 `quality_warnings(...)` 并输出旧 warning dict。独立 `manim-cli qa` 已承担 layout、pedagogy、alignment、timing、math lint 等质量风险。

冲突：PRD 新定位要求 `validate` 只表达 DSL 合法性，`qa` 表达视频质量风险。

已落地取舍：

- 保留 `validate --quality-gate` 一段时间作为兼容入口。
- 文档和 Agent workflow 统一使用 `qa`。
- `validate` 默认不再输出教学/布局质量 warning。

### 13.2 `LayoutSpec` 已存在，但 slot 还偏“中心点移动”

现状：`layout.slot` 已进入模型；`slot_region(scene, slot)` 已作为安全矩形接口，`slot_center` 基于 region 派生以保持兼容。compiler 仍支持创建时 `move_to(slot_center)` 和长文本 `scale_to_fit_width`，并新增 step-level `layout` action，可在步骤中移动对象到 slot 或 custom region。

冲突：PRD 中的 layout slots 是安全区域和编译约束，不只是把对象移到一个中心点。

已落地取舍：

- 短期保留 `slot_center` 兼容。
- `slot_region` 已成为下一阶段主接口。
- QA 和 compiler 已开始从 center-based layout 迁移到 region-based layout；复杂 arrange / fit 仍待实现。

### 13.3 Source Map 已有行级映射，但缺少教学语义

现状：`scene.py.map.json` 已记录 generated line 到 json path / symbol，并补充 `step_id`、`step_index`、`action_index`、`object_ids`、`narration_cue_id`、`storyboard_event_id`。新增 `manim-cli source-map lookup` 支持按 generated line、DSL path、object id、step id 反查。

冲突：PRD 需要 source map 回溯到 step id、object id、storyboard frame、plan goal，当前粒度不足。

已落地取舍：

- 已补 step/action/object 粒度，同时接入 `narration_cue_id`、`storyboard_event_id` 这类 scene 已有引用。
- storyboard frame 和 plan goal 在教学检查启用后一并进入 source map enrichment，用于 structural alignment、goal coverage 和 explainable repair。
- cue/event 级 duration 不作为 P0 source map 前置条件；它只影响 P1/P2 的精细 timing drift。

### 13.4 Visual QA 已有像素分析，但缺少视频抽帧和 source map 回链

现状：`render/visual_qa.py` 已有 `analyze_pixels(...)`、`analyze_keyframe(...)`、keyframe pixel hash 和 feedback writer。新增 `manim-cli visual-qa keyframe pixels.json` 可对 JSON pixel/keyframe fixture 做 blank、edge pressure、overfull、low contrast 检查。真实视频抽帧和 object-level 回链尚未实现。

冲突：PRD 中 Visual QA 要从 preview video 抽帧，并把 findings 关联 scene step。

已落地取舍：

- P0/P1 不依赖视频工具。
- P3 再引入抽帧工具链。
- 第一版 Visual QA 只输出 frame-level finding，不强行精确映射 object。

### 13.5 Regression runner 当前只跑 validate/compile

现状：`run_regression_dir(...)` 已执行 validate、compile、qa，并支持 `expected_qa.json` baseline、severity/fingerprint diff、known false positives、render cost proxy。新增 `manim-cli regression run` 和 `manim-cli qa-eval`。真实 render / keyframe baseline 默认仍跳过。

冲突：PRD 中 Visual Regression 要比较 QA baseline、render cost、keyframe baseline。

已落地取舍：

- Release 5 之前先做 no-render regression baseline。
- keyframe baseline 放到 Preview Visual QA 之后。
- CI 默认不 render，本地 release check 再 render。

### 13.6 Agent-friendly repair hints 与自动修复的边界

现状：QA issue 已统一包含 `repair_hints`、`repair_scope`、`issue_id`、`fingerprint`。`feedback/agent_prompt.md` 会输出高优先级 issue、scope、ID 和修复建议。`repair_context` 已支持 `repaired_issues`、`regression_reintroduced`、`new_issues_after_repair`、`repair_loop_risk`。

冲突：用户价值来自“可修复”，但自动改 JSON 容易引入不可控行为。

已落地取舍：

- 下一阶段只做 repair hints，不做自动 patch。
- repair hints 必须指向具体 path / object / step。
- repair hints 必须包含 `repair_scope`，区分 narration、visual action 和 cross-track alignment。
- 自动修复可以作为后续 `manim-cli repair` 命令单独设计。

### 13.7 Timing alignment 分两阶段

现状：`alignment_warnings(...)` 主要检查 scene step 是否引用合法的 cue/event，`build_timeline(...)` 可以得到 step 的视觉动作时长。当前数据模型里 `StoryboardFrame.duration_seconds` 存在，但 `NarrationCue` 和 `VisualEvent` 没有 duration 字段。

冲突：教学视频中“旁白说到哪里，画面动到哪里”是核心质量问题，只检查 cue/event id 存在不够；但在现有模型下，P0 不能承诺 cue/event 级 drift 检查。

取舍：

- P0 增加 `step_frame_timing_drift`：比较 scene step 动画时长之和与 `StoryboardFrame.duration_seconds`。
- 阈值默认宽松，例如 step duration 与 frame duration 偏差超过 40% 或 1.5s 才报警。
- 阈值按数学复杂度加权：简单公式使用更窄阈值，复杂公式、多行推导、分式和矩阵使用更宽阈值。
- P1/P2 给 `NarrationCue` 和 `VisualEvent` 增加 `duration_seconds: Optional[float]` 后，再启用真正的 `cue_event_timing_drift`。
- Visual QA 阶段再结合真实 render / audio metadata 做二次检查。

复杂度权重第一版只用启发式：

```text
complexity = token_count
  + 3 * number_of_fractions
  + 2 * tex_tree_depth
  + 2 * number_of_lines
  + 2 * matrix_or_cases_blocks
```

`step_frame_timing_drift` 的阈值不直接等于固定 40%，而是：

```text
allowed_drift = max(1.0s, base_ratio(complexity) * frame_duration)
```

这不是教学节奏真值，只是避免“简单等式给太久”和“复杂公式被误报”的第一层保护。

## 14. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| bbox 估算不准 | 误报或漏报重叠 | 输出 `bbox_confidence` 和 measurement method；P0 只阻断高置信 bbox；Tex/Tex 进入 Visual QA 或 quick probe |
| LaTeX 宽度无法纯静态精确确定 | Tex/MathTex 误判 | P0 不用 Tex/Tex 静态 overlap 阻断；strict/final 可要求 quick LaTeX probe 或 preview Visual QA |
| timing duration 估算不准 | 误报 step-frame drift | 默认宽松阈值并按公式复杂度加权；P0 只使用 `StoryboardFrame.duration_seconds`；cue/event 级检查等 duration 字段补齐后再做 |
| 数学语义 lint 过度自信 | 错把合法推导判错 | P0 只检查显式可判定硬错误；通用等价证明不进 P0；缺 metadata 时降级为 warning |
| repair loop 震荡 | Agent 反复引入旧问题 | QA 接收 `repair_context`，输出 `regression_reintroduced` 和 `new_issues_after_repair` |
| QA report token 过大 | Agent 消化成本高 | 同时输出完整 JSON 和短 `feedback/agent_prompt.md` |
| layout slots 限制表达力 | 复杂场景受限 | 保留 absolute / relative position，slot 作为推荐路径 |
| 自动布局不可解释 | Agent 难以修复 | 所有自动修改写入 `layout_changes` |
| QA 过严 | 阻断可接受视频 | 默认 relaxed，CI 和 final 使用 strict |
| Visual QA 依赖视频处理工具 | 跨平台复杂 | 放到 P3，P0/P1 不依赖 |
| 过早扩 API | 产品失焦 | 把 Graph / Brace / NumberPlane 放在 Harness Core 之后 |

## 15. 最小可行下一步

当前 Harness Core 已进入可用状态。下一阶段最小可行路径：

```text
expand QA eval seed set to 10-20 scenes
  -> add real video keyframe extraction
  -> add opt-in Manim/LaTeX bbox probe
  -> connect Visual QA findings to source-map / visible-set context
  -> implement first-use delayed mobject creation (derive from SceneAnalysis.object_lifetimes)
  -> add keyframe visual regression baseline
  -> add manifest comparison for regression
```

这条路径从“render 前静态质量门禁”推进到“render 后真实画面回归”，同时保持原则：不做主观审美判断，不把 Tex 静态估算当真值，不在 CLI 内置 LLM。
