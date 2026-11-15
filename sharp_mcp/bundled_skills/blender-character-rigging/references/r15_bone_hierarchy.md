# R15 & Humanoid Bone Hierarchy Reference

Complete joint hierarchy, parent-child links, and socket attachments for Roblox R15, Unity Humanoid, and standard game skeletons.

---

## 1. R15 Joint Hierarchy Tree

```
HumanoidRootPart (Root origin, non-deforming)
└── LowerTorso (Root motion / pelvis)
    ├── UpperTorso (Spine / chest)
    │   ├── Head
    │   ├── LeftUpperArm
    │   │   └── LeftLowerArm
    │   │       └── LeftHand (Socket: GripL)
    │   └── RightUpperArm
    │       └── RightLowerArm
    │           └── RightHand (Socket: GripR)
    ├── LeftUpperLeg
    │   └── LeftLowerLeg
    │       └── LeftFoot
    └── RightUpperLeg
        └── RightLowerLeg
            └── RightFoot
```

---

## 2. Equipment Sockets & Rigid Part Mounting

Mounting Location | Parent Bone | Typical Attachments | Socket Rotation CFrame
:--- | :--- | :--- | :---
**GripR** | `RightHand` | Gladius, Spatha, Axe, Spear, Sling | World-aligned facing forward + slight tilt
**GripL** | `LeftHand` | Bow handle, Scutum shield forearm grip | Local forearm inward tilt
**HipR** | `LowerTorso` | Sword Scabbard / Sheath | Vertical, tilted slightly forward
**HipL** | `LowerTorso` | Pugio Dagger Scabbard | Symmetrical to HipR
**BeltR** | `LowerTorso` | Sling pouch, Plumbatae quiver | Angled -70 deg forward-down
**BeltL** | `LowerTorso` | Posca heal flask, throwing knives | Angled +70 deg forward-down
**BackDiag** | `UpperTorso` | Pilum, Stowed Bow, Hasta, Dolabra | Diagonal cross across spine (-28 deg roll)
**BackFlat** | `UpperTorso` | Arcuballista / Crossbow | Flat across shoulder blades

---

## 3. Vertex Group Naming Rule
For skinning, each vertex group on the character mesh MUST exactly match the name of the corresponding deforming bone (e.g. `"UpperTorso"`, `"RightUpperArm"`, `"LeftLowerLeg"`).

## Official R15 Attachment Catalog Names

Use these exact attachment names on R15 limbs and Blender Empty sockets:

- `HumanoidRootPart`: `RootRigAttachment`
- `Head`: `FaceCenterAttachment`, `FaceFrontAttachment`, `HairAttachment`, `HatAttachment`, `NeckRigAttachment`
- `UpperTorso`: `NeckRigAttachment`, `WaistRigAttachment`, `LeftShoulderRigAttachment`, `RightShoulderRigAttachment`, `BodyBackAttachment`, `BodyFrontAttachment`, `LeftCollarAttachment`, `RightCollarAttachment`
- `LowerTorso`: `WaistRigAttachment`, `RootRigAttachment`, `LeftHipRigAttachment`, `RightHipRigAttachment`, `WaistBackAttachment`, `WaistCenterAttachment`, `WaistFrontAttachment`
- `LeftUpperArm` / `RightUpperArm`: `Left/RightShoulderRigAttachment`, `Left/RightElbowRigAttachment`, `Left/RightShoulderAttachment`
- `LeftLowerArm` / `RightLowerArm`: `Left/RightElbowRigAttachment`, `Left/RightWristRigAttachment`
- `LeftHand` / `RightHand`: `Left/RightWristRigAttachment`, `Left/RightGripAttachment`
- `LeftUpperLeg` / `RightUpperLeg`: `Left/RightHipRigAttachment`, `Left/RightKneeRigAttachment`
- `LeftLowerLeg` / `RightLowerLeg`: `Left/RightKneeRigAttachment`, `Left/RightAnkleRigAttachment`
- `LeftFoot` / `RightFoot`: `Left/RightAnkleRigAttachment`, `Left/RightFootAttachment`
