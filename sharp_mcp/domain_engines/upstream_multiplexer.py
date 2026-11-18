"""Upstream Multiplexer & Dual-Execution Coordinator (`SharpBridgePlugin` + optional `StudioMCP`).

Provides:
1. Automatic routing of compiled Luau payloads & `module_op` dispatches to:
   - `SharpBridgePlugin.rbxmx` over `127.0.0.1:<port>` (if connected in Studio Edit mode), OR
   - Optional Windows `StudioMCP.exe` (`mcp.bat`) via `mcp.client.stdio` ONLY when
     explicitly requested on Windows (`invoke_upstream_studiomcp_if_plugin_offline=True`), OR
   - Returning the compiled self-contained `--!strict` Luau runner so Sharp works standalone
     across Windows, macOS, and Linux without requiring external `mcp.bat`.
2. Structured broker bind status (`{port, busy, reason}`) and cross-platform health diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..bridge_broker import BridgeBroker


def _resolve_roblox_user_dir() -> Path:
    """Resolves the platform-native Roblox data/plugins base directory without hardcoded user paths."""
    override = os.environ.get("SHARP_ROBLOX_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        return base / "Roblox"
    if sys.platform == "darwin":
        return Path.home() / "Documents" / "Roblox"
    return Path.home() / ".local" / "share" / "Roblox"


def _resolve_studio_plugin_src_dir() -> Optional[Path]:
    """Locate `studio_plugin/src` cleanly across repo checkouts and installed wheels."""
    engine_dir = Path(__file__).resolve().parent
    pkg_dir = engine_dir.parent
    repo_root = pkg_dir.parent
    for candidate in (
        repo_root / "studio_plugin" / "src",
        pkg_dir / "studio_plugin" / "src",
    ):
        if candidate.is_dir():
            return candidate
    return None


def _strip_module_boilerplate(src: str, module_symbol: str) -> str:
    """Strip leading `--!strict` and trailing `return <module_symbol>` for inline bundling."""
    lines = src.splitlines()
    if lines and lines[0].lstrip().startswith("--!strict"):
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and re.match(rf"^return\s+{re.escape(module_symbol)}\s*$", lines[-1].strip()):
        lines.pop()
    return "\n".join(lines)


def _luau_long_string(text: str) -> str:
    """Encode arbitrary text as a Luau long-bracket string literal without collisions."""
    eq_count = 2
    while True:
        eq = "=" * eq_count
        closing = f"]{eq}]"
        if closing not in text and not text.endswith(f"]{eq}"):
            return f"[{eq}[{text}{closing}"
        eq_count += 1


class UpstreamMultiplexer:
    def __init__(self, broker: BridgeBroker) -> None:
        self.broker = broker
        self._broker_started = False
        self.broker_start_status: Dict[str, Any] = {
            "port": broker.port,
            "busy": False,
            "reason": "not_started",
        }
        self.roblox_dir = _resolve_roblox_user_dir()
        mcp_bat_override = os.environ.get("SHARP_STUDIOMCP_BAT")
        self.mcp_bat_path: Optional[Path] = (
            Path(mcp_bat_override).expanduser()
            if mcp_bat_override
            else (self.roblox_dir / "mcp.bat" if sys.platform == "win32" else None)
        )
        self.plugins_dir = self.roblox_dir / "Plugins"
        self._cached_studio_id: Optional[str] = None
        self._cached_studio_ts: float = 0.0

    async def ensure_broker_started(self) -> Dict[str, Any]:
        if self._broker_started:
            return {
                "port": self.broker.port,
                "busy": False,
                "reason": "already_started",
            }
        try:
            bound_port = await self.broker.start()
            self._broker_started = True
            self.broker_start_status = {
                "port": bound_port,
                "busy": False,
                "reason": "started",
            }
        except (OSError, ValueError) as exc:
            self.broker_start_status = {
                "port": self.broker.port,
                "busy": isinstance(exc, OSError),
                "reason": f"{type(exc).__name__}: {exc}",
            }
        return dict(self.broker_start_status)

    def get_upstream_health(self, blender_status: Dict[str, Any]) -> Dict[str, Any]:
        plugin_rbxmx = self.plugins_dir / "SharpBridgePlugin.rbxmx"
        studio_mcp_available = bool(
            sys.platform == "win32"
            and self.mcp_bat_path is not None
            and self.mcp_bat_path.is_file()
        )
        return {
            "sharp_bridge_plugin": {
                "installed_at": str(plugin_rbxmx),
                "installed": plugin_rbxmx.is_file(),
                "loopback_online": self.broker.is_plugin_online(),
                "broker_start_status": dict(self.broker_start_status),
                "bridge_status": self.broker.get_status_snapshot(),
            },
            "roblox_studio_mcp": {
                "optional": True,
                "platform": sys.platform,
                "mcp_bat_path": str(self.mcp_bat_path) if self.mcp_bat_path else None,
                "available": studio_mcp_available,
            },
            "blender_mcp": blender_status,
        }

    async def resolve_active_studio_id(self, studio_id: Optional[str] = None) -> Optional[str]:
        """Resolve an explicit or active Edit-mode Roblox Studio ID with a 15s TTL cache."""
        if isinstance(studio_id, str) and studio_id.strip():
            return studio_id.strip()

        now = time.monotonic()
        if self._cached_studio_id and (now - self._cached_studio_ts) < 15.0:
            return self._cached_studio_id

        res = await self.call_upstream_studio_mcp("list_roblox_studios", {}, timeout_sec=10.0)
        if not res.get("ok"):
            return None

        decoded = res.get("decoded")
        studios = (
            decoded.get("studios")
            if isinstance(decoded, dict)
            else (decoded if isinstance(decoded, list) else None)
        )
        if not isinstance(studios, list):
            return None

        edit_id: Optional[str] = None
        fallback_id: Optional[str] = None
        for entry in studios:
            if not isinstance(entry, dict):
                continue
            sid = entry.get("id") or entry.get("studio_id")
            if not sid:
                continue
            sid_str = str(sid).strip()
            if not sid_str:
                continue
            if str(entry.get("mode", "")).strip().lower() == "edit":
                edit_id = sid_str
                break
            if fallback_id is None:
                fallback_id = sid_str

        chosen = edit_id or fallback_id
        if chosen:
            self._cached_studio_id = chosen
            self._cached_studio_ts = time.monotonic()
        return chosen

    def compile_module_op_luau(
        self,
        module_name: str,
        op: str,
        args: Optional[Dict[str, Any]] = None,
        kind: str = "read",
    ) -> Optional[str]:
        """Compile a self-contained `--!strict` Luau runner for `SharpGuiTools` or `SharpTreeTools` ops."""
        if module_name not in ("SharpGuiTools", "SharpTreeTools"):
            return None
        src_dir = _resolve_studio_plugin_src_dir()
        if src_dir is None:
            return None
        undo_path = src_dir / "SharpUndo.luau"
        mod_path = src_dir / f"{module_name}.luau"
        if not undo_path.is_file() or not mod_path.is_file():
            return None

        undo_body = _strip_module_boilerplate(undo_path.read_text(encoding="utf-8"), "SharpUndo")
        mod_body = _strip_module_boilerplate(mod_path.read_text(encoding="utf-8"), module_name)
        args_json = json.dumps(args or {}, ensure_ascii=False)
        args_lit = _luau_long_string(args_json)
        op_lit = json.dumps(op)
        mod_lit = json.dumps(module_name)
        action_lit = json.dumps(f"Sharp_{module_name}_{op}")
        display_lit = json.dumps(f"Sharp MCP: {module_name}.{op}")

        if kind == "write":
            exec_block = (
                "local function _verifyMutationResult(res: any): (boolean, string?)\n"
                '\tif typeof(res) == "table" then\n'
                "\t\tif res.verified == false then\n"
                "\t\t\tlocal errList = res.errors\n"
                '\t\t\tlocal msg = if typeof(errList) == "table" and #errList > 0\n'
                '\t\t\t\tthen table.concat(errList, "; ")\n'
                '\t\t\t\telse tostring(res.message or "Post-write readback verification failed.")\n'
                "\t\t\treturn false, msg\n"
                "\t\tend\n"
                "\t\tif res.ok == false then\n"
                '\t\t\treturn false, tostring(res.message or res.code or "Mutation reported ok=false.")\n'
                "\t\tend\n"
                "\tend\n"
                "\treturn true, nil\n"
                "end\n"
                "local callOk: boolean, recOk: any, recRes: any, recState: any = pcall(function()\n"
                "\treturn SharpUndo.withRecording(\n"
                f"\t\t{action_lit},\n"
                f"\t\t{display_lit},\n"
                "\t\tfunction(): any\n"
                "\t\t\tlocal opOk, opRes = _invokeModuleOp()\n"
                '\t\t\tif not opOk and typeof(opRes) ~= "table" then\n'
                "\t\t\t\treturn { ok = false, message = tostring(opRes) }\n"
                "\t\t\tend\n"
                '\t\t\tif not opOk and typeof(opRes) == "table" and opRes.ok == nil then\n'
                "\t\t\t\topRes.ok = false\n"
                "\t\t\tend\n"
                "\t\t\treturn opRes\n"
                "\t\tend,\n"
                "\t\t_verifyMutationResult\n"
                "\t)\n"
                "end)\n"
                "if callOk then\n"
                "\tokRun = recOk == true\n"
                "\trunOut = recRes\n"
                '\trecStatus = if typeof(recState) == "string" then recState else "None"\n'
                "else\n"
                "\tokRun = false\n"
                '\trunOut = { ok = false, code = "MODULE_OP_ERROR", message = tostring(recOk) }\n'
                '\trecStatus = "Cancelled"\n'
                "end"
            )
        else:
            exec_block = (
                "local callOk: boolean, opOk: any, opRes: any = pcall(_invokeModuleOp)\n"
                "if callOk then\n"
                "\tokRun = opOk == true\n"
                "\trunOut = opRes\n"
                "else\n"
                "\tokRun = false\n"
                '\trunOut = { ok = false, code = "MODULE_OP_ERROR", message = tostring(opOk) }\n'
                "end"
            )

        return (
            "--!strict\n"
            f"{undo_body}\n\n"
            f"{mod_body}\n\n"
            f"local _opArgsJson: string = {args_lit}\n"
            "local _opArgsDecoded: any = HttpService:JSONDecode(_opArgsJson)\n"
            'local _opArgs: { [string]: any } = if typeof(_opArgsDecoded) == "table" then _opArgsDecoded :: { [string]: any } else {}\n'
            f"local _mod: {{ [string]: any }} = {module_name} :: any\n"
            f"local _fn: any = _mod[{op_lit}]\n"
            'if typeof(_fn) ~= "function" then\n'
            "\treturn HttpService:JSONEncode({\n"
            "\t\tok = false,\n"
            "\t\tresult = {\n"
            "\t\t\tok = false,\n"
            '\t\t\tcode = "UNKNOWN_MODULE_OP",\n'
            f"\t\t\tmodule = {mod_lit},\n"
            f"\t\t\top = {op_lit},\n"
            '\t\t\tmessage = "Operation not found on module.",\n'
            "\t\t},\n"
            '\t\trecordingStatus = "None",\n'
            "\t})\n"
            "end\n"
            "local function _invokeModuleOp(): (boolean, any)\n"
            "\tlocal _callable: (any) -> (any, any) = _fn\n"
            "\tlocal r1, r2 = _callable(_opArgs)\n"
            '\tif typeof(r1) == "boolean" and r2 ~= nil then\n'
            "\t\treturn r1, r2\n"
            "\tend\n"
            '\tif typeof(r1) == "boolean" then\n'
            "\t\treturn r1, { ok = r1 }\n"
            "\tend\n"
            '\tif typeof(r1) == "table" and r1.ok == false then\n'
            "\t\treturn false, r1\n"
            "\tend\n"
            "\treturn true, r1\n"
            "end\n"
            "local okRun: boolean = false\n"
            "local runOut: any = nil\n"
            'local recStatus: string = "None"\n'
            f"{exec_block}\n"
            "return HttpService:JSONEncode({\n"
            "\tok = okRun,\n"
            "\tresult = runOut,\n"
            "\trecordingStatus = recStatus,\n"
            "})\n"
        )

    async def execute_studio_job(
        self,
        tool_name: str,
        compiled_luau: str,
        kind: str = "write",
        studio_id: Optional[str] = None,
        prefer_plugin_bridge: bool = True,
        invoke_upstream_studiomcp_if_plugin_offline: bool = False,
        expected_place_id: Optional[int] = None,
        expected_session_nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes a compiled Studio job via SharpBridgePlugin, optional StudioMCP, or returns Luau."""
        broker_status = await self.ensure_broker_started()
        # 1. If SharpBridgePlugin is online on loopback, dispatch over HTTP bridge
        if prefer_plugin_bridge and self.broker.is_plugin_online():
            res = await self.broker.dispatch_job(
                tool=tool_name,
                args={"compiledLuau": compiled_luau},
                kind=kind,
                lease_ms=30000 if kind == "write" else 15000,
                expected_place_id=expected_place_id,
                expected_session_nonce=expected_session_nonce,
            )
            return {
                "executionMode": f"SharpBridgePlugin_Loopback_{self.broker.port}",
                "bridgePort": self.broker.port,
                "brokerStartStatus": broker_status,
                "bridgeResponse": res,
            }

        # 2. Strictly optional Windows-only subprocess invocation of StudioMCP.exe
        if (
            invoke_upstream_studiomcp_if_plugin_offline
            and sys.platform == "win32"
            and self.mcp_bat_path is not None
            and self.mcp_bat_path.is_file()
        ):
            eff_studio_id = studio_id or await self.resolve_active_studio_id(studio_id)
            if eff_studio_id:
                upstream_res = await self.call_upstream_studio_mcp(
                    tool_name="execute_luau",
                    arguments={
                        "code": compiled_luau,
                        "datamodel_type": "Edit",
                        "studio_id": eff_studio_id,
                    },
                )
                out: Dict[str, Any] = {
                    "executionMode": "Upstream_StudioMCP_Subprocess",
                    "studioId": eff_studio_id,
                    "upstreamResponse": upstream_res,
                }
                if upstream_res.get("ok"):
                    out["decoded"] = upstream_res.get("decoded")
                return out

        # 3. Standalone resilient fallback when plugin HTTP polling is not active
        return {
            "executionMode": "Compiled_Luau_Ready",
            "pluginLoopbackOnline": False,
            "bridgePort": self.broker.port,
            "brokerStartStatus": broker_status,
            "compiledLuau": compiled_luau,
            "nextStepHint": (
                "Install `SharpBridgePlugin.rbxmx` via `sharp-mcp install-plugin` and enable "
                "`HttpService.HttpEnabled = true` in Studio so `SharpBridgePlugin` executes jobs "
                f"automatically on http://{self.broker.host}:{self.broker.port}, or run `compiledLuau` "
                "directly in Studio Edit mode."
            ),
        }

    async def execute_module_op(
        self,
        module_name: str,
        op: str,
        args: Optional[Dict[str, Any]] = None,
        kind: str = "read",
        lease_ms: int = 15000,
        expected_place_id: Optional[int] = None,
        expected_session_nonce: Optional[str] = None,
        studio_id: Optional[str] = None,
        invoke_upstream_studiomcp_if_plugin_offline: bool = False,
    ) -> Dict[str, Any]:
        """Dispatches a structured `module_op` payload when SharpBridgePlugin is online."""
        broker_status = await self.ensure_broker_started()
        if not self.broker.is_plugin_online():
            if (
                invoke_upstream_studiomcp_if_plugin_offline
                and sys.platform == "win32"
                and self.mcp_bat_path is not None
                and self.mcp_bat_path.is_file()
            ):
                compiled = self.compile_module_op_luau(
                    module_name=module_name,
                    op=op,
                    args=args,
                    kind=kind,
                )
                eff_studio_id = await self.resolve_active_studio_id(studio_id) if compiled else None
                if compiled and eff_studio_id:
                    upstream_res = await self.call_upstream_studio_mcp(
                        tool_name="execute_luau",
                        arguments={
                            "code": compiled,
                            "datamodel_type": "Edit",
                            "studio_id": eff_studio_id,
                        },
                    )
                    decoded = upstream_res.get("decoded")
                    if isinstance(decoded, str):
                        try:
                            decoded = json.loads(decoded)
                        except Exception:
                            decoded = None
                    if isinstance(decoded, dict) and "ok" not in decoded and isinstance(decoded.get("result"), str):
                        try:
                            inner = json.loads(decoded["result"])
                            if isinstance(inner, dict):
                                decoded = inner
                        except Exception:
                            pass
                    if upstream_res.get("ok") and isinstance(decoded, dict):
                        return {
                            "ok": bool(decoded.get("ok", True)),
                            "executionMode": "Upstream_StudioMCP_Subprocess",
                            "studioId": eff_studio_id,
                            "bridgePort": self.broker.port,
                            "brokerStartStatus": broker_status,
                            "bridgeResponse": decoded,
                            "result": decoded.get("result", decoded),
                        }
                    if not upstream_res.get("ok"):
                        return {
                            "ok": False,
                            "code": "UPSTREAM_STUDIOMCP_ERROR",
                            "executionMode": "Upstream_StudioMCP_Subprocess",
                            "studioId": eff_studio_id,
                            "bridgePort": self.broker.port,
                            "brokerStartStatus": broker_status,
                            "upstreamResponse": upstream_res,
                            "message": upstream_res.get("error")
                            or (
                                upstream_res.get("content")[0]
                                if upstream_res.get("content")
                                else "Upstream StudioMCP execute_luau failed."
                            ),
                        }
                    return {
                        "ok": bool(upstream_res.get("ok", False)),
                        "executionMode": "Upstream_StudioMCP_Subprocess",
                        "studioId": eff_studio_id,
                        "bridgePort": self.broker.port,
                        "brokerStartStatus": broker_status,
                        "upstreamResponse": upstream_res,
                        "result": decoded if decoded is not None else upstream_res.get("result"),
                    }

            return {
                "ok": False,
                "code": "PLUGIN_OFFLINE",
                "executionMode": "Plugin_Offline",
                "bridgePort": self.broker.port,
                "brokerStartStatus": broker_status,
                "message": (
                    f"SharpBridgePlugin is offline on http://{self.broker.host}:{self.broker.port}. "
                    "Ensure Studio is open in Edit mode with HttpService.HttpEnabled = true."
                ),
            }
        res = await self.broker.send_module_op(
            module_name=module_name,
            op=op,
            args=args,
            kind=kind,
            lease_ms=lease_ms,
            expected_place_id=expected_place_id,
            expected_session_nonce=expected_session_nonce,
        )
        return {
            "ok": bool(res.get("ok", False)),
            "executionMode": f"SharpBridgePlugin_Loopback_{self.broker.port}",
            "bridgePort": self.broker.port,
            "brokerStartStatus": broker_status,
            "bridgeResponse": res,
        }

    async def call_upstream_studio_mcp(
        self, tool_name: str, arguments: Dict[str, Any], timeout_sec: float = 25.0
    ) -> Dict[str, Any]:
        """Optionally invokes Roblox StudioMCP (`mcp.bat`) when explicitly requested on Windows."""
        if sys.platform != "win32":
            return {
                "ok": False,
                "optional": True,
                "tool": tool_name,
                "error": (
                    f"Optional Upstream StudioMCP (mcp.bat) is Windows-only (current platform: "
                    f"{sys.platform}); Sharp operates standalone via SharpBridgePlugin."
                ),
            }
        if self.mcp_bat_path is None or not self.mcp_bat_path.is_file():
            return {
                "ok": False,
                "optional": True,
                "tool": tool_name,
                "error": (
                    f"Optional StudioMCP mcp.bat not found at {self.mcp_bat_path}; "
                    "Sharp operates standalone via SharpBridgePlugin."
                ),
            }

        params = StdioServerParameters(
            command="cmd.exe",
            args=["/c", f"cd /d {self.mcp_bat_path.parent} && .\\{self.mcp_bat_path.name}"],
        )
        try:
            async with asyncio.timeout(timeout_sec):
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        texts = [
                            getattr(c, "text", str(c))
                            for c in getattr(result, "content", [])
                        ]
                        out: Dict[str, Any] = {
                            "ok": not getattr(result, "isError", False),
                            "tool": tool_name,
                            "content": texts,
                        }
                        if texts and isinstance(texts[0], str):
                            try:
                                parsed_json = json.loads(texts[0])
                                out["decoded"] = parsed_json
                                out["result"] = texts[0]
                            except Exception:
                                pass
                        return out
        except Exception as exc:
            return {"ok": False, "optional": True, "tool": tool_name, "error": str(exc)}
