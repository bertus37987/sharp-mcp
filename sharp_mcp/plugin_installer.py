"""Cross-platform Roblox Studio Companion Plugin installer (`SharpBridgePlugin.rbxmx`)."""

from __future__ import annotations

import hashlib
import importlib.resources
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_FILENAME = "SharpBridgePlugin.rbxmx"
LEGACY_PLUGIN_FILENAME = "ForgeBridgePlugin.rbxmx"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def get_plugin_source_path() -> Path:
    """Resolve the bundled `SharpBridgePlugin.rbxmx` source path cleanly across repo & wheel installs."""
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent
    candidates = [
        repo_root / "studio_plugin" / PLUGIN_FILENAME,
        pkg_dir / "studio_plugin" / PLUGIN_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    try:
        res = importlib.resources.files("sharp_mcp").joinpath("studio_plugin", PLUGIN_FILENAME)
        res_path = Path(str(res))
        if res_path.is_file():
            return res_path
    except Exception:
        pass

    return candidates[0]


def get_roblox_plugins_dir(target_dir: Optional[str | Path] = None) -> Path:
    """Return the platform-specific Roblox Studio Plugins directory (or explicit override)."""
    if target_dir is not None:
        return Path(target_dir).expanduser().resolve()

    env_override = os.environ.get("SHARP_ROBLOX_PLUGINS_DIR", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        return base / "Roblox" / "Plugins"

    if sys.platform == "darwin":
        return Path.home() / "Documents" / "Roblox" / "Plugins"

    xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
    return base / "Roblox" / "Plugins"


def get_plugin_install_status(target_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """Inspect source plugin bundle, installed Studio plugin SHA-256, and legacy plugin presence."""
    source_path = get_plugin_source_path()
    plugins_dir = get_roblox_plugins_dir(target_dir)
    installed_path = plugins_dir / PLUGIN_FILENAME
    legacy_path = plugins_dir / LEGACY_PLUGIN_FILENAME

    source_exists = source_path.is_file()
    source_sha256 = _sha256_file(source_path) if source_exists else None
    source_size = source_path.stat().st_size if source_exists else None

    installed = installed_path.is_file()
    installed_sha256 = _sha256_file(installed_path) if installed else None
    installed_size = installed_path.stat().st_size if installed else None

    up_to_date = bool(
        source_exists and installed and source_sha256 is not None and source_sha256 == installed_sha256
    )

    return {
        "ok": True,
        "platform": sys.platform,
        "plugin_filename": PLUGIN_FILENAME,
        "source_path": str(source_path),
        "source_exists": source_exists,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size,
        "plugins_dir": str(plugins_dir),
        "plugins_dir_exists": plugins_dir.is_dir(),
        "installed_path": str(installed_path),
        "installed": installed,
        "installed_sha256": installed_sha256,
        "installed_size_bytes": installed_size,
        "up_to_date": up_to_date,
        "legacy_filename": LEGACY_PLUGIN_FILENAME,
        "legacy_path": str(legacy_path),
        "legacy_present": legacy_path.is_file(),
    }


def install_studio_plugin(
    target_dir: Optional[str | Path] = None,
    prune_legacy: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Install `SharpBridgePlugin.rbxmx` into Roblox Studio Plugins with SHA-256 verification."""
    source_path = get_plugin_source_path()
    plugins_dir = get_roblox_plugins_dir(target_dir)
    dest_path = plugins_dir / PLUGIN_FILENAME
    legacy_path = plugins_dir / LEGACY_PLUGIN_FILENAME

    if not source_path.is_file():
        return {
            "ok": False,
            "code": "PLUGIN_SOURCE_MISSING",
            "source_path": str(source_path),
            "dest_path": str(dest_path),
            "dry_run": dry_run,
            "message": (
                f"Bundled plugin file not found at {source_path}. "
                "Build it with studio_plugin/build_plugin_rbxmx.py first."
            ),
        }

    source_sha256 = _sha256_file(source_path)
    existing_sha256 = _sha256_file(dest_path) if dest_path.is_file() else None
    already_matching = existing_sha256 == source_sha256
    legacy_present = legacy_path.is_file()

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "action": "already_up_to_date" if already_matching else ("would_update" if dest_path.is_file() else "would_install"),
            "source_path": str(source_path),
            "dest_path": str(dest_path),
            "plugins_dir": str(plugins_dir),
            "source_sha256": source_sha256,
            "existing_sha256": existing_sha256,
            "would_copy": not already_matching,
            "would_prune_legacy": bool(prune_legacy and legacy_present),
            "legacy_path": str(legacy_path),
            "legacy_present": legacy_present,
        }

    plugins_dir.mkdir(parents=True, exist_ok=True)
    action = "already_up_to_date"
    if not already_matching:
        action = "updated" if dest_path.is_file() else "installed"
        tmp_path = plugins_dir / f".{PLUGIN_FILENAME}.tmp.{os.getpid()}"
        try:
            shutil.copyfile(source_path, tmp_path)
            os.replace(tmp_path, dest_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    installed_sha256 = _sha256_file(dest_path)
    if installed_sha256 != source_sha256:
        return {
            "ok": False,
            "code": "SHA256_MISMATCH",
            "source_path": str(source_path),
            "dest_path": str(dest_path),
            "expected_sha256": source_sha256,
            "actual_sha256": installed_sha256,
            "message": "Installed plugin SHA-256 verification failed after copy.",
        }

    pruned_legacy = False
    if prune_legacy and legacy_path.is_file():
        legacy_path.unlink()
        pruned_legacy = True

    return {
        "ok": True,
        "dry_run": False,
        "action": action,
        "source_path": str(source_path),
        "dest_path": str(dest_path),
        "plugins_dir": str(plugins_dir),
        "sha256": installed_sha256,
        "sha256_verified": True,
        "pruned_legacy": pruned_legacy,
        "legacy_path": str(legacy_path),
        "status": get_plugin_install_status(target_dir=plugins_dir),
    }
