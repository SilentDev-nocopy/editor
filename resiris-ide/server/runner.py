"""Run Resiris programs with the real interpreter as a child process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


class RunSession:
    def __init__(self, run_id: str, process: subprocess.Popen, cwd: Path):
        self.run_id = run_id
        self.process = process
        self.cwd = cwd
        self.lines: list[str] = []
        self.finished = False
        self.return_code: int | None = None
        self._lock = threading.Lock()
        self._readers: list[threading.Thread] = []

        for stream in (process.stdout, process.stderr):
            reader = threading.Thread(
                target=self._read_stream,
                args=(stream,),
                daemon=True,
            )
            reader.start()
            self._readers.append(reader)

    def _read_stream(self, stream) -> None:
        try:
            for raw_line in iter(stream.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                with self._lock:
                    self.lines.append(line)
        except (ValueError, OSError):
            pass

    def output_since(self, since: int) -> tuple[list[str], int]:
        with self._lock:
            return list(self.lines[since:]), len(self.lines)

    def status(self) -> dict:
        return {
            "running": not self.finished,
            "returnCode": self.return_code,
            "lineCount": len(self.lines),
        }

    def marker(self) -> str:
        return "FINISHED" if self.finished else "RUNNING"


class RunWatcher(threading.Thread):
    def __init__(self, session: RunSession, timeout: float = 2.0):
        super().__init__(daemon=True)
        self.session = session
        self.run_id = session.run_id
        self.timeout = timeout

    def run(self) -> None:
        session = self.session
        try:
            session.process.wait()
        finally:
            session.return_code = session.process.returncode
            session.finished = True
            # give reader threads a final chance to flush remaining lines
            time.sleep(0.05)


class RunManager:
    def __init__(self):
        self._sessions: dict[str, RunSession] = {}

    def start(self, core_dir: Path, modules_dir: Path, file_path: Path) -> str:
        run_id = uuid.uuid4().hex[:12]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(core_dir)
        env["PYTHONUNBUFFERED"] = "1"

        # The real CLI resolves `Modules` relative to the process cwd,
        # so run from the directory that contains the modules dir.
        cwd = modules_dir.parent

        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "resiris", str(file_path)],
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        session = RunSession(run_id, process, cwd)
        RunWatcher(session).start()
        self._sessions[run_id] = session
        return run_id

    def get(self, run_id: str) -> RunSession | None:
        return self._sessions.get(run_id)

    def stop(self, run_id: str) -> bool:
        session = self._sessions.get(run_id)
        if session is None:
            return False
        if session.finished:
            return True
        process = session.process
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            pass

        # escalate to SIGKILL if the process ignores SIGINT
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not session.finished:
            time.sleep(0.05)
        if not session.finished:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        return True

    def drop(self, run_id: str) -> None:
        self._sessions.pop(run_id, None)

    def stop_all(self) -> None:
        for run_id in list(self._sessions.keys()):
            self.stop(run_id)