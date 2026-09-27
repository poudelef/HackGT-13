# 01. Guardrails

Never broken, not even for the demo. If a feature needs to break one, the feature is cut.

## Decision

| # | Rule | Enforced by |
|---|---|---|
| G1 | **No automatic denial.** No code path produces a denial. | No denial value in any enum or constraint. Fake insurer returns only `info_requested` or `approved`. |
| G2 | **AI never diagnoses.** Models locate documentation only. | Prompts; diagnosis answers from coded records or clinician entry. |
| G3 | **AI never invents evidence.** Every AI free-text answer carries an exact quote verified in the original source. | `quote.verify()` against the stored original text. |
| G4 | **LLM extracts, independent LLM judges, human decides.** | OpenAI extracts; Gemini or Grok judges; gates in `11`. |
| G5 | **The judge flags, never approves.** | Only `review.py` sets review states. |
| G6 | **Code decides met or missing.** | Only `pass_eval.py`. |
| G7 | **Questions ask for facts, not verdicts.** | Templates (`08`). |
| G8 | **No dropped conditions.** Every "unless", "or", "except" becomes a question. | Condition coverage 100% to go live. |
| G9 | **Unknown is never yes.** Unknown coverage means PA assumed required. | `pass_eval.py`, `coverage_gate.py`. |
| G10 | **Dates and numbers are code.** "Today" is `DEMO_TODAY` in demo mode. | `dates.py`. |

## Human

| # | Rule | Enforced by |
|---|---|---|
| H1 | **Never overwrite a human edit.** Survives reprocess, re-check, cache rebuild. | `repository.py` lock; test in `16`. |
| H2 | **Only live, human-approved rules touch patients.** | `/pa/check` loads live items only. |
| H3 | **A clinician reviews every answer before submit.** | Verify per rule; `can_submit`. |
| H4 | **Clinicians reject with a reason and enter with a source and attestation.** | DB constraints. |
| H5 | **Every human action is audited.** | Append-only `review_log`. |

## Generality and data

| # | Rule | Enforced by |
|---|---|---|
| R1 | **No insurer or plan hardcoding.** | Identity read from documents; `test_no_hardcoding.py`. |
| R2 | **No service or drug hardcoding.** | Search terms generated from document and order. |
| R3 | **Rules come from real published documents.** Fictional only as a labeled fallback. | `policies.source_kind`; UI banner. |
| R4 | **Patients are synthetic, always labeled.** | `15`; footer on every generated page. |
| R5 | **Fresh code only.** No Ascendion code, prompts, schemas, or client documents. | Review before every push. |
| R6 | **Do not republish insurer PDFs.** Store URLs and hashes in the repo; download with a script. | `14`; `.gitignore` on `data/policies/*.pdf`. |

## Reliability

| # | Rule | Enforced by |
|---|---|---|
| F1 | **Failure degrades one item, never the document.** | try/except per provider call; item to `pending_review`. |
| F2 | **Resume, don't restart.** | Checkpoints in `ingestion_state`. |
| F3 | **Truncation is visible.** | `possibly_truncated`. |
| F4 | **Model calls run in a fixed order.** Extraction is strictly sequential; concurrent stages are re-sorted. Every call is logged with its step number. | `pipeline_runner.py`, `llm_calls`. |
| F5 | **Memory is context, never evidence.** | Grounding on the cited page only. |
| F6 | **Cleaning never removes a rule.** | Protected lines in the context builder. |
| F7 | **Secrets stay server-side.** | Keys in FastAPI env only; Supabase anon key read-only. |
| F8 | **Deterministic where possible.** Temperature 0, pinned model ids, fixed seeds, `DEMO_TODAY`. | `config.py`. |
| F9 | **Episodic log is append-only and complete.** Every unit of work and every human action has a start and one outcome. Resume reads it. | `episodes` (`18`) |
| F10 | **Cache never beats a human, a version change, or validation.** Keys include pipeline, prompt, model, and builder versions; locked rows always win; only validated outputs are cached; writes are atomic. | `artifact_cache` (`18`) |

## Language

"Denied", "rejected" (for coverage), "not eligible", and "diagnosis confirmed" never appear in user-facing text. A rule whose facts fall short is **missing** with a factual reason ("Most recent A1C 6.5% is below the 7.0% threshold").

## Say these to judges

1. It reads real insurance documents from any insurer. Nothing is hardcoded.
2. The AI never makes a medical or coverage decision.
3. A second model flags risk on every rule; a human accepts or edits each one before use.
4. Every answer shows the policy page and the exact chart sentence; a clinician reviews every answer.
5. Human edits are locked; every action is audited.
6. Output is standard FHIR.
7. Documents are real; patients are synthetic.
