# Layout Template and QA Optimization — PRD Addendum and Execution Plan

## 1. Document Purpose

This document supplements `docs/layout-template-and-qa-optimization-plan.md` and turns its remaining work into an executable delivery plan.

The original PRD remains the product-design source. This addendum is the source of truth for:

- release boundaries and implementation status;
- policy lifecycle and execution semantics;
- repair-memory integration boundaries;
- cache identity and invalidation;
- task ordering, acceptance tests, and completion criteria.

Baseline implementation: commit `a9ddeff` (`Stabilize layout QA and add template memory flow`).

## 2. Decisions and Scope Boundaries

### 2.1 Required for the Phase 6 follow-up

- YAML and JSON support for knowledge, policy, and reviewed failure documents.
- Applied policy records in compile `layout_changes`.
- Budgeted Top-K memory context for repair feedback.
- Canonical scene-layout fingerprint cache with explicit invalidation inputs.
- Render smoke coverage when the render toolchain is available.
- Automated runtime-overhead and prompt-budget coverage.
- Explicit memory inspection, review, index, and cleanup commands.

### 2.2 Deferred

- Semantic scene-type auto-classification.
- Automatic scene mutation or frame splitting during compile/render.
- Automatic promotion of failure memory into active policy.
- LLM calls made by `compile`, `qa`, or `render`.
- A general-purpose constraint solver.

### 2.3 Explicit split behavior

The system distinguishes three operations:

1. `split plan`: compile/QA may report a deterministic recommendation.
2. `split-layout`: an explicit command may write a new scene without overwriting the source.
3. automatic split mutation: deferred and forbidden during compile/render in this release.

## 3. Capability Status Matrix

| Capability | Release status | Current state at `a9ddeff` | Target completion signal |
|---|---|---|---|
| Core layout QA and bbox heuristics | Required | Done | Existing regression suite passes |
| Layout templates, roles, and fallback | Required | Done | Compile diagnostics contain selection and placement |
| Explicit split plan and command | Required | Done | Source scene is not overwritten |
| JSON knowledge/policy/failure flow | Required | Done | Record, retrieve, promote, QA matching pass |
| YAML memory documents | Required | Not started | JSON/YAML parity tests pass |
| Policy reporting in compile diagnostics | Required | Partial | Compile/validate/QA report the same policy ID |
| Policy lifecycle, precedence, and conflicts | Required | Not started | Only active policies apply with deterministic conflict behavior |
| Top-K repair context | Required | Partial | Budgeted summaries appear in repair feedback |
| Existing compile-output/retrieval caches | Existing foundation | Done but insufficient | Remain compatible until canonical cache replaces analysis reuse |
| Canonical scene-layout analysis cache | Required | Not started | Canonical hit/miss and invalidation tests pass |
| Memory index and index-first loading | Required | Not started | Normal retrieval uses a validated index; bounded scan is compatibility-only |
| Measured-layout render smoke coverage | Required when toolchain exists | Not verified | Measured safe passes and measured contradiction blocks final QA |
| Performance and token tests | Required | Not started | p95 and prompt budget gates pass |
| Full memory management CLI | Follow-up required | Partial | List/inspect/review/rebuild-index/clean pass |
| Semantic auto-classification | Non-goal | Not implemented | No work planned |
| Automatic frame splitting | Non-goal | Not implemented | No work planned |

### 3.1 Implementation progress after `a9ddeff`

The follow-up implementation is complete in the current working tree as of 2026-07-15:

| Task | Working-tree status | Verification |
|---|---|---|
| P0.1 YAML/JSON memory parity | Complete | JSON/YAML parity, duplicate-ID, safe-loader, atomic-write tests |
| P0.2 Policy lifecycle and compile diagnostics | Complete | Scope, candidate/active/disabled, limit, conflict, allow/block, cache diagnostics tests |
| P1.1 Typed Top-K retrieval | Complete | Index-first selection, source hash, thresholds, issue scoring, matched-feature tests |
| P1.2 Budgeted repair feedback | Complete | 500-token, deduplication, no-match, summary-only prompt tests |
| P2.1 Canonical layout cache | Complete | Source/layout/memory/environment invalidation and corrupt-cache tests |
| P3.1 Measured-layout render smoke | Complete with local dependency skip | Synthetic safe/contradiction paths pass; real render reports explicit dvisvgm resource skip locally |
| P3.2 Performance/token gates | Complete | Typical 40-document corpus meets the 50ms p95 target; prompt hard limit is 500 tokens |
| P3.3 Memory management CLI | Complete | List/inspect/review/promote/activate/disable/rebuild-index/clean lifecycle tests |

Current regression result: `101 passed, 1 skipped`. The single skip is the real render smoke on this machine: Homebrew dvisvgm cannot find its default map/PostScript header resources and reports `PostScript error: undefined in TeXDict`. The smoke is executable, not permanently skipped; it runs the draft render path when the toolchain status is ready.

## 4. Golden End-to-End Acceptance Paths

### 4.1 Safe template compilation

Given a scene with explicit layout roles and a fitting template, when it is compiled, then:

- compile succeeds;
- `layout_changes` records template selection, role placement, bbox source, and fitting decisions;
- strict QA reports no blocking layout issue;
- repeated compilation is deterministic.

### 4.2 Unsafe formula policy

Given an active policy matching a tall formula and crowded bottom layout, when validate, QA, and compile run, then:

- all three report the same `policy_id`;
- QA severity follows the policy type and active profile;
- compile records `layout_memory_policy_applied` in `layout_changes`;
- the applied behavior is deterministic and does not require an LLM.

### 4.3 Failure review and promotion

Given a blocking QA issue, when a developer records, reviews, and promotes it, then:

- `record` writes only to `failures/inbox/`;
- `review` explicitly moves or copies the reviewed artifact to `failures/reviewed/` according to the command contract;
- `promote` creates a `candidate` policy;
- a candidate does not affect compile/QA;
- only an explicitly activated policy affects compile/QA;
- the promotion adds or requires focused regression-test metadata.

### 4.4 Budgeted repair context

Given a failed scene with relevant knowledge and reviewed failures, when QA feedback is written, then:

- retrieval selects at most 2 knowledge summaries and 3 reviewed failure summaries;
- only `prompt_summary` and compact provenance are emitted;
- the configured prompt budget is not exceeded;
- full failure records are not inserted into the prompt;
- the CLI produces context only and performs no LLM call.

## 5. Policy Contract

### 5.1 Required lifecycle fields

Every policy must support:

```yaml
policy_id: tall_formula_bottom_region_safety
version: 1
status: candidate  # candidate | active | disabled
type: enforce      # allow | block | enforce | fallback | diagnostic
priority: 100
supersedes: []
when: {}
message: Short actionable diagnostic.
```

Lifecycle rules:

- `promote` produces `status: candidate` by default.
- Candidate and disabled policies never affect validate, QA, compile, or render.
- Activation must be explicit.
- Built-in memory is read-only.
- Project/user policy changes must never rewrite built-in policy files.

For backward compatibility, a policy without `status` is treated as `active` during the migration window. The CLI should emit a migration warning when such a policy is inspected or rebuilt into an index. A later schema version may require the field.

This compatibility rule applies only to policy files that already exist before P0.2. As part of P0.2, both the existing `knowledge promote-policy` path and the new `memory promote` path must write `status: candidate`. After P0.2 lands, no promotion command may create a status-less policy. Therefore promotion never gains active behavior through the legacy compatibility rule.

### 5.2 Policy type semantics

| Type | Required behavior |
|---|---|
| `diagnostic` | Emits an informational/warning issue and records the match; does not mutate layout |
| `block` | Produces a blocking issue in the configured profiles; never silently falls back |
| `enforce` | Applies a locally testable constraint and records its effect; failure to satisfy becomes an issue |
| `fallback` | Tries the declared ordered template alternatives and records every decision |
| `allow` | Suppresses only explicitly named compatible checks; cannot suppress unrelated blocking issues |

### 5.3 Conflict resolution

Policy evaluation must be stable and deterministic:

1. discard non-active policies;
2. resolve the same `policy_id` by scope precedence: built-in < user < project < scene inline;
3. treat a higher-scope document as a whole-document replacement, not a field merge;
4. sort by descending `priority`, then ascending `policy_id`;
5. apply `supersedes` before normal evaluation;
6. report unresolved contradictory effects as `layout_policy_conflict` rather than choosing silently.

Safety precedence across policy types is:

```text
block > enforce > fallback > diagnostic
```

Priority orders policies within the same safety level; it never allows a lower-safety type to override a higher-safety type. A matching `block` remains blocking even when a higher-priority `enforce` or `fallback` also matches. Compatible effects may all apply and be recorded. Incompatible effects produce `layout_policy_conflict`; strict/final stop before layout mutation, while relaxed reports the conflict and applies no conflicting effect.

`allow` is a narrowly scoped exception rather than a safety level. It may suppress an explicitly named diagnostic rule or the failure issue of an explicitly named enforce rule when the allow condition proves the case safe. It cannot suppress schema errors, policy conflicts, or any `block` policy.

After scope resolution, at most 20 active policies are loaded by default. If more remain, strict/final emit blocking `layout_policy_budget_exceeded` and do not partially evaluate policy. Relaxed emits a warning and deterministically evaluates the highest safety level, then priority, then policy ID up to the limit.

## 6. Memory Document and Index Contract

### 6.1 YAML/JSON parity

- Supported suffixes: `.json`, `.yaml`, `.yml`.
- YAML must use a safe loader.
- Both formats must be normalized and validated through the same schema.
- A document root must be an object/mapping.
- Unknown fields initially produce a warning; invalid required fields produce an error.
- Ambiguous YAML implicit values must be normalized or rejected by schema validation.
- Duplicate IDs in the same scope are an error, including JSON/YAML duplicates.
- Generated artifacts default to JSON; commands may add `--format json|yaml`.

### 6.2 Index behavior

- This section describes the target state, not behavior at `a9ddeff`, where documents are loaded through direct filesystem globbing.
- Normal execution reads metadata from `index.json` before opening detailed knowledge or reviewed-failure files.
- Compile/QA must never recursively scan `failures/inbox/`.
- A missing index may use a bounded direct scan for backward compatibility and must report that the index should be rebuilt.
- A corrupt or unsupported index produces an actionable diagnostic rather than silently dropping policies.
- `rebuild-index` writes atomically.
- Index entries contain metadata and a source revision/hash, not full failure bodies.
- Record, review, promote, activate, disable, and index writes all use temp-file-plus-atomic-rename. The implementation does not require multi-writer locking in this release, but readers must never observe a partially written document.

## 7. Retrieval and Repair Context Contract

### 7.1 Integration boundary

The CLI generates a repair-memory context. It does not own the LLM request.

The first integration target is `feedback/agent_prompt.md` plus a machine-readable field in QA output. Future Agent or generator code may consume the same structure.

Compile, QA evaluation, and render remain local and deterministic. Creating a feedback file is not an LLM call.

### 7.2 Per-kind retrieval budgets

```yaml
retrieval_budget:
  max_knowledge_files: 2
  max_reviewed_failures: 3
  max_policies_loaded: 20
  max_prompt_tokens: 500
  min_knowledge_score: 12
  min_failure_score: 10
```

Knowledge and failure memory are ranked separately. Policies are locally matched and are not mixed into a single global Top-K list.

Each selected result should expose:

```json
{
  "document_type": "knowledge",
  "id": "derivative_geometry",
  "score": 21,
  "matched_features": ["formula:limit_difference_quotient", "role:plot.axes"],
  "prompt_summary": "...",
  "source_scope": "project"
}
```

Tie-breaking is descending score followed by ascending stable ID. Duplicate IDs are resolved by scope precedence before ranking.

The current implementation does not use the PRD's symbolic scoring formula directly: it scores mobject overlap at 2, formula-feature overlap at 3, role overlap at 3, and template matches at 4. P1.1 must either preserve these current weights with tests or intentionally replace them with documented per-kind weights. The PRD formula is a target model, not an assertion about today's implementation.

### 7.3 Prompt budgeting

- Include summaries only; never include the complete source document.
- Deduplicate identical summaries.
- Skip missing/blank summaries.
- Estimate tokens by `ceil(len(text) / 4)` over Unicode code points by default. A configured tokenizer may replace this approximation, but the estimator identity must be emitted with the result.
- Emit `estimated_prompt_tokens`, selected IDs, and skipped-budget IDs.
- The hard default limit is 500 additional tokens.

## 8. Cache Identity and Invalidation

The system uses separate identities instead of one overloaded hash:

- `source_fingerprint`: canonical full scene DSL; used for compile artifacts.
- `layout_fingerprint`: only layout-relevant objects, formulas, visible steps/actions, template, roles, and layout configuration.
- `memory_revision`: resolved active policy/knowledge index revisions.

The layout-analysis cache key is:

```text
hash(
  layout_fingerprint
  + memory_revision
  + compiler_schema_version
  + bbox_environment_version
)
```

Comments, source path, and JSON formatting do not affect `layout_fingerprint`. Formula content, visible actions, template, and role do affect it. Active policy/knowledge content affects `memory_revision`; compiler schema and bbox/LaTeX/Manim environment affect their separate version inputs in the combined cache key.

`memory_revision` is the hash of normalized, scope-resolved index entries plus their source-document content hashes. It must not depend only on index file bytes, formatting, timestamps, or path order.

Cached values may include:

- extracted scene features;
- selected and fallback templates;
- matched policy and memory IDs;
- layout risk;
- measured/estimated bboxes and bbox source.

Cache requirements:

- `--no-cache` bypasses reads and writes for the relevant operation;
- corrupt cache entries are ignored with a diagnostic;
- a cache hit and miss produce equivalent public diagnostics;
- policy or index changes invalidate previous analysis;
- cache schema version is explicit.

## 9. Execution Tasks

### Task P0.1 — YAML/JSON memory parity

Scope:

- introduce shared memory document loading and schema validation;
- support `.json`, `.yaml`, and `.yml` in retrieval, policy matching, inspection, and promotion;
- add safe YAML dependency and format-conflict diagnostics;
- retain JSON as the default generated format.

Tests:

- JSON/YAML equivalents produce identical normalized documents and scores;
- unsafe or invalid YAML fails cleanly;
- duplicate IDs across formats fail;
- promote accepts reviewed YAML and JSON.

Commit target: `Add YAML support for layout memory`.

### Task P0.2 — Policy lifecycle and compile diagnostics

Depends on: P0.1 schema foundation.

Scope:

- add lifecycle/status handling and active-policy filtering;
- centralize policy matching so validate, QA, and compile share results;
- record `layout_memory_policy_applied` in compile `layout_changes`;
- include policy ID, type, source scope, priority, and effect;
- preserve compatible handling for status-less existing policy files.

Tests:

- candidate/disabled policies do not apply;
- active policy appears consistently in validate, QA, and compile;
- cached and uncached compile diagnostics agree;
- deterministic conflict ordering and conflict diagnostics.

Commit target: `Expose active memory policies in compile diagnostics`.

### Task P1.1 — Typed Top-K retrieval

Depends on: P0.1.

Scope:

- rank knowledge and reviewed failures separately;
- add type-specific thresholds and limits;
- incorporate previous QA issue types into failure scoring;
- expose matched features and stable provenance;
- implement the minimal index schema, validation, source hashes, and index-first loading;
- retain a bounded compatibility scan only for a missing legacy index.

Tests:

- per-kind limits and thresholds;
- stable tie-breaking;
- scope precedence and duplicate handling;
- index rebuild primitives and atomic index writes;
- inbox records are never retrieved;
- unrelated memory is excluded.

Commit target: `Make layout memory retrieval typed and explainable`.

### Task P1.2 — Budgeted repair feedback context

Depends on: P1.1.

Scope:

- add a pure `build_repair_memory_context(...)` interface;
- attach machine-readable context to QA output when feedback is requested;
- append a `Known layout risks` section to `agent_prompt.md`;
- enforce summary-only and token-budget guardrails;
- perform no LLM call.

Tests:

- relevant summaries appear in stable order;
- no-match output contains no empty section;
- full failure fields never leak into prompt output;
- default prompt addition stays within 500 estimated tokens;
- selected and skipped IDs are observable.

Commit target: `Add budgeted Top-K memory to repair feedback`.

### Task P2.1 — Canonical layout fingerprint cache

Depends on: P0.2 and P1.1.

Scope:

- implement `source_fingerprint`, `layout_fingerprint`, and `memory_revision`;
- cache layout analysis by the combined versioned key;
- define cache schema, corruption handling, and `--no-cache` behavior;
- avoid recomputing expensive bbox/layout analysis on valid hits.

Tests:

- JSON formatting and path changes preserve layout cache hits;
- formula, visible step, template, role, or policy changes cause misses;
- memory index revision invalidates the cache;
- hit/miss public outputs are equivalent;
- corrupt cache falls back safely.

Commit target: `Cache layout analysis by canonical scene fingerprint`.

### Task P3.1 — Render smoke coverage

Depends on: P2.1 preferred, but can be developed independently after P0.2.

Scope:

- add deterministic render-toolchain detection;
- add safe/static-safe, measured-safe, and measured-contradiction fixtures;
- verify measured bbox takes precedence over heuristic bbox;
- make unavailable LaTeX/dvisvgm an explicit skip reason;
- provide an optional CI render-smoke job with pinned environment guidance.

Acceptance fixtures:

```text
measured-safe:
  heuristic estimate: unsafe or uncertain
  measured formula-caption gap: >= 0.35
  expected final QA: no formula-caption blocking issue
  bbox source: latex_probe

measured-contradiction:
  static estimate: safe
  measured formula-caption gap: < 0.35
  expected final QA: blocking layout_formula_caption_overlap
  bbox source: latex_probe
```

Commit target: `Add measured-layout render smoke coverage`.

### Task P3.2 — Performance and prompt-budget gates

Depends on: P1.2 and P2.1.

Scope:

- benchmark feature extraction, policy matching, retrieval, and cache hit;
- measure cold/warm and hit/miss separately;
- record p50/p95 across a documented corpus size;
- enforce prompt-budget tests;
- add a relaxed CI hard limit to reduce shared-runner flakes.

Targets:

- warm cache hit target: `<5ms`;
- typical policy/retrieval incremental p95 target: `<50ms`;
- repair context hard default: `<=500` estimated tokens;
- record-failure remains local with zero prompt tokens.

Commit target: `Add layout memory performance and budget gates`.

### Task P3.3 — Memory management CLI

Depends on: P0.1 and policy lifecycle from P0.2.

Scope:

- add `memory list`, `inspect`, `review`, `record`, `promote`, `activate`, `disable`, `rebuild-index`, and `clean`;
- retain current `knowledge` commands as compatibility aliases during migration;
- support explicit project/user scopes;
- keep built-in scope read-only;
- require explicit scope and filters for cleanup;
- use dry-run by default for destructive cleanup.

Tests:

- lifecycle state transitions;
- project/user scope precedence;
- public atomic index rebuild command using the P1.1 index primitives;
- clean dry-run and explicit confirmation behavior;
- no command silently deletes or activates memory.

Commit target: `Complete explicit layout memory management commands`.

## 10. Task Order and Delivery Milestones

```text
Milestone A — format and policy correctness
  P0.1 -> P0.2

Milestone B — repair integration
  P1.1 -> P1.2

Milestone C — cache correctness
  P0.2 + P1.1 -> P2.1

Milestone D — release confidence and operations
  P0.2 -> P3.1
  P1.2 + P2.1 -> P3.2
  P0.1 + P0.2 -> P3.3
```

Recommended pull-request/commit order:

1. YAML/JSON memory parity.
2. Policy lifecycle and compile diagnostics.
3. Typed Top-K retrieval.
4. Budgeted repair context.
5. Canonical layout fingerprint cache.
6. Render smoke coverage.
7. Performance/token gates.
8. Memory management CLI.

Tasks should remain independently reviewable. A task is complete only when its tests, command/help text, and relevant documentation are updated together.

A task may be split into smaller sub-PRs when necessary. Each sub-PR must state which acceptance signals it completes, keep unfinished capability rows marked `Partial`, and avoid enabling behavior whose safety contract is incomplete. In particular, P0.2 may land schema/status filtering before conflict execution, but policies requiring the unfinished conflict path must remain candidate or disabled until that path is complete.

## 11. Release Completion Definition

Phase 6 follow-up is complete when:

- JSON and YAML memory documents have equivalent validated behavior;
- only active policies affect behavior, with deterministic precedence and visible diagnostics;
- compile, validate, and QA agree on applied policy identity;
- repair feedback includes only relevant, budgeted summaries and makes no LLM call;
- layout cache invalidates on every defined layout/memory/environment change;
- render smoke either passes in a supported toolchain or reports an explicit dependency skip;
- automated performance and token tests cover their documented targets;
- memory artifacts can be safely listed, inspected, reviewed, promoted, activated, indexed, and cleaned;
- semantic auto-classification and automatic compile/render splitting remain explicitly deferred.

## 12. Migration and Compatibility Notes

- Existing scene JSON remains valid.
- Existing JSON memory files remain readable.
- Existing policies without `status` remain temporarily active for compatibility but should be migrated by `rebuild-index` or an explicit migration command. All promotion commands write `status: candidate` after P0.2.
- Existing `knowledge retrieve`, `knowledge record-failure`, and `knowledge promote-policy` commands remain available until the `memory` command group has a documented deprecation path.
- Indexes are derived data and must always be rebuildable from source memory documents.
- CLI upgrade or uninstall must not remove project or user memory.
