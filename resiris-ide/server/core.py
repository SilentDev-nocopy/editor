"""Locate and set up the real Resiris language core (PyResy).

The IDE reuses the actual Resiris tokenizer / parser / AST / interpreter from
the Resiris project -- it must never reimplement the language itself.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


DEFAULT_CORE_PATHS = [
    Path.home() / "Projects" / "Resiris" / "PyResy",
    Path(os.environ.get("HOME", "/")) / "Projects" / "Resiris" / "PyResy",
]


def _is_core_dir(path: Path) -> bool:
    return path.is_dir() and (path / "resiris").is_dir()


def find_core_dir() -> Path | None:
    env = os.environ.get("RESIRIS_CORE")
    if env:
        candidate = Path(env)
        if _is_core_dir(candidate):
            return candidate
        if (candidate / "PyResy").is_dir() and _is_core_dir(candidate / "PyResy"):
            return candidate / "PyResy"

    for candidate in DEFAULT_CORE_PATHS:
        if _is_core_dir(candidate):
            return candidate

    if importlib.util.find_spec("resiris") is not None:
        return None

    return None


def setup_core() -> Path | None:
    """Return the Resiris core directory, adding it to sys.path if needed."""
    core_dir = find_core_dir()

    if core_dir is not None:
        sys.path.insert(0, str(core_dir))
        return core_dir

    return None


def resiris_version() -> str:
    import resiris

    package_dir = Path(resiris.__file__).resolve().parent.parent
    pyproject = package_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            version = tomllib.loads(pyproject.read_text(encoding="utf-8")).get(
                "project", {}
            ).get("version")
            if isinstance(version, str):
                return version
        except Exception:
            pass
    return "unknown"