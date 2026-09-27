# 16. Quality and delivery

## Engineering rules

1. Branch `suman/*`; merge to `main` only when tests pass and the e2e runs. `main` always demos.
2. Layer rules in `02` enforced in review.
3. TypeScript types mirror `04` exactly; mocks pushed before endpoints.
4. No secrets in code, logs, or client bundle.
5. After every dev server restart, confirm `/health` shows the current commit.
6. Test against something real before calling it done; fakes alone hide bugs.

## Tests (pytest; autouse fixture points providers at an invalid host)

| Test | Must prove |
|---|---|
| test_upload_validation | Magic bytes, size, text layer |
| test_pages | Page offset trusted only on 2+ pages; headers and footers stripped by digit-free comparison |
| test_context_builder | Noise removed; protected lines kept; tables linearized with markers; context-only pages not citable; targets never trimmed |
| test_precheck | TOC with and without dot leaders; role signatures per genre |
| test_cascade | Fall-through order; years not chapters; Tier A uncapped; B to D capped with flag; failures recorded |
| test_role_routing | Mismatch pauses; per-role settings and prompts |
| test_plan_identity | From content only; unverified evidence becomes null |
| test_runner_order, test_runner_limits, test_plan_lock | Sequential extraction; re-sorting; call log; resume; limits; one run per plan |
| test_working_memory, test_plan_memory, test_cross_page_rule | Grounded updates; budget; memory never evidence; live-only plan memory; split rules captured once |
| test_grounding | Changed number, missing code, wrong page, missing exception word each fail |
| test_review_routing | Every verdict routes correctly; provider failure degrades one item |
| test_locks | Locked item survives forced reprocess with different values; unlocked sibling updates; locked answers survive re-check |
| test_question_builder, test_pass_eval | Templates; coverage; logic; tri-state tables; operators; enableWhen |
| test_drug_blocks | Indexed without model calls; extract on demand; unreviewed never used |
| test_service_matcher, test_coverage_gate | Catalog, code, phrase-verified candidates; ambiguity to clinician; gate outcomes |
| test_quote | Exact passes; paraphrase fails; value digits inside quote; verify uses original body |
| test_answer_review | Reject needs reason; enter needs source and attestation; both lock and re-evaluate |
| test_fhir | Questionnaire, InsurancePlan, QuestionnaireResponse validate; linkIds consistent; enableWhen valid |
| test_packet | Only verified rules; immutable; versions |
| test_no_hardcoding | App code contains no insurer names or fixed service lists |
| test_default_provider_wiring | Real provider config path with only the network mocked |
| test_episodes, test_resume, test_fingerprint_cache, test_cache_vs_locks, test_fhir_cache, test_demo_mode_cache | Episodes complete and ordered; resume mid-extraction; content-keyed and versioned cache; locks beat cache; FHIR rebuild only on change; demo mode never calls providers (`18`) |
| test_guardrails | No denial values or words; insurer never denies |
| test_synth_roundtrip | Generated scenario statuses equal the answer key |

## Real-document runs (required)

`scripts/ingest_real_docs.py` ingests every document in `SOURCES.md` (plus the second insurer). Record per document in `memory.md`: tier used, pages located, tokens before and after cleaning, items, auto_approved vs pending_review, verdicts, time, cost estimate.

## End-to-end (`scripts/e2e.py`, real policies, synthetic patient)

1. Reset demo.
2. Not-required order: `not_required` with page.
3. Imaging order: statuses equal the scenario answer key; missing rule has the likely owner.
4. Upload the withheld document; re-check: all met.
5. Reject an AI answer: readiness drops; enter with attestation: restored.
6. Verify all; preview; submit; watch submitted, in review, approved.
7. Drug order: statuses equal the drug scenario answer key.
8. Export and validate Questionnaire, InsurancePlan, QuestionnaireResponse.

## Scope tiers

Build strictly in this order. Guardrails apply at every tier.

| Tier | Contents | Done when |
|---|---|---|
| MVP | Supabase tables and mocks; episodes and model-call cache from the first line of code; upload and ingest one real **clinical policy** (short, clinical route); grounding and judge; Gate 1 accept, edit, reject; questions and Gate 2; one synthetic patient with one withheld document; `/pa/check` with verified quotes; checklist; verify; submit; fake insurer; FHIR Questionnaire and QuestionnaireResponse | e2e steps 1, 3, 4, 6 pass with a real policy |
| Core | Real benefit summary through the cascade and coverage gate; InsurancePlan; clinician reject and enter; audit export; one drug block; eval scorecard numbers; second-insurer ingestion | e2e all steps pass; scorecard captured |
| Stretch | Bundle and PAS-shaped Claim; `info_requested` loop; CDS Hooks card; plan memory linking across documents; more drug blocks | Only after Core is frozen |

## Timeline (relative to now)

| Hours from now | Must be true |
|---|---|
| +2 | Documents chosen and downloaded; SOURCES.md; tables created; mocks pushed |
| +4 | FHIR library spike done; one clinical policy ingests to draft with items and verdicts |
| +7 | Gates 1 and 2 working; policy live; questions and Questionnaire valid |
| +9 | Scenario spec written from live rules; synthetic patient seeded; round-trip passes |
| +12 | MVP e2e passes (checklist, withheld upload to 100%, verify, submit) |
| +16 | Core: benefit summary and coverage gate; clinician reject and enter; audit |
| +19 | Core: drug block; eval scorecard; second insurer run; memory.md updated |
| +21 | Code freeze; demo rehearsals; backup recording |

## Cut order

1. Stretch items.
2. Second drug block and plan memory linking.
3. InsurancePlan (keep coverage gate).
4. Question judge (keep code checks).
5. Never cut: real policy, grounding, judge, Gate 1, pass conditions, verified quotes, Gate 3 verify, submit, FHIR Questionnaire and QuestionnaireResponse, synthetic labels.

## Demo script (this part)

1. Admin: upload a real clinical policy live; watch steps (tier used, tokens cleaned); queue shows a WRONG_VALUE item; edit it; lock appears; go live; open the FHIR Questionnaire and the audit.
2. Doctor: order MRI for synthetic Maria; banner shows PA required with the benefit summary page; checklist at 80% with quotes and pages; missing PT rule with likely owner.
3. Upload the withheld PT note (or Harry's huddle does); readiness 100%.
4. Reject one AI answer to show control; re-enter with attestation.
5. Verify, preview packet, submit; status timeline; show QuestionnaireResponse.
6. One line: "Real documents, synthetic patient, a human decided every step."

## Definition of done

- [ ] Real documents ingested through their own routes; tier used recorded.
- [ ] Second insurer ingested; nothing hardcoded (test passes).
- [ ] Every item decided at Gate 1; policy live only after Gate 2.
- [ ] Human edits and clinician answers survive reprocess and re-check.
- [ ] Call log shows ordered extraction; resume works.
- [ ] Every unit and human action appears in the episode timeline; interrupted run resumes to identical output.
- [ ] Reprocess with no changes makes zero model calls (all cache hits); rehearsed demo makes zero provider calls in demo mode.
- [ ] Context cleaning lost zero gold rules.
- [ ] Synthetic round-trip matches the answer key; every page labeled synthetic.
- [ ] Fabricated quotes and changed numbers rejected.
- [ ] Submit impossible before every rule verified.
- [ ] All FHIR outputs validate with zero errors.
- [ ] Eval shows false met = 0; scorecard in `memory.md`.
- [ ] No user-facing denial language; works at 375px; deployed engine reachable.
