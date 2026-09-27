"""Submission packet. Only met, verified rules. Immutable once stored."""

from __future__ import annotations

from app.fhir.builders import questionnaire_response
from app.fhir.validate import validate_resource
from app.repository import get_repo, now


def build(pa: dict, criteria: list[dict], *, preview: bool) -> dict:
    repo = get_repo()
    patient = repo.get_patient(pa["patient_id"])
    provider = repo.get_provider(pa["ordering_provider_id"])
    policy = repo.get_policy(pa["criteria_policy_id"]) if pa.get("criteria_policy_id") else None
    coverage = repo.get_item(pa["coverage_item_id"]) if pa.get("coverage_item_id") else None
    verified = [c for c in criteria if c.get("status") == "met" and c.get("verified_by")]
    payload = {
        "packet_version": (pa.get("packet_version") or 0) + (0 if preview else 1),
        "preview": preview,
        "pa_request_id": pa["id"],
        "submitted_at": None if preview else now(),
        "payer": {
            "insurer": pa["insurer"],
            "plan_name": pa["plan_name"],
            "plan_year": pa["plan_year"],
            "coverage": {
                "pa_required": True,
                "page": coverage["page"] if coverage else None,
                "policy_id": pa.get("benefit_summary_id"),
            },
            "criteria_source": {
                "policy_id": pa.get("criteria_policy_id"),
                "block_id": pa.get("criteria_block_id"),
                "source_kind": (policy or {}).get("source_kind"),
                "source_url": (policy or {}).get("source_url"),
                "went_live_by": (policy or {}).get("went_live_by"),
            },
        },
        "patient": {
            "full_name": patient["full_name"] if patient else "",
            "dob": patient.get("dob") if patient else None,
            "member_id": patient.get("member_id") if patient else None,
            "synthetic": True,
        },
        "ordering_provider": {
            "full_name": provider["full_name"] if provider else "",
            "specialty": provider.get("specialty") if provider else None,
        },
        "order": {
            "order_text": pa["order_text"],
            "service_code": pa.get("service_code"),
            "drug_name": pa.get("drug_name"),
        },
        "criteria": [_criterion(c, repo) for c in verified],
        "clinician_attestations": _attestations(verified, repo),
        "attachments": _attachments(verified, repo),
        "fhir": {"questionnaire_response": None, "bundle": None},
        "review_log_ids": [],
        "attestation": "The ordering clinician reviewed each criterion, its answers, and its evidence before submission.",
    }
    if policy:
        response = questionnaire_response(
            {**pa, "patient": patient, "submitted_at": payload["submitted_at"]},
            verified,
            policy,
            completed=not preview,
        )
        errors = validate_resource(response)
        if errors and not preview:
            from app.errors import ApiError

            raise ApiError("FHIR_INVALID", "QuestionnaireResponse failed validation.", 409)
        payload["fhir"]["questionnaire_response"] = response
    return payload


def _criterion(criterion: dict, repo) -> dict:
    verifier = repo.get_provider(criterion["verified_by"]) if criterion.get("verified_by") else None
    answers = []
    for answer in repo.answers_for(criterion["id"]):
        if not answer.get("enabled"):
            continue
        if answer.get("value") is None:
            continue
        source = None
        if answer.get("evidence_record_id"):
            record = repo._one("clinical_records", "select * from clinical_records where id = ?", (answer["evidence_record_id"],))
            if record:
                author = repo.get_provider(record["author_provider_id"]) if record.get("author_provider_id") else None
                source = {
                    "author": author["full_name"] if author else None,
                    "date": record.get("start_date"),
                    "document_id": record.get("source_document_id"),
                }
        answers.append(
            {
                "link_id": answer["link_id"],
                "value": answer.get("value"),
                "fill_method": answer.get("fill_method"),
                "review_state": answer.get("review_state"),
                "evidence_text": answer.get("evidence_text"),
                "source": source,
            }
        )
    return {
        "criterion_key": criterion["criterion_key"],
        "requirement_text": criterion["requirement_text"],
        "policy_page": criterion["policy_page"],
        "status": "met",
        "answers": answers,
        "verified_by": verifier["full_name"] if verifier else None,
        "verified_at": criterion.get("verified_at"),
    }


def _attestations(criteria, repo) -> list[dict]:
    rows = []
    for criterion in criteria:
        for answer in repo.answers_for(criterion["id"]):
            if answer.get("attestation"):
                who = repo.get_provider(answer["answered_by"]) if answer.get("answered_by") else None
                rows.append(
                    {
                        "link_id": answer["link_id"],
                        "attestation": answer["attestation"],
                        "by": who["full_name"] if who else None,
                    }
                )
    return rows


def _attachments(criteria, repo) -> list[dict]:
    seen = set()
    rows = []
    for criterion in criteria:
        for answer in repo.answers_for(criterion["id"]):
            record_id = answer.get("evidence_record_id")
            if not record_id:
                continue
            record = repo._one("clinical_records", "select * from clinical_records where id = ?", (record_id,))
            if not record or not record.get("source_document_id") or record["source_document_id"] in seen:
                continue
            seen.add(record["source_document_id"])
            document = repo.get_document(record["source_document_id"])
            if document:
                rows.append({"document_id": document["id"], "file_name": document["file_name"]})
    return rows
