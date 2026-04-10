from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

__all__ = ["__version__"]


def _version_from_pyproject() -> str:
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("version", "0.0.0-dev"))
    except Exception:  # noqa: BLE001
        return "0.0.0-dev"


_pyproject_version = _version_from_pyproject()
if _pyproject_version != "0.0.0-dev":
    __version__ = _pyproject_version
else:
    try:
        __version__ = version("slack-mirror")
    except PackageNotFoundError:
        __version__ = _version_from_pyproject()
