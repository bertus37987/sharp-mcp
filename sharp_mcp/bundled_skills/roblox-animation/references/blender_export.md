# Blender 5.2 Animation Authoring, Retargeting & Export Rules

## 1. Blender 5.2 Slotted Actions & Evaluated Depsgraph

Blender 5.0+ removed legacy `action.fcurves` in favor of **Slotted Actions / Layered Channelbags**:
- Never assume `action.fcurves` exists! In Blender 5.2+:
  - Create/assign via `action.fcurve_ensure_for_datablock(arm_obj, data_path, index=..., group_name=...)` or `pose_bone.keyframe_insert(...)`.
  - Read F-Curves via:
    ```python
    slot = arm_obj.animation_data.action_slot
    fcurves = action.layers[0].strips[0].channelbag(slot).fcurves
    ```
  - `blender_anim_helpers.py` abstracts both Blender 5.2+ and legacy Blender <=4.x automatically.
- **Always read evaluated matrices during baking**:
  - `pose_bone.matrix_basis` ignores IK constraints, `COPY_ROTATION`, `DAMPED_TRACK`, and drivers.
  - Evaluate `depsgraph = bpy.context.evaluated_depsgraph_get()`, then read `arm_eval = arm_obj.evaluated_get(depsgraph)` per frame.

---

## 2. Seamless Looping & Curve Quality

- **FPS**: Author at **60 FPS** (or **30 FPS** for compact `.rbxmx`/Luau payloads).
- **Looping (Idle / Walk / Run)**:
  - Frame `start_frame` and Frame `end_frame` MUST share identical bone poses.
  - Set `keyframe.interpolation = 'BEZIER'` and apply a `'CYCLES'` F-curve modifier (`mode_before='REPEAT'`, `mode_after='REPEAT'`) or flatten end-frame handles so there is no velocity kink at the wrap seam.
- **Snappy Combat / Actions**:
  - Anticipation (frames 1–8) -> Strike/Release (frames 9–14, sparse fast frames) -> Follow-through & Recover (frames 15–30).
  - Add `pose_markers` (`add_animation_marker`) on exact strike/release/footstep frames.

---

## 3. Verified Blender FBX Export Checklist for Roblox

When exporting `.fbx` for Roblox Studio's **3D Importer** or **Animation Editor -> Import from FBX Animation...**:

| Setting | Armature-Only Animation FBX | Skinned Rig / Character Mesh FBX | Why |
| :--- | :--- | :--- | :--- |
| **Scene Scale / Units** | `1 BU = 1 Stud` (`unit_scale=1.0`) | `1 BU = 1 Stud` (`unit_scale=1.0`) | Matches Roblox stud units directly |
| **`apply_scale_options`** | `'FBX_SCALE_UNITS'` | `'FBX_SCALE_UNITS'` | Prevents 100x scale blow-up on import |
| **`global_scale`** | `1.0` | `1.0` | (Scale `1/unit_scale` if authored in meters) |
| **`axis_forward` / `axis_up`** | `'-Z'` / `'Y'` | `'-Z'` / `'Y'` | Matches Roblox world axes |
| **`primary_bone_axis` / `secondary`** | `'Y'` / `'X'` | `'Y'` / `'X'` | Roblox Studio FBX importer convention |
| **`add_leaf_bones`** | **`False`** | **`False`** | **CRITICAL**: Prevents dummy end-bones |
| **`use_armature_deform_only`** | **`True`** | **`True`** | Strips `IK_*` control/pole helper bones |
| **`object_types`** | `{'ARMATURE'}` | `{'ARMATURE', 'MESH'}` | Armature-only keeps animation FBX tiny |
| **`bake_anim`** | **`True`** | `False` (or `True` if bundled) | Evaluates IK/constraints into keyframes |
| **`bake_anim_use_all_bones`** | **`True`** | `True` | Prevents dropped static channels |
| **`bake_anim_use_nla_strips`** | **`False`** | `False` | Exports single clean active Action |
| **`bake_anim_use_all_actions`** | **`False`** | `False` | Prevents merging unrelated clips |
| **`bake_anim_force_startend_keying`** | **`False`** | `False` | Respects authored curve timing |
| **`bake_anim_simplify_factor`** | **`0.0`** | `0.0` | **CRITICAL**: Default `1.0` destroys subtle curves |
| **`path_mode` / `embed_textures`** | `'AUTO'` / `False` | `'COPY'` / `True` | Embeds PBR textures inside rigged FBX |

*(Use [blender_export_roblox_fbx.py](../scripts/blender_export_roblox_fbx.py) to apply these settings automatically.)*

---

## 4. BVH / Mixamo / Motion Capture Retargeting

1. Import source `.bvh` or `.fbx` into Blender (`bpy.ops.import_anim.bvh` or `bpy.ops.import_scene.fbx`).
2. Match source bone names (e.g., `mixamorig:Hips`, `LeftUpLeg`, `LeftForeArm`) to Roblox R15 bones (`LowerTorso`, `LeftUpperLeg`, `LeftLowerArm`).
3. Use `retarget_armature_action()` in `blender_anim_helpers.py` (uses `COPY_ROTATION` world-space retargeting with rest-pose delta compensation, plus optional hip height translation) -> bake directly into Roblox joint space via `blender_bake_to_roblox.py`.

---

## 5. Sharp Blender Auto-Install & Socket/Headless Execution (`sharp_blender_setup`)

Sharp runs a **Blender-only** 3D and animation pipeline:

1. **Detection & Zero-Friction Auto-Install (`sharp_blender_setup`)**:
   - Inspects `SHARP_BLENDER_PATH`, `PATH`, OS standard install paths, and Windows Registry for **Blender** (recommended **5.2+**), verifies `blender --version`, and inspects the Blender `scripts/addons` and `extensions/user_default/mcp` directories for the `mcp-for-blender` addon (`ADDON_PROTOCOL_VERSION`).
   - When missing and `auto_install=True`, runs platform package installation (`winget install --id BlenderFoundation.Blender` on Windows, `brew install --cask blender` on macOS, or `snap`/`flatpak` on Linux), installs the addon via `uvx mcp-for-blender install-addon`, and enables it headlessly (`addon_utils.enable('blender_mcp', default_set=True); bpy.ops.wm.save_userpref()`). Use `dry_run=True` (or `sharp-mcp install-blender --dry-run`) to preview commands without modifying the OS.
2. **Dual Execution Modes (`sharp_blender_rig_and_anim` / `sharp_blender_asset_pipeline`)**:
   - **`socket` / `auto` mode**: Connects first to the live `mcp-for-blender` addon TCP socket (`localhost:9876`) using JSON `{"type": "execute_code", "params": {"code": ...}}` when Blender is open interactively.
   - **`headless` fallback**: Automatically runs `blender --background --python <temp_script.py>` whenever no live socket is listening, compiling `clips.json`, `.glb`/`.fbx`, and `.rbxmx` outputs into project-relative `artifacts/` folders.
