"""Four-tier section locator. Years are not treated as chapter numbers. B–D are capped."""

from __future__ import annotations

import re

from app.config import settings
from rank_bm25 import BM25Okapi

TARGETS = {
    "benefit_summary": ["benefits chart", "authorization", "what you pay", "summary of benefits"],
    "clinical_policy": ["coverage criteria", "medically necessary", "indications", "coding"],
    "drug_criteria": ["prior authorization criteria", "drug:", "age restrictions", "covered uses"],
}

TIER_ORDER = ["A", "B", "C", "D"]


def locate(pages: list[dict], role: str, hints: dict) -> dict:
    start = "A" if hints.get("toc") else ("C" if hints.get("table_pages", 0) >= 1 and role == "benefit_summary" else "B")
    if role == "clinical_policy" and len(pages) <= 8:
        start = "B"
    order = [start] + [tier for tier in TIER_ORDER if tier != start]
    failed = []
    for tier in order:
        found, reason, nums = _run(tier, pages, role)
        if found:
            cap = settings.section_page_cap
            truncated = False
            if tier in {"B", "C", "D"} and len(nums) >= cap:
                nums = nums[:cap]
                truncated = True
            return {
                "tier_used": tier,
                "failed_tiers": failed,
                "pages": nums,
                "possibly_truncated": truncated,
            }
        failed.append({"tier": tier, "reason": reason})
    return {
        "tier_used": "D",
        "failed_tiers": failed,
        "pages": [p["page"] for p in pages][: settings.section_page_cap],
        "possibly_truncated": len(pages) > settings.section_page_cap,
    }


def _run(tier: str, pages: list[dict], role: str) -> tuple[bool, str, list[int]]:
    if tier == "A":
        return _tier_a(pages, role)
    if tier == "B":
        return _tier_b(pages, role)
    if tier == "C":
        return _tier_c(pages, role)
    return _tier_d(pages, role)


def _tier_a(pages: list[dict], role: str) -> tuple[bool, str, list[int]]:
    entries = []
    for page in pages[:10]:
        for line in (page.get("text") or "").splitlines():
            # A section number counts only beside a section word, so a year is not a chapter.
            match = re.search(
                r"(?:section\s+)?(\d+(?:\.\d+)*)\s+([A-Za-z].+?)(?:\.{2,}|\s{2,})(\d+)\s*$",
                line.strip(),
                re.I,
            )
            if not match:
                continue
            title = match.group(2).strip()
            if re.fullmatch(r"20\d{2}", title):
                continue
            entries.append((title, int(match.group(3))))
    if len(entries) < 2:
        return False, "no TOC", []
    targets = TARGETS[role]
    hits = [num for title, num in entries if any(t in title.lower() for t in targets)]
    if not hits:
        return False, "TOC has no target section", []
    start = hits[0]
    later = [num for _, num in entries if num > start]
    end = min(later) - 1 if later else pages[-1]["page"]
    nums = [p["page"] for p in pages if start <= p["page"] <= end]
    if not nums or nums != sorted(nums):
        return False, "TOC ranges are not inside the document", []
    return True, "", nums


def _tier_b(pages: list[dict], role: str) -> tuple[bool, str, list[int]]:
    targets = TARGETS[role]
    for index, page in enumerate(pages):
        lines = page.get("text") or ""
        lower = lines.lower()
        if not any(target in lower for target in targets):
            continue
        window = pages[index : index + 3]
        blob = "\n".join(p.get("text") or "" for p in window).lower()
        if any(target in blob for target in targets):
            nums = [p["page"] for p in pages[index:]]
            return True, "", nums or [page["page"]]
    return False, "no target header", []


def _tier_c(pages: list[dict], role: str) -> tuple[bool, str, list[int]]:
    nums = []
    for page in pages:
        blob = (page.get("text") or "").lower()
        tables = page.get("tables") or []
        if "authorization:" in blob or tables:
            nums.append(page["page"])
    if len(nums) >= 1 and role == "benefit_summary":
        return True, "", nums
    if len(nums) >= 2:
        return True, "", nums
    return False, "no authorization table", []


def _tier_d(pages: list[dict], role: str) -> tuple[bool, str, list[int]]:
    docs = [(p.get("text") or "").lower().split() for p in pages]
    if not any(docs):
        return False, "no text for search", []
    try:
        bm = BM25Okapi(docs)
    except ZeroDivisionError:
        return False, "search index failed", []
    scores = bm.get_scores(TARGETS[role][0].split())
    if scores.max() <= 0 if hasattr(scores, "max") else max(scores) <= 0:
        return False, "no page scored", []
    peak = max(scores)
    nums = [pages[i]["page"] for i, score in enumerate(scores) if score >= peak * 0.5 and score > 0]
    if not nums:
        return False, "no page above the threshold", []
    return True, "", nums
