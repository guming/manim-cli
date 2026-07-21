# Manim Video Skill 优化方案

## 1. 背景与结论

当前 `manim-video` Skill 已经建立了完整的工程链路：

```text
brief.md
  -> plan.json
  -> storyboard.json
  -> scene.json
  -> generated/scene.py
  -> renders/preview.mp4
  -> renders/final.mp4
```

现有版本在禁止手写 Manim Python、逐层验证、上游修复、渲染 QA 和 pacing 方面方向正确。主要不足是：它更擅长告诉 Agent“运行哪些命令”，却没有充分告诉 Agent“如何写出合法、连贯且优质的 artifact”。

实施前还必须解决三个事实问题：

1. 仓库中存在两份已经漂移的 Skill。
2. manifest 的能力信息本身也包含硬编码，不能天然视为唯一事实来源。
3. 当前不同安装入口的依赖声明不一致，CLI 可能在执行 manifest 前就因缺少 `yaml` 无法启动。

因此，优化顺序应是：**先统一事实来源和运行环境，再增强 CLI 自描述能力，然后提升现有示例和 Skill 合同，最后建设视觉与教学评测。**

## 2. Canonical source 决策

仓库当前存在两份实际使用的 Skill：

| 路径 | 当前状态 |
| --- | --- |
| `manim_cli/agent/skill/SKILL.md` | 60 行的打包源文件，由 `manim-cli skill install` 分发 |
| `.opencode/skills/manim-video/SKILL.md` | 250 行的已部署交互式版本，每条命令后暂停等待用户确认 |

两份文件的 frontmatter、触发条件、命令流程和交互合同已经发生漂移。

本方案规定：

- `manim_cli/agent/skill/` 是唯一 canonical source。
- `.opencode/skills/manim-video/` 是安装或同步产物，不再手工维护。
- 本地开发如需 `.opencode` 副本，应通过安装命令生成。
- CI 应验证已安装副本来源于 canonical source。
- `workflow.md` 和 references 只能补充 canonical `SKILL.md`，不能定义另一套合同。

## 3. 优化目标

1. 提高 Agent 首次生成合法 DSL 的成功率。
2. 消除 bundled Skill、deployed Skill、manifest 与 registry 之间的多重事实来源。
3. 让 artifact schema、mobject 参数和 action 契约可机器发现。
4. 明确 interactive、autonomous、preview、final 和 CI smoke 的执行边界。
5. 将 artifact、环境依赖和编译器缺陷分开处理。
6. 将自动 gate 与 Agent/人工自检明确区分。
7. 复用现有示例，避免创建新的漂移副本。
8. 建立文档、示例、registry 和安装产物的一致性测试。

## 4. 当前问题

### 4.1 Artifact 创作契约不足

Skill 要求 Agent 生成 `plan.json`、`storyboard.json` 和 `scene.json`，但缺少：

- 可直接仿写的最小合法结构；
- artifact 之间的引用关系；
- mobject 参数的完整 schema；
- action 的合法字段组合；
- 推荐布局、节奏和视觉表达规则。

`manim-cli init` 创建的是空 JSON；现有 manifest 主要输出模型名称和能力列表，Agent 仍需猜测字段结构。

### 4.2 触发范围与语言覆盖不一致

bundled Skill 中的 `educational video` 范围过宽，可能误触发普通教育视频；deployed Skill 则包含“数学教学视频”“勾股定理”等高精度中文触发词。优化时应收紧任务范围，同时保留中英文高信号触发词。

### 4.3 交互合同存在破坏性变更风险

bundled Skill 只要求用户接受 preview 后再生成 final，而 deployed Skill 的核心身份是“每条命令执行后都暂停等待用户批准”。允许 Agent 自动推进并不是普通决策规则调整，而是对现有合同的破坏性变更。

实施前必须明确保留两种模式：

- `interactive`：逐命令审批，兼容当前 deployed Skill。
- `autonomous`：gate 全部通过时允许连续执行。

兼容期内默认 `interactive`。改变默认模式必须作为独立产品决策发布，不能在文档整理中静默完成。

### 4.4 能力来源仍可能漂移

不支持能力不仅硬编码在 Skill 中，也硬编码在 `manim_cli/commands/manifest_cmd.py`。如果 Skill 完全信任 manifest，但 manifest 本身没有从 registry 派生，漂移仍然存在。

正确原则是：

- supported mobjects 从 `MOBJECT_REGISTRY` 派生；
- supported actions 从 `ACTION_REGISTRY` 派生；
- 参数 schema 从对应 Pydantic 模型生成；
- unsupported 兼容提示应删除，或集中到唯一且受测试的兼容性常量；
- CLI 与 Skill 不得分别维护相同能力列表。

### 4.5 CLI 依赖元数据不一致

`manim_cli/dsl/knowledge.py` 在模块加载阶段直接 `import yaml`。`PyYAML>=6` 已在 `pyproject.toml` 中声明，但不在 `setup.cfg` 的 `install_requires` 中。通过仍读取 `setup.cfg` 的安装路径安装时，CLI 可能在 manifest smoke test 前就报 `ModuleNotFoundError: yaml`。

进入功能优化前应：

- 统一 Python 项目元数据；
- 判断 PyYAML 是硬依赖还是可选依赖；
- 若为硬依赖，在所有支持的安装入口一致声明；
- 若为可选依赖，将 YAML 导入推迟到相关功能调用时；
- 验证每种支持的安装方式均能运行 `manim-cli manifest`。

### 4.6 验收能力被描述得过于理想化

数学正确性、视觉连续性、信息密度和教学层级目前无法全部由 CLI 自动判定。仓库已有 `visual-qa` 和 `qa-eval`，但原计划没有区分这些辅助能力与完整自动 gate。

后续文档必须明确：

- schema validation、compile、render QA 和 pacing QA 是自动 gate；
- 关键帧可读性、视觉层级和数学正确性当前主要是 Agent/人工自检；
- 未实现 OCR、参考图 diff 或数学等价验证前，不宣称这些项目是机器 gate。

## 5. 推荐 Skill 结构

```text
manim_cli/agent/skill/
├── SKILL.md
├── workflow.md
└── references/
    ├── artifact-examples.md
    ├── authoring-guide.md
    └── troubleshooting.md
```

| 文件 | 唯一职责 |
| --- | --- |
| `SKILL.md` | 触发条件、模式选择、核心规则、必须读取的引用 |
| `workflow.md` | 命令顺序、gate、失败映射、重试范围和交付清单 |
| `artifact-examples.md` | 讲解并链接 canonical 示例及 artifact 引用关系 |
| `authoring-guide.md` | 数学叙事、布局、视觉层级、节奏和自检规则 |
| `troubleshooting.md` | artifact、环境和编译器问题的分类处理 |

创作指导只放在 `authoring-guide.md`；其他文件通过链接引用，不再重复表述。

## 6. `SKILL.md` 优化设计

### 6.1 Frontmatter

建议保留中英文高精度触发词：

```yaml
---
name: manim-video
description: Create and repair Manim-based mathematical teaching videos through the manim-cli DSL. Use for equation derivations, theorem explanations, geometric constructions, mathematical graphs, animated notation or diagrams, or requests containing high-signal phrases such as "Manim 视频", "数学教学视频", "勾股定理", "公式推导", or "几何证明". Do not use for general educational videos without meaningful mathematical visualization.
---
```

### 6.2 运行时能力来源

Skill 应要求 Agent 在 authoring 前运行 manifest，并在能力可用后优先读取 schema 和 example：

```bash
manim-cli manifest
manim-cli schema plan
manim-cli schema storyboard
manim-cli schema scene
manim-cli example project
```

但只有在 manifest 的 supported 内容已经从 registry 派生后，才能将它视为权威来源。

### 6.3 文件所有权边界

允许直接编辑：

- `brief.md`
- `plan.json`
- `storyboard.json`
- `scene.json`

禁止直接修改：

- `generated/scene.py`
- source map
- diagnostics
- QA 报告
- 已渲染媒体

### 6.4 模式和输出决策

第一层选择执行模式：

| 模式 | 行为 |
| --- | --- |
| `interactive` | 每个命令完成并通过 gate 后暂停，等待用户确认 |
| `autonomous` | gate 通过后自动执行下游步骤，仅在歧义、成本或阻塞时暂停 |

第二层选择交付目标：

| 用户目标 | 行为 |
| --- | --- |
| preview | 完成 preview 与相应验收后交付 |
| final | preview 通过内部 gate 后继续生成 final；interactive 模式仍需按合同审批 |
| review first | 交付 preview，等待确认后继续 |
| CI smoke | 使用低成本质量和 `accelerated` pacing |

用户可见视频默认使用 `teaching` pacing；`preserve` 仅用于必须保留 DSL 原始时间线的场景。

### 6.5 修复决策

```text
command failure
├── artifact authoring error
│   └── repair the closest editable upstream artifact
├── environment or dependency error
│   └── repair when authorized, otherwise report the exact blocker
└── probable compiler defect
    └── preserve a minimal reproduction and diagnostics
```

任何分支都不得通过编辑 `generated/scene.py` 绕过问题。

## 7. 复用现有 canonical 示例

仓库已经包含：

- `examples/pythagorean_theorem/`
- `examples/vector_projection/`
- `examples/completing_the_square/`
- `examples/derivative_geometric_meaning/`
- `examples/sine_cosine_formulas/`
- `tests/fixtures/*.json`

不应从零创作另一套文档示例。建议将 `examples/pythagorean_theorem/` 提升为 canonical teaching fixture，因为它包含 brief、plan、storyboard、scene 和 project，并与现有中英文触发语境一致。

`artifact-examples.md` 应：

1. 链接 canonical fixture，而不是复制完整 JSON。
2. 解释 learning goal、teaching sequence、narration cue、storyboard event 和 scene reference 的对应关系。
3. 展示稳定 ID、layout、`timing_role: derivation` 和 `timing_role: conclusion` 的用法。
4. 指明其他 examples 分别适合参考哪些能力。

如果安装后的 Skill 无法访问仓库根目录，则由构建步骤从 canonical fixture 生成打包快照，并用一致性测试防止快照分叉。

canonical fixture 必须在 CI 中实际通过：

```bash
manim-cli plan validate plan.json
manim-cli storyboard validate storyboard.json
manim-cli validate scene.json
manim-cli compile scene.json --out generated --profile preview --pacing teaching
```

## 8. CLI 自描述能力优化

### 8.1 Manifest 输出 JSON Schema

manifest 不应只输出 `args_model.__name__`，还应输出模型 schema：

```python
spec.args_model.model_json_schema()
```

示例结构：

```json
{
  "mobject_types": {
    "Tex": {
      "description": "Mathematical TeX object",
      "args_model": "TexArgs",
      "args_schema": {
        "type": "object",
        "required": ["tex"],
        "properties": {
          "tex": {"type": "string"},
          "font_size": {"type": "integer", "default": 48}
        }
      }
    }
  }
}
```

action 同样需要机器可用的字段契约，避免 Agent 猜测 `target`、`to`、`duration`、`slot` 等字段组合。

### 8.2 Schema 命令

```bash
manim-cli schema plan
manim-cli schema storyboard
manim-cli schema scene
```

输出必须直接来自当前 Pydantic 模型。

### 8.3 Example 命令

```bash
manim-cli example plan
manim-cli example storyboard
manim-cli example scene
manim-cli example project
```

`example project` 应复制或输出 canonical fixture 的精简版本，而不是维护第二套手写数据。

### 8.4 暂不实施 `init --template`

仓库已有完整 examples，且计划提供 `example project`，现阶段增加 `init --template` 属于重复能力。该项移入 backlog，只有真实使用数据显示仍存在明显初始化摩擦时再评估。

## 9. Authoring 与验收边界

### 9.1 Authoring Guide

`authoring-guide.md` 统一定义：

- 每个 scene 只承担一个明确教学目标；
- 先建立符号与上下文，再执行推导；
- 优先使用 layout template、role 和 slot；
- 公式变换前后保持视觉锚点稳定；
- derivation 与 conclusion 使用对应 timing role；
- 符号含义、等价变形、图形标注和最终结论保持一致。

这些是创作规则和 Agent 自检提示，不自动等同于 CLI gate。

### 9.2 自动 gate

- plan validation；
- storyboard validation；
- scene validation；
- compile；
- render QA；
- pacing QA；
- actual duration 与 effective duration 的确定性检查。

### 9.3 Agent/人工自检

- 公式和文字是否清晰；
- 是否存在裁切、重叠或信息过密；
- 变换是否保持视觉连续性；
- 最终结论是否具有明确层级；
- 数学符号、推导和结论是否正确；
- 视频是否完成 brief 中的学习目标。

自检应优先使用现有 CLI 生成证据：

```bash
manim-cli visual-qa keyframe <pixels.json>
manim-cli visual-qa bbox-probe "<formula>"
manim-cli visual-qa render-smoke scene.json --out smoke.mp4
manim-cli qa-eval <regression-dir>
```

如果未来要将这些项目升级为自动 gate，需要另行建设 OCR、参考图 diff、数学等价验证或带人工标注的评测集。

## 10. Troubleshooting 设计

### 10.1 Artifact 错误

包括 JSON 结构错误、缺少必填字段、引用不存在的 ID、使用未支持能力以及 layout/timing QA 失败。修复最近的可编辑上游 artifact，再运行失败阶段和受影响的下游阶段。

### 10.2 环境与依赖错误

包括 CLI 不在 PATH、PyYAML/Pydantic/Manim 缺失、LaTeX 或 ffmpeg 缺失、输出目录不可写。应在授权范围内修复环境；无法修复时报告准确命令、退出状态和诊断信息，不修改 scene 猜测解决。

### 10.3 编译器缺陷

当已验证的 scene 稳定触发异常时：

1. 保存最小复现 artifact；
2. 保存结构化错误输出；
3. 记录 CLI、Python 和 Manim 版本；
4. 标记 probable compiler defect；
5. 不修改生成 Python 绕过问题。

## 11. 自动化测试

至少增加：

1. canonical `SKILL.md` frontmatter 可解析。
2. Skill 引用文件全部存在。
3. `.opencode` 安装副本来自 canonical source。
4. Skill 文档中的 CLI 命令均已注册。
5. canonical fixture 的 plan、storyboard 和 scene 全部验证通过。
6. canonical fixture 可以 compile。
7. manifest 的 supported mobjects/actions 与 registry 一致。
8. manifest args schema 与 Pydantic 模型一致。
9. unsupported 提示只有一个受测试的数据源。
10. `manim-cli manifest` 在每种支持的安装入口下完成 smoke test。
11. `interactive` 与 `autonomous` 合同在 canonical Skill 中均有明确声明。

第 11 项首先采用确定性的静态合同测试。Agent 是否能根据自然语言任务正确选择模式，应使用固定提示集运行单独的 agent eval；这类测试成本较高，不混入普通单元测试。

若 CI 具备完整渲染依赖，可增加低质量 smoke render；否则 compile 是默认下限。

## 12. 分阶段实施计划

### Phase 0：统一事实来源与运行环境

- 确认 `manim_cli/agent/skill/` 为 canonical source；
- 将 `.opencode` 副本改为安装或同步产物；
- 增加安装副本一致性测试；
- 统一 `pyproject.toml` 与 `setup.cfg` 的依赖声明；
- 修复或隔离 `yaml` 导入问题；
- 验证 manifest smoke test。

完成标准：CLI 可启动，且仓库中不存在两份可独立手工维护的 Skill。

### Phase 1A：增强 CLI 自描述能力

- manifest 输出 mobject args schema；
- action 输出字段契约；
- 增加 schema/example 命令；
- supported 能力由 registry 派生；
- unsupported 提示集中到唯一数据源。

完成标准：Agent 无需阅读 Python 源码即可获取当前 artifact 和能力契约。

### Phase 1B：提升 canonical 示例

- 将 `examples/pythagorean_theorem/` 提升为 canonical fixture；
- 新增 `artifact-examples.md` 并链接现有文件；
- 增加 validation 与 compile 测试；
- 如需打包快照，由构建过程生成并验证一致性。

完成标准：示例可验证、可编译，且没有第二份手写 JSON。

### Phase 1C：调整 Skill 合同

- 收紧触发范围并保留中英文高精度触发词；
- 明确 interactive 与 autonomous；
- 将默认模式变化标记为破坏性产品决策；
- 消除 `SKILL.md` 与 `workflow.md` 的职责重复。

完成标准：触发边界、模式和兼容策略无歧义并获得确认。

### Phase 2：补充创作与诊断指导

- 新增 `authoring-guide.md`；
- 新增 `troubleshooting.md`；
- 明确三类故障处理；
- 明确自动 gate 与 Agent 自检边界。

完成标准：创作规则只有一个文档归属，环境错误不会被误判为 scene 错误。

### Phase 3：视觉与教学评测增强

- 将现有 `visual-qa` 和 `qa-eval` 接入 workflow；
- 增加关键帧自检证据；
- 评估 OCR、参考图 diff 和数学等价验证；
- 工具就绪前保持 Agent/人工 checklist 定位。

完成标准：每项验收都明确属于机器 gate 或人工判断，不夸大现有自动化能力。

### Phase 4：回归保障

- 增加 Skill 引用与安装一致性测试；
- 增加 canonical fixture 回归；
- 增加 manifest/schema/registry 一致性测试；
- 增加独立的模式选择 agent eval。

完成标准：模型、registry、命令或 Skill 变化时，CI 能发现事实来源之间的漂移。

## 13. 优先级

1. 统一 Skill canonical source，并修复 CLI 依赖与启动卫生问题。
2. 让 manifest 输出完整参数 schema 和 action 契约，并增加 schema/example 命令。
3. 将现有 `pythagorean_theorem` 提升为 canonical fixture。
4. 明确 interactive/autonomous、preview/final 和 CI smoke 的合同与兼容策略。
5. 将 supported 能力从 registry 派生，并集中管理 unsupported 提示。
6. 接入现有 visual-qa/qa-eval，再逐步建设视觉和数学评测。

前两项解决事实来源和机器可发现性，第三项提供稳定可仿写的完整路径；三者对首次成功率和长期防漂移的收益最大。

## 14. 最终完成定义

优化完成后应满足：

- 只有 `manim_cli/agent/skill/` 是可编辑的 canonical Skill；
- 已部署副本可追溯且与 canonical source 一致；
- CLI 在所有支持安装方式下可以运行 manifest；
- Agent 能从 CLI 获取完整 artifact schema 和能力契约；
- canonical 示例与当前模型一致并由 CI 验证；
- interactive 与 autonomous 合同清楚，默认值变更经过显式决策；
- artifact、环境和编译器错误得到不同处理；
- 自动 gate 与 Agent/人工验收有清晰边界；
- `SKILL.md` 保持简洁，具体知识按需放在 workflow 和 references 中。
