"""Resiris IDE backend: a tiny stdlib HTTP server.

`python3 server/main.py [--port 8742] [--core /path/to/PyResy]`

The backend only talks to the real Resiris language core; it never reimplements
the language.
"""

from __future__ import annotations

import argparse
import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import core
from .language import (
    analyze_source,
    autocomplete,
    compute_include_edit,
    hover_at,
    list_modules,
)
from .runner import RunManager

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 4 * 1024 * 1024


class IdeState:
    def __init__(self, core_dir: Path, modules_dir: Path):
        self.core_dir = core_dir
        self.modules_dir = modules_dir
        self.project_dir: Path | None = None
        self.runs = RunManager()

    def modules_dir_for_project(self, project_dir: Path, modules_dir: Path) -> Path:
        project_modules = project_dir / "Modules"
        if project_modules.is_dir():
            return project_modules
        return modules_dir

    def open_project(self, path: Path):
        path = path.expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"not a directory: {path}")
        self.project_dir = path
        self.modules_dir = self.modules_dir_for_project(path, self.modules_dir)
        return self.project_info()

    def project_info(self) -> dict:
        project_dir = self.project_dir
        if project_dir is None:
            return None
        files = list_files(project_dir)
        return {
            "name": project_dir.name,
            "path": str(project_dir),
            "files": files,
            "modules": [module_to_dict(module) for module in list_modules(self.modules_dir)],
            "modulesDir": str(self.modules_dir),
        }

    def resolve_file(self, relative_path: str) -> Path:
        if self.project_dir is None:
            raise ValueError("no project is open")
        target = (self.project_dir / relative_path).resolve()
        try:
            target.relative_to(self.project_dir)
        except ValueError:
            raise ValueError("path is outside the project")
        return target


def list_files(project_dir: Path) -> list[str]:
    files = []
    for path in sorted(project_dir.rglob("*.resy")):
        files.append(str(path.relative_to(project_dir)))
    return files


def module_to_dict(module) -> dict:
    return {
        "name": module.name,
        "functions": module.functions,
        "constants": [
            {"name": constant.name, "type": constant.type_name}
            for constant in module.constants
        ],
    }


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length > MAX_BODY:
        raise ValueError("body too large")
    return json.loads(handler.rfile.read(length) or "{}")


class IdeHandler(BaseHTTPRequestHandler):
    server_version = "ResirisIDE/0.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._send_error(404, "not found")
            return
        content = path.read_bytes()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".map": "application/json",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # --- routing ----------------------------------------------------------

    def do_GET(self):
        state: IdeState = self.server.state
        path = self.path

        if path == "/" or path == "/index.html":
            self._send_file(STATIC_DIR / "index.html")
            return

        if path.startswith("/api/"):
            if path == "/api/state":
                self._send(200, {"project": state.project_info(), "core": core.resiris_version()})
                return
            self._send_error(404, f"unknown endpoint: {path}")
            return

        try:
            relative = path.lstrip("/")
            target = (STATIC_DIR / relative).resolve()
            target.relative_to(STATIC_DIR)
        except ValueError:
            self._send_error(403, "forbidden")
            return
        self._send_file(target)

    def do_POST(self):
        state: IdeState = self.server.state
        path = self.path

        try:
            if path == "/api/project/open":
                body = _read_body(self)
                info = state.open_project(Path(body["path"]))
                self._send(200, {"project": info})
                return

            if path == "/api/file/read":
                body = _read_body(self)
                file_path = state.resolve_file(body["path"])
                content = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
                self._send(200, {"content": content})
                return

            if path == "/api/file/save":
                body = _read_body(self)
                file_path = state.resolve_file(body["path"])
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(body.get("content", ""), encoding="utf-8")
                self._send(200, {"ok": True})
                return

            if path == "/api/analyze":
                body = _read_body(self)
                result = analyze_source(body.get("source", ""), state.modules_dir)
                self._send(200, result)
                return

            if path == "/api/autocomplete":
                body = _read_body(self)
                items = autocomplete(
                    body.get("source", ""),
                    int(body.get("line", 0)),
                    int(body.get("column", 0)),
                    state.modules_dir,
                )
                self._send(200, {"items": items})
                return

            if path == "/api/hover":
                body = _read_body(self)
                result = hover_at(
                    body.get("source", ""),
                    int(body.get("line", 0)),
                    int(body.get("column", 0)),
                    state.modules_dir,
                )
                self._send(200, {"hover": result})
                return

            if path == "/api/quickfix/insert":
                body = _read_body(self)
                source = body.get("source", "")
                module = body.get("module", "")
                offset, text = compute_include_edit(source, module)
                new_source = source[:offset] + text + source[offset:]
                self._send(200, {"source": new_source, "offset": offset, "text": text})
                return

            if path == "/api/run/start":
                body = _read_body(self)
                saved = body.get("saved", False)
                if not saved:
                    raise ValueError("file must be saved before running (run saves it)")
                file_path = state.resolve_file(body["path"])
                if not file_path.is_file():
                    raise ValueError(f"file not found: {file_path}")
                run_id = state.runs.start(state.core_dir, state.modules_dir, file_path)
                self._send(200, {"runId": run_id})
                return

            if path.startswith("/api/run/"):
                parts = path.split("/")
                run_id = parts[3] if len(parts) > 3 else ""
                action = parts[4] if len(parts) > 4 else ""
                session = state.runs.get(run_id)
                if session is None:
                    self._send_error(404, "no such run")
                    return
                if action == "stop":
                    state.runs.stop(run_id)
                    self._send(200, {"stopped": True})
                    return
                if action == "status":
                    self._send(200, session.status())
                    return
                if action == "output":
                    since = int(self.path.split("since=")[-1]) if "since=" in self.path else 0
                    lines, count = session.output_since(since)
                    self._send(200, {"lines": lines, "count": count, "done": session.finished})
                    return
                self._send_error(404, f"unknown run action: {action}")
                return

            self._send_error(404, f"unknown endpoint: {path}")
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._send_error(400, str(error))
        except OSError as error:
            self._send_error(500, f"filesystem error: {error}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()


def build_server(port: int = 8742, core_dir: Path | None = None) -> ThreadingHTTPServer:
    discovered_core = core.setup_core()
    if core_dir is None and discovered_core is not None:
        core_dir = discovered_core
    if core_dir is None:
        import resiris

        core_dir = Path(resiris.__file__).resolve().parent.parent

    modules_dir = core_dir / "Modules"
    state = IdeState(core_dir, modules_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), IdeHandler)
    server.state = state
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Resiris IDE backend")
    parser.add_argument("--port", type=int, default=8742)
    parser.add_argument("--core", type=Path, default=None, help="Resiris PyResy directory")
    args = parser.parse_args()

    server = build_server(port=args.port, core_dir=args.core)
    print(f"Resiris IDE backend listening on http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state: IdeState = server.state
        state.runs.stop_all()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())