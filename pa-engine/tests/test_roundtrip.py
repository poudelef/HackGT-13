"""Synthetic chart against the fictional fallback policy. Statuses must match the answer key."""

from synth.bootstrap import MARIA, REYES, bootstrap_demo
from app.check.service import check, recheck
from app.check.fact_extractor import extract
from app.ingest.pdf_reader import read_pdf
from app.repository import get_repo


def test_mri_starts_missing_therapy_then_meets_after_the_withheld_note():
    bootstrap_demo(force=True)
    base = {
        "patient_id": MARIA,
        "ordering_provider_id": REYES,
        "insurer": "Northwind Mutual",
        "plan_name": "Open Access PPO",
        "plan_year": "2026",
    }
    office = check({**base, "order_text": "Office visit"})
    assert office["status"] == "not_required"
    assert office["coverage"]["pa_required"] is False

    mri = check({**base, "order_text": "MRI lumbar spine without contrast", "service_code": "72148"})
    assert mri["met_count"] == 4
    assert mri["total_count"] == 5
    assert mri["readiness"] == 0.8
    missing = [row for row in mri["criteria"] if row["status"] == "missing"]
    assert len(missing) == 1
    assert missing[0]["criterion_type"] == "prior_treatment"
    assert missing[0]["likely_owner"]["full_name"] == "Dr. Raj Patel"
    assert mri["can_submit"] is False

    repo = get_repo()
    document = repo.documents_for(MARIA, pending_only=True)[0]
    text = "\n".join(page["text"] for page in read_pdf(document["storage_path"]))
    assert "SYNTHETIC TEST DATA" in text
    run = repo.create_run(None, "roundtrip-note")
    extract(MARIA, text, document["id"], run_id=run["id"])
    repo.finish_run(run["id"], "complete")
    again = recheck(mri["id"])
    assert again["met_count"] == 5
    assert again["status"] == "ready_for_review"
    therapy = next(row for row in again["criteria"] if row["criterion_type"] == "prior_treatment")
    quotes = [q["evidence_text"] for q in therapy["questions"] if q.get("evidence_text")]
    assert any(q and "7 weeks of physical therapy" in q for q in quotes)
