"""The only module that calls model APIs. Plain httpx, one JSON repair, think-tag stripping."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import PIPELINE_VERSION, settings
from app.errors import ApiError
from app.offline import complete as offline_complete
from app.pipeline import cache as artifact_cache
from app.repository import get_repo

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_STEP = 0
_STEP_LOCK = threading.Lock()


def reset_steps() -> None:
    global _STEP
    with _STEP_LOCK:
        _STEP = 0


def next_step() -> int:
    global _STEP
    with _STEP_LOCK:
        _STEP += 1
        return _STEP


def prompt_text(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text()


def prompt_version(name: str) -> str:
    return hashlib.sha256(prompt_text(name).encode()).hexdigest()[:12]


def complete(
    prompt_name: str,
    user: dict,
    *,
    schema: type[BaseModel] | None,
    stage: str,
    run_id: str,
    provider_kind: str = "extract",
    group_no: int | None = None,
    item_key: str | None = None,
    episode_id: str | None = None,
) -> dict:
    """provider_kind: extract (OpenAI) or judge (Gemini or Grok)."""
    repo = get_repo()
    if repo.count_llm_calls(run_id) >= settings.run_max_model_calls:
        raise ApiError("RUN_LIMIT", "This run reached its model-call limit.", 429)

    system = prompt_text(prompt_name)
    user_text = json.dumps(user, sort_keys=True, default=str)
    provider, model = _provider_and_model(provider_kind)
    timeout = _timeout(stage)
    key = artifact_cache.model_key(
        prompt_name, prompt_version(prompt_name), model, {"temperature": 0}, user_text
    )
    step = next_step()
    cached = artifact_cache.get(key)
    if cached is not None:
        repo.insert_llm_call(
            {
                "run_id": run_id,
                "episode_id": episode_id,
                "cache_key": key,
                "stage": stage,
                "step_no": step,
                "group_no": group_no,
                "item_key": item_key,
                "provider": provider,
                "model": model,
                "prompt_name": prompt_name,
                "status": "ok",
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
            }
        )
        return {"data": cached, "cache_hit": True, "step_no": step}

    if settings.demo_mode:
        raise ApiError(
            "DEMO_CACHE_MISS",
            f"Demo mode has no cached model call for {prompt_name}. Pre-warm the demo before presenting.",
            503,
        )

    started = time.perf_counter()
    status = "ok"
    data: dict | None = None
    raw_text = ""
    try:
        if _use_offline(provider_kind):
            data = offline_complete(prompt_name, user)
            provider = "offline"
            model = "offline-v1"
        else:
            raw_text = _http_complete(provider_kind, system, user_text, timeout)
            data = _parse_json(raw_text)
        if schema is not None:
            try:
                data = schema.model_validate(data).model_dump()
            except ValidationError as exc:
                status = "repaired"
                if _use_offline(provider_kind):
                    raise
                raw_text = _http_complete(
                    provider_kind,
                    system,
                    user_text + "\nValidation error:\n" + str(exc),
                    timeout,
                )
                data = schema.model_validate(_parse_json(raw_text)).model_dump()
    except ApiError:
        raise
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        fail = "timeout" if isinstance(exc, httpx.TimeoutException) else "error"
        repo.insert_llm_call(
            {
                "run_id": run_id,
                "episode_id": episode_id,
                "cache_key": key,
                "stage": stage,
                "step_no": step,
                "group_no": group_no,
                "item_key": item_key,
                "provider": provider,
                "model": model,
                "prompt_name": prompt_name,
                "status": fail,
                "latency_ms": latency,
                "tokens_in": len(user_text) // 4,
                "tokens_out": 0,
            }
        )
        if fail == "timeout":
            raise ApiError("MODEL_TIMEOUT", f"{prompt_name} timed out.", 504) from exc
        raise

    assert data is not None
    artifact_cache.put(key, "model_call", key, data, episode_id)
    repo.insert_llm_call(
        {
            "run_id": run_id,
            "episode_id": episode_id,
            "cache_key": key,
            "stage": stage,
            "step_no": step,
            "group_no": group_no,
            "item_key": item_key,
            "provider": provider,
            "model": model,
            "prompt_name": prompt_name,
            "status": status,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "tokens_in": len(user_text) // 4,
            "tokens_out": len(json.dumps(data)) // 4,
        }
    )
    return {"data": data, "cache_hit": False, "step_no": step}


def _use_offline(provider_kind: str) -> bool:
    if provider_kind == "judge":
        if settings.judge_provider == "grok":
            return not settings.grok_api_key
        return not settings.gemini_api_key
    return not settings.openai_api_key


def _provider_and_model(provider_kind: str) -> tuple[str, str]:
    if provider_kind == "judge":
        if settings.judge_provider == "grok":
            return "grok", settings.grok_model
        return "gemini", settings.gemini_model
    return "openai", settings.openai_model


def _timeout(stage: str) -> float:
    if "judge" in stage or stage in {"p2", "p6"}:
        return settings.timeout_judge
    if "quote" in stage or stage in {"p4", "p4b"}:
        return settings.timeout_quote
    return settings.timeout_extract


def _parse_json(text: str) -> dict:
    cleaned = _THINK.sub("", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return JSON.")
    return json.loads(cleaned[start : end + 1])


def _http_complete(provider_kind: str, system: str, user_text: str, timeout: float) -> str:
    if provider_kind == "judge" and settings.judge_provider == "gemini":
        return _gemini(system, user_text, timeout)
    if provider_kind == "judge" and settings.judge_provider == "grok":
        return _openai_compatible(
            settings.grok_base_url + "/v1/chat/completions",
            settings.grok_api_key,
            settings.grok_model,
            system,
            user_text,
            timeout,
        )
    return _openai_compatible(
        settings.openai_base_url + "/v1/chat/completions",
        settings.openai_api_key,
        settings.openai_model,
        system,
        user_text,
        timeout,
    )


def _openai_compatible(url: str, key: str, model: str, system: str, user_text: str, timeout: float) -> str:
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    return body["choices"][0]["message"]["content"]


def _gemini(system: str, user_text: str, timeout: float) -> str:
    url = (
        f"{settings.gemini_base_url}/v1beta/models/{settings.gemini_model}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": system + "\n\n" + user_text}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
    return body["candidates"][0]["content"]["parts"][0]["text"]
