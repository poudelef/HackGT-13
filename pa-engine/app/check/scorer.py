"""Readiness is met rules divided by total rules."""

from __future__ import annotations


def readiness(statuses: list[str]) -> tuple[float, str, int, int]:
    total = len(statuses)
    met = sum(1 for status in statuses if status == "met")
    if total == 0:
        return 1.0, "ready_for_review", 0, 0
    score = met / total
    status = "ready_for_review" if met == total else "needs_info"
    return score, status, met, total
