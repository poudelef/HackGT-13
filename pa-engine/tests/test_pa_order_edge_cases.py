"""Edge cases: next-line PA markers on any payer EOC, and order-scoped patient criteria.

These tests must fail if we undercount markers, invent PA from junk fragments,
or attach the whole benefit chart to a single patient order.
"""

from __future__ import annotations

from app.check import coverage_gate, service as check_service
from app.ingest.coverage_lines import coverage_from_line
from app.ingest.pa_markers import annotate_item_from_pages, line_pa_status, windows_by_service_line
from app.repository import get_repo, new_id

DAGGER = "\u2020"
EM = "\u2014"


def test_next_line_dagger_works_for_generic_plan_not_just_uhc():
    """Any EOC that puts em-dash daggers on the following line must mark that service required."""
    page_text = (
        "Acme Health PPO Benefits Chart\n"
        "Outpatient MRI of the lumbar spine $0 copayment for each Not covered out-of-\n"
        f"network.{EM}{DAGGER}{DAGGER}\n"
        "Annual wellness visit $0 copayment\n"
        "Emergency care $0 copayment No prior authorization\n"
    )
    rows = windows_by_service_line(page_text)
    mri = next(r for r in rows if "MRI" in r["service_line"] or "lumbar" in r["service_line"].lower())
    assert mri["pa_status"] == "required"
    wellness = next(r for r in rows if "Annual wellness" in r["service_line"])
    assert wellness["pa_status"] == "not_required"


def test_coverage_from_line_window_catches_next_line_marker():
    line = "Cardiac rehabilitation services $0 copayment for each Not covered out-of-"
    window = f"{line}\nvisit.{EM}{DAGGER}{DAGGER}"
    row = coverage_from_line(line, 64, window=window)
    assert row["pa_required"] is True
    assert row["pa_status"] == "required"
    alone = coverage_from_line(line, 64)
    assert alone["pa_required"] is False


def test_merge_uncovered_window_marker_via_windows_helper():
    page_lines = [
        "Pulmonary rehabilitation services $0 copayment for each Not covered out-of-",
        f"visit.{EM}{DAGGER}{DAGGER}",
    ]
    win = windows_by_service_line("\n".join(page_lines))
    pulmonary = next(r for r in win if "Pulmonary" in r["service_line"])
    assert pulmonary["pa_required"] is True
    row = coverage_from_line(pulmonary["service_line"], 70, window=pulmonary["window"])
    assert row["pa_required"] is True


def test_annotate_does_not_mark_unrelated_service_from_dagger_elsewhere():
    pages = [
        {
            "page": 10,
            "text": (
                "Emergency care $0 copayment\n"
                f"Cardiac rehabilitation services visit.{EM}{DAGGER}{DAGGER}\n"
            ),
        }
    ]
    patch = annotate_item_from_pages(
        {"service_label": "Emergency care", "page": 10, "data": {}},
        pages,
    )
    assert patch is None or patch.get("pa_status") == "not_required" or not patch.get("pa_required")


def test_synthetic_chart_required_count_must_match_markers():
    """Fixture page with exactly 3 dagger services -- undercount or overcount fails."""
    dagger_services = [
        "Outpatient surgery at ambulatory surgical center",
        "Skilled nursing facility (SNF) care",
        "Home health agency care",
    ]
    plain = ["Annual wellness visit", "Emergency care"]
    lines = []
    for name in dagger_services:
        lines.append(f"{name} $0 copayment for each Not covered out-of-")
        lines.append(f"network.{EM}{DAGGER}{DAGGER}")
    for name in plain:
        lines.append(f"{name} $0 copayment")
    text = "\n".join(lines)
    required = [r for r in windows_by_service_line(text) if r["pa_status"] == "required"]
    labels = {r["service_line"].split("$")[0].strip() for r in required}
    for name in dagger_services:
        assert any(name in label for label in labels), f"missing marker for {name}"
    for name in plain:
        assert all(name not in r["service_line"] for r in required)


def test_order_for_one_service_does_not_attach_entire_eoc_chart(tmp_path, monkeypatch):
    """Patient PA must only get criteria for the ordered service, not all required EOC rows."""
    monkeypatch.setenv("INSURER_DELAY_SECONDS", "0")
    repo = get_repo()
    policy_id = new_id()
    sha = new_id().replace("-", "") + new_id().replace("-", "")
    repo._insert_raw(
        "policies",
        {
            "id": policy_id,
            "sha256": sha[:64],
            "file_name": "generic-eoc.pdf",
            "storage_path": str(tmp_path / "x.pdf"),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "source_url": "https://example.test/eoc.pdf",
            "status": "live",
            "insurer": "Generic Mutual",
            "plan_name": "Sample PPO",
            "plan_year": "2026",
        },
    )
    for label, required, codes in [
        ("MRI lumbar spine without contrast", True, ["72148"]),
        ("Cardiac rehabilitation services", True, []),
        ("Annual wellness visit", False, []),
        ("Skilled nursing facility (SNF) care", True, []),
    ]:
        repo.insert_item(
            {
                "id": new_id(),
                "policy_id": policy_id,
                "item_type": "coverage",
                "item_key": label.lower().replace(" ", "_")[:40],
                "seq": 1,
                "service_label": label,
                "service_codes": codes,
                "data": {
                    "service_label": label,
                    "pa_required": required,
                    "pa_status": "required" if required else "not_required",
                    "page": 50,
                    "evidence_text": label,
                },
                "original_data": {},
                "page": 50,
                "grounding": {"passed": True, "failures": []},
                "judge_verdict": "ACCURATE",
                "judge_reason": "test",
                "review_state": "accepted",
                "edited_by_human": True,
            }
        )
    patient_id, provider_id = new_id(), new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "Jane Sample", "dob": "1972-03-14", "member_id": "SAMP-1", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr Rivera", "specialty": "ortho"})
    view = check_service.check(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Generic Mutual",
            "plan_name": "Sample PPO",
            "plan_year": "2026",
            "order_text": "MRI lumbar spine without contrast",
            "service_code": "72148",
        }
    )
    assert view["status"] in {"needs_info", "ready_for_review", "checking"}
    assert view["coverage"] and view["coverage"]["pa_required"] is True
    assert view["total_count"] >= 1
    assert view["total_count"] <= 3
    joined = " ".join(c["requirement_text"] for c in view["criteria"]).lower()
    assert "mri" in joined or "lumbar" in joined or "medical necessity" in joined
    assert "cardiac rehabilitation" not in joined
    assert "skilled nursing" not in joined


def test_not_required_coverage_stops_without_questionnaires(tmp_path, monkeypatch):
    monkeypatch.setenv("INSURER_DELAY_SECONDS", "0")
    repo = get_repo()
    policy_id = new_id()
    sha = new_id().replace("-", "") + new_id().replace("-", "")
    repo._insert_raw(
        "policies",
        {
            "id": policy_id,
            "sha256": sha[:64],
            "file_name": "wellness-eoc.pdf",
            "storage_path": str(tmp_path / "w.pdf"),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "source_url": "https://example.test/w.pdf",
            "status": "live",
            "insurer": "Generic Mutual",
            "plan_name": "Sample PPO",
            "plan_year": "2026",
        },
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy_id,
            "item_type": "coverage",
            "item_key": "annual_wellness_visit",
            "seq": 1,
            "service_label": "Annual wellness visit",
            "service_codes": [],
            "data": {
                "service_label": "Annual wellness visit",
                "pa_required": False,
                "pa_status": "not_required",
                "page": 60,
                "evidence_text": "Annual wellness visit",
            },
            "original_data": {},
            "page": 60,
            "grounding": {"passed": True, "failures": []},
            "judge_verdict": "ACCURATE",
            "judge_reason": "test",
            "review_state": "accepted",
            "edited_by_human": True,
        }
    )
    patient_id, provider_id = new_id(), new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "Pat Wellness", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr PCP", "specialty": "primary care"})
    view = check_service.check(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Generic Mutual",
            "plan_name": "Sample PPO",
            "plan_year": "2026",
            "order_text": "Annual wellness visit",
            "service_code": None,
        }
    )
    assert view["status"] == "not_required"
    assert view["total_count"] == 0
    assert view["criteria"] == []


def test_coverage_gate_picks_best_label_among_same_code():
    items = [
        {
            "id": "1",
            "policy_id": "p",
            "service_label": "Outpatient diagnostic tests - X-rays",
            "service_codes": ["72148"],
            "data": {"pa_required": True, "pa_status": "required"},
            "page": 1,
        },
        {
            "id": "2",
            "policy_id": "p",
            "service_label": "MRI lumbar spine without contrast",
            "service_codes": ["72148"],
            "data": {"pa_required": True, "pa_status": "required"},
            "page": 2,
        },
    ]
    best = coverage_gate._best_label_match(items, "MRI lumbar spine without contrast")
    assert best is not None
    assert "MRI" in best["service_label"]


def test_line_pa_status_conditional_words_not_hard_required():
    status, _ = line_pa_status("Ambulance services. Referral may be required for non-emergency only.")
    assert status == "conditional"
