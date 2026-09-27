"""Unknown coverage means prior authorization is assumed (G9). Never a denial (G1)."""

from __future__ import annotations

import re

from app.ingest.pa_markers import significant_words
from app.repository import get_repo


def evaluate(
    match: dict,
    service_code: str | None,
    order_text: str,
    *,
    insurer: str | None = None,
    plan_name: str | None = None,
    plan_year: str | None = None,
) -> dict:
    repo = get_repo()
    coverage_items = repo.live_items_for_plan(
        insurer=insurer, plan_name=plan_name, plan_year=plan_year, item_type="coverage"
    )
    if match.get("status") == "coverage":
        item = match["items"][0]
        return _from_item(item)
    item = _find(coverage_items, service_code, order_text, match.get("items") or [])
    if item is None:
        return {
            "outcome": "continue",
            "pa_required": True,
            "page": None,
            "evidence_text": None,
            "note": "Coverage not confirmed from benefit summary",
            "item": None,
        }
    return _from_item(item)


def _from_item(item: dict) -> dict:
    data = item["data"] or {}
    status = data.get("pa_status")
    if status == "not_required":
        required = False
    elif status in {"required", "conditional"}:
        required = True
    else:
        required = bool(data.get("pa_required"))
    policy = get_repo().get_policy(item["policy_id"])
    return {
        "outcome": "not_required" if not required else "continue",
        "pa_required": required,
        "page": item["page"],
        "evidence_text": data.get("evidence_text"),
        "note": data.get("evidence_text"),
        "item": item,
        "policy": policy,
    }


def _find(items: list[dict], service_code: str | None, order_text: str, matched_rules: list[dict]) -> dict | None:
    if service_code:
        hits = [item for item in items if service_code in (item.get("service_codes") or [])]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return _best_label_match(hits, order_text)
    tokens = set(re.findall(r"[a-z0-9]{3,}", (order_text or "").lower()))
    for rule in matched_rules:
        tokens.update(str(code).lower() for code in ((rule.get("data") or {}).get("applies_to") or []))
        label = (rule.get("service_label") or (rule.get("data") or {}).get("requirement_text") or "")
        tokens.update(significant_words(label))
    scored = []
    for item in items:
        label = (item.get("service_label") or "").lower()
        label_words = significant_words(label)
        score = sum(1 for token in tokens if token and token in label)
        score += 2 * len(tokens & label_words)
        if score:
            scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], len(row[1].get("service_label") or "")))
    best_score = scored[0][0]
    top = [item for score, item in scored if score == best_score]
    if len(top) == 1:
        return top[0]
    # Tie: prefer the longer, more specific label when it still matches.
    return _best_label_match(top, order_text)


def _best_label_match(items: list[dict], order_text: str) -> dict | None:
    order_words = significant_words(order_text or "")
    if not items:
        return None
    ranked = []
    for item in items:
        label_words = significant_words(item.get("service_label") or "")
        overlap = len(order_words & label_words)
        ranked.append((overlap, len(item.get("service_label") or ""), item))
    ranked.sort(key=lambda row: (-row[0], -row[1]))
    if ranked[0][0] == 0 and len(ranked) > 1:
        return None
    return ranked[0][2]
