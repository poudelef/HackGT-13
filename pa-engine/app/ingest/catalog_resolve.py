"""Resolve free-text order wording to a row that already exists in the live catalog.

A report says "MRI of the lumbar spine"; Order Desk only selects a Service when the
text equals a catalog label. This maps one onto the other using the same label
helpers the check engine uses (`service_matcher._coverage_by_label`,
`pa_markers.labels_match` / `significant_words`), so nothing is invented: every
returned label and code comes from a live accepted item.
"""

from __future__ import annotations

import re
from collections import Counter

from app.repository import get_repo, payer_label

# Same shapes the catalog exposes to the UI: CPT (digits), HCPCS Level II (letter+4), CDT (D####).
_CODE_PATTERNS = (
    re.compile(r"\d{4,5}[A-Za-z]?"),
    re.compile(r"[A-Za-z]\d{4}"),
)


def looks_like_service_code(value: str) -> bool:
    c = (value or "").strip()
    return bool(c) and any(p.fullmatch(c) for p in _CODE_PATTERNS)


def service_codes_for(label: str | None, codes: list) -> list[str]:
    """Billing codes for one catalog row. Prefer real codes; fall back to a code in the label."""
    out: list[str] = []
    for raw in codes or []:
        c = str(raw).strip()
        if c and looks_like_service_code(c) and c not in out:
            out.append(c)
    text = label or ""
    for match in re.finditer(r"\((\d{4,5}[A-Za-z]?)\)", text):
        if match.group(1) not in out:
            out.append(match.group(1))
    if not out:
        bare = re.search(r"\b(\d{5})\b", text)
        if bare and bare.group(1) not in out:
            out.append(bare.group(1))
    if not out:
        out = [str(c).strip() for c in (codes or []) if str(c).strip()]
    return out


def resolveOrderToCatalog(order_text: str, service_code: str | None = None) -> dict:
    """Map an extracted order onto the live catalog across every plan.

    Returns status, the canonical catalog label and code when they are unique, and the
    plan identity only when every match shares one plan.
    """
    order = (order_text or "").strip()
    code = str(service_code or "").strip()
    rows = _catalog_rows()
    if not rows:
        return _unresolved(order, code, "none", [])

    if code:
        hits = [row for row in rows if _has_code(row, code)]
        if hits:
            return _from_rows(_narrow_by_label(hits, order) or hits, order, code)

    if order:
        winner = _coverage_by_label(_shims(rows), order)
        if winner is not None:
            label = winner["service_label"]
            return _from_rows([row for row in rows if _same_label(row["label"], label)], order, code)

    # Nothing unique: hand back the clinician's wording plus anything worth reviewing.
    candidates = _rank(rows, order)
    return _unresolved(order, code, "ambiguous" if candidates else "none", candidates)


def _catalog_rows() -> list[dict]:
    """One row per (plan, label): live coverage rows plus rule labels that carry a billing code."""
    repo = get_repo()
    policies: dict[str, dict] = {}
    merged: dict[tuple, dict] = {}
    for item in repo.live_items():
        policy_id = item["policy_id"]
        if policy_id not in policies:
            policies[policy_id] = repo.get_policy(policy_id) or {}
        policy = policies[policy_id]
        insurer = payer_label(policy)
        if not insurer:
            continue
        identity = (
            insurer,
            policy.get("plan_name") or policy.get("file_name") or "Plan",
            policy.get("plan_year") or "",
        )
        data = item.get("data") or {}
        if item["item_type"] == "coverage":
            label = item.get("service_label") or data.get("service_label") or ""
            pairs = [(label, service_codes_for(label, item.get("service_codes") or data.get("service_codes") or []))]
        else:
            pairs = []
            for label in data.get("applies_to") or []:
                codes = service_codes_for(label, data.get("codes") or [])
                # A rule label is only a catalog service when it carries a billing code.
                if any(looks_like_service_code(c) for c in codes):
                    pairs.append((label, codes))
        for label, codes in pairs:
            if not (label or "").strip():
                continue
            key = (*identity, label)
            row = merged.get(key)
            if row is None:
                merged[key] = {
                    "item_id": item["id"],
                    "kind": item["item_type"],
                    "insurer": identity[0],
                    "plan_name": identity[1],
                    "plan_year": identity[2],
                    "label": label,
                    "codes": list(codes),
                }
                continue
            for c in codes:
                if c not in row["codes"]:
                    row["codes"].append(c)
            if row["kind"] != "coverage" and item["item_type"] == "coverage":
                row["kind"] = "coverage"
    return list(merged.values())


def _shims(rows: list[dict]) -> list[dict]:
    """Shape rows the way `_coverage_by_label` reads items, so the matcher is reused as is."""
    return [{"service_label": row["label"], "service_codes": row["codes"]} for row in rows]


def _coverage_by_label(shims: list[dict], order_text: str) -> dict | None:
    from app.check.service_matcher import _coverage_by_label as match_label

    return match_label(shims, order_text)


def _same_label(a: str, b: str) -> bool:
    from app.ingest.pa_markers import labels_match

    return (a or "") == (b or "") or labels_match(a, b)


def _has_code(row: dict, code: str) -> bool:
    wanted = code.upper()
    return any(str(c).upper() == wanted for c in row["codes"])


def _narrow_by_label(hits: list[dict], order_text: str) -> list[dict] | None:
    if not order_text or len(hits) < 2:
        return None
    winner = _coverage_by_label(_shims(hits), order_text)
    if winner is None:
        return None
    return [row for row in hits if _same_label(row["label"], winner["service_label"])]


def _from_rows(rows: list[dict], order_text: str, service_code: str) -> dict:
    if not rows:
        return _unresolved(order_text, service_code, "none", [])
    label = _canonical_label(rows)
    consistent = all(_same_label(row["label"], label) for row in rows)
    codes = _codes_in(rows)
    if not consistent:
        # Different service families share the code: keep the clinician's wording,
        # and only carry the code forward when the matches agree on one.
        return _unresolved(
            order_text,
            service_code or (codes[0] if len(codes) == 1 else ""),
            "ambiguous",
            _candidates(rows),
        )
    out = {
        "status": "matched",
        "order_text": label,
        "service_code": (codes[0] if codes else "") or service_code,
        "insurer": None,
        "plan_name": None,
        "plan_year": None,
        "candidates": _candidates(rows),
    }
    identities = {(row["insurer"], row["plan_name"], row["plan_year"]) for row in rows}
    if len(identities) == 1:
        insurer, plan_name, plan_year = identities.pop()
        out.update({"insurer": insurer, "plan_name": plan_name, "plan_year": plan_year})
    return out


def _canonical_label(rows: list[dict]) -> str:
    counts = Counter(row["label"] for row in rows)
    top = max(counts.values())
    return sorted([label for label, n in counts.items() if n == top], key=lambda s: (len(s), s))[0]


def _codes_in(rows: list[dict]) -> list[str]:
    """Codes shared by the match, billing-code shapes first, most common first."""
    counts: Counter = Counter()
    for row in rows:
        for c in row["codes"]:
            counts[str(c).strip()] += 1
    ranked = sorted(
        (c for c in counts if c),
        key=lambda c: (0 if looks_like_service_code(c) else 1, -counts[c], c),
    )
    return ranked


def _rank(rows: list[dict], order_text: str) -> list[dict]:
    from app.ingest.pa_markers import significant_words

    order_words = significant_words(order_text)
    scored = []
    for row in rows:
        overlap = len(order_words & significant_words(row["label"]))
        if overlap:
            scored.append((overlap, len(row["label"]), row))
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return _candidates([row for _, _, row in scored])


def _candidates(rows: list[dict], limit: int = 8) -> list[dict]:
    return [
        {
            "item_id": row["item_id"],
            "label": row["label"],
            "service_code": row["codes"][0] if row["codes"] else "",
            "kind": row["kind"],
            "insurer": row["insurer"],
            "plan_name": row["plan_name"],
            "plan_year": row["plan_year"],
        }
        for row in rows[:limit]
    ]


def _unresolved(order_text: str, service_code: str, status: str, candidates: list[dict]) -> dict:
    return {
        "status": status,
        "order_text": order_text,
        "service_code": service_code,
        "insurer": None,
        "plan_name": None,
        "plan_year": None,
        "candidates": candidates,
    }
