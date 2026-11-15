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
import os
import sys
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
            and studio_id
        ):
            upstream_res = await self.call_upstream_studio_mcp(
                tool_name="execute_luau",
                arguments={
                    "code": compiled_luau,
                    "datamodel_type": "Edit",
                    "studio_id": studio_id,
                },
            )
            return {
                "executionMode": "Upstream_StudioMCP_Subprocess",
                "upstreamResponse": upstream_res,
            }

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
    ) -> Dict[str, Any]:
        """Dispatches a structured `module_op` payload when SharpBridgePlugin is online."""
        broker_status = await self.ensure_broker_started()
        if not self.broker.is_plugin_online():
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
                        return {
                            "ok": not getattr(result, "isError", False),
                            "tool": tool_name,
                            "content": texts,
                        }
        except Exception as exc:
            return {"ok": False, "optional": True, "tool": tool_name, "error": str(exc)}
