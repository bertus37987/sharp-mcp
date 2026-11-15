# Non-Humanoid Rigs, Skinned Creatures & Procedural Motion

You do **NOT** need a `Humanoid` to animate objects in Roblox Studio. A `Humanoid` adds physics, state machines, and heavy replication overhead meant only for walking characters.

---

## 1. Rigged Non-Humanoid Models (Doors, Chests, Creatures, Bosses, Vehicles)

### Required Studio Hierarchy
Two supported structures:
1. **Multi-Part Mechanical / Jointed Rig**:
   ```text
   TreasureChest (Model, PrimaryPart = Base)
   ├── AnimationController
   │   └── Animator
   ├── Base (BasePart, Anchored = true for stationary props!)
   │   └── LidJoint (Motor6D: Part0 = Base, Part1 = Lid)
   └── Lid (BasePart, Anchored = false, CanCollide = false/true)
   ```
   - **CRITICAL ANCHORING RULE**: On stationary animated props (chests, levers, doors, turrets), **Anchor ONLY the root (`Base` / `PrimaryPart`)** and leave all child animated parts **`Anchored = false`**! If a child part is `Anchored = true`, `Motor6D.Transform` will not move it visually/physically.
2. **Skinned Mesh Creature / Flag / Boss (`MeshPart` + `Bone`)**:
   ```text
   Dragon (Model, PrimaryPart = BodyMesh)
   ├── AnimationController
   │   └── Animator
   └── BodyMesh (MeshPart, Anchored = true/false)
       ├── RootBone (Bone)
       │   ├── SpineBone (Bone) -> NeckBone -> HeadBone
       │   ├── LeftWing1 (Bone) -> LeftWing2
       │   └── Tail1 (Bone) -> Tail2 -> Tail3
   ```

### Playback Rule (Avoid Deprecated Methods!)
- `AnimationController:LoadAnimation()` and `Humanoid:LoadAnimation()` are **deprecated**.
- Always load through the `Animator` child:
  ```lua
  local animController = model:WaitForChild("AnimationController")
  local animator = animController:FindFirstChildOfClass("Animator") or Instance.new("Animator", animController)
  local track = animator:LoadAnimation(animationInstance)
  track:Play()
  ```

### Authoring Custom Rigs in Blender
1. Either build the rig + mesh directly in Blender, export `.fbx` via `blender_export_roblox_fbx.py` (`mode="rigged_mesh"` or `"rigged_with_anim"`), and import via Studio's 3D Importer;
2. **OR** assemble the parts/bones in Roblox Studio first, run [probe_rig.luau](../scripts/probe_rig.luau) to dump `rig_spec.json`, build an exact Blender rig with [blender_build_roblox_rig.py](../scripts/blender_build_roblox_rig.py), animate in Blender, and bake back via [blender_bake_to_roblox.py](../scripts/blender_bake_to_roblox.py)!

---

## 2. When to Use `TweenService` Instead of Rigs

Use `TweenService` (zero bones or `AnimationController` needed) for simple, deterministic 1–2 property motion:
- Sliding doors, elevators, rotating fans, floating collectibles, UI animations, camera FOV kicks, color/transparency fades.
- **Note**: For models without `Motor6D`, tween a single `CFrameValue` bound to `model:PivotTo(cf)` rather than tweening `PrimaryPart.CFrame` directly (so un-welded children don't get left behind, or weld all sub-parts to `PrimaryPart` with `WeldConstraint` and anchor only `PrimaryPart`).

---

## 3. Runtime Inverse Kinematics (`IKControl`)

`IKControl` solves real-time bone/part chains over any playing animation on both `BasePart` rigs (`Motor6D`/`AnimationConstraint`) and skinned `MeshPart` (`Bone`) rigs.
- Parent `IKControl` directly under `Humanoid` or `AnimationController` (which must contain an `Animator`).
- Key properties:
  - `Type`: `Enum.IKControlType.Position`, `Rotation`, `LookAt`, or `Transform`
  - `ChainRoot`: e.g. `UpperTorso` or `LeftUpperLeg` or `LeftUpperArm`
  - `EndEffector`: e.g. `Head`, `LeftFoot`, or `LeftHand`
  - `Target`: target `Attachment` or `BasePart`
  - `Pole`: optional elbow/knee directional `Attachment` / `BasePart`
  - `Weight`: `0`–`1` blend factor
  - `SmoothTime`: transition smoothing in seconds

Common uses:
- **Head/Torso Look-At**: `Type = LookAt`, `ChainRoot = UpperTorso`, `EndEffector = Head`.
- **Two-Handed Weapon Off-Hand**: `Type = Transform`, `ChainRoot = LeftUpperArm`, `EndEffector = LeftHand`, `Target = Weapon.OffHandAttachment`.
- **Foot Planting**: Raycast below `LeftFoot`/`RightFoot` and move foot target attachments with `Type = Position`.

---

## 4. Procedural Joint Layering (`RunService.PreSimulation`)

To layer recoil, breathing, torso twist toward camera pitch, or procedural lean **on top of** playing animations:
- Multiply into `joint.Transform` during `RunService.PreSimulation` (respecting `animator.EvaluationThrottled`):
  ```lua
  RunService.PreSimulation:Connect(function()
      if animator.EvaluationThrottled then return end
      waistJoint.Transform = CFrame.Angles(aimPitch * 0.4, 0, 0) * waistJoint.Transform
  end)
  ```
- **Never** mutate `Attachment0.CFrame` / `Attachment1.CFrame` on `AnimationConstraint` or `Motor6D.C0` every frame for procedural animation—it fights retargeting and breaks joint math.

---

## 5. Native Roblox Studio AI (`generate_animation`)

When Roblox Studio MCP is connected and you want a quick R15+ draft or R6-to-R15 conversion:
- **New R15+ clip**: `generate_animation(studio_id=..., textPrompt="<exact description>", instance_path="Workspace.MyRig", duration=...)`
- **Upscale legacy R6 clip**: `generate_animation(studio_id=..., inputAssetId="123456789")`
- You can inspect or refine generated clips further in Studio's Animation Editor or export/probe them as reference keyframes.
