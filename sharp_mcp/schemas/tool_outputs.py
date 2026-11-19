"""Pydantic v2 output schema definitions for Sharp MCP tool results."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict


class SharpToolEnvelope(BaseModel):
    """Base envelope returned by every Sharp MCP tool."""

    model_config = ConfigDict(extra="allow")

    ok: Optional[bool] = True
    error: Optional[str] = None
    code: Optional[str] = None
    recovery_action: Optional[str] = None


class SkillRouteOutput(SharpToolEnvelope):
    """Structured output for skill routing and skill documentation loading."""

    recommended_skills: Optional[Any] = None
    dag: Optional[Any] = None
    rule_cards: Optional[Any] = None


class StudioExecOutput(SharpToolEnvelope):
    """Structured output for Studio execution, asset generation, and mutation tools."""

    executionMode: Optional[str] = None
    bridgePort: Optional[int] = None
    compiledLuau: Optional[str] = None
    decoded: Optional[Any] = None


class AuditReportOutput(SharpToolEnvelope):
    """Structured output for static, live, contract, and gate audit tools."""

    verdict: Optional[str] = None
    score: Optional[float] = None
    findings: Optional[List[Any]] = None
    summary: Optional[Any] = None


class SnapshotPageOutput(SharpToolEnvelope):
    """Structured output for SnapshotViewStore cursor-paginated inspection."""

    view_id: Optional[str] = None
    offset: Optional[int] = None
    limit: Optional[int] = None
    total_chars: Optional[int] = None
    returned_chars: Optional[int] = None
    has_more: Optional[bool] = None
    next_offset: Optional[int] = None
    cursor: Optional[str] = None
    nextCursor: Optional[str] = None
    content: Optional[str] = None


TOOL_OUTPUT_MODELS: Dict[str, Type[SharpToolEnvelope]] = {
    "sharp_route_task": SkillRouteOutput,
    "sharp_load_skill": SkillRouteOutput,
    "sharp_studio_status": StudioExecOutput,
    "sharp_blender_setup": StudioExecOutput,
    "sharp_terrain_build": StudioExecOutput,
    "sharp_environment_apply": StudioExecOutput,
    "sharp_gui_slice_and_pack": StudioExecOutput,
    "sharp_gui_build": StudioExecOutput,
    "sharp_gui_inspect": StudioExecOutput,
    "sharp_gui_patch": StudioExecOutput,
    "sharp_visual_diff": AuditReportOutput,
    "sharp_rig_and_animation": StudioExecOutput,
    "sharp_blender_rig_and_anim": StudioExecOutput,
    "sharp_blender_asset_pipeline": StudioExecOutput,
    "sharp_luau_scaffold": StudioExecOutput,
    "sharp_audit_all": AuditReportOutput,
    "sharp_snapshot_and_undo": StudioExecOutput,
    "sharp_combat_and_controllers": StudioExecOutput,
    "sharp_audio_vfx_cutscenes": StudioExecOutput,
    "sharp_data_economy_monetization": StudioExecOutput,
    "sharp_ai_and_gameplay_systems": StudioExecOutput,
    "sharp_world_assembly_and_optimization": StudioExecOutput,
    "sharp_game_library": SharpToolEnvelope,
    "sharp_playtest_scenario": StudioExecOutput,
    "sharp_toolchain": SharpToolEnvelope,
    "sharp_inspect_snapshot_view": SnapshotPageOutput,
    "sharp_upstream_call": StudioExecOutput,
    "sharp_design_system": SharpToolEnvelope,
    "sharp_equipment_attach": StudioExecOutput,
    "sharp_game_plan": SharpToolEnvelope,
    "sharp_critical_audit": AuditReportOutput,
    "sharp_ai_studio": StudioExecOutput,
    "sharp_media_qa": AuditReportOutput,
    "sharp_art_studio": StudioExecOutput,
}

_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def get_tool_output_schema(tool_name: str) -> Dict[str, Any]:
    """Return the cached JSON Schema 2020-12 output schema for ``tool_name``."""
    model = TOOL_OUTPUT_MODELS.get(tool_name, SharpToolEnvelope)
    key = model.__name__
    if key not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[key] = model.model_json_schema()
    return dict(_SCHEMA_CACHE[key])
