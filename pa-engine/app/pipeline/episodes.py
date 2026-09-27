"""Append-only episode log. The only writer of episodes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.config import PIPELINE_VERSION
from app.repository import get_repo


class EpisodeRecorder:
    def __init__(self, subject_type: str, subject_id: str, run_id: str | None, actor: str = "engine"):
        self.subject_type = subject_type
        self.subject_id = subject_id
        self.run_id = run_id
        self.actor = actor
        self.step_no = 0

    def step(
        self,
        stage: str,
        start_summary: str,
        fn: Callable[[], Any],
        *,
        group_no: int | None = None,
        item_key: str | None = None,
        done: Callable[[Any], str] | None = None,
        input_fingerprint: str | None = None,
    ) -> Any:
        self.step_no += 1
        self._write(
            stage,
            "started",
            start_summary,
            group_no=group_no,
            item_key=item_key,
            input_fingerprint=input_fingerprint,
        )
        try:
            value = fn()
        except Exception as exc:
            self._write(
                stage,
                "failed",
                f"{stage} failed: {exc}",
                group_no=group_no,
                item_key=item_key,
                detail={"error": str(exc)},
            )
            raise
        status = "completed"
        summary = done(value) if done else start_summary
        if isinstance(value, dict) and value.get("cache_hit"):
            status = "cache_hit"
        self._write(
            stage,
            status,
            summary,
            group_no=group_no,
            item_key=item_key,
            output_fingerprint=value.get("fingerprint") if isinstance(value, dict) else None,
            detail=value.get("detail") if isinstance(value, dict) else None,
        )
        return value

    def record(
        self,
        stage: str,
        summary: str,
        *,
        status: str = "completed",
        group_no: int | None = None,
        item_key: str | None = None,
        detail: dict | None = None,
        actor: str | None = None,
    ) -> dict:
        self.step_no += 1
        started = self._write(stage, "started", summary, group_no=group_no, item_key=item_key, actor=actor)
        terminal = self._write(
            stage,
            status,
            summary,
            group_no=group_no,
            item_key=item_key,
            detail=detail,
            actor=actor,
        )
        terminal["started_id"] = started["id"]
        return terminal

    def _write(
        self,
        stage: str,
        status: str,
        summary: str,
        *,
        group_no: int | None = None,
        item_key: str | None = None,
        detail: dict | None = None,
        input_fingerprint: str | None = None,
        output_fingerprint: str | None = None,
        actor: str | None = None,
    ) -> dict:
        return get_repo().insert_episode(
            {
                "subject_type": self.subject_type,
                "subject_id": self.subject_id,
                "run_id": self.run_id,
                "stage": stage,
                "step_no": self.step_no,
                "group_no": group_no,
                "item_key": item_key,
                "actor": actor or self.actor,
                "status": status,
                "input_fingerprint": input_fingerprint,
                "output_fingerprint": output_fingerprint,
                "summary": summary,
                "detail": detail,
                "pipeline_version": PIPELINE_VERSION,
            }
        )
