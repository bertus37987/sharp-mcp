"""Targeted unit tests for P0/P1 asset pipeline, project state, adaptive armor, deduplication, CI, and docs fixes."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import aiohttp

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sharp_mcp.bridge_broker import BridgeBroker  # noqa: E402
from sharp_mcp.domain_engines import multimodal_qa_engine, toolchain_engine  # noqa: E402
from sharp_mcp.domain_engines.attachment_engine import (  # noqa: E402
    ARMOR_SLOTS,
    BLOCKY_R15_REF_SIZES,
    SURFACE_ANCHOR_MODES,
    AttachmentEngine,
)
from sharp_mcp.domain_engines.upstream_multiplexer import (  # noqa: E402
    UpstreamMultiplexer,
    _luau_long_string,
)
from sharp_mcp.process_utils import detached_subprocess_kwargs  # noqa: E402
from sharp_mcp.project_library import (  # noqa: E402
    DEFAULT_LIBRARY_ROOT,
    ProjectLibraryManager,
    resolve_project_directory,
)


class _FakeHTTPResponse:
    def __init__(
        self,
        status: int,
        body: str,
        headers: Dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> _FakeHTTPResponse:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeClientSession:
    def __init__(
        self,
        *,
        post_result: Any = None,
        get_results: List[Any] | None = None,
    ) -> None:
        self._post_result = post_result
        self._get_results = list(get_results or [])
        self.get_calls = 0

    def post(self, url: str, **kwargs: Any) -> Any:
        if isinstance(self._post_result, BaseException):
            raise self._post_result
        return self._post_result

    def get(self, url: str, **kwargs: Any) -> Any:
        idx = min(self.get_calls, len(self._get_results) - 1)
        self.get_calls += 1
        item = self._get_results[idx]
        if isinstance(item, BaseException):
            raise item
        return item

    async def __aenter__(self) -> _FakeClientSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class TestUploadSidecarAndOpenCloudFixes(unittest.IsolatedAsyncioTestCase):
    async def test_sidecar_luau_uses_long_string_strips_package_link_and_normalizes_origin(self) -> None:
        broker = BridgeBroker(host="127.0.0.1", port=0)
        mux = UpstreamMultiplexer(broker)
        captured_luau: List[str] = []

        async def fake_call_upstream(tool_name: str, arguments: Dict[str, Any], timeout_sec: float = 25.0) -> Dict[str, Any]:
            if tool_name == "insert_asset":
                return {"ok": True, "decoded": {"inserted": True}}
            if tool_name == "execute_luau":
                captured_luau.append(str(arguments.get("code", "")))
                return {"ok": True, "decoded": "CONFIGURED:Workspace.Blade parts=2 colored=2"}
            return {"ok": True, "decoded": {}}

        with tempfile.TemporaryDirectory(prefix="sharp_b1_") as td:
            asset_file = Path(td) / "Blade.fbx"
            asset_file.write_bytes(b"FBX_DUMMY_DATA")
            sidecar_file = Path(td) / "Blade.sidecar.json"
            sidecar_payload = {
                "material_slots_split": [
                    {
                        "slot_index": 0,
                        "slot_name": 'Steel]]"==]Edge',
                        "srgb_color": [200, 205, 210],
                        "roblox_material": "Metal",
                        "bbox_center_blender": [0.15, -0.25, 0.8],
                    },
                    {
                        "slot_index": 1,
                        "slot_name": "LeatherGrip",
                        "srgb_color": [90, 55, 35],
                        "roblox_material": "Leather",
                        "bbox_center_blender": [0.0, 0.0, -0.4],
                    },
                ],
                "attachments": [
                    {
                        "name": "GripAttachment",
                        "cframe": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
                    }
                ],
            }
            sidecar_file.write_text(json.dumps(sidecar_payload), encoding="utf-8")

            with (
                patch(
                    "sharp_mcp.domain_engines.upstream_multiplexer.get_api_key",
                    return_value="test-key",
                ),
                patch.object(
                    mux,
                    "_upload_via_open_cloud_key",
                    new=AsyncMock(return_value={"ok": True, "upload_mode": "open_cloud_api_key", "asset_id": "123456"}),
                ),
                patch.object(mux, "call_upstream_studio_mcp", side_effect=fake_call_upstream),
            ):
                res = await mux.upload_and_insert_roblox_asset(
                    file_path=asset_file,
                    display_name="Blade",
                    creator_user_id="99999",
                    studio_id="studio-edit-1",
                    insert_into_studio=True,
                    sidecar_path=sidecar_file,
                )

        self.assertTrue(res["ok"], res)
        self.assertEqual(len(captured_luau), 1)
        luau = captured_luau[0]

        slots_json = json.dumps(sidecar_payload["material_slots_split"], ensure_ascii=False)
        atts_json = json.dumps(sidecar_payload["attachments"], ensure_ascii=False)
        self.assertIn(f"HttpService:JSONDecode({_luau_long_string(slots_json)})", luau)
        self.assertIn(f"HttpService:JSONDecode({_luau_long_string(atts_json)})", luau)
        self.assertNotIn("local _, bsz", luau)
        self.assertIn('d:IsA("PackageLink")', luau)
        self.assertIn("d:Destroy()", luau)
        self.assertIn('targetInst:GetAttribute("SharpNormalizedOrigin")', luau)
        self.assertIn('targetInst:SetAttribute("SharpNormalizedOrigin", true)', luau)
        self.assertIn("refPart.Position - Vector3.new(-bx, bz, by)", luau)
        self.assertIn("CFrame.new(origin) * CFrame.Angles(0, math.pi, 0) * CFrame.new(-origin) * part.CFrame", luau)

    async def test_open_cloud_upload_uses_to_thread_and_retries_transient_poll_errors(self) -> None:
        broker = BridgeBroker(host="127.0.0.1", port=0)
        mux = UpstreamMultiplexer(broker)
        fake_session = _FakeClientSession(
            post_result=_FakeHTTPResponse(200, json.dumps({"path": "operations/op-retry-1"})),
            get_results=[
                _FakeHTTPResponse(429, '{"message":"rate limited"}'),
                _FakeHTTPResponse(503, "Service Unavailable"),
                _FakeHTTPResponse(502, "Bad Gateway"),
                _FakeHTTPResponse(200, json.dumps({"done": True, "response": {"assetId": "777888"}})),
            ],
        )

        to_thread_funcs: List[Any] = []
        orig_to_thread = asyncio.to_thread

        async def spy_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            to_thread_funcs.append(func)
            return await orig_to_thread(func, *args, **kwargs)

        sleep_delays: List[float] = []

        async def fake_sleep(delay: float) -> None:
            sleep_delays.append(delay)

        with tempfile.TemporaryDirectory(prefix="sharp_b4_retry_") as td:
            asset_file = Path(td) / "Mesh.fbx"
            asset_file.write_bytes(b"MESH_BYTES")
            with (
                patch("sharp_mcp.domain_engines.upstream_multiplexer.asyncio.to_thread", side_effect=spy_to_thread),
                patch("sharp_mcp.domain_engines.upstream_multiplexer.asyncio.sleep", side_effect=fake_sleep),
                patch("sharp_mcp.domain_engines.upstream_multiplexer.aiohttp.ClientSession", return_value=fake_session),
            ):
                res = await mux._upload_via_open_cloud_key(
                    api_key="super-secret-oc-key-1234",
                    resolved_file=asset_file,
                    request_payload={"assetType": "Model"},
                    timeout_sec=30.0,
                )

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["asset_id"], "777888")
        self.assertEqual(fake_session.get_calls, 4)
        self.assertTrue(any(getattr(f, "__name__", "") == "read_bytes" for f in to_thread_funcs))
        # Bounded exponential backoff: initial 1.0, then 1.0 -> 2.0 -> 4.0
        self.assertEqual(sleep_delays, [1.0, 1.0, 2.0, 4.0])

    async def test_open_cloud_upload_catches_client_error_and_timeout_with_redaction(self) -> None:
        broker = BridgeBroker(host="127.0.0.1", port=0)
        mux = UpstreamMultiplexer(broker)
        secret = "rbx_oc_live_SECRET_TOKEN_98765"

        with tempfile.TemporaryDirectory(prefix="sharp_b4_err_") as td:
            asset_file = Path(td) / "Mesh.glb"
            asset_file.write_bytes(b"GLB_BYTES")

            for exc in (
                aiohttp.ClientConnectionError(f"Connection failed using key {secret}"),
                asyncio.TimeoutError(f"Timed out with {secret}"),
            ):
                fake_session = _FakeClientSession(post_result=exc)
                with patch(
                    "sharp_mcp.domain_engines.upstream_multiplexer.aiohttp.ClientSession",
                    return_value=fake_session,
                ):
                    res = await mux._upload_via_open_cloud_key(
                        api_key=secret,
                        resolved_file=asset_file,
                        request_payload={"assetType": "Model"},
                        timeout_sec=15.0,
                    )
                self.assertFalse(res["ok"])
                self.assertNotIn(secret, json.dumps(res))
                self.assertIn("[REDACTED]", res["error"])

    async def test_open_cloud_upload_bounds_persistent_504_retries(self) -> None:
        broker = BridgeBroker(host="127.0.0.1", port=0)
        mux = UpstreamMultiplexer(broker)
        fake_session = _FakeClientSession(
            post_result=_FakeHTTPResponse(200, json.dumps({"operationId": "op-504"})),
            get_results=[_FakeHTTPResponse(504, "Gateway Timeout")],
        )

        with tempfile.TemporaryDirectory(prefix="sharp_b4_504_") as td:
            asset_file = Path(td) / "Mesh.fbx"
            asset_file.write_bytes(b"BYTES")
            with (
                patch("sharp_mcp.domain_engines.upstream_multiplexer.asyncio.sleep", new=AsyncMock()),
                patch("sharp_mcp.domain_engines.upstream_multiplexer.aiohttp.ClientSession", return_value=fake_session),
            ):
                res = await mux._upload_via_open_cloud_key(
                    api_key="oc-secret-key",
                    resolved_file=asset_file,
                    request_payload={"assetType": "Model"},
                    timeout_sec=30.0,
                )
        self.assertFalse(res["ok"])
        self.assertEqual(res["status_code"], 504)
        self.assertEqual(fake_session.get_calls, 6)  # 5 retries + 1 terminal failure


class TestProjectLibraryUnifiedHomeAndLegacyFallback(unittest.TestCase):
    def test_default_resolution_uses_sharp_mcp_home_and_never_mutates_repo_seed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_b3_home_") as td:
            fake_home = Path(td) / "home"
            fake_cwd = Path(td) / "workspace"
            fake_home.mkdir()
            fake_cwd.mkdir()

            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("SHARP_PROJECT_DIR", "SHARP_HOME", "SHARP_ALLOW_IN_REPO_LIBRARY")
            }
            with (
                patch.dict(os.environ, clean_env, clear=True),
                patch("sharp_mcp.project_library.Path.home", return_value=fake_home),
            ):
                resolved = resolve_project_directory(project_id="default_game", cwd=fake_cwd)
                expected = (fake_home / ".sharp-mcp" / "game_library" / "default_game").resolve()
                self.assertEqual(resolved, expected)
                # Must not have created legacy ~/.sharp directory
                self.assertFalse((fake_home / ".sharp").exists())

                # Instantiating ProjectLibraryManager copies seed cleanly without touching repo
                mgr = ProjectLibraryManager(project_id="default_game")
                self.assertEqual(mgr.project_dir, expected)
                self.assertTrue((mgr.project_dir / "game_state.json").is_file())

                # Binding a place_id writes to ~/.sharp-mcp/game_library/place_bindings.json
                bind_res = mgr.bind_place_id(424242)
                self.assertTrue(bind_res["ok"])
                expected_bindings = (fake_home / ".sharp-mcp" / "game_library" / "place_bindings.json").resolve()
                self.assertEqual(Path(bind_res["bindings_file"]).resolve(), expected_bindings)
                self.assertEqual(
                    resolve_project_directory(place_id=424242, cwd=fake_cwd),
                    expected,
                )

    def test_legacy_place_bindings_read_only_fallback_and_opt_in_repo_flag(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_b3_legacy_") as td:
            fake_home = Path(td) / "home"
            fake_cwd = Path(td) / "workspace"
            legacy_target = (Path(td) / "legacy_bound_proj").resolve()
            fake_home.mkdir()
            fake_cwd.mkdir()
            legacy_target.mkdir()

            legacy_bfile = fake_home / ".sharp" / "game_library" / "place_bindings.json"
            legacy_bfile.parent.mkdir(parents=True, exist_ok=True)
            legacy_bfile.write_text(json.dumps({"777001": str(legacy_target)}), encoding="utf-8")

            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("SHARP_PROJECT_DIR", "SHARP_HOME", "SHARP_ALLOW_IN_REPO_LIBRARY")
            }
            with (
                patch.dict(os.environ, clean_env, clear=True),
                patch("sharp_mcp.project_library.Path.home", return_value=fake_home),
            ):
                bound = resolve_project_directory(place_id=777001, cwd=fake_cwd)
                self.assertEqual(bound, legacy_target)

            with (
                patch.dict(os.environ, {**clean_env, "SHARP_ALLOW_IN_REPO_LIBRARY": "1"}, clear=True),
                patch("sharp_mcp.project_library.Path.home", return_value=fake_home),
            ):
                repo_resolved = resolve_project_directory(project_id="default_game", cwd=fake_cwd)
                self.assertEqual(repo_resolved, (DEFAULT_LIBRARY_ROOT / "default_game").resolve())


class TestAdaptiveArmorAndProcessUtilsAndDocs(unittest.TestCase):
    def test_adaptive_armor_scaling_and_surface_anchors_in_compiled_luau(self) -> None:
        engine = AttachmentEngine(SERVER_ROOT / "sharp_mcp" / "bundled_skills")
        cat = engine.get_catalog()
        self.assertIn("blocky_r15_ref_sizes", cat)
        self.assertIn("surface_anchor_modes", cat)
        self.assertEqual(tuple(cat["surface_anchor_modes"]), SURFACE_ANCHOR_MODES)
        for anchor in ("head_top", "torso_back_top", "top_cap", "front_shin", "foot_sole", "center"):
            self.assertIn(anchor, SURFACE_ANCHOR_MODES)
        self.assertEqual(ARMOR_SLOTS["helmet"]["surface_anchor"], "head_top")
        self.assertEqual(ARMOR_SLOTS["cloak"]["surface_anchor"], "torso_back_top")
        self.assertEqual(ARMOR_SLOTS["left_pauldron"]["surface_anchor"], "top_cap")
        self.assertEqual(ARMOR_SLOTS["right_greave"]["surface_anchor"], "front_shin")
        self.assertEqual(ARMOR_SLOTS["left_boot"]["surface_anchor"], "foot_sole")
        self.assertEqual(ARMOR_SLOTS["chest"]["surface_anchor"], "center")
        self.assertIn("UpperTorso", BLOCKY_R15_REF_SIZES)

        luau_adaptive = engine.compile_attach_luau(
            mode="armor_set",
            item_path="Workspace.ArmorKit",
            adaptive_scale=True,
        )
        self.assertTrue(luau_adaptive.startswith("--!strict"))
        self.assertIn("local ADAPTIVE_SCALE = true", luau_adaptive)
        for token in (
            "computeAdaptiveScale",
            "applyAdaptiveScale",
            "SharpAppliedAdaptiveScale",
            "computeSurfaceAnchorFromSize",
            "computeItemSurfaceAnchorCFrame",
            "SharpSurface_",
            "head_top",
            "torso_back_top",
            "top_cap",
            "front_shin",
            "foot_sole",
            "surfaceAnchor",
            "refSize",
        ):
            self.assertIn(token, luau_adaptive)

        luau_legacy = engine.compile_attach_luau(
            mode="armor_set",
            item_path="Workspace.ArmorKit",
            adaptive_scale=False,
        )
        self.assertIn("local ADAPTIVE_SCALE = false", luau_legacy)

    def test_detached_subprocess_kwargs_deduplicated(self) -> None:
        kw = detached_subprocess_kwargs()
        self.assertEqual(kw.get("stdin"), subprocess.DEVNULL)
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            self.assertEqual(kw.get("creationflags"), subprocess.CREATE_NO_WINDOW)

        self.assertIs(toolchain_engine.detached_subprocess_kwargs, detached_subprocess_kwargs)
        self.assertIs(multimodal_qa_engine.detached_subprocess_kwargs, detached_subprocess_kwargs)
        self.assertFalse(hasattr(toolchain_engine, "_detached_subprocess_kwargs"))
        self.assertFalse(hasattr(multimodal_qa_engine, "_detached_subprocess_kwargs"))

    def test_readme_pyproject_and_ci_workflow(self) -> None:
        readme = (SERVER_ROOT / "README.md").read_text(encoding="utf-8")
        for doc_token in (
            "devin",
            "roblox_open_cloud",
            "ROBLOX_OPEN_CLOUD_API_KEY",
            "keys_prompt_browser",
            "upload_roblox_asset",
            "custom_bmesh",
            "inspect_attachment_fit",
            "LUAU-AIM-001",
            "WEAPON-PIVOT-001",
            "WEAPON-AMMO-001",
            "WEAPON-QUIVER-001",
            "WEAPON-GRIP-001",
            "ANIM-IK-001",
        ):
            self.assertIn(doc_token, readme, f"README.md missing documentation for {doc_token}")

        pyproject = tomllib.loads((SERVER_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("Programming Language :: Python :: 3.14", pyproject["project"]["classifiers"])

        ci_path = SERVER_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_path.is_file(), "Missing .github/workflows/ci.yml")
        ci_text = ci_path.read_text(encoding="utf-8")
        for ci_token in ("ubuntu-latest", "windows-latest", "3.11", "3.13", "ruff", "unittest"):
            self.assertIn(ci_token, ci_text)


if __name__ == "__main__":
    unittest.main()
