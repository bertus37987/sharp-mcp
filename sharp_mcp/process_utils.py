"""Shared subprocess helpers for Sharp MCP engines."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict


def detached_subprocess_kwargs() -> Dict[str, Any]:
    """Return subprocess kwargs preventing Windows MCP stdio pipe inheritance and console popups."""
    kwargs: Dict[str, Any] = {"stdin": subprocess.DEVNULL}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs
