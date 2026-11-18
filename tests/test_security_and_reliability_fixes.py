"""Targeted unit and HTTP tests for P0/P1 security & bridge reliability fixes.

Covers:
- S1: BridgeBroker.handle_hello() session takeover protection (409 SESSION_ALREADY_ACTIVE)
- S2: Fail-closed loopback peer validation in bridge_broker.py & credentials_store.py +
      strict Host/Origin validation and browser history/cookie token hardening
- S3: Restrictive atomic credential file writes (_write_store via os.open(..., 0o600))
- B2: BridgeBroker /v1/result_chunk in_flight validation, byte cap (413), idempotent retry,
      chunk buffer purging on timeout/stale-target/finalize, and plugin sendResult retry/abort
- B5: Studio plugin Mode B compiledLuau read recordingStatus == "None"
- S4: Studio plugin isDestructiveRequest() expanded Terrain:Clear / GetService / whitespace checks
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import aiohttp

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sharp_mcp.bridge_broker import BridgeBroker, validate_local_http_request
from sharp_mcp.credentials_store import (
    _is_loopback_peer,
    _is_valid_loopback_host,
    _write_store,
    async_prompt_credentials_in_browser,
    get_credentials_status,
)


def _lua_pattern_to_regex(lua_pat: str) -> str:
    """Convert the subset of Lua patterns used in isDestructiveRequest() to Python regex."""
    out: list[str] = []
    i = 0
    n = len(lua_pat)
    while i < n:
        ch = lua_pat[i]
        if ch == "%" and i + 1 < n:
            nxt = lua_pat[i + 1]
            if nxt == "s":
                out.append(r"\s")
            elif nxt in "().+-*?[]^$%":
                out.append(re.escape(nxt))
            else:
                out.append(re.escape(nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


class TestBridgeBrokerSecurityAndReliability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.broker = BridgeBroker(host="127.0.0.1", port=0)
        await self.broker.start()
        self.base_url = f"http://127.0.0.1:{self.broker.port}"

    async def asyncTearDown(self) -> None:
        await self.broker.stop()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.broker.session_token}",
            BridgeBroker.EPOCH_HEADER: self.broker.server_epoch,
        }

    def test_s2_validate_local_http_request_fails_closed_on_missing_or_empty_peer(self) -> None:
        host_hdr = {"Host": f"127.0.0.1:{self.broker.port}"}
        empty_peer_transport = SimpleNamespace(get_extra_info=lambda key: ("", 54321) if key == "peername" else None)
        none_peer_transport = SimpleNamespace(get_extra_info=lambda key: None)

        cases = [
            SimpleNamespace(transport=None, remote=None, headers=host_hdr),
            SimpleNamespace(transport=None, remote="", headers=host_hdr),
            SimpleNamespace(transport=None, remote="   ", headers=host_hdr),
            SimpleNamespace(transport=empty_peer_transport, remote=None, headers=host_hdr),
            SimpleNamespace(transport=none_peer_transport, remote="", headers=host_hdr),
        ]
        for req in cases:
            resp = validate_local_http_request(req, expected_port=self.broker.port)
            self.assertIsNotNone(resp, f"Expected 403 for fail-closed peer case: {req}")
            self.assertEqual(resp.status, 403)
            self.assertEqual(json.loads(resp.text)["error"], "FORBIDDEN_NON_LOOPBACK")

        # Valid loopback peers still pass
        for loopback in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            req = SimpleNamespace(transport=None, remote=loopback, headers=host_hdr)
            self.assertIsNone(validate_local_http_request(req, expected_port=self.broker.port))

    async def test_s1_handle_hello_prevents_unauthenticated_session_takeover(self) -> None:
        async with aiohttp.ClientSession() as client:
            # 1. Initial hello when offline succeeds without auth
            async with client.post(
                f"{self.base_url}/v1/hello",
                json={"studioSessionId": "sess_owner", "placeId": 1001, "placeName": "OwnerPlace"},
            ) as r1:
                self.assertEqual(r1.status, 200)
                h1 = await r1.json()
                self.assertTrue(h1["ok"])
                self.assertEqual(h1["sessionToken"], self.broker.session_token)

            # 2. Same studioSessionId reconnects while online -> allowed (200)
            async with client.post(
                f"{self.base_url}/v1/hello",
                json={"studioSessionId": "sess_owner", "placeId": 1001, "placeName": "OwnerPlace"},
            ) as r_same:
                self.assertEqual(r_same.status, 200)
                self.assertEqual((await r_same.json())["sessionToken"], self.broker.session_token)

            # 3. Different studioSessionId WITHOUT Bearer auth while online -> 409 SESSION_ALREADY_ACTIVE
            async with client.post(
                f"{self.base_url}/v1/hello",
                json={"studioSessionId": "sess_attacker", "placeId": 9999, "placeName": "EvilPlace"},
            ) as r_hijack:
                self.assertEqual(r_hijack.status, 409)
                body = await r_hijack.json()
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"], "SESSION_ALREADY_ACTIVE")
                self.assertNotIn("sessionToken", body)
                self.assertNotIn("sess_owner", json.dumps(body))
            self.assertEqual(self.broker.connected_studio["studioSessionId"], "sess_owner")
            self.assertEqual(self.broker.connected_studio["placeId"], 1001)

            # 4. Different studioSessionId WITH wrong Bearer token -> 409 SESSION_ALREADY_ACTIVE
            async with client.post(
                f"{self.base_url}/v1/hello",
                headers={"Authorization": "Bearer wrong_token_value"},
                json={"studioSessionId": "sess_attacker_2", "placeId": 9999},
            ) as r_bad_auth:
                self.assertEqual(r_bad_auth.status, 409)
                self.assertEqual((await r_bad_auth.json())["error"], "SESSION_ALREADY_ACTIVE")
            self.assertEqual(self.broker.connected_studio["studioSessionId"], "sess_owner")

            # 5. Different studioSessionId WITH valid Bearer auth -> 200 takeover allowed
            async with client.post(
                f"{self.base_url}/v1/hello",
                headers={"Authorization": f"Bearer {self.broker.session_token}"},
                json={"studioSessionId": "sess_handoff", "placeId": 2002, "placeName": "NextPlace"},
            ) as r_handoff:
                self.assertEqual(r_handoff.status, 200)
                self.assertEqual((await r_handoff.json())["sessionToken"], self.broker.session_token)
            self.assertEqual(self.broker.connected_studio["studioSessionId"], "sess_handoff")
            self.assertEqual(self.broker.connected_studio["placeId"], 2002)

            # 6. Once current plugin goes offline/stale, a new session can connect without auth
            self.broker.last_seen_monotonic -= 60.0
            self.assertFalse(self.broker.is_plugin_online())
            async with client.post(
                f"{self.base_url}/v1/hello",
                json={"studioSessionId": "sess_fresh", "placeId": 3003, "placeName": "FreshPlace"},
            ) as r_fresh:
                self.assertEqual(r_fresh.status, 200)
                self.assertEqual((await r_fresh.json())["sessionToken"], self.broker.session_token)
            self.assertEqual(self.broker.connected_studio["studioSessionId"], "sess_fresh")

    async def test_b2_result_chunk_validation_cap_idempotent_retry_and_purge(self) -> None:
        async with aiohttp.ClientSession() as client:
            async with client.post(
                f"{self.base_url}/v1/hello",
                json={"studioSessionId": "sess_chunks", "placeId": 555},
            ) as r:
                self.assertEqual(r.status, 200)

            # 1. Unknown requestId (not in_flight) -> 404 UNKNOWN_IN_FLIGHT_JOB
            async with client.post(
                f"{self.base_url}/v1/result_chunk",
                headers=self._auth_headers(),
                json={"requestId": "req_nonexistent", "chunkIndex": 1, "chunkData": "abc"},
            ) as r_unk:
                self.assertEqual(r_unk.status, 404)
                self.assertEqual((await r_unk.json())["error"], "UNKNOWN_IN_FLIGHT_JOB")
            self.assertNotIn("req_nonexistent", self.broker.chunk_buffers)

            # 2. Byte cap enforcement (413 PAYLOAD_TOO_LARGE) + idempotent retry + normal commit
            req_cap = "req_chunk_cap_retry"
            orig_cap = self.broker.MAX_CHUNK_BUFFER_BYTES
            self.broker.MAX_CHUNK_BUFFER_BYTES = 256
            try:
                dispatch_task = asyncio.create_task(
                    self.broker.dispatch_job(
                        tool="sharp_gui_inspect",
                        args={},
                        kind="read",
                        lease_ms=2000,
                        request_id=req_cap,
                    )
                )
                async with client.get(
                    f"{self.base_url}/v1/poll?timeoutMs=1000",
                    headers=self._auth_headers(),
                ) as poll_r:
                    self.assertEqual(poll_r.status, 200)
                    self.assertEqual((await poll_r.json())["requestId"], req_cap)

                envelope = json.dumps({"requestId": req_cap, "ok": True, "result": {"val": 42}})
                mid = len(envelope) // 2
                part1, part2 = envelope[:mid], envelope[mid:]

                # Send chunk 1
                async with client.post(
                    f"{self.base_url}/v1/result_chunk",
                    headers=self._auth_headers(),
                    json={"requestId": req_cap, "chunkIndex": 1, "chunkData": part1},
                ) as c1:
                    self.assertEqual(c1.status, 200)

                # Oversized chunk 2 exceeds 256-byte cap -> 413 PAYLOAD_TOO_LARGE
                async with client.post(
                    f"{self.base_url}/v1/result_chunk",
                    headers=self._auth_headers(),
                    json={"requestId": req_cap, "chunkIndex": 2, "chunkData": "X" * 300},
                ) as c_big:
                    self.assertEqual(c_big.status, 413)
                    self.assertEqual((await c_big.json())["error"], "PAYLOAD_TOO_LARGE")

                # Retrying chunk 1 replaces rather than duplicates
                async with client.post(
                    f"{self.base_url}/v1/result_chunk",
                    headers=self._auth_headers(),
                    json={"requestId": req_cap, "chunkIndex": 1, "chunkData": part1},
                ) as c1_retry:
                    self.assertEqual(c1_retry.status, 200)
                self.assertEqual(len(self.broker.chunk_buffers[req_cap]), 1)

                # Send valid chunk 2 and commit
                async with client.post(
                    f"{self.base_url}/v1/result_chunk",
                    headers=self._auth_headers(),
                    json={"requestId": req_cap, "chunkIndex": 2, "chunkData": part2},
                ) as c2:
                    self.assertEqual(c2.status, 200)

                async with client.post(
                    f"{self.base_url}/v1/result_commit",
                    headers=self._auth_headers(),
                    json={"requestId": req_cap},
                ) as cm:
                    self.assertEqual(cm.status, 200)

                res = await dispatch_task
                self.assertTrue(res["ok"])
                self.assertEqual(res["result"]["val"], 42)
                self.assertNotIn(req_cap, self.broker.chunk_buffers)
                self.assertNotIn(req_cap, self.broker._chunk_buffer_bytes)
            finally:
                self.broker.MAX_CHUNK_BUFFER_BYTES = orig_cap

            # 3. Lease expiration purges buffered chunks
            req_timeout = "req_chunk_timeout_purge"
            timeout_task = asyncio.create_task(
                self.broker.dispatch_job(
                    tool="sharp_gui_inspect",
                    args={},
                    kind="read",
                    lease_ms=180,
                    request_id=req_timeout,
                )
            )
            async with client.get(
                f"{self.base_url}/v1/poll?timeoutMs=1000",
                headers=self._auth_headers(),
            ) as poll_r:
                self.assertEqual(poll_r.status, 200)

            async with client.post(
                f"{self.base_url}/v1/result_chunk",
                headers=self._auth_headers(),
                json={"requestId": req_timeout, "chunkIndex": 1, "chunkData": '{"partial":true'},
            ) as c_part:
                self.assertEqual(c_part.status, 200)
            self.assertIn(req_timeout, self.broker.chunk_buffers)

            timeout_res = await timeout_task
            self.assertFalse(timeout_res["ok"])
            self.assertEqual(timeout_res["code"], "LEASE_EXPIRED")
            self.assertNotIn(req_timeout, self.broker.chunk_buffers)
            self.assertNotIn(req_timeout, self.broker._chunk_buffer_bytes)

            # 4. Mid-flight stale-target failure purges buffered chunks
            req_stale = "req_chunk_stale_purge"
            stale_task = asyncio.create_task(
                self.broker.dispatch_job(
                    tool="sharp_gui_inspect",
                    args={},
                    kind="read",
                    lease_ms=1500,
                    request_id=req_stale,
                    expected_place_id=555,
                    expected_session_nonce="sess_chunks",
                )
            )
            async with client.get(
                f"{self.base_url}/v1/poll?timeoutMs=1000",
                headers=self._auth_headers(),
            ) as poll_r:
                self.assertEqual(poll_r.status, 200)

            async with client.post(
                f"{self.base_url}/v1/result_chunk",
                headers=self._auth_headers(),
                json={"requestId": req_stale, "chunkIndex": 1, "chunkData": '{"partial":'},
            ) as c_stale:
                self.assertEqual(c_stale.status, 200)
            self.assertIn(req_stale, self.broker.chunk_buffers)

            # Authenticated session handoff triggers mid-flight STALE_TARGET_PLACE
            async with client.post(
                f"{self.base_url}/v1/hello",
                headers=self._auth_headers(),
                json={"studioSessionId": "sess_chunks_v2", "placeId": 555},
            ) as r_swap:
                self.assertEqual(r_swap.status, 200)

            stale_res = await stale_task
            self.assertFalse(stale_res["ok"])
            self.assertEqual(stale_res["code"], "STALE_TARGET_PLACE")
            self.assertNotIn(req_stale, self.broker.chunk_buffers)
            self.assertNotIn(req_stale, self.broker._chunk_buffer_bytes)


class TestCredentialsStoreSecurityFixes(unittest.IsolatedAsyncioTestCase):
    def test_s2_loopback_peer_and_host_validation_fail_closed(self) -> None:
        for bad_remote in (None, "", "   ", "203.0.113.7", "::ffff:203.0.113.7", "invalid-ip"):
            req = SimpleNamespace(transport=None, remote=bad_remote, headers={})
            self.assertFalse(_is_loopback_peer(req), f"Expected False for remote={bad_remote!r}")

        for ok_remote in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            req = SimpleNamespace(transport=None, remote=ok_remote, headers={})
            self.assertTrue(_is_loopback_peer(req), f"Expected True for remote={ok_remote!r}")

        for ok_host in ("127.0.0.1:43210", "localhost:43210", "[::1]:43210"):
            req = SimpleNamespace(transport=None, headers={"Host": ok_host})
            self.assertTrue(_is_valid_loopback_host(req, expected_port=43210))

        for bad_host in ("evil.example:43210", "127.0.0.1:9999", "127.0.0.1", "", "localhost.evil:43210"):
            req = SimpleNamespace(transport=None, headers={"Host": bad_host})
            self.assertFalse(_is_valid_loopback_host(req, expected_port=43210))

    def test_s3_write_store_uses_restrictive_os_open_0600_and_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_cred_s3_") as td:
            target = Path(td) / "credentials.json"
            real_open = os.open
            captured_calls: list[tuple[str, int, int]] = []

            def spy_open(path_arg: str, flags: int, mode: int = 0o777, *args, **kwargs) -> int:
                captured_calls.append((str(path_arg), int(flags), int(mode)))
                return real_open(path_arg, flags, mode, *args, **kwargs)

            with mock.patch("sharp_mcp.credentials_store.os.open", side_effect=spy_open):
                _write_store(target, {"schema": "sharp.credentials.v1", "providers": {"gemini": {"api_key": "secret"}}})

            self.assertEqual(len(captured_calls), 1)
            opened_path, opened_flags, opened_mode = captured_calls[0]
            self.assertTrue(opened_path.endswith(".tmp"))
            self.assertNotEqual(Path(opened_path).resolve(), target.resolve())
            self.assertEqual(opened_mode, 0o600)
            self.assertTrue(opened_flags & os.O_CREAT)
            self.assertTrue(opened_flags & os.O_EXCL)
            self.assertTrue(opened_flags & os.O_WRONLY)

            # Atomic replace completed and no temp file left behind
            self.assertTrue(target.is_file())
            self.assertEqual(list(Path(td).glob("*.tmp")), [])
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["providers"]["gemini"]["api_key"], "secret")

            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    async def test_s2_browser_prompt_host_origin_cookie_and_history_scrubbing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_browser_s2_") as td:
            cred_file = Path(td) / "creds.json"
            launched = await async_prompt_credentials_in_browser(
                timeout_sec=15.0,
                open_browser=False,
                wait_for_save=False,
                credentials_path=cred_file,
            )
            setup_url = launched["url"]
            port = launched["port"]
            base_url, query_str = setup_url.split("?", 1)
            token = query_str.split("=", 1)[1]
            root_url = base_url.rsplit("/", 1)[0]

            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as client:
                # 1. Spoofed Host rejected on /setup, /save, /cancel
                async with client.get(setup_url, headers={"Host": f"evil.example:{port}"}) as r:
                    self.assertEqual(r.status, 403)
                async with client.post(
                    f"{root_url}/save",
                    headers={"Host": f"evil.example:{port}"},
                    json={"token": token},
                ) as r:
                    self.assertEqual(r.status, 403)
                async with client.post(
                    f"{root_url}/cancel",
                    headers={"Host": f"evil.example:{port}"},
                    json={"token": token},
                ) as r:
                    self.assertEqual(r.status, 403)

                # 2. Cross-origin Origin header rejected on /save and /cancel
                async with client.post(
                    f"{root_url}/save",
                    headers={"Origin": "https://evil.example"},
                    json={"token": token},
                ) as r:
                    self.assertEqual(r.status, 403)
                async with client.post(
                    f"{root_url}/cancel",
                    headers={"Origin": "https://evil.example"},
                    json={"token": token},
                ) as r:
                    self.assertEqual(r.status, 403)

                # 3. GET /setup without token or cookie -> 403
                async with client.get(f"{root_url}/setup") as r:
                    self.assertEqual(r.status, 403)

                # 4. Initial GET /setup?token=... -> 200, Referrer-Policy, HttpOnly cookie, replaceState scrub
                async with client.get(setup_url) as r:
                    self.assertEqual(r.status, 200)
                    self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")
                    set_cookie = r.headers.get("Set-Cookie", "")
                    self.assertIn("sharp_setup_token=", set_cookie)
                    self.assertIn("HttpOnly", set_cookie)
                    self.assertIn("SameSite=Strict", set_cookie)
                    html_text = await r.text()
                    self.assertIn("window.history.replaceState", html_text)

                # 5. Reload GET /setup without ?token= succeeds via HttpOnly cookie
                async with client.get(f"{root_url}/setup") as r:
                    self.assertEqual(r.status, 200)

                # 6. POST /cancel works via HttpOnly cookie without token in URL or body
                async with client.post(f"{root_url}/cancel", json={}) as r:
                    self.assertEqual(r.status, 200)
                    self.assertTrue((await r.json())["cancelled"])

            await asyncio.sleep(0.05)
            self.assertFalse(get_credentials_status(cred_file)["providers"]["gemini"]["configured"])


class TestStudioPluginReliabilityAndSafetyFixes(unittest.TestCase):
    def _load_init_luau_and_rbxmx_root_source(self) -> tuple[str, str]:
        src_luau = (SERVER_ROOT / "studio_plugin" / "src" / "init.server.luau").read_text(encoding="utf-8")
        rbxmx_path = SERVER_ROOT / "studio_plugin" / "SharpBridgePlugin.rbxmx"
        root = ET.fromstring(rbxmx_path.read_text(encoding="utf-8"))
        root_script = root.find("./Item[@class='Script']")
        self.assertIsNotNone(root_script)
        assert root_script is not None
        rbxmx_src = root_script.find("./Properties/ProtectedString[@name='Source']").text or ""
        return src_luau, rbxmx_src

    def test_rbxmx_matches_init_server_luau_and_b2_b5_fixes_present(self) -> None:
        src_luau, rbxmx_src = self._load_init_luau_and_rbxmx_root_source()
        self.assertTrue(src_luau.lstrip().startswith("--!strict"))
        self.assertEqual(src_luau, rbxmx_src, "SharpBridgePlugin.rbxmx is out of sync with init.server.luau")

        # B2: sendResult inspects ok + resp.StatusCode, retries failed chunks up to 2 times, aborts commit
        self.assertIn("postBridgeJson", src_luau)
        self.assertIn("resp.StatusCode >= 200 and resp.StatusCode < 300", src_luau)
        self.assertIn("for attempt = 1, 3 do", src_luau)
        self.assertIn("allChunksOk = false", src_luau)
        self.assertIn("if not allChunksOk then\n\t\t\treturn\n\t\tend", src_luau)

        # B5: Mode B compiledLuau sets recStatus = "None" when kind == "read"
        self.assertIn('if kind == "read" then\n\t\t\t\t\trecStatus = "None"', src_luau)

    def test_s4_is_destructive_request_patterns_match_all_required_variants(self) -> None:
        src_luau, _ = self._load_init_luau_and_rbxmx_root_source()

        # Verify the Luau source defines all protected services and pattern checks
        for svc in ("Workspace", "StarterGui", "ReplicatedStorage", "ServerScriptService"):
            self.assertIn(f'"{svc}"', src_luau)
        self.assertIn("Terrain%s*:%s*Clear%s*%(", src_luau)
        self.assertIn("ClearAllChildren%s*%(", src_luau)
        self.assertIn("GetService%s*%(?", src_luau)

        # Mirror the exact Luau patterns from isDestructiveRequest() and verify behavior
        services = ("Workspace", "StarterGui", "ReplicatedStorage", "ServerScriptService")
        lua_patterns = [
            "Terrain%s*:%s*Clear%s*%(",
            "workspace%s*:%s*ClearAllChildren%s*%(",
        ]
        for svc in services:
            lua_patterns.append(svc + "%s*:%s*ClearAllChildren%s*%(")
            lua_patterns.append(":%s*GetService%s*%(?%s*[\"']" + svc + "[\"']%s*%)?%s*:%s*ClearAllChildren%s*%(")
        compiled_regexes = [re.compile(_lua_pattern_to_regex(p)) for p in lua_patterns]

        def matches_destructive(snippet: str) -> bool:
            return any(rx.search(snippet) is not None for rx in compiled_regexes)

        destructive_samples = [
            "workspace.Terrain:Clear()",
            "game.Workspace.Terrain : Clear ( )",
            "Workspace:ClearAllChildren()",
            "Workspace : ClearAllChildren ( )",
            "workspace:ClearAllChildren()",
            "workspace : ClearAllChildren()",
            'game:GetService("Workspace"):ClearAllChildren()',
            "game:GetService('Workspace') : ClearAllChildren ()",
            'game:GetService("StarterGui"):ClearAllChildren()',
            'game : GetService ( "ReplicatedStorage" ) : ClearAllChildren ( )',
            'game:GetService("ServerScriptService"):ClearAllChildren()',
            'game:GetService"Workspace":ClearAllChildren()',
            "StarterGui : ClearAllChildren()",
            "ReplicatedStorage:ClearAllChildren()",
            "ServerScriptService : ClearAllChildren()",
        ]
        for sample in destructive_samples:
            self.assertTrue(matches_destructive(sample), f"Expected destructive match for: {sample}")

        safe_samples = [
            'local folder = Instance.new("Folder"); folder:ClearAllChildren()',
            'local ws = game:GetService("Workspace"); return ws.Name',
            'local t = workspace.Terrain; t:FillBall(Vector3.zero, 4, Enum.Material.Grass)',
        ]
        for sample in safe_samples:
            self.assertFalse(matches_destructive(sample), f"Unexpected false positive for: {sample}")


if __name__ == "__main__":
    unittest.main()
