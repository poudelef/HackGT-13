"""Health, catalog helpers, and the sample-library bootstrap."""

from __future__ import annotations

import subprocess

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import PIPELINE_VERSION, settings
from app.repository import get_repo

router = APIRouter()


@router.get("/health")
def health() -> dict:
    db = "ok"
    try:
        get_repo().ping()
    except Exception:
        db = "error"
    return {
        "commit": _commit(),
        "database": db,
        "openai": "configured" if settings.openai_api_key else "unconfigured",
        "judge": "configured" if _judge_key() else "unconfigured",
        "pipeline_version": PIPELINE_VERSION,
        "demo_mode": settings.demo_mode,
    }


@router.post("/demo/bootstrap")
def bootstrap(force: bool = False) -> dict:
    from synth.bootstrap import bootstrap_demo

    return bootstrap_demo(force=force)


@router.get("/demo/files/{name}")
def demo_file(name: str):
    path = settings.demo_dir / name
    if not path.exists() or path.suffix.lower() != ".pdf":
        from app.errors import ApiError

        raise ApiError("POLICY_NOT_FOUND", "That sample file is not on disk.", 404)
    return FileResponse(path, media_type="application/pdf", filename=name)


def _judge_key() -> bool:
    if settings.judge_provider == "grok":
        return bool(settings.grok_api_key)
    return bool(settings.gemini_api_key)


def _commit() -> str:
    try:
        root = __import__("pathlib").Path(__file__).resolve().parents[3]
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "uncommitted"
