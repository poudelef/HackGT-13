"""A likely owner is the author of a related referral, or nobody. Never a guessed person."""

from __future__ import annotations

import re

from app.check.dates import parse_date


def find(requirement: str, records: list[dict], providers: dict[str, dict]) -> tuple[dict | None, str | None]:
    words = {w for w in re.findall(r"[a-z]{5,}", requirement.lower())}
    for record in records:
        if record.get("record_kind") != "referral":
            continue
        blob = " ".join(filter(None, [record.get("display"), record.get("body")])).lower()
        if not any(word in blob for word in words):
            continue
        provider = providers.get(record.get("author_provider_id") or "")
        if not provider:
            continue
        when = parse_date(record.get("start_date"))
        label = record.get("display") or "a related referral"
        when_text = f" on {when.strftime('%b')} {when.day}" if when else ""
        return provider, f"Wrote {label}{when_text}"
    return None, None
