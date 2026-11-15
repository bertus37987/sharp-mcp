"""Transient Single-Use Loopback Asset Server (`127.0.0.1:<ephemeral_port>`) for Studio image uploads.

Spawns an on-demand loopback HTTP server that exposes only explicitly staged image/atlas
files under a single-use random token URL (`http://127.0.0.1:<port>/<token>/<filename>`),
rejects non-loopback peers / spoofed Host headers / browser Origin & Sec-Fetch-* headers,
consumes each `(token, filename)` on first valid fetch, and auto-stops after TTL.
"""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from aiohttp import web

from .bridge_broker import validate_local_http_request


class TransientAssetServer:
    """Serves staged PNG/asset files on loopback with single-use token URLs and auto-TTL."""

    MAX_CONSUMED_HISTORY = 1024

    def __init__(self, host: str = "127.0.0.1", ttl_seconds: float = 60.0) -> None:
        self.host = host
        self.ttl_seconds = ttl_seconds
        self.port: int = 0
        self.batches: Dict[str, Dict[str, Path]] = {}
        self._consumed: Set[Tuple[str, str]] = set()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._ttl_task: Optional[asyncio.Task] = None

    async def _handle_file(self, request: web.Request) -> web.StreamResponse:
        sec_err = validate_local_http_request(request, expected_port=self.port or None)
        if sec_err is not None:
            return sec_err

        token = request.match_info.get("token", "")
        filename = request.match_info.get("filename", "")
        if (token, filename) in self._consumed:
            return web.Response(status=410, text="Gone: single-use asset token already consumed")

        batch = self.batches.get(token)
        if not batch or filename not in batch:
            return web.Response(status=404, text="Not Found")

        file_path = batch.pop(filename)
        if not batch:
            self.batches.pop(token, None)

        if len(self._consumed) >= self.MAX_CONSUMED_HISTORY:
            self._consumed.clear()
        self._consumed.add((token, filename))

        if not file_path.is_file():
            return web.Response(status=404, text="File Missing")

        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        return web.Response(body=data, content_type=ctype)

    def create_web_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/{token}/{filename}", self._handle_file, allow_head=False)
        return app

    async def ensure_started(self) -> int:
        if self._runner is not None and self.port > 0:
            return self.port
        app = self.create_web_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, 0)
        await self._site.start()
        if self._site._server and self._site._server.sockets:
            self.port = self._site._server.sockets[0].getsockname()[1]
        return self.port

    async def stage_files(self, file_paths: List[Path]) -> Dict[str, str]:
        """Stages a list of local files and returns their single-use transient HTTP URLs."""
        port = await self.ensure_started()
        token = secrets.token_urlsafe(16)
        mapping: Dict[str, Path] = {}
        urls: Dict[str, str] = {}
        host_fmt = f"[{self.host}]" if ":" in self.host else self.host

        for p in file_paths:
            resolved = p.resolve()
            if resolved.is_file():
                mapping[resolved.name] = resolved
                urls[resolved.name] = f"http://{host_fmt}:{port}/{token}/{resolved.name}"

        self.batches[token] = mapping

        # Reset auto-shutdown TTL timer
        if self._ttl_task and not self._ttl_task.done():
            self._ttl_task.cancel()
        self._ttl_task = asyncio.create_task(self._auto_shutdown_after_ttl())
        return urls

    async def _auto_shutdown_after_ttl(self) -> None:
        try:
            await asyncio.sleep(self.ttl_seconds)
            await self.stop()
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self.batches.clear()
        self._consumed.clear()
        if self._ttl_task and not self._ttl_task.done():
            self._ttl_task.cancel()
            self._ttl_task = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self.port = 0
