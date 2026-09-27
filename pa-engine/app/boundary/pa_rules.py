"""PA requirement lookup over live coverage items (no duplicate PARule table)."""

from __future__ import annotations

from app.ingest.pa_markers import labels_match, significant_words
from app.repository import get_repo


def pa_rules_from_coverage(
    *,
    insurance_plan_id: str | None = None,
    service_category: str | None = None,
    service_code: str | None = None,
) -> list[dict]:
    """Return requirement rows shaped like PARule, sourced from live coverage items."""
    repo = get_repo()
    items = repo.live_items("coverage")
    rows: list[dict] = []
    for item in items:
        policy = repo.get_policy(item["policy_id"])
        if policy is None:
            continue
        if insurance_plan_id and policy["id"] != insurance_plan_id and item["policy_id"] != insurance_plan_id:
            # Also allow matching when insurance_plan_id is opaque teammate id stored on PA.
            if (policy.get("insurer") or "") != insurance_plan_id:
                continue
        data = item.get("data") or {}
        status = data.get("pa_status")
        if status not in {"required", "not_required", "conditional"}:
            status = "required" if data.get("pa_required") else "not_required"
        label = item.get("service_label") or data.get("service_label") or ""
        codes = item.get("service_codes") or data.get("service_codes") or []
        if service_code and service_code not in [str(c) for c in codes]:
            if not service_category:
                continue
        if service_category and not _category_matches(service_category, label, codes):
            continue
        rows.append(
            {
                "insurance_plan_id": policy["id"],
                "payer_name": policy.get("insurer"),
                "plan_name": policy.get("plan_name"),
                "service_category": label,
                "service_codes": codes,
                "requirement": status,
                "condition_notes": data.get("evidence_text") or data.get("note"),
                "policy_item_id": item["id"],
                "page": item.get("page"),
            }
        )
    return rows


def lookup_requirement(
    *,
    insurance_plan_id: str | None,
    service_category: str,
    service_code: str | None = None,
) -> dict:
    """Single best rule for [plan, service]. Unknown -> required (G9)."""
    rows = pa_rules_from_coverage(
        insurance_plan_id=insurance_plan_id,
        service_category=service_category,
        service_code=service_code,
    )
    if not rows:
        # Broader: any live coverage matching category regardless of plan id.
        rows = pa_rules_from_coverage(service_category=service_category, service_code=service_code)
    if not rows:
        return {
            "insurance_plan_id": insurance_plan_id,
            "service_category": service_category,
            "requirement": "required",
            "condition_notes": "Coverage not confirmed from benefit summary; PA assumed required (G9).",
            "matched": False,
        }
    # Prefer exact code, then required/conditional over not_required when tied.
    def rank(row: dict) -> tuple:
        codes = [str(c) for c in (row.get("service_codes") or [])]
        code_hit = 1 if service_code and service_code in codes else 0
        req_rank = {"required": 2, "conditional": 1, "not_required": 0}.get(row["requirement"], 0)
        return (-code_hit, -req_rank, len(row.get("service_category") or ""))

    rows.sort(key=rank)
    best = rows[0]
    return {**best, "matched": True}


def _category_matches(category: str, label: str, codes: list) -> bool:
    if not category:
        return True
    if any(str(c).lower() == category.lower() for c in codes):
        return True
    if labels_match(category, label):
        return True
    ca, lb = significant_words(category), significant_words(label)
    if ca and lb and len(ca & lb) >= max(1, min(2, len(ca) // 2)):
        return True
    return category.lower() in (label or "").lower() or (label or "").lower() in category.lower()
