"""The judge flags. It never sets a review state (G5)."""

from __future__ import annotations

from app import llm
from app.models.shapes import JudgeResult


def judge_item(item: dict, page_text: str, *, run_id: str) -> dict:
    try:
        result = llm.complete(
            "p2",
            {
                "item": {
                    "requirement_text": item.get("requirement_text") or item.get("service_label"),
                    "evidence_text": item.get("evidence_text"),
                    "codes": item.get("codes") or item.get("service_codes") or [],
                    "conditions": item.get("conditions") or [],
                },
                "page_text": page_text,
            },
            schema=JudgeResult,
            stage="judge",
            run_id=run_id,
            provider_kind="judge",
            item_key=item.get("criterion_key") or item.get("service_label"),
        )
        return result["data"]
    except Exception:
        return {"verdict": "UNAVAILABLE", "reason": "The judge did not return a verdict. A person still decides."}
