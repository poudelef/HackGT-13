"""Apply a structured coverage chart only as an optional import aid.

This is NOT the extraction path. The overview pipeline
(pages -> cascade order -> context builder -> sequential extract + working memory ->
ground -> judge) is the only path that produces judge verdicts.

Imports are always pending_review / UNAVAILABLE until a real extract+judge run.
They never hardcode HALLUCINATED or ACCURATE.
"""

from __future__ import annotations

import re

from app.errors import ApiError
from app.fhir import builders
from app.fhir.validate import validate_resource
from app.repository import get_repo, new_id


def apply_categories(policy_id: str, categories: list[dict], *, reviewer: str = "engine") -> dict:
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        raise ApiError("POLICY_NOT_FOUND", "No policy with that id.", 404)
    if policy["document_role"] != "benefit_summary":
        raise ApiError("INVALID_PDF", "Coverage extracts apply only to Evidence of Coverage / plan documents.", 400)
    if not categories:
        raise ApiError("INVALID_PDF", "No coverage categories were provided.", 400)

    repo.delete_unlocked_items(policy_id, None)
    saved = []
    seen: set[str] = set()
    for index, row in enumerate(categories, start=1):
        label = " ".join(str(row.get("service_label") or "").split()).strip()
        if not label:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:48] or f"coverage_{index}"
        if key in seen:
            key = f"{key}_{index}"[:48]
        seen.add(key)
        pa_required = bool(row.get("pa_required"))
        pa_status = row.get("pa_status") or ("required" if pa_required else "not_required")
        page = int(row.get("page") or 1)
        evidence = row.get("evidence_text") or label
        data = {
            "service_label": label,
            "service_codes": list(row.get("service_codes") or []),
            "pa_required": pa_required,
            "pa_status": pa_status,
            "page": page,
            "evidence_text": evidence,
            "marker_used": row.get("marker_used"),
            "reference": row.get("note") or row.get("reference"),
        }
        grounding = {
            "passed": False,
            "failures": ["Structured import only - run Reprocess for page-grounded extract and judge."],
        }
        item = repo.insert_item(
            {
                "id": new_id(),
                "policy_id": policy_id,
                "item_type": "coverage",
                "item_key": key,
                "seq": index,
                "service_label": label,
                "service_codes": data["service_codes"],
                "data": data,
                "original_data": data,
                "page": page,
                "grounding": grounding,
                "judge_verdict": "UNAVAILABLE",
                "judge_reason": "Awaiting extract+judge on the uploaded PDF (overview pipeline).",
                "review_state": "pending_review",
                "edited_by_human": False,
            }
        )
        saved.append(item)

    fresh = repo.get_policy(policy_id)
    resource = builders.insurance_plan(fresh, saved, status="draft")
    errors = validate_resource(resource)
    report = {"valid": not errors, "errors": errors}
    repo.update_policy(
        policy_id,
        {
            "status": "draft",
            "fhir_insurance_plan": resource,
            "validation_report": {"fhir": report},
            "insurer": policy.get("insurer") or fresh.get("insurer"),
            "plan_name": policy.get("plan_name") or fresh.get("plan_name"),
            "plan_year": policy.get("plan_year") or fresh.get("plan_year") or "2026",
        },
        actor=reviewer,
    )
    totals = {
        "total": len(saved),
        "required": sum(1 for item in saved if (item["data"] or {}).get("pa_status") == "required"),
        "not_required": sum(1 for item in saved if (item["data"] or {}).get("pa_status") == "not_required"),
        "conditional": sum(1 for item in saved if (item["data"] or {}).get("pa_status") == "conditional"),
        "pending_review": sum(1 for item in saved if item["review_state"] == "pending_review"),
        "hallucinated": sum(1 for item in saved if item.get("judge_verdict") == "HALLUCINATED"),
    }
    return {
        "id": policy_id,
        "status": "draft",
        "item_count": len(saved),
        "totals": totals,
        "fhir_valid": report["valid"],
        "insurance_plan": resource,
    }


def summarize_insurance_plan(resource: dict) -> dict:
    benefits = ((resource.get("coverage") or [{}])[0].get("benefit") or [])
    required = not_required = conditional = 0
    counted = 0
    for benefit in benefits:
        if not benefit.get("requirement"):
            continue
        counted += 1
        req = benefit.get("requirement") or ""
        status = None
        for extension in benefit.get("extension") or []:
            if str(extension.get("url") or "").endswith("pa-requirement-status"):
                status = extension.get("valueCode")
        if status == "conditional" or "may be required" in req.lower():
            conditional += 1
        elif req.startswith("No prior"):
            not_required += 1
        else:
            required += 1
    return {
        "benefit_count": counted,
        "required": required,
        "not_required": not_required,
        "conditional": conditional,
    }
