"""Turn a saved row into the fields a reviewer reads on the card."""

from __future__ import annotations

import re


def present_item(item: dict) -> dict:
    data = item.get("data") or {}
    item_type = item.get("item_type") or ""
    label = data.get("service_label") or data.get("requirement_text") or item.get("service_label") or "Item"
    evidence = " ".join(str(data.get("evidence_text") or data.get("requirement_text") or "").split())
    cost = cost_share(evidence, data)
    pa = data.get("pa_required")
    if pa is None and item_type == "rule":
        pa = True
    if pa is not True and evidence_says_pa(evidence):
        pa = True
    status = pa_status_of(data, pa)
    why = explain(item, evidence, cost, pa)
    exception = exception_text(data, evidence)
    codes = [str(c).strip() for c in (data.get("service_codes") or []) if str(c).strip()]
    return {
        "title": label,
        "cost_share": cost,
        "pa_required": bool(pa) if pa is not None else None,
        "pa_status": status,
        "marker_used": data.get("marker_used"),
        "service_codes": codes,
        "listing_index": data.get("listing_index"),
        "has_exception": bool(exception),
        "exception": exception,
        "limits": limits(evidence),
        "evidence": evidence,
        "why": why,
        "criteria": criteria_text(data, evidence),
    }


def pa_status_of(data: dict, pa_required: bool | None) -> str | None:
    """Normalize stored PA taxonomy for the review UI (required / conditional / not_required)."""
    status = data.get("pa_status")
    if status in {"required", "conditional", "not_required"}:
        return status
    if pa_required is True:
        return "required"
    if pa_required is False:
        return "not_required"
    return None


def cost_share(evidence: str, data: dict) -> str:
    if data.get("cost_share"):
        return str(data["cost_share"])
    parts = []
    for label in ("In-network", "Out-of-network", "You pay", "Other"):
        needle = f"{label}:"
        if needle not in evidence:
            continue
        chunk = evidence.split(needle, 1)[1]
        chunk = re.split(
            r"\s\|\s(?:In-network|Out-of-network|You pay|Authorization|Other|Service):",
            chunk,
            maxsplit=1,
        )[0]
        chunk = chunk.strip(" |")
        if chunk:
            parts.append(f"{label}: {chunk}")
    if parts:
        return " | ".join(parts)
    if re.search(r"\bcovered\b.+\bcovered\b", evidence, re.I) or evidence.lower().endswith("covered covered"):
        return "Covered"
    if re.search(r"\bnot covered\b", evidence, re.I):
        return "Not covered"
    match = re.search(r"(\$\d[\w\s%,.\-/$]*|covered(?: with limitations)?|not covered).*$", evidence, re.I)
    if match:
        return match.group(0).strip()
    return "See page quote"


def limits(evidence: str) -> str | None:
    match = re.search(
        r"(\d+\s+(?:visits?|days?|treatments?|meals?)(?:\s+per\s+(?:year|stay|month))?|"
        r"up to \d+|unlimited number of days|"
        r"\$\d[\d,]*\s+allowance)",
        evidence,
        re.I,
    )
    return match.group(0) if match else None


def criteria_text(data: dict, evidence: str) -> str:
    conditions = data.get("conditions") or []
    if conditions:
        return " | ".join(str(c.get("text") or "").strip() for c in conditions if c.get("text"))
    if data.get("requirement_text"):
        return str(data["requirement_text"])
    return evidence


def exception_text(data: dict, evidence: str) -> str | None:
    if data.get("exception"):
        return str(data["exception"])
    exceptions = [
        str(c.get("text") or "").strip()
        for c in (data.get("conditions") or [])
        if c.get("kind") == "exception" and c.get("text")
    ]
    if exceptions:
        return " | ".join(exceptions)
    match = re.search(
        r"((?:unless|except|exception|waived|waive)[^.|]{0,120})",
        evidence,
        re.I,
    )
    return match.group(1).strip() if match else None


def evidence_says_pa(evidence: str) -> bool:
    low = evidence.lower()
    if "no prior authorization" in low or "not require prior" in low:
        return False
    return any(
        word in low
        for word in (
            "prior authorization",
            "preauthorization",
            "precertification",
            "prior approval",
            "may require your provider to get prior authorization",
        )
    )


def explain(item: dict, evidence: str, cost: str, pa: bool | None) -> str:
    verdict = item.get("judge_verdict") or ""
    reason = (item.get("judge_reason") or "").strip()
    generic = reason.lower() in {
        "",
        "evidence, numbers, and codes match the cited page.",
        "evidence text and codes match the page exactly.",
    }
    short_match = "match" in reason.lower() and len(reason) < 80
    if verdict == "ACCURATE" and (generic or short_match):
        bits = ["The page states this service."]
        if cost and cost != "See page quote":
            bits.append(f"Cost share on the page: {cost}.")
        if pa is True:
            bits.append("Prior authorization is required on the page.")
        elif pa is False:
            bits.append("The page does not require prior authorization for this row.")
        if evidence:
            quote = evidence if len(evidence) < 180 else evidence[:177] + "..."
            bits.append(f'Quote: "{quote}"')
        return " ".join(bits)
    return reason or "Open the page quote and decide."
