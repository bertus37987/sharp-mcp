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
from contextlib import AsyncExitStack
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import aiohttp
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..ai_http import redact_error
from ..bridge_broker import BridgeBroker
from ..credentials_store import get_api_key, get_credentials_status


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


class StudioMcpSessionPool:
    """Lazy, lock-guarded persistent session pool for StudioMCP stdio subprocesses."""

    def __init__(
        self,
        *,
        idle_ttl_sec: float = 120.0,
        client_factory: Optional[Callable[[StdioServerParameters], Any]] = None,
        session_factory: Optional[Callable[[Any, Any], Any]] = None,
    ) -> None:
        self.idle_ttl_sec = max(1.0, float(idle_ttl_sec))
        self._client_factory = client_factory
        self._session_factory = session_factory
        self._lock = asyncio.Lock()
        self._stack: Optional[AsyncExitStack] = None
        self._session: Optional[Any] = None
        self._last_used: float = 0.0
        self._last_params_key: Optional[tuple[str, tuple[str, ...]]] = None
        self.connect_count: int = 0
        self.call_count: int = 0

    async def _close_locked(self) -> None:
        stack = self._stack
        self._stack = None
        self._session = None
        self._last_used = 0.0
        self._last_params_key = None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:
                pass

    async def _ensure_connected_locked(self, params: StdioServerParameters) -> Any:
        now = time.monotonic()
        params_key = (params.command, tuple(params.args or ()))
        if self._session is not None:
            expired = (now - self._last_used) > self.idle_ttl_sec
            changed = params_key != self._last_params_key
            if not expired and not changed:
                return self._session
            await self._close_locked()

        stack = AsyncExitStack()
        c_fac = self._client_factory or stdio_client
        s_fac = self._session_factory or ClientSession
        try:
            read_stream, write_stream = await stack.enter_async_context(c_fac(params))
            session = await stack.enter_async_context(s_fac(read_stream, write_stream))
            await session.initialize()
            self._stack = stack
            self._session = session
            self._last_used = time.monotonic()
            self._last_params_key = params_key
            self.connect_count += 1
            return session
        except Exception:
            try:
                await stack.aclose()
            except Exception:
                pass
            raise

    async def call_tool(
        self,
        params: StdioServerParameters,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        timeout_sec: float = 25.0,
    ) -> Any:
        """Execute ``tool_name`` over the pooled session, reconnecting once on transient transport failure."""
        async with asyncio.timeout(timeout_sec):
            async with self._lock:
                for attempt in (0, 1):
                    session = await self._ensure_connected_locked(params)
                    try:
                        result = await session.call_tool(tool_name, arguments)
                        self._last_used = time.monotonic()
                        self.call_count += 1
                        return result
                    except Exception:
                        await self._close_locked()
                        if attempt == 1:
                            raise
        raise RuntimeError("StudioMcpSessionPool exhausted retries unexpectedly.")

    async def aclose(self) -> None:
        """Close the pooled StudioMCP stdio session and subprocess cleanly."""
        async with self._lock:
            await self._close_locked()


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
        idle_ttl = float(os.environ.get("SHARP_STUDIOMCP_IDLE_TTL_SEC", "120") or 120.0)
        self.session_pool = StudioMcpSessionPool(idle_ttl_sec=idle_ttl)
        self.plugins_dir = self.roblox_dir / "Plugins"
        self._cached_studio_id: Optional[str] = None
        self._cached_studio_ts: float = 0.0

    async def aclose(self) -> None:
        """Close pooled upstream connections."""
        await self.session_pool.aclose()

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
            result = await self.session_pool.call_tool(
                params,
                tool_name,
                arguments,
                timeout_sec=timeout_sec,
            )
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

    @staticmethod
    def _extract_operation_id(payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        op_id = payload.get("operationId")
        if isinstance(op_id, str) and op_id.strip():
            return op_id.strip()
        path_val = payload.get("path")
        if isinstance(path_val, str) and path_val.strip():
            parts = path_val.strip().split("/")
            if parts[-1]:
                return parts[-1]
        return None

    @staticmethod
    def _extract_asset_id(payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        resp = payload.get("response")
        if isinstance(resp, dict) and resp.get("assetId"):
            return str(resp["assetId"]).strip()
        if payload.get("assetId"):
            return str(payload["assetId"]).strip()
        return None

    async def _resolve_creator_user_id(
        self,
        *,
        studio_id: Optional[str],
        creator_user_id: Optional[str],
        credentials_path: Optional[str | Path],
    ) -> Optional[str]:
        if creator_user_id and str(creator_user_id).strip():
            return str(creator_user_id).strip()
        cred_creator = get_credentials_status(credentials_path).get("roblox_creator_id")
        if cred_creator and str(cred_creator).strip():
            return str(cred_creator).strip()
        if not studio_id:
            return None
        luau = (
            'local ok, uid = pcall(function() return game:GetService("StudioService"):GetUserId() end)\n'
            "if ok and tonumber(uid) and tonumber(uid) > 0 then return tostring(uid) end\n"
            "if game.CreatorType == Enum.CreatorType.User and game.CreatorId > 0 then\n"
            "\treturn tostring(game.CreatorId)\n"
            "end\n"
            'return ""'
        )
        res = await self.call_upstream_studio_mcp(
            "execute_luau",
            {"code": luau, "datamodel_type": "Edit", "studio_id": studio_id},
            timeout_sec=15.0,
        )
        if not res.get("ok"):
            return None
        raw = res.get("decoded")
        if raw is None and res.get("content"):
            raw = str(res["content"][0]).strip()
        cand = str(raw or "").strip().strip('"')
        return cand if cand.isdigit() and int(cand) > 0 else None

    async def _upload_via_open_cloud_key(
        self,
        *,
        api_key: str,
        resolved_file: Path,
        request_payload: Dict[str, Any],
        timeout_sec: float,
    ) -> Dict[str, Any]:
        url = "https://apis.roblox.com/assets/v1/assets"
        suffix = resolved_file.suffix.lower()
        content_type_map = {
            ".fbx": "model/fbx",
            ".glb": "model/gltf-binary",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
        }
        file_ctype = content_type_map.get(suffix) or mimetypes.guess_type(resolved_file.name)[0] or "application/octet-stream"
        form = aiohttp.FormData()
        form.add_field("request", json.dumps(request_payload), content_type="application/json")
        file_bytes = await asyncio.to_thread(resolved_file.read_bytes)
        form.add_field("fileContent", file_bytes, filename=resolved_file.name, content_type=file_ctype)

        headers = {"x-api-key": api_key}
        total_timeout = max(10.0, float(timeout_sec))
        deadline = time.monotonic() + total_timeout
        op_id: Optional[str] = None
        op_payload: Dict[str, Any] = {}
        asset_id: Optional[str] = None
        transient_statuses = {429, 502, 503, 504}
        max_transient_retries = 5

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=total_timeout)) as session:
                async with session.post(url, data=form, headers=headers) as resp:
                    raw_text = await resp.text()
                    try:
                        decoded = json.loads(raw_text) if raw_text.strip() else {}
                    except json.JSONDecodeError:
                        decoded = {"raw": redact_error(raw_text[:600], api_key)}
                    if resp.status >= 400:
                        return {
                            "ok": False,
                            "status_code": resp.status,
                            "error": redact_error(f"Open Cloud asset upload failed (HTTP {resp.status}).", api_key),
                            "response": decoded,
                        }

                op_payload = decoded if isinstance(decoded, dict) else {}
                asset_id = self._extract_asset_id(op_payload)
                op_id = self._extract_operation_id(op_payload)
                transient_retries = 0
                poll_delay = 1.0
                while not asset_id and not op_payload.get("done") and op_id and time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(poll_delay, remaining))
                    op_url = f"https://apis.roblox.com/assets/v1/operations/{op_id}"
                    async with session.get(op_url, headers=headers) as poll_resp:
                        poll_text = await poll_resp.text()
                        try:
                            poll_dec = json.loads(poll_text) if poll_text.strip() else {}
                        except json.JSONDecodeError:
                            poll_dec = {"raw": redact_error(poll_text[:600], api_key)}
                        if (
                            poll_resp.status in transient_statuses
                            and transient_retries < max_transient_retries
                            and time.monotonic() < deadline
                        ):
                            transient_retries += 1
                            backoff = min(8.0, 0.5 * (2 ** transient_retries))
                            retry_after = (
                                poll_resp.headers.get("Retry-After")
                                if hasattr(poll_resp, "headers") and poll_resp.headers
                                else None
                            )
                            if retry_after:
                                try:
                                    backoff = max(0.1, min(8.0, float(retry_after)))
                                except ValueError:
                                    pass
                            poll_delay = backoff
                            continue
                        if poll_resp.status >= 400:
                            return {
                                "ok": False,
                                "status_code": poll_resp.status,
                                "operation_id": op_id,
                                "error": redact_error(
                                    f"Open Cloud operation poll failed (HTTP {poll_resp.status}).",
                                    api_key,
                                ),
                                "response": poll_dec,
                            }
                        transient_retries = 0
                        poll_delay = 1.0
                        op_payload = poll_dec if isinstance(poll_dec, dict) else {}
                        asset_id = self._extract_asset_id(op_payload)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            err_payload: Dict[str, Any] = {
                "ok": False,
                "error": redact_error(f"Open Cloud asset upload request failed ({type(exc).__name__}): {exc}", api_key),
            }
            if op_id:
                err_payload["operation_id"] = op_id
            return err_payload

        if op_payload.get("error"):
            return {
                "ok": False,
                "operation_id": op_id,
                "error": f"Open Cloud operation returned error: {op_payload.get('error')}",
                "response": op_payload,
            }
        if not asset_id:
            return {
                "ok": False,
                "operation_id": op_id,
                "error": "Upload accepted but operation did not complete with an assetId before timeout.",
                "response": op_payload,
            }
        return {
            "ok": True,
            "upload_mode": "open_cloud_api_key",
            "asset_id": asset_id,
            "operation_id": op_id,
            "operation": op_payload,
        }

    async def _upload_via_studio_mcp(
        self,
        *,
        studio_id: str,
        resolved_file: Path,
        request_payload: Dict[str, Any],
        timeout_sec: float,
    ) -> Dict[str, Any]:
        post_res = await self.call_upstream_studio_mcp(
            "open_cloud_invoke",
            {
                "studio_id": studio_id,
                "method": "POST",
                "endpoint": "/assets/v1/assets",
                "scopes": ["asset:read", "asset:write"],
                "body": json.dumps(request_payload),
                "files": [{"name": "fileContent", "path": str(resolved_file)}],
            },
            timeout_sec=max(15.0, float(timeout_sec)),
        )
        if not post_res.get("ok"):
            err_msg = post_res.get("error") or (
                post_res.get("content")[0] if post_res.get("content") else "open_cloud_invoke POST failed."
            )
            return {"ok": False, "upload_mode": "studio_mcp_open_cloud_invoke", "error": err_msg, "upstream": post_res}

        op_payload = post_res.get("decoded")
        if not isinstance(op_payload, dict) and post_res.get("content"):
            try:
                cand = json.loads(post_res["content"][0])
                if isinstance(cand, dict):
                    op_payload = cand
            except Exception:
                op_payload = {}
        op_payload = op_payload if isinstance(op_payload, dict) else {}

        asset_id = self._extract_asset_id(op_payload)
        op_id = self._extract_operation_id(op_payload)
        deadline = time.monotonic() + max(10.0, float(timeout_sec))
        while not asset_id and not op_payload.get("done") and op_id and time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            poll_res = await self.call_upstream_studio_mcp(
                "open_cloud_invoke",
                {
                    "studio_id": studio_id,
                    "method": "GET",
                    "endpoint": f"/assets/v1/operations/{op_id}",
                    "scopes": ["asset:read"],
                },
                timeout_sec=15.0,
            )
            if not poll_res.get("ok"):
                err_msg = poll_res.get("error") or (
                    poll_res.get("content")[0] if poll_res.get("content") else "open_cloud_invoke operation poll failed."
                )
                return {
                    "ok": False,
                    "upload_mode": "studio_mcp_open_cloud_invoke",
                    "operation_id": op_id,
                    "error": err_msg,
                }
            poll_dec = poll_res.get("decoded")
            if isinstance(poll_dec, dict):
                op_payload = poll_dec
                asset_id = self._extract_asset_id(op_payload)

        if op_payload.get("error"):
            return {
                "ok": False,
                "upload_mode": "studio_mcp_open_cloud_invoke",
                "operation_id": op_id,
                "error": f"Studio MCP Open Cloud operation returned error: {op_payload.get('error')}",
                "operation": op_payload,
            }
        if not asset_id:
            return {
                "ok": False,
                "upload_mode": "studio_mcp_open_cloud_invoke",
                "operation_id": op_id,
                "error": "Studio MCP Open Cloud upload did not return an assetId.",
                "operation": op_payload,
            }
        return {
            "ok": True,
            "upload_mode": "studio_mcp_open_cloud_invoke",
            "asset_id": asset_id,
            "operation_id": op_id,
            "operation": op_payload,
        }

    async def upload_and_insert_roblox_asset(
        self,
        *,
        file_path: str | Path,
        asset_type: str = "Model",
        display_name: Optional[str] = None,
        description: str = "Uploaded via Sharp MCP",
        creator_user_id: Optional[str] = None,
        studio_id: Optional[str] = None,
        insert_into_studio: bool = True,
        parent_path: Optional[str] = None,
        sidecar_path: Optional[str | Path] = None,
        credentials_path: Optional[str | Path] = None,
        timeout_sec: float = 60.0,
    ) -> Dict[str, Any]:
        """Upload a local 3D/2D file to Roblox Open Cloud and optionally insert it into Studio."""
        resolved_file = Path(file_path).expanduser().resolve()
        if not resolved_file.is_file():
            return {"ok": False, "error": f"Asset file does not exist: {resolved_file}"}

        eff_name = (display_name or "").strip() or resolved_file.stem
        eff_type = (asset_type or "Model").strip() or "Model"
        eff_studio_id = (studio_id or "").strip() or await self.resolve_active_studio_id(studio_id)
        eff_creator_id = await self._resolve_creator_user_id(
            studio_id=eff_studio_id,
            creator_user_id=creator_user_id,
            credentials_path=credentials_path,
        )
        if not eff_creator_id:
            return {
                "ok": False,
                "error": (
                    "Could not resolve Roblox creator_user_id. Pass creator_user_id, save it via "
                    "sharp_ai_studio(action='keys_prompt_browser'), or keep Roblox Studio open while logged in."
                ),
            }

        request_payload = {
            "assetType": eff_type,
            "displayName": eff_name,
            "description": description or "Uploaded via Sharp MCP",
            "creationContext": {"creator": {"userId": str(eff_creator_id)}},
        }

        oc_key = get_api_key("roblox_open_cloud", credentials_path=credentials_path)
        if oc_key:
            upload_res = await self._upload_via_open_cloud_key(
                api_key=oc_key,
                resolved_file=resolved_file,
                request_payload=request_payload,
                timeout_sec=timeout_sec,
            )
        else:
            if not eff_studio_id:
                return {
                    "ok": False,
                    "error": (
                        "Neither ROBLOX_OPEN_CLOUD_API_KEY is configured nor an active Roblox Studio instance was found. "
                        "Use sharp_ai_studio(action='keys_prompt_browser') to enter a Roblox Open Cloud API key or open Studio."
                    ),
                }
            upload_res = await self._upload_via_studio_mcp(
                studio_id=eff_studio_id,
                resolved_file=resolved_file,
                request_payload=request_payload,
                timeout_sec=timeout_sec,
            )

        if not upload_res.get("ok"):
            return {
                **upload_res,
                "file_path": str(resolved_file),
                "display_name": eff_name,
                "asset_type": eff_type,
                "creator_user_id": eff_creator_id,
                "studio_id": eff_studio_id,
            }

        asset_id = str(upload_res["asset_id"])
        inserted_into_studio = False
        insert_res: Optional[Dict[str, Any]] = None
        if insert_into_studio and eff_studio_id:
            insert_args: Dict[str, Any] = {
                "assetId": asset_id,
                "assetName": eff_name,
                "assetType": eff_type,
                "studio_id": eff_studio_id,
            }
            if parent_path and parent_path.strip():
                insert_args["parentPath"] = parent_path.strip()
            insert_res = await self.call_upstream_studio_mcp(
                "insert_asset",
                insert_args,
                timeout_sec=max(15.0, float(timeout_sec)),
            )
            inserted_into_studio = bool(insert_res.get("ok"))

        sidecar_applied: Optional[Dict[str, Any]] = None
        if inserted_into_studio and eff_studio_id and sidecar_path:
            sc_file = Path(sidecar_path).expanduser()
            if sc_file.is_file():
                try:
                    sc_data = json.loads(sc_file.read_text(encoding="utf-8"))
                    slots_json = json.dumps(sc_data.get("material_slots_split") or [], ensure_ascii=False)
                    atts_json = json.dumps(sc_data.get("attachments") or [], ensure_ascii=False)
                    slots_lit = _luau_long_string(slots_json)
                    atts_lit = _luau_long_string(atts_json)
                    parent_expr = json.dumps((parent_path or "Workspace").strip())
                    name_expr = json.dumps(eff_name)
                    luau_cfg = f"""
local HttpService = game:GetService("HttpService")
local Workspace = game:GetService("Workspace")
local function resolveParent(pathStr)
\tif pathStr == "" or pathStr == "Workspace" then return Workspace end
\tlocal cur = game
\tlocal first = true
\tfor seg in string.gmatch(pathStr, "[^%.]+") do
\t\tif first then
\t\t\tlocal okS, s = pcall(function() return game:GetService(seg) end)
\t\t\tcur = if okS and s then s else cur:FindFirstChild(seg)
\t\telse
\t\t\tcur = cur and cur:FindFirstChild(seg)
\t\tend
\t\tfirst = false
\tend
\treturn cur or Workspace
end
local parentInst = resolveParent({parent_expr})
local candidates = parentInst:GetChildren()
local targetInst = nil
for i = #candidates, 1, -1 do
\tlocal ch = candidates[i]
\tif ch.Name == {name_expr} or string.find(ch.Name, {name_expr}, 1, true) then
\t\ttargetInst = ch
\t\tbreak
\tend
end
if not targetInst then return "NO_TARGET:" .. {name_expr} end
local slots = HttpService:JSONDecode({slots_lit})
local atts = HttpService:JSONDecode({atts_lit})
local parts = {{}}
for _, d in ipairs(targetInst:GetDescendants()) do
\tif d:IsA("PackageLink") then
\t\tpcall(function() d:Destroy() end)
\telseif d:IsA("BasePart") then
\t\ttable.insert(parts, d)
\tend
end
if targetInst:IsA("BasePart") then table.insert(parts, targetInst) end
local slotColored = 0
local refPart = nil
local refBbox = nil
local refIsSlot0 = false
for _, p in ipairs(parts) do
\tp.Anchored = false
\tp.CanCollide = false
\tp.Massless = true
\tlocal pname = p.Name
\tfor slIdx, sl in ipairs(slots) do
\t\tlocal sname = tostring(sl.slot_name or "")
\t\tif sname ~= "" and (string.find(pname, sname, 1, true) or #slots == 1) then
\t\t\tlocal rgb = sl.srgb_color
\t\t\tif type(rgb) == "table" and #rgb >= 3 then
\t\t\t\tp.Color = Color3.fromRGB(math.clamp(math.floor(rgb[1]),0,255), math.clamp(math.floor(rgb[2]),0,255), math.clamp(math.floor(rgb[3]),0,255))
\t\t\tend
\t\t\tlocal rmat = tostring(sl.roblox_material or "Metal")
\t\t\tpcall(function() p.Material = (Enum.Material :: any)[rmat] end)
\t\t\tlocal sa = p:FindFirstChildOfClass("SurfaceAppearance")
\t\t\tif sa then sa:Destroy() end
\t\t\tlocal bb = sl.bbox_center_blender
\t\t\tif type(bb) == "table" and #bb >= 3 then
\t\t\t\tlocal isSlot0 = (sl.slot_index == 0) or (sl.slot_index == nil and slIdx == 1)
\t\t\t\tif refPart == nil or (isSlot0 and not refIsSlot0) then
\t\t\t\t\trefPart = p
\t\t\t\t\trefBbox = bb
\t\t\t\t\trefIsSlot0 = isSlot0
\t\t\t\tend
\t\t\tend
\t\t\tslotColored += 1
\t\t\tbreak
\t\tend
\tend
end
local recoveredOrigin = nil
if refPart and refBbox then
\tlocal bx = tonumber(refBbox[1]) or 0
\tlocal by = tonumber(refBbox[2]) or 0
\tlocal bz = tonumber(refBbox[3]) or 0
\tif not targetInst:GetAttribute("SharpNormalizedOrigin") then
\t\tlocal origin = refPart.Position - Vector3.new(-bx, bz, by)
\t\tfor _, part in ipairs(parts) do
\t\t\tpart.CFrame = CFrame.new(origin) * CFrame.Angles(0, math.pi, 0) * CFrame.new(-origin) * part.CFrame
\t\tend
\t\ttargetInst:SetAttribute("SharpNormalizedOrigin", true)
\t\trecoveredOrigin = origin
\telse
\t\trecoveredOrigin = refPart.Position - Vector3.new(bx, bz, -by)
\tend
end
if targetInst:IsA("Model") then
\tlocal pivCF = if recoveredOrigin then CFrame.new(recoveredOrigin) else targetInst:GetPivot()
\tlocal handle = targetInst:FindFirstChild("Handle")
\tif not handle or not handle:IsA("BasePart") then
\t\thandle = Instance.new("Part")
\t\thandle.Name = "Handle"
\t\thandle.Size = Vector3.new(0.25, 0.25, 0.25)
\t\thandle.Transparency = 1
\t\thandle.CanCollide = false
\t\thandle.Massless = true
\t\thandle.Anchored = false
\t\thandle.CFrame = pivCF
\t\thandle.Parent = targetInst
\tend
\ttargetInst.PrimaryPart = handle
\tfor _, p in ipairs(parts) do
\t\tif p ~= handle then
\t\t\tlocal hasW = false
\t\t\tfor _, c in ipairs(handle:GetChildren()) do
\t\t\t\tif c:IsA("WeldConstraint") and (c.Part1 == p or c.Part0 == p) then hasW = true break end
\t\t\tend
\t\t\tif not hasW then
\t\t\t\tlocal w = Instance.new("WeldConstraint")
\t\t\t\tw.Part0 = handle
\t\t\t\tw.Part1 = p
\t\t\t\tw.Parent = handle
\t\t\tend
\t\tend
\tend
\tfor _, a in ipairs(atts) do
\t\tlocal aname = tostring(a.name or "")
\t\tif aname ~= "" and type(a.cframe) == "table" and #a.cframe >= 12 then
\t\t\tlocal existing = handle:FindFirstChild(aname)
\t\t\tif not existing then
\t\t\t\tlocal att = Instance.new("Attachment")
\t\t\t\tatt.Name = aname
\t\t\t\tlocal c = a.cframe
\t\t\t\tatt.CFrame = CFrame.new(c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10], c[11], c[12])
\t\t\t\tatt.Parent = handle
\t\t\tend
\t\tend
\tend
end
return string.format("CONFIGURED:%s parts=%d colored=%d", targetInst:GetFullName(), #parts, slotColored)
"""
                    sidecar_applied = await self.call_upstream_studio_mcp(
                        "execute_luau",
                        {"code": luau_cfg, "datamodel_type": "Edit", "studio_id": eff_studio_id},
                        timeout_sec=15.0,
                    )
                except Exception as exc:
                    sidecar_applied = {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "upload_mode": upload_res.get("upload_mode"),
            "asset_id": asset_id,
            "rbxassetid": f"rbxassetid://{asset_id}",
            "display_name": eff_name,
            "asset_type": eff_type,
            "creator_user_id": eff_creator_id,
            "studio_id": eff_studio_id,
            "operation_id": upload_res.get("operation_id"),
            "inserted_into_studio": inserted_into_studio,
            "insert_result": insert_res,
            "sidecar_configured": sidecar_applied,
        }
