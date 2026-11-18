"""Isolated unit and adversarial tests for GamePlanner, CriticalAuditEngine, LuauAuditSnapshotEngine, and ProjectLibraryManager."""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sharp_mcp.domain_engines.critical_audit_engine import CriticalAuditEngine, tokenize_luau
from sharp_mcp.domain_engines.game_planner import GamePlanner
from sharp_mcp.domain_engines.luau_audit_engine import LuauAuditSnapshotEngine
from sharp_mcp.domain_engines.terrain_env_engine import TerrainEnvironmentEngine
from sharp_mcp.project_library import ProjectLibraryManager
from sharp_mcp.skill_router import resolve_default_archive_dir, resolve_default_skills_dir


BAD_LUAU_FIXTURE = """
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local MarketplaceService = game:GetService("MarketplaceService")
local Debris = game:GetService("Debris")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local store = DataStoreService:GetDataStore("PlayerData")
local BuyRemote = ReplicatedStorage.BuyRemote
local ClientAsk = ReplicatedStorage.ClientAsk

-- Deprecated globals, polling, and unbounded Instance.new
spawn(function()
    while true do
        wait(0.2)
        local p = Instance.new("Part")
        Debris:AddItem(p, 2)
    end
end)

-- Unvalidated, unthrottled RemoteEvent trusting client amount + RemoteFunction:InvokeClient
BuyRemote.OnServerEvent:Connect(function(player, amount, damage)
    local data = store:GetAsync("u_" .. tostring(player.UserId))
    player.leaderstats.Gold.Value += amount
    local char = player.Character
    if char and char:FindFirstChildOfClass("Humanoid") then
        char:FindFirstChildOfClass("Humanoid"):TakeDamage(damage)
        char:FindFirstChildOfClass("Humanoid"):LoadAnimation(ReplicatedStorage.Anim)
    end
    ClientAsk:InvokeClient(player)
end)

-- Non-idempotent ProcessReceipt without pcall or NotProcessedYet
MarketplaceService.ProcessReceipt = function(receiptInfo)
    store:SetAsync("r_" .. tostring(receiptInfo.PlayerId), true)
    return Enum.ProductPurchaseDecision.PurchaseGranted
end

-- Leaked connections inside CharacterAdded + undebounced Touched
Players.PlayerAdded:Connect(function(player)
    player.CharacterAdded:Connect(function(char)
        char.PrimaryPart.Touched:Connect(function(hit)
            print(hit.Name)
        end)
    end)
end)
"""

CLEAN_LUAU_FIXTURE = """--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local DataStoreService = game:GetService("DataStoreService")
local MarketplaceService = game:GetService("MarketplaceService")
local RunService = game:GetService("RunService")

-- Comments mentioning bad APIs must be ignored by tokenizer:
-- wait(1) spawn(fn) delay(2) RemoteFunction:InvokeClient Humanoid:LoadAnimation loadstring("x")
--[[
    while true do
        Instance.new("Part")
        Debris:AddItem(p, 1)
    end
]]

local COMMENT_SAFE_STRINGS = "wait(1) spawn() delay() :InvokeClient() Humanoid:LoadAnimation() loadstring('bad')"
local LONG_TEXT = [[
    while true do wait(0.1) end
    BuyRemote.OnServerEvent:Connect(function(p, amount) end)
]]
local BACKTICK_TEXT = `Notice: wait(1) and InvokeClient are banned; safe value is {10 + 5}`

local store = DataStoreService:GetDataStore("PlayerDataV1")
local PurchaseRemote = ReplicatedStorage:WaitForChild("Remotes"):WaitForChild("Purchase") :: RemoteEvent
local CATALOG: { [string]: { price: number } } = table.freeze({
    Sword = { price = 100 },
})

local lastRequest: { [Player]: number } = {}
local playerConnections: { [Player]: { RBXScriptConnection } } = {}
local COOLDOWN_SEC = 0.5

local function playCachedAnim(animator: Animator, anim: Animation, cache: { [string]: AnimationTrack }): AnimationTrack
    local track = cache[anim.Name]
    if not track then
        track = animator:LoadAnimation(anim)
        cache[anim.Name] = track
    end
    return track
end

PurchaseRemote.OnServerEvent:Connect(function(player: Player, itemId: unknown)
    if typeof(itemId) ~= "string" or #itemId > 32 then
        return
    end
    local now = os.clock()
    if lastRequest[player] and (now - lastRequest[player]) < COOLDOWN_SEC then
        return
    end
    lastRequest[player] = now

    local item = CATALOG[itemId]
    if not item then
        return
    end

    local ok, err = pcall(function()
        store:UpdateAsync("u_" .. tostring(player.UserId), function(old)
            local state = if type(old) == "table" then old else { Gold = 500 }
            if state.Gold >= item.price then
                state.Gold -= item.price
            end
            return state
        end)
    end)
    if not ok then
        warn(err)
    end
end)

MarketplaceService.ProcessReceipt = function(receiptInfo)
    local ok, granted = pcall(function()
        local receiptKey = tostring(receiptInfo.PurchaseId)
        local alreadyProcessed = false
        store:UpdateAsync("rcpt_" .. receiptKey, function(prev)
            if prev == true then
                alreadyProcessed = true
                return true
            end
            return true
        end)
        return not alreadyProcessed
    end)
    if not ok then
        return Enum.ProductPurchaseDecision.NotProcessedYet
    end
    return Enum.ProductPurchaseDecision.PurchaseGranted
end

Players.PlayerAdded:Connect(function(player: Player)
    playerConnections[player] = {}
    local charConn = player.CharacterAdded:Connect(function(_char: Model)
        local hb = RunService.Heartbeat:Once(function() end)
        table.insert(playerConnections[player], hb)
    end)
    table.insert(playerConnections[player], charConn)
end)

Players.PlayerRemoving:Connect(function(player: Player)
    lastRequest[player] = nil
    for _, conn in playerConnections[player] or {} do
        conn:Disconnect()
    end
    playerConnections[player] = nil
end)

game:BindToClose(function()
    for player in playerConnections do
        pcall(function()
            store:UpdateAsync("u_" .. tostring(player.UserId), function(prev)
                return prev
            end)
        end)
    end
end)
"""


def _snapshot_tree_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[f.relative_to(root).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


class TestCriticalAuditEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.luau_engine = LuauAuditSnapshotEngine(
            skills_dir=resolve_default_skills_dir(),
            archive_dir=resolve_default_archive_dir(),
        )
        self.audit = CriticalAuditEngine(luau_audit_engine=self.luau_engine)

    def test_bad_luau_fixture_yields_blocker_findings_and_reject(self) -> None:
        res = self.audit.audit_static(luau_sources={"ServerScriptService/BadShop.server.luau": BAD_LUAU_FIXTURE})
        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "REJECT")
        self.assertLess(res["score"], 50)
        self.assertGreaterEqual(res["summary"]["blocker"], 4)
        self.assertGreaterEqual(res["summary"]["critical"], 5)

        ids = {f["id"] for f in res["findings"]}
        for expected_rule in (
            "LUAU-TYPE-001",
            "LUAU-SEC-001",
            "LUAU-SEC-003",
            "LUAU-SEC-005",
            "LUAU-ECO-001",
            "LUAU-ECO-002",
            "LUAU-ECO-003",
            "LUAU-PERF-001",
            "LUAU-PERF-002",
            "LUAU-PERF-003",
            "LUAU-PERF-004",
            "LUAU-PERF-005",
            "LUAU-ANIM-001",
            "LUAU-MEM-001",
            "LUAU-MEM-002",
        ):
            self.assertIn(expected_rule, ids, f"Missing expected finding {expected_rule} in {sorted(ids)}")

        for f in res["findings"]:
            for req_key in ("id", "severity", "domain", "evidence", "why_it_matters", "fix", "auto_fixable"):
                self.assertIn(req_key, f)

    def test_clean_luau_fixture_ignores_comments_strings_and_yields_ship(self) -> None:
        res = self.audit.audit_static(luau_sources={"ServerScriptService/CleanShop.server.luau": CLEAN_LUAU_FIXTURE})
        self.assertTrue(res["ok"])
        self.assertEqual(res["findings"], [], f"Unexpected findings on clean fixture: {res['findings']}")
        self.assertEqual(res["score"], 100)
        self.assertEqual(res["verdict"], "SHIP")

    def test_backtick_interpolation_still_tokenizes_inner_expression(self) -> None:
        src = "--!strict\nlocal s = `time={wait(1)}`\n"
        toks, _ = tokenize_luau(src)
        vals = [t.value for t in toks]
        self.assertIn("wait", vals)
        res = self.audit.audit_static(luau_sources=src)
        self.assertIn("LUAU-PERF-001", {f["id"] for f in res["findings"]})

    def test_gui_anim_world_and_design_lint_checks(self) -> None:
        bad_gui = {
            "viewport": {"x": 800, "y": 480},
            "canvas_group_count": 7,
            "screen_guis": [
                {
                    "name": "HudA",
                    "ScreenInsets": "None",
                    "DisplayOrder": 5,
                    "ZIndexBehavior": "Global",
                    "has_canvas_group": True,
                    "controls": [
                        {
                            "name": "TinyBtn",
                            "interactive": True,
                            "width": 32,
                            "height": 32,
                            "x": 20,
                            "y": 400,
                            "text_scaled": True,
                            "has_text_size_constraint": False,
                            "fg_hex": "#777777",
                            "bg_hex": "#888888",
                        }
                    ],
                },
                {
                    "name": "HudB",
                    "DisplayOrder": 5,
                    "ZIndexBehavior": "Sibling",
                    "controls": [],
                },
            ],
        }
        design_lint = {
            "ok": False,
            "findings": [
                {"id": "SLOP-FLAT-BTN", "severity": "CRITICAL", "evidence": "Flat single-color button without stroke", "fix": "Add UIGradient + UIStroke"},
            ],
        }
        bad_anim = {
            "name": "SwordSlash",
            "loop": True,
            "priority": "Core",
            "frames": [
                {"t": 0.0, "poses": {"RightUpperArm": {"rot_deg": [0.0, 0.0, 0.0]}}},
                {"t": 0.5, "poses": {"RightUpperArm": {"rot_deg": [85.0, 0.0, 0.0]}}},
            ],
        }
        bad_world = {
            "part_count": 20000,
            "precise_collision_count": 15,
            "streaming_enabled": False,
            "unanchored_count": 40,
            "spawn_location_count": 0,
        }
        res = self.audit.audit_static(
            gui_spec=bad_gui,
            design_lint=design_lint,
            anim_clips=bad_anim,
            world_stats=bad_world,
        )
        self.assertEqual(res["verdict"], "REJECT")
        ids = {f["id"] for f in res["findings"]}
        for expected in (
            "GUI-SAFE-001",
            "GUI-SAFE-002",
            "GUI-SAFE-003",
            "GUI-TOUCH-001",
            "GUI-MOBILE-001",
            "GUI-TEXT-001",
            "GUI-CONTRAST-001",
            "GUI-PERF-001",
            "SLOP-FLAT-BTN",
            "ANIM-PRIO-002",
            "ANIM-SEAM-001",
            "WORLD-BUDGET-001",
            "WORLD-COL-001",
            "WORLD-STREAM-001",
            "WORLD-PHYS-001",
            "WORLD-SPAWN-001",
        ):
            self.assertIn(expected, ids, f"Missing {expected} in {sorted(ids)}")

    def test_live_compile_merge_and_challenge_modes(self) -> None:
        luau = self.audit.compile_live_audit_luau(domains=["luau_security"], include_script_sources=True)
        self.assertIn("scriptInventory", luau)
        self.assertIn("worldTelemetry", luau)

        mock_live_report = {
            "ok": True,
            "reports": {
                "luau_security": {
                    "findings": [
                        {
                            "id": "SEC-01",
                            "severity": "FAIL",
                            "path": "ServerStorage.BrokenScript",
                            "message": "Executable Script placed inside ServerStorage",
                            "recommendation": "Move to ServerScriptService",
                        }
                    ]
                }
            },
            "telemetry": {"world": {"partCount": 120, "streamingEnabled": True, "spawnLocationCount": 1}, "gui": {"canvasGroupCount": 1}},
            "scriptInventory": {"scripts": [{"path": "ServerScriptService/Bad.server.luau", "source": "wait(1)\n"}]},
        }
        live_res = self.audit.audit_live(live_report=mock_live_report)
        self.assertTrue(live_res["live_executed"])
        self.assertEqual(live_res["verdict"], "REJECT")
        ids = {f["id"] for f in live_res["findings"]}
        self.assertIn("LIVE-SEC-01", ids)
        self.assertIn("LUAU-PERF-001", ids)

        chal = self.audit.challenge(luau_sources=BAD_LUAU_FIXTURE)
        self.assertTrue(chal["ok"])
        self.assertEqual(set(chal["scenarios_by_axis"].keys()), {"100_players", "phone", "after_rejoin"})
        self.assertGreater(chal["summary"]["confirmed_risks"], 0)

    def test_sec003_property_type_access_and_sec005_clamp_do_not_bypass(self) -> None:
        # Regression for QA Defect #4(a): `payload.type` table access must NOT satisfy LUAU-SEC-003
        spoof_type_src = """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remote = ReplicatedStorage:WaitForChild("ShopRemote") :: RemoteEvent
local cooldowns: { [Player]: number } = {}
Remote.OnServerEvent:Connect(function(player: Player, payload: any)
    cooldowns[player] = os.clock()
    if payload.type == "buy" then
        print(payload.id)
    end
end)
"""
        res_4a = self.audit.audit_static(luau_sources={"ServerScriptService/Shop.server.luau": spoof_type_src})
        ids_4a = {f["id"] for f in res_4a["findings"]}
        self.assertIn("LUAU-SEC-003", ids_4a)
        self.assertEqual(res_4a["verdict"], "REJECT")

        # Regression for QA Defect #4(b): `math.clamp(amount, ...)` must NOT satisfy server authority for LUAU-SEC-005
        spoof_clamp_src = """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local BuyRemote = ReplicatedStorage:WaitForChild("BuyRemote") :: RemoteEvent
local lastUse: { [Player]: number } = {}
BuyRemote.OnServerEvent:Connect(function(player: Player, amount: number)
    lastUse[player] = os.clock()
    if typeof(amount) ~= "number" or not math.isfinite(amount) then
        return
    end
    local safeAmount = math.clamp(amount, 0, 1000000)
    player.leaderstats.Gold.Value += safeAmount
end)
"""
        res_4b = self.audit.audit_static(luau_sources={"ServerScriptService/ClampGold.server.luau": spoof_clamp_src})
        ids_4b = {f["id"] for f in res_4b["findings"]}
        self.assertIn("LUAU-SEC-005", ids_4b)
        self.assertEqual(res_4b["verdict"], "REJECT")

        # Also catch client table field access `payload.amount` even with math.clamp + missing validation
        spoof_payload_amt = """--!strict
local Remote = game:GetService("ReplicatedStorage"):WaitForChild("R") :: RemoteEvent
Remote.OnServerEvent:Connect(function(player: Player, payload: any)
    local now = os.clock()
    if payload.type == "reward" then
        player.leaderstats.Gold.Value += math.clamp(payload.amount, 0, 1000)
    end
end)
"""
        res_4ab = self.audit.audit_static(luau_sources={"ServerScriptService/PayloadGold.server.luau": spoof_payload_amt})
        ids_4ab = {f["id"] for f in res_4ab["findings"]}
        self.assertIn("LUAU-SEC-003", ids_4ab)
        self.assertIn("LUAU-SEC-005", ids_4ab)
        self.assertEqual(res_4ab["verdict"], "REJECT")


class TestGamePlannerAndGating(unittest.TestCase):
    def test_plan_creation_mvp_lock_gating_and_full_progression(self) -> None:
        default_game_dir = SERVER_ROOT / "game_library" / "default_game"
        before_hashes = _snapshot_tree_hashes(default_game_dir)

        with tempfile.TemporaryDirectory(prefix="sharp_planner_test_") as td:
            mgr = ProjectLibraryManager(project_dir=Path(td) / "test_game", project_id="test_game")
            audit_engine = CriticalAuditEngine(project_library=mgr)
            planner = GamePlanner(mgr, audit_engine=audit_engine)

            # Empty project fails PLAN-001 in gate mode
            missing_plan_audit = audit_engine.audit_gate(stage_id="S0")
            self.assertFalse(missing_plan_audit["gate_passed"])
            self.assertIn("PLAN-001", {f["id"] for f in missing_plan_audit["findings"]})

            created = planner.create_plan(
                title="SkyBlade Arena",
                genre="Action Arena",
                pitch="Fast 3-minute sword duels on floating ruins",
                audience="Ages 13+ competitive Roblox players",
                session_length_min=10,
                monetization="Cosmetic Blades + VIP Pass",
                platforms=["Desktop", "Mobile", "Console"],
            )
            self.assertTrue(created["ok"])
            self.assertTrue(mgr.plan_json_path.exists())
            plan_md = mgr.plan_md_path.read_text(encoding="utf-8")
            for required_section in (
                "Design Pillars",
                "Core Loop",
                "MVP Scope",
                "Cut List",
                "Systems Dependency DAG",
                "Risk Register",
                "Asset & Performance Budget",
                "Stage Gates & Acceptance Criteria",
            ):
                self.assertIn(required_section, plan_md)

            # Check next_step returns exactly ONE step (S0.1)
            step0 = planner.next_step()
            self.assertTrue(step0["ok"])
            self.assertEqual(step0["step_id"], "S0.1")
            self.assertFalse(step0["mvp_unlocked"])

            # Premature / spoofed / unattested / bad-audit complete_step attempts MUST BE REFUSED
            self.assertFalse(planner.complete_step("S0.1", {})["ok"])
            self.assertFalse(planner.complete_step("S0.1", {"audit_passed": True, "snapshot_taken": True})["ok"])
            forged_ship = planner.complete_step(
                "S0.1",
                {
                    "snapshot_taken": True,
                    "audit_report": {"findings": [], "verdict": "SHIP", "score": 100},
                },
            )
            self.assertFalse(forged_ship["ok"])
            self.assertIn("UNATTESTED_AUDIT_REPORT", {c["code"] for c in forged_ship["failed_checks"]})

            bad_audit = audit_engine.audit_static(luau_sources=BAD_LUAU_FIXTURE)
            bad_res = planner.complete_step("S0.1", {"audit_report": bad_audit, "snapshot_taken": True})
            self.assertFalse(bad_res["ok"])
            self.assertEqual(bad_res["error_code"], "GATE_EVIDENCE_REJECTED")

            # Empty-scope audit_static() (0 scripts & 0 domains) cannot bypass gate
            empty_audit = audit_engine.audit_static()
            empty_res = planner.complete_step("S0.1", {"audit_report": empty_audit, "snapshot_taken": True})
            self.assertFalse(empty_res["ok"])
            self.assertIn("EMPTY_AUDIT_SCOPE", {c["code"] for c in empty_res["failed_checks"]})

            # Missing snapshot refused even with clean audit
            clean_audit = audit_engine.audit_static(luau_sources=CLEAN_LUAU_FIXTURE)
            self.assertEqual(clean_audit["verdict"], "SHIP")
            no_snap = planner.complete_step("S0.1", {"audit_report": clean_audit})
            self.assertFalse(no_snap["ok"])

            # Tampered audit_report (mutated verdict/findings) is rejected by HMAC attestation
            tampered_audit = {**bad_audit, "verdict": "SHIP", "score": 100, "findings": []}
            tampered_res = planner.complete_step("S0.1", {"audit_report": tampered_audit, "snapshot_taken": True})
            self.assertFalse(tampered_res["ok"])
            self.assertIn("UNATTESTED_AUDIT_REPORT", {c["code"] for c in tampered_res["failed_checks"]})

            # Out-of-order S1.1 before S0.1 refused
            ooo = planner.complete_step(
                "S1.1",
                {
                    "audit_report": clean_audit,
                    "world_stats": {"spawn_location_count": 1, "part_count": 20, "streaming_enabled": True},
                    "snapshot_taken": True,
                },
            )
            self.assertFalse(ooo["ok"])
            self.assertEqual(ooo["error_code"], "STAGE_ORDER_LOCKED")

            # MVP-first lock: S3, S5, S6 strictly refused before S0-S2 + minimal S4 HUD pass
            for locked_id in ("S3.1", "S3", "S5.1", "S5", "S6.1", "S6"):
                refused = planner.complete_step(locked_id, {"audit_report": clean_audit, "snapshot_taken": True})
                self.assertFalse(refused["ok"])
                self.assertEqual(refused["error_code"], "MVP_LOCKED", f"Expected MVP_LOCKED for {locked_id}, got {refused}")

            # Advance S0.1 -> S1.1 -> S2.1 cleanly
            self.assertTrue(planner.complete_step("S0.1", {"audit_report": clean_audit, "snapshot_taken": True})["ok"])
            self.assertEqual(planner.next_step()["step_id"], "S1.1")

            # Regression for QA Defect #3(b): S1.1 refuses bare spawn_verified/bounds_verified booleans without world telemetry
            bare_s1 = planner.complete_step(
                "S1.1",
                {"audit_report": clean_audit, "spawn_verified": True, "bounds_verified": True, "snapshot_taken": True},
            )
            self.assertFalse(bare_s1["ok"])
            self.assertIn("MISSING_WORLD_EVIDENCE", {c["code"] for c in bare_s1["failed_checks"]})

            # Regression for QA Defect #3(a): REJECT audit_report MUST NEVER be overwritten when clean luau_sources are also supplied
            reject_merge = planner.complete_step(
                "S1.1",
                {
                    "snapshot_taken": True,
                    "world_stats": {"spawn_location_count": 1, "part_count": 24, "streaming_enabled": True},
                    "audit_report": {"findings": [], "verdict": "REJECT", "score": 85},
                    "luau_sources": {"Clean.luau": "--!strict\nlocal x: number = 1\nreturn x\n"},
                },
            )
            self.assertFalse(reject_merge["ok"])
            self.assertIn("AUDIT_VERDICT_REJECTED", {c["code"] for c in reject_merge["failed_checks"]})

            self.assertTrue(
                planner.complete_step(
                    "S1.1",
                    {
                        "audit_report": clean_audit,
                        "world_stats": {"spawn_location_count": 1, "part_count": 24, "streaming_enabled": True},
                        "snapshot_taken": True,
                    },
                )["ok"]
            )
            self.assertEqual(planner.next_step()["step_id"], "S2.1")

            # Regression for QA Defect #3(b): S2.1 refuses bare playtest_passed=True / playtest_scenario="smoke"
            no_pt = planner.complete_step("S2.1", {"audit_report": clean_audit, "snapshot_taken": True})
            self.assertFalse(no_pt["ok"])
            bare_pt = planner.complete_step(
                "S2.1",
                {"audit_report": clean_audit, "playtest_passed": True, "playtest_scenario": "smoke", "snapshot_taken": True},
            )
            self.assertFalse(bare_pt["ok"])
            self.assertIn("MISSING_PLAYTEST_REPORT", {c["code"] for c in bare_pt["failed_checks"]})

            self.assertTrue(
                planner.complete_step(
                    "S2.1",
                    {
                        "audit_report": clean_audit,
                        "playtest_report": {
                            "ok": True,
                            "passed": True,
                            "scenario": "full_slice_bot",
                            "checks": ["spawn_valid", "loop_win", "reset_clean"],
                        },
                        "snapshot_taken": True,
                    },
                )["ok"]
            )

            # Next step MUST be S4.1 (minimal HUD), and S3/S5/S6 MUST STILL BE LOCKED until S4.1 passes!
            self.assertEqual(planner.next_step()["step_id"], "S4.1")
            self.assertEqual(
                planner.complete_step("S3.1", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})["error_code"],
                "MVP_LOCKED",
            )

            # S4.1 refuses if design_system missing
            no_ds = planner.complete_step("S4.1", {"audit_report": clean_audit, "snapshot_taken": True})
            self.assertFalse(no_ds["ok"])

            # Complete S4.1 with design_system slot -> MVP unlocks!
            sample_ds = {
                "seed": "skyblade_arena_v1",
                "harmony": "triadic",
                "palette": {"bg_deep": "#12101A", "primary": "#FF5722", "accent": "#00E5FF", "text": "#F8FAFC"},
            }
            s4_min = planner.complete_step(
                "S4.1",
                {"audit_report": clean_audit, "design_system": sample_ds, "snapshot_taken": True},
            )
            self.assertTrue(s4_min["ok"], s4_min)
            self.assertTrue(s4_min["mvp_unlocked"])
            self.assertIsNotNone(mgr.get_design_system())

            # Now S3.1 unlocks, refuses fake asset_registered=True AND refuses dummy/nonexistent asset entries!
            self.assertEqual(planner.next_step()["step_id"], "S3.1")
            fake_asset = planner.complete_step("S3.1", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})
            self.assertFalse(fake_asset["ok"])
            mgr.register_asset(name="DummyMissing", category="animation", roblox_asset_id="dummy", local_path="nonexistent/fake.fbx")
            dummy_asset_res = planner.complete_step("S3.1", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})
            self.assertFalse(dummy_asset_res["ok"])
            self.assertIn("ASSET_NOT_REGISTERED_IN_MANIFEST", {c["code"] for c in dummy_asset_res["failed_checks"]})

            # Register real rig/anim asset -> S3.1 passes
            mgr.register_asset(name="SkyBladeSlash", category="animation", roblox_asset_id="rbxassetid://112233")
            self.assertTrue(planner.complete_step("S3.1", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})["ok"])

            # Register GUI asset -> S4.2 passes
            self.assertEqual(planner.next_step()["step_id"], "S4.2")
            mgr.register_asset(name="ArenaPanel9Slice", category="gui_9slice", roblox_asset_id="rbxassetid://445566")
            self.assertTrue(planner.complete_step("S4.2", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})["ok"])

            # S5.1 Economy passes
            self.assertEqual(planner.next_step()["step_id"], "S5.1")
            self.assertTrue(planner.complete_step("S5.1", {"audit_report": clean_audit, "snapshot_taken": True})["ok"])

            # S6.1 Audio/VFX passes after registering sfx
            self.assertEqual(planner.next_step()["step_id"], "S6.1")
            mgr.register_asset(name="BladeHitSFX", category="sfx", roblox_asset_id="rbxassetid://778899")
            self.assertTrue(planner.complete_step("S6.1", {"audit_report": clean_audit, "asset_registered": True, "snapshot_taken": True})["ok"])

            # S7.1 Release-hardening rejects FIX_FIRST (real attested audit missing --!strict) and requires SHIP
            fix_first_audit = audit_engine.audit_static(luau_sources={"ServerScriptService/NoStrict.server.luau": "local x = 1\nreturn x\n"})
            self.assertEqual(fix_first_audit["verdict"], "FIX_FIRST")
            s7_reject = planner.complete_step(
                "S7.1",
                {
                    "audit_report": fix_first_audit,
                    "playtest_report": {
                        "ok": True,
                        "passed": True,
                        "scenario": "full_slice_bot",
                        "checks": ["join", "combat", "rejoin"],
                    },
                    "snapshot_taken": True,
                },
            )
            self.assertFalse(s7_reject["ok"])

            # Real gate check on project + clean Luau yields SHIP and completes S7.1
            ship_gate = audit_engine.audit_gate(
                stage_id="S7",
                step_id="S7.1",
                luau_sources={"ServerScriptService/Main.server.luau": CLEAN_LUAU_FIXTURE},
            )
            self.assertTrue(ship_gate["gate_passed"], ship_gate)
            self.assertEqual(ship_gate["verdict"], "SHIP")
            self.assertTrue(
                planner.complete_step(
                    "S7.1",
                    {
                        "audit_report": ship_gate,
                        "playtest_report": {
                            "ok": True,
                            "passed": True,
                            "scenario": "full_slice_bot",
                            "checks": ["join", "combat", "save", "rejoin"],
                        },
                        "snapshot_taken": True,
                    },
                )["ok"]
            )
            self.assertTrue(planner.next_step()["completed"])

            # Cross-check test: plan says feature "ClanWars" is required, no system/code implements it -> XCHK-001
            plan_doc = mgr.load_plan()
            plan_doc["features"] = ["ClanWars"]
            mgr.save_plan(plan_doc)
            xchk = audit_engine.audit_static(luau_sources={"Main.server.luau": CLEAN_LUAU_FIXTURE})
            self.assertIn("XCHK-001", {f["id"] for f in xchk["findings"]})

        after_hashes = _snapshot_tree_hashes(default_game_dir)
        self.assertEqual(before_hashes, after_hashes, "Tests must never mutate game_library/default_game!")
        self.assertEqual(len(after_hashes), 13)


class TestSkillMirrorAndHygiene(unittest.TestCase):
    def test_roblox_luau_coding_three_way_mirror_parity_and_clean_runtime(self) -> None:
        live = Path.home() / ".gemini" / "config" / "skills" / "roblox-luau-coding"
        desktop = REPO_ROOT / "04_roblox_luau_coding" / "skill"
        bundled = SERVER_ROOT / "sharp_mcp" / "bundled_skills" / "roblox-luau-coding"

        for root in (live, desktop):
            if not root.is_dir():
                self.skipTest(f"External skill mirror not installed: {root}")

        for root in (live, desktop, bundled):
            self.assertTrue(root.is_dir(), f"Missing skill dir: {root}")
            self.assertEqual(list(root.rglob("__pycache__")), [], f"__pycache__ found in {root}")
            self.assertTrue((root / "references" / "audit_rules_catalog.md").is_file())

        h_live = _snapshot_tree_hashes(live)
        h_desk = _snapshot_tree_hashes(desktop)
        h_bund = _snapshot_tree_hashes(bundled)
        self.assertEqual(h_live, h_desk, "Live vs Desktop roblox-luau-coding parity mismatch")
        self.assertEqual(h_live, h_bund, "Live vs bundled_skills roblox-luau-coding parity mismatch")

        # Check zero Forge / Mixar / personal user path in new runtime modules & skill
        for p in (
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "game_planner.py",
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "critical_audit_engine.py",
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "luau_audit_engine.py",
            SERVER_ROOT / "sharp_mcp" / "domain_engines" / "terrain_env_engine.py",
            *(f for f in live.rglob("*") if f.is_file()),
        ):
            txt = p.read_text(encoding="utf-8")
            self.assertNotIn("Forge", txt, f"Stray 'Forge' in {p}")
            self.assertNotIn("Mixar", txt, f"Stray 'Mixar' in {p}")
            self.assertNotIn("willy", txt.lower(), f"Stray 'willy' in {p}")

    def test_roblox_terrain_atmosphere_three_way_mirror_parity(self) -> None:
        live = Path.home() / ".gemini" / "config" / "skills" / "roblox-terrain-atmosphere"
        desktop = REPO_ROOT / "03_roblox_terrain_atmosphere" / "skill"
        bundled = SERVER_ROOT / "sharp_mcp" / "bundled_skills" / "roblox-terrain-atmosphere"

        for root in (live, desktop):
            if not root.is_dir():
                self.skipTest(f"External skill mirror not installed: {root}")

        for root in (live, desktop, bundled):
            self.assertTrue(root.is_dir(), f"Missing skill dir: {root}")
            self.assertEqual(list(root.rglob("__pycache__")), [], f"__pycache__ found in {root}")
            self.assertTrue((root / "scripts" / "terrain_chunked_builder.luau").is_file())

        h_live = _snapshot_tree_hashes(live)
        h_desk = _snapshot_tree_hashes(desktop)
        h_bund = _snapshot_tree_hashes(bundled)
        self.assertEqual(h_live, h_desk, "Live vs Desktop roblox-terrain-atmosphere parity mismatch")
        self.assertEqual(h_live, h_bund, "Live vs bundled_skills roblox-terrain-atmosphere parity mismatch")


class TestSystemContractsAndCustomTerrainV05(unittest.TestCase):
    def setUp(self) -> None:
        self.skills = resolve_default_skills_dir()
        self.archive = resolve_default_archive_dir()
        self.luau_engine = LuauAuditSnapshotEngine(self.skills, self.archive)
        self.audit = CriticalAuditEngine(luau_audit_engine=self.luau_engine)
        self.terrain_engine = TerrainEnvironmentEngine(self.skills, self.archive)

    def test_compile_system_contracts_and_smoke_test_luau(self) -> None:
        contracts_spec = {
            "remotes": [
                {"name": "SwingSword", "kind": "RemoteEvent", "direction": "ClientToServer", "rate_limit": 4},
                {"name": "DamagePopup", "kind": "RemoteEvent", "direction": "ServerToClient"},
                {"name": "FetchLoadout", "kind": "RemoteFunction", "direction": "ClientToServer"},
            ],
            "tags": {"Enemy": "SharpEnemy", "Interactable": "SharpInteractable"},
            "modules": {
                "CombatConfig": {
                    "path": "ReplicatedStorage.Shared.CombatConfig",
                    "exports": ["CalcDamage", "BASE_DAMAGE"],
                    "role": "shared",
                }
            },
        }
        contracts_installer = self.luau_engine.compile_system_contracts_luau(contracts_spec)
        self.assertIn("--!strict", contracts_installer)
        self.assertIn("SystemContracts", contracts_installer)
        self.assertIn("SwingSword", contracts_installer)
        self.assertIn("FetchLoadout", contracts_installer)
        self.assertIn("SharpEnemy", contracts_installer)
        self.assertIn("CombatConfig", contracts_installer)

        embedded = [m[1] for m in re.findall(r"\[(=*)\[(.*?)\]\1\]", contracts_installer, re.S) if "--!strict" in m[1]]
        self.assertEqual(len(embedded), 1)
        embedded_mod = embedded[0]
        self.assertTrue(embedded_mod.lstrip().startswith("--!strict"))
        self.assertIn("table.freeze", embedded_mod)

        # Both the installer and the embedded SystemContracts module must pass CriticalAuditEngine cleanly
        audit_installer = self.audit.audit_static(luau_sources={"ServerScriptService/InstallContracts.server.luau": contracts_installer})
        self.assertEqual(audit_installer["findings"], [], f"Installer audit failed: {audit_installer['findings']}")
        audit_mod = self.audit.audit_static(luau_sources={"ReplicatedStorage/Shared/SystemContracts.luau": embedded_mod})
        self.assertEqual(audit_mod["findings"], [], f"SystemContracts module audit failed: {audit_mod['findings']}")

        smoke_luau = self.luau_engine.compile_smoke_test_luau()
        self.assertTrue(smoke_luau.lstrip().startswith("--!strict"))
        for container in ("ReplicatedStorage", "ServerScriptService", "StarterPlayerScripts"):
            self.assertIn(container, smoke_luau)
        self.assertIn("pcall(require, entry.mod)", smoke_luau)
        audit_smoke = self.audit.audit_static(luau_sources={"ServerScriptService/SmokeTest.luau": smoke_luau})
        self.assertEqual(audit_smoke["findings"], [], f"Smoke test Luau audit failed: {audit_smoke['findings']}")

    def test_verify_system_contracts_catches_all_four_cross_script_failures(self) -> None:
        # 1. CONTRACT-REQ-001: broken require target path
        broken_req_sources = {
            "ReplicatedStorage/Shared/RealMod.luau": "--!strict\nlocal RealMod = {}\nfunction RealMod.Ping(): number\n\treturn 1\nend\nreturn RealMod\n",
            "ServerScriptService/Boot.server.luau": (
                "--!strict\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local Missing = require(ReplicatedStorage.Shared.DoesNotExist)\n"
                "local _n = Missing.Ping()\n"
            ),
        }
        res_req = self.audit.verify_system_contracts(broken_req_sources)
        self.assertFalse(res_req["passed"])
        self.assertIn("CONTRACT-REQ-001", {f["id"] for f in res_req["findings"]})

        # 2. CONTRACT-EXPORT-001: caller invokes Mod.MissingMethod / Mod:MissingMethod
        broken_export_sources = {
            "ReplicatedStorage/Shared/CombatUtil.luau": (
                "--!strict\n"
                "local CombatUtil = {}\n"
                "function CombatUtil.CalcDamage(base: number): number\n"
                "\treturn base * 2\n"
                "end\n"
                "return CombatUtil\n"
            ),
            "ServerScriptService/CombatMain.server.luau": (
                "--!strict\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local CombatUtil = require(ReplicatedStorage:WaitForChild('Shared', 5):WaitForChild('CombatUtil', 5))\n"
                "local dmg = CombatUtil.DealDamageMissing(25)\n"
                "local crit = CombatUtil:RollCritMissing()\n"
                "print(dmg, crit)\n"
            ),
        }
        res_exp = self.audit.verify_system_contracts(broken_export_sources)
        self.assertFalse(res_exp["passed"])
        exp_findings = [f for f in res_exp["findings"] if f["id"] == "CONTRACT-EXPORT-001"]
        self.assertEqual(len(exp_findings), 2, exp_findings)

        # 3. CONTRACT-NET-001: FireServer / FireClient / InvokeServer mismatches
        broken_net_sources = {
            "ServerScriptService/NetServer.server.luau": (
                "--!strict\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local Remotes = ReplicatedStorage:WaitForChild('Remotes', 5)\n"
                "local SwingEvent = Remotes:WaitForChild('SwingSword', 5) :: RemoteEvent\n"
                "local NotifyEvent = Remotes:WaitForChild('NotifyHit', 5) :: RemoteEvent\n"
                "SwingEvent.OnServerEvent:Connect(function(player: Player) end)\n"
                "NotifyEvent:FireAllClients({ ok = true })\n"
            ),
            "StarterPlayer/StarterPlayerScripts/NetClient.client.luau": (
                "--!strict\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local Remotes = ReplicatedStorage:WaitForChild('Remotes', 5)\n"
                "local TypoSwing = Remotes:WaitForChild('SwingSwordsTypo', 5) :: RemoteEvent\n"
                "local ShopFunc = Remotes:WaitForChild('GetShopItems', 5) :: RemoteFunction\n"
                "TypoSwing:FireServer()\n"
                "local _items = ShopFunc:InvokeServer()\n"
            ),
        }
        res_net = self.audit.verify_system_contracts(broken_net_sources)
        self.assertFalse(res_net["passed"])
        net_findings = [f for f in res_net["findings"] if f["id"] == "CONTRACT-NET-001"]
        self.assertEqual(len(net_findings), 3, net_findings)  # FireServer typo, FireAllClients unconsumed, InvokeServer missing OnServerInvoke

        # 4. CONTRACT-LIFECYCLE-001: PlayerAdded without GetPlayers() AND per-player state without PlayerRemoving
        broken_lifecycle_sources = {
            "ServerScriptService/PlayerBoot.server.luau": (
                "--!strict\n"
                "local Players = game:GetService('Players')\n"
                "local cooldowns: { [Player]: number } = {}\n"
                "Players.PlayerAdded:Connect(function(player: Player)\n"
                "\tcooldowns[player] = os.clock()\n"
                "end)\n"
            ),
            "StarterPlayer/StarterPlayerScripts/ClientBoot.client.luau": (
                "--!strict\n"
                "local ready: boolean = true\n"
                "print(ready)\n"
            ),
        }
        res_life = self.audit.verify_system_contracts(broken_lifecycle_sources)
        self.assertFalse(res_life["passed"])
        life_findings = [f for f in res_life["findings"] if f["id"] == "CONTRACT-LIFECYCLE-001"]
        self.assertEqual(len(life_findings), 2, life_findings)

        # audit_static automatically enables verify_contracts when >= 2 scripts are present
        static_auto = self.audit.audit_static(luau_sources=broken_net_sources)
        self.assertIn("contracts", static_auto["summary"]["domains_audited"])
        self.assertIn("CONTRACT-NET-001", {f["id"] for f in static_auto["findings"]})

        static_disabled = self.audit.audit_static(luau_sources=broken_net_sources, verify_contracts=False)
        self.assertNotIn("CONTRACT-NET-001", {f["id"] for f in static_disabled["findings"]})

    def test_verify_system_contracts_passes_on_valid_modular_system_and_audit_live(self) -> None:
        contracts_installer = self.luau_engine.compile_system_contracts_luau({
            "remotes": [
                {"name": "SwingSword", "kind": "RemoteEvent"},
                {"name": "DamagePopup", "kind": "RemoteEvent"},
                {"name": "FetchLoadout", "kind": "RemoteFunction"},
            ],
            "tags": ["SharpEnemy"],
            "modules": {
                "CombatConfig": {
                    "path": "ReplicatedStorage.Shared.CombatConfig",
                    "exports": ["CalcDamage", "MAX_RANGE"],
                }
            },
        })
        contracts_src = [m[1] for m in re.findall(r"\[(=*)\[(.*?)\]\1\]", contracts_installer, re.S) if "--!strict" in m[1]][0]

        valid_sources = {
            "ReplicatedStorage/Shared/SystemContracts.luau": contracts_src,
            "ReplicatedStorage/Shared/CombatConfig.luau": (
                "--!strict\n"
                "local CombatConfig = {}\n"
                "CombatConfig.MAX_RANGE = 12\n"
                "function CombatConfig.CalcDamage(base: number): number\n"
                "\treturn math.clamp(base, 1, 100)\n"
                "end\n"
                "return CombatConfig\n"
            ),
            "ServerScriptService/CombatServer.server.luau": (
                "--!strict\n"
                "local Players = game:GetService('Players')\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local SystemContracts = require(ReplicatedStorage:WaitForChild('Shared', 5):WaitForChild('SystemContracts', 5))\n"
                "local CombatConfig = require(ReplicatedStorage.Shared.CombatConfig)\n"
                "local Remotes = SystemContracts.GetRemotesFolder(5) :: Folder\n"
                "local SwingEvent = Remotes:WaitForChild('SwingSword', 5) :: RemoteEvent\n"
                "local PopupEvent = Remotes:WaitForChild('DamagePopup', 5) :: RemoteEvent\n"
                "local LoadoutFunc = Remotes:WaitForChild('FetchLoadout', 5) :: RemoteFunction\n"
                "local cooldowns: { [Player]: number } = {}\n"
                "local function onPlayerAdded(player: Player)\n"
                "\tcooldowns[player] = 0\n"
                "end\n"
                "for _, existing in ipairs(Players:GetPlayers()) do\n"
                "\tonPlayerAdded(existing)\n"
                "end\n"
                "Players.PlayerAdded:Connect(onPlayerAdded)\n"
                "Players.PlayerRemoving:Connect(function(player: Player)\n"
                "\tcooldowns[player] = nil\n"
                "end)\n"
                "SwingEvent.OnServerEvent:Connect(function(player: Player, targetId: unknown)\n"
                "\tif typeof(targetId) ~= 'string' then return end\n"
                "\tlocal now = os.clock()\n"
                "\tif cooldowns[player] and (now - cooldowns[player]) < 0.25 then return end\n"
                "\tcooldowns[player] = now\n"
                "\tlocal dmg = CombatConfig.CalcDamage(20)\n"
                "\tPopupEvent:FireClient(player, dmg)\n"
                "end)\n"
                "LoadoutFunc.OnServerInvoke = function(player: Player, slot: unknown)\n"
                "\tif typeof(slot) ~= 'number' then return nil end\n"
                "\treturn { range = CombatConfig.MAX_RANGE }\n"
                "end\n"
            ),
            "StarterPlayer/StarterPlayerScripts/CombatClient.client.luau": (
                "--!strict\n"
                "local ReplicatedStorage = game:GetService('ReplicatedStorage')\n"
                "local CombatConfig = require(ReplicatedStorage:WaitForChild('Shared', 5):WaitForChild('CombatConfig', 5))\n"
                "local Remotes = ReplicatedStorage:WaitForChild('Remotes', 5)\n"
                "local SwingEvent = Remotes:WaitForChild('SwingSword', 5) :: RemoteEvent\n"
                "local PopupEvent = Remotes:WaitForChild('DamagePopup', 5) :: RemoteEvent\n"
                "local LoadoutFunc = Remotes:WaitForChild('FetchLoadout', 5) :: RemoteFunction\n"
                "PopupEvent.OnClientEvent:Connect(function(dmg: number)\n"
                "\tprint(dmg, CombatConfig.MAX_RANGE)\n"
                "end)\n"
                "local _loadout = LoadoutFunc:InvokeServer(1)\n"
                "SwingEvent:FireServer('Dummy')\n"
            ),
        }
        contract_res = self.audit.verify_system_contracts(valid_sources)
        self.assertTrue(contract_res["passed"], f"Expected valid modular system to pass: {contract_res['findings']}")
        self.assertEqual(contract_res["findings"], [])
        self.assertEqual(contract_res["verdict"], "SHIP")
        self.assertEqual(contract_res["score"], 100)

        full_static = self.audit.audit_static(luau_sources=valid_sources)
        self.assertEqual(full_static["findings"], [], f"Expected full audit SHIP: {full_static['findings']}")
        self.assertEqual(full_static["verdict"], "SHIP")
        self.assertEqual(full_static["score"], 100)
        self.assertIn("contracts", full_static["summary"]["domains_audited"])

        # Also test audit_live integration with >= 2 scripts in scriptInventory
        live_rep = {
            "ok": True,
            "reports": {"luau_security": {"findings": []}, "gui": {"errors": [], "warnings": []}, "environment": {"errors": [], "warnings": []}},
            "telemetry": {"world": {"partCount": 10, "streamingEnabled": True, "spawnLocationCount": 1}, "gui": {"canvasGroupCount": 1}},
            "scriptInventory": {
                "scripts": [{"path": p, "source": s} for p, s in valid_sources.items()]
            },
        }
        live_res = self.audit.audit_live(live_report=live_rep)
        self.assertEqual(live_res["verdict"], "SHIP", live_res["findings"])
        self.assertIn("contracts", live_res["summary"]["domains_audited"])

    def test_custom_terrain_spec_and_custom_atmosphere(self) -> None:
        custom_spec = {
            "biome": "Volcanic",
            "noise_weight": 0.65,
            "height_layers": [
                {"type": "crater", "x": 0, "z": 0, "radius": 48, "depth": 28, "rimHeight": 14, "material": "Basalt"},
                {
                    "type": "river",
                    "points": [{"x": -120, "z": -60}, {"x": -40, "z": 10}, {"x": 80, "z": 90}],
                    "width": 18,
                    "depth": 14,
                    "waterFill": True,
                },
                {"type": "ridge", "x1": -90, "z1": 40, "x2": 90, "z2": -40, "width": 22, "height": 34},
                {"type": "terrace", "x": 60, "z": -60, "radius": 50, "stepHeight": 8},
                {"type": "plateau", "x": -70, "z": 70, "radius": 32, "height": 104, "material": "Slate"},
            ],
            "material_rules": [
                {"minY": 115, "material": "CrackedLava"},
                {"minSlope": 0.65, "material": "Rock"},
                {"x": 0, "z": 0, "maxRadius": 28, "material": "Basalt"},
            ],
        }
        terrain_luau = self.terrain_engine.compile_terrain_build_luau(
            min_corner=[-128, -32, -128],
            max_corner=[128, 160, 128],
            custom_terrain_spec=custom_spec,
        )
        for token in (
            "ApplyHeightLayers",
            "ResolveMaterialRules",
            "heightLayers",
            "materialRules",
            '"crater"',
            '"river"',
            '"ridge"',
            '"terrace"',
            '"plateau"',
            "Enum.Material.CrackedLava",
            "Enum.Material.Basalt",
            "Enum.Material.Slate",
            "waterFill = true",
        ):
            self.assertIn(token, terrain_luau)

        toks, dirs = tokenize_luau(terrain_luau)
        self.assertIn("--!strict", dirs)
        self.assertGreater(len(toks), 100)
        builder_path = self.skills / "roblox-terrain-atmosphere" / "scripts" / "terrain_chunked_builder.luau"
        b_src = builder_path.read_text(encoding="utf-8")
        b_toks, b_dirs = tokenize_luau(b_src)
        self.assertIn("--!strict", b_dirs)
        self.assertGreater(len(b_toks), 100)
        self.assertIn("Canyon =", b_src)
        self.assertIn("regionMin = { X = regionMin.X, Y = regionMin.Y, Z = regionMin.Z }", b_src)

        # Case-insensitive contracts_spec keys (PascalCase Remotes/Tags/Modules)
        pascal_installer = self.luau_engine.compile_system_contracts_luau(
            {"Remotes": {"FireRailgun": {"direction": "C2S"}}, "Tags": ["MechTarget"], "Modules": {"Weapons": ["Fire"]}}
        )
        self.assertIn('name = "FireRailgun"', pascal_installer)
        self.assertIn('["MechTarget"] = "MechTarget"', pascal_installer)
        pascal_check = self.audit.verify_system_contracts(
            {
                "StarterPlayerScripts/Test.client.luau": "--!strict\nlocal ReplicatedStorage = game:GetService('ReplicatedStorage')\nReplicatedStorage.Remotes.FireRailgun:FireServer()\n",
                "ServerScriptService/Test.server.luau": "--!strict\nlocal ReplicatedStorage = game:GetService('ReplicatedStorage')\nReplicatedStorage.Remotes.FireRailgun.OnServerEvent:Connect(function(_player) end)\n",
            },
            contracts_spec={"Remotes": {"FireRailgun": {"direction": "C2S"}}},
        )
        self.assertTrue(pascal_check["passed"], f"PascalCase contracts_spec failed: {pascal_check}")

        env_luau = self.terrain_engine.compile_environment_apply_luau(
            preset_name="VolcanicAsh",
            custom_atmosphere={
                "clock_time": 18.2,
                "atmosphere": {"Density": 0.44, "Glare": 1.4, "Haze": 2.2, "Color": "#FFB07A"},
                "clouds": {"Enabled": True, "Cover": 0.72, "Density": 0.8},
                "global_wind": [14, 0, -6],
                "bloom": {"Enabled": True, "Intensity": 0.75},
            },
        )
        self.assertIn("VolcanicAsh", env_luau)
        self.assertIn("18.2", env_luau)
        self.assertIn("ColorCorrectionEffect", env_luau)
        self.assertIn("parseHexColor", env_luau)

    def test_game_planner_v05_subagent_directives(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sharp_v05_plan_") as td:
            mgr = ProjectLibraryManager(project_dir=Path(td) / "v05_game", project_id="v05_game")
            planner = GamePlanner(mgr, audit_engine=self.audit)
            planner.create_plan(title="Ashfall Keep", genre="Action RPG", granularity="micro")

            intake = planner.dispatch_action("intake_questions", title="Ashfall Keep", genre="Action RPG")
            q_dump = str(intake)
            for required_kw in ("TEXTURE_STYLE_PROFILES", "ASSET_STYLE_PROFILES", "ANIMATION_STYLE_PROFILES", "compose_custom", "pose_strip"):
                self.assertIn(required_kw, q_dump)

            for focus, sid in (("auto", "S0.1"), ("auto", "S1.1"), ("auto", "S2.1"), ("auto", "S3.1"), ("auto", "S4.1"), ("art_creation", None)):
                brief = planner.build_subagent_brief(step_id=sid, role_focus=focus)
                self.assertTrue(brief["ok"])
                self.assertIn("workflow_directives", brief)
                self.assertIn("three_tier_art_pipeline", brief["workflow_directives"])
                self.assertIn("selected_style_profiles", brief)

            art_brief = planner.build_subagent_brief(role_focus="art_creation")
            art_txt = str(art_brief)
            for token in (
                "sharp_gui_build(mode='custom')",
                "TEXTURE_STYLE_PROFILES",
                "ASSET_STYLE_PROFILES",
                "ANIMATION_STYLE_PROFILES",
                "compose_custom",
                "pose_strip",
                "custom_bmesh",
                "inspect_attachment_fit",
                "custom_terrain_spec",
                "verify_contracts",
            ):
                self.assertIn(token, art_txt, f"Missing v0.5 directive '{token}' in subagent_brief")

    def test_weapon_pivot_grip_ammo_ik_and_aim_audit_rules(self) -> None:
        bad_aim_src = (
            "--!strict\n"
            "local cam = workspace.CurrentCamera\n"
            "local vp = cam.ViewportSize\n"
            "local r = cam:ViewportPointToRay(vp.X * 0.5, vp.Y * 0.46)\n"
            "local dir = (r.Origin + r.Direction * 120 - Vector3.zero).Unit\n"
        )
        static_res = self.audit.audit_static(luau_sources={"StarterPlayerScripts/Aim.client.luau": bad_aim_src})
        ids = {f["id"] for f in static_res["findings"]}
        self.assertIn("LUAU-AIM-001", ids)

        live_rep = {
            "ok": True,
            "reports": {"luau_security": {"findings": []}, "gui": {"errors": [], "warnings": []}, "environment": {"errors": [], "warnings": []}},
            "telemetry": {
                "world": {"partCount": 10, "streamingEnabled": True, "spawnLocationCount": 1},
                "gui": {"canvasGroupCount": 1},
                "weapons": {
                    "rotatedPivotModels": [{"path": "ReplicatedStorage.Assets.MedievalBolt", "primaryPart": "LeatherGrip", "lookDot": 0.0, "upDot": 0.0}],
                    "brokenLoadedAmmo": ["StarterPack.Crossbow.LoadedBolt.Tip"],
                    "verticalRangedTools": ["StarterPack.Crossbow"],
                    "transformArmIKs": ["Workspace.Hero.Humanoid.RightAimIK"],
                },
            },
        }
        live_res = self.audit.audit_live(live_report=live_rep)
        live_ids = {f["id"] for f in live_res["findings"]}
        for expected in ("WEAPON-PIVOT-001", "WEAPON-AMMO-001", "WEAPON-GRIP-001", "ANIM-IK-001"):
            self.assertIn(expected, live_ids, f"Missing live weapon/IK finding {expected}: {live_ids}")

        compiled = self.luau_engine.compile_critical_audit_luau()
        for tok in ("weaponTelemetry", "rotatedPivotModels", "brokenLoadedAmmo", "verticalRangedTools", "transformArmIKs"):
            self.assertIn(tok, compiled)


if __name__ == "__main__":
    unittest.main()
