"""Format and role hints. A hint never decides the document type by itself."""

from __future__ import annotations

import re

ROLE_PHRASES = {
    "benefit_summary": [
        "evidence of coverage",
        "summary of benefits",
        "benefits chart",
        "what you pay",
        "cost sharing",
        "copayment",
        "coinsurance",
        "in-network",
    ],
    "clinical_policy": [
        "medical policy",
        "clinical policy",
        "coverage policy",
        "medically necessary",
        "coverage criteria",
        "indications",
        "policy number",
        "effective date",
    ],
    "drug_criteria": [
        "prior authorization criteria",
        "drug name",
        "covered uses",
        "exclusion criteria",
        "required medical information",
        "age restrictions",
        "prescriber restrictions",
        "coverage duration",
    ],
}


def precheck(pages: list[dict], declared_role: str) -> dict:
    sample = "\n".join(p.get("text") or "" for p in pages[:10]).lower()
    scores = {
        role: sum(1 for phrase in phrases if phrase in sample) for role, phrases in ROLE_PHRASES.items()
    }
    hint = max(scores, key=lambda role: scores[role]) if any(scores.values()) else declared_role
    mismatch = scores.get(hint, 0) >= scores.get(declared_role, 0) + 2 and hint != declared_role
    return {
        "toc": _has_toc(pages[:10]),
        "table_pages": sum(1 for p in pages if p.get("tables")),
        "page_count": len(pages),
        "scores": scores,
        "role_hint": hint,
        "mismatch": mismatch,
    }


def _has_toc(pages: list[dict]) -> bool:
    count = 0
    for page in pages:
        for line in (page.get("text") or "").splitlines():
            if re.search(r"\.{2,}\s*\d+\s*$", line) or re.search(
                r"^(section\s+)?\d+(\.\d+)*\s+.+\s+\d+\s*$", line, re.I
            ):
                count += 1
    return count >= 5
