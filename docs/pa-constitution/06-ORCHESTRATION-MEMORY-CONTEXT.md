# 06. Orchestration, working memory, context builder

## 1. Pipeline runner (the agent loop)

A controlled loop, not an autonomous agent. Code chooses every next step; no model output can choose, skip, or reorder steps.

| # | Rule |
|---|---|
| O1 | Stages are a fixed ordered list (`05`); each declares inputs and outputs. |
| O2 | A stage starts only after the previous stage's output validated. |
| O3 | Extraction is strictly sequential over page groups in document order (group n+1 needs group n's memory). Exception: drug blocks are independent and may run concurrently. |
| O4 | Independent per-item stages (judge, phrasing, question judge, drug blocks) run with bounded concurrency, then results are re-sorted into document order (`seq`) before the next stage. |
| O5 | Every model call is logged in `llm_calls` with run id, stage, step number, group, item. The log reproduces the exact order. |
| O6 | Every stage and extraction group writes episodes and a finalized artifact, including the working memory snapshot. Rerun resumes from the last completed episode (`18`); completed units become `cache_hit`. |
| O7 | One repair retry for invalid JSON, one retry on timeout; then the unit fails, is recorded, and the run continues (F1). |
| O8 | Run limits (`RUN_MAX_MODEL_CALLS`, `RUN_MAX_SECONDS`); hitting one stops the run as `partial`. |
| O9 | One running ingestion per plan (unique index on `ingestion_runs.plan_key`). |
| O10 | Temperature 0, pinned model ids. |

Document order within a plan: benefit summary first, then clinical policies and drug criteria, so later documents can use plan memory. A clinical policy uploaded first still ingests; its links recompute when the benefit summary goes live.

Order-time order: match, coverage gate, then rules in `seq` order and questions in link order; quote calls for one question may run across notes concurrently and are re-sorted by note date (first verified quote wins).

## 2. Working memory

Structured JSON maintained by code, never free-form model notes.

| Level | Scope | Stored in | Built from |
|---|---|---|---|
| Document memory | One document across its groups | `ingestion_state` during run; `policies.working_memory` at end | Validated, grounded output of earlier groups |
| Plan memory | All documents of one plan (previous files) | `plan_memory` | Live, human-approved items only |

Document memory:
```json
{
  "section_path": ["Chapter 4", "Outpatient diagnostic services"],
  "items_found": [ { "key": "advanced_imaging", "label": "Advanced imaging (MRI, CT, PET)", "page": 34 } ],
  "definitions": [ { "term": "conservative therapy", "text": "...", "page": 3 } ],
  "markers": [ { "marker": "*", "meaning": "Prior authorization required", "page": 30 } ],
  "open_item": { "key": "pt_six_weeks", "started_page": 12, "partial_text": "At least 6 weeks of physical therapy within" },
  "exceptions_seen": [ { "term": "red flag symptoms", "page": 14 } ],
  "logic_group": { "type": "all_of", "started_page": 12 }
}
```

Plan memory:
```json
{
  "insurer": "Example Health Plan", "plan_name": "Example PPO", "plan_year": "2026",
  "pa_services": [ { "label": "Advanced imaging (MRI, CT, PET)", "page": 34, "reference": "Clinical Policy CP-IMG-012", "policy_id": "uuid" } ],
  "no_pa_services": [ { "label": "Diagnostic X-ray", "page": 34 } ],
  "definitions": [ { "term": "medically necessary", "text": "...", "policy_id": "uuid", "page": 88 } ],
  "linked_policies": [ { "reference": "CP-IMG-012", "policy_id": "uuid" } ]
}
```

| # | Rule |
|---|---|
| M1 | Only validated, grounded output updates memory. |
| M2 | Extractor returns `memory_updates` with exact evidence strings; code verifies them on target pages. |
| M3 | Code merges: dedup by key or term, keep earliest page, replace `open_item` each group. |
| M4 | Memory is never evidence. An item supported only by memory goes to `pending_review` (`grounded_only_in_memory`). |
| M5 | Budget `WORKING_MEMORY_MAX_TOKENS`; trim deterministically: item details to keys, then oldest unreferenced definitions. |
| M6 | Plan memory updates on go-live, edit, and reject. |
| M7 | Memory is checkpointed with each group. |

## 3. Context builder

Runs in code before every extraction call and every report fact extraction.

| # | Step | How | Safety |
|---|---|---|---|
| C1 | Normalize | NFKC, ligatures, straight quotes, collapse spaces, rejoin hyphenated line breaks | |
| C2 | Headers and footers | Lines on 50%+ of pages after removing digits and collapsing whitespace, up to 100 characters | Protected lines kept |
| C3 | Page labels, running titles | Remove after recording printed page number | |
| C4 | Non-content pages | Cover, blank, index, TOC (TOC kept separately as hints) | Located pages never removed |
| C5 | Generic boilerplate | Multi-language taglines, nondiscrimination notices, repeated disclaimers; detected by repetition plus a generic list (no insurer patterns) | Protected lines kept |
| C6 | Tables | Linearize rows as `Column: value | Column: value`; keep markers | |
| C7 | Out-of-section pages | Only located pages enter the call | Section recall measured |
| C8 | Duplicate paragraphs | Keep once per group | |
| C9 | Protected lines | Never removed: authorization terms; criteria words (must, required, at least, within, unless, except, one of, all of); numbers with units; codes | Guards against losing a rule |
| C10 | Role settings | Benefit: linearize tables. Clinical: keep list numbering and indentation. Drug: one block, field labels kept. Reports: C1 to C3, C5, C6 only | |

Assembled input:
```
[WORKING MEMORY] {...}
[PLAN MEMORY] {...}
[SECTION] Chapter 4 > Outpatient diagnostic services
[CONTEXT ONLY: tail of page 33, do not extract] ...
[PAGE 34] ...
[PAGE 35] ...
[CONTEXT ONLY: head of page 36, do not extract] ...
```

| Rule | Detail |
|---|---|
| Groups | `CONTEXT_GROUP_PAGES` target pages; a heading never separated from its first page |
| Neighbors | `CONTEXT_NEIGHBOR_LINES` from each side, labeled context-only, not citable |
| Budget | Over `CONTEXT_MAX_TOKENS`: trim neighbors, then memory detail; target pages never trimmed (split the group instead) |
| Reports | Quote verification always uses the stored original `body`, never cleaned text |
| Recorded | Tokens before and after, lines removed per step, protected lines kept, pages dropped and why, groups built |
