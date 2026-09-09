"""Read actual supported launch commands; run their transport flags on an owned native port.

Container host/port and the reload supervisor are normalized for an isolated test process.
Proxy options are never added by this harness: they must come from the source command.
"""

import json
import os
import shlex
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]


def launch_commands() -> dict[str, list[str]]:
    commands = {}
    for name in ("README.md", "docs/18-devops.md", "docker-compose.yml", "docker-compose.dev.yml"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        matches = [line.split("uvicorn ", 1)[1].strip().rstrip('"') for line in lines if "uvicorn app.main:app" in line]
        if len(matches) != 1:
            raise AssertionError("Review every executable launch command in " + name)
        commands[name] = shlex.split(matches[0])
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    commands["backend/Dockerfile"] = json.loads(dockerfile.split("CMD ")[-1])[1:]
    return commands


@contextmanager
def native_server(command, log_path, *, extra_env=None, app_module=None):
    args = list(command)
    if app_module:
        args[0] = app_module
    # No Docker/WSL or reload subprocess tree is necessary to exercise server transport options.
    if "--reload" in args:
        args.remove("--reload")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    for option, value in (("--host", "127.0.0.1"), ("--port", str(port)),
                          ("--loop", "app.core.event_loop:new_event_loop")):
        if option in args:
            args[args.index(option) + 1] = value
        else:
            args.extend([option, value])
    env = os.environ.copy()
    env.update(extra_env or {})
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(  # noqa: S603 — source-derived Uvicorn args, no shell
            [sys.executable, "-m", "uvicorn", *args], cwd=ROOT / "backend", env=env,
            stdout=output, stderr=subprocess.STDOUT, creationflags=flags,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError("Owned native server exited before readiness")
                    try:
                        if client.get("/healthz").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Owned native server startup timed out")
                yield client
        finally:
            process.terminate()
            process.wait(timeout=10)


def log_records(path):
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            pass
    return records
