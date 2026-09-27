"""Isolate teammate INPUT JSON -> ClearPath Patient / Provider / draft PARequest.

When the teammate finalizes field names, change only this module.
"""

from __future__ import annotations

from typing import Any

from app.errors import ApiError
from app.repository import get_repo, new_id, now


def ingestExtractedDocument(payload: dict[str, Any]) -> dict:
    """Map placeholder teammate extraction shape into stored draft PA records."""
    patient_in = payload.get("patient") or {}
    provider_in = payload.get("provider") or {}
    treatment = payload.get("treatment_requested") or {}
    if not patient_in.get("name") and not patient_in.get("id"):
        raise ApiError("INVALID_PDF", "patient.name or patient.id is required.", 400)
    if not treatment.get("service_category") and not treatment.get("clinical_notes"):
        raise ApiError("INVALID_PDF", "treatment_requested.service_category is required.", 400)

    repo = get_repo()
    patient_id = str(patient_in.get("id") or new_id())
    provider_id = str(provider_in.get("id") or new_id())

    patient = repo.upsert_patient(
        {
            "id": patient_id,
            "full_name": patient_in.get("name") or f"Patient {patient_id[:8]}",
            "dob": patient_in.get("dob"),
            "sex": patient_in.get("sex"),
            "member_id": patient_in.get("member_id") or patient_in.get("id"),
            "synthetic": True,
        }
    )
    # Stash plan id on patient via clinical record note if no column; plan lives on PA.
    provider = repo.upsert_provider(
        {
            "id": provider_id,
            "full_name": provider_in.get("name") or "Ordering clinician",
            "specialty": provider_in.get("specialty") or provider_in.get("npi") or None,
        }
    )

    plan_id = patient_in.get("insurance_plan_id")
    insurer, plan_name, plan_year = _resolve_plan(plan_id)
    service_category = (treatment.get("service_category") or "").strip()
    clinical_notes = (treatment.get("clinical_notes") or "").strip()
    diagnosis_codes = treatment.get("diagnosis_codes") or []
    order_text = service_category or clinical_notes[:120] or "Ingested order"
    service_code = _first_code(diagnosis_codes)  # CPT may arrive later; keep placeholder

    # Prefer a CPT-looking code from notes / codes if present.
    for code in diagnosis_codes:
        if str(code).isdigit() and len(str(code)) == 5:
            service_code = str(code)
            break

    if clinical_notes:
        repo.insert_record(
            {
                "patient_id": patient["id"],
                "resource_type": "DocumentReference",
                "record_kind": "clinical_note",
                "display": "Ingested clinical notes",
                "body": clinical_notes,
                "author_provider_id": provider["id"],
                "synthetic": 1,
            }
        )

    source_ref = payload.get("source_document_reference")
    pa = repo.create_pa(
        {
            "patient_id": patient["id"],
            "ordering_provider_id": provider["id"],
            "insurer": insurer,
            "plan_name": plan_name,
            "plan_year": plan_year or "",
            "order_text": order_text,
            "service_code": service_code,
            "drug_name": None,
            "status": "draft",
            "readiness": 0,
            "insurance_plan_id": plan_id,
            "service_category": service_category,
            "source_document_reference": source_ref,
            "ingest_payload": payload,
            "coverage_note": None,
        }
    )
    repo.add_event(pa["id"], "created", "Ingested from teammate extraction (draft)", "engine")
    return {
        "patient_id": patient["id"],
        "provider_id": provider["id"],
        "pa_request_id": pa["id"],
        "status": "draft",
        "service_category": service_category,
        "insurance_plan_id": plan_id,
        "created_at": pa.get("created_at") or now(),
    }


def _resolve_plan(plan_id: str | None) -> tuple[str, str, str | None]:
    repo = get_repo()
    if plan_id:
        policy = repo.get_policy(plan_id)
        if policy:
            return (
                policy.get("insurer") or "Unknown insurer",
                policy.get("plan_name") or policy.get("file_name") or "Plan",
                policy.get("plan_year"),
            )
        # Accept opaque ids that are not policy UUIDs yet.
        return ("Unknown insurer", str(plan_id), None)
    # Default to first live benefit summary so doctor can edit.
    for policy in repo.list_policies(False):
        if policy.get("document_role") == "benefit_summary":
            return (
                policy.get("insurer") or "Unknown insurer",
                policy.get("plan_name") or "Plan",
                policy.get("plan_year"),
            )
    return ("Unknown insurer", "Unassigned plan", None)


def _first_code(codes: list) -> str | None:
    for code in codes:
        if code:
            return str(code)
    return None
