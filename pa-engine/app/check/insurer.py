"""Insurer review actions. Humans approve or ask for evidence. Never denies (G1)."""

from __future__ import annotations

import threading
import time

from app.config import settings
from app.pipeline.episodes import EpisodeRecorder
from app.repository import get_repo, new_id

ALLOWED = {"info_requested", "approved"}


def schedule(pa_id: str) -> None:
    """Move a submitted packet into the insurer queue. Humans decide next (no auto-approve)."""

    def run() -> None:
        delay = settings.insurer_delay_seconds
        if delay > 0:
            time.sleep(delay)
        _transition(pa_id, "in_review", "in_review", "Waiting for insurer review.")

    if settings.insurer_delay_seconds <= 0:
        run()
        return
    threading.Thread(target=run, daemon=True).start()


def settle(pa_id: str) -> None:
    """Test helper: auto ask-once or approve. Production uses schedule + human actions."""
    delay = settings.insurer_delay_seconds
    if delay > 0:
        time.sleep(delay)
    _transition(pa_id, "in_review", "in_review", "The request is in review.")
    if delay > 0:
        time.sleep(delay)
    repo = get_repo()
    already_asked = any(c.get("origin") == "insurer_request" for c in repo.criteria_for(pa_id))
    if settings.insurer_request_info and not already_asked:
        request_info(pa_id)
        return
    approve(pa_id)


def approve(pa_id: str, *, note: str | None = None) -> None:
    _transition(pa_id, "approved", "approved", note or "Approved by the insurer.")


def request_info(pa_id: str, *, note: str | None = None) -> None:
    """Ask for more clinical documentation. Adds an insurer_request criterion."""
    repo = get_repo()
    pa = repo.get_pa(pa_id)
    if pa is None or pa["status"] == "approved":
        return
    if pa["status"] not in {"submitted", "in_review", "info_requested"}:
        return
    existing = repo.criteria_for(pa_id)
    open_ask = any(
        c.get("origin") == "insurer_request" and c.get("status") != "met" for c in existing
    )
    if open_ask:
        _transition(
            pa_id,
            "info_requested",
            "info_requested",
            note or "More information was requested. Upload evidence and recheck.",
        )
        return
    key = f"insurer_request_{new_id()[:8]}"
    criterion_id = new_id()
    seq = (max((c.get("seq") or 0) for c in existing) + 1) if existing else 1
    requirement = (note or "").strip() or "Provide additional clinical documentation supporting medical necessity."
    repo._insert_raw(
        "pa_criteria",
        {
            "id": criterion_id,
            "pa_request_id": pa_id,
            "policy_item_id": None,
            "seq": seq,
            "criterion_key": key,
            "requirement_text": requirement,
            "criterion_type": "clinical_note",
            "policy_page": 0,
            "origin": "insurer_request",
            "pass_condition": {
                "all": [
                    {
                        "q": "additional_evidence",
                        "op": "eq",
                        "value": True,
                        "missing": "Supporting clinical documentation has not been confirmed.",
                    }
                ]
            },
            "status": "missing",
            "status_reason": "The insurer asked for more evidence.",
            "evidence_text": None,
            "likely_owner_provider_id": pa.get("ordering_provider_id"),
            "likely_owner_reason": "Ordering clinician",
            "verified_by": None,
            "verified_at": None,
        },
    )
    repo._insert_raw(
        "pa_answers",
        {
            "id": new_id(),
            "pa_criterion_id": criterion_id,
            "link_id": "additional_evidence",
            "seq": 1,
            "question_text": "Is supporting clinical documentation available in the chart?",
            "answer_type": "boolean",
            "enabled": 1,
            "value": None,
            "unit": None,
            "fill_method": "llm_quote",
            "evidence_text": None,
            "evidence_record_id": None,
            "review_state": "unanswered",
            "edited_by_human": 0,
            "rejected_ai_value": None,
            "reject_reason": None,
            "attestation": None,
            "answered_by": None,
            "answered_at": None,
        },
    )
    _transition(
        pa_id,
        "info_requested",
        "info_requested",
        note or "More information was requested. Upload evidence and recheck.",
    )


def _transition(pa_id: str, status: str, event: str, message: str) -> None:
    if status not in {"in_review", *ALLOWED}:
        raise RuntimeError("The insurer cannot produce that status.")
    repo = get_repo()
    current = repo.get_pa(pa_id)
    if current is None:
        return
    if current["status"] == "approved":
        return
    repo.update_pa(pa_id, {"status": status})
    recorder = EpisodeRecorder("pa_request", pa_id, None, actor="insurer")
    episode = recorder.record(status, message, actor="insurer")
    repo.add_event(pa_id, event, message, "insurer", episode["id"])
