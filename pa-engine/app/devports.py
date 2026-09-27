"""Dev port helpers: free a port, wait until closed/open, start a fresh API listener.

Used by verify_change and tests so an old uvicorn/next process cannot keep serving
stale code on 8000/3000 after a restart.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def listeners_on_port(port: int) -> list[int]:
    """PIDs listening on TCP port (macOS/Linux lsof). Empty if none or lsof missing."""
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def free_port(port: int, *, timeout: float = 8.0, sig: int = signal.SIGTERM) -> list[int]:
    """Kill listeners on `port` and wait until the port accepts nothing. Returns killed PIDs."""
    killed: list[int] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = listeners_on_port(port)
        if not pids and not port_in_use(port):
            return killed
        for pid in pids:
            if pid == os.getpid() or pid in killed:
                continue
            try:
                os.kill(pid, sig)
                killed.append(pid)
            except ProcessLookupError:
                continue
            except PermissionError:
                continue
        time.sleep(0.2)
    # Last resort hard kill
    for pid in listeners_on_port(port):
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            if pid not in killed:
                killed.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.3)
    if port_in_use(port):
        raise RuntimeError(f"Port {port} is still in use after free_port (pids={listeners_on_port(port)})")
    return killed


def wait_port_free(port: int, *, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_in_use(port) and not listeners_on_port(port):
            return
        time.sleep(0.15)
    raise TimeoutError(f"Port {port} did not become free within {timeout}s")


def wait_port_open(port: int, *, timeout: float = 20.0, host: str = "127.0.0.1") -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_in_use(port, host=host):
            return
        time.sleep(0.15)
    raise TimeoutError(f"Port {port} did not open within {timeout}s")


def pick_free_port(preferred: int | None = None) -> int:
    """Return preferred if free, else an ephemeral free port."""
    if preferred is not None and not port_in_use(preferred) and not listeners_on_port(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_uvicorn(
    port: int,
    *,
    host: str = "127.0.0.1",
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    """Start uvicorn on a port that must already be free."""
    if port_in_use(port) or listeners_on_port(port):
        raise RuntimeError(f"Refusing to start API: port {port} still has listeners {listeners_on_port(port)}")
    root = Path(__file__).resolve().parents[1]
    engine = cwd or root
    venv_python = root.parent / ".venv" / "bin" / "python"
    python = str(venv_python if venv_python.exists() else Path(os.sys.executable))
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("INSURER_DELAY_SECONDS", "0")
    proc = subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(engine),
        env=merged,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return proc


def wait_health(port: int, *, timeout: float = 25.0, host: str = "127.0.0.1") -> dict:
    import json
    import urllib.error
    import urllib.request

    wait_port_open(port, timeout=timeout, host=host)
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1.5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and body.get("database"):
                    return body
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_err = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"/health on :{port} not ready ({last_err})")


def stop_process(proc: subprocess.Popen | None, *, port: int | None = None) -> None:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    if port is not None:
        try:
            free_port(port, timeout=5.0)
        except RuntimeError:
            free_port(port, timeout=3.0, sig=signal.SIGKILL)
