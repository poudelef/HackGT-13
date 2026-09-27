"""Prior authorization routes. No business logic."""

from __future__ import annotations

from fastapi import APIRouter

from app.check import service

router = APIRouter(prefix="/pa")


@router.post("/check")
def check(body: dict):
    return service.check(body)


@router.get("")
def list_requests(queue: str | None = None):
    return service.list_recent(queue=queue)


@router.post("/{pa_id}/match")
def match(pa_id: str, body: dict):
    return service.choose_match(pa_id, body["item_id"])


@router.get("/{pa_id}")
def get_request(pa_id: str):
    return service.present(pa_id)

@router.post("/{pa_id}/recheck")
def recheck(pa_id: str):
    return service.recheck(pa_id)


@router.post("/{pa_id}/answers/{answer_id}/reject")
def reject(pa_id: str, answer_id: str, body: dict):
    service.reject_answer(pa_id, answer_id, body["provider_id"], body.get("reason") or "")
    return service.present(pa_id)


@router.post("/{pa_id}/answers/{answer_id}/enter")
def enter(pa_id: str, answer_id: str, body: dict):
    service.enter_answer(pa_id, answer_id, body)
    return service.present(pa_id)


@router.post("/{pa_id}/criteria/{criterion_id}/verify")
def verify(pa_id: str, criterion_id: str, body: dict):
    service.verify(pa_id, criterion_id, body["provider_id"])
    return service.present(pa_id)


@router.get("/{pa_id}/packet")
def packet(pa_id: str):
    return service.preview(pa_id)


@router.post("/{pa_id}/submit")
def submit(pa_id: str, body: dict):
    return service.submit(pa_id, body["provider_id"])


@router.post("/{pa_id}/insurer/approve")
def insurer_approve(pa_id: str, body: dict | None = None):
    body = body or {}
    return service.insurer_approve(pa_id, note=body.get("note"))


@router.post("/{pa_id}/insurer/request-info")
def insurer_request_info(pa_id: str, body: dict | None = None):
    body = body or {}
    return service.insurer_request_info(pa_id, note=body.get("note"))
