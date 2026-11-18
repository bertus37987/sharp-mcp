"""Isolated tests for AttachmentEngine, RigAnimationEngine quality/presets, Blender asset attach & skills."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sharp_mcp.domain_engines.attachment_engine import (  # noqa: E402
    SOCKET_PRESETS,
    AttachmentEngine,
)
from sharp_mcp.blender_installer import detect_blender_installation  # noqa: E402
from sharp_mcp.domain_engines.blender_engine import BlenderDomainEngine  # noqa: E402
from sharp_mcp.domain_engines.rig_anim_engine import (  # noqa: E402
    ANIMATION_STYLE_PROFILES,
    PROCEDURAL_PRESET_CATALOG,
    RigAnimationEngine,
)


BUNDLED_SKILLS_DIR = SERVER_ROOT / "sharp_mcp" / "bundled_skills"
LIVE_SKILLS_DIR = Path.home() / ".gemini" / "config" / "skills"
DESKTOP_ANIM_SKILL = SERVER_ROOT.parent / "01_roblox_animation" / "skill"


def _tokenize_luau_code(src: str) -> List[Tuple[str, str]]:
    """Strip Luau comments & string literals cleanly and return non-whitespace code tokens."""
    tokens: List[Tuple[str, str]] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        # Skip whitespace
        if ch.isspace():
            i += 1
            continue

        # Comments: --[=*[ ... ]=*] or -- ... \n
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                eqs = m.group(1)
                close_tag = "]" + eqs + "]"
                end_idx = src.find(close_tag, i + len(m.group(0)))
                i = n if end_idx == -1 else end_idx + len(close_tag)
            else:
                nl = src.find("\n", i)
                i = n if nl == -1 else nl + 1
            continue

        # Long bracket string: [=*[ ... ]=*]
        if ch == "[":
            m = re.match(r"\[(=*)\[", src[i:])
            if m:
                eqs = m.group(1)
                close_tag = "]" + eqs + "]"
                end_idx = src.find(close_tag, i + len(m.group(0)))
                if end_idx == -1:
                    raise AssertionError("Unterminated Luau long string literal")
                tokens.append(("STRING", "str"))
                i = end_idx + len(close_tag)
                continue

        # Quoted string literal
        if ch in ('"', "'", "`"):
            quote = ch
            i += 1
            closed = False
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    closed = True
                    i += 1
                    break
                i += 1
            if not closed:
                raise AssertionError(f"Unterminated Luau {quote} string literal")
            tokens.append(("STRING", "str"))
            continue

        # Punctuation & multi-char operators
        matched = False
        for sym in ("...", "..=", "..", "::", "->", "+=", "-=", "*=", "/=", "//=", "%=", "^=", "==", "~=", "<=", ">="):
            if src.startswith(sym, i):
                tokens.append(("OP", sym))
                i += len(sym)
                matched = True
                break
        if matched:
            continue

        if ch in "(){}[].,:;+-*/%^#<>=~":
            tokens.append(("PUNCT", ch))
            i += 1
            continue

        # Identifier / keyword / number
        m_id = re.match(r"[A-Za-z_][A-Za-z0-9_]*", src[i:])
        if m_id:
            word = m_id.group(0)
            tokens.append(("WORD", word))
            i += len(word)
            continue

        m_num = re.match(r"0[xXbB][0-9A-Fa-f_]+|[0-9][0-9_]*(\.[0-9_]+)?([eE][+-]?[0-9_]+)?", src[i:])
        if m_num:
            tokens.append(("NUM", m_num.group(0)))
            i += len(m_num.group(0))
            continue

        i += 1
    return tokens


def assert_valid_luau_sanity(src: str, label: str = "luau") -> None:
    """Verify balanced (), {}, [], block/end structure, and absence of deprecated LoadAnimation."""
    assert "Humanoid:LoadAnimation" not in src, f"{label}: uses deprecated Humanoid:LoadAnimation"
    assert "AnimationController:LoadAnimation" not in src, f"{label}: uses deprecated AnimationController:LoadAnimation"

    tokens = _tokenize_luau_code(src)
    delim_stack: List[str] = []
    block_stack: List[str] = []
    delim_pairs = {"(": ")", "{": "}", "[": "]"}
    close_to_open = {")": "(", "}": "{", "]": "["}
    expr_prev_ops = {
        "=", "return", "local", "(", "{", "[", ",", "+", "-", "*", "/", "//", "%", "^",
        "..", "==", "~=", "<", ">", "<=", ">=", "and", "or", "not", "?", ":",
    }

    idx = 0
    while idx < len(tokens):
        kind, val = tokens[idx]
        if val in delim_pairs:
            delim_stack.append(val)
        elif val in close_to_open:
            assert delim_stack and delim_stack[-1] == close_to_open[val], (
                f"{label}: unmatched delimiter '{val}' (stack={delim_stack[-5:]})"
            )
            delim_stack.pop()
        elif kind == "WORD":
            prev_val = tokens[idx - 1][1] if idx > 0 else ""
            prev_kind = tokens[idx - 1][0] if idx > 0 else ""
            # Ignore table field access or method call after `.` or `:` (e.g., anim.end, obj:function)
            if prev_val in (".", ":"):
                idx += 1
                continue

            if val == "function":
                block_stack.append("function")
            elif val in ("for", "while"):
                block_stack.append(val)
            elif val == "repeat":
                block_stack.append("repeat")
            elif val == "do":
                # Only standalone `do` opens a new block; `for ... do` and `while ... do` already opened one
                if not block_stack or block_stack[-1] not in ("for", "while"):
                    block_stack.append("do")
                else:
                    # Mark loop header closed so an inner `do` inside the loop body still works
                    block_stack[-1] = block_stack[-1] + "_body"
            elif val == "if":
                # Inline Luau ternary expression `local x = if c then a else b` does NOT use `end`
                is_expr_if = (prev_val in expr_prev_ops) or (prev_val in ("else", "elseif", "then") and prev_kind == "WORD" and False)
                if not is_expr_if:
                    block_stack.append("if")
                else:
                    block_stack.append("expr_if")
            elif val == "then":
                # Close marker on expr_if? Wait until we see if `else` stays inline
                pass
            elif val == "else":
                if block_stack and block_stack[-1] == "expr_if":
                    block_stack.pop()
            elif val == "until":
                assert block_stack and block_stack[-1] == "repeat", (
                    f"{label}: 'until' without matching 'repeat' (stack={block_stack[-5:]})"
                )
                block_stack.pop()
            elif val == "end":
                assert block_stack, f"{label}: extra 'end' with empty block stack"
                top = block_stack.pop()
                assert top != "repeat", f"{label}: 'repeat' closed by 'end' instead of 'until'"

        idx += 1

    # Any trailing expr_if without else wouldn't occur in valid Luau; real statement blocks must be empty
    assert not delim_stack, f"{label}: unclosed delimiters {delim_stack}"
    assert not block_stack, f"{label}: unclosed Luau blocks {block_stack}"


def _tree_sha256(root: Path) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        if p.is_file():
            files[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


class TestAttachmentEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = AttachmentEngine(BUNDLED_SKILLS_DIR)

    def test_official_r15_catalog_and_validators(self) -> None:
        cat = self.engine.get_catalog()
        self.assertTrue(cat["ok"])
        self.assertIn("HumanoidRootPart", cat["r15_attachments"])
        self.assertIn("RightHand", cat["r15_attachments"])
        self.assertIn("RightGripAttachment", cat["r15_attachments"]["RightHand"])
        self.assertIn("BodyBackAttachment", cat["r15_attachments"]["UpperTorso"])
        self.assertIn("WaistCenterAttachment", cat["r15_attachments"]["LowerTorso"])
        self.assertIn("LeftFootAttachment", cat["r15_attachments"]["LeftFoot"])
        self.assertIn("RightFootAttachment", cat["r15_attachments"]["RightFoot"])

        for preset_name in ("sword", "bow", "shield", "staff", "gun", "backpack", "cape", "wings", "pet"):
            self.assertIn(preset_name, cat["socket_presets"])
            self.assertIn(preset_name, SOCKET_PRESETS)

        good = self.engine.validate_r15_attachment("RightHand", "RightGripAttachment")
        self.assertTrue(good["ok"])

        bad_limb = self.engine.validate_r15_attachment("NonExistentLimb", "RightGripAttachment")
        self.assertFalse(bad_limb["ok"])

        bad_att = self.engine.validate_r15_attachment("RightHand", "FakeSocket")
        self.assertFalse(bad_att["ok"])

        bad_spec = self.engine.validate_attachment_spec(mode="unknown_mode")
        self.assertFalse(bad_spec["ok"])

        oversized = self.engine.validate_attachment_spec(
            mode="accessory_rigid",
            preset="sword",
            rig_height_studs=5.0,
            item_size_studs=[20.0, 1.0, 1.0],
        )
        self.assertTrue(oversized["ok"])
        self.assertTrue(oversized["warnings"], "Expected scale mismatch warning for oversized prop")

    def test_blender_sidecar_load_and_consumption(self) -> None:
        sidecar = {
            "schema": "sharp.attachment_sidecar.v1",
            "prop_name": "Sunblade",
            "prop_kind": "sword",
            "attachment_mode": "rigid",
            "slot": "right_hand",
            "rig_height_studs": 5.0,
            "prop_dimensions_studs": [0.4, 3.6, 0.9],
            "target_limb": "RightHand",
            "target_limb_attachment": "RightGripAttachment",
            "attachments": [
                {
                    "name": "GripAttachment",
                    "role": "primary",
                    "target_limb": "RightHand",
                    "target_limb_attachment": "RightGripAttachment",
                    "pos": [0.0, 0.0, 0.0],
                    "rot_deg": [0.0, 0.0, 0.0],
                },
                {
                    "name": "ForegripAttachment",
                    "role": "foregrip",
                    "target_limb": "LeftHand",
                    "target_limb_attachment": "LeftGripAttachment",
                    "pos": [0.0, 0.65, 0.0],
                    "rot_matrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            sc_path = Path(td) / "Sunblade_attachments.json"
            sc_path.write_text(json.dumps(sidecar), encoding="utf-8")

            loaded = self.engine.load_blender_sidecar(sc_path)
            self.assertTrue(loaded["ok"])
            self.assertEqual(loaded["prop_name"], "Sunblade")
            self.assertEqual(len(loaded["attachments"]), 2)
            self.assertEqual(loaded["attachments"][1]["rot_deg"], [0.0, 0.0, 0.0])

            luau = self.engine.compile_attach_luau(
                rig_path="Workspace.Hero",
                item_path="ReplicatedStorage.Sunblade",
                mode="two_hand_ik",
                preset="sword",
                sidecar_path=str(sc_path),
            )
            assert_valid_luau_sanity(luau, "two_hand_ik_sidecar")
            self.assertIn("ForegripAttachment", luau)
            self.assertIn("IKControl", luau)

    def test_compile_all_attachment_modes_and_luau_sanity(self) -> None:
        luau_rigid = self.engine.compile_attach_luau(mode="accessory_rigid", preset="backpack")
        assert_valid_luau_sanity(luau_rigid, "accessory_rigid")
        self.assertIn("RigidConstraint", luau_rigid)
        self.assertIn("__SharpActiveRecordingId", luau_rigid)
        self.assertIn("ChangeHistoryService", luau_rigid)
        self.assertIn("Massless = true", luau_rigid)
        self.assertIn("CanCollide = false", luau_rigid)
        self.assertIn("CustomPhysicalProperties", luau_rigid)

        luau_tool = self.engine.compile_attach_luau(mode="tool_grip", preset="sword")
        assert_valid_luau_sanity(luau_tool, "tool_grip")
        self.assertIn("RequiresHandle = true", luau_tool)
        self.assertIn(".Grip =", luau_tool)

        luau_m6d = self.engine.compile_attach_luau(mode="motor6d_weapon", preset="sword")
        assert_valid_luau_sanity(luau_m6d, "motor6d_weapon")
        self.assertIn('Instance.new("Motor6D")', luau_m6d)
        self.assertIn("RequiresHandle = false", luau_m6d)
        self.assertIn("RightGrip", luau_m6d)
        self.assertIn("limbAtt.CFrame", luau_m6d)
        self.assertIn("itemAtt.CFrame", luau_m6d)

        for holster_mode in ("holster_back", "holster_hip", "shield_back"):
            luau_h = self.engine.compile_attach_luau(mode=holster_mode, preset="shield" if holster_mode == "shield_back" else "sword")
            assert_valid_luau_sanity(luau_h, holster_mode)
            self.assertIn("RigidConstraint", luau_h)

        luau_armor = self.engine.compile_attach_luau(
            mode="armor_set",
            item_path="Workspace.KnightArmorSet",
            armor_slot_map={
                "helmet": "Workspace.KnightArmorSet.Helmet",
                "chest": "Workspace.KnightArmorSet.Cuirass",
                "left_pauldron": "Workspace.KnightArmorSet.PauldronL",
                "right_greave": "Workspace.KnightArmorSet.GreaveR",
            },
        )
        assert_valid_luau_sanity(luau_armor, "armor_set")
        self.assertIn("HttpService:JSONDecode", luau_armor)
        self.assertIn("HatAttachment", luau_armor)
        self.assertIn("LeftShoulderAttachment", luau_armor)

        luau_ik = self.engine.compile_attach_luau(mode="two_hand_ik", preset="gun")
        assert_valid_luau_sanity(luau_ik, "two_hand_ik")
        self.assertIn("IKControlType", luau_ik)
        self.assertIn("pcall(", luau_ik)
        self.assertIn("ChainRoot", luau_ik)
        self.assertIn("EndEffector", luau_ik)
        self.assertIn("SmoothTime", luau_ik)

        luau_verify = self.engine.compile_attach_luau(
            mode="verify",
            rig_path="Workspace.Rig",
            item_path="Workspace.Weapon",
            preset="sword",
        )
        assert_valid_luau_sanity(luau_verify, "verify")
        self.assertNotIn("TryBeginRecording", luau_verify, "verify mode must remain read-only")
        self.assertIn("attachmentWorldOffsets", luau_verify)
        self.assertIn("conflictingJoints", luau_verify)
        self.assertIn("scaleMismatch", luau_verify)

    def test_compile_inspect_attachment_fit_luau(self) -> None:
        for pose in ("raised_arm", "slash_windup", "block_guard", "overhead_reach", "crouch"):
            luau_fit = self.engine.compile_inspect_attachment_fit_luau(
                rig_path="Workspace.TestWarrior",
                item_path="Workspace.PauldronR",
                test_pose=pose,
                clearance_margin_studs=0.02,
            )
            assert_valid_luau_sanity(luau_fit, f"inspect_fit_{pose}")
            self.assertEqual(luau_fit.count("--!strict"), 1)
            self.assertNotIn("TryBeginRecording", luau_fit, "inspect_attachment_fit must remain read-only")
            for required_token in (
                "obbSignedGap",
                "fit_passed",
                "penetrations",
                "minClearanceStuds",
                "recommendedOffsets",
                "UpperTorso",
                "LeftUpperArm",
                "RightUpperArm",
            ):
                self.assertIn(required_token, luau_fit)


class TestRigAnimationQualityAndPresets(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RigAnimationEngine(BUNDLED_SKILLS_DIR)

    def test_all_thirteen_procedural_presets_generate_normalize_and_pass_quality(self) -> None:
        cat = self.engine.list_procedural_presets()
        self.assertTrue(cat["ok"])
        expected_names = [
            "idle_breathing",
            "walk",
            "run",
            "sword_slash_single",
            "sword_combo_3hit",
            "dash_roll",
            "jump_land",
            "cast_spell",
            "bow_draw_release",
            "shield_block",
            "hit_react",
            "death",
            "emote_wave",
        ]
        self.assertEqual(len(cat["presets"]), 13)
        for name in expected_names:
            self.assertIn(name, cat["presets"])
            raw = self.engine.generate_procedural_preset(name, fps=30.0, intensity=1.0)
            norm = self.engine.normalize_clip_dict(raw)
            report_default = self.engine.analyze_clip(norm)
            self.assertTrue(report_default["ok"], f"{name} (default kind) failed analyze_clip")
            self.assertTrue(report_default["passed"], f"{name} (default kind) reported quality issues: {report_default['issues']}")
            self.assertGreaterEqual(report_default["quality_score"], 85, f"{name} (default kind) low score: {report_default}")
            report = self.engine.analyze_clip(norm, expected_kind=name)
            self.assertTrue(report["ok"], f"{name} failed analyze_clip")
            self.assertTrue(report["passed"], f"{name} reported quality issues: {report['issues']}")
            self.assertGreaterEqual(report["quality_score"], 85, f"{name} low score: {report}")
            if name == "shield_block":
                max_slide = max(m["total_stance_slide_studs"] for m in report_default["metrics"]["feet"].values())
                self.assertLessEqual(max_slide, 0.1, f"shield_block stance foot slide too high: {max_slide}")

        # Verify new 4 preset specific metadata, markers, and launch arcs
        slash_raw = self.engine.generate_procedural_preset("sword_slash_single")
        self.assertEqual(slash_raw["priority"], "Action2")
        self.assertFalse(slash_raw["loop"])
        self.assertTrue(any(m.get("name") == "HitFrame" for m in slash_raw.get("markers", [])))

        dash_raw = self.engine.generate_procedural_preset("dash_roll")
        self.assertEqual(dash_raw["priority"], "Action")
        self.assertFalse(dash_raw["loop"])

        jump_raw = self.engine.generate_procedural_preset("jump_land")
        self.assertEqual(jump_raw["priority"], "Movement")
        self.assertFalse(jump_raw["loop"])
        max_torso_y = max(fr["poses"]["LowerTorso"]["pos"][1] for fr in jump_raw["frames"])
        self.assertGreater(max_torso_y, 0.5, f"jump_land missing +Y LowerTorso launch arc: {max_torso_y}")

        cast_raw = self.engine.generate_procedural_preset("cast_spell")
        self.assertEqual(cast_raw["priority"], "Action2")
        self.assertFalse(cast_raw["loop"])
        self.assertTrue(any(m.get("name") == "CastRelease" for m in cast_raw.get("markers", [])))

        # Verify expected_kind='shield_block' normalizes to 'block' and catches foot sliding
        shield_bad = json.loads(json.dumps(self.engine.generate_procedural_preset("shield_block")))
        for idx, fr in enumerate(shield_bad["frames"]):
            phase = idx / max(1, len(shield_bad["frames"]) - 1)
            ang = math.radians(18.0 * math.sin(math.pi * phase))
            c, s = math.cos(ang), math.sin(ang)
            fr["poses"]["RightUpperLeg"]["rot"] = [c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c]
        for ek in (None, "shield_block", "block"):
            rep_shield_bad = self.engine.analyze_clip(shield_bad, expected_kind=ek)
            self.assertFalse(rep_shield_bad["passed"], f"shield_block bad slide not caught for expected_kind={ek}")
            self.assertIn("foot_sliding", {i["check"] for i in rep_shield_bad["issues"]})

        batch = self.engine.generate_procedural_presets(["idle_breathing", "walk", "sword_combo_3hit"])
        self.assertEqual(batch["count"], 3)
        self.assertIn("Idle_Breathing", batch["clips"])

        # Verify v2 RPG pacing durations (tempo_scale=1.0, style='heavy_souls') and all 5 animation style profiles
        expected_v2_durations = {
            "idle_breathing": 2.80,
            "walk": 1.20,
            "run": 0.80,
            "sword_slash_single": 1.35,
            "sword_combo_3hit": 2.40,
            "shield_block": 1.30,
            "bow_draw_release": 1.65,
            "cast_spell": 1.70,
            "jump_land": 1.25,
            "dash_roll": 1.05,
            "hit_react": 0.95,
            "death": 1.80,
            "emote_wave": 2.10,
        }
        self.assertEqual(set(ANIMATION_STYLE_PROFILES.keys()), {
            "heavy_souls", "snappy_anime", "stylized_cartoony", "tactical_military", "floaty_arcane",
        })
        for pname, expected_dur in expected_v2_durations.items():
            self.assertAlmostEqual(PROCEDURAL_PRESET_CATALOG[pname]["duration"], expected_dur, places=4)
            clip_hs = self.engine.generate_procedural_preset(pname, style="heavy_souls", tempo_scale=1.0)
            self.assertAlmostEqual(clip_hs["frames"][-1]["t"], expected_dur, places=3)

        for style_id in ANIMATION_STYLE_PROFILES:
            for pname in ("sword_slash_single", "cast_spell", "sword_combo_3hit", "walk"):
                styled = self.engine.generate_procedural_preset(pname, style=style_id, tempo_scale=1.0)
                rep = self.engine.analyze_clip(styled, expected_kind=pname)
                self.assertTrue(rep["passed"], f"{style_id}/{pname} failed: {rep['issues']}")
                self.assertGreaterEqual(rep["quality_score"], 85, f"{style_id}/{pname} low score: {rep}")

        # Verify explicit windup hold & impact hit-stop markers on slash/cast
        self.assertIn("WindupHoldEnd", {m["name"] for m in slash_raw["markers"]})
        self.assertIn("HitStopEnd", {m["name"] for m in slash_raw["markers"]})
        self.assertIn("CastHoldEnd", {m["name"] for m in cast_raw["markers"]})

    def test_compose_custom_clip_and_pose_preview_luau(self) -> None:
        composed_kp = self.engine.compose_custom_clip(
            {
                "name": "GreatswordCleave",
                "priority": "Action2",
                "kind": "attack",
                "keyposes": [
                    {"t": 0.0, "poses": {"UpperTorso": {"rot": [0, 0, 0]}, "RightUpperArm": {"rot": [-5, 0, -8]}}},
                    {
                        "t": 0.25,
                        "hold": 0.20,
                        "poses": {
                            "LowerTorso": {"rot": [2, -16, 0]},
                            "UpperTorso": {"rot": [8, -22, 0]},
                            "RightUpperArm": {"rot": [-36, -22, -18]},
                            "RightLowerArm": {"rot": [-48, 0, 0]},
                            "LeftUpperLeg": {"rot": [12, 0, 0]},
                            "LeftLowerLeg": {"rot": [-24, 0, 0]},
                            "RightUpperLeg": {"rot": [12, 0, 0]},
                            "RightLowerLeg": {"rot": [-24, 0, 0]},
                        },
                    },
                    {
                        "t": 0.68,
                        "hold": 0.16,
                        "poses": {
                            "LowerTorso": {"rot": [-4, 18, 0]},
                            "UpperTorso": {"rot": [-12, 24, 0]},
                            "RightUpperArm": {"rot": [46, 26, 12]},
                            "RightLowerArm": {"rot": [-14, 0, 0]},
                        },
                    },
                    {"t": 1.25, "poses": {"UpperTorso": {"rot": [0, 0, 0]}, "RightUpperArm": {"rot": [-5, 0, -8]}}},
                ],
                "markers": [{"t": 0.68, "name": "HitFrame", "value": "cleave"}],
            },
            style="heavy_souls",
            tempo_scale=1.0,
            auto_ground_feet=True,
        )
        self.assertTrue(composed_kp["ok"])
        self.assertTrue(composed_kp["analysis"]["passed"], f"compose_custom_clip failed: {composed_kp['analysis']}")
        self.assertGreaterEqual(composed_kp["analysis"]["quality_score"], 85)
        self.assertGreater(len(composed_kp["frames"]), 20)
        self.assertEqual(composed_kp["markers"][0]["name"], "HitFrame")

        composed_ct = self.engine.compose_custom_clip(
            {
                "name": "ArcaneFloat",
                "priority": "Action",
                "kind": "emote",
                "channel_tracks": {
                    "LowerTorso.y": [(0.0, 0.0), (0.5, -0.04), (1.0, 0.0)],
                    "UpperTorso.rx": [(0.0, 0.0), (0.4, -10.0), (0.6, -10.0), (1.0, 0.0)],
                    "RightUpperArm.rx": [(0.0, -5.0), (0.4, 72.0), (0.6, 72.0), (1.0, -5.0)],
                    "RightLowerArm.rx": [(0.0, -14.0), (0.4, -36.0), (1.0, -14.0)],
                    "Head.rx": [(0.0, 0.0), (0.5, -12.0), (1.0, 0.0)],
                },
                "markers": [{"t": 0.4, "name": "Apex", "value": "float"}],
            },
            style="floaty_arcane",
        )
        self.assertTrue(composed_ct["ok"])
        self.assertTrue(composed_ct["analysis"]["passed"], f"channel_tracks failed: {composed_ct['analysis']}")
        self.assertGreaterEqual(composed_ct["analysis"]["quality_score"], 85)

        luau_pose = self.engine.compile_pose_at_time_luau(
            rig_path="Workspace.TestWarrior",
            clip_name="Sword_Slash_Single",
            folder_name="Animations",
            time_fraction=0.55,
        )
        assert_valid_luau_sanity(luau_pose, "compile_pose_at_time_luau")
        self.assertEqual(luau_pose.count("--!strict"), 1)
        self.assertIn("Motor6D", luau_pose)
        self.assertIn(".Transform", luau_pose)
        self.assertIn("CurveAnimation", luau_pose)
        self.assertIn("KeyframeSequence", luau_pose)

        luau_strip = self.engine.compile_pose_strip_luau(
            rig_path="Workspace.TestWarrior",
            clip_name="Sword_Slash_Single",
            folder_name="Animations",
            sample_fractions=(0.0, 0.25, 0.55, 0.78, 1.0),
        )
        assert_valid_luau_sanity(luau_strip, "compile_pose_strip_luau")
        self.assertEqual(luau_strip.count("--!strict"), 1)
        self.assertIn("SharpPoseStrip_", luau_strip)
        self.assertIn("SAMPLE_FRACTIONS", luau_strip)

    def test_quality_analyzer_catches_negative_fixtures(self) -> None:
        # 1) Loop seam mismatch
        walk = self.engine.generate_procedural_preset("walk")
        bad_seam = json.loads(json.dumps(walk))
        bad_seam["frames"][-1]["poses"]["RightUpperArm"]["rot"] = [0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        rep_seam = self.engine.analyze_clip(bad_seam, expected_kind="walk")
        self.assertFalse(rep_seam["passed"])
        self.assertIn("loop_seam_delta", {i["check"] for i in rep_seam["issues"]})

        # 2) Rotation pop / overspeed
        bad_pop = json.loads(json.dumps(walk))
        mid = len(bad_pop["frames"]) // 2
        bad_pop["frames"][mid]["poses"]["UpperTorso"]["rot"] = [-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0]
        rep_pop = self.engine.analyze_clip(bad_pop, expected_kind="walk")
        self.assertFalse(rep_pop["passed"])
        self.assertIn("overspeed_rotation", {i["check"] for i in rep_pop["issues"]})

        # 3) Foot sliding on stationary pose: slide RightFoot horizontally across frames then back smoothly
        idle = self.engine.generate_procedural_preset("idle_breathing")
        bad_slide = json.loads(json.dumps(idle))
        n_fr = len(bad_slide["frames"])
        for idx, fr in enumerate(bad_slide["frames"]):
            phase = idx / max(1, n_fr - 1)
            ang = math.radians(18.0 * math.sin(math.pi * phase))
            c, s = math.cos(ang), math.sin(ang)
            fr["poses"]["RightUpperLeg"]["rot"] = [1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c]
        rep_slide = self.engine.analyze_clip(bad_slide, expected_kind="idle")
        self.assertFalse(rep_slide["passed"])
        self.assertIn("foot_sliding", {i["check"] for i in rep_slide["issues"]})

        # 4) Missing root motion in locomotion
        bad_root = json.loads(json.dumps(walk))
        ident = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        for fr in bad_root["frames"]:
            fr["poses"]["LowerTorso"] = {"pos": [0.0, 0.0, 0.0], "rot": ident}
            fr["poses"]["HumanoidRootPart"] = {"pos": [0.0, 0.0, 0.0], "rot": ident}
        rep_root = self.engine.analyze_clip(bad_root, expected_kind="walk")
        self.assertIn("missing_root_motion", {i["check"] for i in rep_root["issues"]})

        # 5) Bad priority & non-looping walk
        bad_meta = json.loads(json.dumps(walk))
        bad_meta["priority"] = "FakePriority"
        bad_meta["loop"] = False
        rep_meta = self.engine.analyze_clip(bad_meta, expected_kind="walk")
        checks = {i["check"] for i in rep_meta["issues"]}
        self.assertIn("priority_sanity", checks)
        self.assertIn("loop_sanity", checks)

        # 6) Completely frozen 0-motion clip must fail (QA Defect #5a)
        frozen = {
            "name": "Frozen_Idle",
            "loop": True,
            "priority": "Idle",
            "fps": 30.0,
            "frames": [
                {"t": i / 15.0 * 0.5, "poses": {"UpperTorso": {"pos": [0.0, 0.0, 0.0], "rot": ident}}}
                for i in range(16)
            ],
        }
        rep_frozen = self.engine.analyze_clip(frozen, expected_kind="idle")
        self.assertFalse(rep_frozen["passed"])
        self.assertIn("frozen_static_clip", {i["check"] for i in rep_frozen["issues"]})

        # 7) 3-joint lockstep robotic slash peaking simultaneously with static torso must fail (QA Defect #5b)
        lockstep_frames = []
        n_ls = 16
        dur_ls = 0.5
        for i in range(n_ls):
            t = dur_ls * i / (n_ls - 1)
            # Symmetric tent peaking smoothly at t=0.25 across UpperTorso, RightUpperArm, RightLowerArm identically
            u = 1.0 - abs(2.0 * (i / (n_ls - 1)) - 1.0)
            deg = 32.0 * (u * u * (3.0 - 2.0 * u))
            r = math.radians(deg)
            c, s = math.cos(r), math.sin(r)
            rot_x = [1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c]
            lockstep_frames.append({
                "t": t,
                "poses": {
                    "UpperTorso": {"pos": [0.0, 0.0, 0.0], "rot": rot_x},
                    "RightUpperArm": {"pos": [0.0, 0.0, 0.0], "rot": rot_x},
                    "RightLowerArm": {"pos": [0.0, 0.0, 0.0], "rot": rot_x},
                },
            })
        rep_lock = self.engine.analyze_clip(
            {"name": "Robotic_Slash", "loop": False, "priority": "Action", "fps": 30.0, "frames": lockstep_frames},
            expected_kind="attack",
        )
        self.assertFalse(rep_lock["passed"])
        lock_checks = {i["check"] for i in rep_lock["issues"]}
        self.assertIn("robotic_lockstep", lock_checks)
        self.assertIn("missing_root_motion", lock_checks)

    def test_generated_playback_and_clip_builder_luau(self) -> None:
        walk = self.engine.generate_procedural_preset("walk")
        luau_build = self.engine.compile_animation_from_clips_luau(
            clips_data={"Walk": walk},
            rig_path="Workspace.Rig",
            install_track_cache_helper=True,
        )
        assert_valid_luau_sanity(luau_build, "compile_animation_from_clips_luau")
        self.assertIn("SharpAnimTrackCache", luau_build)
        self.assertIn("Animator:LoadAnimation", luau_build)

        luau_play = self.engine.compile_playback_test_luau(
            rig_path="Workspace.Rig",
            clip_name="Walk_Locomotion",
            play_now=True,
        )
        assert_valid_luau_sanity(luau_play, "compile_playback_test_luau")
        self.assertIn("anim: Animator", luau_play)
        self.assertIn(":LoadAnimation(", luau_play)
        self.assertIn("trackCache", luau_play)

        for raw_path in ("Workspace.TestWarrior", "game.Workspace.TestWarrior"):
            probe_luau = self.engine.compile_probe_rig_luau(rig_path=raw_path)
            assert_valid_luau_sanity(probe_luau, f"compile_probe_rig_luau({raw_path})")
            self.assertEqual(probe_luau.count("--!strict"), 1)
            self.assertIn('local TARGET_PATH: string = "Workspace.TestWarrior"', probe_luau)
            self.assertNotIn('local TARGET_PATH: string = ""', probe_luau)


class TestBlenderAttachCompilerAndHygiene(unittest.TestCase):
    def setUp(self) -> None:
        self.blender = BlenderDomainEngine(BUNDLED_SKILLS_DIR)

    def test_compile_asset_attach_bpy_rigid_and_skinned_compile_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            res_rigid = self.blender.compile_asset_attach_bpy(
                prop_kind="sword",
                prop_name="IronLongsword",
                attachment_mode="rigid",
                output_dir=td,
                execute=False,
            )
            self.assertTrue(res_rigid["ok"])
            self.assertEqual(res_rigid["attachment_mode"], "rigid")
            self.assertEqual(res_rigid["target_limb"], "RightHand")
            self.assertEqual(res_rigid["target_limb_attachment"], "RightGripAttachment")
            compile(res_rigid["compiled_bpy_code"], "compile_asset_attach_rigid.py", "exec")
            self.assertIn("BSDF_PRINCIPLED", res_rigid["compiled_bpy_code"])
            self.assertIn("wm.obj_import", res_rigid["compiled_bpy_code"])
            code_lines = [ln for ln in res_rigid["compiled_bpy_code"].splitlines() if not ln.lstrip().startswith("#")]
            self.assertNotIn("use_auto_smooth", "\n".join(code_lines))

            res_armor = self.blender.compile_asset_attach_bpy(
                prop_kind="chest",
                prop_name="SteelCuirass",
                attachment_mode="skinned_armor",
                output_dir=td,
                execute=False,
            )
            self.assertTrue(res_armor["ok"])
            self.assertEqual(res_armor["attachment_mode"], "skinned_armor")
            compile(res_armor["compiled_bpy_code"], "compile_asset_attach_armor.py", "exec")
            self.assertIn("ARMATURE_AUTO", res_armor["compiled_bpy_code"])
            self.assertIn("kept = non_zero[:4]", res_armor["compiled_bpy_code"])

    def test_blender_prop_presets_match_official_r15_and_attachment_modes(self) -> None:
        attach_eng = AttachmentEngine(BUNDLED_SKILLS_DIR)
        all_kinds = (
            "sword", "bow", "shield", "staff", "gun", "backpack", "cape", "wings", "pet",
            "helmet", "chest", "pauldron", "left_pauldron", "right_pauldron",
            "greave", "left_greave", "right_greave", "boot", "gauntlet",
        )
        with tempfile.TemporaryDirectory() as td:
            for k in all_kinds:
                res = self.blender.compile_asset_attach_bpy(prop_kind=k, output_dir=td, execute=False)
                self.assertTrue(res["ok"], f"{k} failed compile_asset_attach_bpy")
                chk = attach_eng.validate_r15_attachment(res["target_limb"], res["target_limb_attachment"])
                self.assertTrue(chk["ok"], f"{k} emitted invalid R15 pair: {chk}")
                spec = attach_eng.validate_attachment_spec(
                    mode=res["attachment_mode"],
                    slot=res["slot"],
                    limb_part=res["target_limb"],
                    limb_attachment=res["target_limb_attachment"],
                )
                self.assertTrue(spec["ok"], f"{k} rejected by AttachmentEngine: {spec}")
                self.assertEqual(spec["warnings"], [], f"{k} produced warnings: {spec['warnings']}")
                luau = attach_eng.compile_attach_luau(
                    mode=res["attachment_mode"],
                    slot=res["slot"],
                    limb_part=res["target_limb"],
                    limb_attachment=res["target_limb_attachment"],
                )
                assert_valid_luau_sanity(luau, f"blender_compat_{k}")

            # Specifically verify QA Defect #1 limbs + two_handed_ik / two_hand_ik tolerance
            pauldron = self.blender.compile_asset_attach_bpy(prop_kind="pauldron", output_dir=td, execute=False)
            self.assertEqual(pauldron["target_limb"], "RightUpperArm")
            self.assertEqual(pauldron["target_limb_attachment"], "RightShoulderAttachment")
            l_pauldron = self.blender.compile_asset_attach_bpy(prop_kind="left_pauldron", output_dir=td, execute=False)
            self.assertEqual(l_pauldron["target_limb"], "LeftUpperArm")
            self.assertEqual(l_pauldron["target_limb_attachment"], "LeftShoulderAttachment")
            pet = self.blender.compile_asset_attach_bpy(prop_kind="pet", output_dir=td, execute=False)
            self.assertEqual(pet["target_limb"], "UpperTorso")
            self.assertEqual(pet["target_limb_attachment"], "RightCollarAttachment")

            for ik_mode in ("two_hand_ik", "two_handed_ik"):
                ik_res = self.blender.compile_asset_attach_bpy(
                    prop_kind="gun", attachment_mode=ik_mode, output_dir=td, execute=False
                )
                self.assertEqual(ik_res["attachment_mode"], "rigid")
                self.assertEqual(ik_res["attach_mode"], "two_hand_ik")

    def test_sculpted_multi_material_prop_geometry_and_mesh_stats(self) -> None:
        all_kinds = (
            "sword", "bow", "shield", "staff", "gun", "backpack", "cape", "wings", "pet",
            "helmet", "chest", "pauldron", "left_pauldron", "right_pauldron",
            "greave", "left_greave", "right_greave", "boot", "gauntlet",
        )
        attach_eng = AttachmentEngine(BUNDLED_SKILLS_DIR)
        with tempfile.TemporaryDirectory(prefix="sharp_bmesh_test_") as td:
            for k in all_kinds:
                res = self.blender.compile_asset_attach_bpy(
                    prop_kind=k,
                    prop_name=f"Hero_{k}",
                    accent_hex="#FF3366",
                    output_dir=td,
                    execute=False,
                )
                self.assertTrue(res["ok"])
                self.assertEqual(res["accent_hex"], "#FF3366")
                src = res["compiled_bpy_code"]
                compile(src, f"sculpted_{k}.py", "exec")
                self.assertIn("_sharp_ensure_multi_materials", src)
                self.assertIn("within_roblox_10k_budget", src)
                self.assertIn("PrimaryMetal", src)
                self.assertIn("CoreEmblem", src)

            # Sidecar loader preserves mesh_stats cleanly
            sample_sidecar = {
                "schema": "sharp.attachment_sidecar.v1",
                "prop_name": "Sunblade",
                "prop_kind": "sword",
                "mesh_stats": {
                    "triangle_count": 402,
                    "vertex_count": 225,
                    "material_count": 4,
                    "uv_present": True,
                    "within_roblox_10k_budget": True,
                },
                "attachments": [
                    {
                        "name": "GripAttachment",
                        "role": "primary",
                        "target_limb": "RightHand",
                        "target_limb_attachment": "RightGripAttachment",
                        "pos": [0.0, 0.0, 0.0],
                        "rot_deg": [0.0, 0.0, 0.0],
                    }
                ],
            }
            parsed = attach_eng.load_blender_sidecar(sample_sidecar)
            self.assertTrue(parsed["ok"])
            self.assertEqual(parsed["mesh_stats"]["triangle_count"], 402)
            self.assertEqual(parsed["mesh_stats"]["material_count"], 4)

            if detect_blender_installation().get("installed"):
                live_res = self.blender.compile_asset_attach_bpy(
                    prop_kind="sword",
                    prop_name="StarforgeSword",
                    accent_hex="#22D3EE",
                    output_dir=str(Path(td) / "live_sword"),
                    execute=True,
                    execution_mode="headless",
                    timeout_sec=60.0,
                )
                self.assertTrue(live_res["ok"] and live_res["executed"], f"Headless Blender failed: {live_res}")
                ms = live_res.get("mesh_stats") or {}
                self.assertGreaterEqual(int(ms.get("triangle_count", 0)), 150)
                self.assertEqual(ms.get("material_count"), 4)
                self.assertTrue(ms.get("uv_present"))
                self.assertTrue(ms.get("within_roblox_10k_budget"))
                loaded = attach_eng.load_blender_sidecar(live_res["sidecar_path"])
                self.assertTrue(loaded["ok"])
                self.assertEqual(loaded["warnings"], [])
                self.assertEqual(loaded["mesh_stats"]["material_count"], 4)

    def test_compile_custom_bmesh_asset_bpy_and_live_headless_blender(self) -> None:
        attach_eng = AttachmentEngine(BUNDLED_SKILLS_DIR)
        with tempfile.TemporaryDirectory(prefix="sharp_custom_bmesh_") as td:
            custom_code = """
add_cylinder(bm, 0.06, 0.055, 0.75, segs=10, loc=(0.0, 0.0, 0.0), mat_idx=2)
add_box(bm, (0.55, 0.14, 0.12), (0.0, 0.0, 0.38), bevel_ratio=0.16, mat_idx=1)
add_tapered_blade(bm, width=0.24, thickness=0.09, length=2.2, tip_len=0.45, loc=(0.0, 0.0, 0.44), mat_idx=0)
add_faceted_gem(bm, 0.08, 0.09, 0.10, loc=(0.0, 0.0, 0.38), mat_idx=3)
"""
            compiled = self.blender.compile_custom_bmesh_asset_bpy(
                asset_name="ArcaneGreatsword",
                custom_bpy_code=custom_code,
                asset_style="dark_gothic_souls",
                texture_style="arcane_emissive_runes",
                attach_mode="motor6d_weapon",
                slot="right_hand",
                primary_hex="#2D313A",
                secondary_hex="#C89D54",
                accent_hex="#F43F5E",
                output_dir=td,
                execute=False,
            )
            self.assertTrue(compiled["ok"])
            self.assertEqual(compiled["asset_style"], "dark_gothic_souls")
            self.assertEqual(compiled["texture_style"], "arcane_emissive_runes")
            src = compiled["compiled_bpy_code"]
            compile(src, "custom_bmesh_compiled.py", "exec")
            for mat_slot in ("PrimaryMetal", "TrimAccent", "LeatherGrip", "CoreEmblem"):
                self.assertIn(mat_slot, src)
            self.assertIn("smart_project", src)
            self.assertIn("recalc_face_normals", src)

            if detect_blender_installation().get("installed"):
                live_dir = Path(td) / "live_custom"
                live_res = self.blender.compile_custom_bmesh_asset_bpy(
                    asset_name="ArcaneGreatsword",
                    custom_bpy_code=custom_code,
                    asset_style="handpainted_fantasy_rpg",
                    texture_style="stylized_gradient_atlas",
                    attach_mode="motor6d_weapon",
                    slot="right_hand",
                    output_dir=str(live_dir),
                    export_fbx=True,
                    export_glb=True,
                    render_preview=True,
                    execute=True,
                    execution_mode="headless",
                    timeout_sec=90.0,
                )
                self.assertTrue(live_res["ok"] and live_res["executed"], f"Headless custom_bmesh failed: {live_res}")
                self.assertTrue(Path(live_res["fbx_path"]).is_file())
                self.assertTrue(Path(live_res["glb_path"]).is_file())
                self.assertTrue(Path(live_res["sidecar_path"]).is_file())
                self.assertTrue(Path(live_res["preview_path"]).is_file())
                self.assertTrue((live_dir / "preview.png").is_file())
                self.assertGreater((live_dir / "preview.png").stat().st_size, 500)

                ms = live_res["mesh_stats"]
                self.assertEqual(ms["material_slots"], ["PrimaryMetal", "TrimAccent", "LeatherGrip", "CoreEmblem"])
                self.assertTrue(ms["uv_present"])
                self.assertTrue(ms["within_roblox_10k_budget"])
                self.assertEqual(ms["non_manifold_edges"], 0)
                self.assertTrue(ms["is_manifold"])
                self.assertLess(ms["triangle_count"], 10000)

                sidecar = attach_eng.load_blender_sidecar(live_res["sidecar_path"])
                self.assertTrue(sidecar["ok"])
                self.assertEqual(sidecar["warnings"], [])
                self.assertEqual(sidecar["target_limb"], "RightHand")
                self.assertEqual(sidecar["target_limb_attachment"], "RightGripAttachment")

    def test_runtime_files_and_skills_hygiene_and_mirror_parity(self) -> None:
        runtime_files = [
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "attachment_engine.py",
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "rig_anim_engine.py",
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "blender_engine.py",
        ]
        forbidden = ["Mixar", "mixar", "Forge", "C:\\Users\\willy", "C:/Users/willy", "@auto_inject_skill"]
        for rf in runtime_files:
            txt = rf.read_text(encoding="utf-8")
            for pat in forbidden:
                self.assertNotIn(pat, txt, f"Forbidden token {pat!r} found in {rf.name}")

        # Verify studio_test_anim.luau sanity
        test_anim_luau = BUNDLED_SKILLS_DIR / "roblox-animation" / "scripts" / "studio_test_anim.luau"
        assert_valid_luau_sanity(test_anim_luau.read_text(encoding="utf-8"), "studio_test_anim.luau")

    def test_external_skill_mirror_parity(self) -> None:
        for root in (LIVE_SKILLS_DIR / "roblox-animation", LIVE_SKILLS_DIR / "blender-game-assets", LIVE_SKILLS_DIR / "blender-character-rigging", DESKTOP_ANIM_SKILL):
            if not root.is_dir():
                self.skipTest(f"External skill mirror not installed: {root}")
        forbidden = ["Mixar", "mixar", "Forge", "C:\\Users\\willy", "C:/Users/willy", "@auto_inject_skill"]
        skill_pairs = [
            ("roblox-animation", [BUNDLED_SKILLS_DIR / "roblox-animation", LIVE_SKILLS_DIR / "roblox-animation", DESKTOP_ANIM_SKILL]),
            ("blender-game-assets", [BUNDLED_SKILLS_DIR / "blender-game-assets", LIVE_SKILLS_DIR / "blender-game-assets"]),
            ("blender-character-rigging", [BUNDLED_SKILLS_DIR / "blender-character-rigging", LIVE_SKILLS_DIR / "blender-character-rigging"]),
        ]
        for sname, dirs in skill_pairs:
            existing = [d for d in dirs if d.is_dir()]
            if not existing:
                continue
            for d in existing:
                self.assertEqual(list(d.rglob("__pycache__")), [], f"Unexpected __pycache__ in {d}")
                for p in d.rglob("*"):
                    if p.is_file():
                        body = p.read_text(encoding="utf-8", errors="ignore")
                        for pat in forbidden:
                            self.assertNotIn(pat, body, f"Forbidden token {pat!r} in skill file {p}")
            baseline = _tree_sha256(existing[0])
            for other in existing[1:]:
                self.assertEqual(baseline, _tree_sha256(other), f"Skill mirror drift for {sname}: {other}")


if __name__ == "__main__":
    unittest.main()
