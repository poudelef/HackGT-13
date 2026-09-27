"""Coverage chart extract -> InsurancePlan must keep every PA row."""

from __future__ import annotations

import json
from pathlib import Path

from app.fhir.builders import insurance_plan
from app.fhir.validate import validate_resource
from app.ingest.coverage_lines import coverage_from_line
from app.ingest.coverage_seed import apply_categories, summarize_insurance_plan
from app.repository import get_repo, new_id


FIXTURE = Path(__file__).parent / "fixtures" / "uhc_oh_s3_2026_coverage.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_uhc_fixture_has_full_chart_counts():
    data = _load_fixture()
    cats = data["categories"]
    assert len(cats) == 90
    assert sum(1 for c in cats if c["pa_status"] == "required") == 41
    assert sum(1 for c in cats if c["pa_status"] == "not_required") == 41
    assert sum(1 for c in cats if c["pa_status"] == "conditional") == 8


def test_dagger_marker_sets_pa_required():
    dagger = "\u2021\u2021"
    row = coverage_from_line(f"Cardiac rehabilitation services {dagger} $0 copay per visit", 62)
    assert row["pa_required"] is True
    assert row["marker_used"] == dagger
    assert "Cardiac" in row["service_label"]
    plain = coverage_from_line("Annual wellness visit $0 copay (preventive)", 60)
    assert plain["pa_required"] is False


def test_insurance_plan_includes_all_fixture_benefits():
    data = _load_fixture()
    policy = {
        "id": new_id(),
        "document_role": "benefit_summary",
        "plan_name": data["plan_name"],
        "insurer": data["insurer"],
        "plan_year": data["plan_year"],
        "sha256": "a" * 64,
        "source_url": data["source"],
        "file_name": data["source"],
    }
    items = []
    for row in data["categories"]:
        payload = {
            "service_label": row["service_label"],
            "service_codes": [],
            "pa_required": row["pa_required"],
            "pa_status": row["pa_status"],
            "page": row.get("page") or 1,
            "evidence_text": row.get("evidence_text") or row["service_label"],
            "reference": row.get("note"),
        }
        items.append(
            {
                "item_type": "coverage",
                "review_state": "auto_approved",
                "page": payload["page"],
                "service_label": row["service_label"],
                "data": payload,
            }
        )
    resource = insurance_plan(policy, items, status="draft")
    assert resource["resourceType"] == "InsurancePlan"
    assert resource["name"] == data["plan_name"]
    summary = summarize_insurance_plan(resource)
    assert summary["benefit_count"] == 90
    assert summary["required"] == 41
    assert summary["not_required"] == 41
    assert summary["conditional"] == 8
    errors = validate_resource(resource)
    assert errors == [], errors
    benefits = resource["coverage"][0]["benefit"]
    assert len(benefits) == 90


def test_apply_coverage_seed_rebuilds_failed_eoc_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    data = _load_fixture()
    repo = get_repo()
    pdf = tmp_path / "eoc.pdf"
    pdf.write_bytes(b"%PDF-1.4\ntrailer\n%%EOF\n" + b"x" * 200)
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "source_url": "https://example.test/eoc.pdf",
            "downloaded_at": "2026-09-26",
            "file_name": "EOC_UnitedHealth.pdf",
            "storage_path": str(pdf),
            "sha256": "b" * 64,
            "status": "failed",
            "ingestion_state": {},
            "plan_name": data["plan_name"],
            "insurer": data["insurer"],
            "plan_year": "2026",
        }
    )
    result = apply_categories(policy["id"], data["categories"])
    assert result["item_count"] == 90
    assert result["totals"]["total"] == 90
    assert result["totals"]["required"] == 41
    assert result["totals"]["not_required"] == 41
    assert result["totals"]["conditional"] == 8
    # Without a real extract+judge run, imports stay pending / UNAVAILABLE (not HALLUCINATED).
    assert result["totals"]["pending_review"] == 90
    assert result["totals"]["hallucinated"] == 0
    assert result["fhir_valid"] is True
    assert all(item.get("judge_verdict") == "UNAVAILABLE" for item in get_repo().items_for(policy["id"]))
    summary = summarize_insurance_plan(result["insurance_plan"])
    assert summary["benefit_count"] == 90
    stored = repo.get_policy(policy["id"])
    assert stored["status"] == "draft"
    assert len((stored.get("fhir_insurance_plan") or {}).get("coverage", [{}])[0].get("benefit") or []) == 90
    assert len(repo.items_for(policy["id"])) == 90


def test_partial_extract_recovery_keeps_all_seeded_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    repo = get_repo()
    pdf = tmp_path / "partial.pdf"
    pdf.write_bytes(b"%PDF-1.4\ntrailer\n%%EOF\n" + b"y" * 200)
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "file_name": "partial.pdf",
            "storage_path": str(pdf),
            "sha256": "c" * 64,
            "status": "failed",
            "ingestion_state": {},
            "plan_name": "Test Plan",
            "insurer": "Test",
            "plan_year": "2026",
        }
    )
    dagger = "\u2021\u2021"
    assert coverage_from_line(f"Cardiac rehabilitation {dagger} $0", 1)["pa_required"] is True
    result = apply_categories(
        policy["id"],
        [
            {
                "service_label": "Cardiac rehabilitation",
                "pa_required": True,
                "pa_status": "required",
                "page": 1,
                "evidence_text": f"Cardiac rehabilitation {dagger} $0",
            },
            {
                "service_label": "Emergency care",
                "pa_required": False,
                "pa_status": "not_required",
                "page": 2,
                "evidence_text": "Emergency care $0 copay",
            },
        ],
    )
    assert result["item_count"] == 2
    assert result["fhir_valid"] is True
