"""Edge-case coverage for constitution requirements.

On failure, dump episodic memory for the subject so the next fix is guided by the log (18).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from app.errors import ApiError
from app.ingest.upload_validation import require_text_layer, validate_bytes
from app.pipeline import cache as artifact_cache
from app.pipeline.episodes import EpisodeRecorder
from app.pipeline.progress import BENEFIT_STEPS, CLINICAL_STEPS, current_step_label, ingestion_steps
from app.repository import get_repo, new_id


TERMINAL = {"completed", "failed", "skipped", "cache_hit"}


def _pdf(tag: bytes = b"edge") -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + tag * 40


def dump_episodes(subject_type: str, subject_id: str) -> str:
    rows = get_repo().episodes_for(subject_type, subject_id)
    if not rows:
        return f"(no episodes for {subject_type}/{subject_id})"
    lines = []
    for row in rows:
        lines.append(
            f"#{row['seq']} {row['actor']} {row['stage']} {row['status']}: {row['summary']}"
        )
    return "\n".join(lines)


def assert_with_episodes(condition: bool, subject_type: str, subject_id: str, message: str) -> None:
    if not condition:
        pytest.fail(f"{message}\n\nEpisodic memory:\n{dump_episodes(subject_type, subject_id)}")


def _seed_policy(tmp_path: Path, *, status: str, role: str, tag: bytes, name: str = "doc.pdf") -> dict:
    data = _pdf(tag)
    digest = hashlib.sha256(data).hexdigest()
    path = tmp_path / f"{digest}.pdf"
    path.write_bytes(data)
    row = {
        "id": new_id(),
        "document_role": role,
        "source_kind": "published",
        "source_url": "https://example.test/doc.pdf",
        "downloaded_at": "2026-09-26",
        "file_name": name,
        "storage_path": str(path),
        "sha256": digest,
        "status": status,
        "ingestion_state": {},
        "insurer": "Example Health Plan",
        "plan_name": "Example PPO",
        "plan_year": "2026",
        "identity_evidence": {},
        "sections": {},
        "validation_report": {},
    }
    return get_repo().create_policy(row)


# --- E1 / E2 episodic memory ---


def test_episode_step_writes_started_then_completed():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())
    value = recorder.step("pages", "Reading pages", lambda: {"pages": [1], "detail": {"pages": 1}}, done=lambda v: "Read 1 page")
    assert value["pages"] == [1]
    rows = get_repo().episodes_for("policy", subject)
    assert_with_episodes(len(rows) == 2, "policy", subject, "Expected started + completed")
    assert_with_episodes(rows[0]["status"] == "started", "policy", subject, "First row must be started")
    assert_with_episodes(rows[1]["status"] == "completed", "policy", subject, "Second row must be completed")
    assert_with_episodes(rows[1]["seq"] > rows[0]["seq"], "policy", subject, "seq must increase")


def test_episode_step_records_failed_and_reraises():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())

    def boom():
        raise RuntimeError("page read failed")

    with pytest.raises(RuntimeError, match="page read failed"):
        recorder.step("pages", "Reading pages", boom)
    rows = get_repo().episodes_for("policy", subject)
    assert_with_episodes(len(rows) == 2, "policy", subject, "Failed step needs started + failed")
    assert_with_episodes(rows[0]["status"] == "started", "policy", subject, "started missing")
    assert_with_episodes(rows[1]["status"] == "failed", "policy", subject, "failed terminal missing")
    assert "page read failed" in rows[1]["summary"]


def test_episode_step_marks_cache_hit_terminal():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())
    recorder.step("clean", "Cleaning", lambda: {"cache_hit": True, "fingerprint": "x"})
    rows = get_repo().episodes_for("policy", subject)
    assert_with_episodes(rows[-1]["status"] == "cache_hit", "policy", subject, "cache_hit status required")


def test_episodes_are_append_only_no_update_path():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())
    first = recorder.record("upload", "Received document")
    before = dump_episodes("policy", subject)
    # There is no update API; inserting another episode must not rewrite the first.
    recorder.record("pages", "Reading pages")
    again = get_repo().episodes_for("policy", subject)
    first_again = next(row for row in again if row["id"] == first["id"])
    assert first_again["summary"] == "Received document"
    assert first_again["status"] == "completed"
    assert before.splitlines()[0] in dump_episodes("policy", subject)


def test_every_record_has_started_and_one_terminal_per_step_no():
    subject = new_id()
    recorder = EpisodeRecorder("policy", subject, new_id())
    recorder.record("upload", "up")
    recorder.step("pages", "p", lambda: {"ok": True})
    rows = get_repo().episodes_for("policy", subject)
    by_step: dict[int, list] = {}
    for row in rows:
        by_step.setdefault(int(row["step_no"]), []).append(row)
    for step_no, group in by_step.items():
        statuses = [row["status"] for row in group]
        assert_with_episodes(
            statuses[0] == "started",
            "policy",
            subject,
            f"step {step_no} must begin with started",
        )
        terminals = [s for s in statuses[1:] if s in TERMINAL]
        assert_with_episodes(
            len(terminals) == 1,
            "policy",
            subject,
            f"step {step_no} must have exactly one terminal status",
        )


# --- K1 fingerprint cache ---


def test_fingerprint_cache_hit_writes_cache_hit_episode(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="draft", role="benefit_summary", tag=b"same-bytes")
    data = Path(policy["storage_path"]).read_bytes()
    body = pipeline_runner.ingest_upload(data, "other-name.pdf", "benefit_summary", None, None)
    assert body["cached"] is True
    assert body["id"] == policy["id"]
    episodes = get_repo().episodes_for("policy", policy["id"])
    cache_rows = [row for row in episodes if row["stage"] == "cache"]
    assert_with_episodes(bool(cache_rows), "policy", policy["id"], "cache stage episode missing")
    assert_with_episodes(
        any(row["status"] == "cache_hit" for row in cache_rows),
        "policy",
        policy["id"],
        "cache_hit terminal missing",
    )


def test_fingerprint_cache_miss_on_different_bytes(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    first = _seed_policy(tmp_path, status="draft", role="clinical_policy", tag=b"alpha")
    other = _pdf(b"beta-different")

    def fake_run(policy_id: str):
        get_repo().update_policy(policy_id, {"status": "draft"}, actor="engine")
        return {"id": policy_id, "cached": False, "status": "draft"}

    monkeypatch.setattr(pipeline_runner, "run", fake_run)
    body = pipeline_runner.ingest_upload(other, "beta.pdf", "clinical_policy", None, None)
    assert body["cached"] is False
    assert body["id"] != first["id"]
    assert body["status"] == "ingesting" or body.get("accepted") is True


def test_fingerprint_failed_policy_restarts_without_claiming_cache_hit(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="failed", role="clinical_policy", tag=b"failed-doc")
    data = Path(policy["storage_path"]).read_bytes()
    started = {"n": 0}

    def fake_run(policy_id: str):
        started["n"] += 1
        get_repo().update_policy(policy_id, {"status": "draft"}, actor="engine")
        return {"id": policy_id, "cached": False}

    monkeypatch.setattr(pipeline_runner, "run", fake_run)
    body = pipeline_runner.ingest_upload(data, "retry.pdf", "clinical_policy", None, None)
    assert body.get("cached") is not True
    assert body["id"] == policy["id"]
    deadline = time.time() + 2
    while time.time() < deadline and started["n"] == 0:
        time.sleep(0.02)
    assert started["n"] == 1


def test_fingerprint_ingesting_policy_does_not_start_second_thread(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="ingesting", role="clinical_policy", tag=b"inflight")
    data = Path(policy["storage_path"]).read_bytes()
    calls = {"n": 0}

    def fake_run(policy_id: str):
        calls["n"] += 1
        time.sleep(0.3)
        get_repo().update_policy(policy_id, {"status": "draft"}, actor="engine")
        return {"id": policy_id}

    monkeypatch.setattr(pipeline_runner, "run", fake_run)
    first = pipeline_runner.ingest_upload(data, "a.pdf", "clinical_policy", None, None)
    second = pipeline_runner.ingest_upload(data, "b.pdf", "clinical_policy", None, None)
    assert first["id"] == second["id"] == policy["id"]
    deadline = time.time() + 2
    while time.time() < deadline and get_repo().get_policy(policy["id"])["status"] == "ingesting":
        time.sleep(0.05)
    assert calls["n"] == 1


def test_unknown_document_role_is_rejected(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    with pytest.raises(ApiError) as caught:
        pipeline_runner.ingest_upload(_pdf(b"role"), "x.pdf", "pa_form", None, None)
    assert caught.value.code == "INVALID_PDF"


# --- async ingest + progress checklist ---


def test_async_ingest_returns_before_background_finishes(tmp_path, monkeypatch):
    from app.pipeline import pipeline_runner

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    def slow(policy_id: str):
        time.sleep(0.35)
        get_repo().update_policy(policy_id, {"status": "draft"}, actor="engine")
        return {"id": policy_id}

    monkeypatch.setattr(pipeline_runner, "run", slow)
    t0 = time.perf_counter()
    body = pipeline_runner.ingest_upload(_pdf(b"async2"), "async2.pdf", "benefit_summary", None, None)
    assert time.perf_counter() - t0 < 0.25
    assert body["accepted"] is True
    assert body["status"] == "ingesting"


def test_processing_checklist_labels_match_overview_for_benefit_and_clinical(tmp_path):
    benefit = _seed_policy(tmp_path, status="ingesting", role="benefit_summary", tag=b"benefit-labels")
    clinical = _seed_policy(tmp_path, status="ingesting", role="clinical_policy", tag=b"clinical-labels")
    benefit_labels = [step["label"] for step in ingestion_steps(benefit["id"])]
    clinical_labels = [step["label"] for step in ingestion_steps(clinical["id"])]
    assert benefit_labels == [label for _, label in BENEFIT_STEPS]
    assert clinical_labels == [label for _, label in CLINICAL_STEPS]
    assert "Extracting pages" in benefit_labels
    assert "Independent accuracy review" in benefit_labels
    assert "Building FHIR output" in benefit_labels


def test_processing_checklist_marks_active_step_from_started_episode(tmp_path):
    policy = _seed_policy(tmp_path, status="ingesting", role="benefit_summary", tag=b"active-step")
    recorder = EpisodeRecorder("policy", policy["id"], new_id())
    recorder.record("upload", "Queued", status="completed")
    # Leave pages mid-flight.
    recorder._write("pages", "started", "Extracting pages")
    steps = ingestion_steps(policy["id"])
    active = [step for step in steps if step["status"] == "active"]
    assert_with_episodes(len(active) == 1, "policy", policy["id"], "Exactly one active step expected")
    assert active[0]["label"] == "Extracting pages"
    assert current_step_label(policy["id"]) == "Extracting pages"


def test_processing_checklist_advances_after_pages_complete(tmp_path):
    policy = _seed_policy(tmp_path, status="ingesting", role="benefit_summary", tag=b"advance-step")
    recorder = EpisodeRecorder("policy", policy["id"], new_id())
    for stage, summary in (("upload", "Queued"), ("pages", "Extracting pages"), ("identity", "Identifying plan")):
        recorder.record(stage, summary, status="completed")
    recorder._write("precheck", "started", "Analyzing document format")
    label = current_step_label(policy["id"])
    assert_with_episodes(label == "Analyzing document format", "policy", policy["id"], f"got {label}")


# --- delete ---


def test_delete_policy_removes_episodes_and_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="draft", role="clinical_policy", tag=b"delete-me")
    path = Path(policy["storage_path"])
    recorder = EpisodeRecorder("policy", policy["id"], new_id())
    recorder.record("upload", "Received")
    artifact_cache.put(
        artifact_cache.stage_key(policy["sha256"], "pages"),
        "stage",
        policy["sha256"],
        [{"page": 1, "text": "x"}],
        None,
    )
    result = get_repo().delete_policy(policy["id"])
    assert result["deleted"] is True
    assert get_repo().get_policy(policy["id"]) is None
    assert get_repo().episodes_for("policy", policy["id"]) == []
    assert not path.exists()
    assert artifact_cache.get(artifact_cache.stage_key(policy["sha256"], "pages")) is None


def test_delete_missing_policy_raises():
    with pytest.raises(KeyError):
        get_repo().delete_policy(new_id())


def test_delete_paused_eoc_with_no_items(tmp_path, monkeypatch):
    """Paused uploads (e.g. mis-roled EOC.pdf) must delete even with zero items."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="paused", role="clinical_policy", tag=b"eoc-paused", name="EOC.pdf")
    path = Path(policy["storage_path"])
    assert path.exists()
    result = get_repo().delete_policy(policy["id"])
    assert result["deleted"] is True
    assert result["file_name"] == "EOC.pdf"
    assert get_repo().get_policy(policy["id"]) is None
    assert not path.exists()


def test_delete_policy_clears_pa_criteria_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    policy = _seed_policy(tmp_path, status="live", role="drug_criteria", tag=b"drug-ref")
    patient_id = new_id()
    provider_id = new_id()
    repo = get_repo()
    repo.upsert_patient({"id": patient_id, "full_name": "Test Patient", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr Test", "specialty": "spine"})
    pa = repo.create_pa(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Example Health Plan",
            "plan_name": "Example PPO",
            "plan_year": "2026",
            "order_text": "Northpine",
            "status": "needs_info",
            "criteria_policy_id": policy["id"],
            "readiness": 0,
        }
    )
    result = repo.delete_policy(policy["id"])
    assert result["deleted"] is True
    refreshed = repo.get_pa(pa["id"])
    assert refreshed is not None
    assert refreshed.get("criteria_policy_id") is None


# --- PA missing id / list ---


def test_missing_pa_returns_404_and_list_excludes_it():
    from app.check import service

    missing = new_id()
    with pytest.raises(ApiError) as caught:
        service.present(missing)
    assert caught.value.status == 404
    assert caught.value.code == "POLICY_NOT_FOUND"
    listed = service.list_recent()
    assert "requests" in listed
    assert all(row["id"] != missing for row in listed["requests"])


def test_list_recent_includes_seeded_pa():
    from app.check import service

    repo = get_repo()
    patient_id = new_id()
    provider_id = new_id()
    repo.upsert_patient({"id": patient_id, "full_name": "List Patient", "synthetic": 1})
    repo.upsert_provider({"id": provider_id, "full_name": "Dr List", "specialty": "spine"})
    pa = repo.create_pa(
        {
            "patient_id": patient_id,
            "ordering_provider_id": provider_id,
            "insurer": "Example Health Plan",
            "plan_name": "Example PPO",
            "plan_year": "2026",
            "order_text": "MRI lumbar",
            "status": "needs_info",
            "readiness": 0.5,
        }
    )
    listed = service.list_recent()
    ids = [row["id"] for row in listed["requests"]]
    assert pa["id"] in ids
    row = next(r for r in listed["requests"] if r["id"] == pa["id"])
    assert row["patient"]["full_name"] == "List Patient"
    assert row["status"] == "needs_info"


# --- upload validation edge cases ---


def test_upload_validation_edge_cases():
    with pytest.raises(ApiError) as empty:
        validate_bytes(b"%PDF")
    assert empty.value.code == "INVALID_PDF"
    with pytest.raises(ApiError) as huge:
        validate_bytes(b"%PDF" + b"x" * (20_000_001))
    assert huge.value.code == "INVALID_PDF"
    validate_bytes(_pdf(b"ok-size"))
    with pytest.raises(ApiError) as scanned:
        require_text_layer([{"page": 1, "text": "   "}])
    assert scanned.value.code == "NO_TEXT_LAYER"
    require_text_layer([{"page": 1, "text": "Coverage criteria"}])


# --- human lock edge ---


def test_engine_cannot_overwrite_human_locked_item_fields():
    repo = get_repo()
    policy = repo.create_policy(
        {
            "document_role": "clinical_policy",
            "file_name": "lock.pdf",
            "storage_path": "/tmp/lock.pdf",
            "sha256": new_id(),
            "status": "draft",
        }
    )
    item = repo.insert_item(
        {
            "policy_id": policy["id"],
            "item_type": "rule",
            "item_key": "pt_weeks",
            "seq": 1,
            "page": 1,
            "data": {"requirement_text": "6 weeks"},
            "original_data": {"requirement_text": "6 weeks"},
            "review_state": "edited",
            "edited_by_human": True,
        }
    )
    tried = repo.write_item(item["id"], {"data": {"requirement_text": "4 weeks"}}, actor="engine")
    assert tried["lock_preserved"] is True
    assert tried["data"]["requirement_text"] == "6 weeks"
    human = repo.write_item(item["id"], {"data": {"requirement_text": "8 weeks"}}, actor="Suman")
    assert human["data"]["requirement_text"] == "8 weeks"
