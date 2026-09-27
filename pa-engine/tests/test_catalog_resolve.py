"""Report wording -> live catalog label, and the OCR/code cleanup that feeds it.

These must fail if we prefill Order Desk with a service the catalog does not have,
or if an accession number is read as a billing code.
"""

from __future__ import annotations

from app.ingest.catalog_resolve import resolveOrderToCatalog
from app.ingest.report_extract import _clean_ocr, _find_codes, _find_service
from app.repository import get_repo, new_id

STAMP = "SAMPLE DOCUMENT"


def _seed_plan(tmp_path, insurer: str, plan_name: str, rows: list[tuple[str, list[str]]]) -> str:
    repo = get_repo()
    policy_id = new_id()
    sha = (new_id() + new_id()).replace("-", "")
    repo._insert_raw(
        "policies",
        {
            "id": policy_id,
            "sha256": sha[:64],
            "file_name": f"{plan_name}.pdf",
            "storage_path": str(tmp_path / "x.pdf"),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "source_url": "https://example.test/eoc.pdf",
            "status": "live",
            "insurer": insurer,
            "plan_name": plan_name,
            "plan_year": "2026",
        },
    )
    for seq, (label, codes) in enumerate(rows, start=1):
        repo.insert_item(
            {
                "id": new_id(),
                "policy_id": policy_id,
                "item_type": "coverage",
                "item_key": f"{plan_name}-{seq}",
                "seq": seq,
                "service_label": label,
                "service_codes": codes,
                "data": {"service_label": label, "pa_required": True, "pa_status": "required", "page": 12},
                "original_data": {},
                "page": 12,
                "grounding": {"passed": True, "failures": []},
                "judge_verdict": "ACCURATE",
                "judge_reason": "test",
                "review_state": "accepted",
            }
        )
    return policy_id


def test_report_wording_resolves_to_the_catalog_label_and_plan(tmp_path):
    _seed_plan(
        tmp_path,
        "Sample Mutual",
        "Open Access PPO",
        [("Thoracic ultrasonography survey without sedation", ["11111"]), ("Annual wellness visit", [])],
    )
    resolved = resolveOrderToCatalog("ultrasonography survey of the thoracic wall")
    assert resolved["status"] == "matched"
    assert resolved["order_text"] == "Thoracic ultrasonography survey without sedation"
    assert resolved["service_code"] == "11111"
    assert resolved["insurer"] == "Sample Mutual"
    assert resolved["plan_name"] == "Open Access PPO"
    assert resolved["plan_year"] == "2026"


def test_a_code_shared_by_two_plans_leaves_the_plan_unset(tmp_path):
    _seed_plan(tmp_path, "First Mutual", "Value HMO", [("Cranial venography mapping", ["22222"])])
    _seed_plan(tmp_path, "Second Mutual", "Choice PPO", [("Outpatient diagnostic tests - vascular", ["22222"])])
    resolved = resolveOrderToCatalog("", "22222")
    assert resolved["status"] == "ambiguous"
    assert resolved["insurer"] is None
    assert resolved["service_code"] == "22222"
    assert len(resolved["candidates"]) >= 2


def test_a_wrong_code_falls_back_to_the_label_and_never_invents_a_service(tmp_path):
    _seed_plan(tmp_path, "Third Mutual", "Basic PPO", [("Pelvic densitometry panel", ["33333"])])
    resolved = resolveOrderToCatalog("densitometry panel of the pelvis", "99998")
    assert resolved["status"] == "matched"
    assert resolved["order_text"] == "Pelvic densitometry panel"
    assert resolved["service_code"] == "33333"
    assert resolveOrderToCatalog("zzz qqq wwww")["status"] == "none"


def test_watermark_letters_are_stripped_only_when_the_stamp_is_proven():
    stamped = "\n".join(
        [
            f"{STAMP} - SYNTHETIC DATA",
            "L",
            "E",
            "A",
            "M",
            "R",
            "Impression: spinal stenosis suspected, MMRI of the lumbar spine is recommended. E",
            "P",
            "findings are asRsociated with degenerative change",
        ]
    )
    cleaned = _clean_ocr(stamped)
    assert "MRI of the lumbar spine" in cleaned
    assert "MMRI" not in cleaned
    assert "associated" in cleaned
    assert "\nL\n" not in f"\n{cleaned}\n"
    plain = "Vitamin D level checked.\nMMRI of the lumbar spine is recommended."
    assert _clean_ocr(plain) == plain


def test_recommended_service_wins_over_the_completed_exam_and_ids_are_not_codes():
    text = (
        "Exam: XR Lumbar Spine, 4 views Accession #: SAMP-IMG-77341\n"
        "Member ID: IMP-4471209\n"
        "Impression: MRI of the lumbar spine is recommended for further evaluation.\n"
    )
    assert _find_service(text) == "MRI of the lumbar spine"
    assert "77341" not in _find_codes(text)
    ordered = "Ordered: CT abdomen with contrast\nCPT: 74160\nExam: XR chest\n"
    assert _find_service(ordered) == "CT abdomen with contrast"
    assert "74160" in _find_codes(ordered)
