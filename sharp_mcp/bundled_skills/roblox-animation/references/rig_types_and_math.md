# Rig Types, Joint Hierarchies & Coordinate Math

## 1. Roblox Coordinate System vs. Blender

- **Roblox**: Right-handed, **`+X` right, `+Y` up, `-Z` forward** (units = **studs**, 1 stud ≈ 0.28 m; classic blocky R15 avatar height ≈ 5.1 studs).
- **Blender**: Right-handed, **`+X` right, `+Z` up, `-Y` forward** (recommended scale when authoring Roblox animations: **1 Blender Unit = 1 stud**, or track `unit_scale` explicitly).

Conjugation matrix converting Roblox `(x, y, z)` to Blender `(x, -z, y)`:

```python
ROBLOX_TO_BLENDER = Matrix((
    (1.0,  0.0,  0.0, 0.0),
    (0.0,  0.0, -1.0, 0.0),
    (0.0,  1.0,  0.0, 0.0),
    (0.0,  0.0,  0.0, 1.0),
))
```

- `M_blender = ROBLOX_TO_BLENDER @ M_roblox @ ROBLOX_TO_BLENDER.transposed()` (with translation scaled by `unit_scale`).
- `M_roblox  = ROBLOX_TO_BLENDER.transposed() @ M_blender @ ROBLOX_TO_BLENDER` (with translation divided by `unit_scale`).

---

## 2. Joint Systems in Roblox Studio

### A. `Motor6D` (Classic R6, R15, Tools, Custom Mechanical Rigs)
Connects `Part0` to `Part1` via `C0`, `C1`, and runtime `Transform`:
```text
Part1.CFrame = Part0.CFrame * C0 * Transform * C1^-1
```

### B. `AnimationConstraint` (Modern R15 `StarterPlayer.AvatarJointUpgrade`)
Enabled by default on new experiences for R15 characters. Connects `Attachment0` (`Part0`) and `Attachment1` (`Part1`):
- `IsKinematic = true` (default): behaves kinematically identically to `Motor6D` (`C0 = Attachment0.CFrame`, `C1 = Attachment1.CFrame`, `Transform` driven by `Animator`).
- `IsKinematic = false`: switches to physical force/torque simulation (ragdolls, physical hit reactions).
- `C0`, `C1`, `Part0`, `Part1` exist as **read-only** compatibility properties.
- **Rule**: Never write procedural animation offsets to `Attachment0.CFrame` / `Attachment1.CFrame` (breaks retargeting). Always multiply into `joint.Transform` during `RunService.PreSimulation`.

### C. `Bone` (Skinned `MeshPart` Rigs)
`Bone` inherits from `Attachment` and lives inside a `MeshPart` (in nested hierarchies).
- **Rest CFrames**: `Bone.CFrame` (local to parent Bone/MeshPart) and `Bone.WorldCFrame` (world-space rest frame).
- **Animation Delta**: `Bone.Transform` (authored via `Pose.CFrame` or `CurveAnimation` folder matching `Bone.Name`).
- **Combined Animated CFrames**: `Bone.TransformedCFrame` and `Bone.TransformedWorldCFrame` (rest + `Transform`).

---

## 3. Exact Blender-to-Roblox Pose Extraction Formula

If each Blender armature bone `b` has edit-mode rest matrix:
- Root part (`HumanoidRootPart` / `PrimaryPart`): `bone.matrix_local = to_blender(Root_rest)`
- Each child joint (`Motor6D` / `AnimationConstraint`): `bone.matrix_local = to_blender(Part0_rest * C0)`
- Each skinned `Bone`: `bone.matrix_local = to_blender(Bone.WorldCFrame)`

Then for any posed child bone `pb` evaluated on `depsgraph` (`arm_eval = arm_obj.evaluated_get(depsgraph)`):
```python
rest_rel = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
t_blender = (pb.parent.matrix @ rest_rel).inverted() @ pb.matrix
t_roblox = ROBLOX_TO_BLENDER.transposed() @ t_blender @ ROBLOX_TO_BLENDER
# Scale translation back from Blender units to studs:
t_roblox.translation /= unit_scale
```
Why use `(pb.parent.matrix @ rest_rel).inverted() @ pb.matrix` instead of `pb.matrix_basis`?
`pose_bone.matrix_basis` ignores IK constraints, Copy Rotation, Damped Track, and drivers. Evaluating `pb.matrix` from the depsgraph captures **everything** cleanly with zero Euler-order ambiguity.

---

## 4. Standard Roblox Pose Hierarchies (`Pose.Name`)

In `KeyframeSequence` (`Pose.Name`) and `CurveAnimation` (`Folder.Name`), names **must match the child `BasePart.Name` (`Motor6D.Part1.Name`) or `Bone.Name`**, NOT the `Motor6D.Name`.

### Standard R15 Hierarchy
```text
HumanoidRootPart
└── LowerTorso
    ├── UpperTorso
    │   ├── Head
    │   ├── LeftUpperArm -> LeftLowerArm -> LeftHand
    │   └── RightUpperArm -> RightLowerArm -> RightHand
    ├── LeftUpperLeg -> LeftLowerLeg -> LeftFoot
    └── RightUpperLeg -> RightLowerLeg -> RightFoot
```
*(Optional `R15+` or custom weapon bones attach under `LeftHand`, `RightHand`, `UpperTorso`, `LowerTorso`, or `Head`.)*

### Standard R6 Hierarchy
```text
HumanoidRootPart
└── Torso
    ├── Head
    ├── Left Arm
    ├── Right Arm
    ├── Left Leg
    └── Right Leg
```
*(Note: R6 `Motor6D` names are `RootJoint`, `Neck`, `Left Shoulder`, `Right Shoulder`, `Left Hip`, `Right Hip`, but `Pose.Name` must be `Torso`, `Head`, `Left Arm`, `Right Arm`, `Left Leg`, `Right Leg`!)*
