"""Comprehensive tests for Sharp v0.4.0 capabilities:
1. Outside-repo Gemini & OpenRouter credentials store + CLI `keys` subcommand
2. Multimodal Video, Audio Soundtest DSP & Anti-Slop Vision GUI QA Engine
3. ArtCreationEngine (procedural 2D SSAA kit, custom BitmapFont, 2D/3D VFX flipbooks, AI image gen)
4. 3D Map Building Overlap & Floating Check (Luau SAT + CriticalAuditEngine)
5. Concept Intake Questions, Micro-Step MVP Planning & Sub-Agent Delegation Briefs
6. Full MCP stdio E2E round-trip for v0.4 tools & prompts (non-destructive, zero real API calls)
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import wave

import numpy as np
from PIL import Image, ImageDraw
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sharp_mcp.credentials_store import (
    MODEL_PRESETS,
    clear_credentials,
    get_credentials_status,
    mask_api_key,
    resolve_provider_and_model,
    set_credentials,
)
from sharp_mcp.domain_engines.art_creation_engine import ArtCreationEngine
from sharp_mcp.domain_engines.attachment_engine import AttachmentEngine
from sharp_mcp.domain_engines.critical_audit_engine import CriticalAuditEngine
from sharp_mcp.domain_engines.design_engine import DesignEngine
from sharp_mcp.domain_engines.game_planner import GamePlanner, MICRO_MVP_REQUIRED_STEPS, MICRO_STEP_EXECUTION_ORDER
from sharp_mcp.domain_engines.gameplay_systems_engine import GameplaySystemsEngine
from sharp_mcp.domain_engines.gui_engine import GuiDomainEngine
from sharp_mcp.domain_engines.luau_audit_engine import LuauAuditSnapshotEngine
from sharp_mcp.domain_engines.multimodal_qa_engine import MultimodalQAEngine
from sharp_mcp.domain_engines.rig_anim_engine import RigAnimationEngine
from sharp_mcp.domain_engines.terrain_env_engine import TerrainEnvironmentEngine
from sharp_mcp.project_library import ProjectLibraryManager
from sharp_mcp.skill_router import resolve_default_archive_dir, resolve_default_skills_dir


def _luau_compiler() -> str | None:
    return os.environ.get("LUAU_COMPILE") or shutil.which("luau-compile")


class _FakeHttpResponse:
    def __init__(self, status: int, body_obj: dict | str) -> None:
        self.status = status
        self._text = json.dumps(body_obj) if isinstance(body_obj, dict) else str(body_obj)

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> "_FakeHttpResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _write_test_wav(path: Path, samples: np.ndarray, sample_rate: int = 22050) -> Path:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_i16 = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_i16.tobytes())
    return path


def _write_test_avi(path: Path, *, mode: str = "moving", num_frames: int = 10) -> Path:
    try:
        import cv2
    except ImportError:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise unittest.SkipTest("Video fixtures require OpenCV or ffmpeg") from None
        with tempfile.TemporaryDirectory(prefix="sharp_video_frames_") as td:
            for i in range(num_frames):
                frame = Image.new("RGB", (320, 180), (0, 0, 0) if mode == "black" else (40, 80, 120))
                if mode != "black":
                    x = 20 + i * 12 if mode == "moving" else 80
                    ImageDraw.Draw(frame).rectangle((x, 50, x + 48, 120), fill=(255, 220, 45))
                frame.save(Path(td) / f"{i:03d}.png")
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-framerate", "10", "-i", str(Path(td) / "%03d.png"), "-c:v", "mjpeg", str(path)],
                check=True, capture_output=True,
            )
        return path

    w, h = 320, 180
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open OpenCV VideoWriter for {path}")
    try:
        for i in range(num_frames):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            if mode == "moving":
                frame[:, :] = (32, 42, 68)
                cx = 30 + i * 24
                cv2.rectangle(frame, (cx, 50), (cx + 48, 120), (45, 220, 255), -1)
                cv2.circle(frame, (260, 45 + (i % 4) * 10), 18, (255, 130, 80), -1)
            elif mode == "black":
                pass  # near-black zero frames
            elif mode == "frozen":
                frame[:, :] = (40, 80, 120)
                cv2.rectangle(frame, (80, 40), (180, 140), (220, 220, 220), -1)
            writer.write(frame)
    finally:
        writer.release()
    return path


def _tiny_png_bytes(color: tuple[int, int, int, int] = (240, 90, 60, 255), size: tuple[int, int] = (128, 128)) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGBA", size, (255, 0, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((16, 16, size[0] - 17, size[1] - 17), radius=14, fill=color, outline=(255, 255, 255, 255), width=4)
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestCredentialsStoreAndCliKeys(unittest.TestCase):
    def test_set_status_clear_env_precedence_and_masking(self) -> None:
        fake_gemini = "AIzaTestMockGeminiKeyNotReal00001111"
        fake_or = "sk-or-v1-testmockopenrouterkeynotreal0000"
        with tempfile.TemporaryDirectory(prefix="sharp_creds_") as td:
            cred_file = Path(td) / "creds.json"
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "SHARP_CREDENTIALS_PATH")
            }
            clean_env["SHARP_CREDENTIALS_PATH"] = str(cred_file)

            with mock.patch.dict(os.environ, clean_env, clear=True):
                empty = get_credentials_status(cred_file)
                self.assertFalse(empty["providers"]["gemini"]["configured"])
                self.assertFalse(empty["providers"]["openrouter"]["configured"])

                res_set = set_credentials(
                    gemini_api_key=fake_gemini,
                    openrouter_api_key=fake_or,
                    model_preferences={"gui_code": "qwen/qwen-2.5-coder-32b-instruct"},
                    credentials_path=cred_file,
                )
                self.assertTrue(res_set["ok"])
                self.assertTrue(res_set["providers"]["gemini"]["configured"])
                self.assertTrue(res_set["providers"]["openrouter"]["configured"])
                self.assertEqual(res_set["providers"]["gemini"]["source"], "credentials_file")
                # Raw keys must NEVER appear in serialized status responses
                serialized = json.dumps(res_set)
                self.assertNotIn(fake_gemini, serialized)
                self.assertNotIn(fake_or, serialized)
                self.assertEqual(mask_api_key(fake_gemini), res_set["providers"]["gemini"]["masked_preview"])

                routed_vision = resolve_provider_and_model(role="vision", preferred_provider="auto", credentials_path=cred_file)
                self.assertEqual(routed_vision["provider"], "gemini")
                self.assertEqual(routed_vision["model"], MODEL_PRESETS["gemini"]["vision"]["default"])

                routed_code = resolve_provider_and_model(role="gui_code", preferred_provider="openrouter", credentials_path=cred_file)
                self.assertEqual(routed_code["provider"], "openrouter")
                self.assertEqual(routed_code["model"], "qwen/qwen-2.5-coder-32b-instruct")

                # Env variable takes precedence cleanly
                with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-override-1234"}, clear=False):
                    stat_env = get_credentials_status(cred_file)
                    self.assertEqual(stat_env["providers"]["openrouter"]["source"], "env")
                    self.assertEqual(stat_env["providers"]["openrouter"]["active_env_var"], "OPENROUTER_API_KEY")

                cleared = clear_credentials("gemini", credentials_path=cred_file)
                self.assertIn("gemini", cleared["cleared"])
                self.assertFalse(cleared["providers"]["gemini"]["configured"])
                self.assertTrue(cleared["providers"]["openrouter"]["configured"])

                # Subprocess CLI `keys set/status/models/clear --json`
                for args in (
                    ["keys", "set", "--provider", "gemini", "--api-key", fake_gemini, "--json"],
                    ["keys", "status", "--json"],
                    ["keys", "models", "--json"],
                    ["keys", "clear", "--provider", "all", "--json"],
                ):
                    proc = subprocess.run(
                        [sys.executable, "-B", "-m", "sharp_mcp.cli", *args],
                        cwd=str(SERVER_ROOT),
                        env={**clean_env, "PYTHONPATH": str(SERVER_ROOT)},
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    self.assertEqual(proc.returncode, 0, f"CLI failed {args}: {proc.stderr}")
                    self.assertNotIn(fake_gemini, proc.stdout)
                    parsed = json.loads(proc.stdout)
                    self.assertTrue(parsed.get("ok"))


class TestMultimodalQAEngine(unittest.IsolatedAsyncioTestCase):
    async def test_audio_dsp_video_contact_sheet_and_mocked_vision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_mediaqa_") as td:
            root = Path(td)
            cred_file = root / "creds.json"
            set_credentials(
                gemini_api_key="AIzaMockMediaQaTestKey00001111",
                openrouter_api_key="sk-or-v1-mockmediaqatestkey00001111",
                credentials_path=cred_file,
            )
            qa = MultimodalQAEngine(credentials_path=cred_file)

            # 1. Clean SFX wav vs clipping + DC offset vs silence
            t = np.linspace(0, 0.4, int(22050 * 0.4), endpoint=False)
            clean_wav = _write_test_wav(root / "clean.wav", 0.55 * np.sin(2.0 * math.pi * 440.0 * t))
            res_clean = await qa.inspect_audio(audio_path=str(clean_wav), provider="openrouter")
            self.assertTrue(res_clean["ok"])
            self.assertEqual(res_clean["findings"], [])
            self.assertGreater(res_clean["dsp_telemetry"]["rms_dbfs"], -20.0)

            clip_dc_wav = _write_test_wav(root / "bad_clip.wav", np.clip(0.35 + 1.25 * np.sin(2.0 * math.pi * 220.0 * t), -1.0, 1.0))
            res_bad = await qa.inspect_audio(audio_path=str(clip_dc_wav), provider="openrouter")
            bad_ids = {f["id"] for f in res_bad["findings"]}
            self.assertIn("AUDIO-CLIP-001", bad_ids)
            self.assertIn("AUDIO-DC-001", bad_ids)

            silent_wav = _write_test_wav(root / "silent.wav", np.zeros(4410, dtype=np.float32))
            res_sil = await qa.inspect_audio(audio_path=str(silent_wav), provider="openrouter")
            self.assertIn("AUDIO-SILENT-001", {f["id"] for f in res_sil["findings"]})

            # 2. Moving video + black/frozen videos -> contact sheets & telemetry + mocked OpenRouter vision
            moving_vid = _write_test_avi(root / "playtest_move.avi", mode="moving", num_frames=10)
            frozen_vid = _write_test_avi(root / "anim_frozen.avi", mode="frozen", num_frames=10)
            black_vid = _write_test_avi(root / "playtest_black.avi", mode="black", num_frames=8)

            fake_or_ok = _FakeHttpResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "verdict": "SHIP",
                                    "score": 91,
                                    "summary": "Clear moving character & HUD without asset overlap.",
                                    "findings": [],
                                })
                            }
                        }
                    ]
                },
            )
            with mock.patch("aiohttp.ClientSession.post", return_value=fake_or_ok):
                vid_res = await qa.inspect_video(
                    video_path=str(moving_vid),
                    focus="playtest",
                    output_dir=root / "qa_out",
                    provider="openrouter",
                    include_audio_dsp=False,
                )
            self.assertTrue(vid_res["ok"])
            self.assertTrue(Path(vid_res["contact_sheet_path"]).is_file())
            self.assertGreater(vid_res["video_telemetry"]["mean_motion_delta"], 1.0)
            self.assertTrue(vid_res["ai_analysis"]["ok"])
            self.assertEqual(vid_res["ai_analysis"]["parsed_json"]["verdict"], "SHIP")

            frozen_res = await qa.inspect_video(
                video_path=str(frozen_vid),
                focus="animation",
                output_dir=root / "qa_out",
                provider="openrouter",
                include_audio_dsp=False,
            )
            self.assertIn("VIDEO-FROZEN-001", {f["id"] for f in frozen_res["findings"]})

            black_res = await qa.inspect_video(
                video_path=str(black_vid),
                focus="playtest",
                output_dir=root / "qa_out",
                provider="openrouter",
                include_audio_dsp=False,
            )
            self.assertIn("VIDEO-BLACK-001", {f["id"] for f in black_res["findings"]})

            # 3. GUI Vision QA: blank image vs stylized UI image + mocked Gemini Vision
            blank_png = root / "blank.png"
            Image.new("RGB", (256, 144), (24, 24, 24)).save(blank_png)
            gui_png = root / "hud.png"
            Image.open(io.BytesIO(_tiny_png_bytes((255, 110, 40, 255), (256, 144)))).save(gui_png)

            fake_gem_ok = _FakeHttpResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps({
                                            "verdict": "SHIP",
                                            "score": 89,
                                            "slop_risk": "low",
                                            "summary": "Crisp anti-slop UI framing.",
                                            "findings": [],
                                            "praise": ["High contrast borders"],
                                        })
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
            with mock.patch("aiohttp.ClientSession.post", return_value=fake_gem_ok):
                vis_blank = await qa.inspect_gui_vision(image_path=str(blank_png), provider="gemini")
                self.assertIn("VIS-BLANK-001", {f["id"] for f in vis_blank["findings"]})

                vis_good = await qa.inspect_gui_vision(image_path=str(gui_png), before_image_path=str(blank_png), provider="gemini")
                self.assertTrue(vis_good["ok"])
                self.assertTrue(vis_good["ai_analysis"]["ok"])
                self.assertEqual(vis_good["ai_analysis"]["parsed_json"]["slop_risk"], "low")
                self.assertIsNotNone(vis_good["image_telemetry"]["visual_diff"])


class TestArtCreationEngine(unittest.IsolatedAsyncioTestCase):
    async def test_procedural_2d_kit_custom_font_vfx_and_ai_art(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_art_") as td:
            root = Path(td)
            skills_dir = resolve_default_skills_dir()
            archive_dir = resolve_default_archive_dir()
            design_eng = DesignEngine(skills_dir, archive_dir)
            gui_eng = GuiDomainEngine(skills_dir, archive_dir)
            cred_file = root / "creds.json"
            art = ArtCreationEngine(design_engine=design_eng, gui_engine=gui_eng, credentials_path=cred_file)

            ds = design_eng.generate_design_system(game_title="Crystal Clash", genre="Action RPG", mood="vibrant")

            # 1. Procedural 2D Anti-Slop Kit
            kit = art.create_procedural_2d_kit(design_system=ds, output_dir=str(root / "kit"))
            self.assertTrue(kit["ok"])
            self.assertTrue(Path(kit["button_9slice"]["path"]).is_file())
            self.assertTrue(Path(kit["panel_9slice"]["path"]).is_file())
            self.assertTrue(Path(kit["emblem_rays_path"]).is_file())
            self.assertTrue(Path(kit["icon_atlas"]["atlas_path"]).is_file())
            with Image.open(kit["icon_atlas"]["atlas_path"]) as atlas_im:
                self.assertLessEqual(max(atlas_im.size), 1024)
                self.assertEqual(atlas_im.mode, "RGBA")

            # 2. Custom Font Kit (Roblox Font Pairing + BitmapFont Sheet + Luau Module)
            fkit = art.create_custom_font_kit(design_system=ds, output_dir=str(root / "fonts"))
            self.assertTrue(fkit["ok"])
            self.assertIn("rbxasset://fonts/families/", fkit["roblox_font_pairing"]["display_font"]["uri"])
            self.assertTrue(Path(fkit["bitmap_font"]["atlas_path"]).is_file())
            self.assertTrue(Path(fkit["bitmap_font"]["metrics_path"]).is_file())
            luau_font = Path(fkit["luau_module_path"]).read_text(encoding="utf-8")
            self.assertTrue(luau_font.startswith("--!strict"))

            # 3. 2D UI & 3D World VFX 4x4 Flipbooks + Strict Luau VFX Controllers
            vfx = art.create_custom_vfx(design_system=ds, vfx_mode="both", output_dir=str(root / "vfx"))
            self.assertTrue(vfx["ok"])
            self.assertTrue(Path(vfx["ui_2d_vfx"]["flipbook"]["path"]).is_file())
            self.assertTrue(Path(vfx["world_3d_vfx"]["flipbook"]["path"]).is_file())
            self.assertTrue(Path(vfx["ui_2d_vfx"]["luau_module_path"]).read_text(encoding="utf-8").startswith("--!strict"))
            self.assertTrue(Path(vfx["world_3d_vfx"]["luau_module_path"]).read_text(encoding="utf-8").startswith("--!strict"))

            # 4. AI UI Concept (offline deterministic lint >= 80) + Mocked AI Image Gen w/ auto-slice
            concept = await art.generate_ui_concept(design_system=ds, screen_name="CombatHud", use_ai=False)
            self.assertTrue(concept["ok"])
            self.assertGreaterEqual(concept["design_lint"]["score"], 80)
            self.assertEqual(concept["generation_mode"], "offline_deterministic_blueprint")

            missing_img = await art.generate_ai_art(design_system=ds, asset_kind="panel_9slice", output_dir=str(root / "ai_miss"))
            self.assertFalse(missing_img["ok"])
            self.assertEqual(missing_img["error_code"], "MISSING_API_KEY")
            self.assertTrue(bool(missing_img["prompt_ready"]))

            set_credentials(gemini_api_key="AIzaMockArtImageKey00001111", credentials_path=cred_file)
            b64_png = base64.b64encode(_tiny_png_bytes((220, 70, 55, 255), (256, 256))).decode("ascii")
            fake_img_resp = _FakeHttpResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"inlineData": {"mimeType": "image/png", "data": b64_png}}
                                ]
                            }
                        }
                    ]
                },
            )
            with mock.patch("aiohttp.ClientSession.post", return_value=fake_img_resp):
                gen_res = await art.generate_ai_art(
                    design_system=ds,
                    asset_kind="panel_9slice",
                    provider="gemini",
                    auto_slice=True,
                    output_dir=str(root / "ai_ok"),
                )
            self.assertTrue(gen_res["ok"])
            self.assertTrue(Path(gen_res["raw_image_path"]).is_file())
            self.assertIsNotNone(gen_res["sliced_result"])
            self.assertTrue(gen_res["sliced_result"]["ok"])


class TestMapOverlapAndMicroPlanner(unittest.TestCase):
    def test_overlap_audit_luau_and_critical_audit_box_detection(self) -> None:
        eng = GameplaySystemsEngine(resolve_default_skills_dir(), resolve_default_archive_dir())
        audit_luau = eng.compile_world_assembly_optimize_luau(action="audit_overlaps", tolerance_studs=0.2)
        self.assertTrue(audit_luau.startswith("--!strict"))
        self.assertIn("overlapCount", audit_luau)
        self.assertIn("GetBoundingBox", audit_luau)
        for fragment in (
            "Workspace:Raycast", "RaycastParams.new()", "Enum.RaycastFilterType.Exclude",
            "params.FilterDescendantsInstances = { asset.inst }", "_verticalRadius(asset)",
            "math.abs(cf.RightVector.Y)", "math.abs(cf.UpVector.Y)", "math.abs(cf.LookVector.Y)",
            "SharpAllowFloating", "not _isAnchored(asset.inst)", "floatingCount = #floating",
            "gapStuds = gap", "hit.Instance:GetFullName()", "#overlaps == 0 and #floating == 0",
        ):
            self.assertIn(fragment, audit_luau)

        fix_luau = eng.compile_world_assembly_optimize_luau(action="fix_overlaps", tolerance_studs=0.2)
        self.assertIn("PivotTo", fix_luau)
        self.assertIn("SharpWorldAssembly", fix_luau)
        for fragment in (
            "for iteration = 1, MAX_ITERATIONS do", "SharpLocked", "volumeA < volumeB",
            "moved[target.inst]", "moved[entry._asset.inst]", "if target == B then axis else -axis",
            "math.abs(away.Y) > 0.9", "top - bottom", "_translateAsset(entry._asset",
            "result.remainingOverlapCount = result.overlapCount",
            "result.remainingFloatingCount = result.floatingCount", "result.grounded = grounded",
        ):
            self.assertIn(fragment, fix_luau)

        ca = CriticalAuditEngine()
        bad_world = ca.audit_static(
            luau_sources={"ServerScriptService/Main.server.luau": "--!strict\nprint('ok')\n"},
            world_stats={
                "placements": [
                    {"name": "TavernWallA", "center": [0, 5, 0], "size": [10, 10, 4]},
                    {"name": "TavernPillarB", "center": [3, 5, 0], "size": [6, 10, 4]},
                ],
                "floating_count": 2,
            },
        )
        ids = {f["id"] for f in bad_world["findings"]}
        self.assertIn("WORLD-OVERLAP-001", ids)
        self.assertIn("WORLD-FLOAT-001", ids)

        clean_world = ca.audit_static(
            luau_sources={"ServerScriptService/Main.server.luau": "--!strict\nprint('ok')\n"},
            world_stats={
                "placements": [
                    {"name": "HouseA", "center": [0, 5, 0], "size": [10, 10, 10]},
                    {"name": "HouseB", "center": [20, 5, 0], "size": [10, 10, 10]},
                ],
                "floating_count": 0,
                "overlap_count": 0,
            },
        )
        clean_ids = {f["id"] for f in clean_world["findings"]}
        self.assertNotIn("WORLD-OVERLAP-001", clean_ids)
        self.assertNotIn("WORLD-FLOAT-001", clean_ids)

    def test_world_audit_camel_case_counts(self) -> None:
        for count in (0, 1):
            with self.subTest(count=count):
                result = CriticalAuditEngine().audit_static(world_stats={"overlapCount": count, "floatingCount": count})
                ids = {f["id"] for f in result["findings"]}
                for rule in ("WORLD-OVERLAP-001", "WORLD-FLOAT-001"):
                    self.assertEqual(rule in ids, count > 0)

    def test_world_repair_parameter_bounds(self) -> None:
        eng = GameplaySystemsEngine(resolve_default_skills_dir(), resolve_default_archive_dir())
        for tolerance, iterations, expected_tolerance, expected_iterations in (
            (0.5, 8, 0.5, 8), (-2.0, 0, 0.0, 1), (1000.0, 100, 512.0, 64),
        ):
            with self.subTest(tolerance=tolerance, iterations=iterations):
                luau = eng.compile_world_assembly_optimize_luau(float_tolerance_studs=tolerance, max_iterations=iterations)
                self.assertIn(f"local FLOAT_TOLERANCE = {expected_tolerance}", luau)
                self.assertIn(f"local MAX_ITERATIONS = {expected_iterations}", luau)
        for tolerance in (math.nan, math.inf, -math.inf):
            with self.subTest(tolerance=tolerance), self.assertRaisesRegex(ValueError, "must be finite"):
                eng.compile_world_assembly_optimize_luau(float_tolerance_studs=tolerance)
        for iterations in (math.nan, math.inf):
            with self.subTest(iterations=iterations), self.assertRaises((ValueError, OverflowError)):
                eng.compile_world_assembly_optimize_luau(max_iterations=iterations)

    def test_world_assembly_actions_compile(self) -> None:
        compiler = _luau_compiler()
        if not compiler:
            self.skipTest("luau-compile is not installed (set LUAU_COMPILE or add it to PATH)")
        eng = GameplaySystemsEngine(resolve_default_skills_dir(), resolve_default_archive_dir())
        with tempfile.TemporaryDirectory(prefix="sharp_world_compile_") as td:
            for action in ("install", "scatter_and_optimize", "audit_overlaps", "fix_overlaps", "smoke_test", "cleanup"):
                with self.subTest(action=action):
                    source = Path(td) / f"{action}.luau"
                    source.write_text(eng.compile_world_assembly_optimize_luau(action=action), encoding="utf-8")
                    result = subprocess.run([compiler, "--null", str(source)], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, f"{action}:\n{result.stdout}\n{result.stderr}")

    def test_plugin_skills_and_generated_luau_compile(self) -> None:
        compiler = _luau_compiler()
        if not compiler:
            self.skipTest("luau-compile is not installed (set LUAU_COMPILE or add it to PATH)")
        skills = SERVER_ROOT / "sharp_mcp" / "bundled_skills"
        sources = {str(p.relative_to(SERVER_ROOT)): p.read_text(encoding="utf-8") for p in (
            *sorted((SERVER_ROOT / "studio_plugin" / "src").glob("*.luau")), *sorted(skills.rglob("*.luau")),
        )}
        with tempfile.TemporaryDirectory(prefix="sharp_corpus_compile_") as td:
            root = Path(td)
            gameplay = GameplaySystemsEngine(skills)
            for name in ("combat_and_controller", "audio_vfx_cutscene", "data_economy_monetization", "ai_and_gameplay", "playtest_scenario"):
                sources[name] = getattr(gameplay, f"compile_{name}_luau")()
            audit = LuauAuditSnapshotEngine(skills)
            sources["scaffold"] = audit.compile_scaffold_luau()
            sources["inventory"] = audit.compile_script_inventory_luau()
            sources["critical"] = CriticalAuditEngine(luau_audit_engine=audit).compile_live_audit_luau()
            sources["snapshot"] = audit.compile_snapshot_and_undo_luau()
            sources["audit"] = audit.compile_audit_all_luau()
            sources["gui"] = GuiDomainEngine(skills).compile_gui_build_luau()
            terrain = TerrainEnvironmentEngine(skills)
            sources["terrain"] = terrain.compile_terrain_build_luau([0, 0, 0], [64, 64, 64])
            sources["environment"] = terrain.compile_environment_apply_luau()
            sources["attach"] = AttachmentEngine(skills).compile_attach_luau()
            sources["verify"] = AttachmentEngine(skills).compile_verify_luau()
            rig = RigAnimationEngine(skills)
            sources["probe"] = rig.compile_probe_rig_luau()
            sources["playback"] = rig.compile_playback_test_luau()
            for anim_format in ("KeyframeSequence", "CurveAnimation"):
                sources[anim_format] = rig.compile_animation_from_clips_luau(
                    {"clips": {"Walk": rig.generate_procedural_preset("walk")}}, anim_format=anim_format,
                )
            design = DesignEngine()
            ds = design.generate_design_system("Corpus")
            for module_mode in (True, False):
                sources[f"theme_{module_mode}"] = design.compile_theme_luau(ds, module_mode=module_mode)
            art = ArtCreationEngine(design_engine=design, gui_engine=GuiDomainEngine(skills))
            sources["bitmap_font"] = art.create_custom_font_kit(output_dir=str(root / "art"))["luau_source"]
            vfx = art.create_custom_vfx(output_dir=str(root / "art"))
            for key in ("ui_2d_vfx", "world_3d_vfx"):
                sources[key] = vfx[key]["luau_source"]
            library = ProjectLibraryManager(project_dir=root / "project", project_id="corpus")
            sources["registry_empty"] = library.luau_registry_path.read_text(encoding="utf-8")
            sources["registry_populated"] = library._build_luau_registry_source(
                {"systems": {"combat": {}}}, {"assets": {"weapon": {"name": "Épée"}}},
            )
            sources["library_sync"] = library.compile_studio_sync_luau()
            for name, source in list(sources.items()):
                embedded = [match[1] for match in re.findall(r"\[(=*)\[(.*?)\]\1\]", source, re.S) if "--!strict" in match[1]]
                embedded += [json.loads(match) for match in re.findall(r'\.Source\s*=\s*("(?:\\.|[^"\\])*")', source)]
                for index, snippet in enumerate(embedded):
                    sources[f"{name}/embedded_{index}"] = snippet
            for index, (name, source) in enumerate(sources.items()):
                with self.subTest(source=name):
                    path = root / f"{index}.luau"
                    path.write_text(source, encoding="utf-8")
                    result = subprocess.run([compiler, "--null", str(path)], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, f"{name}:\n{result.stdout}\n{result.stderr}")

    def test_intake_questions_micro_step_progression_and_subagent_brief(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_micro_plan_") as td:
            lib = ProjectLibraryManager(project_dir=Path(td), project_id="micro_rpg")
            ca = CriticalAuditEngine(luau_audit_engine=LuauAuditSnapshotEngine(resolve_default_skills_dir(), resolve_default_archive_dir()), project_library=lib)
            gp = GamePlanner(project_library=lib, audit_engine=ca)

            intake = gp.dispatch_action("intake_questions", title="Blade Trial", genre="Action RPG")
            self.assertTrue(intake["ok"])
            self.assertGreaterEqual(len(intake["questions"]), 5)

            created = gp.dispatch_action("create", title="Blade Trial", genre="Action RPG", granularity="micro")
            self.assertTrue(created["ok"])
            self.assertEqual(created["plan"]["granularity"], "micro")
            self.assertEqual(list(created["plan"]["step_execution_order"]), list(MICRO_STEP_EXECUTION_ORDER))
            self.assertEqual(list(created["plan"]["mvp_required_steps"]), list(MICRO_MVP_REQUIRED_STEPS))

            art_brief = gp.dispatch_action("subagent_brief", role_focus="art_creation")
            self.assertTrue(art_brief["ok"])
            self.assertIn("roblox-gui", art_brief["skills_to_load"])

            # Next step should start at S0.1 with a subagent_brief
            nxt0 = gp.dispatch_action("next_step")
            self.assertEqual(nxt0["step_id"], "S0.1")
            self.assertIn("subagent_brief", nxt0)
            self.assertTrue(bool(nxt0["subagent_brief"]["subagent_role"]))

            clean_luau = {"ServerScriptService/Boot.server.luau": "--!strict\nlocal ok = true\n"}
            ds = DesignEngine(resolve_default_skills_dir(), resolve_default_archive_dir()).generate_design_system(
                game_title="Blade Trial", genre="Action RPG"
            )
            good_gui = {
                "ScreenGuis": [
                    {
                        "Name": "MainHudGui",
                        "ResetOnSpawn": False,
                        "ScreenInsets": "CoreUISafeInsets",
                        "Descendants": [
                            {"Name": "AttackBtn", "ClassName": "TextButton", "AbsoluteSize": [96, 56], "Clipped": False}
                        ],
                    }
                ]
            }
            good_clip = {
                "clip_name": "Attack1",
                "rig_type": "R15",
                "duration": 0.45,
                "keyframes": [
                    {"time": 0.0, "poses": {"UpperTorso": {"rot": [0, 0, 0]}, "RightUpperArm": {"rot": [0, 0, -25]}}},
                    {"time": 0.2, "poses": {"UpperTorso": {"rot": [0, 22, 0]}, "RightUpperArm": {"rot": [40, 0, -65]}}},
                    {"time": 0.45, "poses": {"UpperTorso": {"rot": [0, 0, 0]}, "RightUpperArm": {"rot": [0, 0, -25]}}},
                ],
            }

            # S2.2 cannot run before S2.1
            self.assertEqual(gp.complete_step("S2.2")["error_code"], "STAGE_ORDER_LOCKED")
            # S3.1 locked until S0.1..S4.1 complete
            self.assertEqual(gp.complete_step("S3.1")["error_code"], "MVP_LOCKED")

            # Advance S0.1 -> S1.1 -> S2.1 (attack only!) -> S2.2 (block only!) -> S2.3 -> S4.1
            s0 = gp.complete_step("S0.1", {"luau_sources": clean_luau, "snapshot_taken": True})
            self.assertTrue(s0["ok"], f"S0.1 failed: {s0}")
            s1 = gp.complete_step(
                "S1.1",
                {
                    "luau_sources": clean_luau,
                    "world_stats": {
                        "spawn_location_count": 1,
                        "part_count": 24,
                        "streaming_enabled": True,
                        "overlap_count": 0,
                    },
                    "snapshot_taken": True,
                },
            )
            self.assertTrue(s1["ok"], f"S1.1 failed: {s1}")
            s21 = gp.complete_step("S2.1", {"luau_sources": clean_luau, "anim_clips": [good_clip], "snapshot_taken": True})
            self.assertTrue(s21["ok"], f"S2.1 failed: {s21}")
            self.assertEqual(s21["next_step_id"], "S2.2")
            s22 = gp.complete_step("S2.2", {"luau_sources": clean_luau, "anim_clips": [good_clip], "snapshot_taken": True})
            self.assertTrue(s22["ok"], f"S2.2 failed: {s22}")
            s23 = gp.complete_step(
                "S2.3",
                {
                    "luau_sources": clean_luau,
                    "playtest_report": {
                        "ok": True,
                        "passed": True,
                        "scenario": "full_slice_bot",
                        "checks": ["spawn_valid", "hit_dummy", "vfx_sfx_ok"],
                    },
                    "snapshot_taken": True,
                },
            )
            self.assertTrue(s23["ok"], f"S2.3 failed: {s23}")
            self.assertFalse(s23["mvp_unlocked"])

            s41 = gp.complete_step("S4.1", {"luau_sources": clean_luau, "gui_spec": good_gui, "design_system": ds, "snapshot_taken": True})
            self.assertTrue(s41["ok"], f"S4.1 failed: {s41}")
            self.assertTrue(s41["mvp_unlocked"])
            self.assertEqual(s41["next_step_id"], "S3.1")


class TestV04StdioE2E(unittest.IsolatedAsyncioTestCase):
    async def test_v04_tools_and_prompts_over_stdio(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_v04_e2e_") as td:
            root = Path(td)
            cred_file = root / "creds.json"
            clean_wav = _write_test_wav(root / "sfx.wav", 0.5 * np.sin(2.0 * math.pi * 520.0 * np.linspace(0, 0.25, 5512)))
            env = {
                **os.environ,
                "PYTHONPATH": str(SERVER_ROOT),
                "SHARP_PROJECT_DIR": str(root / "proj"),
                "SHARP_CREDENTIALS_PATH": str(cred_file),
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "OPENROUTER_API_KEY": "",
            }
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "sharp_mcp.cli", "serve", "--no-bridge-listener", "--profile", "full"],
                env=env,
                cwd=str(SERVER_ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # 1. Verify sharp_concept_intake_workflow prompt exists and renders
                    p_res = await session.get_prompt("sharp_concept_intake_workflow", {"game_idea": "Slime Arena", "genre": "Action"})
                    self.assertIn("intake_questions", p_res.messages[0].content.text)

                    # 2. sharp_ai_studio keys_status + model_presets + offline generate_ui_concept
                    ai_stat = json.loads((await session.call_tool("sharp_ai_studio", {"action": "keys_status"})).content[0].text)
                    self.assertTrue(ai_stat["ok"])
                    ui_con = json.loads((await session.call_tool("sharp_ai_studio", {"action": "generate_ui_concept", "screen_name": "ShopHud", "use_ai": False})).content[0].text)
                    self.assertTrue(ui_con["ok"])
                    self.assertGreaterEqual(ui_con["design_lint"]["score"], 80)

                    # 3. sharp_art_studio procedural 2D kit, custom font kit, 2D/3D VFX
                    kit = json.loads((await session.call_tool("sharp_art_studio", {"action": "create_2d_kit", "game_title": "Slime Arena"})).content[0].text)
                    self.assertTrue(kit["ok"])
                    self.assertTrue(Path(kit["button_9slice"]["path"]).is_file())

                    fnt = json.loads((await session.call_tool("sharp_art_studio", {"action": "create_font_kit", "game_title": "Slime Arena"})).content[0].text)
                    self.assertTrue(fnt["ok"])
                    self.assertTrue(Path(fnt["bitmap_font"]["atlas_path"]).is_file())

                    vfx = json.loads((await session.call_tool("sharp_art_studio", {"action": "create_vfx", "game_title": "Slime Arena"})).content[0].text)
                    self.assertTrue(vfx["ok"])
                    self.assertTrue(Path(vfx["ui_2d_vfx"]["flipbook"]["path"]).is_file())

                    # 4. sharp_media_qa audio + GUI vision (local telemetry path)
                    aud = json.loads((await session.call_tool("sharp_media_qa", {"action": "inspect_audio", "audio_path": str(clean_wav)})).content[0].text)
                    self.assertTrue(aud["ok"])
                    self.assertEqual(aud["findings"], [])

                    # 5. sharp_world_assembly_and_optimization(action='audit_overlaps') offline + readOnly
                    ov = json.loads((await session.call_tool("sharp_world_assembly_and_optimization", {"action": "audit_overlaps", "float_tolerance_studs": 0.75, "max_iterations": 3, "execute_in_studio": True})).content[0].text)
                    self.assertTrue(ov["ok"])
                    self.assertEqual(ov["executionMode"], "Compiled_Luau_Ready")
                    self.assertIn("local FLOAT_TOLERANCE = 0.75", ov["compiledLuau"])
                    self.assertIn("local MAX_ITERATIONS = 3", ov["compiledLuau"])

                    # 6. sharp_game_plan intake_questions & granularity='micro'
                    iq = json.loads((await session.call_tool("sharp_game_plan", {"action": "intake_questions", "title": "Slime Arena", "genre": "Action"})).content[0].text)
                    self.assertTrue(iq["ok"])
                    self.assertGreaterEqual(len(iq["questions"]), 5)

                    mp = json.loads((await session.call_tool("sharp_game_plan", {"action": "create", "title": "Slime Arena", "granularity": "micro"})).content[0].text)
                    self.assertTrue(mp["ok"])
                    self.assertEqual(mp["plan_summary"]["granularity"], "micro")
                    self.assertEqual(mp["plan_summary"]["step_count"], len(MICRO_STEP_EXECUTION_ORDER))


if __name__ == "__main__":
    unittest.main()
