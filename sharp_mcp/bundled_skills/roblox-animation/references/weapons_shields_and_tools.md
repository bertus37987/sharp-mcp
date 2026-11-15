# Weapons, Shields, Tools & Held Props

## 1. Golden Rule: `Motor6D` vs. `Weld` / `WeldConstraint`

- **`Weld` / `WeldConstraint` CANNOT be animated** by `Animator` or `AnimationTrack`. By default, `Tool` with `RequiresHandle = true` automatically creates a rigid `Weld` named `RightGrip` between `RightHand` (R15) / `Right Arm` (R6) and `Tool.Handle`.
- **`Motor6D` (or `AnimationConstraint`) CAN be animated**: `Animator` actively drives `Motor6D.Transform` whenever the `KeyframeSequence` / `CurveAnimation` contains a `Pose` (or `Folder`) matching `Motor6D.Part1.Name`.

---

## 2. Three Proven Patterns for Weapons & Shields

### Pattern A: `Tool` with Independent Weapon Motion (Spinning, Drawing, Throwing, Two-Handed Swaps)
1. Set `Tool.RequiresHandle = false` (or destroy the auto-created `RightGrip` Weld on `Tool.Equipped`).
2. Name the weapon's root part something unique and consistent across rigs (e.g. `WeaponRoot` or `SwordHandle`) so its `Pose.Name` never collides with `"Handle"` across different tools unless intentional.
3. On `Tool.Equipped`, create a `Motor6D` on the server (or client if local-only, though server ensures replication of the joint structure):
   ```lua
   local motor = Instance.new("Motor6D")
   motor.Name = "WeaponMotor"
   motor.Part0 = character:WaitForChild("RightHand") -- or LowerTorso when sheathed
   motor.Part1 = tool:WaitForChild("WeaponRoot")
   motor.C0 = CFrame.new(0, 0, 0) -- match calibrated grip offset from rig_spec.json
   motor.C1 = CFrame.new(0, 0, 0)
   motor.Parent = motor.Part0
   ```
4. On `Tool.Unequipped`, destroy `WeaponMotor` (or re-parent `Part0` to a `LowerTorso` / `UpperTorso` sheath socket!).
5. **In Blender**: Add `WeaponRoot` as a child bone of `RightHand` (or `LowerTorso`) at the exact `Part0_rest * C0` frame. Animate both the character's arms AND `WeaponRoot` in the same clip (e.g. tossing/flipping the blade, or un-parented scabbard draw).

### Pattern B: Hand-Locked Weapons & World-Locked Shields (Rigidly Held in Hand/Forearm)
When a sword or shield stays fixed in the hand/forearm grip and the *arm/wrist* drives all motion:
1. Still prefer `Motor6D` (or `WeldConstraint` to `RightHand`/`LeftHand`/`LeftLowerArm` via calibrated `GripAttachment` / `Socket_*`).
2. **In Blender**, attach a proxy or real mesh of the weapon/shield onto `RightHand` / `LeftHand` / `LeftLowerArm` at the exact socket CFrame so you see real clipping and facing in `look()`.
3. **World-Locked Shield Trick (`solve_world_locked_hand`)**:
   - Large tower shields (*Scutum*) or banners look broken if upper-arm swings tilt the shield face toward the ground or sky.
   - During block / combat stances, solve `LeftHand` rotation each frame so the shield stays vertical and forward-facing in world space (`solve_world_locked_hand` in `blender_anim_helpers.py`).
   - Note: Do **not** world-lock the wrist during locomotion walks unless you want a rigid march; let the shield sway slightly with the torso.

### Pattern C: Deformable / Skinned Weapons & Gear (Bows, Crossbows, Flails, Capes, Banners)
1. Author the weapon in Blender as a **Mesh + Armature** (e.g., `Bow_Armature` with `BowRoot` + `Bone_BowString` + `UpperLimb` / `LowerLimb` weighted vertices).
2. Export as `.fbx` (`Only Deform Bones = True`, `Add Leaf Bones = False`, `Apply Scalings = 'FBX_SCALE_UNITS'`) and import into Studio via 3D Importer -> yields a `MeshPart` with child `Bone` instances!
3. Mount `MeshPart` to the character's `LeftHand` via a `Motor6D` (`Part0 = LeftHand`, `Part1 = BowMeshPart`).
4. **Animate Character + Bowstring in One Clip**:
   - In Blender, parent or constrain the bow armature to `LeftHand`, and constrain an arrow/string bone (`Bone_BowString`) to draw toward `RightHand` during `Draw`/`ChargeHold`!
   - When baked into `KeyframeSequence` / `CurveAnimation`, nest the `Bone_BowString` `Pose` under `BowMeshPart` (which is under `LeftHand`).
   - Playing that single animation on the character's `Animator` bends the bow limbs, pulls the bowstring, and moves the archer's arms in perfect frame-sync!

---

## 3. Two-Handed Weapons (Greatswords, Rifles, Spears, Polearms)

Two ways to keep the off-hand (`LeftHand`) glued to the weapon's secondary grip across every frame:
1. **Bake-time in Blender (`attach_two_handed_ik`)**:
   - Call `attach_two_handed_ik(rig_obj, effector_bone="LeftLowerArm", chain_count=2, target_parent_bone="RightHand", offset_studs=...)` to attach an `IK_OffHandGrip` helper bone parented to `RightHand` and bind the arm IK constraint.
   - Because `blender_bake_to_roblox.py` reads the **evaluated depsgraph**, the baked `KeyframeSequence` / `CurveAnimation` automatically reproduces exact off-hand tracking with zero runtime overhead!
2. **Runtime Dynamic Grip (`IKControl`)**:
   - Place an `Attachment` (`OffHandGrip`) on the weapon `MeshPart` / `Handle`.
   - Attach an `IKControl` under `Humanoid` (or `AnimationController`):
     - `Type = Enum.IKControlType.Transform`
     - `ChainRoot = LeftUpperArm`
     - `EndEffector = LeftHand`
     - `Target = Weapon.OffHandGrip`
     - `Weight = 1` (tween `Weight` to `0` during reloads or one-handed attacks!).

---

## 4. Calibrating Grip Offsets (`C0` / `C1`)

Never eyeball `Motor6D.C0` in Luau:
- Export weapons with origin `(0, 0, 0)` directly at the primary hand grip point, blade/barrel pointing `-Z` (or `+Y` consistently across your armory).
- When `Weapon.Pivot` is at `(0, 0, 0)` in Blender and aligned to the hand bone's grip attachment:
  - In Roblox, `RightHand` has `RightGripAttachment`.
  - Match `Motor6D.C0 = RightHand.RightGripAttachment.CFrame` and `Motor6D.C1 = Weapon.GripAttachment.CFrame` (or `CFrame.identity` if the weapon's origin is already at the grip!).
