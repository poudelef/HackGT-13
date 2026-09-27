"""Port lifecycle + edge-suite guard.

Unit tests always run. Live restart+health tests run when RUN_LIVE_PORT_TESTS=1
(or via scripts/verify_change.py after every code change).
"""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest

from app import devports


def test_port_in_use_false_for_unused_ephemeral():
    port = devports.pick_free_port()
    assert not devports.port_in_use(port)
    assert devports.listeners_on_port(port) == []


def test_free_port_closes_previous_listener_before_rebind():
    """Old process on a port must be gone before a new bind succeeds."""
    port = devports.pick_free_port()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)

    def _serve() -> None:
        try:
            while True:
                conn, _ = sock.accept()
                conn.close()
        except OSError:
            return

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    time.sleep(0.1)
    assert devports.port_in_use(port)

    # Same-process socket: close it, then free_port must report clean.
    sock.close()
    time.sleep(0.1)
    killed = devports.free_port(port)
    assert isinstance(killed, list)
    assert not devports.port_in_use(port)

    # New listener must be able to bind the same port (previous closed).
    replacement = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    replacement.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    replacement.bind(("127.0.0.1", port))
    replacement.listen(1)
    replacement.close()
    devports.wait_port_free(port, timeout=3.0)


def test_free_port_kills_foreign_listener_subprocess():
    """A child listener on a port is terminated so the next start uses a clean port."""
    port = devports.pick_free_port()
    child = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    child.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    child.bind(("127.0.0.1", port))
    child.listen(1)

    # Foreign listener must be killed by free_port so a fresh bind succeeds.
    child.close()
    import subprocess
    import sys

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import socket,time;"
                f"s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
                f"s.bind(('127.0.0.1',{port}));s.listen(1);time.sleep(30)"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        devports.wait_port_open(port, timeout=5.0)
        assert holder.pid in devports.listeners_on_port(port)
        killed = devports.free_port(port)
        assert holder.pid in killed or holder.poll() is not None
        assert not devports.port_in_use(port)
        # Fresh bind works after kill
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.close()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=3)


@pytest.mark.skipif(os.environ.get("RUN_LIVE_PORT_TESTS") != "1", reason="Set RUN_LIVE_PORT_TESTS=1 for live API restart")
def test_live_api_starts_only_after_port_cleared():
    """Kill anything on the test port, start a new uvicorn, /health must answer."""
    preferred = int(os.environ.get("VERIFY_API_PORT", "18080"))
    port = preferred
    if devports.port_in_use(port) or devports.listeners_on_port(port):
        devports.free_port(port)
    devports.wait_port_free(port, timeout=5.0)

    proc = None
    try:
        proc = devports.start_uvicorn(port, env={"INSURER_DELAY_SECONDS": "0"})
        health = devports.wait_health(port, timeout=30.0)
        assert health.get("database") in {"ok", "error"}  # process up; db may be test path
        assert not (set(devports.listeners_on_port(port)) - {proc.pid}), "unexpected extra listener"
        # Second start must refuse while occupied
        with pytest.raises(RuntimeError, match="still has listeners"):
            devports.start_uvicorn(port)
    finally:
        devports.stop_process(proc, port=port)
        assert not devports.port_in_use(port)
