# Manim Harness PRD Review：缺口与建议

> 本文档基于 [manim-cli-phase-1-product-prd.md](./manim-cli-phase-1-product-prd.md) 与论文
> [LLM2Manim: Pedagogy-Aware AI Generation of STEM Animations](https://arxiv.org/html/2604.05266)
> 的对比分析，并经过代码库现状验证，供 Codex review 使用。
>
> 本文仅做分析，不修改任何代码。

---

## 0. 结论速览

| 评估维度 | 结论 |
|---|---|
| 文档合理性 | ✅ 合理。定位清晰、优先级正确、边界克制、与代码现状基本吻合。 |
| 是否达到论文理论 | ✅ 达到。在验证侧（QA Gate、Source Map、Regression）覆盖并细化了论文的 reliability mechanisms。 |
| 是否超过论文 | 🟡 部分超越。在"布局重叠静态检测""错误可定位性""结构化 repair"三处明确超越论文（这些恰是论文未解决/靠人工的问题）。 |
| 关键不足 | ❌ timing alignment 检查缺失（论文头号难题）；bbox 对 LaTeX 的根本限制被低估；无验证方法论；不覆盖生成侧 drift。 |

一句话：PRD 在"质量约束层"这一维度超过论文（论文是 HITL 兜底，PRD 是工程化门禁），但在"时间对齐"和"生成侧可靠性"两个维度落后于论文。补上 timing check 和 QA gate 的 precision/recall 验证，就能形成对论文的完整超越。

---

## 1. 对比基线：论文的可靠性理论

论文（LLM2Manim）的可靠性建立在六层防线上，最终仍需人工兜底：

| 层 | 论文机制 | 性质 |
|---|---|---|
| 1 | Plan-first（scene goals + symbol list + storyboard + code constraints） | 生成侧约束 |
| 2 | Parallel narration/code tracks（错误隔离，局部重生成） | 生成侧约束 |
| 3 | Deterministic scaffolding（低温度、受限 primitive、constrained template） | 生成侧约束 |
| 4 | Symbol ledger + lightweight validators（imports/LaTeX/timing/meaning checks） | 验证侧 |
| 5 | Regression scenes + build manifest（防 LLM drift / library breakage） | 回归侧 |
| 6 | Three-pass HITL review（subject-matter / teaching / engineering） | 人工兜底 |

论文明确承认未解决的问题：

- 布局重叠（Fig 2 用 "text and figure overlap" 作为典型问题，靠人工修复）
- 长视频可靠性（仅 3-10 min 验证）
- 全自动化（HITL 必需；减少 HITL 是 future work）
- 跨模型版本鲁棒性（仅缓解）
- 低基础学习者受益更少（H3 被数据推翻）

---

## 2. PRD 超越论文之处（保持并强化）

| 维度 | 论文 | PRD | 判定 |
|---|---|---|---|
| 布局重叠 | 未解决，靠人工修复（Fig 2） | QA Gate 的高置信 bbox 检查 + Layout Slots 安全区域 + Visual QA 回填 Tex 真实 bbox | **部分超越**——几何/文本高置信问题前置，LaTeX overlap 不在 P0 静态阶段强判 |
| 静态预渲染质量门禁 | "lightweight validation"（imports/LaTeX/run/cue-event/meaning）笼统 | 正式化的 QA Gate：score、severity、profile、Issue schema | **超越**——把"轻量检查"升级为工程化门禁 |
| 错误可定位性 | 并行 track 隔离 + 局部重生成，但无正式 traceability | Source Map（line → scene path → object → step → storyboard frame → plan goal） | **超越**——论文只能"重生成整个 scene/part"，PRD 能精确定位 |
| Agent 可执行修复 | 依赖人工读懂 traceback | Repair Hints（结构化、指向具体 path/object） | **超越**——这是减少 HITL 的关键路径 |
| 回归基线 | regression scenes + build manifest（定性比较） | QA baseline + keyframe baseline + render cost baseline + manifest diff | **超越**——更系统化 |
| 视觉后检 | 全部预渲染检查 | Visual QA：抽帧 + blank/edge/density 检测 | **超越**——论文无 post-render 视觉分析 |

---

## 3. 缺口（PRD 不足或缺失）

### 缺口 1（最重要）：无并行 track 概念——错过了论文的关键可靠性洞察

论文 §II-C 明确指出：narration 和 code 并行生成，错误隔离，只重生成坏的那条 track。这是论文可靠性的核心设计之一（"a code break does not contaminate the narration"）。

PRD 完全没有这个概念。PRD 的工作流是单向链路：

```text
Brief -> Plan -> Storyboard -> Scene DSL -> ...
```

scene.json 同时承载视觉和旁白 cue。一旦某处出错，Agent 修复粒度是"scene.json 的某个 step"，而非"只重生成 narration track 或 code track"。

这不是必须照搬，但 PRD 应该明确说明：为什么不拆分 track，以及当前单 scene.json 设计的错误隔离边界在哪里。

**代码现状**：`manim_cli/dsl/models.py` 的 `StepDef` 同时包含 `actions`（视觉）和 `narration_cue_id`（旁白），二者耦合在一个 step 内。

### 缺口 2：timing drift / temporal contiguity 检查缺失

论文 §II-B 用 timing markers 显式处理 narration cue 与 visual event 的时间漂移（"if they drift, adjust timing or regenerate"）。论文明确指出 temporal contiguity 是 "prominent difficulty"。

PRD §2 列出了"旁白 cue 和视觉事件不同步"作为痛点，但 QA Gate 的检查项里**没有任何时间对齐检查**。

**代码现状**：

- `manim_cli/planning/alignment.py:10` 的 `alignment_warnings` 做的是**结构性检查**（step 是否引用了合法的 cue_id / event_id），而非**时间性检查**（cue 的 narration 时间戳与 visual event 的动画时间是否对齐）。
- `manim_cli/dsl/timeline.py` 的 `build_timeline` 能提取每个 step 的 entered/exited/transformed，但未与 plan.json 的 cue duration 做比对。

这是 PRD 与论文之间最大的**理论落差**——论文认为这是最难的问题，PRD 却没正面处理。

### 缺口 3：bbox 估算的根本性困难被低估

PRD §14 把 "bbox 估算不准" 列为风险并说"先保守估算"。但问题比表述的更深：

- `Tex` / `MathTex` 的宽度**取决于 LaTeX 编译结果**，无法在不调用 LaTeX 的情况下静态确定。
- `Text` 的宽度取决于字体度量，Manim 社区内部也是用渲染后测量。
- 动画过程中的 bbox（Transform 前/后）变化巨大。

**代码现状**：`manim_cli/dsl/layout.py:41` 的 `estimate_bbox` 存在，但其对 LaTeX 类型的精度是核心瓶颈，当前没有置信度标记。

论文绕开了这个问题（直接渲染再人工看），PRD 试图静态解决——这是更大的野心，但也暴露在更高的误报/漏报风险下。

### 缺口 4：无任何评估方法论

论文有严格的对照实验（N=100, A-B crossover, ANCOVA, 效应量, CI）。PRD §10 的"成功指标"全是工程指标（"QA issue 100% 含 object id"），**没有任何关于"QA gate 是否真的提升了最终视频质量"的验证设计**。

- 如果这是研究/学术导向，这是硬伤。
- 如果是纯工程产品，可以接受——但建议至少设计一个"QA gate 命中率 vs 人工标注"的验证实验。

### 缺口 5：不覆盖生成侧可靠性（刻意但需说明影响）

论文可靠性理论有**一半在生成侧**（低温度、受限 primitive、constrained template、parallel track）。PRD §12.5 明确"CLI 不内置 LLM"，这是正确的架构决策，但意味着：

- PRD 只覆盖"验证侧 + 回归侧"，生成侧的 drift 控制完全依赖上层 Agent。
- 论文的 regression scenes + build manifest 是**双向**的（既检测生成 drift 也检测库 breakage），PRD 的 regression 只检测 compiler/DSL 变更，**不检测 LLM 模型版本变更**（因为 CLI 不调 LLM）。

这是范围选择问题，但 PRD 应明确：Manim Harness 只对"已生成的 scene.json"负责，不对"LLM 生成 scene.json 的稳定性"负责。

---

## 4. 建议

### 建议 1：补上 timing alignment 检查（理论落差最大处）

论文视 temporal contiguity 为头号难题。最终建议采用两阶段 timing alignment：

- P0 `step_frame_timing_drift`：利用已有的 `build_timeline` 提取 step 动画时长，与 `StoryboardFrame.duration_seconds` 比对。
- P1/P2 `cue_event_timing_drift`：在 `NarrationCue` 和 `VisualEvent` 增加 `duration_seconds` 后，再做 cue/event 级漂移检查。
- timing 阈值不采用固定比例，按公式 token 数、分式数量、TeX tree depth、多行/矩阵结构做复杂度加权。

这是从"工程约束"向"教学可信"升级的关键，也是对论文最直接的补强。

### 建议 2：正视 bbox 估算对 LaTeX 的根本限制

不要承诺静态精确估算。建议：

- 明确分层：几何 primitive（Circle/Rectangle/Arrow）用解析估算；Text 用中置信启发式；Tex/MathTex 标记为 `bbox_confidence: unknown_static`。
- P0 不用 Tex/Tex 静态 overlap 阻断；strict/final 如需阻断，需要先跑 quick LaTeX probe 或 preview Visual QA。
- 考虑：compile 阶段 Manim 实际渲染后回填真实 bbox，反哺给 QA 做二次检查（半静态半动态）。

### 建议 3：引入 partial-regen / track 隔离的概念

即便不拆分 narration/code 成独立 track，也应该在 source map 和 repair hints 中体现**最小修复单元**：

- repair hint 应指明"只需改 narration cue"还是"只需改 visual action"还是"两者都要改"。
- 这呼应论文 parallel drafting 的精神：让 Agent 只改坏的部分。

### 建议 4：为 QA Gate 设计验证实验

不要只交付"能输出 issue 的 CLI"。建议增加：

- 一个小型标注集（10-20 个 scene，人工标注真实重叠/越界/密度问题）。
- 衡量 QA gate 的 precision / recall / false-positive rate。
- 这既是论文级别的贡献，也是产品信任的基础。论文缺少这一步（它验证的是学习效果，没验证 pipeline 本身的检测质量）。

### 建议 5：明确与 LLM 生成层的关系边界

在 PRD 中增加一节"与生成 Agent 的契约"：

- Manim Harness 假设输入 scene.json 已生成。
- Manim Harness 的 regression **不覆盖** LLM 模型版本变更（只覆盖 DSL/compiler/Manim 版本）。
- 建议上层 Agent 配合提供 build manifest（model id / prompt version），这样 source map 和 regression 可以追溯生成来源——这正好复用论文的 build manifest 概念，但放到 Harness 层消费。

### 建议 6：教学准确性（§9）应提前，不应只是"长期护城河"

**代码现状**：symbol ledger、cue-event alignment、learning goal coverage **已经实现**（`manim_cli/planning/pedagogy.py`、`manim_cli/planning/alignment.py`），只是产出松散 warning dict 而非结构化 Issue。

建议：

- 把这些已有的教学检查**立刻纳入统一 Issue schema**，不要等到"长期"。
- 论文恰恰是因为有 symbol ledger + goal coverage 才自称 "pedagogy-aware"。PRD 把这个优势埋在了"扩展"章节，反而弱化了差异化。

### 建议 7：修正文档中的小不准

- §8.3 称 "`LayoutSpec` 已存在"——实际代码中是 `LayoutDef`（`manim_cli/dsl/models.py`）。
- §13.1 称 validate 默认会因质量 warning 失败——实际 `validate_scene_data`（`manim_cli/dsl/validators.py:35`）默认 `quality_gate="relaxed"`，只有显式 `strict`/`final` 才阻断。措辞应改为"strict 模式下会"。

---

## 5. 代码库现状验证（供 Codex 核实）

| PRD 声明 | 代码现状 | 判定 |
|---|---|---|
| `manim_cli/dsl/timeline.py` 已有 `build_timeline(scene)` | `manim_cli/dsl/timeline.py:25` 确实存在 | ✅ |
| `estimate_bbox(...)`、`layout_warnings(...)` 已有 | `manim_cli/dsl/layout.py:41`、`:129` 确实存在 | ✅ |
| `LayoutSpec` 已存在 | 实际是 `LayoutDef`（`manim_cli/dsl/models.py`），无 `LayoutSpec` 类 | ❌ 名称不符 |
| `slot_center(scene, slot)` 已存在 | `manim_cli/dsl/layout.py:101` 确实存在 | ✅ |
| `slot_region` 待新增 | 当前不存在，只有 `slot_center` 和 `slot_max_width` | ✅ 一致 |
| `validate_scene_data(..., quality_gate="strict")` | `manim_cli/dsl/validators.py:35`，默认 `quality_gate="relaxed"` | ⚠️ 默认值描述不准 |
| validate 会调用 `quality_warnings(...)` | `validators.py:44` 确实调用，含 layout/pedagogy/alignment warnings | ✅ |
| `manim-cli qa` 命令待新增 | 当前 CLI 只有 8 个命令（init/plan/storyboard/validate/compile/render/diagnose/manifest），无 qa | ✅ 一致 |
| `render/diagnose.py` 已能映射 line→source map | `manim_cli/render/diagnose.py:44` `map_line` 存在 | ✅ |
| `render/visual_qa.py` 已有 `analyze_pixels` / `write_feedback` | `manim_cli/render/visual_qa.py:12`、`:51` 存在，但**未接入任何 CLI 命令** | ⚠️ 是死代码 |
| `regression/manifest.py` 已有 `run_regression_dir` | `manim_cli/regression/manifest.py:10` 存在，但**只跑 validate+compile，render 参数形同虚设** | ⚠️ 功能缩水 |
| `CodeWriter.source_map(...)` 已存在 | `manim_cli/dsl/writer.py:26` 存在 | ✅ |
| compile 输出 `scene.py.map.json` | `manim_cli/dsl/compiler.py:55`、`:87` 确实输出 | ✅ |
| source map 含 `step_id`、`object_ids` | 当前只有 `json_path`、`python_lines`、`symbol`，**缺 step_id 和 object_ids** | ❌ 字段缺失 |
| symbol ledger 已实现 | `manim_cli/planning/models.py:19` `SymbolLedgerItem` + `pedagogy.py:43` `symbol_warnings` | ✅ |
| learning goal coverage 已实现 | `manim_cli/planning/pedagogy.py:72` `goal_coverage_warnings` | ✅ |
| cue-event alignment 已实现 | `manim_cli/planning/alignment.py:10` `alignment_warnings`（结构性，非时间性） | ⚠️ 不含 timing |
| 统一 Issue schema | 不存在，当前是松散 warning dict | ❌ 缺失 |
| repair_hints | 不存在，仅 `jsonio.py:32` 有通用 `suggestions` | ❌ 缺失 |

---

## 6. 给 Codex 的 review 要点

1. **缺口 1（并行 track）和缺口 2（timing alignment）是理论层落差，优先讨论是否接受、如何补。**
2. **缺口 3（bbox 对 LaTeX 的限制）是工程层硬约束，建议明确置信度分层策略。**
3. **建议 4（QA gate 验证实验）和建议 6（教学检查提前）是对产品最有价值的增量，建议优先采纳。**
4. **建议 7（文档修正）是小修，但影响 PRD 可执行性，应一并修正。**

---

## 7. Codex 专家评估与处理结论

以下结论以 Agent 工作流和 Python/Manim 工程实现为判断基准，不按论文逐项照搬，而按 Phase 1 是否可落地、是否能降低 Agent 返工、是否能保持 CLI deterministic 来取舍。

### 7.1 总体判断

opencode 的核心质疑成立：PRD 原版确实低估了 timing alignment 和 LaTeX bbox 的工程难度，也缺少 QA Gate 自身的验证方法论。二审进一步确认：当前 `NarrationCue` 和 `VisualEvent` 没有 duration 字段，因此 P0 不能承诺 cue/event 级 drift 检查。上述问题已经在 PRD 中补为明确产品约束：

- QA Gate P0 增加 `step_frame_timing_drift`。
- P1/P2 增加 `NarrationCue.duration_seconds` 和 `VisualEvent.duration_seconds` 后，再启用 `cue_event_timing_drift`。
- bbox estimator 增加 `bbox_confidence` / measurement method，对 `Tex` / `MathTex` 明确标记为 `unknown_static`，P0 不用 Tex/Tex 静态 overlap 阻断。
- 成功指标增加人工标注集、precision、recall、false-positive rate。
- CLI 与生成 Agent 的边界改为 manifest 契约，不把 LLM drift 归因给 Harness。

### 7.2 建议采纳矩阵

| opencode 建议 | 结论 | 处理 |
|---|---|---|
| 补 timing alignment 检查 | 调整采纳 | P0 改为 `step_frame_timing_drift`，比较 scene step 动画时长与 `StoryboardFrame.duration_seconds`；P1/P2 补 `NarrationCue.duration_seconds` / `VisualEvent.duration_seconds` 后再做 `cue_event_timing_drift`。 |
| 正视 bbox 对 LaTeX 的限制 | 采纳并加强 | PRD 已把 LaTeX bbox 定位为 `unknown_static`；几何对象 `high`，Text `medium`，Tex/MathTex 不做 P0 静态重叠阻断，strict/final 需要 quick LaTeX probe 或 Visual QA。 |
| 引入 partial-regen / track 隔离 | 调整采纳 | 不在 Phase 1 强制拆 narration/code 两套 artifact；改用 `repair_scope` 表达最小修复单元：`narration_cue`、`visual_action`、`cross_track_alignment`、`artifact_reference`。这对 Agent 更直接，也不破坏现有 scene.json。 |
| 为 QA Gate 设计验证实验 | 采纳 | PRD 已新增 QA 有效性指标：10-20 个人工标注 scene，统计 precision/recall/false positive rate。 |
| 明确与 LLM 生成层的关系边界 | 采纳 | PRD 已新增“与生成 Agent 的契约”和 12.5 边界说明；Harness 负责已生成 artifact 的质量门禁，manifest 记录 model/prompt 元数据。 |
| 教学准确性提前 | 采纳 | PRD 已把“教学准确性扩展”改为“教学准确性约束”，Phase 1 纳入 symbol ledger、goal coverage、structural cue-event alignment。 |
| 修正文档小不准 | 部分采纳 | `quality_gate` 默认 relaxed 的质疑成立；但 `LayoutSpec` 不存在这一条不成立，当前代码 `manim_cli/dsl/models.py` 已有 `LayoutSpec`。 |

### 7.3 对并行 track 质疑的最终判断

论文里的 parallel narration/code tracks 是生成侧可靠性设计；Manim Harness 的定位是质量编译器和 CI 层，不内置 LLM，也不应为了贴合论文而强制上层 Agent 拆成两个生成管线。

Phase 1 更合适的工程解法是：

- scene.json 保持单一 artifact，降低工具链复杂度。
- `StepDef` 继续允许 `actions` 与 `narration_cue_id` 在同一个 step 内关联。
- Source Map 补齐 `step_id`、`action_index`、`object_ids`、`narration_cue_id`、`storyboard_event_id`。
- Repair Hint 用 `repair_scope` 告诉 Agent 只改旁白、只改视觉动作，还是同时改两者。

这样可以获得论文中“错误隔离、局部重生成”的主要收益，同时避免 Phase 1 引入双 track 同步、merge、版本一致性和 schema 迁移成本。

### 7.4 对 timing alignment 的实现建议

建议先做数据模型可支持的轻量静态版本，不要直接上音频强对齐。P0 的可用数据是 scene step duration 和 storyboard frame duration：

```text
scene.step actions run_time + wait_after
  vs
storyboard frame duration_seconds
```

P0 规则：

- 只有在 `StoryboardFrame.duration_seconds` 存在时启用。
- step duration 与 frame duration 使用复杂度加权阈值；简单公式阈值更窄，复杂公式、多行推导、分式和矩阵阈值更宽。
- strict/final profile 可把连续 drift 或大幅 drift 升级为 error。
- issue location 指向 step 和 storyboard frame，`repair_scope = "cross_track_alignment"`。

P1/P2 再补齐：

- `NarrationCue.duration_seconds: Optional[float]`
- `VisualEvent.duration_seconds: Optional[float]`
- cue/event 级 `cue_event_timing_drift`

这比纯引用合法性更有教学意义，也能保持 P0 不依赖渲染、音频工具链或尚不存在的数据字段。

### 7.5 对 bbox 的实现建议

PRD 不应承诺静态 bbox 精确。Python/Manim 实现上建议：

- `BBox` 扩展字段：`confidence: Literal["high", "medium", "unknown_static"]`、`method`、`padding`。
- overlap 规则根据 confidence 决定 severity；P0 默认只阻断 high/high 几何重叠。
- `Tex` / `MathTex` 标记为 `unknown_static`，输出 `bbox_unmeasured` 或 `layout_needs_visual_qa`，不作为 P0 fail 条件。
- Visual QA 或 quick LaTeX probe 作为后续真实测量来源，不进入 Release 1 的硬依赖。

这能避免 QA Gate 因 LaTeX 误报过多而失去 Agent 信任。

### 7.6 需要后续代码实现的点

PRD 已解决产品和理论层面的质疑，但代码仍需要跟进：

- 新增统一 `Issue` / `RepairHint` schema。
- 新增 `manim-cli qa` 命令。
- `quality_warnings(...)` 从 validate 迁移或复用到 QA 模块。
- `build_timeline(...)` 增加 step duration 计算。
- `NarrationCue` / `VisualEvent` 后续增加可选 duration 字段，支撑 cue/event 级 drift。
- `estimate_bbox(...)` 返回 confidence。
- source map enrichment：step/action/object/cue/event。
- regression runner 增加 QA baseline。

结论：opencode review 的高优先级建议应采纳；二审指出的 timing duration 数据模型缺口成立，PRD 已改为 P0 step/frame 级检查、P1/P2 cue/event 级检查。唯一需要反驳的是 `LayoutSpec` 的代码事实判断。Phase 1 不应变成论文复刻，而应把论文中的可靠性洞察转化为 Harness 可维护、可测试、可被 Agent 消费的工程契约。

---

## 8. opencode 二审处理

二审结论基本接受：

| 异议 | 结论 | 处理 |
|---|---|---|
| `LayoutSpec` 存在 | 接受事实修正 | 当前代码确实有 `LayoutSpec`，原 review 的“无 LayoutSpec”判断作废。 |
| timing drift 缺 duration 数据模型 | 接受 | PRD 改为两阶段：P0 `step_frame_timing_drift`，P1/P2 增加 cue/event duration 后做 `cue_event_timing_drift`。 |
| §9 与 P0 优先级矛盾 | 接受 | §9 已改为 P0 做 step-frame timing drift，P1/P2 做 cue/event timing drift。 |
| §13.3 取舍过时 | 接受 | §13.3 已改为 P1 补 step/action/object + cue/event 引用，storyboard frame 和 plan goal 随教学检查接入 source map enrichment。 |

关键工程判断：在当前 Python 数据模型下，P0 不应该新增一个依赖不存在字段的检测项。先用已有 `StoryboardFrame.duration_seconds` 做 frame 级 drift，可以产生真实价值，也不会让 QA Gate 的实现建立在隐含 schema 变更上。

---

## 9. deepseek 数学与 Agent 侧 review 处理

deepseek 的 review 补上了前两轮没有充分展开的两个硬问题：数学语义风险和 Agent repair loop 风险。其中 LaTeX bbox 的判断尤其关键：它不是单纯“低置信度”，而是静态不可知。

### 9.1 采纳矩阵

| deepseek 建议 | 结论 | 处理 |
|---|---|---|
| LaTeX bbox 是结构性不可知，不应把 Tex/Tex overlap 作为 P0 主规则 | 采纳 | PRD 已把 `Tex` / `MathTex` 从 `low` 改为 `unknown_static`；P0 不用 Tex/Tex 静态 overlap 阻断，只输出 `layout_needs_visual_qa` / `bbox_unmeasured`。 |
| 数学语义一致性应进 P0 | 限定采纳 | P0 增加 explicit math safety lint：显式分母零、未定义符号引用、带 metadata 的符号类型漂移；Tex transform relation 放到 P1/P2。 |
| timing drift 应引入数学复杂度权重 | 采纳 | `step_frame_timing_drift` 从固定阈值改为复杂度加权阈值，考虑 token count、fraction、tree depth、line count、matrix/cases block。 |
| repair loop 震荡风险 | 采纳 | PRD 增加 `repair_context` 输入和 `repaired_issues`、`regression_reintroduced`、`new_issues_after_repair` 输出。 |
| Layout Slots 表达力悬崖 | 采纳 | PRD 增加 `layout.slot = "custom"` + `layout.region`，保留安全区域约束但不强制预设 arrange。 |
| repair scope 需要 action 级 | 采纳 | `repair_scope` 增加 `single_action`，action 级 issue 必须带 `action_index`。 |
| QA feedback token 效率 | 采纳 | QA/Visual QA 输出增加 `feedback/agent_prompt.md`，作为 Agent 默认消费的短摘要；完整信息保留在 JSON。 |

### 9.2 LaTeX bbox 的最终定位

P0 Static QA 的职责不是“猜对 LaTeX 渲染尺寸”，而是提前拦截确定性高的问题。最终规则：

- 几何对象 overlap：P0 可阻断。
- Text overlap：P0 可在明显重叠时 warning/strict error。
- Tex/Tex、Tex/Text overlap：P0 不阻断，只提示需要 quick LaTeX probe 或 preview Visual QA。
- QA 指标单独统计 `unknown_static`，不让 LaTeX 静态误报污染 layout precision。

这会牺牲一部分 P0 recall，但换来更重要的 Agent 信任：QA Gate 报 error 时应尽量是真的。

### 9.3 数学语义 lint 的边界

deepseek 提到的数学问题都重要，但不能把 Phase 1 变成 CAS 或 theorem prover。Release 1 可落地边界是：

- `math_denominator_zero`：只检查显式可判定模式，例如同一 frame 中同时有 `1/(x-1)` 和 `x=1`。
- `math_undefined_symbol`：step 使用符号，但前序 step、symbol ledger、mobject math metadata 均未引入。
- `math_symbol_type_drift`：依赖 symbol ledger 或 mobject math metadata，检查 scalar/vector/matrix/domain/shape 前后冲突。

`math_transform_without_relation` 放到 P1/P2：Tex/MathTex 之间的 `transform` 必须带 `semantic_relation`、`reason` 或 storyboard event 解释；否则建议改成 `FadeOut + Write`。

没有 metadata 或无法解析时，只能 warning，不能 error。P0 目标是抓“明显错视频”，不是证明每一步都数学等价。

### 9.4 Agent 侧应对策略

Repair Hints 从“告诉 Agent 改哪里”升级为“帮助 Agent 不要循环返工”：

- `single_action` 缩小修改半径，降低引入新 bug 的概率。
- `repair_context` 记录本轮修复目标和历史问题。
- `regression_reintroduced` 明确指出旧问题回归，阻止 A/B 修复震荡。
- `feedback/agent_prompt.md` 降低 token 成本，让 Agent 直接看到高优先级修复摘要。

结论：deepseek 的核心观点应采纳，但数学语义部分必须限定在静态可判定 lint。Manim Harness 的 Phase 1 不应该声称理解所有数学推导；它应该可靠地阻断显式硬错误，并把不可判定部分交给 metadata、Visual QA 或人工审阅。

### 9.5 deepseek 复审补充处理

deepseek 复审认可分层架构后，补充要求把三个低成本高收益项前移到 Release 1。处理结论：

| 补充建议 | 结论 | PRD 调整 |
|---|---|---|
| custom layout region 提到 Release 1 | 采纳 | P0 增加 custom layout region boundary check；P2 保留 custom region 的 arrange / fit 策略。 |
| 数学硬错误 lint 具体化 | 采纳 | Release 1 明确三条规则：`math_denominator_zero`、`math_undefined_symbol`、带 metadata 的 `math_symbol_type_drift`。 |
| QA precision/recall eval 进入 Release 1 尾声 | 采纳 | Release 1 增加 10-20 个人工标注 scene 的 QA eval seed set，输出 precision / recall / false positive rate。 |

最终 Release 1 边界：

- 静态布局：safe area、高置信 bbox overlap、density、font size、custom region 边界。
- 静态数学 lint：显式分母零、未定义符号、带 metadata 的符号类型漂移。
- timing：step-frame drift，依赖 `StoryboardFrame.duration_seconds`。
- 评估：小标注集验证，不让 QA Gate 的误报问题拖到后续版本才暴露。

仍不进入 Release 1：

- Tex/Tex overlap 阻断。
- cue/event 级 timing drift。
- 通用数学等价证明。
- custom region 的复杂 arrange / fit。
