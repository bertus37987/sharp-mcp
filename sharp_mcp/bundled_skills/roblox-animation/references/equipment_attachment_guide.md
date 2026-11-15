# Roblox R15 Equipment & Weapon Attachment Guide

Standard R15 attachment catalog, joint selection rules, physics flags, and two-handed IK setup used by `AttachmentEngine`.

## 1. Official R15 Attachment Catalog

Always attach to existing R15 attachment names (creating them with exact official offsets only if a custom rig omits them):

| Body Part | Official Attachments |
|---|---|
| `HumanoidRootPart` | `RootRigAttachment` |
| `Head` | `FaceCenterAttachment`, `FaceFrontAttachment`, `HairAttachment`, `HatAttachment`, `NeckRigAttachment` |
| `UpperTorso` | `NeckRigAttachment`, `WaistRigAttachment`, `LeftShoulderRigAttachment`, `RightShoulderRigAttachment`, `BodyBackAttachment`, `BodyFrontAttachment`, `LeftCollarAttachment`, `RightCollarAttachment` |
| `LowerTorso` | `WaistRigAttachment`, `RootRigAttachment`, `LeftHipRigAttachment`, `RightHipRigAttachment`, `WaistBackAttachment`, `WaistCenterAttachment`, `WaistFrontAttachment` |
| `LeftUpperArm` | `LeftShoulderRigAttachment`, `LeftElbowRigAttachment`, `LeftShoulderAttachment` |
| `LeftLowerArm` | `LeftElbowRigAttachment`, `LeftWristRigAttachment` |
| `LeftHand` | `LeftWristRigAttachment`, `LeftGripAttachment` |
| `RightUpperArm` | `RightShoulderRigAttachment`, `RightElbowRigAttachment`, `RightShoulderAttachment` |
| `RightLowerArm` | `RightElbowRigAttachment`, `RightWristRigAttachment` |
| `RightHand` | `RightWristRigAttachment`, `RightGripAttachment` |
| `LeftUpperLeg` | `LeftHipRigAttachment`, `LeftKneeRigAttachment` |
| `LeftLowerLeg` | `LeftKneeRigAttachment`, `LeftAnkleRigAttachment` |
| `LeftFoot` | `LeftAnkleRigAttachment`, `LeftFootAttachment` |
| `RightUpperLeg` | `RightHipRigAttachment`, `RightKneeRigAttachment` |
| `RightLowerLeg` | `RightKneeRigAttachment`, `RightAnkleRigAttachment` |
| `RightFoot` | `RightAnkleRigAttachment`, `RightFootAttachment` |

## 2. Attachment Modes & When to Use Each

1. **`accessory_rigid`**: Static rigid accessories (capes, backpacks, wings, shoulder pets, helmets). Creates a `RigidConstraint` with `Attachment0 = itemAttachment` and `Attachment1 = limbAttachment`. Sets all item parts `Anchored = false`, `CanCollide = false`, `Massless = true`, zero-density `CustomPhysicalProperties`.
2. **`tool_grip`**: Standard Roblox `Tool` backpack/equip item. Sets `RequiresHandle = true`, ensures primary `BasePart` is named `Handle` directly parented under the `Tool` (avoiding `Tool > Model > Handle` hierarchy breakage), and writes `Tool.Grip`.
3. **`motor6d_weapon`**: Combat weapons (`sword`, `bow`, `shield`, `staff`, `gun`) that need independent weapon-bone animation (twirls, draws, recoil).
   - If the item is inside a `Tool`, sets `RequiresHandle = false` and removes fighting `RightGrip` welds cleanly via `pcall`.
   - Creates `Motor6D` with `Part0 = limbPart`, `Part1 = handlePart`, `C0 = limbAttachment.CFrame`, `C1 = itemAttachment.CFrame` so the initial pose matches `RigidConstraint` identically.
4. **`holster_back` / `holster_hip` / `shield_back`**: Unarmed stow sockets onto `UpperTorso.BodyBackAttachment` or `LowerTorso.WaistCenterAttachment` using holster-specific item attachments (`HolsterBackAttachment`, `HolsterHipAttachment`, `ShieldBackAttachment`).
5. **`armor_set`**: Multi-piece rig attachment supporting slot names `helmet`, `chest`, `left_pauldron`, `right_pauldron`, `left_greave`, `right_greave`, `left_boot`, `right_boot`, `left_gauntlet`, `right_gauntlet`, `cape`, `backpack`.
6. **`two_hand_ik`**: Configures off-hand `IKControl` (`ChainRoot = LeftUpperArm` / `RightUpperArm`, `EndEffector = LeftHand` / `RightHand`, `Target = ForegripAttachment` / `StringNockAttachment`, optional `Pole`, `Weight`, `SmoothTime`). Guard `Instance.new("IKControl")`, `Enum.IKControlType`, `EndEffectorOffset`, and `Priority` inside `pcall` for cross-version resilience.

## 3. Edit-Mode & Verification Checklist

- Generated Edit-mode scripts wrap mutations in `ChangeHistoryService` via `__SharpActiveRecordingId` so Ctrl+Z undoes cleanly.
- Always run `verify` mode (`AttachmentEngine.compile_verify_luau`) before Playtest to catch:
  - Missing official R15 attachments or required item sockets.
  - Non-`Massless` or collidable accessory/weapon parts distorting character movement.
  - Competing joints (`RightGrip` + `Motor6D` + `RigidConstraint` fighting on the same part pair).
  - Scale mismatches when item dimensions exceed expected multiples of rig height (`5.0` studs standard R15).
- Blender-authored props pass socket offsets via `<prop>_attachments.json` (`AttachmentEngine.load_blender_sidecar`).
