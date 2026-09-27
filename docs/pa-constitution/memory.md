# memory.md: decision log (append-only)

Append only; never edit past entries. Every change to extraction, prompts, thresholds, or models gets an entry with real before and after numbers from `scripts/eval.py`. If eval was not run, say "eval not run". No estimates.

```
## YYYY-MM-DD HH:MM, <author>
Change:
Why:
Documents tested (insurer, role, sha256 prefix, tier used):
Before (scorecard):
After (scorecard):
Decision:
```

---

## 2026-09-26, Suman
Change: Constitution v4 written from scratch, replacing v1 to v3.2.
Why: earlier versions centered a demo patient and fictional policies, had a thin human loop, and were patched incrementally. v4 makes real documents the only source of rules, generates synthetic patients from live rules with answer keys, and consolidates: pre-check and 4-tier cascade with three document routes; ordered pipeline runner, working memory, context builder; four human gates plus synthetic content review; locks and audit; FHIR engine following the earlier Questionnaire, InsurancePlan, QuestionnaireResponse design with 100% validation; one comparison method; scope tiers.
Documents tested: none yet.
Before / After: eval not run.
Decision: next entries record document choice, FHIR library pin, and first real ingestion results.

## 2026-09-26, Suman
Change: Added episodic memory (append-only episodes timeline; resume reads it; linked from llm_calls, review_log, pa_events) and fingerprint cache layers (document, stage artifact, model call, FHIR build, QuestionnaireResponse, answer, synthetic) with versioned keys and atomic writes.
Why: carry the earlier work's episodic log and fingerprint-first cache; v4 had only a checkpoint field, an upload hash check, and an answer cache.
Documents tested: none yet.
Before / After: eval not run.
Decision: build episodes and the model-call cache first, since every later stage depends on them.

## 2026-09-26 19:37, Auto
Change: Fixed PA marker undercount. Next-line dagger windows on EOC rows; sequential PA-listing parser for pdfplumber wraps (split entry numbers, Conditiona/l, Not/required, FHIR True/False); listing reconcile with grounding + fuzzy label match; reject fragment hijacks.
Why: Live UHC EOC showed 2/41 pa_required because extract missed markers on the following line, and the listing PDF parse produced truncated junk instead of 90 categories.
Documents tested: UHC Dual Complete OH-S3 EOC policy 84687cb4 (benefit_summary); listing UHC_OH-S3_2026_prior_authorization_fhir_1.pdf (and plain twin). sha256 from policy record. Tier: listing reconcile + EOC annotate.
Before (scorecard): total 41 coverage rows; pa_status required=2, not_required=39, conditional=0. eval not run.
After (scorecard): total 90; required=41, not_required=41, conditional=8 (reference 41/41/8 of 90). eval not run; unit tests test_pa_markers 9 passed.
Decision: Keep sequential listing parse + EOC dagger annotate. Reconcile via POST /policies/{id}/reconcile-pa with listing text. No payer hardcoding.

## 2026-09-26 19:51, Auto
Change: Payer-agnostic next-line dagger harden (negation "no prior authorization"; stop look-ahead at next service row); coverage_from_line windows; order-scoped PA criteria (one service / synthetic medical-necessity when only EOC says required); coverage label match before LLM; edge tests in test_pa_order_edge_cases.py.
Why: Same undercount would hit any EOC that puts markers on the following line; patient/insurer must not see all 41 chart rows for one order.
Documents tested: synthetic Acme/Generic Mutual pages in unit tests; UHC fixture counts unchanged (41/41/8). eval not run.
Before (scorecard): risk of 2/N PA flags on next-line-marker EOCs; patient check could attach empty or overly broad criteria. eval not run.
After (scorecard): test_pa_order_edge_cases 9 passed; test_pa_markers 9 passed; broader suite green. eval not run.
Decision: Keep listing reconcile optional; EOC annotate+windows is the default path for any payer. Patient packet is order-scoped only.

## 2026-09-26 20:45, Auto
Change: Teammate JSON boundary adapters (ingestExtractedDocument / buildOutputForTeammate); POST /ingest/patient-extraction; GET /pa-requests/{id}/export; PA rules view over live coverage (no duplicate PARule SoT); draft status + confirm; FHIR Questionnaire/QR snapshot tables; doctor/insurer PA-determination + questionnaire UX. G1 held: no deny; decision API rejects deny with 409.
Why: Align teammate branch contract and make PA-required + questionnaires visible without rebuilding the check engine.
Documents tested: none (contract unit tests only). eval not run.
Before (scorecard): no teammate ingest/export edge; insurer UI lacked PA-required banner. eval not run.
After (scorecard): test_boundary_contract 3 passed; edge suite with markers/order still green. eval not run.
Decision: Wrap existing engine. Export on demand (no webhook yet). Lock teammate real schema before merge; swap only boundary/*.py.
