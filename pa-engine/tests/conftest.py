import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="clearpath-test-"))
os.environ["DATABASE_PATH"] = str(_root / "test.db")
os.environ["STORAGE_DIR"] = str(_root / "storage")
os.environ["DEMO_DIR"] = str(_root / "demo")
os.environ["INSURER_DELAY_SECONDS"] = "0"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROK_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9"
os.environ["GEMINI_BASE_URL"] = "http://127.0.0.1:9"
os.environ["GROK_BASE_URL"] = "http://127.0.0.1:9"
os.environ["DEMO_TODAY"] = "2026-09-27"
os.environ["DEMO_MODE"] = "false"

import pytest


@pytest.fixture(autouse=True)
def _block_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GEMINI_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GROK_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROK_API_KEY", "")
