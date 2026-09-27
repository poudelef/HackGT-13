"""Recall of chart rows and how many saved rows the judge called accurate."""

from __future__ import annotations

import re


def benefit_score(grid_rows: list[dict], items: list[dict]) -> dict:
    matched = sum(1 for row in grid_rows if _saved(row.get("service") or "", items))
    judged = [item for item in items if item.get("judge_verdict")]
    accurate = sum(1 for item in judged if item.get("judge_verdict") == "ACCURATE")
    total_grid = len(grid_rows)
    total_judged = len(judged)
    return {
        "grid_rows": total_grid,
        "grid_matched": matched,
        "grid_recall": round(matched / total_grid, 3) if total_grid else None,
        "items": len(items),
        "accurate": accurate,
        "accurate_of": total_judged,
        "accurate_rate": round(accurate / total_judged, 3) if total_judged else None,
    }


def _saved(service: str, items: list[dict]) -> bool:
    return any(_same(service, item.get("service_label") or "") for item in items)


def _same(left: str, right: str) -> bool:
    a = re.sub(r"[^a-z0-9]+", " ", left.lower()).strip()
    b = re.sub(r"[^a-z0-9]+", " ", right.lower()).strip()
    if len(a) < 4 or len(b) < 4:
        return False
    if a in b or b in a:
        return True
    words = [word for word in a.split() if len(word) >= 5][:2]
    return bool(words) and all(word in b for word in words)
