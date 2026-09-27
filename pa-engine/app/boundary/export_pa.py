"""Isolate ClearPath PA state -> teammate OUTPUT JSON.

Internal statuses map at this edge only. G1: never emit denied.
"""

from __future__ import annotations

from typing import Any

from app.errors import ApiError
from app.repository import get_repo

# Internal -> teammate export status. No denied (G1).
EXPORT_STATUS = {
    "not_required": "no_pa_needed",
    "approved": "approved",
    "info_requested": "additional_info_requested",
    "submitted": "submitted",
    "in_review": "under_review",
    "draft": "draft",
    "matching": "draft",
    "checking": "questionnaire_pending",
    "needs_info": "questionnaire_pending",
    "ready_for_review": "questionnaire_pending",
}


def buildOutputForTeammate(pa_id: str) -> dict[str, Any]:
    repo = get_repo()
    pa = repo.get_pa(pa_id)
    if pa is None:
        raise ApiError("POLICY_NOT_FOUND", "No request with that id.", 404)

    events = repo.events_for(pa_id)
    history = []
    for event in events:
        history.append(
            {
                "status": EXPORT_STATUS.get(event.get("event_type"), str(event.get("event_type") or "")),
                "actor": event.get("actor") or "engine",
                "note": event.get("message"),
                "timestamp": event.get("created_at"),
            }
        )

    export_status = EXPORT_STATUS.get(pa["status"], pa["status"])
    decided_at = None
    reviewer_note = None
    if pa["status"] in {"approved", "not_required"}:
        for event in reversed(events):
            if event.get("event_type") in {"approved", "not_required"}:
                decided_at = event.get("created_at")
                reviewer_note = event.get("message")
                break
    elif pa["status"] == "info_requested":
        for event in reversed(events):
            if event.get("event_type") == "info_requested":
                decided_at = event.get("created_at")
                reviewer_note = event.get("message")
                break

    return {
        "patient_id": pa["patient_id"],
        "pa_request_id": pa["id"],
        "service_category": pa.get("service_category") or pa.get("order_text") or "",
        "status": export_status,
        "decided_at": decided_at,
        "reviewer_note": reviewer_note,
        "history": history,
    }
