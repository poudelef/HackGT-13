#!/usr/bin/env python3
"""After every code change: free old ports, start a fresh API, run edge + port tests.

Usage (from repo root or pa-engine):

  ../.venv/bin/python scripts/verify_change.py
  ../.venv/bin/python scripts/verify_change.py --keep   # leave API running
  ../.venv/bin/python scripts/verify_change.py --port 8000

Default API port is 8000 (demo). Also frees web port 3000 so a stale Next process
cannot sit on the UI port; web is not auto-started unless --web is passed.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import devports  # noqa: E402


EDGE_TESTS = [
    "tests/test_port_lifecycle.py",
    "tests/test_pa_order_edge_cases.py",
    "tests/test_pa_markers.py",
    "tests/test_pipeline_overview_edges.py",
    "tests/test_coverage_insurance_plan.py",
    "tests/test_requirements_edge_cases.py",
    "tests/test_boundary_contract.py",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Free ports, restart API, run edge tests")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VERIFY_API_PORT", "8000")))
    parser.add_argument("--web-port", type=int, default=int(os.environ.get("VERIFY_WEB_PORT", "3000")))
    parser.add_argument("--keep", action="store_true", help="Leave the fresh API running")
    parser.add_argument("--web", action="store_true", help="Also start Next.js on --web-port after freeing it")
    parser.add_argument("--skip-live", action="store_true", help="Only free ports + unit tests (no uvicorn)")
    args = parser.parse_args()

    def log(msg: str) -> None:
        print(msg, flush=True)

    log(f"==> Closing previous listeners on API :{args.port} and web :{args.web_port}")
    for port in (args.port, args.web_port):
        try:
            killed = devports.free_port(port)
            log(f"    port {port}: killed {killed or 'none'}; free={not devports.port_in_use(port)}")
        except RuntimeError as exc:
            log(f"    port {port}: {exc}")
            return 1

    venv_py = REPO / ".venv" / "bin" / "python"
    python = str(venv_py if venv_py.exists() else sys.executable)

    # Always run port unit tests + PA edge suite (no live server required for most).
    log("==> Running edge / port unit tests")
    unit = subprocess.run(
        [python, "-m", "pytest", "-q", *EDGE_TESTS],
        cwd=str(ROOT),
        env={**os.environ, "RUN_LIVE_PORT_TESTS": "0", "PYTHONUNBUFFERED": "1"},
    )
    if unit.returncode != 0:
        log("Unit/edge tests failed")
        return unit.returncode

    if args.skip_live:
        log("==> Skip live API (--skip-live)")
        return 0

    log(f"==> Starting fresh API on :{args.port}")
    if devports.port_in_use(args.port) or devports.listeners_on_port(args.port):
        log("Port still busy; abort")
        return 1

    # Load .env if present so keys reach uvicorn
    env = os.environ.copy()
    env_path = REPO / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    env["INSURER_DELAY_SECONDS"] = env.get("INSURER_DELAY_SECONDS", "1")

    api_proc = None
    web_proc = None
    try:
        api_proc = devports.start_uvicorn(args.port, env=env)
        health = devports.wait_health(args.port, timeout=30.0)
        print(f"    /health ok commit={health.get('commit')} db={health.get('database')} pipeline={health.get('pipeline_version')}")

        print("==> Live port lifecycle test (fresh process only)")
        live = subprocess.run(
            [python, "-m", "pytest", "-q", "tests/test_port_lifecycle.py::test_live_api_starts_only_after_port_cleared"],
            cwd=str(ROOT),
            env={
                **env,
                "RUN_LIVE_PORT_TESTS": "1",
                "VERIFY_API_PORT": str(int(os.environ.get("VERIFY_LIVE_PROBE_PORT", "18080"))),
            },
        )
        if live.returncode != 0:
            print("Live port test failed")
            return live.returncode

        if args.web:
            web_dir = REPO / "web"
            print(f"==> Starting fresh web on :{args.web_port}")
            web_proc = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", str(args.web_port)],
                cwd=str(web_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            devports.wait_port_open(args.web_port, timeout=40.0)
            print(f"    web listening http://127.0.0.1:{args.web_port}")

        print("==> All change-guard checks passed")
        print(f"    API  http://127.0.0.1:{args.port}/health")
        print(f"    App  http://127.0.0.1:{args.web_port if args.web else 3000}")
        if args.keep:
            print("    --keep: leaving servers running (Ctrl+C in this terminal does not stop them)")
            # Detach: do not kill children on exit
            if api_proc:
                api_proc = None
            if web_proc:
                web_proc = None
        return 0
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1
    finally:
        if not args.keep:
            print("==> Stopping temporary servers")
            if web_proc is not None:
                web_proc.terminate()
                try:
                    web_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    web_proc.kill()
            devports.stop_process(api_proc, port=args.port)
            try:
                devports.free_port(args.web_port)
            except RuntimeError:
                pass


if __name__ == "__main__":
    sys.exit(main())
