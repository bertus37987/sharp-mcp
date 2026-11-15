"""Cross-platform Blender detection, auto-installation, addon setup, and bpy execution (Blender-only)."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:
    winreg = None  # type: ignore[assignment]


ENABLE_ADDON_PYTHON_EXPR = (
    "import addon_utils, bpy; "
    "addon_utils.enable('blender_mcp', default_set=True); "
    "bpy.ops.wm.save_userpref()"
)


def _parse_version_tuple(text: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", text)
    return tuple(int(n) for n in nums) if nums else (0,)


def _get_blender_user_config_root() -> Path:
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA", "").strip()
        base = Path(app_data) if app_data else (Path.home() / "AppData" / "Roaming")
        return base / "Blender Foundation" / "Blender"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Blender"
    xdg_cfg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_cfg) if xdg_cfg else (Path.home() / ".config")
    return base / "blender"


def _collect_windows_registry_blenders() -> List[Tuple[str, Path]]:
    if winreg is None or sys.platform != "win32":
        return []

    found: List[Tuple[str, Path]] = []
    uninstall_subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, uninstall_subkey),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, uninstall_subkey),
    ]

    for hive, subkey_path in roots:
        try:
            with winreg.OpenKey(hive, subkey_path) as root_key:
                num_subkeys = winreg.QueryInfoKey(root_key)[0]
                for idx in range(num_subkeys):
                    try:
                        sub_name = winreg.EnumKey(root_key, idx)
                        with winreg.OpenKey(root_key, sub_name) as item_key:
                            try:
                                disp_name, _ = winreg.QueryValueEx(item_key, "DisplayName")
                            except OSError:
                                continue
                            if not isinstance(disp_name, str) or "blender" not in disp_name.lower():
                                continue

                            install_loc = ""
                            disp_icon = ""
                            try:
                                val, _ = winreg.QueryValueEx(item_key, "InstallLocation")
                                if isinstance(val, str):
                                    install_loc = val.strip().strip('"')
                            except OSError:
                                pass
                            try:
                                val, _ = winreg.QueryValueEx(item_key, "DisplayIcon")
                                if isinstance(val, str):
                                    disp_icon = val.strip().strip('"').split(",")[0]
                            except OSError:
                                pass

                            for raw_candidate in (
                                str(Path(install_loc) / "blender.exe") if install_loc else "",
                                disp_icon if disp_icon.lower().endswith("blender.exe") else "",
                            ):
                                if raw_candidate:
                                    p = Path(raw_candidate)
                                    if p.is_file():
                                        found.append(("windows_registry", p))
                    except OSError:
                        continue
        except OSError:
            continue

    return found


def _collect_blender_candidates() -> List[Tuple[str, Path]]:
    candidates: List[Tuple[str, Path]] = []

    env_path = os.environ.get("SHARP_BLENDER_PATH", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_dir():
            p = p / ("blender.exe" if sys.platform == "win32" else "blender")
        candidates.append(("env:SHARP_BLENDER_PATH", p))

    which_path = shutil.which("blender")
    if which_path:
        candidates.append(("PATH", Path(which_path)))

    if sys.platform == "win32":
        program_files_dirs = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        win_matches: List[Tuple[Tuple[int, ...], str, Path]] = []
        for pf in program_files_dirs:
            if not pf:
                continue
            bf_dir = Path(pf) / "Blender Foundation"
            if bf_dir.is_dir():
                for exe in bf_dir.glob("Blender */blender.exe"):
                    win_matches.append((_parse_version_tuple(exe.parent.name), "program_files", exe))
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            la_dir = Path(local_app) / "Programs" / "Blender Foundation"
            if la_dir.is_dir():
                for exe in la_dir.glob("*/blender.exe"):
                    win_matches.append((_parse_version_tuple(exe.parent.name), "localappdata_programs", exe))
        win_matches.sort(key=lambda item: item[0], reverse=True)
        for _, src, exe in win_matches:
            candidates.append((src, exe))
        candidates.extend(_collect_windows_registry_blenders())
    elif sys.platform == "darwin":
        candidates.append(("macos_applications", Path("/Applications/Blender.app/Contents/MacOS/Blender")))
        candidates.append(("macos_user_applications", Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"))
    else:
        for src, raw in (
            ("usr_bin", "/usr/bin/blender"),
            ("snap_bin", "/snap/bin/blender"),
            ("usr_local_bin", "/usr/local/bin/blender"),
            ("flatpak_user", str(Path.home() / ".local/share/flatpak/exports/bin/org.blender.Blender")),
            ("flatpak_system", "/var/lib/flatpak/exports/bin/org.blender.Blender"),
        ):
            candidates.append((src, Path(raw)))

    deduped: List[Tuple[str, Path]] = []
    seen: set[str] = set()
    for src, p in candidates:
        try:
            key = os.path.normcase(str(p.resolve()))
        except OSError:
            key = os.path.normcase(str(p))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((src, p))
    return deduped


def _probe_blender_version(executable: Path, timeout_sec: float = 10.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        proc = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        first_line = out.splitlines()[0].strip() if out else ""
        match = re.search(r"Blender\s+(\d+\.\d+(?:\.\d+)?)", out)
        if match:
            full_ver = match.group(1)
            parts = full_ver.split(".")
            major_minor = ".".join(parts[:2]) if len(parts) >= 2 else full_ver
            return first_line, full_ver, major_minor
        return first_line or None, None, None
    except (OSError, subprocess.SubprocessError):
        return None, None, None


def _parse_addon_protocol_version(file_paths: List[Path]) -> Optional[int]:
    for fp in file_paths:
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"ADDON_PROTOCOL_VERSION\s*=\s*(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def _inspect_blender_addons(major_minor: Optional[str]) -> Dict[str, Any]:
    config_root = _get_blender_user_config_root()
    version_dirs: List[Path] = []
    if major_minor and (config_root / major_minor).is_dir():
        version_dirs.append(config_root / major_minor)
    if config_root.is_dir():
        others = [d for d in config_root.iterdir() if d.is_dir() and re.match(r"^\d+\.\d+$", d.name)]
        others.sort(key=lambda d: _parse_version_tuple(d.name), reverse=True)
        for d in others:
            if d not in version_dirs:
                version_dirs.append(d)

    addon_installed = False
    addon_kind: Optional[str] = None
    addon_path: Optional[str] = None
    protocol_version: Optional[int] = None
    ext_mcp_present = False
    ext_mcp_path: Optional[str] = None
    inspected_ver_dir: Optional[str] = str(version_dirs[0]) if version_dirs else None

    for vdir in version_dirs:
        addons_dir = vdir / "scripts" / "addons"
        single_file = addons_dir / "blender_mcp.py"
        pkg_init = addons_dir / "blendermcp" / "__init__.py"
        ext_dir = vdir / "extensions" / "user_default" / "mcp"

        if ext_dir.is_dir():
            ext_mcp_present = True
            ext_mcp_path = str(ext_dir)
            if protocol_version is None:
                protocol_version = _parse_addon_protocol_version(
                    [ext_dir / "__init__.py", ext_dir / "mcp_to_blender_server.py", ext_dir / "cli.py"]
                )

        if single_file.is_file():
            addon_installed = True
            addon_kind = "scripts_addon_file"
            addon_path = str(single_file)
            proto = _parse_addon_protocol_version([single_file])
            if proto is not None:
                protocol_version = proto
            inspected_ver_dir = str(vdir)
            break

        if pkg_init.is_file():
            addon_installed = True
            addon_kind = "scripts_addon_pkg"
            addon_path = str(pkg_init)
            proto = _parse_addon_protocol_version([pkg_init, pkg_init.parent / "server.py"])
            if proto is not None:
                protocol_version = proto
            inspected_ver_dir = str(vdir)
            break

        if ext_dir.is_dir() and ((ext_dir / "__init__.py").is_file() or (ext_dir / "blender_manifest.toml").is_file()):
            addon_installed = True
            addon_kind = "extension_user_default"
            addon_path = str(ext_dir)
            inspected_ver_dir = str(vdir)
            break

    return {
        "config_root": str(config_root),
        "inspected_version_dir": inspected_ver_dir,
        "addon_installed": addon_installed,
        "addon_kind": addon_kind,
        "addon_path": addon_path,
        "addon_protocol_version": protocol_version,
        "extension_mcp_present": ext_mcp_present,
        "extension_mcp_path": ext_mcp_path,
    }


def _probe_blender_socket(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def detect_blender_installation() -> Dict[str, Any]:
    """Detect Blender executable, version, `blender_mcp` addon/extension, and TCP socket status."""
    candidates = _collect_blender_candidates()
    existing: List[Dict[str, str]] = []
    chosen_exe: Optional[Path] = None
    chosen_source: Optional[str] = None

    for src, path_obj in candidates:
        if path_obj.is_file():
            existing.append({"source": src, "path": str(path_obj)})
            if chosen_exe is None:
                chosen_exe = path_obj
                chosen_source = src

    version_raw: Optional[str] = None
    version_full: Optional[str] = None
    major_minor: Optional[str] = None
    if chosen_exe is not None:
        version_raw, version_full, major_minor = _probe_blender_version(chosen_exe)

    addon_info = _inspect_blender_addons(major_minor)
    host = os.environ.get("BLENDER_HOST", "localhost").strip() or "localhost"
    port = int(os.environ.get("BLENDER_PORT", "9876"))
    socket_reachable = _probe_blender_socket(host, port)

    return {
        "ok": True,
        "installed": chosen_exe is not None,
        "executable": str(chosen_exe) if chosen_exe else None,
        "source": chosen_source,
        "version_raw": version_raw,
        "version": version_full,
        "major_minor": major_minor,
        "candidates_found": existing,
        "uv_available": shutil.which("uv") is not None,
        "uvx_available": shutil.which("uvx") is not None,
        "socket_host": host,
        "socket_port": port,
        "socket_reachable": socket_reachable,
        **addon_info,
    }


def _platform_blender_install_command() -> Tuple[Optional[List[str]], Optional[str]]:
    if sys.platform == "win32":
        return (
            [
                "winget",
                "install",
                "--id",
                "BlenderFoundation.Blender",
                "-e",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            "winget",
        )
    if sys.platform == "darwin":
        return (["brew", "install", "--cask", "blender"], "brew")

    if shutil.which("snap"):
        return (["snap", "install", "blender", "--classic"], "snap")
    if shutil.which("flatpak"):
        return (["flatpak", "install", "-y", "flathub", "org.blender.Blender"], "flatpak")
    return (["snap", "install", "blender", "--classic"], None)


def ensure_blender_installed(
    auto_install: bool = True,
    install_addon: bool = True,
    enable_addon: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Ensure Blender and `mcp-for-blender` addon are installed & enabled headlessly."""
    detect = detect_blender_installation()
    install_cmd, pkg_mgr = _platform_blender_install_command()
    addon_cmd = ["uvx", "mcp-for-blender", "install-addon"]
    blender_bin = detect["executable"] or "blender"
    enable_cmd = [
        blender_bin,
        "--background",
        "--python-expr",
        ENABLE_ADDON_PYTHON_EXPR,
    ]

    planned_commands: List[List[str]] = []
    if not detect["installed"] and auto_install and install_cmd:
        planned_commands.append(install_cmd)
    if install_addon and not detect["addon_installed"]:
        planned_commands.append(addon_cmd)
    if enable_addon:
        planned_commands.append(enable_cmd)

    command_templates = {
        "install_blender": install_cmd,
        "install_addon": addon_cmd,
        "enable_addon": enable_cmd,
    }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "installed_before": detect["installed"],
            "addon_installed_before": detect["addon_installed"],
            "planned_commands": planned_commands,
            "command_templates": command_templates,
            "detected": detect,
        }

    executed_steps: List[Dict[str, Any]] = []

    if not detect["installed"]:
        if not auto_install:
            return {
                "ok": False,
                "code": "BLENDER_NOT_INSTALLED",
                "detected": detect,
                "planned_commands": planned_commands,
                "command_templates": command_templates,
                "message": "Blender is not installed and auto_install=False.",
            }
        if not install_cmd or (pkg_mgr is None) or (shutil.which(install_cmd[0]) is None):
            return {
                "ok": False,
                "code": "PACKAGE_MANAGER_MISSING",
                "command": install_cmd,
                "detected": detect,
                "message": (
                    f"Required package manager '{install_cmd[0] if install_cmd else 'unknown'}' "
                    "was not found to auto-install Blender."
                ),
            }
        proc = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        executed_steps.append({
            "step": "install_blender",
            "command": install_cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        })
        if proc.returncode != 0:
            return {
                "ok": False,
                "code": "BLENDER_INSTALL_FAILED",
                "executed_steps": executed_steps,
                "message": f"Blender installation command exited with code {proc.returncode}.",
            }
        detect = detect_blender_installation()
        if not detect["installed"]:
            return {
                "ok": False,
                "code": "BLENDER_NOT_FOUND_AFTER_INSTALL",
                "executed_steps": executed_steps,
                "detected": detect,
                "message": "Blender installer ran, but executable was not detected afterward.",
            }

    blender_bin = detect["executable"] or "blender"
    enable_cmd = [
        blender_bin,
        "--background",
        "--python-expr",
        ENABLE_ADDON_PYTHON_EXPR,
    ]

    if install_addon and not detect["addon_installed"]:
        if shutil.which("uvx") is None:
            return {
                "ok": False,
                "code": "UVX_NOT_FOUND",
                "command": addon_cmd,
                "executed_steps": executed_steps,
                "detected": detect,
                "message": "`uvx` is required to run `uvx mcp-for-blender install-addon`.",
            }
        proc = subprocess.run(
            addon_cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        executed_steps.append({
            "step": "install_addon",
            "command": addon_cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        })
        if proc.returncode != 0:
            return {
                "ok": False,
                "code": "ADDON_INSTALL_FAILED",
                "executed_steps": executed_steps,
                "message": f"Addon installation failed with exit code {proc.returncode}.",
            }
        detect = detect_blender_installation()

    if enable_addon and detect["installed"]:
        proc = subprocess.run(
            enable_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        executed_steps.append({
            "step": "enable_addon",
            "command": enable_cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        })
        if proc.returncode != 0:
            return {
                "ok": False,
                "code": "ADDON_ENABLE_FAILED",
                "executed_steps": executed_steps,
                "detected": detect,
                "message": f"Headless Blender addon enable failed with exit code {proc.returncode}.",
            }

    final_detect = detect_blender_installation()
    return {
        "ok": True,
        "dry_run": False,
        "executed_steps": executed_steps,
        "command_templates": command_templates,
        "detected": final_detect,
    }


def _execute_bpy_via_socket(
    code: str,
    host: str,
    port: int,
    timeout_sec: float,
) -> Dict[str, Any]:
    payload = json.dumps({"type": "execute_code", "params": {"code": code}}).encode("utf-8")
    connect_timeout = min(2.0, max(0.25, float(timeout_sec)))
    with socket.create_connection((host, int(port)), timeout=connect_timeout) as sock:
        sock.settimeout(float(timeout_sec))
        sock.sendall(payload)
        chunks: List[bytes] = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
            raw = b"".join(chunks)
            try:
                parsed = json.loads(raw.decode("utf-8"))
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        else:
            raw = b"".join(chunks)
            parsed = json.loads(raw.decode("utf-8")) if raw else {}

    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "mode": "socket",
            "code": "INVALID_SOCKET_RESPONSE",
            "host": host,
            "port": port,
            "raw": parsed,
        }

    status = parsed.get("status")
    result_obj = parsed.get("result")
    if status == "success" or (isinstance(result_obj, dict) and result_obj.get("executed") is True):
        stdout_text = result_obj.get("result", "") if isinstance(result_obj, dict) else ""
        return {
            "ok": True,
            "mode": "socket",
            "host": host,
            "port": port,
            "stdout": stdout_text,
            "response": parsed,
        }

    return {
        "ok": False,
        "mode": "socket",
        "code": "BLENDER_SOCKET_EXEC_ERROR",
        "host": host,
        "port": port,
        "message": parsed.get("message", "Blender socket command failed."),
        "response": parsed,
    }


def execute_bpy_over_socket_or_headless(
    code: str,
    host: str = "localhost",
    port: int = 9876,
    mode: str = "auto",
    auto_install: bool = False,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    """Execute Blender `bpy` Python code over live `mcp-for-blender` TCP socket or headless CLI."""
    if mode not in ("auto", "socket", "headless"):
        return {
            "ok": False,
            "code": "INVALID_EXECUTION_MODE",
            "mode": mode,
            "message": "mode must be one of 'auto', 'socket', or 'headless'.",
        }

    socket_error: Optional[str] = None
    if mode in ("auto", "socket"):
        try:
            return _execute_bpy_via_socket(code=code, host=host, port=port, timeout_sec=timeout_sec)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            socket_error = str(exc)
            if mode == "socket":
                return {
                    "ok": False,
                    "mode": "socket",
                    "code": "BLENDER_SOCKET_UNAVAILABLE",
                    "host": host,
                    "port": port,
                    "message": socket_error,
                }

    detect = detect_blender_installation()
    if not detect["installed"] and auto_install:
        ensure_res = ensure_blender_installed(
            auto_install=True,
            install_addon=False,
            enable_addon=False,
            dry_run=False,
        )
        if not ensure_res.get("ok"):
            return {
                "ok": False,
                "mode": "headless",
                "code": ensure_res.get("code", "BLENDER_INSTALL_FAILED"),
                "socket_fallback_reason": socket_error,
                "install_result": ensure_res,
                "message": ensure_res.get("message", "Blender auto-install failed."),
            }
        detect = ensure_res.get("detected") or detect_blender_installation()

    blender_exe = detect.get("executable")
    if not blender_exe:
        return {
            "ok": False,
            "mode": "headless",
            "code": "BLENDER_NOT_INSTALLED",
            "socket_fallback_reason": socket_error,
            "message": (
                "Blender is not installed locally. Run `sharp-mcp install-blender` "
                "or pass `auto_install=True`."
            ),
        }

    with tempfile.TemporaryDirectory(prefix="sharp_bpy_") as tmp_dir:
        script_path = Path(tmp_dir) / "sharp_task.py"
        script_path.write_text(code, encoding="utf-8")
        cmd = [
            str(blender_exe),
            "--background",
            "--python-exit-code",
            "1",
            "--python",
            str(script_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=float(timeout_sec),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "mode": "headless",
                "code": "BLENDER_HEADLESS_TIMEOUT",
                "executable": str(blender_exe),
                "socket_fallback_reason": socket_error,
                "message": f"Headless Blender execution timed out after {timeout_sec}s.",
                "stdout": exc.stdout or "" if isinstance(exc.stdout, str) else "",
                "stderr": exc.stderr or "" if isinstance(exc.stderr, str) else "",
            }

    return {
        "ok": proc.returncode == 0,
        "mode": "headless",
        "executable": str(blender_exe),
        "version": detect.get("version"),
        "returncode": proc.returncode,
        "socket_fallback_reason": socket_error,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
