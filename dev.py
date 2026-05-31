#!/usr/bin/env python3
"""Atelier dev orchestrator — one command to run the whole stack locally.

What it does:
  1. Verifies prerequisites (Python 3.12+, uv, Docker — soft-fails on Docker).
  2. Ensures backend/.venv exists via `uv sync`.
  3. Copies backend/.env from .env.example if missing.
  4. Brings up docker compose services (MongoDB + Redis) from backend/.
  5. Starts the FastAPI API (uvicorn, --reload).
  6. Starts the arq worker.
  7. Starts the Next.js frontend if a `frontend/` directory exists (npm run dev).
  8. Streams interleaved logs with a colored prefix per service.
  9. Ctrl+C cleanly terminates every child and stops docker compose.

Usage:
    python dev.py                  # start the full stack
    python dev.py --setup          # one-time setup, then exit
    python dev.py --no-docker      # skip docker compose (use existing Mongo/Redis)
    python dev.py --no-worker      # skip the arq worker
    python dev.py --no-frontend    # skip the Next.js dev server
    python dev.py --port 8080      # change API port (default 8000)
    python dev.py --help

This script uses only the Python standard library — it doesn't need its own
venv. It assumes Python 3.10+ for syntax; everything else is delegated to uv.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Optional

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

# ── ANSI ──────────────────────────────────────────────────────────────
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
GREEN = "\033[32m"
GRAY = "\033[90m"
BRIGHT_BLUE = "\033[94m"

SERVICE_COLORS = {
    "docker": GRAY,
    "api": CYAN,
    "worker": MAGENTA,
    "frontend": GREEN,
}


def colored(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def banner(msg: str) -> None:
    print(colored(f"[dev] {msg}", BRIGHT_BLUE), flush=True)


def warn(msg: str) -> None:
    print(colored(f"[dev] {msg}", YELLOW), flush=True)


def err(msg: str) -> None:
    print(colored(f"[dev] {msg}", RED), file=sys.stderr, flush=True)


def has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ── Subprocess log streaming ──────────────────────────────────────────
def _pump(stream: IO[bytes], prefix: str, color: str) -> None:
    """Read a subprocess output stream and re-print each line with a prefix."""
    pad = f"{prefix:>8}"
    try:
        for raw in iter(stream.readline, b""):
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(f"{color}{pad}{RESET} {DIM}│{RESET} {line}", flush=True)
    except Exception:
        pass


class Service:
    """A single long-running child process with prefixed log output."""

    def __init__(
        self,
        name: str,
        cmd: list[str],
        cwd: Path,
        color: str,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.color = color
        self.env = env
        self.process: Optional[subprocess.Popen[bytes]] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        banner(f"start {self.name} → {' '.join(self.cmd)}  ({self.cwd.relative_to(ROOT)})")
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)
        try:
            self.process = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=merged_env,
                bufsize=0,
                # On POSIX, start in a new process group so we can signal the whole
                # group on shutdown (uvicorn spawns workers; arq spawns child tasks).
                start_new_session=(os.name == "posix"),
            )
        except FileNotFoundError:
            err(f"command not found for {self.name}: {self.cmd[0]}")
            return

        self._thread = threading.Thread(
            target=_pump,
            args=(self.process.stdout, self.name, self.color),
            daemon=True,
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self, timeout: float = 6.0) -> None:
        if not self.process or self.process.poll() is not None:
            return
        banner(f"stop  {self.name} …")
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            else:
                self.process.terminate()
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            warn(f"{self.name} did not terminate in {timeout}s; killing")
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                else:
                    self.process.kill()
            except Exception:
                pass
        except Exception as e:
            warn(f"error stopping {self.name}: {e}")


# ── Docker compose helpers ────────────────────────────────────────────
def docker_up() -> bool:
    """Start MongoDB + Redis via docker compose. Returns True on success."""
    if not has_cmd("docker"):
        warn("Docker not found — start MongoDB and Redis yourself, or install Docker Desktop.")
        return False

    banner("starting docker compose (mongo + redis)…")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=str(BACKEND),
    )
    if result.returncode != 0:
        err("docker compose up failed. Is the Docker daemon running?")
        return False
    # Give containers a moment to become healthy.
    time.sleep(2)
    return True


def docker_down() -> None:
    if not has_cmd("docker"):
        return
    banner("stopping docker compose…")
    subprocess.run(
        ["docker", "compose", "stop"],
        cwd=str(BACKEND),
        check=False,
    )


# ── Setup / preflight ─────────────────────────────────────────────────
def ensure_env_file() -> None:
    env_path = BACKEND / ".env"
    example_path = BACKEND / ".env.example"
    if env_path.exists():
        return
    if not example_path.exists():
        err(f"missing both backend/.env and backend/.env.example")
        sys.exit(1)
    banner(f"creating backend/.env from .env.example")
    shutil.copyfile(example_path, env_path)
    warn("backend/.env created from template — edit it to set real secrets before serious use.")


def ensure_uv_sync() -> None:
    if not has_cmd("uv"):
        err("uv is required. Install with one of:")
        err("  brew install uv")
        err("  pipx install uv")
        err("  curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)
    banner("syncing backend dependencies (uv sync)…")
    result = subprocess.run(["uv", "sync"], cwd=str(BACKEND))
    if result.returncode != 0:
        err("uv sync failed — see output above")
        sys.exit(result.returncode)


def preflight() -> None:
    # Python version: this script needs 3.10+ for its own syntax; backend needs 3.12+ (uv handles that).
    if sys.version_info < (3, 10):
        err(f"this script needs Python 3.10+. You have {sys.version_info.major}.{sys.version_info.minor}.")
        sys.exit(1)
    if not BACKEND.exists():
        err(f"backend/ not found at {BACKEND}")
        sys.exit(1)


# ── Service builders ──────────────────────────────────────────────────
def build_services(args: argparse.Namespace) -> list[Service]:
    services: list[Service] = []

    services.append(
        Service(
            name="api",
            cmd=["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", str(args.port)],
            cwd=BACKEND,
            color=SERVICE_COLORS["api"],
        )
    )

    if not args.no_worker:
        services.append(
            Service(
                name="worker",
                cmd=["uv", "run", "arq", "worker.main.WorkerSettings"],
                cwd=BACKEND,
                color=SERVICE_COLORS["worker"],
            )
        )

    if not args.no_frontend:
        if FRONTEND.exists():
            if has_cmd("npm"):
                services.append(
                    Service(
                        name="frontend",
                        cmd=["npm", "run", "dev"],
                        cwd=FRONTEND,
                        color=SERVICE_COLORS["frontend"],
                    )
                )
            else:
                warn("npm not found — skipping frontend.")
        else:
            banner("frontend/ not present yet — skipping (will be added in a future milestone).")

    return services


# ── Main loop ─────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Atelier dev orchestrator — runs the full local stack.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--setup", action="store_true", help="One-time setup (env + uv sync), then exit")
    parser.add_argument("--no-docker", action="store_true", help="Skip docker compose (use existing Mongo/Redis)")
    parser.add_argument("--no-worker", action="store_true", help="Skip the arq worker")
    parser.add_argument("--no-frontend", action="store_true", help="Skip the Next.js dev server")
    parser.add_argument("--port", type=int, default=8000, help="API port (default 8000)")
    args = parser.parse_args()

    preflight()
    ensure_env_file()
    ensure_uv_sync()

    if args.setup:
        banner("setup complete. Run `python dev.py` to start the stack.")
        return 0

    if not args.no_docker:
        docker_up()

    services = build_services(args)
    for s in services:
        s.start()
        time.sleep(0.4)  # stagger so prefixed logs don't interleave on startup

    print()
    banner("running. Endpoints:")
    banner(f"  health   →  http://localhost:{args.port}/api/v1/health")
    banner(f"  docs     →  http://localhost:{args.port}/docs")
    banner(f"  storage  →  http://localhost:{args.port}/api/v1/__debug__/storage")
    if FRONTEND.exists():
        banner("  frontend →  http://localhost:3000")
    banner("Ctrl+C to stop.")
    print()

    # Signal handling
    stopping = threading.Event()

    def on_signal(*_: object) -> None:
        if stopping.is_set():
            return
        stopping.set()
        print()
        banner("shutdown requested…")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        # Watch for unexpected exits while waiting for shutdown.
        while not stopping.is_set():
            time.sleep(0.5)
            for s in services:
                if s.process is None:
                    # Failed to start — count as fatal.
                    stopping.set()
                    break
                if s.process.poll() is not None:
                    code = s.process.returncode
                    warn(f"{s.name} exited (code {code}). Bringing the stack down.")
                    stopping.set()
                    break
    finally:
        for s in reversed(services):
            s.stop()
        if not args.no_docker:
            docker_down()
        banner("done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
