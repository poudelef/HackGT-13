# 13. Validation and accuracy

## Validation layers (every item, every run)

| # | Layer | Applies to | Type | On failure |
|---|---|---|---|---|
| 1 | Schema | all extraction | code | repair retry, then listed as failed |
| 2 | Grounding (`05`) | coverage, rules, identity, memory updates | code | pending_review with reason |
| 3 | Judge (P2) | coverage, rules | second model | routes per `11` |
| 4 | Question checks (`08`) | questions | code | pending_review |
| 5 | Question judge (P6) | questions | second model | pending_review unless complete |
| 6 | FHIR validation (`09`) | Questionnaire, InsurancePlan, QuestionnaireResponse, Bundle | code | blocks go-live or packet |
| 7 | Human Gates 1 and 2 (`11`) | every item, every question set | human | stays draft |
| 8 | Quote verification | every AI free-text answer | code | no answer |
| 9 | Human Gate 3 | every answer | human | cannot submit |
| 10 | Regression eval | engine changes | code | merge blocked |

## Targets (carried from the earlier work, plus new ones)

| Area | Metric | Target |
|---|---|---|
| Decision fields | pa_required correct per service | 98%+ |
| Descriptive fields | Rules: requirement text, type, page, values correct | 95%+ |
| FHIR | Validation errors | 0 (100% valid) |
| Traceability | Items and answers with document and page | 100% |
| Identity | Insurer, plan, year correct | 100% |
| Cascade | Gold relevant pages located, per role | 100% |
| Drug index | Gold drugs indexed | 100% |
| Rules | Recall of gold rules | 100% |
| Conditions | Gold conditions extracted | 100% |
| Questions | Condition coverage | 100% (go-live gate) |
| Grounding | Number, code, page mutations caught | 100% |
| Judges | Wording and scope mutations flagged | 90%+ |
| Review | Auto-approved items accepted unchanged | 95%+ |
| Judge risk recall | Human-edited or rejected items the judge had flagged | 90%+ |
| Context | Gold rules lost by cleaning | 0 |
| Memory | Cross-page rules captured; duplicates after dedup | 100%; 0 |
| Answers | Correct answers across synthetic variants | 95%+ |
| Rule status | Correct met or missing | 95%+ |
| **False met** | Rules met that should not be | **0, blocks merge** |
| Quotes | Injected fake quotes rejected | 100% |
| Stability | Identical output over 3 runs | 100% |
| Resume | Interrupted runs produce output identical to uninterrupted | 100% |
| Cache | Model-call hit rate on unchanged reprocess and rehearsed demo | 100% |
| Episodes | Units with a terminal status | 100% |

## Comparison method (one only)

As in the earlier work, extracted-vs-gold text is compared with a single fuzzy method: token-overlap Jaccard, match at 0.4 or higher, plus exact equality of type, page, and condition values. No second comparison method is added.

## Gold sets (built from the real documents)

```
eval/
  gold_coverage/{sha256}.json    true services and pa_required, by hand from each real benefit summary
  gold_rules/{sha256}.json       true rules and conditions, by hand from each real clinical policy or drug block
  gold_sections/{sha256}.json    true relevant page ranges
  gold_questions/{sha256}.json   expected question set per rule
  gold_patients/*.json           synthetic scenario variants with expected rule statuses (generated, 15)
  mutations.json                 changed number, dropped exception, swapped code, wrong page, invented condition, leading question
```

Hand-labeling time box: 60 minutes for one benefit summary section, one clinical policy, one drug block. Record who labeled and when.

## Patient variants (generated from the scenario spec, `15`)

For each live rule: satisfied, missing, below threshold, outside time window, exception documented, paraphrased-only evidence (must stay missing), and conflicting records (must be unclear). Plus one order the benefit summary marks as not requiring PA.

## Scorecard (`scripts/eval.py`)

```
IDENTITY     3/3
SECTIONS     benefit 12/12 pages  clinical 4/4  drug 1/1 blocks
COVERAGE     decision 24/24 (100%)
RULES        recall 9/9  descriptive 9/9  conditions 22/22
QUESTIONS    coverage 22/22  fidelity 9/9
FHIR         Questionnaire 2/2 valid  InsurancePlan 1/1  QR 3/3
GROUNDING    mutations 8/8
JUDGES       mutations 6/7
CONTEXT      gold rules lost 0
ANSWERS      61/63   RULE STATUS 74/76   FALSE MET 0
QUOTES       fakes rejected 10/10
STABILITY    3/3
```

Only measured numbers go on the pitch slide and into `memory.md`.
