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

## 2026-09-26, Suman
Change: First implementation of the v4 engine and review UI. Extraction, judging, and quotes use the provider path when keys are set, and a deterministic reader when they are not. The sample library is a labeled fictional fallback.
Why: the app has to run for review before a published PDF set is pinned.
Documents tested: fictional fallback only (clinical policy, benefit summary, drug criteria). Eval script not run against a published PDF.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: replace the fallback documents with published PDFs and record tier, items, and verdicts here.

## 2026-09-26, Suman
Change: OpenAI extraction key is configured. Downloaded the UnitedHealthcare Community Plan of Ohio 2026 Adult Spine Imaging Guidelines (sha256 70d93a6d, 164 pages) and did not ingest it.
Why: the sample library stays the labeled fictional fallback. This PDF is the first published clinical-policy candidate, and it is too long to be the short-policy pass. The judge provider is still unconfigured, so an extract would have no independent judge.
Documents tested: none ingested. Eval not run.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: demo on the fictional library. Ingest a published policy only after a short text PDF is chosen and a judge key is set.

## 2026-09-26, Suman
Change: `.env` pins `OPENAI_MODEL` to `gpt-4.1-mini-2025-04-14`. The code default stays `gpt-4.1-mini`.
Why: this key's project returns 403 model_not_found for the alias `gpt-4.1-mini` and lists only the dated snapshot.
Documents tested: none. The alias failure dropped free-text quotes, so a fresh MRI check was 2 of 5 instead of 4 of 5.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: use the dated snapshot for this key. Do not change the committed default until eval compares the two ids.

## 2026-09-26, Suman
Change: Benefit-summary memory notes may be bare strings; a note is kept only when that string is on the cited page. Extraction groups default to 10 target pages (`CONTEXT_GROUP_PAGES`), split only when a group would pass `CONTEXT_MAX_TOKENS`. The p0 prompt asks for marker objects. A failed upload of the same file is read again instead of returning the failed row.
Why: uploading Summary of Benefits.pdf (sha256 0eae6006097b, 20 pages) returned 500 because `memory_updates.markers` was a string and `apply_updates` called `.get` on it. Page groups of 3 made long documents into too many model calls.
Documents tested: Summary of Benefits.pdf, benefit_summary, sha256 0eae6006097b. Re-read after the fix is recorded below if it completes.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: batch 10 pages per extraction call. Do not raise the 40-page section cap.

## 2026-09-26, Suman
Change: A benefit-summary batch that returns far fewer coverage rows than the service lines on those pages is split in half and read again. The p0 prompt now requires one coverage object per service row, including rows that do not need authorization.
Why: Summary of Benefits.pdf (sha256 0eae6006097b, 13 located pages) came back as 2 ambulance rows. Each 10-page call returned a single service.
Documents tested: that benefit summary, re-read after this change.
Before (scorecard): eval not run. Saved items: 2.
After (scorecard): eval not run. Item count recorded after the re-read.
Decision: keep 10-page batches, and split a batch only when it is thin.

## 2026-09-26, Suman
Change: Benefit summaries are read 2 pages at a time. A coverage row is saved only when its quote is on the cited page, and a repeated service name is kept once.
Why: the 10-page batches returned one example. A follow-up read copied the same few services onto neighboring pages.
Documents tested: Summary of Benefits.pdf, sha256 0eae6006097b, tier C, 13 pages.
Before (scorecard): eval not run. 2 saved rows.
After (scorecard): eval not run. 32 saved rows with a quote on the cited page.
Decision: smaller batches for benefit charts. Clinical policies stay at 10 pages per call.

## 2026-09-26, Suman
Change: After a benefit extract, chart lines that name a copay, coinsurance, allowance, or covered/not-covered result and were not saved are read again. A line the model still skips is saved from that line, with the quote copied exactly. Clinical batches that return too few requirements are split. Question text is written by the P5 prompt from the requirement and the slot. A question that pastes the policy sentence, or says "this requirement" or "the following", is discarded and a fact question is kept. P6 receives the questions.
Why: Summary of Benefits.pdf came back with two ambulance rows, then 32 rows that still skipped emergency care, specialist visits, and other chart lines. Questionnaire text was the policy sentence or "this requirement".
Documents tested: Summary of Benefits.pdf, benefit_summary, sha256 0eae6006097b, tier C. Fictional lumbar policy and fictional drug criteria, question text only.
Before (scorecard): eval not run. Benefit rows saved: 32. Question text repeated the rule.
After (scorecard): eval not run. Benefit rows saved: 60. Sample questions: "How many weeks of physical therapy were completed?", "Is a neurological symptom documented in the clinical note?", "Has physical therapy been received?".
Decision: keep the second pass for benefit charts. Do not treat a pasted sentence as a questionnaire question.

## 2026-09-26, Suman
Change: Benefit charts are read as columns (service, in-network, out-of-network, or a covered/covered grid) and each service becomes one labeled row. Pages whose chart rows were not saved are read again from those rows. Flagged rows are sent back together, at most 4 at a time, with the chart row when one exists. Judging of a batch runs together and is saved in page order. The extract model stays the pinned gpt-4.1-mini snapshot because this key cannot call a larger model. The judge stays Grok.
Why: smashed text was still splitting one service across lines. The earlier project rechecked only flagged rows and judged them together.
Documents tested: Summary of Benefits.pdf, benefit_summary, sha256 0eae6006097b, tier C.
Before (scorecard): eval not run. Chart recall 72 of 85 (0.847). Judge accurate 48 of 60 (0.800).
After (scorecard): eval not run. Chart recall 84 of 85 (0.988). Judge accurate 55 of 72 (0.764). Saved rows 72. Recheck updated 10 flagged rows.
Decision: keep the chart grid and the flagged-row recheck. A higher accurate rate needs a stronger extract model than this key can call.

## 2026-09-26, Suman
Change: Human-facing labels for document_role benefit_summary now say Evidence of Coverage / plan. The p0 prompt states that the document describes a health plan and extracts plan benefits, not clinical questionnaires. The database role key stays benefit_summary.
Why: the uploaded plan PDF is an Evidence of Coverage / plan chart, not a thin "benefit summary" label.
Documents tested: none re-extracted. Label and prompt wording only.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: keep one route for EOC and Summary of Benefits plan charts. Clinical rules stay on clinical_policy.

## 2026-09-26, Suman
Change: Re-upload of the same PDF bytes returns the stored policy immediately (fingerprint-first). A cache_hit episode is written. A renamed copy updates the display file name only. The upload UI and review page show when a load came from cache.
Why: match the earlier project's global sha256 cache so the same plan document is never extracted twice.
Documents tested: unit test with synthetic PDF bytes only.
Before (scorecard): eval not run.
After (scorecard): eval not run. test_same_pdf_bytes_hit_the_fingerprint_cache_even_under_a_new_name passed.
Decision: cache by document content hash, not by insurer name. A different PDF for the same insurer is still a new read.

## 2026-09-26, Suman
Change: Policy upload returns immediately and finishes in a background thread. The review page polls every 1.5s and shows a live episode timeline (stage labels, pulse on the active step, stall warning after 90s, Show JSON on episode detail). Same-fingerprint cache hits still return instantly. Extract JSON button exports rows in a document_type/tables envelope. Report extract returns the same envelope shape for chart facts.
Why: the pale static episode list hid progress; a long sync upload could also time out in the browser. Sambhav's patient PDF→JSON flow already shows structured output as work completes.
Documents tested: unit tests only (async return + fingerprint cache).
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: keep policy extraction on the background runner; keep PA_FORM patient extraction with Sambhav.

## 2026-09-26, Suman
Change: Added overview-style async Job Progress checklist (IngestionSteps) and Extracted pages panel. GET /policies/{id}/pages returns page previews from the fingerprint cache as soon as pdfplumber finishes, while extract/judge still run. The review page polls pages every 1.2s on first upload.
Why: match the earlier project's async job UI so the user sees real page text first, not a pale Loading line.
Documents tested: unit test for pages_preview with cached page bytes.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: show pages from the pages/clean stage artifact before rules are ready; do not wait for draft status.

## 2026-09-26, Suman
Change: Replaced the pale episode/page dump with the overview Processing Document checklist (teal checks, active "in progress...", pending gray). Removed full PDF page previews from the review screen. Library table gained Delete (DB + storage PDF + fingerprint cache) and a live extracting indicator that polls while any row is ingesting.
Why: user asked for the earlier product's processing UI, no page dump, and a way to remove documents and see extraction running.
Documents tested: unit tests for pages_preview count and delete_policy.
Before (scorecard): eval not run.
After (scorecard): eval not run.
Decision: processing checklist only while ingesting; library delete is hard-delete from DB and storage.

## 2026-09-26, Suman
Change: Overview extract is the only EOC path (no HARDCODED HALLUCINATED seed). Pages → cascade order → context builder → sequential extract + working memory → ground → judge. Timed-out groups are skipped; failed/orphan runs resume from stage cache; items checkpoint after each group; `_apply_grid` no longer re-reads the full PDF; POST /finalize builds draft FHIR after a late crash. Insurer asks once then approves; doctor evidence rechecks insurer_request. Edge tests: 18 passed.
Why: seeded Claude quotes forced all 90 rows to HALLUCINATED; live UHC died on one timeout / PDF re-read.
Documents tested: live EOC_UnitedHealth 84687cb4 (253 pages, tier A, 42 groups); unit edge tests.
Before (scorecard): eval not run. Seeded 90 HALLUCINATED.
After (scorecard): eval not run. Live draft: 41 coverage rows (35 ACCURATE, 5 HALLUCINATED, 1 VAGUE from judge); InsurancePlan FHIR valid; 182 services in working memory for gap fill. 18 tests passed.
Decision: judge only from judge stage; sequential groups + working/episodic memory; G1 never deny; no payer hardcoding.


## 2026-09-26 20:45, Auto
Change: Teammate JSON boundary adapters; wrap existing PA engine; G1 held (no deny); doctor/insurer PA-determination + questionnaire UX.
Why: Spec alignment without duplicate check engine.
Documents tested: none. eval not run.
Before / After: test_boundary_contract 3 passed. eval not run.
Decision: Export on demand; swap only boundary/*.py when teammate schema lands.
