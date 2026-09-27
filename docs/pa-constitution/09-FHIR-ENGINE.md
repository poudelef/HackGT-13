# 09. FHIR engine

Built on the FHIR design proven in Suman's earlier benefit-plan work (`Questionnaire`, `InsurancePlan`, `QuestionnaireResponse`, 100% validation, markdown audit, source traceability), rewritten from the public HL7 specification. That work was constrained to documents only and no database; this project has neither constraint, so the engine also reads a FHIR-native patient chart and can emit a submission Bundle.

## Resources

| Resource | Built from | When | Tier |
|---|---|---|---|
| `Questionnaire` | Live clinical policy rules, or one live drug block | Draft build (validated), finalized at go-live | MVP |
| `QuestionnaireResponse` | PA request answers | On demand and at submit | MVP |
| `InsurancePlan` | Live benefit summary coverage items and plan identity | Draft build, finalized at go-live | Core |
| Patient chart (input) | Synthetic FHIR R4 bundle: Patient, Practitioner, Condition, MedicationRequest, Observation, Procedure, ServiceRequest, DocumentReference | Seeded (`15`) | MVP |
| `Bundle` (collection) | Packet: Patient, Practitioner, order (ServiceRequest or MedicationRequest), QuestionnaireResponse, DocumentReference evidence | At submit | Stretch |
| `Claim` (use = preauthorization), PAS-shaped | Order, patient, provider, insurer | At submit | Stretch |
| CDS Hooks `order-select` response | Coverage gate result as a card | On order | Stretch |

## Version decision

| Question | Decision |
|---|---|
| R4 or R4B | Emit R4B, validated, as in the earlier work. For Questionnaire, QuestionnaireResponse, InsurancePlan, and Bundle as used here, R4 and R4B are structurally the same. Da Vinci guides target R4; we say "FHIR R4-family" and record the choice in `memory.md`. |
| Library | `fhir.resources` R4B models. The earlier work pinned 7.1.0 with the R4B import path and rejected the newer default (R5) and the wrong serializer. Here, pin the release whose pydantic major matches the app's pydantic (v2); confirm in a 10-minute spike: import R4B Questionnaire, build, serialize with that release's serializer, validate. Record the pinned version in `memory.md`. |
| Patient input | Synthea and hand-authored bundles are R4 JSON. Read them as JSON into `clinical_records` (flattened fields plus `fhir_resource`); do not strict-validate input against R4B models. |

## Questionnaire mapping

| ClearPath | FHIR |
|---|---|
| Policy or drug block | `Questionnaire`: `url` `{FHIR_BASE_URL}/Questionnaire/{policy_id}[-{block_key}]`, `version` = first 12 chars of sha256, `status` draft or active, `title`, `publisher` = insurer, `date` = went_live_at |
| Rule | `item` type `group`, `linkId` = criterion_key, `text` = requirement_text |
| Page | extension `policy-page` (valueInteger) on the group |
| Source | extension `policy-source` (valueString: title, URL) on the root |
| Question | nested `item`, `linkId` = link_id, `type` from answer type, `required` true for always-enabled items |
| Units | `quantity` items with extension `questionnaire-unit` (valueCoding, UCUM) |
| enableWhen | `enableWhen` (`question`, `operator`, `answerBoolean`), `enableBehavior` when several |
| Pass condition | Not expressed in FHIR (production systems use CQL); kept in ClearPath JSON and cited in the audit |
| Review | extension `review-state` on each group (accepted or edited) |

## InsurancePlan mapping

| ClearPath | FHIR |
|---|---|
| Plan identity | `name`, `ownedBy.display`, `period` from plan year, `status` active |
| Identifier | `identifier.system` is a placeholder URL (`{FHIR_BASE_URL}/plan-id`), flagged as an open question as in the earlier work |
| Coverage item | `coverage[0].benefit[]`: `type.text` = service label (codes in `type.coding` only when written in the document), `requirement` = "Prior authorization required" or "No prior authorization required" |
| Evidence | extensions `policy-page` and `evidence-text` on each benefit |
| Criteria link | extension `criteria-questionnaire` (valueCanonical) when a live clinical policy is linked |

## QuestionnaireResponse mapping

| ClearPath | FHIR |
|---|---|
| Request | `questionnaire` = canonical with version; `status` = in-progress before submit, completed at submit; `subject.display` = synthetic patient; `author` = verifying clinician; `authored` |
| Answer | `item.answer.value[x]`: valueBoolean, valueQuantity (UCUM, e.g. `wk`), valueDate, valueString, valueCoding |
| Evidence | extension `evidence-quote` (valueString) and `evidence-source` (valueReference to DocumentReference) on the item |
| Clinician entry | extension `clinician-attestation` (valueString) |
| Disabled questions | Omitted |

Extension URLs live under `https://clearpath.example/fhir/StructureDefinition/`. They are demo identifiers, documented in `fhir/extensions.py`.

## Validation (100% target, zero errors)

1. Parse every emitted resource with the pinned `fhir.resources` R4B model.
2. Every Questionnaire linkId unique; every response linkId exists in its Questionnaire; every enableWhen references an earlier item; answer value types match item types.
3. A policy cannot go live, and a packet cannot be stored, with any validation error.
4. Validation results stored in the policy's `validation_report` and shown in the UI.

## Human-readable outputs

| Output | Content |
|---|---|
| Readable questionnaire view | The Questionnaire rendered as a form a reviewer can read or fill |
| FHIR JSON viewer | Pretty JSON with copy and download |
| Markdown audit per policy | Identity with evidence, sections and tier used, every item with page, source sentence, judge verdict, review decision, reviewer, time; questions and pass conditions; FHIR validation result |

## Build rules

- Builders are pure functions from stored ClearPath data to resource JSON.
- Built after human decisions; a locked human edit always wins.
- Written atomically (compute, validate, then store).
- Cached by fingerprint (`18`): Questionnaire and InsurancePlan keyed by builder version, current item data, and review states; QuestionnaireResponse keyed by builder version, answers, and verification state. Only validated resources are cached; a human decision changes the key and forces a rebuild.
- Every build writes an episode with the resource's fingerprint.
