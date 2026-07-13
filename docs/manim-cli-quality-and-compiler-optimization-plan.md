# manim-cli 视频质量与编译器优化方案

## 1. 背景

当前 `manim-cli` 已经跑通 MVP 链路：

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

现阶段主要问题不是单点功能缺失，而是缺少面向“最终视频质量”的约束系统。`validate` 主要检查 JSON schema、字段枚举和引用关系；`compile` 主要负责把 DSL 翻译成确定性的 Manim Python；`render` 主要负责调用 Manim 输出视频。

因此，画面重叠、对象越界、节奏拥挤、公式过长、渲染慢等问题会在较晚阶段才暴露，导致 Agent 需要反复试错。

本方案目标是把 `manim-cli` 从“能生成视频的 DSL 工具”升级为“能稳定生成可读教学视频的质量控制流水线”。

## 2. 优化目标

### 2.1 视频质量目标

- 减少对象重叠、文字遮挡、画面越界。
- 降低单屏视觉密度，提升可读性。
- 固化标题区、主体区、公式区、说明区等安全布局。
- 让 Agent 少猜坐标，多表达布局意图。
- 让质量问题尽量在 render 前暴露。
- 渲染后能抽帧诊断，并反馈到最近上游 artifact。

### 2.2 编译器目标

- 减少重复解析、重复编译和重复渲染。
- 支持 preview / final 两种不同编译策略。
- 在编译期优化动画、对象生命周期和静态布局。
- 生成更少、更清晰、更可诊断的 Manim Python。
- 为后续增量渲染、分段渲染和视觉 QA 留出接口。

### 2.3 总体性能目标

这里的“速度”分三类：

| 类型 | 主要瓶颈 | 优化方向 |
|------|----------|----------|
| CLI compile 速度 | JSON 解析、Pydantic 校验、Python 生成、`py_compile` | 缓存、单次解析、fast mode |
| Manim render 速度 | LaTeX、动画数量、分辨率、fps、对象复杂度 | preview 策略、动画合并、对象复用、分段渲染 |
| 端到端生成速度 | 质量返工次数 | render 前质量诊断、抽帧 QA、结构化反馈 |

## 3. 现状问题

### 3.1 质量约束不足

当前 DSL 支持 `absolute`、`edge`、`relative`、`align_to` 等位置表达，但缺少：

- 安全区检查。
- 同屏对象碰撞检查。
- 字号与文本长度约束。
- 可见对象数量限制。
- 标题、主体、公式、注释的区域分配。
- 画面密度评分。

结果是：只要 JSON 字段合法，CLI 就认为 scene 合法，即使最终画面明显重叠。

### 3.2 缺少时间轴可见性模型

`mobjects` 是全局定义，`steps` 决定对象何时出现或消失。但当前验证阶段没有模拟每一步的可见对象集合。

这会带来两个问题：

- 不能准确判断同一时间哪些对象会互相遮挡。
- 不能检测对象生命周期异常，例如未清理旧对象导致画面越来越拥挤。

### 3.3 过度依赖绝对坐标

复杂场景里，Agent 很容易生成大量 `position.mode = "absolute"` 的对象。绝对坐标短期直接，但长期不稳定：

- 文本长度变化后容易越界。
- 对象大小变化后容易重叠。
- 不同分辨率或 frame height 下难以复用。
- Agent 需要凭经验猜坐标。

### 3.4 编译器只翻译，不优化

当前 `compile` 主要做语法翻译：

```text
Scene DSL -> GeneratedScene.construct()
```

它没有做：

- 对象复用。
- 动画合并。
- preview 模式降级。
- 静态对象分层。
- 延迟创建对象。
- 布局归一化。
- 编译缓存。

### 3.5 渲染成本没有被提前控制

Manim 渲染慢通常来自：

- 大量 `Tex` / `MathTex` LaTeX 编译。
- 太多独立 `self.play(...)`。
- 高分辨率和高 fps。
- 长动画和大量 wait。
- 对象数量过多。

当前 CLI 没有在编译期给出成本预估，也没有对 preview render 做足够 aggressive 的降级。

### 3.6 教学语义准确性没有进入校验闭环

参考论文 `LLM2Manim: Pedagogy-Aware AI Generation of STEM Animations` 的 Fig. 1 / Fig. 3 / Fig. 4，该类系统的准确性不只来自代码能运行，还来自更早阶段的教学规划约束：

- scene goals 是否覆盖用户问题。
- symbol list 是否固定符号、单位和假设。
- narration cues 是否和 visual events 同步。
- storyboard frames 是否有明确布局、时间和 allowed primitives。
- 代码生成失败时是否只修复局部，而不是全量重来。

当前 `manim-cli` 已有 `plan.json`、`storyboard.json`、`scene.json` 三段 artifact，但 plan / storyboard 对 scene 的约束还偏弱。结果是：CLI 能检查 DSL 合法，却很难判断“讲解是否准确”“公式是否前后一致”“旁白和画面是否同步”。

## 4. 质量优化方案

### 4.1 增加布局质量校验

在 `validate scene.json` 基础上增加 `layout_validate` 阶段，输出 warning / error / score。

建议检查项：

| 检查项 | 说明 | 默认级别 |
|--------|------|----------|
| safe area | 对象 bbox 是否超出画面安全区 | error |
| overlap | 同一步可见对象 bbox 是否重叠 | warning / error |
| text width | 文本估算宽度是否超过区域 | warning |
| font size | 字号是否过大或过小 | warning |
| density | 单屏可见对象数量是否过多 | warning |
| bottom collision | 底部公式区和说明区是否冲突 | error |
| title collision | 标题区是否被主体对象侵占 | error |
| edge margin | 对象距离边缘是否太近 | warning |

输出示例：

```json
{
  "ok": false,
  "phase": "validate",
  "error_type": "layout_overlap",
  "message": "Visible objects overlap in step_show_small_squares",
  "location": {
    "path": "$.steps[3]",
    "objects": ["square_a_area", "plus_label"]
  },
  "suggestions": [
    "Move plus_label to the right of square_a_area with a larger buff.",
    "Use a horizontal layout slot instead of absolute coordinates."
  ]
}
```

### 4.2 建立时间轴可见性模型

新增内部结构 `SceneTimeline`：

```text
step_id
  visible_before
  visible_after
  entered
  exited
  transformed
```

动作语义：

| Action | 可见性影响 |
|--------|------------|
| `add` | target 变为 visible |
| `write` | target 变为 visible |
| `fade_in` | target 变为 visible |
| `show_creation` | target 变为 visible |
| `fade_out` | target 变为 hidden |
| `remove` | target 变为 hidden |
| `transform` | target 保持 visible，to 的可见性需要明确策略 |
| `highlight` | 不改变可见性 |
| `wait` | 不改变可见性 |

`transform` 建议在 Phase 1 明确语义：

- `to` 只作为 transform target template，不自动 visible。
- 或增加 `replace: true|false`，明确 transform 后是否替换源对象。

### 4.3 bbox 估算与碰撞检测

在不运行 Manim 的情况下，先做保守 bbox 估算。

基础对象估算：

| 类型 | bbox 来源 |
|------|-----------|
| `Circle` | center + radius |
| `Square` | center + side_length |
| `Line` | start / end + stroke_width buffer |
| `Arrow` | start / end + stroke_width / tip buffer |
| `Dot` | point + radius |
| `Axes` | center + width / height |
| `Text` | text length + font_size 估算 |
| `Tex` | tex length + font_size 估算，保守放大 |

第一版不追求像素级准确，重点是拦住明显问题。后续可通过 Manim dry-run 或截图抽帧修正。

### 4.4 引入布局槽位

在 DSL 中加入高层布局意图，减少绝对坐标：

```json
{
  "id": "formula",
  "type": "Text",
  "args": {"text": "a² + b² = c²", "font_size": 56},
  "layout": {
    "slot": "bottom_formula",
    "align": "center"
  }
}
```

建议内置槽位：

| Slot | 用途 |
|------|------|
| `title` | 顶部标题 |
| `subtitle` | 标题下方说明 |
| `main` | 主体区域 |
| `left_panel` | 左侧图形 |
| `right_panel` | 右侧说明或公式 |
| `bottom_formula` | 底部公式 |
| `caption` | 最底部短说明 |
| `callout` | 局部提示 |

槽位由编译器映射到 Manim 坐标，Agent 优先表达意图，而不是手写坐标。

### 4.5 自动缩放与避让

编译前增加 layout normalization：

- 长文本自动限制最大宽度。
- 公式自动 `scale_to_fit_width`。
- 面板内对象超出高度时整体缩放。
- `relative` 布局冲突时增大 `buff`。
- 同槽位多个对象自动 `arrange`。
- 标题、底部公式和主体对象保持最小间距。

这类修正必须可追踪，建议输出 `layout_changes`：

```json
{
  "object": "conclusion",
  "change": "scale_to_fit_width",
  "from": 7.8,
  "to": 6.4,
  "reason": "caption slot max width exceeded"
}
```

### 4.6 DSL 扩展

为了减少手工坐标，需要补充 Manim 高价值能力：

| 能力 | 优先级 | 原因 |
|------|--------|------|
| `VGroup` / `Group` | P0 | 组合布局和整体变换的基础 |
| multi-target action | P0 | 合并动画、降低代码重复 |
| `arrange` | P0 | 公式栈、对象行列布局 |
| `scale_to_fit_width` | P0 | 防止长文本越界 |
| `to_corner` | P1 | 标题、角标、提示稳定定位 |
| `SurroundingRectangle` | P1 | 高亮区域更清晰 |
| `Brace` | P1 | 数学讲解常用 |
| `MathTex` | P1 | 区分公式与普通 Tex |
| `NumberPlane` | P2 | 函数和坐标讲解 |
| camera movement | P2 | 复杂视频节奏控制 |

## 5. 教学准确性优化方案

本节借鉴 `LLM2Manim` 论文中的 pedagogy-aware pipeline：先规划，再生成细节描述，再生成代码，再用反馈和错误摘要做局部修复。它对 `manim-cli` 的关键启发是：准确性校验要前置到 `plan.json` 和 `storyboard.json`，不能只在 `scene.json` 或 render 阶段兜底。

### 5.1 强化 Plan First, Then Generate

当前 artifact 链路已经具备 plan / storyboard / scene，但需要把上游 artifact 变成强约束：

```text
brief.md
  -> plan.json       # 教学目标、符号账本、旁白 cue
  -> storyboard.json # 分镜、视觉事件、布局/时间约束
  -> scene.json      # 可编译 DSL
```

建议 `plan.json` 必须回答：

- 本视频解释什么概念。
- 面向什么水平的学习者。
- 学生看完应掌握哪些 learning goals。
- 哪些符号、单位、假设必须保持一致。
- 哪些推导步骤不能跳过。

建议 `storyboard.json` 必须回答：

- 每个 frame 对应哪个 learning goal。
- 每个 frame 的 narration cue 是什么。
- 每个 visual event 展示什么对象、强调什么符号。
- 每个 frame 的 layout / timing / allowed primitives 约束是什么。

### 5.2 Symbol Ledger 强约束

论文中 symbol list 用于固定 notation、units、assumptions。`manim-cli` 已有 `symbol_ledger`，但应升级为准确性校验来源。

建议检查项：

| 检查项 | 说明 |
|--------|------|
| symbol defined | `scene.json` 中出现的重要变量必须在 `symbol_ledger` 中定义 |
| canonical tex | 同一符号必须使用统一写法，例如 `v` / `\vec{v}` 不应混用 |
| color role | 同一符号跨 scene / step 颜色保持一致 |
| unit consistency | 有单位的物理量不能在推导中丢失或换单位 |
| assumption coverage | 推导用到的假设必须在 plan 或 narration 中出现 |
| symbol reuse conflict | 同一个符号不能在同一视频里表示两个概念 |

建议 `symbol_ledger` 扩展：

```json
{
  "symbol": "T",
  "meaning": "temperature",
  "canonical_tex": "T",
  "unit": "K",
  "color_role": "state_variable",
  "aliases": ["temperature"],
  "scope": "global"
}
```

### 5.3 Cue-Event Alignment

论文强调 narration cues linked to visual events，用 timing markers 保持 speech-visual alignment。当前 `StepDef` 已有 `narration_cue_id` 和 `storyboard_event_id`，但还需要校验它们是否真的对齐。

建议检查项：

| 检查项 | 说明 |
|--------|------|
| cue coverage | 每个 narration cue 至少对应一个 visual event 或 step |
| event coverage | 每个 visual event 至少对应一个 action |
| symbol visibility | 旁白提到的符号在同一时间段可见或被 highlight |
| temporal contiguity | 视觉事件不能明显早于或晚于对应旁白 |
| focus agreement | visual event 的 focus 必须能映射到 scene 对象 |
| redundant text | 屏幕文字不应重复旁白全文，避免认知负荷过高 |

建议 diagnostic 示例：

```json
{
  "ok": false,
  "phase": "alignment",
  "error_type": "cue_event_mismatch",
  "message": "Narration cue cue_relation mentions c², but area_label_c2 is not visible in the linked step.",
  "location": {
    "cue_id": "cue_relation",
    "storyboard_event_id": "event_highlight_small_areas",
    "path": "$.steps[5]"
  }
}
```

### 5.4 Detail Description Generation

论文 Fig. 1 中的 Detail Description Generation 很适合补强 storyboard。建议在 storyboard frame 或 visual event 中增加结构化细节描述，而不是让 Agent 从高层 intent 直接跳到 scene DSL。

建议字段：

```json
{
  "id": "frame_relation",
  "section": "area relationship",
  "input_goal": "Explain that the two leg areas combine to equal the hypotenuse area.",
  "visual_elements": ["square_a_area", "square_b_area", "square_c_area", "formula"],
  "animation_logic": "Show a² and b² first, then reveal equality with c².",
  "state_transitions": [
    "small squares visible",
    "equals sign appears",
    "c square fades in",
    "formula is written"
  ],
  "camera_behavior": "static",
  "mathematical_derivation": ["a²", "b²", "a² + b²", "a² + b² = c²"],
  "layout_constraints": {
    "left_panel": ["triangle"],
    "right_panel": ["area blocks"],
    "bottom_formula": ["formula"]
  }
}
```

这些字段可以驱动：

- scene 生成。
- cue-event alignment。
- symbol consistency。
- derivation step coverage。
- layout validate。

### 5.5 Mathematical Derivation Check

数学和物理动画的准确性经常坏在“推导跳步”或“符号突然变化”。建议增加轻量推导检查，不追求完整 theorem prover，而是先做结构一致性。

第一阶段检查：

- 每个 derivation step 中出现的符号都在 symbol ledger 中。
- 新符号首次出现时必须有解释或 visual event。
- 相邻公式之间不能突然删除关键项，除非 storyboard 说明了操作。
- 等式左右两边变量集合变化需要有 reason。
- 单位维度明显不一致时 warning。

后续可扩展：

- 使用 SymPy 检查简单代数等价。
- 对常见公式模板做 domain-specific validator。
- 对物理量做 dimensional analysis。

### 5.6 Goal Coverage Check

每个 learning goal 应被 storyboard 和 scene 覆盖。建议建立映射：

```text
learning_goal
  -> teaching_sequence item
  -> storyboard frame
  -> visual event
  -> scene step
```

检查项：

- learning goal 没有对应 storyboard frame：error。
- storyboard frame 没有 scene step：error。
- scene step 没有对应 narration cue：warning。
- 某个 visual event 没有实现：error。

这可以避免视频看起来完成了，但漏掉了关键教学目标。

### 5.7 Parallel Tracks and Local Repair

论文中的并行生成与合并机制值得借鉴：旁白和代码分轨生成，哪个坏修哪个，避免错误扩散。

建议把 artifact 分成四条可局部修复的轨道：

| Track | Artifact | 常见问题 | 修复策略 |
|-------|----------|----------|----------|
| pedagogy | `plan.json` | 目标不清、受众不匹配 | 重写 plan |
| narration | `plan.json` / narration cues | 讲解不准、节奏不稳 | 只修 cue |
| storyboard | `storyboard.json` | 分镜缺步骤、事件错位 | 只修 frame/event |
| implementation | `scene.json` | 布局、动作、渲染失败 | 只修 step/mobject |

diagnostic 应始终指向最近上游 artifact，而不是默认让 Agent 重写全部内容。

### 5.8 HITL 三类审查

论文保留 human-in-the-loop，并采用 subject-matter、teaching quality、engineering 三类 quick-pass criteria。`manim-cli` 可以把这三类变成 final gate 的审查清单：

| 审查类型 | 自动检查 | 人工确认 |
|----------|----------|----------|
| subject-matter | symbol consistency、derivation check、unit check | 概念是否真的正确 |
| teaching quality | goal coverage、cue-event alignment、density score | 节奏和解释是否易懂 |
| engineering | validate、compile、render、visual QA、regression scenes | 最终视频是否可交付 |

### 5.9 Build Manifest and Reproducibility

论文建议保存 model id、prompt version、Manim / LaTeX versions 等信息。建议 `manim-cli` 在每次 compile / render 后写入 build manifest：

```json
{
  "manim_cli_version": "0.1.0",
  "manim_version": "...",
  "python_version": "...",
  "latex_version": "...",
  "ffmpeg_version": "...",
  "model_id": "...",
  "prompt_version": "...",
  "scene_hash": "...",
  "compile_profile": "preview",
  "render_profile": "draft"
}
```

收益：

- 复现某次错误。
- 比较不同 prompt / compiler 版本的输出差异。
- 为 regression scenes 提供环境上下文。

### 5.10 Regression Scene Suite

论文提到 curated regression test scenes。建议建立 `tests/fixtures/regression_scenes/`，覆盖高频 STEM 场景：

- 单公式推导。
- 多步公式变换。
- 几何证明。
- 坐标系与向量。
- 函数图像。
- 物理状态变量。
- 标签密集的图形解释。

每个 regression scene 保存：

- `plan.json`
- `storyboard.json`
- `scene.json`
- expected diagnostics
- preview keyframes baseline
- render cost baseline

当 templates、DSL、compiler、Manim 版本变化时，自动重跑并比较：

- 是否仍能 validate / compile / render。
- diagnostics 是否发生非预期变化。
- keyframe 是否出现明显视觉退化。
- render cost 是否异常上升。

## 6. 编译器优化方案

### 6.1 单次解析与校验

当前 `compile_scene_file` 存在“先 validate，再 parse”的重复工作。建议改为：

```text
load_json once
  -> parse SceneDef once
  -> semantic_validate(scene)
  -> compile_scene(scene)
```

收益：

- 减少 IO 和 Pydantic parse。
- 让 validate / compile 共用同一份结构化对象。
- 后续 layout validate 可以复用 scene，不重复读文件。

### 6.2 编译缓存

对 `scene.json` 内容、CLI 版本、编译选项计算 hash：

```text
cache_key = hash(scene_json_content, manim_cli_version, compile_mode, target_profile)
```

如果 cache hit：

- 复用 `generated/scene.py`。
- 复用 `scene.py.map.json`。
- 返回 cached diagnostic。

缓存元数据：

```json
{
  "cache_key": "...",
  "scene_hash": "...",
  "compiler_version": "0.1.0",
  "mode": "preview",
  "scene_py": "generated/scene.py",
  "source_map": "generated/scene.py.map.json",
  "created_at": "..."
}
```

### 6.3 编译模式

新增 compile profiles：

| 模式 | 用途 | 行为 |
|------|------|------|
| `strict` | 默认交付 | 完整 validate、layout validate、`py_compile` |
| `fast` | Agent 快速迭代 | 可跳过 `py_compile`，使用缓存 |
| `preview` | 低清预览 | 动画降级、run_time 缩短、低成本对象策略 |
| `final` | 高清交付 | 完整动画、完整质量门禁 |

命令示例：

```text
manim-cli compile scene.json --out generated --profile preview
manim-cli compile scene.json --out generated --profile final
```

### 6.4 可选 `py_compile`

`py_compile` 对发现代码生成 bug 有价值，但在快速迭代时可以变成可选。

建议：

- `strict` / `final` 默认开启。
- `fast` / `preview` 可以关闭。
- CI 测试永远开启。

### 6.5 更精确的 import 收集

当前编译器固定导入所有 MVP 颜色和方向。建议按实际使用收集：

- mobject 类型 import。
- action 类型 import。
- style 中实际使用的颜色。
- position 中实际使用的方向。
- rate function 中实际使用的函数。

收益不主要是速度，而是：

- 生成代码更清晰。
- source map 和错误诊断更聚焦。
- 后续支持更多 Manim 类型时避免 import 膨胀。

### 6.6 动画合并

把相邻且可并行的 action 合并为一个 `self.play(...)`。

示例 DSL：

```json
[
  {"type": "fade_in", "target": "a", "run_time": 0.5},
  {"type": "fade_in", "target": "b", "run_time": 0.5},
  {"type": "fade_in", "target": "c", "run_time": 0.5}
]
```

可编译为：

```python
self.play(FadeIn(a), FadeIn(b), FadeIn(c), run_time=0.5)
```

合并规则：

- action 类型兼容。
- 没有依赖关系。
- `run_time` 和 `rate_func` 相同或可统一。
- 不跨 step 合并，除非显式开启优化。

收益：

- 减少 Manim animation scheduling 开销。
- 减少视频中不必要的串行动画。
- preview 更快，节奏更紧凑。

### 6.7 wait 合并和节奏压缩

连续短 wait 可以合并。preview 模式可以缩短 wait：

```text
preview_wait = min(original_wait, 0.2)
preview_run_time = min(original_run_time, 0.5)
```

建议策略：

| 模式 | run_time | wait_after |
|------|----------|------------|
| preview | 限制最大值，必要时整体乘 0.5 | 限制最大值 |
| final | 使用原始值 | 使用原始值 |

### 6.8 静态对象直接 add

某些对象如果只是背景、坐标轴、网格、装饰框，不需要动画出现。可在 DSL 或 storyboard 中标记：

```json
{
  "id": "axes",
  "type": "Axes",
  "render_role": "static_background"
}
```

编译器将其放入：

```python
self.add(axes)
```

而不是 `Create(axes)`。

收益：

- preview 更快。
- 画面更稳定。
- 降低动画噪音。

### 6.9 对象延迟创建

当前所有 mobject 都在 `construct()` 开头创建。对于复杂场景，可以按首次使用 step 延迟创建：

```text
first_use_step(object_id)
  -> emit object construction before first visible action
```

收益：

- 降低场景初始化成本。
- 减少未使用对象干扰诊断。
- 为分段渲染做准备。

注意：

- `relative` position 引用目标对象时，需要保证依赖对象已经创建。
- transform target template 需要特殊处理。

### 6.10 对象复用和 copy

重复 `Text` / `Tex` / `MathTex` 会带来额外构造成本，尤其是 LaTeX。

编译器可以检测相同内容和样式：

```text
(type, args, style) identical
  -> create template once
  -> use .copy()
```

适合：

- 重复符号。
- 多处出现的公式片段。
- 坐标标签。

不适合：

- 需要独立 updater 的对象。
- 后续会被 transform 并改变内部结构的对象。

### 6.11 LaTeX 缓存与降级

Manim 本身有一定缓存，但 CLI 可以在更高层做成本控制：

- 对重复 Tex 做复用。
- 对 preview 模式优先使用 `Text` 或简化公式。
- 对复杂 Tex 给出 warning。
- 对相同公式统一 canonical tex。

建议增加 `tex_complexity_score`：

```text
score = length + command_count * 3 + environment_count * 10
```

超过阈值时提示拆分或简化。

### 6.12 分段编译与分段渲染

长期最有效的渲染提速方案是按 step 或 section 切分：

```text
GeneratedScene_step_001
GeneratedScene_step_002
GeneratedScene_step_003
```

修改某一段后，只重渲染受影响段，最后用 ffmpeg 拼接。

需要编译器提供：

- step dependency graph。
- 每段初始状态。
- 每段输出路径。
- 拼接 manifest。

第一版可以只支持 storyboard frame 级分段，不必支持任意 step。

## 7. 渲染优化方案

### 7.1 preview / final 渲染策略

当前 render 只有 `low` 和 `high`。建议拆成更明确的 profile：

| Profile | 分辨率 | FPS | 目标 |
|---------|--------|-----|------|
| `draft` | 480p | 10-15 | 快速检查布局 |
| `preview` | 720p | 15-24 | 用户预览 |
| `final` | scene config | scene config | 最终交付 |

`draft` 应尽量快，允许动画压缩和质量降级。

### 7.2 成本预估

在 render 前输出估算：

```json
{
  "estimated": {
    "visible_object_peak": 12,
    "animation_count": 38,
    "tex_count": 9,
    "total_run_time": 42.5,
    "render_cost_score": 78
  }
}
```

可设置阈值：

- `render_cost_score > 100`：warning。
- `visible_object_peak > 15`：warning。
- `tex_count > 20`：warning。

### 7.3 只渲染局部

新增命令能力：

```text
manim-cli render scene.json --step step_show_small_squares
manim-cli render scene.json --frame frame_003
manim-cli render scene.json --from-step a --to-step b
```

这要求编译器能生成局部 scene 或在 Python 中跳过不相关步骤。

### 7.4 渲染产物缓存

缓存维度：

```text
scene_hash
compile_profile
render_profile
step_range
manim_version
```

cache hit 时直接返回已有 mp4 / png / diagnostics。

## 8. 渲染后视觉 QA

### 8.1 抽帧检查

preview 渲染后自动抽取关键帧：

- 每个 step 结束帧。
- 每个 storyboard frame 中点。
- 视频首帧和尾帧。

输出：

```text
feedback/frames/
  step_001.png
  step_002.png
  ...
feedback/latest.md
```

### 8.2 图像级检查

第一版可做无需 OCR 的基础检查：

- 非背景像素 bbox 是否压边。
- 画面是否近似空白。
- 画面是否过满。
- 亮度 / 对比度是否过低。
- 相邻关键帧变化是否异常小。

后续可加入 OCR 或视觉模型检查：

- 文字是否重叠。
- 公式是否可读。
- 标签是否贴错对象。
- 主视觉是否居中。

### 8.3 反馈格式

`feedback/latest.md` 建议面向 Agent：

```md
# Render Feedback

## Blocking

- `step_show_small_squares`: `plus_label` overlaps `square_a_area`.
- `step_final_formula`: `conclusion` is too close to bottom edge.

## Suggestions

- Move `plus_label` into `right_panel` or increase horizontal spacing.
- Reduce `conclusion` font size from 23 to 20 or use caption slot.
```

同时保留机器可读 JSON：

```text
feedback/latest.json
```

## 9. 质量门禁

新增 `--quality-gate`：

```text
manim-cli validate scene.json --quality-gate relaxed
manim-cli validate scene.json --quality-gate strict
manim-cli render scene.json --quality-gate final
```

建议门禁：

| Gate | 用途 | 行为 |
|------|------|------|
| `off` | 调试 | 不阻断 |
| `relaxed` | MVP 默认 | error 阻断，warning 放行 |
| `strict` | final 前 | 高风险 warning 也阻断 |
| `final` | 交付 | 必须通过 layout、render、visual QA |

质量评分：

```json
{
  "quality": {
    "layout_score": 86,
    "readability_score": 78,
    "density_score": 82,
    "timing_score": 74,
    "render_cost_score": 61
  }
}
```

## 10. Agent 工作流优化

### 10.1 Skill 规则加强

Agent 生成 scene 时应遵守：

- 每屏最多 5-7 个主要对象。
- 标题固定在 `title` slot。
- 主体图形优先放 `main` / `left_panel`。
- 公式优先放 `bottom_formula` / `right_panel`。
- 说明文字优先放 `caption`。
- 禁止默认使用绝对坐标。
- 标签优先 `relative` 到目标对象。
- 新信息出现前先清理旧信息。
- 长句拆分，不把整段话塞进一个 Text。
- 先生成 detail description，再生成 scene DSL。
- scene 中出现的公式、符号、单位必须能回溯到 `symbol_ledger`。
- narration cue 提到的重点必须在对应 step 可见或被 highlight。
- preview 失败时先修 `scene.json`，不改 `generated/scene.py`。

### 10.2 artifact 反馈闭环

推荐流程：

```text
validate schema
  -> validate pedagogy
  -> validate alignment
  -> validate layout
  -> compile preview
  -> render draft
  -> extract frames
  -> visual QA
  -> write feedback/latest.md
  -> Agent repairs scene.json
```

Agent 每次只修最近上游 artifact：

| 失败阶段 | 修复对象 |
|----------|----------|
| plan validate | `plan.json` |
| storyboard validate | `storyboard.json` |
| pedagogy validate | `plan.json` 或 `storyboard.json` |
| alignment validate | `storyboard.json` 或 `scene.json` |
| scene schema validate | `scene.json` |
| layout validate | `scene.json` |
| compile | `scene.json` 或 compiler bug |
| render | `scene.json` 或依赖环境 |
| visual QA | `scene.json`，必要时 `storyboard.json` |

## 11. 分阶段落地计划

### Phase 0: 低风险性能改造

目标：不改变 DSL 语义，先提升 CLI 迭代速度。

- 单次 parse / validate。
- 编译缓存。
- 可选 `py_compile`。
- compile profile: `strict` / `fast`。
- render cost 基础统计。

交付标准：

- 同一 `scene.json` 重复 compile 可以 cache hit。
- fast compile 不执行 `py_compile`。
- compile diagnostic 标明是否来自 cache。

### Phase 1: 静态质量诊断

目标：在 render 前发现明显画面问题。

- 时间轴可见性模型。
- bbox 估算。
- safe area 检查。
- 同步可见对象 overlap 检查。
- density 检查。
- text / tex 估算宽度检查。

交付标准：

- 能指出哪个 step、哪些对象发生风险。
- 示例项目可生成 layout diagnostic。
- quality gate 可控制 warning 是否阻断。

### Phase 2: 教学准确性诊断

目标：把 plan / storyboard 变成 scene 的准确性约束来源。

- symbol ledger consistency。
- cue-event alignment。
- goal coverage check。
- visual event implementation check。
- detail description schema。
- build manifest。

交付标准：

- 能发现符号未定义、符号含义冲突、cue 没有对应 event。
- 每个 learning goal 能追踪到 storyboard frame 和 scene step。
- diagnostic 能指向 `plan.json` / `storyboard.json` / `scene.json` 的最近修复位置。

### Phase 3: 编译期布局归一化

目标：让 CLI 不只是报错，也能做安全修正。

- layout slots。
- `scale_to_fit_width`。
- 同槽位 arrange。
- 自动 buff 调整。
- 标题、主体、底部公式安全区。

交付标准：

- Agent 可以少用绝对坐标。
- 编译结果包含 `layout_changes`。
- 常见文本越界可自动修正。

### Phase 4: 渲染速度优化

目标：减少 Manim 渲染成本。

- preview / final 编译策略。
- 动画合并。
- wait 压缩。
- 静态对象直接 add。
- Text / Tex 对象复用。
- Tex complexity warning。

交付标准：

- preview render 总时长明显下降。
- 生成 Python 行数减少或更清晰。
- 动画数量和总 run_time 有统计输出。

### Phase 5: 渲染后视觉 QA

目标：让 preview 反馈更接近真实观看质量。

- 抽取关键帧。
- 空白帧检查。
- 非背景 bbox 压边检查。
- 画面密度检查。
- 输出 `feedback/latest.md` 和 `feedback/latest.json`。

交付标准：

- render 后自动产生可读反馈。
- Agent 能依据反馈定位 `scene.json` 路径。

### Phase 6: Regression Scene Suite

目标：防止 prompt、DSL、compiler、依赖版本变化导致输出退化。

- curated STEM regression scenes。
- expected diagnostics baseline。
- preview keyframe baseline。
- render cost baseline。
- build manifest comparison。

交付标准：

- 改动 compiler 后能一键跑核心场景。
- 可以发现明显视觉退化、诊断退化和渲染成本异常。

### Phase 7: 分段编译与增量渲染

目标：大幅降低局部修改后的等待时间。

- step / storyboard frame dependency graph。
- 局部 scene 生成。
- 局部 render。
- ffmpeg 拼接 manifest。
- 渲染产物缓存。

交付标准：

- 修改单个 step 后只重渲染相关片段。
- final render 可复用未变化片段。

## 12. 优先级建议

如果当前最痛的是“画面重叠、不可读”，优先级：

1. 时间轴可见性模型。
2. bbox 估算。
3. safe area / overlap / density 检查。
4. layout slots。
5. 自动缩放和 arrange。

如果当前最痛的是“生成太慢”，优先级：

1. 编译缓存。
2. preview profile。
3. 动画合并。
4. wait 压缩。
5. Tex / Text 复用。
6. 分段渲染。

如果目标是端到端稳定交付，推荐顺序：

```text
Phase 0
  -> Phase 1
  -> Phase 2
  -> Phase 4
  -> Phase 3
  -> Phase 5
  -> Phase 6
  -> Phase 7
```

原因是：先提升迭代速度，再减少质量和准确性返工，然后再做自动布局、视觉 QA、回归场景和分段渲染。

如果目标是提升“教学准确性”，优先级：

1. symbol ledger consistency。
2. cue-event alignment。
3. goal coverage check。
4. detail description schema。
5. derivation validity check。
6. regression scene suite。

推荐最小准确性闭环：

```text
plan.json symbol ledger
  -> storyboard cue/event mapping
  -> scene step references
  -> alignment validate
  -> local repair
```

## 13. 风险与取舍

### 13.1 bbox 估算不准确

静态估算不会完全等于 Manim 实际 bbox，尤其是 `Tex`。第一版应保守估算，只拦截明显问题，避免误伤。

### 13.2 自动布局可能改变创作意图

自动缩放和避让需要可关闭，并输出 `layout_changes`。final 模式建议保守，preview 模式可以更 aggressive。

### 13.3 动画合并可能改变节奏

合并只应发生在同 step、无依赖、参数兼容的 action 上。需要保留 `disable_optimization` 或 `sequence: true` 之类的逃生口。

### 13.4 分段渲染复杂度高

分段渲染需要处理场景初始状态和跨段对象生命周期，不适合作为早期任务。应先完成时间轴模型，再做分段。

### 13.5 教学准确性校验可能误判

symbol consistency、goal coverage、derivation check 只能先做结构化近似，不能替代领域专家。final gate 应保留 HITL 审查入口，自动检查负责发现高风险点和减少漏检。

### 13.6 Detail description 增加生成负担

让 Agent 多生成一层 detail description 会增加 artifact 复杂度。取舍上，应先只要求关键 frame 和复杂推导填写完整字段，简单过渡 frame 可以使用默认模板。

## 14. 建议新增模块

建议后续拆分模块：

```text
manim_cli/
  dsl/
    compiler.py
    optimizer.py        # 动画合并、对象复用、profile 策略
    layout.py           # bbox、slot、safe area、normalization
    timeline.py         # 可见性模型、step dependency
    cost.py             # render cost 估算
  planning/
    pedagogy.py         # goal coverage、symbol ledger、derivation checks
    alignment.py        # narration cue 与 visual event 对齐检查
  render/
    runner.py
    cache.py            # render artifact cache
    visual_qa.py         # 抽帧和图像检查
  feedback/
    writer.py           # latest.md / latest.json
  regression/
    manifest.py         # regression scene manifest 和 baseline comparison
```

第一批新增模块建议只做：

- `timeline.py`
- `layout.py`
- `planning/pedagogy.py`
- `planning/alignment.py`
- `optimizer.py`

## 15. 验收指标

### 15.1 质量指标

- 示例项目中明显重叠问题能在 render 前发现。
- final gate 下没有对象越界。
- 单屏主要对象数量可统计。
- `feedback/latest.md` 能指出具体 step 和对象 id。

### 15.2 准确性指标

- `scene.json` 中核心符号能回溯到 `symbol_ledger`。
- 每个 learning goal 至少被一个 storyboard frame 和 scene step 覆盖。
- narration cue 提到的核心符号在对应 step 可见或被 highlight。
- 常见符号漂移、单位缺失、visual event 未实现能被 diagnostic 捕获。
- build manifest 能记录影响复现的关键版本信息。

### 15.3 性能指标

- 同一 scene 二次 compile 命中缓存。
- preview profile 的总动画时长低于 final profile。
- 相邻兼容动画能合并。
- 重复 Tex / Text 可复用。
- 大型 scene 局部修改后可避免全量重渲染。

### 15.4 工程指标

- 所有诊断都能映射到 DSL path。
- 生成的 Python 仍然确定性、可 diff。
- 默认行为兼容 MVP。
- 严格模式可用于 CI。
- regression scenes 能在 DSL / compiler 变更后发现输出退化。

## 16. 总结

短期最值得做的是：

```text
时间轴可见性
  + bbox 估算
  + safe area / overlap 检查
  + symbol ledger consistency
  + cue-event alignment
  + compile cache
  + preview profile
```

这组改动能同时解决三个核心问题：

- 视频质量问题更早暴露，减少 Agent 返工。
- 教学准确性问题前置到 plan / storyboard 阶段，减少符号漂移和讲解错位。
- 预览迭代更快，减少等待时间。

中长期再引入 layout slots、自动归一化、视觉 QA、regression scenes 和分段渲染，把 CLI 从 MVP 工具推进到稳定的视频生成基础设施。
