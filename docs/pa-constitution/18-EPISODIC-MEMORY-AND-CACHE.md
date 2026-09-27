# 18. Episodic memory and fingerprint cache

Two mechanisms carried from the earlier benefit-plan work and extended here:

- **Episodic memory:** an append-only timeline of everything that happened, used to resume, explain, audit, and show history.
- **Fingerprint cache:** every artifact and model output stored under a content hash, so the same work is never paid for twice and a rerun is reproducible.

## The three memories

| Memory | Question it answers | Lifetime | Where | File |
|---|---|---|---|---|
| Working memory | What have earlier pages of this document established? | One run | `ingestion_state`, `policies.working_memory` | `06` |
| Plan memory | What do this plan's other live documents say? | Until documents change | `plan_memory` | `06` |
| **Episodic memory** | What happened, in what order, who did it, what came out? | Permanent, append-only | `episodes` | this file |

Working and plan memory are context for model calls. Episodic memory is never sent to an extraction model as evidence; it drives resume, explanations, audit, and the timeline UI.

## 1. Episodic memory

### What is an episode

One unit of work or decision with a start and an outcome: a stage, an extraction group, a judge call, a human review action, an answer fill, a verification, a submission, an insurer event.

```sql
create table episodes (
  id uuid primary key default gen_random_uuid(),
  subject_type text not null check (subject_type in ('policy','block','pa_request','synthetic_scenario','eval_run')),
  subject_id uuid not null,
  run_id uuid,                              -- ingestion run, check run, or eval run
  seq bigint generated always as identity,  -- global order
  stage text not null,                      -- e.g. extract, judge, gate1_edit, fill_answers, submit
  step_no int, group_no int, item_key text,
  actor text not null,                      -- engine, reviewer name, clinician id, insurer
  status text not null check (status in ('started','completed','failed','skipped','resumed','cache_hit')),
  input_fingerprint text,                   -- hash of the exact input
  output_fingerprint text,                  -- hash of the produced artifact
  artifact_ref text,                        -- cache key where the output is stored
  summary text not null,                    -- one human-readable line
  detail jsonb,                             -- counts, reasons, verdicts, errors
  pipeline_version text not null,
  created_at timestamptz default now()
);
create index on episodes (subject_type, subject_id, seq);
create index on episodes (run_id, stage, group_no);
```

Append-only: no update or delete grants. `llm_calls`, `review_log`, and `pa_events` each carry an `episode_id`, so every model call, human action, and status event hangs off one timeline.

### Rules

| # | Rule |
|---|---|
| E1 | Every stage, extraction group, per-item call, human action, and status change writes a `started` episode and then exactly one terminal episode (`completed`, `failed`, `skipped`, or `cache_hit`). |
| E2 | Episodes are written **before** the next unit starts, so the log is always a true prefix of what happened. |
| E3 | **Resume uses episodes.** On rerun, the runner reads the last `completed` episode per stage and group for this run and continues from the next unit, restoring working memory from that episode's artifact. Resume is the normal path, not a separate error path. |
| E4 | A failed unit is recorded with its error and the run continues where rules allow (F1). A later rerun retries only failed units. |
| E5 | Summaries are factual one-liners written by code: "Extracted 4 rules from pages 12 to 14 (group 3 of 5)". |
| E6 | Episodes never contain API keys or real patient data (there is none). Synthetic text appears only as short quotes. |
| E7 | Human episodes record before and after through the linked `review_log` row. |
| E8 | Reprocess shows prior human episodes for each item ("Edited by Suman on Sep 26: 4 weeks to 6 weeks, p.13") to the reviewer. They are shown to the human, never fed to the extractor or judge. |

### Example timeline (policy)

```
#101 engine    upload           completed  "Received clinical policy, 18 pages, sha256 9f2c1a"
#102 engine    cache            completed  "No prior artifacts for 9f2c1a / pipeline v4"
#103 engine    clean            completed  "Removed 31% of tokens; 42 protected lines kept"
#104 engine    precheck         completed  "Role hint clinical_policy matches declared role"
#105 engine    identity         completed  "Example Health Plan, 2026 (page 1 evidence)"
#106 engine    cascade          completed  "Tier A failed (no TOC); Tier B found criteria pages 3 to 6"
#107 engine    extract g1       completed  "3 rules, pages 3 to 4; open item pt_six_weeks"
#108 engine    extract g2       completed  "2 rules, pages 5 to 6; open item closed"
#109 engine    judge            completed  "4 ACCURATE, 1 WRONG_VALUE"
#110 Suman     gate1_edit       completed  "pt_six_weeks: 4 weeks to 6 weeks, p.13"
#111 Suman     go_live          completed  "Policy live; Questionnaire valid"
```

### Example timeline (PA request)

```
#240 engine        match           completed  "Order matched to Advanced imaging (p.34)"
#241 engine        coverage_gate   completed  "PA required per benefit summary p.34"
#242 engine        fill_answers    cache_hit  "12 answers from cache (record set unchanged)"
#243 engine        evaluate        completed  "4 of 5 met; pt_six_weeks missing"
#244 Dr. Patel     upload          completed  "PT progress note added (via huddle)"
#245 engine        recheck         completed  "5 of 5 met"
#246 Dr. Reyes     verify          completed  "5 rules verified"
#247 Dr. Reyes     submit          completed  "Packet v1 submitted"
#248 insurer       approved        completed  "Approved"
```

### Uses

| Use | How |
|---|---|
| Resume | E3 |
| "Why is this here?" | Every item and answer links to the episode that produced it and the input fingerprint |
| Timeline UI | Policy page and PA request page show the episode list |
| Audit export | Markdown audit includes the episode timeline |
| Debugging | Order, inputs, outputs, cache hits, and errors in one place |
| Demo | Shows the system's steps plainly |
| Improvement | A weekly (or end-of-hackathon) query lists recurring human corrections by type; a human decides whether to change prompts and records it in `memory.md` |

## 2. Fingerprint cache

### Rules (from the earlier work)

| # | Rule |
|---|---|
| K1 | **Fingerprint first.** The document sha256 is checked globally before any plan or name lookup. The same PDF under a different file name hits the cache. |
| K2 | **Artifacts keyed by content, not by name.** Every stage output is stored at `artifacts/{sha256}/{pipeline_version}/{stage}/{key}.json`. |
| K3 | **Atomic writes.** Write to a temporary key, validate, then finalize (copy to the final key and record it in `artifact_cache`). Readers only see finalized entries. |
| K4 | **Human locks beat cache.** A cached artifact never restores a value over a human-locked row (H1). |
| K5 | **Versioned keys.** `PIPELINE_VERSION`, each prompt's version, the model id, and the builder version are part of the keys, so changing any of them misses the cache automatically. No manual invalidation needed. |
| K6 | **No silent purge.** Cache entries are removed only by an explicit admin command, logged as an episode. |

### Cache layers

| Layer | Key | Stores | Hit means |
|---|---|---|---|
| Document | sha256 of bytes | Policy row and all finalized artifacts | Upload returns instantly (`cached: true`) |
| Stage artifact | sha256 + pipeline version + stage (+ group) | Pages, cleaned pages, pre-check, sections, identity, extraction per group, grounding, questions, audit | Resume and reprocess skip completed stages |
| Model call | sha256(prompt name, prompt version, model id, params, exact input text) | Raw validated model output | No repeated paid call for identical input (reprocess, eval reruns, demo) |
| FHIR build | sha256(builder version, current item data, review states) | Validated Questionnaire or InsurancePlan | Rebuild only when a human decision or data changed |
| QuestionnaireResponse | sha256(builder version, answers, verification state) | Validated response | Same answers never rebuilt |
| Answer | sha256(link_id, rule version, patient record-set hash) | Filled answer with evidence | Re-check and demo reruns are fast |
| Synthetic generation | sha256(scenario spec, seed, generator version) | Notes, PDFs, bundle | Regenerating the same scenario is free and identical |

```sql
create table artifact_cache (
  key text primary key,
  layer text not null check (layer in ('stage','model_call','fhir','qr','answer','synthetic')),
  fingerprint text not null,                -- document sha256 or subject hash
  pipeline_version text not null,
  storage_path text,                        -- Supabase Storage path for large artifacts
  value jsonb,                              -- small artifacts inline
  finalized boolean not null default false,
  created_by_episode uuid references episodes(id),
  created_at timestamptz default now()
);
```

The existing `answer_cache` table becomes the `answer` layer of `artifact_cache`.

### Demo mode

With `DEMO_MODE=true`, model calls read the model-call cache only. A miss returns a clear error instead of calling a provider, so the demo never waits on a network call it did not rehearse. Pre-warm by running the full demo once before presenting.

### What the cache never does

- Never replaces grounding, judging, or human gates (cached outputs were validated when first produced; human decisions are always current).
- Never serves a result across a changed prompt, model, or pipeline version.
- Never hides a failure: a cached failure is not stored; only finalized, validated outputs are cached.

## Tests

| Test | Must prove |
|---|---|
| test_episodes | Every unit writes started and one terminal episode; order is monotonic; no updates or deletes |
| test_resume | Interrupt mid-extraction; rerun resumes at the next group with restored working memory; no duplicate items; completed groups are `cache_hit` |
| test_fingerprint_cache | Same PDF with a different name hits; changed prompt version misses; atomic write never exposes partial artifacts |
| test_cache_vs_locks | A cached artifact never overwrites a human-locked item or answer |
| test_fhir_cache | Rebuild only when items or review states change |
| test_demo_mode_cache | Miss in demo mode errors clearly; no provider call |

## Metrics

| Metric | Target |
|---|---|
| Resume correctness (interrupted runs completing with identical output to uninterrupted) | 100% |
| Model-call cache hit rate on reprocess with no changes | 100% |
| Model-call cache hit rate during rehearsed demo | 100% |
| Episodes with a terminal status | 100% |
