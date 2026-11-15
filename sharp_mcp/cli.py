"""Command-line interface for Sharp MCP (`serve`, `install-plugin`, `install-blender`, `register`, `keys`, `doctor`, `self-test`)."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import os
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __app_name__, __version__
from .blender_installer import detect_blender_installation, ensure_blender_installed
from .client_registry import (
    SUPPORTED_CLIENTS,
    get_client_registration_status,
    register_clients,
)
from .credentials_store import (
    MODEL_PRESETS,
    SUPPORTED_PROVIDERS,
    clear_credentials,
    get_credentials_status,
    set_credentials,
)
from .plugin_installer import get_plugin_install_status, install_studio_plugin


def _resolve_runtime_version() -> str:
    """Read package version from pyproject.toml when present, falling back to sharp_mcp.__version__."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
            ver = str(data.get("project", {}).get("version") or "").strip()
            if ver:
                return ver
        except Exception:
            pass
    return __version__


RUNTIME_VERSION = _resolve_runtime_version()


KNOWN_SUBCOMMANDS = {
    "serve",
    "install-plugin",
    "install-blender",
    "register",
    "keys",
    "doctor",
    "self-test",
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _emit_output(payload: Dict[str, Any], as_json: bool = False, summary_lines: Optional[List[str]] = None) -> None:
    if as_json or not summary_lines:
        print(json.dumps(payload, indent=2))
        return
    for line in summary_lines:
        print(line)


def _cmd_serve(args: argparse.Namespace) -> int:
    if args.project_dir:
        os.environ["SHARP_PROJECT_DIR"] = str(Path(args.project_dir).expanduser().resolve())
    if args.skills_dir:
        os.environ["SHARP_SKILLS_DIR"] = str(Path(args.skills_dir).expanduser().resolve())
    if args.bridge_host:
        os.environ["SHARP_BRIDGE_HOST"] = args.bridge_host
    if args.bridge_port is not None:
        os.environ["SHARP_BRIDGE_PORT"] = str(args.bridge_port)

    # Construct SharpMcpApplication lazily so doctor/register/install-* stay lightweight
    from .mcp_server import SharpMcpApplication

    sig = inspect.signature(SharpMcpApplication.__init__)
    params = sig.parameters
    kwargs: Dict[str, Any] = {}

    if "skills_dir" in params and args.skills_dir:
        kwargs["skills_dir"] = Path(args.skills_dir).expanduser().resolve()
    if "project_dir" in params and args.project_dir:
        kwargs["project_dir"] = Path(args.project_dir).expanduser().resolve()
    if "bridge_host" in params:
        kwargs["bridge_host"] = args.bridge_host
    if "bridge_port" in params:
        kwargs["bridge_port"] = args.bridge_port
    if "start_bridge" in params:
        kwargs["start_bridge"] = not args.no_bridge_listener
    if "profile" in params:
        kwargs["profile"] = args.profile

    app = SharpMcpApplication(**kwargs)
    if hasattr(app, "run") and callable(app.run):
        app.run(transport=args.transport)
    else:
        app.mcp.run(transport=args.transport)
    return 0


def _cmd_install_plugin(args: argparse.Namespace) -> int:
    res = install_studio_plugin(
        target_dir=args.target_dir,
        prune_legacy=not args.keep_legacy,
        dry_run=args.dry_run,
    )
    lines = [
        f"Sharp Studio Plugin Install ({'DRY RUN' if args.dry_run else res.get('action', 'status')}):",
        f"  ok:          {res.get('ok')}",
        f"  source:      {res.get('source_path')}",
        f"  destination: {res.get('dest_path')}",
    ]
    if res.get("sha256") or res.get("source_sha256"):
        lines.append(f"  sha256:      {res.get('sha256') or res.get('source_sha256')}")
    if res.get("pruned_legacy") or res.get("would_prune_legacy"):
        lines.append(f"  legacy:      pruned {res.get('legacy_path')}")
    if not res.get("ok") and res.get("message"):
        lines.append(f"  error:       {res.get('message')}")
    _emit_output(res, as_json=args.json, summary_lines=lines)
    return 0 if res.get("ok") else 1


def _cmd_install_blender(args: argparse.Namespace) -> int:
    res = ensure_blender_installed(
        auto_install=not args.no_auto_install,
        install_addon=not args.no_addon,
        enable_addon=not args.no_enable,
        dry_run=args.dry_run,
    )
    det = res.get("detected", {})
    lines = [
        f"Sharp Blender Setup ({'DRY RUN' if args.dry_run else ('OK' if res.get('ok') else 'FAILED')}):",
        f"  installed:      {det.get('installed')} ({det.get('version_raw') or det.get('executable') or 'none'})",
        f"  addon_installed:{det.get('addon_installed')} (protocol={det.get('addon_protocol_version')})",
    ]
    if args.dry_run:
        lines.append(f"  planned_cmds:   {len(res.get('planned_commands', []))}")
        for cmd in res.get("planned_commands", []):
            lines.append(f"    - {' '.join(cmd)}")
    if not res.get("ok") and res.get("message"):
        lines.append(f"  error:          {res.get('message')}")
    _emit_output(res, as_json=args.json, summary_lines=lines)
    return 0 if res.get("ok") else 1


def _cmd_register(args: argparse.Namespace) -> int:
    clients_arg: Any = args.client if args.client else ["all"]
    if len(clients_arg) == 1 and clients_arg[0] == "all":
        clients_arg = "all"

    res = register_clients(
        clients=clients_arg,
        launcher=args.launcher,
        profile=args.profile,
        home_dir=args.home_dir,
        config_root=args.config_root,
        project=args.project,
        project_dir=args.project_dir,
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
        prune_legacy=not args.keep_legacy,
        dry_run=args.dry_run,
    )
    lines = [f"Sharp MCP Client Registration ({'DRY RUN' if args.dry_run else 'APPLIED'}):"]
    for cname, cdata in res.get("clients", {}).items():
        status_tag = "OK" if cdata.get("ok") else "FAIL"
        file_list = ", ".join(f.get("path", "") for f in cdata.get("files", []))
        lines.append(f"  [{status_tag}] {cname}: {file_list or cdata.get('message', '')}")
    _emit_output(res, as_json=args.json, summary_lines=lines)
    return 0 if res.get("ok") else 1


def _resolve_skills_dir_for_doctor() -> Dict[str, Any]:
    candidates: List[Path] = []
    env_dir = os.environ.get("SHARP_SKILLS_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir).expanduser().resolve())
    candidates.append(Path(__file__).resolve().parent / "bundled_skills")
    candidates.append(Path.home() / ".gemini" / "config" / "skills")
    candidates.append(Path(__file__).resolve().parent.parent.parent)

    for cand in candidates:
        if cand.is_dir():
            found_roblox = sorted(p.name for p in cand.glob("roblox-*") if (p / "SKILL.md").is_file())
            found_blender = sorted(p.name for p in cand.glob("blender-*") if (p / "SKILL.md").is_file())
            if found_roblox or found_blender:
                return {
                    "found": True,
                    "path": str(cand),
                    "roblox_skills": found_roblox,
                    "blender_skills": found_blender,
                }
    return {
        "found": False,
        "checked": [str(c) for c in candidates],
        "roblox_skills": [],
        "blender_skills": [],
    }


def _cmd_doctor(args: argparse.Namespace) -> int:
    req_modules = {
        "mcp": importlib.util.find_spec("mcp") is not None,
        "aiohttp": importlib.util.find_spec("aiohttp") is not None,
        "PIL": importlib.util.find_spec("PIL") is not None,
        "numpy": importlib.util.find_spec("numpy") is not None,
    }
    py_ok = sys.version_info >= (3, 11)
    deps_ok = all(req_modules.values())

    plugin_status = get_plugin_install_status()
    blender_status = detect_blender_installation()
    client_status = get_client_registration_status(
        home_dir=args.home_dir,
        config_root=args.config_root,
        project_dir=args.project_dir,
    )
    skills_status = _resolve_skills_dir_for_doctor()
    credentials_status = get_credentials_status()

    pkg_root = Path(__file__).resolve().parent.parent
    node_wrapper = pkg_root / "bin" / "sharp-mcp.mjs"
    toolchain_bins = {
        tool: shutil.which(tool)
        for tool in ("node", "uv", "uvx", "rojo", "lune", "selene", "stylua", "wally", "rokit")
    }

    overall_ok = py_ok and deps_ok
    if args.strict:
        overall_ok = overall_ok and plugin_status.get("up_to_date", False) and blender_status.get("installed", False)

    payload: Dict[str, Any] = {
        "ok": overall_ok,
        "app": __app_name__,
        "version": RUNTIME_VERSION,
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "ok_3_11_plus": py_ok,
            "dependencies": req_modules,
            "all_dependencies_present": deps_ok,
        },
        "launcher": {
            "package_root": str(pkg_root),
            "node_wrapper_exists": node_wrapper.is_file(),
            "node_wrapper_path": str(node_wrapper),
        },
        "studio_plugin": plugin_status,
        "blender": blender_status,
        "clients": client_status.get("clients", {}),
        "skills": skills_status,
        "credentials": credentials_status,
        "toolchain_binaries": toolchain_bins,
    }

    gem_stat = credentials_status.get("providers", {}).get("gemini", {})
    or_stat = credentials_status.get("providers", {}).get("openrouter", {})
    lines = [
        f"Sharp MCP Doctor (v{RUNTIME_VERSION}):",
        f"  Python {sys.version.split()[0]}: {'OK' if py_ok else 'FAIL'} | deps: {'OK' if deps_ok else req_modules}",
        f"  Studio Plugin: source={plugin_status['source_exists']} installed={plugin_status['installed']} up_to_date={plugin_status['up_to_date']}",
        f"  Blender:       installed={blender_status['installed']} version={blender_status.get('version')} addon={blender_status.get('addon_installed')} socket={blender_status.get('socket_reachable')}",
        f"  Skills:        found={skills_status['found']} ({len(skills_status['roblox_skills'])} roblox, {len(skills_status['blender_skills'])} blender)",
        f"  AI Keys:       gemini={gem_stat.get('configured')} ({gem_stat.get('source')}) | openrouter={or_stat.get('configured')} ({or_stat.get('source')})",
        "  Clients:",
    ]
    for cname, cstat in payload["clients"].items():
        lines.append(f"    - {cname}: registered={cstat.get('registered')}")
    _emit_output(payload, as_json=args.json, summary_lines=lines)
    return 0 if overall_ok else 1


def _cmd_self_test(args: argparse.Namespace) -> int:
    checks: Dict[str, Dict[str, Any]] = {}

    # 1. Core imports check
    import_results: Dict[str, Any] = {}
    for mod_name in (
        "sharp_mcp",
        "sharp_mcp.plugin_installer",
        "sharp_mcp.blender_installer",
        "sharp_mcp.client_registry",
        "sharp_mcp.cli",
        "sharp_mcp.bridge_broker",
        "sharp_mcp.transient_http",
        "sharp_mcp.skill_router",
        "sharp_mcp.project_library",
        "sharp_mcp.credentials_store",
        "sharp_mcp.domain_engines.design_engine",
        "sharp_mcp.domain_engines.art_creation_engine",
        "sharp_mcp.domain_engines.multimodal_qa_engine",
        "sharp_mcp.domain_engines.attachment_engine",
        "sharp_mcp.domain_engines.game_planner",
        "sharp_mcp.domain_engines.critical_audit_engine",
        "sharp_mcp.mcp_server",
    ):
        try:
            importlib.import_module(mod_name)
            import_results[mod_name] = True
        except Exception as exc:
            import_results[mod_name] = f"ERROR: {exc}"
    imports_ok = all(v is True for v in import_results.values())
    checks["imports"] = {"ok": imports_ok, "modules": import_results}

    # 2. Plugin installer isolated test
    with tempfile.TemporaryDirectory(prefix="sharp_selftest_plugin_") as tmp_p:
        tmp_plugins = Path(tmp_p) / "Plugins"
        tmp_plugins.mkdir(parents=True, exist_ok=True)
        legacy_file = tmp_plugins / "ForgeBridgePlugin.rbxmx"
        legacy_file.write_text("<roblox/>", encoding="utf-8")

        dry_res = install_studio_plugin(target_dir=tmp_plugins, prune_legacy=True, dry_run=True)
        status_before = get_plugin_install_status(target_dir=tmp_plugins)
        if status_before["source_exists"]:
            inst_res = install_studio_plugin(target_dir=tmp_plugins, prune_legacy=True, dry_run=False)
            plugin_ok = bool(
                inst_res.get("ok")
                and inst_res.get("sha256_verified")
                and inst_res.get("pruned_legacy")
                and not legacy_file.exists()
            )
            checks["plugin_installer"] = {"ok": plugin_ok, "mode": "full_copy", "sha256": inst_res.get("sha256")}
        else:
            plugin_ok = dry_res.get("code") == "PLUGIN_SOURCE_MISSING" and legacy_file.exists()
            checks["plugin_installer"] = {
                "ok": plugin_ok,
                "mode": "source_not_built_yet",
                "status": status_before,
            }

    # 3. Blender installer detection & dry-run check
    blend_det = detect_blender_installation()
    blend_dry = ensure_blender_installed(dry_run=True)
    checks["blender_installer"] = {
        "ok": bool(blend_det.get("ok") and blend_dry.get("ok") and blend_dry.get("dry_run")),
        "installed": blend_det.get("installed"),
        "version": blend_det.get("version"),
        "planned_commands_count": len(blend_dry.get("planned_commands", [])),
    }

    # 4. Multi-client registry isolated round-trip test (all 5 targets)
    with tempfile.TemporaryDirectory(prefix="sharp_selftest_clients_") as tmp_h:
        home_p = Path(tmp_h)
        # Seed Antigravity legacy + .gemini dir, OpenCode JSONC with comments, and Codex TOML with comments
        (home_p / ".gemini" / "config").mkdir(parents=True, exist_ok=True)
        (home_p / ".gemini" / "config" / "mcp_config.json").write_text(
            json.dumps({"mcpServers": {"Roblox_Forge": {"command": "python"}}}),
            encoding="utf-8",
        )
        (home_p / ".config" / "opencode").mkdir(parents=True, exist_ok=True)
        (home_p / ".config" / "opencode" / "opencode.jsonc").write_text(
            '// OpenCode comment\n{\n  /* block */\n  "mcp": { "servers": { "Roblox_Forge": { "type": "local", "command": ["x"], }, } },\n}\n',
            encoding="utf-8",
        )
        (home_p / ".codex").mkdir(parents=True, exist_ok=True)
        (home_p / ".codex" / "config.toml").write_text(
            '# Preserve this comment\nmodel = "gpt-5"\n\n[mcp_servers.Roblox_Forge]\ncommand = "python"\nargs = []\n',
            encoding="utf-8",
        )

        reg_res = register_clients(
            clients="all",
            home_dir=home_p,
            launcher="auto",
            profile="full",
            prune_legacy=True,
            dry_run=False,
        )
        stat_res = get_client_registration_status(clients="all", home_dir=home_p)
        codex_text = (home_p / ".codex" / "config.toml").read_text(encoding="utf-8")
        codex_parsed = tomllib.loads(codex_text)
        all_registered = all(
            stat_res["clients"][c]["registered"] and not any(f.get("legacy_present") for f in stat_res["clients"][c]["files"])
            for c in SUPPORTED_CLIENTS
        )
        clients_ok = (
            reg_res.get("ok")
            and all_registered
            and "# Preserve this comment" in codex_text
            and "sharp" in codex_parsed.get("mcp_servers", {})
            and (home_p / ".codex" / "config.toml.bak").is_file()
        )
        checks["client_registry"] = {"ok": clients_ok, "clients": list(SUPPORTED_CLIENTS)}

    # 5. SharpMcpApplication lazy instantiation check (with bridge disabled)
    try:
        from .mcp_server import SharpMcpApplication

        with tempfile.TemporaryDirectory(prefix="sharp_selftest_app_") as tmp_lib:
            sig = inspect.signature(SharpMcpApplication.__init__)
            app_kwargs: Dict[str, Any] = {}
            if "start_bridge" in sig.parameters:
                app_kwargs["start_bridge"] = False
            if "profile" in sig.parameters:
                app_kwargs["profile"] = "core"
            if "bridge_port" in sig.parameters:
                app_kwargs["bridge_port"] = 0
            if "library_root" in sig.parameters:
                app_kwargs["library_root"] = Path(tmp_lib)
            app = SharpMcpApplication(**app_kwargs)
            checks["mcp_app"] = {"ok": hasattr(app, "mcp"), "profile": "core"}
    except Exception as exc:
        checks["mcp_app"] = {"ok": False, "error": str(exc)}

    overall_ok = all(item.get("ok", False) for item in checks.values())
    payload = {"ok": overall_ok, "version": RUNTIME_VERSION, "checks": checks}
    lines = [f"Sharp Self-Test (v{RUNTIME_VERSION}): {'PASS' if overall_ok else 'FAIL'}"]
    for cname, cdata in checks.items():
        lines.append(f"  [{'PASS' if cdata.get('ok') else 'FAIL'}] {cname}")
    _emit_output(payload, as_json=args.json, summary_lines=lines)
    return 0 if overall_ok else 1


def _cmd_keys(args: argparse.Namespace) -> int:
    sub = (getattr(args, "keys_action", None) or "status").strip().lower()
    if sub == "status":
        res = get_credentials_status()
        provs = res.get("providers", {})
        lines = [f"Sharp AI Credentials Store ({res.get('credentials_file')}):"]
        for pname, pstat in provs.items():
            lines.append(
                f"  - {pname}: configured={pstat.get('configured')} source={pstat.get('source')} "
                f"key={pstat.get('masked_preview')}"
            )
        prefs = res.get("model_preferences") or {}
        if prefs:
            lines.append(f"  model_preferences: {json.dumps(prefs)}")
        _emit_output(res, as_json=args.json, summary_lines=lines)
        return 0
    if sub == "set":
        api_key = args.api_key
        if args.stdin:
            api_key = sys.stdin.read().strip()
        elif not api_key:
            api_key = os.environ.get("SHARP_SET_API_KEY", "").strip()
        prefs: Optional[Dict[str, str]] = None
        if args.model:
            role_key = (args.role or ("gui_code" if args.provider == "openrouter" else "vision")).strip()
            prefs = {role_key: args.model}
        res = set_credentials(
            gemini_api_key=api_key if args.provider == "gemini" else None,
            openrouter_api_key=api_key if args.provider == "openrouter" else None,
            model_preferences=prefs,
        )
        lines = [
            f"Sharp AI Credentials Set ({args.provider}): updated={res.get('updated')} file={res.get('credentials_file')}"
        ]
        _emit_output(res, as_json=args.json, summary_lines=lines)
        return 0 if res.get("ok") else 1
    if sub == "clear":
        res = clear_credentials(provider=args.provider)
        _emit_output(
            res,
            as_json=args.json,
            summary_lines=[f"Sharp AI Credentials Cleared: {res.get('cleared')}"],
        )
        return 0 if res.get("ok") else 1
    if sub == "models":
        res = {"ok": True, "presets": MODEL_PRESETS}
        lines = ["Sharp Recommended Affordable Models:"]
        for prov_name, roles in MODEL_PRESETS.items():
            lines.append(f"  [{prov_name}]")
            for role_name, info in roles.items():
                lines.append(
                    f"    - {role_name}: default={info.get('default')} | budget={info.get('budget')} | flagship={info.get('flagship')}"
                )
        _emit_output(res, as_json=args.json, summary_lines=lines)
        return 0
    return 1


def _add_serve_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-bridge-listener",
        action="store_true",
        default=_env_flag("SHARP_NO_BRIDGE_LISTENER", False),
        help="Disable starting the local Studio HTTP bridge listener.",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "core", "blender"),
        default=os.environ.get("SHARP_PROFILE", "full"),
        help="Tool profile to expose (default: full).",
    )
    parser.add_argument(
        "--project-dir",
        default=os.environ.get("SHARP_PROJECT_DIR") or None,
        help="Active Roblox project workspace directory.",
    )
    parser.add_argument(
        "--skills-dir",
        default=os.environ.get("SHARP_SKILLS_DIR") or None,
        help="Override directory containing roblox-* and blender-* skill folders.",
    )
    parser.add_argument(
        "--bridge-host",
        default=os.environ.get("SHARP_BRIDGE_HOST", "127.0.0.1"),
        help="Loopback bind host for SharpBridgePlugin (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=int(os.environ.get("SHARP_BRIDGE_PORT", "58421")),
        help="Loopback bind port for SharpBridgePlugin (default: 58421).",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio",),
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sharp-mcp",
        description=f"{__app_name__} v{RUNTIME_VERSION} — Unified Roblox Studio & Blender MCP Server and Setup CLI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {RUNTIME_VERSION}",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    p_serve = subparsers.add_parser("serve", help="Run the Sharp MCP stdio server (default).")
    _add_serve_arguments(p_serve)
    p_serve.set_defaults(handler=_cmd_serve)

    p_plugin = subparsers.add_parser("install-plugin", help="Install SharpBridgePlugin.rbxmx into Roblox Studio Plugins.")
    p_plugin.add_argument("--target-dir", default=None, help="Override Roblox Plugins directory.")
    p_plugin.add_argument("--keep-legacy", action="store_true", help="Do not delete legacy ForgeBridgePlugin.rbxmx.")
    p_plugin.add_argument("--dry-run", action="store_true", help="Preview installation without writing files.")
    p_plugin.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_plugin.set_defaults(handler=_cmd_install_plugin)

    p_blender = subparsers.add_parser("install-blender", help="Detect or auto-install Blender and the mcp-for-blender addon.")
    p_blender.add_argument("--no-auto-install", action="store_true", help="Do not auto-install Blender if missing.")
    p_blender.add_argument("--no-addon", action="store_true", help="Skip installing mcp-for-blender addon.")
    p_blender.add_argument("--no-enable", action="store_true", help="Skip headless addon enable step.")
    p_blender.add_argument("--dry-run", action="store_true", help="Return planned commands without executing.")
    p_blender.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_blender.set_defaults(handler=_cmd_install_blender)

    p_reg = subparsers.add_parser("register", help="Register Sharp MCP across Antigravity, Claude Desktop, Claude Code, Codex, and OpenCode.")
    p_reg.add_argument(
        "--client",
        action="append",
        choices=("all", *SUPPORTED_CLIENTS),
        help="Target client(s) to register (repeatable; default: all).",
    )
    p_reg.add_argument("--launcher", choices=("auto", "npx", "uvx", "python"), default="auto")
    p_reg.add_argument("--profile", choices=("full", "core", "blender"), default="full")
    p_reg.add_argument("--project", action="store_true", help="Write project-local config where supported (.mcp.json, opencode.json, .antigravity).")
    p_reg.add_argument("--project-dir", default=None, help="Project directory for project-scoped config & SHARP_PROJECT_DIR.")
    p_reg.add_argument("--home-dir", default=None, help="Override user home directory (for isolated testing).")
    p_reg.add_argument("--config-root", default=None, help="Override client config root directory.")
    p_reg.add_argument("--bridge-host", default=os.environ.get("SHARP_BRIDGE_HOST", "127.0.0.1"))
    p_reg.add_argument("--bridge-port", type=int, default=int(os.environ.get("SHARP_BRIDGE_PORT", "58421")))
    p_reg.add_argument("--keep-legacy", action="store_true", help="Keep legacy Roblox_Forge entries.")
    p_reg.add_argument("--dry-run", action="store_true", help="Preview changes without modifying config files.")
    p_reg.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_reg.set_defaults(handler=_cmd_register)

    p_doc = subparsers.add_parser("doctor", help="Inspect Python, dependencies, Roblox plugin, Blender, clients, and toolchain status.")
    p_doc.add_argument("--home-dir", default=None, help="Override home directory for client inspection.")
    p_doc.add_argument("--config-root", default=None, help="Override config root for client inspection.")
    p_doc.add_argument("--project-dir", default=None, help="Project directory to inspect.")
    p_doc.add_argument("--strict", action="store_true", help="Fail unless plugin is up-to-date and Blender is installed.")
    p_doc.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_doc.set_defaults(handler=_cmd_doctor)

    p_test = subparsers.add_parser("self-test", help="Run isolated non-destructive self-tests for Sharp packaging & installers.")
    p_test.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_test.set_defaults(handler=_cmd_self_test)

    p_keys = subparsers.add_parser(
        "keys",
        help="Manage external OpenRouter & Gemini API keys securely outside repositories.",
    )
    keys_sub = p_keys.add_subparsers(dest="keys_action")
    p_keys.set_defaults(keys_action="status", json=False, handler=_cmd_keys)

    p_keys_status = keys_sub.add_parser("status", help="Show masked status of OpenRouter & Gemini API keys.")
    p_keys_status.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_keys_status.set_defaults(keys_action="status", handler=_cmd_keys)

    p_keys_set = keys_sub.add_parser("set", help="Store an OpenRouter or Gemini API key / default model.")
    p_keys_set.add_argument("--provider", required=True, choices=SUPPORTED_PROVIDERS)
    p_keys_set.add_argument("--api-key", default=None, help="API key (or omit and pass --stdin / SHARP_SET_API_KEY).")
    p_keys_set.add_argument("--stdin", action="store_true", help="Read API key from stdin cleanly.")
    p_keys_set.add_argument("--model", default=None, help="Override preferred model ID for a role (e.g. google/gemini-2.5-flash).")
    p_keys_set.add_argument("--role", default="vision", choices=("video", "audio", "vision", "gui_code", "image_gen"), help="Model preference role when --model is supplied.")
    p_keys_set.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_keys_set.set_defaults(keys_action="set", handler=_cmd_keys)

    p_keys_clear = keys_sub.add_parser("clear", help="Remove stored credentials for a provider or all providers.")
    p_keys_clear.add_argument("--provider", default="all", choices=("all", *SUPPORTED_PROVIDERS))
    p_keys_clear.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_keys_clear.set_defaults(keys_action="clear", handler=_cmd_keys)

    p_keys_models = keys_sub.add_parser("models", help="List curated cheap UI/Vision/Image model presets.")
    p_keys_models.add_argument("--json", action="store_true", help="Emit JSON output.")
    p_keys_models.set_defaults(keys_action="models", handler=_cmd_keys)

    return parser


def _normalize_argv(argv: List[str]) -> List[str]:
    if not argv:
        return ["serve"]
    first = argv[0]
    if first in KNOWN_SUBCOMMANDS or first in ("-h", "--help", "--version"):
        return argv
    return ["serve", *argv]


def main(argv: Optional[List[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized = _normalize_argv(raw_argv)
    parser = build_parser()
    parsed = parser.parse_args(normalized)
    handler = getattr(parsed, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return int(handler(parsed))


if __name__ == "__main__":
    sys.exit(main())
