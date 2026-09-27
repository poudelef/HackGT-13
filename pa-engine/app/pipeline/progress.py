"""Helpers that expose mid-run artifacts to the async job UI."""

from __future__ import annotations

from app.pipeline import cache
from app.pipeline import pipeline_runner
from app.repository import get_repo

# Overview "Processing Document..." checklist. Labels follow the earlier product UI.
BENEFIT_STEPS = [
    ("upload", "Queued"),
    ("pages", "Extracting pages"),
    ("identity", "Identifying plan"),
    ("precheck", "Analyzing document format"),
    ("cascade", "Locating benefit/coverage chapter"),
    ("extract", "Extracting benefit rules"),
    ("judge", "Independent accuracy review"),
    ("recheck", "Rechecking flagged items"),
    ("fhir", "Building FHIR output"),
]

CLINICAL_STEPS = [
    ("upload", "Queued"),
    ("pages", "Extracting pages"),
    ("identity", "Identifying plan"),
    ("precheck", "Analyzing document format"),
    ("cascade", "Locating criteria section"),
    ("extract", "Extracting clinical rules"),
    ("judge", "Independent accuracy review"),
    ("recheck", "Rechecking flagged items"),
    ("fhir", "Building FHIR output"),
]

DRUG_STEPS = [
    ("upload", "Queued"),
    ("pages", "Extracting pages"),
    ("identity", "Identifying plan"),
    ("precheck", "Analyzing document format"),
    ("cascade", "Locating drug criteria"),
    ("extract", "Indexing drug blocks"),
    ("judge", "Independent accuracy review"),
    ("recheck", "Rechecking flagged items"),
    ("fhir", "Building FHIR output"),
]

STAGE_ALIAS = {
    "clean": "precheck",
    "recover": "extract",
    "ground": "judge",
    "questions": "judge",
}


def pages_preview(policy_id: str) -> dict:
    """Internal page count helper. UI no longer dumps full PDF page text."""
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        from app.errors import ApiError

        raise ApiError("POLICY_NOT_FOUND", "No policy with that id.", 404)
    digest = policy["sha256"]
    cleaned = cache.get(cache.stage_key(digest, "clean"))
    raw = cache.get(cache.stage_key(digest, "pages"))
    rows: list = []
    if isinstance(cleaned, dict) and cleaned.get("pages"):
        rows = cleaned["pages"]
    elif isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and raw.get("pages"):
        rows = raw["pages"]
    return {
        "policy_id": policy_id,
        "status": policy["status"],
        "page_count": len(rows),
        "pages": [],
        "ingestion_running": pipeline_runner.ingestion_running(policy_id),
    }


def ingestion_steps(policy_id: str) -> list[dict]:
    """Checklist for the Processing Document screen."""
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        return []
    role = policy.get("document_role") or "clinical_policy"
    if role == "benefit_summary":
        order = BENEFIT_STEPS
    elif role == "drug_criteria":
        order = DRUG_STEPS
    else:
        order = CLINICAL_STEPS

    episodes = repo.episodes_for("policy", policy_id)
    latest: dict[str, dict] = {}
    for episode in episodes:
        stage = episode["stage"]
        if stage == "cache":
            continue
        key = STAGE_ALIAS.get(stage, stage)
        prev = latest.get(key)
        if prev is None or int(episode["seq"]) >= int(prev["seq"]):
            latest[key] = episode

    running = pipeline_runner.ingestion_running(policy_id) or policy["status"] == "ingesting"
    finished = policy["status"] in {"draft", "live", "paused", "failed"} and not running

    steps: list[dict] = []
    for stage, label in order:
        episode = latest.get(stage)
        if episode is None:
            steps.append({"id": stage, "label": label, "status": "pending", "detail": None})
            continue
        ep_status = episode["status"]
        if ep_status in {"completed", "cache_hit", "skipped"}:
            status = "done"
        elif ep_status == "failed":
            status = "failed"
        else:
            status = "active"
        # Checklist stays clean - no long episode summaries in the label row.
        steps.append({"id": stage, "label": label, "status": status, "detail": None})

    if running and not any(step["status"] == "active" for step in steps):
        for step in steps:
            if step["status"] == "pending":
                step["status"] = "active"
                break

    if finished:
        # Mark trailing unused stages (e.g. recheck never ran) as done when draft/live.
        if policy["status"] != "failed":
            for step in steps:
                if step["status"] == "pending":
                    step["status"] = "done"
        return steps
    return steps


def current_step_label(policy_id: str) -> str | None:
    for step in ingestion_steps(policy_id):
        if step["status"] == "active":
            return step["label"]
    return None
