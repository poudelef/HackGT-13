"""Gate 1 and Gate 2 routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.repository import get_repo, new_id
from app.review.present import present_item
from app.review.review import accept, apply_suggestion, edit, go_live, queue, reject

router = APIRouter(prefix="/policies")


@router.get("/{policy_id}/review-queue")
def review_queue(policy_id: str):
    from app.pipeline.cache import get, stage_key

    policy = get_repo().get_policy(policy_id)
    pages = get(stage_key(policy["sha256"], "clean")) if policy else None
    page_rows = (pages or {}).get("pages") if isinstance(pages, dict) else []
    text = {row["page"]: row["text"] for row in page_rows or []}
    items = []
    for item in queue(policy_id):
        data = item["data"]
        shown = present_item(item)
        items.append(
            {
                "id": item["id"],
                "item_key": item["item_key"],
                "item_type": item["item_type"],
                "seq": item["seq"],
                "page": item["page"],
                "page_text": text.get(item["page"], ""),
                "review_state": item["review_state"],
                "judge_verdict": item.get("judge_verdict"),
                "judge_reason": item.get("judge_reason"),
                "question_verdict": item.get("question_verdict"),
                "grounding": item.get("grounding"),
                "edited_by_human": bool(item.get("edited_by_human")),
                "suggestion": item.get("suggestion"),
                "review_note": item.get("review_note"),
                "summary": shown["title"],
                "title": shown["title"],
                "cost_share": shown["cost_share"],
                "pa_required": shown["pa_required"],
                "has_exception": shown["has_exception"],
                "exception": shown["exception"],
                "limits": shown["limits"],
                "evidence": shown["evidence"],
                "why": shown["why"],
                "criteria": shown["criteria"],
                "data": data,
                "original_data": item.get("original_data"),
            }
        )
    return {"items": items}


@router.post("/{policy_id}/items/{item_id}/accept")
def accept_item(policy_id: str, item_id: str, body: dict):
    return accept(policy_id, item_id, body["reviewer"], body.get("note"))


@router.post("/{policy_id}/items/{item_id}/edit")
def edit_item(policy_id: str, item_id: str, body: dict):
    run = get_repo().create_run(policy_id, f"edit-{new_id()[:8]}")
    try:
        return edit(policy_id, item_id, body["reviewer"], body.get("data") or {}, body.get("note"), run["id"])
    finally:
        get_repo().finish_run(run["id"], "complete")


@router.post("/{policy_id}/items/{item_id}/reject")
def reject_item(policy_id: str, item_id: str, body: dict):
    return reject(policy_id, item_id, body["reviewer"], body.get("note") or "")


@router.post("/{policy_id}/items/{item_id}/apply-suggestion")
def suggestion(policy_id: str, item_id: str, body: dict):
    return apply_suggestion(policy_id, item_id, body["reviewer"])


@router.post("/{policy_id}/go-live")
def live(policy_id: str, body: dict):
    return go_live(policy_id, body["reviewer"])


@router.post("/{policy_id}/blocks/{block_id}/go-live")
def block_live(policy_id: str, block_id: str, body: dict):
    return go_live(policy_id, body["reviewer"], block_id=block_id)
