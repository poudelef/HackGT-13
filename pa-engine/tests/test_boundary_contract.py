"""Boundary contract: teammate ingest/export + PA rules view + deny blocked (G1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.boundary.export_pa import EXPORT_STATUS, buildOutputForTeammate
from app.boundary.ingest_extracted import ingestExtractedDocument
from app.boundary.pa_rules import lookup_requirement
from app.check import service as check_service
from app.main import app
from app.repository import get_repo, new_id

client = TestClient(app)


def test_export_status_mapping_no_denied():
    assert "denied" not in EXPORT_STATUS.values()
    assert EXPORT_STATUS["approved"] == "approved"
    assert EXPORT_STATUS["info_requested"] == "additional_info_requested"
    assert EXPORT_STATUS["not_required"] == "no_pa_needed"
    assert EXPORT_STATUS["in_review"] == "under_review"


def test_ingest_creates_draft_and_export_maps_status():
    repo = get_repo()
    policy_id = new_id()
    sha = new_id().replace("-", "") + new_id().replace("-", "")
    repo._insert_raw(
        "policies",
        {
            "id": policy_id,
            "sha256": sha[:64],
            "file_name": "plan.pdf",
            "storage_path": "/tmp/plan.pdf",
            "document_role": "benefit_summary",
            "source_kind": "fictional_fallback",
            "status": "live",
            "insurer": "Acme",
            "plan_name": "PPO",
            "plan_year": "2026",
        },
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy_id,
            "item_type": "coverage",
            "item_key": "mri_lumbar",
            "seq": 1,
            "service_label": "MRI lumbar spine",
            "service_codes": ["72148"],
            "data": {
                "service_label": "MRI lumbar spine",
                "pa_status": "required",
                "pa_required": True,
                "evidence_text": "PA required",
            },
            "original_data": {},
            "page": 3,
            "review_state": "accepted",
            "edited_by_human": True,
        }
    )

    payload = {
        "patient": {
            "id": "pat-boundary-1",
            "name": "Alex Boundary",
            "dob": "1980-01-01",
            "insurance_plan_id": policy_id,
        },
        "provider": {"id": "prov-boundary-1", "name": "Dr Test"},
        "treatment_requested": {
            "service_category": "MRI lumbar spine",
            "diagnosis_codes": ["M54.5"],
            "clinical_notes": "Chronic low back pain.",
        },
        "source_document_reference": "referral-1.pdf",
    }
    created = ingestExtractedDocument(payload)
    assert created["status"] == "draft"
    pa_id = created["pa_request_id"]
    pa = repo.get_pa(pa_id)
    assert pa is not None
    assert pa["status"] == "draft"
    assert pa["source_document_reference"] == "referral-1.pdf"

    out = buildOutputForTeammate(pa_id)
    assert out["patient_id"] == "pat-boundary-1"
    assert out["status"] == "draft"
    assert out["service_category"] == "MRI lumbar spine"

    rule = lookup_requirement(insurance_plan_id=policy_id, service_category="MRI lumbar spine")
    assert rule["requirement"] == "required"

    # HTTP surface
    res = client.post("/ingest/patient-extraction", json={**payload, "patient": {**payload["patient"], "id": "pat-boundary-2"}})
    assert res.status_code == 200
    assert res.json()["status"] == "draft"

    deny = client.post(f"/pa-requests/{pa_id}/decision", json={"action": "deny", "note": "no"})
    assert deny.status_code == 409
    msg = deny.json()["error"]["message"]
    assert "G1" in msg or "Denial" in msg


def test_present_includes_pa_determination_banner_fields():
    repo = get_repo()
    patient_id, provider_id = new_id(), new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "Pat Det", "dob": "1970-01-01", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr Det", "specialty": "ortho"})
    policy_id = new_id()
    sha = new_id().replace("-", "") + new_id().replace("-", "")
    repo._insert_raw(
        "policies",
        {
            "id": policy_id,
            "sha256": sha[:64],
            "file_name": "eoc.pdf",
            "storage_path": "/tmp/eoc.pdf",
            "document_role": "benefit_summary",
            "source_kind": "published",
            "status": "live",
            "insurer": "Banner Plan",
            "plan_name": "PPO",
            "plan_year": "2026",
        },
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy_id,
            "item_type": "coverage",
            "item_key": "mri",
            "seq": 1,
            "service_label": "MRI lumbar spine without contrast",
            "service_codes": ["72148"],
            "data": {
                "service_label": "MRI lumbar spine without contrast",
                "pa_status": "required",
                "pa_required": True,
                "evidence_text": "Authorization required",
            },
            "original_data": {},
            "page": 10,
            "review_state": "accepted",
            "edited_by_human": True,
        }
    )
    view = check_service.check(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Banner Plan",
            "plan_name": "PPO",
            "plan_year": "2026",
            "order_text": "MRI lumbar spine without contrast",
            "service_code": "72148",
        }
    )
    assert view.get("pa_determination")
    assert view["pa_determination"]["pa_required"] is True
    assert "required" in view["pa_determination"]["label"].lower() or view["pa_determination"]["requirement"] == "required"
    exported = client.get(f"/pa-requests/{view['id']}/export")
    assert exported.status_code == 200
    assert exported.json()["pa_request_id"] == view["id"]
