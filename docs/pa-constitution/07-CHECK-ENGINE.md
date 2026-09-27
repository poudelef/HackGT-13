# 07. Check engine: from order to submission

## 1. Order input

The order screen offers a **catalog** built from live documents: coverage items from benefit summaries, services named in live clinical policies' `applies_to`, and live drug blocks. Free text is allowed as a fallback.

## 2. Service matching

1. Catalog item chosen: direct match.
2. Code given: exact match on `service_codes` or `applies_to`.
3. Otherwise P-SVC returns candidates, each with a matched phrase verified by code.
4. Zero or several candidates: status `matching`, `match_candidates` returned, clinician chooses (`POST /pa/{id}/match`). Never guess silently.

## 3. Coverage gate

| Situation | Result |
|---|---|
| Matched coverage item says PA not required | `not_required`, cite page, stop |
| Says PA required | Continue; `coverage_note` cites page |
| No live benefit summary or no coverage match | Continue; note "Coverage not confirmed from benefit summary" (G9) |
| Drug with live block but no PA marker found | Continue; note it |
| Drug block indexed but not live | Stop with `BLOCK_NOT_LIVE`; reviewer notified |

## 4. Report fact extraction

1. Store the original text as one `DocumentReference` record (`record_kind = note`, `body` = original).
2. Clean with the context builder (report settings) and run P3 for coded facts; dates only if written.
3. Insert each fact as a FHIR-shaped `clinical_records` row with `source_document_id`.
4. Structured records already seeded from the synthetic FHIR bundle (`15`) are used directly.

## 5. Answer filling

Rules in `seq` order, questions in link order.

| Fill method | How |
|---|---|
| `code_lookup` | Records by code prefix, code system, or normalized drug name; age from `patients.dob`; specialty from `providers` |
| `date_math` | Python over record dates relative to today (`DEMO_TODAY` in demo) |
| `llm_quote` | P4 per note (newest first); `quote.verify` against original body; min length 12 |
| `llm_quote_value` | P4b quote plus value; quote verified and value digits inside the quote |

Then apply `enableWhen`. Answers are cached in the answer layer of `artifact_cache` (`18`), keyed by question, rule version, and the hash of the patient's record set; any new record changes the hash. Every fill, evaluation, review action, and status change writes an episode, shown as the request's timeline.

## 6. Evaluation

`pass_eval.py`, three values (true, false, unknown). `all`: false if any false, else unknown if any unknown, else true. `any`: true if any true, else unknown if any unknown, else false.

| Result | Status | Reason |
|---|---|---|
| true | met | none |
| false | missing | factual leaf message ("Physical therapy completed: 3 weeks; policy requires 6") |
| unknown | missing | "No documentation found that {condition}" |
| true but relies on an LLM answer and the rule's judge verdict was VAGUE | unclear | "Policy wording flagged as vague; review" |
| conflicting records for one answer | unclear | "Records conflict: ..." |

Operators: `eq`, `gte`, `gt`, `lte`, `lt`, `within`, `at_least_ago`, `duration_gte`, `prefix_in`, `in`, `exists` (`08`).

## 7. Likely owner

For missing rules: author of a related referral; else a care team provider whose specialty maps to the rule; else none. Never guess a person.

## 8. Score and save

`readiness = met / total`. All met: `ready_for_review`; else `needs_info`. Atomic write; on failure, roll back.

## 9. Clinician review (Gate 3)

| Action | Effect |
|---|---|
| Reject answer | AI value moved to `rejected_ai_value`; reason required; locked; rule re-evaluated; event and `review_log` |
| Enter answer | Value, source document, evidence text, attestation required; `clinician_entered`; locked; rule re-evaluated |
| Verify rule | Only when met; enabled answers become `clinician_confirmed` unless clinician-set |

## 10. Re-check

Skips verified rules and locked answers. Refills unanswered, unlocked questions; re-evaluates; event "x of y criteria met". Idempotent.

## 11. Packet and submit (Gate 4)

Built only when `can_submit`.

```json
{
  "packet_version": 1, "preview": false, "pa_request_id": "uuid", "submitted_at": "iso",
  "payer": { "insurer": "...", "plan_name": "...", "plan_year": "...",
             "coverage": { "pa_required": true, "page": 34, "policy_id": "uuid" },
             "criteria_source": { "policy_id": "uuid", "block_id": null, "source_kind": "published", "source_url": "...", "went_live_by": "Suman" } },
  "patient": { "full_name": "Maria Rodriguez", "dob": "1974-03-11", "member_id": "SYN-0042", "synthetic": true },
  "ordering_provider": { "full_name": "Dr. Reyes", "specialty": "spine" },
  "order": { "order_text": "MRI lumbar spine without contrast", "service_code": "72148", "drug_name": null },
  "criteria": [ { "criterion_key": "...", "requirement_text": "...", "policy_page": 13, "status": "met",
                  "answers": [ { "link_id": "...", "value": true, "fill_method": "llm_quote", "review_state": "clinician_confirmed",
                                 "evidence_text": "...", "source": { "author": "Dr. Patel", "date": "2026-09-20", "document_id": "uuid" } } ],
                  "verified_by": "Dr. Reyes", "verified_at": "iso" } ],
  "clinician_attestations": [ { "link_id": "...", "attestation": "...", "by": "Dr. Reyes" } ],
  "attachments": [ { "document_id": "uuid", "file_name": "pt_progress_note.pdf" } ],
  "fhir": { "questionnaire_response": {}, "bundle": null },
  "review_log_ids": ["uuid"],
  "attestation": "The ordering clinician reviewed each criterion, its answers, and its evidence before submission."
}
```

Rules: only met and verified rules; only enabled answered questions; attachments limited to cited documents; immutable once submitted; resubmission creates a new version; FHIR must validate first.

## 12. Fake insurer

Background task: submitted, then in review after `INSURER_DELAY_SECONDS`, then approved. With `INSURER_REQUEST_INFO=true`, it instead requests one item (a rule from the same live policy, or a named document), which becomes a criterion with `origin = insurer_request`, and status moves to `info_requested`, then per scoring. Never denies (G1).
