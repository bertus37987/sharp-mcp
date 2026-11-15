"""Builds the Roblox Studio Companion Plugin (`SharpBridgePlugin.rbxmx`) and installs it.

Bundles:
1. Standalone `--!strict` Luau sources from `studio_plugin/src/`:
   - `init.server.luau` (`SharpBridgePlugin` root `Script`)
   - `SharpUndo.luau` (`ModuleScript`)
   - `DockWidget.luau` (`ModuleScript`)
   - `SharpGuiTools.luau` (`ModuleScript`)
   - `SharpTreeTools.luau` (`ModuleScript`)
2. All 25 embedded `--!strict` skill `ModuleScript`s across the 9 Roblox skills
   (raising `FileNotFoundError` immediately if ANY listed `.luau` source is missing).
3. Writes `SharpBridgePlugin.rbxmx` (29 `ModuleScript` children + root `Script`) and
   optionally installs cross-platform to the native Roblox Plugins directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple


PLUGIN_SRC_MODULES: Tuple[str, ...] = (
    "SharpUndo",
    "DockWidget",
    "SharpGuiTools",
    "SharpTreeTools",
)

SKILL_SCRIPT_MAP: Dict[str, Tuple[str, str]] = {
    "ProbeRig": ("roblox-animation", "probe_rig.luau"),
    "StudioTestAnim": ("roblox-animation", "studio_test_anim.luau"),
    "TerrainChunkedBuilder": ("roblox-terrain-atmosphere", "terrain_chunked_builder.luau"),
    "AtmospherePresets": ("roblox-terrain-atmosphere", "atmosphere_presets.luau"),
    "AuditEnvironment": ("roblox-terrain-atmosphere", "audit_environment.luau"),
    "UIThemeAndComponents": ("roblox-gui", "ui_theme_and_components.luau"),
    "ProjectScaffold": ("roblox-luau-coding", "project_scaffold.luau"),
    "SafeRemoteGateway": ("roblox-luau-coding", "safe_remote_gateway.luau"),
    "ArchitectureSecurityAudit": ("roblox-luau-coding", "architecture_security_audit.luau"),
    "StudioRuntimeSmokeTest": ("roblox-luau-coding", "studio_runtime_smoke_test.luau"),
    "ControllerManagerRig": ("roblox-combat-and-controllers", "controller_manager_rig.luau"),
    "WeaponToolAssembler": ("roblox-combat-and-controllers", "weapon_tool_assembler.luau"),
    "CombatHitboxAndProjectile": ("roblox-combat-and-controllers", "combat_hitbox_and_projectile.luau"),
    "AudioBusGraphBuilder": ("roblox-audio-vfx-cutscenes", "audio_bus_graph_builder.luau"),
    "VfxPresetAndHighlightPool": ("roblox-audio-vfx-cutscenes", "vfx_preset_and_highlight_pool.luau"),
    "CameraShakeAndCutscene": ("roblox-audio-vfx-cutscenes", "camera_shake_and_cutscene.luau"),
    "SessionLockedDataStore": ("roblox-data-economy-monetization", "session_locked_datastore.luau"),
    "EconomyInventoryQuestService": ("roblox-data-economy-monetization", "economy_inventory_quest_service.luau"),
    "MonetizationReceiptHandler": ("roblox-data-economy-monetization", "monetization_receipt_handler.luau"),
    "NpcAiDirector": ("roblox-ai-and-gameplay-systems", "npc_ai_director.luau"),
    "DialogueAndInteraction": ("roblox-ai-and-gameplay-systems", "dialogue_and_interaction.luau"),
    "RoundAndWaveDirector": ("roblox-ai-and-gameplay-systems", "round_and_wave_director.luau"),
    "PoissonSurfaceScatter": ("roblox-world-assembly-and-optimization", "poisson_surface_scatter.luau"),
    "ModularSocketAssembler": ("roblox-world-assembly-and-optimization", "modular_socket_assembler.luau"),
    "SceneBudgetOptimizer": ("roblox-world-assembly-and-optimization", "scene_budget_optimizer.luau"),
}


def resolve_default_skills_dir() -> Path:
    env_dir = os.environ.get("SHARP_SKILLS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return (Path.home() / ".gemini" / "config" / "skills").resolve()


def resolve_roblox_plugins_dir() -> Path:
    override = os.environ.get("SHARP_ROBLOX_PLUGINS_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        return base / "Roblox" / "Plugins"
    if sys.platform == "darwin":
        return Path.home() / "Documents" / "Roblox" / "Plugins"
    return Path.home() / ".local" / "share" / "Roblox" / "Plugins"


def _read_required_luau(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required Luau source file: {path}")
    return path.read_text(encoding="utf-8")


def build_plugin_rbxmx(
    skills_dir: Path,
    plugin_dir: Path,
    install_to_localappdata: bool = True,
    target_plugins_dir: Optional[Path] = None,
    prune_legacy: bool = True,
) -> Dict[str, str]:
    src_dir = plugin_dir / "src"
    init_src = _read_required_luau(src_dir / "init.server.luau")

    embedded_modules: Dict[str, str] = {}
    for mod_name in PLUGIN_SRC_MODULES:
        embedded_modules[mod_name] = _read_required_luau(src_dir / f"{mod_name}.luau")

    for mod_name, (skill_name, file_name) in SKILL_SCRIPT_MAP.items():
        script_path = skills_dir / skill_name / "scripts" / file_name
        embedded_modules[mod_name] = _read_required_luau(script_path)

    roblox = ET.Element("roblox", attrib={"version": "4"})
    root_script = ET.SubElement(
        roblox, "Item", attrib={"class": "Script", "referent": "RBX_SHARP_PLUGIN_ROOT"}
    )
    root_props = ET.SubElement(root_script, "Properties")
    ET.SubElement(root_props, "string", attrib={"name": "Name"}).text = "SharpBridgePlugin"
    ET.SubElement(root_props, "ProtectedString", attrib={"name": "Source"}).text = init_src

    for idx, (m_name, m_src) in enumerate(embedded_modules.items(), start=1):
        item_mod = ET.SubElement(
            root_script,
            "Item",
            attrib={"class": "ModuleScript", "referent": f"RBX_SHARP_MOD_{idx}"},
        )
        m_props = ET.SubElement(item_mod, "Properties")
        ET.SubElement(m_props, "string", attrib={"name": "Name"}).text = m_name
        ET.SubElement(m_props, "ProtectedString", attrib={"name": "Source"}).text = m_src

    out_rbxmx = plugin_dir / "SharpBridgePlugin.rbxmx"
    tree = ET.ElementTree(roblox)
    ET.indent(tree, space="  ")
    tree.write(out_rbxmx, encoding="utf-8", xml_declaration=True)

    installed_path = ""
    if install_to_localappdata:
        plugins_folder = target_plugins_dir or resolve_roblox_plugins_dir()
        if plugins_folder.is_dir():
            dest = plugins_folder / "SharpBridgePlugin.rbxmx"
            shutil.copy2(out_rbxmx, dest)
            installed_path = str(dest)
            if prune_legacy:
                legacy_dest = plugins_folder / "ForgeBridgePlugin.rbxmx"
                if legacy_dest.is_file():
                    legacy_dest.unlink()

    return {
        "archive_rbxmx": str(out_rbxmx),
        "installed_rbxmx": installed_path,
        "embedded_modules_count": str(len(embedded_modules)),
    }


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    skills = resolve_default_skills_dir()
    res = build_plugin_rbxmx(skills_dir=skills, plugin_dir=base, install_to_localappdata=True)
    print("Built SharpBridgePlugin.rbxmx:", res)
