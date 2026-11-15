"""Loopback HTTP Bridge Broker (`127.0.0.1:58421`) for SharpBridgePlugin.

Implements:
- Strict loopback peer IPv4/IPv6 validation (`403 FORBIDDEN_NON_LOOPBACK`)
- Strict `Host` header allowlist (`127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>` -> `403 FORBIDDEN_HOST_HEADER`)
- Anti-CSRF / anti-DNS-rebinding (`403 FORBIDDEN_ORIGIN_HEADER` on `Origin`, `403 FORBIDDEN_BROWSER_FETCH` on `Sec-Fetch-*`)
- Fail-closed token authentication (`sessionToken` + `X-Sharp-Server-Epoch` issued on `/v1/hello`)
- Stale-target binding (`expected_place_id` / `expected_session_nonce` -> `STALE_TARGET_PLACE`)
- 1-Writer / 4-Reader concurrency mutex (`BUSY` on contention)
- Delivery leases with `/v1/heartbeat` extension and `outcome_unknown` transition
  on lease timeout (timed-out writes are NEVER auto-replayed)
- 500-entry deduplication result cache
- UTF-8 multi-chunk payload reassembly (`/v1/result_chunk` + `/v1/result_commit`)
- `planHash` SHA-256 computation & verification for bulk/destructive operations
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import secrets
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import web


def validate_local_http_request(
    request: web.Request,
    expected_port: Optional[int] = None,
) -> Optional[web.Response]:
    """Enforces loopback peer IP, strict Host allowlist, and browser CSRF header rejection."""
    peer_ip: Optional[str] = None
    transport = getattr(request, "transport", None)
    if transport is not None:
        peername = transport.get_extra_info("peername")
        if isinstance(peername, tuple) and len(peername) >= 1 and isinstance(peername[0], str):
            peer_ip = peername[0]
        elif isinstance(peername, str) and peername:
            peer_ip = peername
    if peer_ip is None:
        remote_val = getattr(request, "remote", None)
        if isinstance(remote_val, str) and remote_val:
            peer_ip = remote_val

    if peer_ip is not None:
        cleaned_ip = peer_ip.split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(cleaned_ip)
        except ValueError:
            return web.json_response(
                {"ok": False, "error": "FORBIDDEN_NON_LOOPBACK", "remote": peer_ip},
                status=403,
            )
        is_loopback = addr.is_loopback or (
            isinstance(addr, ipaddress.IPv6Address)
            and addr.ipv4_mapped is not None
            and addr.ipv4_mapped.is_loopback
        )
        if not is_loopback:
            return web.json_response(
                {"ok": False, "error": "FORBIDDEN_NON_LOOPBACK", "remote": peer_ip},
                status=403,
            )

    active_port = expected_port
    if transport is not None:
        sockname = transport.get_extra_info("sockname")
        if (
            isinstance(sockname, tuple)
            and len(sockname) >= 2
            and isinstance(sockname[1], int)
            and sockname[1] > 0
        ):
            active_port = sockname[1]

    host_hdr = (request.headers.get("Host") or "").strip().lower()
    if active_port is not None and active_port > 0:
        allowed_hosts = {
            f"127.0.0.1:{active_port}",
            f"localhost:{active_port}",
            f"[::1]:{active_port}",
        }
        if host_hdr not in allowed_hosts:
            return web.json_response(
                {"ok": False, "error": "FORBIDDEN_HOST_HEADER", "host": host_hdr},
                status=403,
            )
    else:
        if host_hdr not in {"127.0.0.1", "localhost", "[::1]"}:
            return web.json_response(
                {"ok": False, "error": "FORBIDDEN_HOST_HEADER", "host": host_hdr},
                status=403,
            )

    if "Origin" in request.headers:
        return web.json_response(
            {"ok": False, "error": "FORBIDDEN_ORIGIN_HEADER"},
            status=403,
        )

    for hdr_name in request.headers.keys():
        if hdr_name.lower().startswith("sec-fetch-"):
            return web.json_response(
                {"ok": False, "error": "FORBIDDEN_BROWSER_FETCH"},
                status=403,
            )

    return None


@dataclass
class BridgeJob:
    request_id: str
    epoch: str
    attempt: int
    kind: str  # "read" | "write"
    tool: str
    args: Dict[str, Any]
    lease_ms: int = 10000
    expected_place_id: Optional[int] = None
    expected_session_nonce: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)
    dispatched_at: Optional[float] = None
    last_heartbeat_at: Optional[float] = None
    status: str = "queued"  # queued | in_flight | committed | failed | outcome_unknown
    result: Optional[Dict[str, Any]] = None
    future: Optional[asyncio.Future] = None


class BridgeBroker:
    """Manages communication with SharpBridgePlugin.rbxmx on 127.0.0.1:58421."""

    MAX_READERS = 4
    DEDUP_CACHE_LIMIT = 500
    EPOCH_HEADER = "X-Sharp-Server-Epoch"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 58421,
        require_explicit_token_for_non_loopback: bool = True,
    ) -> None:
        if host not in ("127.0.0.1", "::1", "localhost"):
            if require_explicit_token_for_non_loopback and not os.environ.get("SHARP_SESSION_TOKEN"):
                raise ValueError(
                    f"Refusing to bind non-loopback host '{host}' without explicit SHARP_SESSION_TOKEN."
                )

        self.host = host
        self.port = port
        self.server_epoch = f"epoch_{int(time.time())}_{secrets.token_hex(4)}"
        self.session_token = os.environ.get("SHARP_SESSION_TOKEN") or secrets.token_hex(32)

        # Connected Studio Plugin state
        self.connected_studio: Optional[Dict[str, Any]] = None
        self.last_seen_monotonic: float = 0.0

        # Concurrency & Queue state
        self.active_writer: Optional[str] = None
        self.active_readers: set[str] = set()
        self.pending_queue: asyncio.Queue[BridgeJob] = asyncio.Queue()
        self.in_flight: Dict[str, BridgeJob] = {}
        self.dedup_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.chunk_buffers: Dict[str, List[Tuple[int, str]]] = {}
        self.action_log: List[Dict[str, Any]] = []

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    @staticmethod
    def compute_plan_hash(tool_name: str, canonical_payload: Dict[str, Any]) -> str:
        raw = json.dumps(
            {"tool": tool_name, "payload": canonical_payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def is_plugin_online(self, max_stale_seconds: float = 35.0) -> bool:
        if not self.connected_studio:
            return False
        return (time.monotonic() - self.last_seen_monotonic) <= max_stale_seconds

    def can_acquire_mutex(self, kind: str) -> Tuple[bool, Optional[str]]:
        if kind == "write":
            if self.active_writer is not None:
                return False, f"Active writer job '{self.active_writer}' in progress"
            if len(self.active_readers) > 0:
                return False, f"{len(self.active_readers)} active reader job(s) in progress"
            return True, None
        else:
            if self.active_writer is not None:
                return False, f"Active writer job '{self.active_writer}' in progress"
            if len(self.active_readers) >= self.MAX_READERS:
                return False, f"Max concurrent readers ({self.MAX_READERS}) reached"
            return True, None

    def _acquire_mutex(self, request_id: str, kind: str) -> bool:
        ok, _ = self.can_acquire_mutex(kind)
        if not ok:
            return False
        if kind == "write":
            self.active_writer = request_id
        else:
            self.active_readers.add(request_id)
        return True

    def _release_mutex(self, request_id: str) -> None:
        if self.active_writer == request_id:
            self.active_writer = None
        self.active_readers.discard(request_id)

    def _record_dedup(self, request_id: str, payload: Dict[str, Any]) -> None:
        self.dedup_cache[request_id] = payload
        self.dedup_cache.move_to_end(request_id)
        while len(self.dedup_cache) > self.DEDUP_CACHE_LIMIT:
            self.dedup_cache.popitem(last=False)

    def _check_stale_target(
        self,
        expected_place_id: Optional[int],
        expected_session_nonce: Optional[str],
        result_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if expected_place_id is None and expected_session_nonce is None:
            return None

        studio = self.connected_studio
        if not studio:
            return {
                "ok": False,
                "code": "STALE_TARGET_PLACE",
                "message": "Connected Studio session disappeared or never completed /v1/hello.",
                "expectedPlaceId": expected_place_id,
                "expectedSessionNonce": expected_session_nonce,
                "actualPlaceId": None,
                "actualSessionNonce": None,
            }

        actual_place = studio.get("placeId")
        actual_nonce = studio.get("studioSessionId")

        if expected_place_id is not None and actual_place != expected_place_id:
            return {
                "ok": False,
                "code": "STALE_TARGET_PLACE",
                "message": f"Target PlaceId changed mid-flight (expected {expected_place_id}, got {actual_place}).",
                "expectedPlaceId": expected_place_id,
                "actualPlaceId": actual_place,
                "expectedSessionNonce": expected_session_nonce,
                "actualSessionNonce": actual_nonce,
            }

        if expected_session_nonce is not None and actual_nonce != expected_session_nonce:
            return {
                "ok": False,
                "code": "STALE_TARGET_PLACE",
                "message": (
                    f"Target studioSessionId changed mid-flight "
                    f"(expected '{expected_session_nonce}', got '{actual_nonce}')."
                ),
                "expectedPlaceId": expected_place_id,
                "actualPlaceId": actual_place,
                "expectedSessionNonce": expected_session_nonce,
                "actualSessionNonce": actual_nonce,
            }

        if result_body is not None:
            if (
                expected_place_id is not None
                and "placeId" in result_body
                and result_body.get("placeId") != expected_place_id
            ):
                return {
                    "ok": False,
                    "code": "STALE_TARGET_PLACE",
                    "message": (
                        f"Result PlaceId mismatch (expected {expected_place_id}, "
                        f"got {result_body.get('placeId')})."
                    ),
                    "expectedPlaceId": expected_place_id,
                    "actualPlaceId": result_body.get("placeId"),
                    "expectedSessionNonce": expected_session_nonce,
                    "actualSessionNonce": result_body.get("studioSessionId", actual_nonce),
                }
            if (
                expected_session_nonce is not None
                and "studioSessionId" in result_body
                and result_body.get("studioSessionId") != expected_session_nonce
            ):
                return {
                    "ok": False,
                    "code": "STALE_TARGET_PLACE",
                    "message": (
                        f"Result studioSessionId mismatch (expected '{expected_session_nonce}', "
                        f"got '{result_body.get('studioSessionId')}')."
                    ),
                    "expectedPlaceId": expected_place_id,
                    "actualPlaceId": result_body.get("placeId", actual_place),
                    "expectedSessionNonce": expected_session_nonce,
                    "actualSessionNonce": result_body.get("studioSessionId"),
                }

        return None

    def _check_headers(self, request: web.Request, require_auth: bool = True) -> Optional[web.Response]:
        local_err = validate_local_http_request(request, expected_port=self.port)
        if local_err is not None:
            return local_err

        if request.method == "POST":
            ctype = request.headers.get("Content-Type", "")
            if "application/json" not in ctype.lower():
                return web.json_response(
                    {"ok": False, "error": "UNSUPPORTED_CONTENT_TYPE"},
                    status=415,
                )
        if require_auth:
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {self.session_token}"
            if not secrets.compare_digest(auth, expected):
                return web.json_response(
                    {"ok": False, "error": "UNAUTHORIZED_TOKEN"},
                    status=401,
                )
            epoch = request.headers.get(self.EPOCH_HEADER, "")
            if epoch != self.server_epoch:
                return web.json_response(
                    {
                        "ok": False,
                        "error": "EPOCH_MISMATCH",
                        "expectedEpoch": self.server_epoch,
                    },
                    status=409,
                )
        return None

    async def handle_hello(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=False)
        if err is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "INVALID_JSON"}, status=400)

        self.connected_studio = {
            "studioSessionId": body.get("studioSessionId", "unknown"),
            "placeId": body.get("placeId", 0),
            "universeId": body.get("universeId", 0),
            "placeName": body.get("placeName", "UnknownPlace"),
            "pluginVersion": body.get("pluginVersion", "0.2.0"),
            "safetyMode": body.get("safetyMode", "Safe Mutate"),
            "capabilities": body.get("capabilities", {}),
            "httpEnabled": body.get("httpEnabled", True),
        }
        self.last_seen_monotonic = time.monotonic()
        return web.json_response({
            "ok": True,
            "sessionToken": self.session_token,
            "serverEpoch": self.server_epoch,
            "recommendedPollMs": 20000,
            "supportsWebSocket": False,
        })

    async def handle_poll(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=True)
        if err is not None:
            return err

        self.last_seen_monotonic = time.monotonic()
        try:
            raw_timeout = int(request.query.get("timeoutMs", "5000"))
        except ValueError:
            raw_timeout = 5000
        timeout_ms = min(25000, max(50, raw_timeout))
        deadline = time.monotonic() + (timeout_ms / 1000.0)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return web.Response(status=204)
            try:
                job = await asyncio.wait_for(
                    self.pending_queue.get(), timeout=remaining
                )
            except asyncio.TimeoutError:
                return web.Response(status=204)

            # Skip jobs whose lease already expired while waiting in the queue
            if job.status in ("outcome_unknown", "failed") or (job.future and job.future.done()):
                continue

            stale_err = self._check_stale_target(job.expected_place_id, job.expected_session_nonce)
            if stale_err is not None:
                self._release_mutex(job.request_id)
                job.status = "failed"
                job.result = stale_err
                if job.future and not job.future.done():
                    job.future.set_result(stale_err)
                continue
            break

        job.status = "in_flight"
        job.dispatched_at = time.monotonic()
        job.last_heartbeat_at = job.dispatched_at
        self.in_flight[job.request_id] = job

        return web.json_response({
            "requestId": job.request_id,
            "epoch": job.epoch,
            "attempt": job.attempt,
            "leaseMs": job.lease_ms,
            "kind": job.kind,
            "tool": job.tool,
            "args": job.args,
            "expectedPlaceId": job.expected_place_id,
            "expectedSessionNonce": job.expected_session_nonce,
        })

    async def handle_heartbeat(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=True)
        if err is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "INVALID_JSON"}, status=400)
        req_id = str(body.get("requestId", ""))
        self.last_seen_monotonic = time.monotonic()

        job = self.in_flight.get(req_id)
        if not job:
            return web.json_response({"ok": False, "error": "UNKNOWN_IN_FLIGHT_JOB"}, status=404)

        stale_err = self._check_stale_target(
            job.expected_place_id, job.expected_session_nonce, result_body=body
        )
        if stale_err is not None:
            self.in_flight.pop(req_id, None)
            self._release_mutex(req_id)
            job.status = "failed"
            job.result = stale_err
            if job.future and not job.future.done():
                job.future.set_result(stale_err)
            return web.json_response(stale_err, status=409)

        job.last_heartbeat_at = time.monotonic()
        return web.json_response({"ok": True, "leaseExtendedMs": job.lease_ms})

    async def handle_result(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=True)
        if err is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "INVALID_JSON"}, status=400)
        return self._finalize_job_result(body)

    async def handle_result_chunk(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=True)
        if err is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "INVALID_JSON"}, status=400)
        req_id = str(body.get("requestId", ""))
        idx = int(body.get("chunkIndex", 0))
        data = str(body.get("chunkData", ""))

        if req_id not in self.chunk_buffers:
            self.chunk_buffers[req_id] = []
        self.chunk_buffers[req_id].append((idx, data))
        self.last_seen_monotonic = time.monotonic()
        if req_id in self.in_flight:
            self.in_flight[req_id].last_heartbeat_at = self.last_seen_monotonic
        return web.json_response({"ok": True, "receivedChunk": idx})

    async def handle_result_commit(self, request: web.Request) -> web.Response:
        err = self._check_headers(request, require_auth=True)
        if err is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "INVALID_JSON"}, status=400)
        req_id = str(body.get("requestId", ""))
        chunks = self.chunk_buffers.pop(req_id, [])
        chunks.sort(key=lambda x: x[0])
        reassembled = "".join(part for _, part in chunks)
        try:
            envelope = json.loads(reassembled)
        except Exception as exc:
            return web.json_response(
                {"ok": False, "error": f"CHUNK_JSON_DECODE_ERROR: {exc}"},
                status=400,
            )
        return self._finalize_job_result(envelope)

    def _finalize_job_result(self, body: Dict[str, Any]) -> web.Response:
        req_id = str(body.get("requestId", ""))
        self.last_seen_monotonic = time.monotonic()

        # Idempotent deduplication check
        if req_id in self.dedup_cache:
            return web.json_response({"ok": True, "deduplicated": True})

        job = self.in_flight.pop(req_id, None)
        self._release_mutex(req_id)

        if not job:
            return web.json_response({"ok": False, "error": "JOB_NOT_FOUND_OR_EXPIRED"}, status=404)

        stale_err = self._check_stale_target(
            job.expected_place_id, job.expected_session_nonce, result_body=body
        )
        if stale_err is not None:
            job.status = "failed"
            job.result = stale_err
            if job.future and not job.future.done():
                job.future.set_result(stale_err)
            return web.json_response(stale_err, status=409)

        job.status = "committed" if body.get("ok", False) else "failed"
        job.result = body
        self._record_dedup(req_id, body)

        self.action_log.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "requestId": req_id,
            "tool": job.tool,
            "kind": job.kind,
            "ok": bool(body.get("ok", False)),
            "recordingStatus": body.get("recordingStatus", "None"),
        })
        if len(self.action_log) > 20:
            self.action_log = self.action_log[-20:]

        if job.future and not job.future.done():
            job.future.set_result(body)

        return web.json_response({"ok": True, "deduplicated": False})

    async def dispatch_job(
        self,
        tool: str,
        args: Dict[str, Any],
        kind: str = "write",
        lease_ms: int = 10000,
        request_id: Optional[str] = None,
        expected_place_id: Optional[int] = None,
        expected_session_nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches a job to the connected Studio Plugin with mutex, lease & target binding."""
        stale_err = self._check_stale_target(expected_place_id, expected_session_nonce)
        if stale_err is not None:
            return stale_err

        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"

        if req_id in self.dedup_cache:
            cached = dict(self.dedup_cache[req_id])
            cached["deduplicated"] = True
            return cached

        if not self._acquire_mutex(req_id, kind):
            _, reason = self.can_acquire_mutex(kind)
            return {
                "ok": False,
                "code": "BUSY",
                "message": reason or "Mutex busy",
                "retryAfterMs": 1000,
            }

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        job = BridgeJob(
            request_id=req_id,
            epoch=self.server_epoch,
            attempt=1,
            kind=kind,
            tool=tool,
            args=args,
            lease_ms=lease_ms,
            expected_place_id=expected_place_id,
            expected_session_nonce=expected_session_nonce,
            future=fut,
        )
        await self.pending_queue.put(job)

        # Monitor lease expiration, heartbeats & target session continuity
        lease_sec = lease_ms / 1000.0
        try:
            while not fut.done():
                await asyncio.sleep(min(0.05, lease_sec / 4.0))
                if fut.done():
                    break

                midflight_stale = self._check_stale_target(
                    expected_place_id, expected_session_nonce
                )
                if midflight_stale is not None:
                    self.in_flight.pop(req_id, None)
                    self._release_mutex(req_id)
                    job.status = "failed"
                    job.result = midflight_stale
                    midflight_stale["requestId"] = req_id
                    return midflight_stale

                now = time.monotonic()
                ref_time = job.last_heartbeat_at or job.created_at
                if (now - ref_time) > lease_sec:
                    # Lease expired! Remove from in_flight & release mutex.
                    self.in_flight.pop(req_id, None)
                    self._release_mutex(req_id)
                    job.status = "outcome_unknown" if kind == "write" else "failed"
                    return {
                        "ok": False,
                        "code": "LEASE_EXPIRED_OUTCOME_UNKNOWN" if kind == "write" else "LEASE_EXPIRED",
                        "requestId": req_id,
                        "autoReplayed": False,
                        "message": (
                            "Studio plugin lease expired before completion; write job marked "
                            "outcome_unknown and NEVER auto-replayed."
                        ),
                    }
            return await fut
        finally:
            self._release_mutex(req_id)

    async def send_module_op(
        self,
        module_name: str,
        op: str,
        args: Optional[Dict[str, Any]] = None,
        kind: str = "read",
        lease_ms: int = 15000,
        request_id: Optional[str] = None,
        expected_place_id: Optional[int] = None,
        expected_session_nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches a direct embedded-ModuleScript operation without loadstring."""
        return await self.dispatch_job(
            tool=f"{module_name}.{op}",
            args={
                "mode": "module_op",
                "module": module_name,
                "op": op,
                "args": dict(args or {}),
            },
            kind=kind,
            lease_ms=lease_ms,
            request_id=request_id,
            expected_place_id=expected_place_id,
            expected_session_nonce=expected_session_nonce,
        )

    def create_web_app(self) -> web.Application:
        app = web.Application(client_max_size=4 * 1024 * 1024)
        app.router.add_post("/v1/hello", self.handle_hello)
        app.router.add_get("/v1/poll", self.handle_poll)
        app.router.add_post("/v1/heartbeat", self.handle_heartbeat)
        app.router.add_post("/v1/result", self.handle_result)
        app.router.add_post("/v1/result_chunk", self.handle_result_chunk)
        app.router.add_post("/v1/result_commit", self.handle_result_commit)
        return app

    async def start(self) -> int:
        if self._runner is not None:
            return self.port
        self._app = self.create_web_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        # Resolve actual bound port if port=0 was passed in unit tests
        if self._site._server and self._site._server.sockets:
            self.port = self._site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self._app = None

    def get_status_snapshot(self) -> Dict[str, Any]:
        return {
            "bridgeHost": self.host,
            "bridgePort": self.port,
            "serverEpoch": self.server_epoch,
            "pluginOnline": self.is_plugin_online(),
            "connectedStudio": self.connected_studio,
            "activeWriter": self.active_writer,
            "activeReadersCount": len(self.active_readers),
            "dedupCacheEntries": len(self.dedup_cache),
            "recentActions": self.action_log,
        }
