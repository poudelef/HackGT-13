"""Load the fictional library, approve it, and seed the synthetic chart."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.check.dates import today
from app.config import settings
from app.pipeline import pipeline_runner
from app.repository import get_repo, new_id, reset_repo
from app.review.review import accept, go_live
from synth.documents import (
    BENEFIT_PAGES,
    CLINICAL_PAGES,
    DRUG_PAGES,
    NOTE_BODY,
    PATIENT_FOOTER,
    POLICY_FOOTER,
    REFERRAL_DISPLAY,
    WITHHELD_BODY,
    write_pdf,
)

MARIA = "11111111-1111-4111-8111-111111111111"
REYES = "22222222-2222-4222-8222-222222222222"
PATEL = "33333333-3333-4333-8333-333333333333"


def bootstrap_demo(force: bool = False) -> dict:
    repo = get_repo()
    if repo.list_policies(True) and not force:
        return {"status": "already_loaded", "patients": repo.list_patients(), "policies": repo.list_policies(True)}
    if force:
        path = settings.database_path
        repo.close()
        Path(path).unlink(missing_ok=True)
        reset_repo(path)
        repo = get_repo()
    settings.demo_dir.mkdir(parents=True, exist_ok=True)
    clinical = settings.demo_dir / "lumbar-imaging-policy.pdf"
    benefit = settings.demo_dir / "summary-of-benefits.pdf"
    drug = settings.demo_dir / "northpine-criteria.pdf"
    withheld = settings.demo_dir / "pt-progress-note.pdf"
    write_pdf(clinical, CLINICAL_PAGES, POLICY_FOOTER)
    write_pdf(benefit, BENEFIT_PAGES, POLICY_FOOTER)
    write_pdf(drug, DRUG_PAGES, POLICY_FOOTER)
    write_pdf(withheld, [[WITHHELD_BODY, "Author: Dr. Raj Patel", "Date: September 20, 2026"]], PATIENT_FOOTER)

    clinical_policy = _ingest(clinical, "clinical_policy")
    benefit_policy = _ingest(benefit, "benefit_summary")
    drug_policy = _ingest(drug, "drug_criteria")
    _decide(clinical_policy["id"])
    _decide(benefit_policy["id"])
    go_live(clinical_policy["id"], "Suman")
    go_live(benefit_policy["id"], "Suman")
    block = get_repo().blocks_for(drug_policy["id"])[0]
    pipeline_runner.extract_block(drug_policy["id"], block["id"])
    _decide(drug_policy["id"])
    go_live(drug_policy["id"], "Suman", block_id=block["id"])

    _seed_chart(withheld)
    return {
        "status": "loaded",
        "clinical_policy_id": clinical_policy["id"],
        "benefit_policy_id": benefit_policy["id"],
        "drug_policy_id": drug_policy["id"],
        "patient_id": MARIA,
        "provider_id": REYES,
    }


def _ingest(path: Path, role: str) -> dict:
    body = pipeline_runner.ingest_upload(
        path.read_bytes(),
        path.name,
        role,
        f"file://{path.name}",
        "2026-09-26",
        "fictional_fallback",
    )
    if body.get("cached"):
        return body
    return pipeline_runner.wait_for_ingestion(body["id"])


def _decide(policy_id: str) -> None:
    repo = get_repo()
    for item in repo.items_for(policy_id):
        if item["review_state"] in {"accepted", "edited", "rejected"}:
            continue
        note = None
        if not (item.get("grounding") or {}).get("passed", True):
            note = "Reviewer confirmed the source sentence on the cited page."
        accept(policy_id, item["id"], "Suman", note)


def _seed_chart(withheld: Path) -> None:
    repo = get_repo()
    repo.upsert_provider({"id": REYES, "full_name": "Dr. Ana Reyes", "specialty": "spine"})
    repo.upsert_provider({"id": PATEL, "full_name": "Dr. Raj Patel", "specialty": "primary care"})
    repo.upsert_patient(
        {
            "id": MARIA,
            "full_name": "Maria Rodriguez",
            "dob": "1974-03-11",
            "sex": "female",
            "member_id": "SYN-0042",
            "synthetic": True,
        }
    )
    clock = today()
    onset = (clock - timedelta(weeks=12)).isoformat()
    repo.insert_record(
        {
            "patient_id": MARIA,
            "resource_type": "Condition",
            "record_kind": "diagnosis",
            "code": "M54.16",
            "code_system": "http://hl7.org/fhir/sid/icd-10-cm",
            "display": "Lumbar radiculopathy",
            "start_date": onset,
            "author_provider_id": REYES,
            "synthetic": True,
            "fhir_resource": {"resourceType": "Condition", "code": {"text": "Lumbar radiculopathy"}},
        }
    )
    repo.insert_record(
        {
            "patient_id": MARIA,
            "resource_type": "DocumentReference",
            "record_kind": "note",
            "body": NOTE_BODY,
            "start_date": "2026-09-02",
            "author_provider_id": REYES,
            "display": "Clinic note",
            "synthetic": True,
            "fhir_resource": {"resourceType": "DocumentReference", "status": "current"},
        }
    )
    repo.insert_record(
        {
            "patient_id": MARIA,
            "resource_type": "ServiceRequest",
            "record_kind": "referral",
            "display": REFERRAL_DISPLAY,
            "start_date": "2026-07-15",
            "author_provider_id": PATEL,
            "body": "Physical therapy referral for lumbar radiculopathy.",
            "synthetic": True,
            "fhir_resource": {"resourceType": "ServiceRequest", "status": "active"},
        }
    )
    document = repo.create_document(
        {
            "id": new_id(),
            "patient_id": MARIA,
            "file_name": withheld.name,
            "storage_path": str(withheld),
            "doc_type": "pt_progress_note",
            "in_chart": False,
            "synthetic": True,
        }
    )
    repo.add_review_log(
        {
            "actor": "Suman",
            "actor_role": "content_reviewer",
            "target_table": "documents",
            "target_id": document["id"],
            "action": "approve_synthetic",
            "before": None,
            "after": {"synthetic": True},
            "note": "Synthetic note reviewed before seeding.",
        }
    )
