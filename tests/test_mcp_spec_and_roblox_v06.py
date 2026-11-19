"""Milestone 1 (v0.6.0) verification tests: MCP spec compliance, context slimming, Roblox modern APIs & pooling."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import time
from typing import Any
import unittest
from unittest.mock import AsyncMock, patch

from mcp import StdioServerParameters
import mcp.types as mcp_types

from sharp_mcp.domain_engines.attachment_engine import AttachmentEngine
from sharp_mcp.domain_engines.critical_audit_engine import CriticalAuditEngine
from sharp_mcp.domain_engines.luau_audit_engine import LuauAuditSnapshotEngine
from sharp_mcp.domain_engines.upstream_multiplexer import StudioMcpSessionPool
from sharp_mcp.mcp_server import SharpMcpApplication, resolve_enabled_tools_for_profile
from sharp_mcp.tool_effects import SnapshotViewStore, build_mcp_result


def _decode_tool_res(raw: Any) -> dict[str, Any]:
    text = raw.content[0].text if hasattr(raw, "content") else str(raw)
    if text.startswith("[UNTRUSTED_PLACE_CONTENT"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return json.loads(text)


class TestMcpSpecComplianceV06(unittest.IsolatedAsyncioTestCase):
    def test_structured_output_error_flag_and_schemas_all_profiles(self) -> None:
        err_res = build_mcp_result({"ok": False, "error": "boom"})
        self.assertIsInstance(err_res, mcp_types.CallToolResult)
        self.assertTrue(err_res.isError)
        self.assertEqual(err_res.structuredContent, {"ok": False, "error": "boom"})

        ok_res = build_mcp_result({"ok": True, "value": 42})
        self.assertFalse(ok_res.isError)
        self.assertEqual(ok_res.structuredContent, {"ok": True, "value": 42})

    async def test_profiles_budgets_output_schemas_resources_and_params(self) -> None:
        lean_names = resolve_enabled_tools_for_profile("lean")
        self.assertEqual(len(lean_names), 10)
        self.assertEqual(len(resolve_enabled_tools_for_profile("full")), 34)
        self.assertEqual(len(resolve_enabled_tools_for_profile("core")), 30)
        self.assertEqual(len(resolve_enabled_tools_for_profile("blender")), 11)

        with tempfile.TemporaryDirectory(prefix="sharp_v06_") as td:
            for profile_name, max_schema_bytes in (("lean", 14336), ("full", 32768)):
                app = SharpMcpApplication(
                    project_dir=td,
                    bridge_port=0,
                    profile=profile_name,
                    start_bridge=False,
                )
                self.assertLess(len(app.server_instructions.encode("utf-8")), 2400)
                tools = await app.mcp.list_tools()
                schema_bytes = len(json.dumps([t.inputSchema for t in tools], separators=(",", ":")).encode("utf-8"))
                self.assertLess(schema_bytes, max_schema_bytes)
                for t in tools:
                    self.assertIsNotNone(t.outputSchema, f"{t.name} missing outputSchema in {profile_name}")
                    self.assertNotIn("title", t.inputSchema)

            full_app = SharpMcpApplication(project_dir=td, bridge_port=0, profile="full", start_bridge=False)
            full_tools = {t.name: t for t in await full_app.mcp.list_tools()}
            # Ensure actual parameter named "title" on sharp_game_plan is preserved
            self.assertIn("title", full_tools["sharp_game_plan"].inputSchema["properties"])

            # Verify sharp://skills/cheatsheet and sharp://views/{view_id} resources
            cheatsheet = await full_app.mcp.read_resource("sharp://skills/cheatsheet")
            cheatsheet_text = "".join(getattr(c, "content", str(c)) for c in cheatsheet)
            self.assertIn("SHARP MCP 5-STEP QUICKSTART", cheatsheet_text)

            stored = full_app.view_store.store({"hello": "world", "arr": [1, 2, 3]}, label="unit", source_tool="sharp_game_library")
            view_id = stored["view_id"]
            self.assertTrue(view_id.startswith("sv_"))
            self.assertGreaterEqual(len(view_id), 20)
            res_view = await full_app.mcp.read_resource(f"sharp://views/{view_id}")
            res_view_text = "".join(getattr(c, "content", str(c)) for c in res_view)
            self.assertIn("world", res_view_text)

            # Error propagation sets CallToolResult.isError = True
            err_plan = full_app.mcp._tool_manager._tools["sharp_game_plan"].fn(
                action="create",
                design_system="{bad json",
            )
            self.assertTrue(err_plan.isError)
            self.assertFalse(_decode_tool_res(err_plan)["ok"])

            # Mega-tool params dict forwarding + flat kwarg backward compatibility
            equip_fn = full_app.mcp._tool_manager._tools["sharp_equipment_attach"].fn
            by_params = _decode_tool_res(
                await equip_fn(
                    action="attach",
                    mode="accessory_rigid",
                    execute_in_studio=False,
                    params={"slot": "back"},
                )
            )
            self.assertTrue(by_params["ok"])
            self.assertEqual(by_params["mode"], "accessory_rigid")
            self.assertIn("BodyBackAttachment", by_params["compiledLuau"])

            by_flat = _decode_tool_res(
                await equip_fn(action="attach", mode="accessory_rigid", slot="back", execute_in_studio=False)
            )
            self.assertTrue(by_flat["ok"])
            self.assertIn("BodyBackAttachment", by_flat["compiledLuau"])

            # Audit mode error
            bad_audit = await full_app.mcp._tool_manager._tools["sharp_critical_audit"].fn(mode="bogus_mode")
            self.assertTrue(bad_audit.isError)

    def test_snapshot_view_store_csprng_and_hmac_cursors(self) -> None:
        store = SnapshotViewStore()
        payload = {"items": [{"idx": i, "text": f"row_{i}_data"} for i in range(40)]}
        v1 = store.store(payload, label="p1", source_tool="test")
        v2 = store.store(payload, label="p2", source_tool="test")
        self.assertTrue(v1["view_id"].startswith("sv_"))
        self.assertNotEqual(v1["view_id"], v2["view_id"])

        page1 = store.inspect(v1["view_id"], offset=0, limit=120)
        self.assertTrue(page1["ok"])
        self.assertTrue(page1["has_more"])
        self.assertIsInstance(page1["cursor"], str)
        self.assertIsInstance(page1["nextCursor"], str)

        page2 = store.inspect(v1["view_id"], cursor=page1["nextCursor"])
        self.assertTrue(page2["ok"])
        self.assertEqual(page2["offset"], 120)
        self.assertEqual(page2["content"], store.inspect(v1["view_id"], offset=120, limit=120)["content"])

        # Tampered signature rejected
        bad_sig = page1["nextCursor"][:-4] + ("AAAA" if page1["nextCursor"][-4:] != "AAAA" else "BBBB")
        rej_sig = store.inspect(v1["view_id"], cursor=bad_sig)
        self.assertFalse(rej_sig["ok"])
        self.assertEqual(rej_sig["code"], "INVALID_CURSOR")

        # Cross-view cursor rejected
        rej_cross = store.inspect(v2["view_id"], cursor=page1["nextCursor"])
        self.assertFalse(rej_cross["ok"])
        self.assertEqual(rej_cross["code"], "INVALID_CURSOR")


class TestRobloxModernApisV06(unittest.TestCase):
    def test_animation_constraint_parity_in_engine_skill_and_audit(self) -> None:
        skills_dir = Path(__file__).resolve().parent.parent / "sharp_mcp" / "bundled_skills"
        eng = AttachmentEngine(skills_dir)
        verify_luau = eng.compile_verify_luau(rig_path="Workspace.Rig")
        self.assertIn('IsA("AnimationConstraint")', verify_luau)
        self.assertIn("dangling_animation_constraint", verify_luau)

        fit_luau = eng.compile_inspect_attachment_fit_luau(rig_path="Workspace.Rig")
        self.assertIn('d:IsA("RigidConstraint") or d:IsA("AnimationConstraint")', fit_luau)

        attach_luau = eng.compile_attach_luau(
            rig_path="Workspace.Rig",
            item_path="Workspace.Sword",
            mode="motor6d_weapon",
            preset="sword",
            joint_mode="animation_constraint",
        )
        self.assertIn('local JOINT_MODE = "animation_constraint"', attach_luau)
        self.assertIn('Instance.new("AnimationConstraint")', attach_luau)

        assembler_path = (
            Path(__file__).resolve().parent.parent
            / "sharp_mcp"
            / "bundled_skills"
            / "roblox-combat-and-controllers"
            / "scripts"
            / "weapon_tool_assembler.luau"
        )
        assembler_src = assembler_path.read_text(encoding="utf-8")
        self.assertIn("AnimationConstraint", assembler_src)
        self.assertIn("Attachment0", assembler_src)

        auditor = CriticalAuditEngine()
        bad_rig_src = "--!strict\nlocal motor: Motor6D = rightShoulder\nRightShoulder.C0 = CFrame.new(0, 1, 0)\n"
        f_ids = {f["id"] for f in auditor.audit_static(luau_sources={"ServerScriptService.Pose": bad_rig_src})["findings"]}
        self.assertIn("ANIM-JOINT-001", f_ids)

        dangling_src = '--!strict\nlocal jc = Instance.new("AnimationConstraint")\njc.Parent = workspace\n'
        f_ids2 = {f["id"] for f in auditor.audit_static(luau_sources={"ServerScriptService.Joint": dangling_src})["findings"]}
        self.assertIn("ANIM-JOINT-002", f_ids2)

        clean_joint_src = (
            "--!strict\n"
            "local jc = Instance.new(\"AnimationConstraint\")\n"
            "jc.Attachment0 = att0\n"
            "jc.Attachment1 = att1\n"
            "jc.Enabled = true\n"
        )
        f_ids_clean = {f["id"] for f in auditor.audit_static(luau_sources={"ServerScriptService.CleanJoint": clean_joint_src})["findings"]}
        self.assertNotIn("ANIM-JOINT-001", f_ids_clean)
        self.assertNotIn("ANIM-JOINT-002", f_ids_clean)

    def test_slim_solver_parallel_profiler_and_optimizer_rules(self) -> None:
        skills_dir = Path(__file__).resolve().parent.parent / "sharp_mcp" / "bundled_skills"
        snap = LuauAuditSnapshotEngine(skills_dir)
        live_luau = snap.compile_critical_audit_luau()
        for tok in (
            "slimCandidateCount",
            "nestedPersistentInAtomicCount",
            "useNewLuauTypeSolver",
            "authorityMode",
            "meshContentCount",
            "meshIdStringCount",
        ):
            self.assertIn(tok, live_luau)

        opt_path = (
            Path(__file__).resolve().parent.parent
            / "sharp_mcp"
            / "bundled_skills"
            / "roblox-world-assembly-and-optimization"
            / "scripts"
            / "scene_budget_optimizer.luau"
        )
        opt_src = opt_path.read_text(encoding="utf-8")
        self.assertIn("ModelLevelOfDetail.SLIM", opt_src)
        self.assertIn(">= 64", opt_src)
        self.assertIn("CollisionFidelity.Box", opt_src)
        self.assertIn("hasAtomicAncestor", opt_src)

        auditor = CriticalAuditEngine()
        world_res = auditor.audit_static(
            world_stats={
                "partCount": 120,
                "slimCandidateCount": 3,
                "nestedPersistentInAtomicCount": 1,
                "meshIdStringCount": 4,
                "meshContentCount": 0,
                "useNewLuauTypeSolver": False,
            }
        )
        world_rules = {f["id"] for f in world_res["findings"]}
        self.assertTrue({"WORLD-SLIM-001", "WORLD-STREAM-002", "WORLD-INST-001", "LUAU-SOLVER-001"}.issubset(world_rules))

        bad_par_and_mesh = (
            "--!strict\n"
            "local mp = workspace:FindFirstChildOfClass('MeshPart')\n"
            "mp.MeshId = 'rbxassetid://1234'\n"
            "task.desynchronize()\n"
            "mp.Position = Vector3.new(1, 2, 3)\n"
            "task.synchronize()\n"
            "RunService.PreSimulation:Connect(function(dt: number)\n"
            "    local x = 1\n"
            "    for i = 1, 10 do\n"
            "        x += i\n"
            "        local r = workspace:Raycast(Vector3.zero, Vector3.new(0, -10, 0))\n"
            "        if r then\n"
            "            x += 1\n"
            "        end\n"
            "    end\n"
            "end)\n"
        )
        s_rules = {f["id"] for f in auditor.audit_static(luau_sources={"ServerScriptService.Par": bad_par_and_mesh})["findings"]}
        self.assertTrue({"WORLD-INST-001", "LUAU-PAR-001", "PERF-PROF-001"}.issubset(s_rules))

        clean_par = (
            "--!strict\n"
            "local mp = workspace:FindFirstChildOfClass('MeshPart')\n"
            "mp.MeshContent = Content.fromUri('rbxassetid://1234')\n"
            "task.desynchronize()\n"
            "local res = workspace:Raycast(Vector3.zero, Vector3.new(0, -5, 0))\n"
            "task.synchronize()\n"
            "if res then\n"
            "    mp.Position = res.Position\n"
            "end\n"
            "RunService.PreSimulation:Connect(function(dt: number)\n"
            "    debug.profilebegin('StepPhysics')\n"
            "    for i = 1, 10 do\n"
            "        local _ = i * dt\n"
            "    end\n"
            "    debug.profileend()\n"
            "end)\n"
        )
        clean_rules = {f["id"] for f in auditor.audit_static(luau_sources={"ServerScriptService.CleanPar": clean_par})["findings"]}
        for unexpected in ("WORLD-INST-001", "LUAU-PAR-001", "PERF-PROF-001", "LUAU-SOLVER-001"):
            self.assertNotIn(unexpected, clean_rules)


class TestStudioMcpSessionPoolV06(unittest.IsolatedAsyncioTestCase):
    async def test_session_reuse_reconnect_ttl_and_aclose(self) -> None:
        created_sessions: list[Any] = []
        fail_first_call = {"flag": False}
        closed_contexts = {"count": 0}

        class FakeSession:
            def __init__(self, idx: int) -> None:
                self.idx = idx
                self.initialized = False
                self.calls = 0

            async def __aenter__(self) -> "FakeSession":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            async def initialize(self) -> None:
                self.initialized = True

            async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
                self.calls += 1
                if fail_first_call["flag"]:
                    fail_first_call["flag"] = False
                    raise ConnectionResetError("transient broken pipe")
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=json.dumps({"ok": True, "session": self.idx, "tool": tool_name}))]
                )

        @asynccontextmanager
        async def fake_client(_params: StdioServerParameters):
            try:
                yield ("r", "w")
            finally:
                closed_contexts["count"] += 1

        def fake_session_factory(_r: Any, _w: Any) -> FakeSession:
            s = FakeSession(len(created_sessions) + 1)
            created_sessions.append(s)
            return s

        pool = StudioMcpSessionPool(
            idle_ttl_sec=120.0,
            client_factory=fake_client,
            session_factory=fake_session_factory,
        )
        params = StdioServerParameters(command="cmd.exe", args=["/c", "echo ok"])

        # 1 & 2: Two calls reuse a single initialized session
        r1 = await pool.call_tool(params, "execute_luau", {"code": "return 1"})
        r2 = await pool.call_tool(params, "execute_luau", {"code": "return 2"})
        self.assertEqual(pool.connect_count, 1)
        self.assertEqual(pool.call_count, 2)
        self.assertEqual(json.loads(r1.content[0].text)["session"], 1)
        self.assertEqual(json.loads(r2.content[0].text)["session"], 1)

        # 3: Transient error closes stale session and reconnects once cleanly
        fail_first_call["flag"] = True
        r3 = await pool.call_tool(params, "execute_luau", {"code": "return 3"})
        self.assertEqual(pool.connect_count, 2)
        self.assertEqual(json.loads(r3.content[0].text)["session"], 2)

        # 4: Idle TTL expiry reconnects on next call
        pool._last_used = time.monotonic() - 500.0
        r4 = await pool.call_tool(params, "execute_luau", {"code": "return 4"})
        self.assertEqual(pool.connect_count, 3)
        self.assertEqual(json.loads(r4.content[0].text)["session"], 3)

        await pool.aclose()
        self.assertEqual(closed_contexts["count"], 3)

        # Verify lifespan closes multiplexer pool
        with tempfile.TemporaryDirectory(prefix="sharp_life_") as td:
            app = SharpMcpApplication(project_dir=td, bridge_port=0, start_bridge=False)
            with patch.object(app.multiplexer, "aclose", new=AsyncMock()) as mock_aclose:
                async with app._lifespan(app.mcp):
                    pass
                self.assertEqual(mock_aclose.await_count, 1)


if __name__ == "__main__":
    unittest.main()
