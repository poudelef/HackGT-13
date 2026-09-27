"""Overview pipeline edge cases: pages -> order -> context -> memory -> extract -> judge -> gates -> insurer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.errors import ApiError
from app.ingest import cascade, precheck
from app.ingest.coverage_lines import coverage_from_line
from app.ingest.grounding import check as ground
from app.pipeline.context_builder import clean
from app.pipeline.episodes import EpisodeRecorder
from app.pipeline.working_memory import apply_updates, empty, remember_items, render
from app.repository import get_repo, new_id
from app.review.review import initial_state, queue
from app.check import insurer as fake_insurer


def _pdf(tag: bytes = b"pipe") -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + tag * 40


def dump_episodes(subject_type: str, subject_id: str) -> str:
    rows = get_repo().episodes_for(subject_type, subject_id)
    if not rows:
        return f"(no episodes for {subject_type}/{subject_id})"
    return "\n".join(f"#{r['seq']} {r['stage']} {r['status']}: {r['summary']}" for r in rows)


def assert_with_episodes(ok: bool, subject_type: str, subject_id: str, message: str) -> None:
    if not ok:
        pytest.fail(f"{message}\n\nEpisodic memory:\n{dump_episodes(subject_type, subject_id)}")


def test_context_builder_strips_repeated_headers_keeps_protected_auth_lines():
    pages = [
        {"page": 1, "text": "ACME PLAN 2026\nCardiac rehab needs prior authorization\nPage 1 of 3", "words": []},
        {"page": 2, "text": "ACME PLAN 2026\nAnnual wellness visit $0\nPage 2 of 3", "words": []},
        {"page": 3, "text": "ACME PLAN 2026\nMRI lumbar spine prior authorization required\nPage 3 of 3", "words": []},
    ]
    cleaned, report = clean(pages)
    assert report["removed_lines"] >= 1
    joined = "\n".join(p["text"] for p in cleaned)
    assert "prior authorization" in joined.lower()


def test_cascade_returns_pages_in_ascending_document_order():
    pages = [{"page": n, "text": f"Benefits chart authorization row {n} copay $0"} for n in range(1, 8)]
    hints = precheck.precheck(pages, "benefit_summary")
    sections = cascade.locate(pages, "benefit_summary", hints)
    nums = sections.get("pages") or []
    assert nums == sorted(nums), f"pages not sequential: {nums}"
    assert nums, "cascade located no pages"


def test_working_memory_carries_markers_only_when_grounded_on_page():
    dagger = "\u2021\u2021"
    memory = empty()
    pages = {10: f"The double dagger {dagger} means prior authorization is required."}
    updated = apply_updates(
        memory,
        {
            "markers": [
                {
                    "marker": dagger,
                    "meaning": "Prior authorization required",
                    "page": 10,
                    "evidence": f"{dagger} means prior authorization is required",
                },
                {"marker": "*", "meaning": "fake", "page": 10, "evidence": "not on the page at all"},
            ]
        },
        pages,
    )
    assert any(m.get("marker") == dagger for m in updated["markers"])
    assert not any(m.get("marker") == "*" for m in updated["markers"])
    remembered = remember_items(updated, ["cardiac_rehab"])
    blob = render(remembered)
    assert "items_found" in blob and "cardiac_rehab" in blob
    assert "CONTEXT ONLY" in blob


def test_grounding_and_initial_state_route_accurate_vs_hallucinated():
    dagger = "\u2021\u2021"
    page = f"Cardiac rehabilitation services {dagger} $0 copay per visit. Prior authorization required."
    good = {"evidence_text": f"Cardiac rehabilitation services {dagger} $0 copay per visit", "requirement_text": "", "codes": []}
    bad = {"evidence_text": "This quote was invented and is not on the page", "requirement_text": "", "codes": []}
    g_ok = ground(good, page)
    g_bad = ground(bad, page)
    assert g_ok["passed"] is True
    assert g_bad["passed"] is False
    assert initial_state(g_ok, "ACCURATE", None) == "auto_approved"
    assert initial_state(g_bad, "HALLUCINATED", None) == "pending_review"
    assert initial_state(g_ok, "VAGUE", None) == "pending_review"


def test_review_queue_orders_hallucinated_before_accurate():
    repo = get_repo()
    pdf = Path(repo.path).parent / f"{new_id()}.pdf"
    pdf.write_bytes(_pdf(b"qord"))
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "file_name": "qord.pdf",
            "storage_path": str(pdf),
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "status": "draft",
            "ingestion_state": {},
        }
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy["id"],
            "item_type": "coverage",
            "item_key": "good",
            "seq": 2,
            "service_label": "Wellness",
            "service_codes": [],
            "data": {"service_label": "Wellness", "pa_required": False, "evidence_text": "x", "page": 1},
            "original_data": {},
            "page": 1,
            "grounding": {"passed": True},
            "judge_verdict": "ACCURATE",
            "review_state": "auto_approved",
            "edited_by_human": False,
        }
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy["id"],
            "item_type": "coverage",
            "item_key": "bad",
            "seq": 1,
            "service_label": "Fake MRI",
            "service_codes": [],
            "data": {"service_label": "Fake MRI", "pa_required": True, "evidence_text": "y", "page": 1},
            "original_data": {},
            "page": 1,
            "grounding": {"passed": False},
            "judge_verdict": "HALLUCINATED",
            "review_state": "pending_review",
            "edited_by_human": False,
        }
    )
    ordered = queue(policy["id"])
    assert ordered[0]["judge_verdict"] == "HALLUCINATED"
    assert ordered[-1]["judge_verdict"] == "ACCURATE"


def test_any_insurer_dagger_marker_sets_pa_without_hardcoding_payer():
    dagger = "\u2021\u2021"
    row = coverage_from_line(f"Outpatient surgery {dagger} $0 copay", 88)
    assert row["pa_required"] is True
    assert row["marker_used"] == dagger


def test_episode_records_failed_extract_group_without_wiping_subject():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())
    recorder.record("extract", "Skipped group 3 after extract error: bad json", status="failed", group_no=3)
    rows = get_repo().episodes_for("policy", subject)
    assert_with_episodes(any(r["status"] == "failed" and r["stage"] == "extract" for r in rows), "policy", subject, "missing failed extract episode")


def test_reprocess_clears_unlocked_items_and_starts_background(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    repo = get_repo()
    pdf = tmp_path / "repro.pdf"
    pdf.write_bytes(_pdf(b"repro"))
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "file_name": "repro.pdf",
            "storage_path": str(pdf),
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "status": "draft",
            "ingestion_state": {},
            "fhir_insurance_plan": {"resourceType": "InsurancePlan", "coverage": []},
        }
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy["id"],
            "item_type": "coverage",
            "item_key": "seed",
            "seq": 1,
            "service_label": "Seeded",
            "service_codes": [],
            "data": {"service_label": "Seeded", "pa_required": True, "page": 1, "evidence_text": "Seeded"},
            "original_data": {},
            "page": 1,
            "grounding": {"passed": False},
            "judge_verdict": "UNAVAILABLE",
            "review_state": "pending_review",
            "edited_by_human": False,
        }
    )
    started = {"ok": False}

    def fake_start(pid):
        started["ok"] = True
        started["id"] = pid

    monkeypatch.setattr(pipeline_runner, "start_ingestion", fake_start)
    body = pipeline_runner.reprocess(policy["id"], full=True)
    assert body["accepted"] is True
    assert started["ok"] is True
    assert started["id"] == policy["id"]
    assert get_repo().items_for(policy["id"]) == []
    fresh = get_repo().get_policy(policy["id"])
    assert fresh["status"] == "ingesting"


def test_failed_reprocess_resumes_without_wipe(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    repo = get_repo()
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(_pdf(b"resume"))
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "benefit_summary",
            "source_kind": "published",
            "file_name": "resume.pdf",
            "storage_path": str(pdf),
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "status": "failed",
            "ingestion_state": {"group": 5, "groups": 42},
            "working_memory": {"items_found": ["Cardiac rehab"], "markers": [], "definitions": [], "open_item": None},
        }
    )
    started = {"ok": False}

    def fake_start(pid):
        started["ok"] = True

    monkeypatch.setattr(pipeline_runner, "start_ingestion", fake_start)
    body = pipeline_runner.reprocess(policy["id"])
    assert body["accepted"] is True
    assert started["ok"] is True
    fresh = get_repo().get_policy(policy["id"])
    assert fresh["status"] == "ingesting"
    assert (fresh.get("working_memory") or {}).get("items_found") == ["Cardiac rehab"]


def test_insurer_info_request_adds_criterion_never_denies(tmp_path, monkeypatch):
    monkeypatch.setenv("INSURER_DELAY_SECONDS", "0")
    monkeypatch.setenv("INSURER_REQUEST_INFO", "true")
    repo = get_repo()
    patient_id = new_id()
    provider_id = new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "Test", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr Test", "specialty": "spine"})
    pa = repo.create_pa(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Any Plan",
            "plan_name": "Any PPO",
            "plan_year": "2026",
            "order_text": "MRI lumbar",
            "status": "submitted",
            "readiness": 1.0,
        }
    )
    fake_insurer.settle(pa["id"])
    refreshed = repo.get_pa(pa["id"])
    assert refreshed["status"] == "info_requested"
    criteria = repo.criteria_for(pa["id"])
    assert any(c.get("origin") == "insurer_request" for c in criteria)
    answers = repo.answers_for(criteria[-1]["id"])
    assert answers and answers[0]["link_id"] == "additional_evidence"
    # Second settle after evidence must approve, not ask again.
    repo.update_pa(pa["id"], {"status": "submitted"})
    fake_insurer.settle(pa["id"])
    assert repo.get_pa(pa["id"])["status"] == "approved"


def test_doctor_evidence_recheck_scores_insurer_request(tmp_path, monkeypatch):
    from app.check import service as check_service
    from app.check.pass_eval import evaluate

    monkeypatch.setenv("INSURER_DELAY_SECONDS", "0")
    monkeypatch.setenv("INSURER_REQUEST_INFO", "true")
    repo = get_repo()
    patient_id = new_id()
    provider_id = new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "Chart Patient", "dob": "1980-01-15", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr Spine", "specialty": "spine"})
    # Patient chart / clinical note exists before questionnaires are scored.
    repo.insert_record(
        {
            "id": new_id(),
            "patient_id": patient_id,
            "resource_type": "DocumentReference",
            "record_kind": "note",
            "body": "MRI lumbar ordered. Conservative therapy documented for 6 weeks.",
            "start_date": "2026-01-10",
            "synthetic": True,
        }
    )
    pa = repo.create_pa(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Any",
            "plan_name": "PPO",
            "plan_year": "2026",
            "order_text": "MRI lumbar",
            "status": "submitted",
            "readiness": 1.0,
        }
    )
    fake_insurer.settle(pa["id"])
    assert repo.get_pa(pa["id"])["status"] == "info_requested"
    criterion = next(c for c in repo.criteria_for(pa["id"]) if c.get("origin") == "insurer_request")
    answer = repo.answers_for(criterion["id"])[0]
    # Doctor confirms evidence after upload.
    repo.write_answer(
        answer["id"],
        {
            "value": json.dumps(True),
            "review_state": "clinician_confirmed",
            "edited_by_human": True,
            "evidence_text": "Note uploaded 2026-01-10",
        },
        actor=provider_id,
    )
    judged = evaluate(criterion["pass_condition"], {"additional_evidence": {"value": True, "enabled": True}})
    assert judged["status"] == "met"
    view = check_service.recheck(pa["id"])
    refreshed = next(c for c in repo.criteria_for(pa["id"]) if c.get("origin") == "insurer_request")
    assert refreshed["status"] == "met"
    assert view["status"] in {"ready_for_review", "needs_info"}


def test_insurer_cannot_transition_to_denied():
    with pytest.raises(RuntimeError):
        fake_insurer._transition(new_id(), "denied", "denied", "no")  # type: ignore[arg-type]


def test_go_live_requires_human_decision_on_auto_approved(tmp_path, monkeypatch):
    from app.review.review import go_live

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    repo = get_repo()
    pdf = tmp_path / "live.pdf"
    pdf.write_bytes(_pdf(b"live"))
    policy = repo.create_policy(
        {
            "id": new_id(),
            "document_role": "clinical_policy",
            "source_kind": "fictional_fallback",
            "file_name": "live.pdf",
            "storage_path": str(pdf),
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "status": "draft",
            "ingestion_state": {},
            "validation_report": {"fhir": {"valid": True}, "questions": {"condition_coverage": 1}},
        }
    )
    repo.insert_item(
        {
            "id": new_id(),
            "policy_id": policy["id"],
            "item_type": "rule",
            "item_key": "age",
            "seq": 1,
            "service_label": "Age",
            "service_codes": [],
            "data": {
                "criterion_key": "age",
                "requirement_text": "18 or older",
                "criterion_type": "age",
                "policy_page": 1,
                "conditions": [],
                "questions": [{"link_id": "age_years", "text": "Age?", "answer_type": "quantity", "fill_method": "date_math", "covers": []}],
                "pass_condition": {"all": [{"gte": ["age_years", 18]}]},
                "evidence_text": "18 or older",
            },
            "original_data": {},
            "page": 1,
            "grounding": {"passed": True},
            "judge_verdict": "ACCURATE",
            "question_verdict": "complete",
            "review_state": "auto_approved",
            "edited_by_human": False,
        }
    )
    with pytest.raises(ApiError) as caught:
        go_live(policy["id"], "Suman")
    assert caught.value.status == 409
