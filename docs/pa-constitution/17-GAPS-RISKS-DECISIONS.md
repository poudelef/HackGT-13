# 17. Gaps, risks, and decisions

What earlier plans were missing, what could go wrong, and what we decided.

## Gaps closed in v4

| # | Gap | Fix |
|---|---|---|
| 1 | Rules were built around a demo patient | Rules come only from real documents; patients are generated from live rules (`14`, `15`) |
| 2 | No way to know the synthetic demo is correct | Scenario spec is an answer key; round-trip check runs the real engine against it |
| 3 | Real EOCs are long and noisy | Pre-check, 4-tier cascade, context builder with protected lines (`05`, `06`) |
| 4 | Three document genres treated alike | Separate routes for benefit summary, clinical policy, drug criteria |
| 5 | Drug criteria documents can hold hundreds of drugs | Index all blocks free; extract and review per block on demand |
| 6 | Human-in-the-loop was one approve button | Gates 0 to 4 plus S, per-item review, locks, audit (`11`) |
| 7 | Clinician could only verify | Reject with reason, enter with source and attestation |
| 8 | Order input was free text only | Catalog from live documents; phrase-verified matching; ambiguity goes to clinician |
| 9 | "Today" changed between runs, breaking date math | `DEMO_TODAY` |
| 10 | Live demo latency from quote calls | `answer_cache` keyed by record-set hash; pre-warm before demo |
| 11 | Patient chart shape was custom | FHIR-native `clinical_records` with flattened fields (`03`) |
| 12 | FHIR library and pydantic version conflict risk | 10-minute spike; pin the release matching pydantic v2; record in memory.md (`09`) |
| 13 | Republishing insurer PDFs in a public repo | Commit URLs and hashes only; download script (R6) |
| 14 | Accuracy claims without data | Gold sets from real documents, eval scorecard, only measured numbers |
| 15 | Model call order could vary | Pipeline runner, call log, re-sorting (`06`) |
| 16 | Too much scope for the time left | Scope tiers and cut order (`16`) |
| 17 | Episodic log reduced to a checkpoint field | `episodes` timeline: resume, audit, UI, explanations (`18`) |
| 18 | Only upload-level and answer caching; no artifact, model-call, or FHIR cache | Fingerprint cache layers with versioned keys and atomic writes (`18`) |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Aligned real documents (same insurer and plan) are hard to find | Medium | Coverage gate and criteria don't connect | 45-minute time box; accept different insurers and say so; fictional fallback labeled |
| Real EOC ingestion takes minutes | High | Slow live demo | Pre-ingest benefit summary; live-upload only the short clinical policy |
| Judge flags many items as VAGUE | Medium | Long review queue | Fine for the demo: shows the human gate; edit a few, accept the rest |
| Quote finder misses paraphrased evidence | Medium | Rule shows missing | That is the safe direction; clinician can enter with attestation |
| API credit limits | Low to medium | Stalled runs | Run limits, caching by hash, gpt-4.1-mini class for extraction |
| Scanned PDFs | Medium | Cannot ingest | Pick text-based documents; `NO_TEXT_LAYER` error |
| Teammate contract drift | Medium | Integration breaks late | Mocks first; `04` contract; any change announced |
| FHIR library friction | Medium | Lost hours | Spike first; fall back to building JSON by hand plus structural checks in `fhir/validate.py`, then add library validation later |
| Synthetic background data satisfying a criterion by accident | Low | Wrong demo result | Round-trip check |
| Demo network failure | Medium | Demo breaks | Local run, deployed backup, recorded backup video, `DEMO_MODE` cache |

## Decisions

| Decision | Reason |
|---|---|
| Supabase instead of stateless files | Shared team state and Realtime; the earlier stateless rule does not apply here |
| Emit FHIR R4B, call it R4-family | Proven path; structurally equal for the resources used; recorded as open question |
| OpenAI extracts, Gemini judges (Grok optional) | Different providers for independence |
| Clinical policy is the MVP route, benefit summary is Core | Short documents make the first end-to-end fast; the long EOC comes second |
| Patients generated from live rules | Makes every demo and eval result checkable |
| Drug blocks extracted on demand | Cost and time on large documents |
| One comparison method (Jaccard 0.4) | Same discipline as the earlier regression gate |
| No OCR this weekend | Time; choose text-based PDFs |

## Open questions (record answers in memory.md)

1. Which insurer and plan gives the best aligned set? (decide in the first 45 minutes)
2. Which `fhir.resources` version pins cleanly with pydantic v2?
3. Does Impiricus consider PA part of their existing product? (ask at their tech talk)
4. Does Meta count WhatsApp Cloud API as their Graph API requirement? (Harry, at their workshop)
