"""Fingerprint cache. Only this module reads and writes artifact_cache. Writes are atomic."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.config import PIPELINE_VERSION
from app.repository import get_repo


def fingerprint(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def model_key(prompt_name: str, prompt_version: str, model: str, params: dict, user_text: str) -> str:
    return "model:" + fingerprint(prompt_name, prompt_version, model, params, user_text, PIPELINE_VERSION)


def stage_key(document_sha: str, stage: str, extra: str = "") -> str:
    return "stage:" + fingerprint(document_sha, PIPELINE_VERSION, stage, extra)


def get(key: str) -> Any | None:
    row = get_repo().cache_get(key)
    if not row or not row.get("finalized"):
        return None
    return row.get("value")


def put(key: str, layer: str, fp: str, value: Any, episode_id: str | None) -> None:
    """Write a temporary row, then the finalized row. Readers only see finalized entries."""
    repo = get_repo()
    temp = key + ":tmp"
    repo.cache_put(
        {
            "key": temp,
            "layer": layer,
            "fingerprint": fp,
            "pipeline_version": PIPELINE_VERSION,
            "value": value,
            "finalized": False,
            "created_by_episode": episode_id,
        }
    )
    if value is None:
        repo.cache_delete(temp)
        raise ValueError("Refusing to cache an empty artifact.")
    repo.cache_put(
        {
            "key": key,
            "layer": layer,
            "fingerprint": fp,
            "pipeline_version": PIPELINE_VERSION,
            "value": value,
            "finalized": True,
            "created_by_episode": episode_id,
        }
    )
    repo.cache_delete(temp)
    hidden = repo.cache_get(temp)
    if hidden is not None:
        raise RuntimeError("Temporary cache row was visible.")
