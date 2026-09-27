# 04. API

Base URL `NEXT_PUBLIC_PA_ENGINE_URL`. JSON everywhere except uploads. Mock copies of every response live in `web/mocks/pa/` and are pushed before real endpoints exist. Real responses must match mocks exactly.

## Library and review (Gates 1 and 2)

| Method | Path | Purpose |
|---|---|---|
| POST | `/policies` | Upload a real PDF (multipart: `file`, `document_role`, `source_url`, `downloaded_at`, optional `source_kind`) |
| GET | `/policies` | Live insurers, plans, services, drugs (drives order screen); `?include_drafts=true` for admin |
| GET | `/policies/{id}` | Policy with identity, sections, context report, validation report |
| POST | `/policies/{id}/confirm-role` | Confirm type when pre-check disagreed |
| PATCH | `/policies/{id}/identity` | Correct insurer, plan, year (locks) |
| GET | `/policies/{id}/review-queue` | Items sorted by risk |
| POST | `/policies/{id}/items/{item_id}/accept` | Gate 1 |
| POST | `/policies/{id}/items/{item_id}/edit` | Gate 1; re-runs checks; locks |
| POST | `/policies/{id}/items/{item_id}/reject` | Gate 1; note required |
| POST | `/policies/{id}/items/{item_id}/apply-suggestion` | Apply newer extractor output to a locked item (human action) |
| POST | `/policies/{id}/reprocess` | Re-extract; locked items preserved |
| POST | `/policies/{id}/go-live` | Gate 2 |
| GET | `/policies/{id}/blocks` | Drug blocks index |
| POST | `/policies/{id}/blocks/{block_id}/extract` | Extract one drug block |
| POST | `/policies/{id}/blocks/{block_id}/go-live` | Gates 1 and 2 for a block |
| GET | `/policies/{id}/audit.md` | Markdown audit |
| GET | `/policies/{id}/fhir` | Questionnaire (clinical, block) or InsurancePlan (benefit summary) |

## Reports and checks (Gates 3 and 4)

| Method | Path | Purpose |
|---|---|---|
| POST | `/reports/extract` | Document to FHIR-shaped `clinical_records` |
| POST | `/pa/check` | Create request: match, gate, answer, evaluate |
| POST | `/pa/{id}/match` | Clinician picks the policy item when ambiguous |
| GET | `/pa/{id}` | Full request |
| POST | `/pa/{id}/recheck` | Refill unlocked unanswered questions, re-evaluate |
| POST | `/pa/{id}/answers/{aid}/reject` | Gate 3; reason required |
| POST | `/pa/{id}/answers/{aid}/enter` | Gate 3; source and attestation required |
| POST | `/pa/{id}/criteria/{cid}/verify` | Gate 3; rule must be met |
| GET | `/pa/{id}/packet` | Gate 4 preview or stored packet |
| POST | `/pa/{id}/submit` | Gate 4 |
| GET | `/pa/{id}/fhir/questionnaire-response` | FHIR QuestionnaireResponse |
| GET | `/pa/{id}/fhir/bundle` | FHIR Bundle (stretch) |
| GET | `/health` | Commit, DB, providers |

## Key payloads

`POST /policies` response:
```json
{
  "id": "uuid", "cached": false, "status": "draft",
  "document_role": "clinical_policy", "role_hint": "clinical_policy", "source_kind": "published",
  "identity": {
    "insurer": { "value": "Example Health Plan", "evidence": "Example Health Plan Medical Policy", "page": 1 },
    "plan_name": { "value": null, "evidence": null, "page": null },
    "plan_year": { "value": "2026", "evidence": "Effective Date: 01/01/2026", "page": 1 }
  },
  "sections": { "tier_used": "B", "failed_tiers": [{ "tier": "A", "reason": "no TOC" }], "pages": [2,3,4], "possibly_truncated": false },
  "item_counts": { "total": 6, "auto_approved": 4, "pending_review": 2 },
  "validation_report": {
    "grounding": { "passed": 5, "failed": 1 },
    "judge": { "ACCURATE": 4, "WRONG_VALUE": 1, "HALLUCINATED": 0, "VAGUE": 1, "UNAVAILABLE": 0 },
    "questions": { "condition_coverage": 1.0 },
    "fhir": { "valid": true, "errors": [] }
  }
}
```

`POST /policies/{id}/items/{item_id}/edit`:
```json
{ "reviewer": "Suman", "data": { "criterion_key": "pt_six_weeks", "requirement_text": "...", "conditions": [] }, "note": "Page says six weeks" }
```

`POST /pa/check`:
```json
{
  "patient_id": "uuid", "ordering_provider_id": "uuid",
  "insurer": "Example Health Plan", "plan_name": "Example PPO", "plan_year": "2026",
  "order_text": "MRI lumbar spine without contrast", "service_code": "72148", "drug_name": null,
  "catalog_item_id": "uuid or null"
}
```

PA request object (check, get, recheck, reject, enter, verify, submit):
```json
{
  "id": "uuid", "status": "needs_info", "readiness": 0.8, "met_count": 4, "total_count": 5, "can_submit": false,
  "order_text": "MRI lumbar spine without contrast",
  "patient": { "id": "uuid", "full_name": "Maria Rodriguez", "synthetic": true },
  "ordering_provider": { "id": "uuid", "full_name": "Dr. Reyes" },
  "coverage": { "pa_required": true, "page": 34, "evidence_text": "...", "document_url": "signed-url" },
  "criteria_source": { "policy_id": "uuid", "title": "...", "source_kind": "published", "document_url": "signed-url" },
  "match_candidates": null,
  "criteria": [
    {
      "id": "uuid", "criterion_key": "pt_six_weeks", "seq": 5,
      "requirement_text": "...", "criterion_type": "prior_treatment", "policy_page": 13, "origin": "policy",
      "status": "missing", "status_reason": "No documentation found that physical therapy was received",
      "judge_verdict": "ACCURATE", "review_state_of_rule": "accepted",
      "likely_owner": { "provider_id": "uuid", "full_name": "Dr. Patel", "reason": "Wrote physical therapy referral on Jul 15" },
      "verified_by": null,
      "questions": [
        {
          "id": "uuid", "link_id": "pt_six_weeks.received", "text": "Has the patient received physical therapy for this condition?",
          "answer_type": "boolean", "enabled": true, "value": null, "fill_method": null,
          "review_state": "unanswered", "evidence_text": null, "evidence_source": null,
          "edited_by_human": false, "rejected_ai_value": null, "reject_reason": null, "attestation": null
        }
      ]
    }
  ],
  "events": [ { "event_type": "checked", "message": "4 of 5 criteria met", "actor": "engine", "created_at": "iso" } ]
}
```

`POST /pa/{id}/answers/{aid}/reject`: `{ "provider_id": "uuid", "reason": "Quote refers to the knee, not the spine" }`

`POST /pa/{id}/answers/{aid}/enter`:
```json
{ "provider_id": "uuid", "value": 7, "unit": "weeks", "source_document_id": "uuid",
  "evidence_text": "Completed 7 weeks of PT", "attestation": "I reviewed the PT discharge summary dated Sep 20." }
```

`POST /pa/{id}/criteria/{cid}/verify` and `/submit`: `{ "provider_id": "uuid" }`.

## Errors

`{ "error": { "code": "...", "message": "..." } }`

| Code | HTTP | When |
|---|---|---|
| `INVALID_PDF` / `NO_TEXT_LAYER` | 400 | Unreadable or scanned |
| `ROLE_UNCONFIRMED` | 409 | Pre-check disagreed; confirm needed |
| `EXTRACTION_FAILED` | 502 | Group failed after retry (others continue) |
| `ITEMS_UNDECIDED` | 409 | Go-live with undecided items |
| `QUESTIONS_INCOMPLETE` | 409 | Condition coverage below 100% |
| `FHIR_INVALID` | 409 | Resource failed validation |
| `LOCKED_BY_HUMAN` | 409 | Engine write to a locked row |
| `POLICY_NOT_FOUND` | 404 | No live criteria for the order |
| `BLOCK_NOT_LIVE` | 409 | Drug block not reviewed |
| `AMBIGUOUS_MATCH` | 409 | Clinician must choose the item |
| `REASON_REQUIRED` / `ATTESTATION_REQUIRED` | 400 | Gate 3 inputs missing |
| `CRITERION_NOT_MET` | 409 | Verify a rule not met |
| `NOT_ALL_VERIFIED` | 409 | Submit too early |
| `INVALID_TRANSITION` | 409 | Illegal status change |
| `RUN_LIMIT` | 429 | Run hit call or time limit (status partial) |
| `MODEL_TIMEOUT` | 504 | Timeout with no fallback |

## Teammate contracts

| From | To | What |
|---|---|---|
| Sambhav | Engine | `POST /reports/extract` after upload; `POST /pa/check` from the order screen |
| Engine | Sambhav | `GET /policies` catalog; `drug_name` for access panel; Realtime on `pa_requests`, `pa_events` |
| Sambhav | Engine | `clinical_records` in the FHIR-native shape above; `patients.synthetic = true` |
| Engine | Harry | `criteria[].likely_owner`, `status_reason` |
| Harry | Engine | Evidence upload then `POST /pa/{id}/recheck` |
