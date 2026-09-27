"""Human edits win over engine writes and cached artifacts (H1, K4)."""

from __future__ import annotations

from app.repository import get_repo


def write_item(item_id: str, changes: dict, *, actor: str) -> dict:
    return get_repo().write_item(item_id, changes, actor=actor)


def write_answer(answer_id: str, changes: dict, *, actor: str) -> dict:
    return get_repo().write_answer(answer_id, changes, actor=actor)
