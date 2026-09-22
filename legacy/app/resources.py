"""Resource path resolution for dev mode and PyInstaller .app bundles."""

import sys
from pathlib import Path

# PyInstaller sets sys._MEIPASS to the temp extraction dir at runtime.
# In dev mode, fall back to the project root.
if getattr(sys, "_MEIPASS", None):
    _BASE = Path(sys._MEIPASS)
else:
    _BASE = Path(__file__).parent.parent


def get_resource_path(*parts: str) -> Path:
    """Resolve a path relative to the resource root.

    Usage:
        get_resource_path("config", "default.toml")
        get_resource_path("assets", "icon_menubar.png")
    """
    return _BASE.joinpath(*parts)
