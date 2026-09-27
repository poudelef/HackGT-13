"""Apply example billing codes from a published service-code reference PDF/JSON.

Codes are matched to live coverage rows by service label. Human-edited rows stay locked (H1).
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from app.errors import ApiError
from app.repository import get_repo, now

_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "uhc_oh_s3_2026_service_codes.json"


def load_reference(path: Path | None = None) -> dict:
    target = path or _FIXTURE
    if not target.exists():
        raise ApiError("MISSING_REFERENCE", f"Service code reference not found: {target}", 404)
    return json.loads(target.read_text())


def normalize_label(label: str) -> str:
    text = (label or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[\"'()]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _looks_like_billing_code(value: str) -> bool:
    c = str(value or "").strip()
    return bool(
        re.fullmatch(r"\d{4,5}[A-Za-z]?", c)
        or re.fullmatch(r"[A-Za-z]\d{4}", c)
        or re.fullmatch(r"D\d{4}", c, re.I)
    )


def match_category(label: str, categories: list[dict], *, threshold: float = 0.72) -> dict | None:
    needle = normalize_label(label)
    if not needle:
        return None
    best: tuple[float, dict] | None = None
    for cat in categories:
        hay = normalize_label(cat.get("service_label") or "")
        if not hay:
            continue
        if needle == hay or needle in hay or hay in needle:
            score = 1.0 if needle == hay else 0.94
        else:
            score = SequenceMatcher(None, needle, hay).ratio()
        if best is None or score > best[0]:
            best = (score, cat)
    if best is None or best[0] < threshold:
        return None
    return best[1]


def apply_service_code_reference(
    policy_id: str,
    *,
    reference: dict | None = None,
    reference_path: Path | None = None,
    actor: str = "engine",
) -> dict:
    """Write matched example codes onto coverage rows that are not human-locked."""
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        raise ApiError("NOT_FOUND", "No policy with that id", 404)
    if policy.get("document_role") != "benefit_summary":
        raise ApiError(
            "INVALID_ROLE",
            "Service code reference applies to Evidence of Coverage / plan documents.",
            400,
        )

    ref = reference or load_reference(reference_path)
    categories = ref.get("categories") or []
    if not categories:
        raise ApiError("EMPTY_REFERENCE", "Service code reference has no categories", 400)

    updated = 0
    matched = 0
    skipped_locked = 0
    unmatched: list[str] = []
    for item in repo.items_for(policy_id):
        if item.get("item_type") != "coverage":
            continue
        data = dict(item.get("data") or {})
        label = data.get("service_label") or item.get("service_label") or ""
        hit = match_category(label, categories)
        if hit is None:
            unmatched.append(label)
            continue
        matched += 1
        codes = [str(c) for c in (hit.get("codes") or []) if str(c).strip()]
        if not codes:
            continue
        existing = [str(c) for c in (data.get("service_codes") or []) if str(c).strip()]
        if existing == codes:
            continue
        if item.get("edited_by_human"):
            skipped_locked += 1
            continue

        new_data = {
            **data,
            "service_codes": codes,
            "service_code_reference": {
                "source_file": ref.get("source_file"),
                "plan_name": ref.get("plan_name"),
                "plan_year": ref.get("plan_year"),
                "matched_label": hit.get("service_label"),
                "descriptor": hit.get("descriptor"),
                "code_system": hit.get("code_system"),
                "applied_at": now(),
            },
        }
        changes = {
            "data": new_data,
            "service_codes": json.dumps(codes),
            "service_label": label,
        }
        result = repo.write_item(item["id"], changes, actor=actor)
        if result.get("lock_preserved"):
            skipped_locked += 1
        else:
            updated += 1

    return {
        "policy_id": policy_id,
        "source_file": ref.get("source_file"),
        "categories": len(categories),
        "matched": matched,
        "updated": updated,
        "skipped_locked": skipped_locked,
        "unmatched": unmatched,
        "with_codes_in_reference": sum(1 for c in categories if c.get("codes")),
    }
