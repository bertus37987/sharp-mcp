# Blender 5.2+ Prop, Armor & Roblox Socket Export Guide

Workflow for building or importing 3D equipment/armor in Blender, aligning to R15 scale, adding Roblox socket Empties, and exporting FBX/GLB + attachment JSON sidecar for `AttachmentEngine`.

## 1. Blender 5.2+ API Compatibility Rules

- **`use_auto_smooth` removed**: Blender 4.1+ and 5.2 removed `mesh.use_auto_smooth`. Never set `mesh.use_auto_smooth = True` directly; use smooth/flat polygon flags, `WeightedNormal` modifiers, or `recalc_face_normals`.
- **Principled BSDF lookup**: Find shader nodes by `node.type == "BSDF_PRINCIPLED"` rather than `mat.node_tree.nodes["Principled BSDF"]` (breaks on localized Blender installs).
- **OBJ import**: Prefer `bpy.ops.wm.obj_import(filepath=...)` when present, falling back to `bpy.ops.import_scene.obj(filepath=...)`.
- **Headless Armature Skinning**: `bpy.ops.object.parent_set(type="ARMATURE_AUTO")` can fail heat-weighting on thin plates headless. Always catch `RuntimeError`, fall back to bone-proximity vertex groups + `ARMATURE` modifier, and enforce Roblox's **4-bone influence limit** per vertex normalized to `1.0`.

## 2. Scale & Coordinate Convention

- Build/scale in **Roblox studs**: `1 Blender Unit (BU) = 1 stud`, calibrated to the target R15 rig (`~5.0` studs tall).
- Before parenting or exporting, select the prop and run `bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)` so local scale is `(1, 1, 1)`.
- Convert Blender Z-up (`-Y` forward) transforms into Roblox Y-up (`-Z` forward) CFrames via `matrix_to_roblox_cf(rel_mat, unit_scale=1.0)`.

## 3. Socket Empties & Binding Modes

1. **Rigid Props & Weapons (`attachment_mode="rigid"`)**:
   - Parent the mesh to the target R15 rig bone (`prop.parent = rig; prop.parent_type = "BONE"; prop.parent_bone = limb_name`) with `matrix_parent_inverse = Translation((0, -bone.length, 0)) @ bone.matrix_local.inverted()`.
   - Add `EMPTY` children named identically to Roblox catalog / weapon sockets:
     - Sword/Gun: `GripAttachment`, `ForegripAttachment`, `HolsterBackAttachment`, `MuzzleAttachment`
     - Bow: `BowGripAttachment`, `StringNockAttachment`, `HolsterBackAttachment`
     - Shield: `ShieldGripAttachment`, `ShieldBackAttachment`
     - Staff: `StaffGripAttachment`, `ForegripAttachment`, `HolsterBackAttachment`
     - Armor/Back: `BodyBackAttachment`, `BodyFrontAttachment`, `RightCollarAttachment`, `HatAttachment`, `RightShoulderAttachment`, `LeftShoulderAttachment`
2. **Skinned Armor (`attachment_mode="skinned_armor"`)**:
   - Align the mesh to the target bone region (`UpperTorso`, `RightUpperLeg`, etc.), bind with `ARMATURE_AUTO` (or bone-proximity fallback), and clamp each vertex to max 4 weights summing to `1.0`.
   - Export `.fbx` with `object_types={"ARMATURE", "MESH", "EMPTY"}`, `axis_forward="-Z"`, `axis_up="Y"`, `add_leaf_bones=False`, `bake_anim=False`, alongside `.glb` (`export_yup=True`).

## 4. JSON Sidecar (`<prop_name>_attachments.json`)

`BlenderDomainEngine.compile_asset_attach_bpy` emits a `sharp.attachment_sidecar.v1` JSON file alongside `.fbx`/`.glb` containing `prop_dimensions_studs`, `rig_height_studs`, `target_limb`, `target_limb_attachment`, and `attachments[]` (`name`, `role`, `target_limb`, `target_limb_attachment`, `pos`, `rot_deg`, `cframe`). Feed `sidecar_path` directly into `AttachmentEngine.compile_attach_luau(...)` or `validate_attachment_spec(...)`.
