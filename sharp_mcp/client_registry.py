"""Multi-client MCP registration & inspection for Sharp (Antigravity, Claude Desktop, Claude Code, Codex, OpenCode, Devin)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .credentials_store import get_api_key, get_credentials_status, mask_api_key, resolve_credentials_path

SUPPORTED_CLIENTS: Tuple[str, ...] = (
    "antigravity",
    "claude-desktop",
    "claude-code",
    "codex",
    "opencode",
    "devin",
)

LEGACY_SERVER_NAMES: Tuple[str, ...] = (
    "Roblox_Forge",
    "roblox_forge",
    "roblox-forge-mcp",
)


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def normalize_client_name(name: str) -> str:
    cleaned = name.strip().lower().replace("_", "-")
    aliases = {
        "antigravity": "antigravity",
        "agy": "antigravity",
        "claude-desktop": "claude-desktop",
        "claudedesktop": "claude-desktop",
        "claude-code": "claude-code",
        "claudecode": "claude-code",
        "codex": "codex",
        "opencode": "opencode",
        "devin": "devin",
    }
    return aliases.get(cleaned, cleaned)


def strip_jsonc_comments(text: str) -> str:
    """Strip `//` line comments, `/* ... */` block comments, and trailing commas safely outside JSON strings."""
    out: List[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in ("\r", "\n"):
                i += 1
            continue

        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1

    no_comments = "".join(out)

    # Remove trailing commas before `}` or `]` outside string literals
    final_chars: List[str] = []
    in_string = False
    escape = False
    m = len(no_comments)
    j = 0
    while j < m:
        ch = no_comments[j]
        if in_string:
            final_chars.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            j += 1
            continue

        if ch == '"':
            in_string = True
            final_chars.append(ch)
            j += 1
            continue

        if ch == ",":
            k = j + 1
            while k < m and no_comments[k] in " \t\r\n":
                k += 1
            if k < m and no_comments[k] in "}]":
                j += 1
                continue

        final_chars.append(ch)
        j += 1

    return "".join(final_chars)


def build_server_spec(
    launcher: str = "auto",
    profile: str = "full",
    project_dir: Optional[str | Path] = None,
    bridge_host: str = "127.0.0.1",
    bridge_port: int = 58421,
    package_root: Optional[str | Path] = None,
    python_executable: Optional[str] = None,
    include_api_keys: bool = False,
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Build normalized command/args/env launch specification for Sharp MCP."""
    if launcher not in ("auto", "npx", "uvx", "python"):
        raise ValueError(f"Unsupported launcher '{launcher}'. Expected auto|npx|uvx|python.")
    if profile not in ("full", "core", "blender"):
        raise ValueError(f"Unsupported profile '{profile}'. Expected full|core|blender.")

    root = Path(package_root).expanduser().resolve() if package_root else _package_root()
    wrapper_mjs = root / "bin" / "sharp-mcp.mjs"
    serve_args = ["serve", "--profile", profile]

    cred_file = resolve_credentials_path(credentials_path)
    env: Dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "SHARP_BRIDGE_HOST": str(bridge_host),
        "SHARP_BRIDGE_PORT": str(int(bridge_port)),
        "SHARP_CREDENTIALS_PATH": str(cred_file),
    }
    if include_api_keys:
        gem_key = get_api_key("gemini", credentials_path=cred_file)
        if gem_key:
            env["GEMINI_API_KEY"] = gem_key
        or_key = get_api_key("openrouter", credentials_path=cred_file)
        if or_key:
            env["OPENROUTER_API_KEY"] = or_key
        oc_key = get_api_key("roblox_open_cloud", credentials_path=cred_file)
        if oc_key:
            env["ROBLOX_OPEN_CLOUD_API_KEY"] = oc_key
        creator_id = get_credentials_status(cred_file).get("roblox_creator_id")
        if creator_id:
            env["ROBLOX_CREATOR_ID"] = str(creator_id)
    if project_dir:
        resolved_proj = str(Path(project_dir).expanduser().resolve())
        env["SHARP_PROJECT_DIR"] = resolved_proj
        serve_args.extend(["--project-dir", resolved_proj])

    chosen_launcher = launcher
    if launcher == "auto":
        if shutil.which("node") and wrapper_mjs.is_file():
            chosen_launcher = "node-wrapper"
        elif shutil.which("uvx"):
            chosen_launcher = "uvx"
        else:
            chosen_launcher = "python"

    if chosen_launcher == "node-wrapper":
        command = "node"
        args = [str(wrapper_mjs), *serve_args]
    elif chosen_launcher == "npx":
        command = "npx"
        args = ["--yes", str(root), *serve_args]
    elif chosen_launcher == "uvx":
        command = "uvx"
        args = ["--from", str(root), "sharp-mcp", *serve_args]
    else:
        command = python_executable or sys.executable or "python"
        args = ["-m", "sharp_mcp.cli", *serve_args]
        env["PYTHONPATH"] = str(root)

    return {
        "launcher": chosen_launcher,
        "requested_launcher": launcher,
        "profile": profile,
        "command": command,
        "args": args,
        "env": env,
    }


def _atomic_write_with_backup(path: Path, content: str) -> Optional[Path]:
    """Atomically write UTF-8 text to `path`, creating `.bak` if the file already existed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if path.is_file():
        backup_path = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup_path)

    tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp_path.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return backup_path


def _resolve_bases(
    home_dir: Optional[str | Path] = None,
    config_root: Optional[str | Path] = None,
) -> Tuple[Path, Optional[Path], bool]:
    """Return `(home, config_root, isolated_home_mode)` safely for real or test roots."""
    isolated = home_dir is not None or config_root is not None
    if home_dir is not None:
        home = Path(home_dir).expanduser().resolve()
    elif config_root is not None:
        home = Path(config_root).expanduser().resolve()
    else:
        home = Path.home()

    cfg_root = Path(config_root).expanduser().resolve() if config_root is not None else None
    return home, cfg_root, isolated


def _resolve_antigravity_targets(
    home: Path,
    cfg_root: Optional[Path],
    project: bool,
    project_dir: Optional[Path],
) -> List[Path]:
    if cfg_root is not None:
        base_gemini = cfg_root / ".gemini" if (cfg_root / ".gemini").is_dir() else cfg_root
        targets = [base_gemini / "antigravity" / "mcp_config.json"]
        if (base_gemini / "config").is_dir() or base_gemini.name == ".gemini":
            targets.append(base_gemini / "config" / "mcp_config.json")
        if (cfg_root / ".antigravity").is_dir():
            targets.append(cfg_root / ".antigravity" / "mcp_config.json")
    else:
        gemini_dir = home / ".gemini"
        gemini_existed = gemini_dir.is_dir()
        targets = [gemini_dir / "antigravity" / "mcp_config.json"]
        if gemini_existed or (gemini_dir / "config").is_dir() or (gemini_dir / "config" / "mcp_config.json").is_file():
            targets.append(gemini_dir / "config" / "mcp_config.json")
        if (home / ".antigravity").is_dir() or (home / ".antigravity" / "mcp_config.json").is_file():
            targets.append(home / ".antigravity" / "mcp_config.json")

    if project and project_dir is not None:
        ws_path = project_dir / ".antigravity" / "mcp_config.json"
        if ws_path not in targets:
            targets.append(ws_path)
    elif project_dir is not None and (project_dir / ".antigravity").is_dir():
        ws_path = project_dir / ".antigravity" / "mcp_config.json"
        if ws_path not in targets:
            targets.append(ws_path)

    return targets


def _resolve_claude_desktop_target(
    home: Path,
    cfg_root: Optional[Path],
    isolated: bool,
) -> Path:
    if cfg_root is not None:
        return cfg_root / "Claude" / "claude_desktop_config.json"

    if sys.platform == "win32":
        if isolated:
            app_data = home / "AppData" / "Roaming"
        else:
            env_ap = os.environ.get("APPDATA", "").strip()
            app_data = Path(env_ap) if env_ap else (home / "AppData" / "Roaming")
        return app_data / "Claude" / "claude_desktop_config.json"

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"

    if isolated:
        xdg_cfg = home / ".config"
    else:
        env_xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
        xdg_cfg = Path(env_xdg) if env_xdg else (home / ".config")
    return xdg_cfg / "Claude" / "claude_desktop_config.json"


def _resolve_devin_target(
    home: Path,
    cfg_root: Optional[Path],
    isolated: bool,
) -> Path:
    if cfg_root is not None:
        return cfg_root / "Devin" / "mcp_config.json"

    if sys.platform == "win32":
        if isolated:
            app_data = home / "AppData" / "Roaming"
        else:
            env_ap = os.environ.get("APPDATA", "").strip()
            app_data = Path(env_ap) if env_ap else (home / "AppData" / "Roaming")
        return app_data / "Devin" / "mcp_config.json"

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Devin" / "mcp_config.json"

    if isolated:
        xdg_cfg = home / ".config"
    else:
        env_xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
        xdg_cfg = Path(env_xdg) if env_xdg else (home / ".config")
    return xdg_cfg / "Devin" / "mcp_config.json"


def _resolve_claude_code_target(
    home: Path,
    cfg_root: Optional[Path],
    project: bool,
    project_dir: Optional[Path],
) -> Path:
    if project:
        proj_base = project_dir or Path.cwd()
        return proj_base / ".mcp.json"
    base = cfg_root if (cfg_root is not None and not (home / ".claude.json").is_file()) else home
    return base / ".claude.json"


def _resolve_codex_target(
    home: Path,
    cfg_root: Optional[Path],
    isolated: bool,
    project: bool,
    project_dir: Optional[Path],
) -> Path:
    if project and project_dir is not None:
        return project_dir / ".codex" / "config.toml"
    if cfg_root is not None:
        if (cfg_root / "config.toml").is_file():
            return cfg_root / "config.toml"
        return cfg_root / ".codex" / "config.toml"
    if not isolated:
        codex_home = os.environ.get("CODEX_HOME", "").strip()
        if codex_home:
            return Path(codex_home).expanduser().resolve() / "config.toml"
    return home / ".codex" / "config.toml"


def _resolve_opencode_target(
    home: Path,
    cfg_root: Optional[Path],
    isolated: bool,
    project: bool,
    project_dir: Optional[Path],
) -> Path:
    if project:
        base_dir = project_dir or Path.cwd()
    elif cfg_root is not None:
        base_dir = cfg_root / "opencode"
    else:
        if isolated:
            xdg_cfg = home / ".config"
        else:
            env_xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
            xdg_cfg = Path(env_xdg) if env_xdg else (home / ".config")
        base_dir = xdg_cfg / "opencode"

    jsonc = base_dir / "opencode.jsonc"
    if jsonc.is_file():
        return jsonc
    return base_dir / "opencode.json"


def _update_json_mcp_servers(
    target_path: Path,
    server_key: str,
    server_entry: Dict[str, Any],
    prune_legacy: bool,
    dry_run: bool,
    schema_url: Optional[str] = None,
    use_opencode_v2: bool = False,
) -> Dict[str, Any]:
    existed = target_path.is_file()
    data: Dict[str, Any] = {}
    if existed:
        raw = target_path.read_text(encoding="utf-8").strip()
        if raw:
            cleaned = strip_jsonc_comments(raw) if (use_opencode_v2 or target_path.suffix.lower() == ".jsonc") else raw
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object in {target_path}, got {type(parsed).__name__}")
            data = parsed

    pruned: List[str] = []
    if use_opencode_v2:
        if schema_url and "$schema" not in data:
            ordered: Dict[str, Any] = {"$schema": schema_url}
            ordered.update(data)
            data = ordered
        mcp_block = data.setdefault("mcp", {})
        if not isinstance(mcp_block, dict):
            raise ValueError(f"Expected object at 'mcp' in {target_path}")
        servers = mcp_block.setdefault("servers", {})
        if not isinstance(servers, dict):
            raise ValueError(f"Expected object at 'mcp.servers' in {target_path}")
    else:
        servers = data.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError(f"Expected object at 'mcpServers' in {target_path}")

    if prune_legacy:
        for legacy in LEGACY_SERVER_NAMES:
            if legacy in servers:
                servers.pop(legacy, None)
                pruned.append(legacy)
            if use_opencode_v2 and legacy in mcp_block and legacy != "servers":
                mcp_block.pop(legacy, None)
                pruned.append(f"mcp.{legacy}")

    servers[server_key] = server_entry
    rendered = json.dumps(data, indent=2) + "\n"

    backup_path: Optional[Path] = None
    if not dry_run:
        backup_path = _atomic_write_with_backup(target_path, rendered)

    redacted_entry = json.loads(json.dumps(server_entry))
    for env_field in ("env", "environment"):
        env_map = redacted_entry.get(env_field)
        if isinstance(env_map, dict):
            for secret_k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "ROBLOX_OPEN_CLOUD_API_KEY", "ROBLOX_API_KEY"):
                if secret_k in env_map and env_map[secret_k]:
                    env_map[secret_k] = mask_api_key(str(env_map[secret_k])) or "***"

    return {
        "path": str(target_path),
        "existed": existed,
        "written": not dry_run,
        "backup_path": str(backup_path) if backup_path else None,
        "server_key": server_key,
        "pruned_legacy": pruned,
        "entry": redacted_entry,
    }


def _strip_toml_tables(raw_text: str, table_names: Iterable[str]) -> Tuple[str, List[str]]:
    """Remove specified TOML `[table]` blocks while preserving all surrounding comments and tables."""
    normalized_targets = {t.strip().lower() for t in table_names}
    lines = raw_text.splitlines(keepends=True)
    kept: List[str] = []
    removed: List[str] = []
    skipping = False

    header_re = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
    for line in lines:
        m = header_re.match(line)
        if m:
            raw_header = m.group(1).strip()
            norm_header = raw_header.replace('"', "").replace("'", "").lower()
            if norm_header in normalized_targets:
                skipping = True
                removed.append(raw_header)
                continue
            skipping = False
        if not skipping:
            kept.append(line)

    result = "".join(kept).rstrip()
    return (result + "\n") if result else "", removed


def _format_toml_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, list):
        items = ", ".join(_format_toml_value(x) for x in val)
        return f"[{items}]"
    return json.dumps(str(val))


def _update_codex_toml(
    target_path: Path,
    spec: Dict[str, Any],
    prune_legacy: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    existed = target_path.is_file()
    raw_text = target_path.read_text(encoding="utf-8") if existed else ""
    if raw_text.strip():
        tomllib.loads(raw_text)

    tables_to_strip = [
        "mcp_servers.sharp",
        "mcp_servers.sharp.env",
    ]
    if prune_legacy:
        for legacy in LEGACY_SERVER_NAMES:
            tables_to_strip.append(f"mcp_servers.{legacy}")
            tables_to_strip.append(f"mcp_servers.{legacy}.env")

    cleaned_text, removed_headers = _strip_toml_tables(raw_text, tables_to_strip)

    block_lines = [
        "[mcp_servers.sharp]",
        "enabled = true",
        f"command = {_format_toml_value(spec['command'])}",
        f"args = {_format_toml_value(spec['args'])}",
        "",
        "[mcp_servers.sharp.env]",
    ]
    for k, v in spec["env"].items():
        block_lines.append(f"{k} = {_format_toml_value(v)}")
    block_text = "\n".join(block_lines) + "\n"

    if cleaned_text.strip():
        final_text = cleaned_text.rstrip() + "\n\n" + block_text
    else:
        final_text = block_text

    # Validate syntax strictly before touching disk
    tomllib.loads(final_text)

    backup_path: Optional[Path] = None
    if not dry_run:
        backup_path = _atomic_write_with_backup(target_path, final_text)

    pruned_legacy = [
        h for h in removed_headers if any(leg.lower() in h.lower() for leg in LEGACY_SERVER_NAMES)
    ]
    return {
        "path": str(target_path),
        "existed": existed,
        "written": not dry_run,
        "backup_path": str(backup_path) if backup_path else None,
        "server_key": "sharp",
        "pruned_legacy": pruned_legacy,
        "toml_verified": True,
    }


def register_client(
    client: str,
    launcher: str = "auto",
    profile: str = "full",
    home_dir: Optional[str | Path] = None,
    config_root: Optional[str | Path] = None,
    project: bool = False,
    project_dir: Optional[str | Path] = None,
    bridge_host: str = "127.0.0.1",
    bridge_port: int = 58421,
    prune_legacy: bool = True,
    dry_run: bool = False,
    package_root: Optional[str | Path] = None,
    python_executable: Optional[str] = None,
    include_api_keys: bool = False,
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Register Sharp MCP in one supported client configuration file."""
    canonical = normalize_client_name(client)
    if canonical not in SUPPORTED_CLIENTS:
        return {
            "ok": False,
            "code": "UNKNOWN_CLIENT",
            "client": client,
            "supported_clients": list(SUPPORTED_CLIENTS),
            "message": f"Unsupported client '{client}'. Supported: {', '.join(SUPPORTED_CLIENTS)}",
        }

    spec = build_server_spec(
        launcher=launcher,
        profile=profile,
        project_dir=project_dir,
        bridge_host=bridge_host,
        bridge_port=bridge_port,
        package_root=package_root,
        python_executable=python_executable,
        include_api_keys=include_api_keys,
        credentials_path=credentials_path,
    )
    home, cfg_root, isolated = _resolve_bases(home_dir=home_dir, config_root=config_root)
    proj_path = Path(project_dir).expanduser().resolve() if project_dir else None

    standard_entry = {
        "command": spec["command"],
        "args": spec["args"],
        "env": spec["env"],
    }
    opencode_entry = {
        "type": "local",
        "command": [spec["command"], *spec["args"]],
        "environment": spec["env"],
        "disabled": False,
    }

    try:
        files_updated: List[Dict[str, Any]] = []
        if canonical == "antigravity":
            targets = _resolve_antigravity_targets(home, cfg_root, project, proj_path)
            for target in targets:
                files_updated.append(
                    _update_json_mcp_servers(
                        target_path=target,
                        server_key="Sharp",
                        server_entry=standard_entry,
                        prune_legacy=prune_legacy,
                        dry_run=dry_run,
                    )
                )
        elif canonical == "claude-desktop":
            target = _resolve_claude_desktop_target(home, cfg_root, isolated)
            files_updated.append(
                _update_json_mcp_servers(
                    target_path=target,
                    server_key="Sharp",
                    server_entry=standard_entry,
                    prune_legacy=prune_legacy,
                    dry_run=dry_run,
                )
            )
        elif canonical == "claude-code":
            target = _resolve_claude_code_target(home, cfg_root, project, proj_path)
            files_updated.append(
                _update_json_mcp_servers(
                    target_path=target,
                    server_key="Sharp",
                    server_entry=standard_entry,
                    prune_legacy=prune_legacy,
                    dry_run=dry_run,
                )
            )
        elif canonical == "codex":
            target = _resolve_codex_target(home, cfg_root, isolated, project, proj_path)
            files_updated.append(
                _update_codex_toml(
                    target_path=target,
                    spec=spec,
                    prune_legacy=prune_legacy,
                    dry_run=dry_run,
                )
            )
        elif canonical == "opencode":
            target = _resolve_opencode_target(home, cfg_root, isolated, project, proj_path)
            files_updated.append(
                _update_json_mcp_servers(
                    target_path=target,
                    server_key="sharp",
                    server_entry=opencode_entry,
                    prune_legacy=prune_legacy,
                    dry_run=dry_run,
                    schema_url="https://opencode.ai/config.json",
                    use_opencode_v2=True,
                )
            )
        elif canonical == "devin":
            target = _resolve_devin_target(home, cfg_root, isolated)
            files_updated.append(
                _update_json_mcp_servers(
                    target_path=target,
                    server_key="Sharp",
                    server_entry=standard_entry,
                    prune_legacy=prune_legacy,
                    dry_run=dry_run,
                )
            )
    except Exception as exc:
        return {
            "ok": False,
            "code": "CONFIG_UPDATE_ERROR",
            "client": canonical,
            "dry_run": dry_run,
            "message": str(exc),
        }

    return {
        "ok": True,
        "client": canonical,
        "dry_run": dry_run,
        "launcher": spec["launcher"],
        "profile": spec["profile"],
        "files": files_updated,
    }


def register_clients(
    clients: Optional[Sequence[str] | str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Register Sharp MCP across one, many, or `'all'` supported clients."""
    if clients is None or clients == "all" or (isinstance(clients, (list, tuple, set)) and "all" in clients):
        target_clients = list(SUPPORTED_CLIENTS)
    elif isinstance(clients, str):
        target_clients = [c.strip() for c in clients.split(",") if c.strip()]
    else:
        target_clients = list(clients)

    results: Dict[str, Any] = {}
    all_ok = True
    for client_name in target_clients:
        res = register_client(client_name, **kwargs)
        results[client_name] = res
        if not res.get("ok"):
            all_ok = False

    return {
        "ok": all_ok,
        "dry_run": bool(kwargs.get("dry_run", False)),
        "clients": results,
    }


def _inspect_json_file_status(path: Path, server_key: str, use_opencode_v2: bool = False) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "registered": False,
        "legacy_present": [],
        "error": None,
    }
    if not path.is_file():
        return info
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return info
        cleaned = strip_jsonc_comments(raw) if (use_opencode_v2 or path.suffix.lower() == ".jsonc") else raw
        parsed = json.loads(cleaned)
        if use_opencode_v2:
            servers = parsed.get("mcp", {}).get("servers", {}) if isinstance(parsed, dict) else {}
        else:
            servers = parsed.get("mcpServers", {}) if isinstance(parsed, dict) else {}
        if isinstance(servers, dict):
            info["registered"] = server_key in servers
            info["legacy_present"] = [leg for leg in LEGACY_SERVER_NAMES if leg in servers]
            if server_key in servers:
                redacted = json.loads(json.dumps(servers[server_key]))
                if isinstance(redacted, dict):
                    for env_field in ("env", "environment"):
                        env_map = redacted.get(env_field)
                        if isinstance(env_map, dict):
                            for secret_k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "ROBLOX_OPEN_CLOUD_API_KEY", "ROBLOX_API_KEY"):
                                if secret_k in env_map and env_map[secret_k]:
                                    env_map[secret_k] = mask_api_key(str(env_map[secret_k])) or "***"
                info["entry"] = redacted
    except Exception as exc:
        info["error"] = str(exc)
    return info


def _inspect_codex_toml_status(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "registered": False,
        "legacy_present": [],
        "error": None,
    }
    if not path.is_file():
        return info
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        mcp_servers = parsed.get("mcp_servers", {})
        if isinstance(mcp_servers, dict):
            info["registered"] = "sharp" in mcp_servers
            info["legacy_present"] = [leg for leg in LEGACY_SERVER_NAMES if leg in mcp_servers]
            if "sharp" in mcp_servers:
                info["entry"] = mcp_servers["sharp"]
    except Exception as exc:
        info["error"] = str(exc)
    return info


def get_client_registration_status(
    clients: Optional[Sequence[str] | str] = None,
    home_dir: Optional[str | Path] = None,
    config_root: Optional[str | Path] = None,
    project: bool = False,
    project_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Read-only inspection of Sharp MCP registration status across supported clients."""
    if clients is None or clients == "all":
        target_clients = list(SUPPORTED_CLIENTS)
    elif isinstance(clients, str):
        target_clients = [c.strip() for c in clients.split(",") if c.strip()]
    else:
        target_clients = list(clients)

    home, cfg_root, isolated = _resolve_bases(home_dir=home_dir, config_root=config_root)
    proj_path = Path(project_dir).expanduser().resolve() if project_dir else None

    statuses: Dict[str, Any] = {}
    for raw_name in target_clients:
        canonical = normalize_client_name(raw_name)
        if canonical == "antigravity":
            # Report all potential Antigravity config files cleanly
            candidates = _resolve_antigravity_targets(home, cfg_root, project, proj_path)
            extra = home / ".gemini" / "config" / "mcp_config.json"
            if cfg_root is None and extra not in candidates:
                candidates.append(extra)
            extra_agy = home / ".antigravity" / "mcp_config.json"
            if cfg_root is None and extra_agy not in candidates:
                candidates.append(extra_agy)
            file_infos = [_inspect_json_file_status(p, "Sharp") for p in candidates]
            statuses[canonical] = {
                "registered": any(f["registered"] for f in file_infos),
                "files": file_infos,
            }
        elif canonical == "claude-desktop":
            f_info = _inspect_json_file_status(_resolve_claude_desktop_target(home, cfg_root, isolated), "Sharp")
            statuses[canonical] = {"registered": f_info["registered"], "files": [f_info]}
        elif canonical == "claude-code":
            f_info = _inspect_json_file_status(_resolve_claude_code_target(home, cfg_root, project, proj_path), "Sharp")
            statuses[canonical] = {"registered": f_info["registered"], "files": [f_info]}
        elif canonical == "codex":
            f_info = _inspect_codex_toml_status(_resolve_codex_target(home, cfg_root, isolated, project, proj_path))
            statuses[canonical] = {"registered": f_info["registered"], "files": [f_info]}
        elif canonical == "opencode":
            f_info = _inspect_json_file_status(
                _resolve_opencode_target(home, cfg_root, isolated, project, proj_path),
                "sharp",
                use_opencode_v2=True,
            )
            statuses[canonical] = {"registered": f_info["registered"], "files": [f_info]}
        elif canonical == "devin":
            f_info = _inspect_json_file_status(_resolve_devin_target(home, cfg_root, isolated), "Sharp")
            statuses[canonical] = {"registered": f_info["registered"], "files": [f_info]}
        else:
            statuses[raw_name] = {"ok": False, "error": f"Unknown client '{raw_name}'"}

    return {
        "ok": True,
        "clients": statuses,
    }
