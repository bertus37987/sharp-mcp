"""Equipment Attachment, R15 Catalog, Rig Validation & Two-Handed IK Engine.

Provides:
- Official R15 attachment catalog (`R15_ATTACHMENTS`) and socket/armor presets (`SOCKET_PRESETS`, `ARMOR_SLOTS`)
- Spec/sidecar validators (`validate_attachment_spec`, `load_blender_sidecar`)
- Edit-mode Luau generators wrapped in `ChangeHistoryService` (`__SharpActiveRecordingId` pattern) for:
  `accessory_rigid`, `tool_grip`, `motor6d_weapon`, `holster_back`, `holster_hip`, `shield_back`,
  `armor_set`, `two_hand_ik`, and read-only `verify`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Canonical Roblox R15 limb attachments (classic blocky R15 proportions, 1.0 scale).
R15_ATTACHMENTS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "HumanoidRootPart": {
        "RootRigAttachment": {"pos": [0.0, -1.0, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "Head": {
        "HatAttachment": {"pos": [0.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "HairAttachment": {"pos": [0.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "FaceCenterAttachment": {"pos": [0.0, 0.0, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "FaceFrontAttachment": {"pos": [0.0, 0.0, -0.6], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "NeckRigAttachment": {"pos": [0.0, -0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "UpperTorso": {
        "NeckRigAttachment": {"pos": [0.0, 0.8, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "BodyBackAttachment": {"pos": [0.0, 0.0, 0.5], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "BodyFrontAttachment": {"pos": [0.0, 0.0, -0.5], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "LeftCollarAttachment": {"pos": [-0.8, 0.8, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "RightCollarAttachment": {"pos": [0.8, 0.8, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "WaistRigAttachment": {"pos": [0.0, -0.8, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftShoulderRigAttachment": {"pos": [-1.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightShoulderRigAttachment": {"pos": [1.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "LowerTorso": {
        "WaistRigAttachment": {"pos": [0.0, 0.2, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "WaistCenterAttachment": {"pos": [0.0, 0.0, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "WaistFrontAttachment": {"pos": [0.0, 0.0, -0.5], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "WaistBackAttachment": {"pos": [0.0, 0.0, 0.5], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
        "RootRigAttachment": {"pos": [0.0, -0.2, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftHipRigAttachment": {"pos": [-0.5, -0.2, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightHipRigAttachment": {"pos": [0.5, -0.2, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "LeftUpperArm": {
        "LeftShoulderRigAttachment": {"pos": [0.5, 0.4, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftElbowRigAttachment": {"pos": [0.0, -0.5, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftShoulderAttachment": {"pos": [0.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
    },
    "LeftLowerArm": {
        "LeftElbowRigAttachment": {"pos": [0.0, 0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftWristRigAttachment": {"pos": [0.0, -0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "LeftHand": {
        "LeftWristRigAttachment": {"pos": [0.0, 0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftGripAttachment": {"pos": [0.0, -0.15, 0.0], "rot_deg": [-90.0, 0.0, 0.0], "category": "grip"},
    },
    "RightUpperArm": {
        "RightShoulderRigAttachment": {"pos": [-0.5, 0.4, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightElbowRigAttachment": {"pos": [0.0, -0.5, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightShoulderAttachment": {"pos": [0.0, 0.6, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
    },
    "RightLowerArm": {
        "RightElbowRigAttachment": {"pos": [0.0, 0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightWristRigAttachment": {"pos": [0.0, -0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "RightHand": {
        "RightWristRigAttachment": {"pos": [0.0, 0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightGripAttachment": {"pos": [0.0, -0.15, 0.0], "rot_deg": [-90.0, 0.0, 0.0], "category": "grip"},
    },
    "LeftUpperLeg": {
        "LeftHipRigAttachment": {"pos": [0.0, 0.55, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftKneeRigAttachment": {"pos": [0.0, -0.55, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "LeftLowerLeg": {
        "LeftKneeRigAttachment": {"pos": [0.0, 0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftAnkleRigAttachment": {"pos": [0.0, -0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "LeftFoot": {
        "LeftAnkleRigAttachment": {"pos": [0.0, 0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "LeftFootAttachment": {"pos": [0.0, -0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
    },
    "RightUpperLeg": {
        "RightHipRigAttachment": {"pos": [0.0, 0.55, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightKneeRigAttachment": {"pos": [0.0, -0.55, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "RightLowerLeg": {
        "RightKneeRigAttachment": {"pos": [0.0, 0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightAnkleRigAttachment": {"pos": [0.0, -0.35, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
    },
    "RightFoot": {
        "RightAnkleRigAttachment": {"pos": [0.0, 0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "rig"},
        "RightFootAttachment": {"pos": [0.0, -0.15, 0.0], "rot_deg": [0.0, 0.0, 0.0], "category": "accessory"},
    },
}


# Preset equipment sockets & attachment defaults (studs / degrees in Roblox frame).
SOCKET_PRESETS: Dict[str, Dict[str, Any]] = {
    "sword": {
        "category": "weapon_melee",
        "default_mode": "motor6d_weapon",
        "default_slot": "right_hand",
        "limb_part": "RightHand",
        "limb_attachment": "RightGripAttachment",
        "item_attachment": "GripAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
        "tool_grip": {"pos": [0.0, 0.0, -0.45], "rot_deg": [-90.0, 0.0, 0.0]},
        "holster": {
            "back": {
                "limb_part": "UpperTorso",
                "limb_attachment": "BodyBackAttachment",
                "item_attachment": "HolsterBackAttachment",
                "offset_pos": [0.15, 0.1, 0.12],
                "offset_rot_deg": [0.0, 0.0, -32.0],
            },
            "hip_left": {
                "limb_part": "LowerTorso",
                "limb_attachment": "WaistCenterAttachment",
                "item_attachment": "HolsterHipAttachment",
                "offset_pos": [-1.08, -0.05, 0.15],
                "offset_rot_deg": [55.0, 0.0, -8.0],
            },
            "hip_right": {
                "limb_part": "LowerTorso",
                "limb_attachment": "WaistCenterAttachment",
                "item_attachment": "HolsterHipAttachment",
                "offset_pos": [1.08, -0.05, 0.15],
                "offset_rot_deg": [55.0, 0.0, 8.0],
            },
        },
        "two_hand_ik": {
            "chain_root": "LeftUpperArm",
            "end_effector": "LeftHand",
            "foregrip_attachment": "ForegripAttachment",
            "foregrip_pos": [0.0, -0.55, 0.0],
            "foregrip_rot_deg": [0.0, 0.0, 0.0],
            "pole_limb": "UpperTorso",
            "pole_pos": [-1.6, 0.0, 1.2],
        },
    },
    "bow": {
        "category": "weapon_ranged",
        "default_mode": "motor6d_weapon",
        "default_slot": "left_hand",
        "limb_part": "LeftHand",
        "limb_attachment": "LeftGripAttachment",
        "item_attachment": "BowGripAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
        "tool_grip": {"pos": [0.0, 0.0, 0.0], "rot_deg": [-90.0, 0.0, 0.0]},
        "holster": {
            "back": {
                "limb_part": "UpperTorso",
                "limb_attachment": "BodyBackAttachment",
                "item_attachment": "HolsterBackAttachment",
                "offset_pos": [0.0, 0.05, 0.15],
                "offset_rot_deg": [0.0, 0.0, 35.0],
            },
        },
        "two_hand_ik": {
            "chain_root": "RightUpperArm",
            "end_effector": "RightHand",
            "foregrip_attachment": "StringNockAttachment",
            "foregrip_pos": [0.0, 0.0, 0.35],
            "foregrip_rot_deg": [0.0, 0.0, 0.0],
            "pole_limb": "UpperTorso",
            "pole_pos": [1.6, 0.1, 1.2],
        },
    },
    "shield": {
        "category": "defense",
        "default_mode": "motor6d_weapon",
        "default_slot": "left_hand",
        "limb_part": "LeftHand",
        "limb_attachment": "LeftGripAttachment",
        "item_attachment": "ShieldGripAttachment",
        "offset_pos": [-0.22, 0.15, 0.0],
        "offset_rot_deg": [0.0, 90.0, 0.0],
        "tool_grip": {"pos": [0.22, 0.0, 0.0], "rot_deg": [0.0, 90.0, 0.0]},
        "holster": {
            "back": {
                "limb_part": "UpperTorso",
                "limb_attachment": "BodyBackAttachment",
                "item_attachment": "ShieldBackAttachment",
                "offset_pos": [0.0, 0.05, 0.18],
                "offset_rot_deg": [0.0, 180.0, 0.0],
            },
        },
    },
    "staff": {
        "category": "weapon_magic",
        "default_mode": "motor6d_weapon",
        "default_slot": "right_hand",
        "limb_part": "RightHand",
        "limb_attachment": "RightGripAttachment",
        "item_attachment": "StaffGripAttachment",
        "offset_pos": [0.0, -0.35, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
        "tool_grip": {"pos": [0.0, -0.35, 0.0], "rot_deg": [-90.0, 0.0, 0.0]},
        "holster": {
            "back": {
                "limb_part": "UpperTorso",
                "limb_attachment": "BodyBackAttachment",
                "item_attachment": "HolsterBackAttachment",
                "offset_pos": [0.0, 0.15, 0.14],
                "offset_rot_deg": [0.0, 0.0, -28.0],
            },
        },
        "two_hand_ik": {
            "chain_root": "LeftUpperArm",
            "end_effector": "LeftHand",
            "foregrip_attachment": "ForegripAttachment",
            "foregrip_pos": [0.0, 0.9, 0.0],
            "foregrip_rot_deg": [0.0, 0.0, 0.0],
            "pole_limb": "UpperTorso",
            "pole_pos": [-1.5, 0.0, 1.1],
        },
    },
    "gun": {
        "category": "weapon_ranged",
        "default_mode": "two_hand_ik",
        "default_slot": "right_hand",
        "limb_part": "RightHand",
        "limb_attachment": "RightGripAttachment",
        "item_attachment": "GripAttachment",
        "offset_pos": [0.0, 0.0, -0.25],
        "offset_rot_deg": [0.0, 0.0, 0.0],
        "tool_grip": {"pos": [0.0, -0.1, 0.35], "rot_deg": [0.0, 0.0, 0.0]},
        "holster": {
            "back": {
                "limb_part": "UpperTorso",
                "limb_attachment": "BodyBackAttachment",
                "item_attachment": "HolsterBackAttachment",
                "offset_pos": [0.1, 0.05, 0.15],
                "offset_rot_deg": [0.0, 90.0, -35.0],
            },
            "hip_right": {
                "limb_part": "LowerTorso",
                "limb_attachment": "WaistCenterAttachment",
                "item_attachment": "HolsterHipAttachment",
                "offset_pos": [1.05, -0.1, 0.05],
                "offset_rot_deg": [80.0, 0.0, 0.0],
            },
        },
        "two_hand_ik": {
            "chain_root": "LeftUpperArm",
            "end_effector": "LeftHand",
            "foregrip_attachment": "ForegripAttachment",
            "foregrip_pos": [0.0, 0.0, -1.15],
            "foregrip_rot_deg": [0.0, 0.0, 0.0],
            "pole_limb": "UpperTorso",
            "pole_pos": [-1.4, -0.2, 1.0],
        },
    },
    "backpack": {
        "category": "wearable_back",
        "default_mode": "accessory_rigid",
        "default_slot": "back",
        "limb_part": "UpperTorso",
        "limb_attachment": "BodyBackAttachment",
        "item_attachment": "BodyBackAttachment",
        "offset_pos": [0.0, 0.0, 0.45],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "cape": {
        "category": "wearable_back",
        "default_mode": "accessory_rigid",
        "default_slot": "back",
        "limb_part": "UpperTorso",
        "limb_attachment": "BodyBackAttachment",
        "item_attachment": "BodyBackAttachment",
        "offset_pos": [0.0, 0.55, 0.12],
        "offset_rot_deg": [6.0, 0.0, 0.0],
    },
    "wings": {
        "category": "wearable_back",
        "default_mode": "accessory_rigid",
        "default_slot": "back",
        "limb_part": "UpperTorso",
        "limb_attachment": "BodyBackAttachment",
        "item_attachment": "BodyBackAttachment",
        "offset_pos": [0.0, 0.25, 0.22],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "pet": {
        "category": "companion",
        "default_mode": "accessory_rigid",
        "default_slot": "right_collar",
        "limb_part": "UpperTorso",
        "limb_attachment": "RightCollarAttachment",
        "item_attachment": "PetMountAttachment",
        "offset_pos": [0.35, 0.55, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
}


# Canonical armor slot -> R15 limb + attachment mapping.
ARMOR_SLOTS: Dict[str, Dict[str, Any]] = {
    "helmet": {
        "limb_part": "Head",
        "limb_attachment": "HatAttachment",
        "item_attachment": "HatAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "face_visor": {
        "limb_part": "Head",
        "limb_attachment": "FaceFrontAttachment",
        "item_attachment": "FaceFrontAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "chest": {
        "limb_part": "UpperTorso",
        "limb_attachment": "BodyFrontAttachment",
        "item_attachment": "BodyFrontAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "belt": {
        "limb_part": "LowerTorso",
        "limb_attachment": "WaistCenterAttachment",
        "item_attachment": "WaistCenterAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "left_pauldron": {
        "limb_part": "LeftUpperArm",
        "limb_attachment": "LeftShoulderAttachment",
        "item_attachment": "LeftShoulderAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "right_pauldron": {
        "limb_part": "RightUpperArm",
        "limb_attachment": "RightShoulderAttachment",
        "item_attachment": "RightShoulderAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "left_gauntlet": {
        "limb_part": "LeftLowerArm",
        "limb_attachment": "LeftWristRigAttachment",
        "item_attachment": "LeftWristRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "right_gauntlet": {
        "limb_part": "RightLowerArm",
        "limb_attachment": "RightWristRigAttachment",
        "item_attachment": "RightWristRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "left_thigh": {
        "limb_part": "LeftUpperLeg",
        "limb_attachment": "LeftHipRigAttachment",
        "item_attachment": "LeftHipRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "right_thigh": {
        "limb_part": "RightUpperLeg",
        "limb_attachment": "RightHipRigAttachment",
        "item_attachment": "RightHipRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "left_greave": {
        "limb_part": "LeftLowerLeg",
        "limb_attachment": "LeftKneeRigAttachment",
        "item_attachment": "LeftKneeRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "right_greave": {
        "limb_part": "RightLowerLeg",
        "limb_attachment": "RightKneeRigAttachment",
        "item_attachment": "RightKneeRigAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "left_boot": {
        "limb_part": "LeftFoot",
        "limb_attachment": "LeftFootAttachment",
        "item_attachment": "LeftFootAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
    "right_boot": {
        "limb_part": "RightFoot",
        "limb_attachment": "RightFootAttachment",
        "item_attachment": "RightFootAttachment",
        "offset_pos": [0.0, 0.0, 0.0],
        "offset_rot_deg": [0.0, 0.0, 0.0],
    },
}

ARMOR_SLOT_ALIASES: Dict[str, str] = {
    "head": "helmet",
    "hat": "helmet",
    "helm": "helmet",
    "visor": "face_visor",
    "cuirass": "chest",
    "torso": "chest",
    "chestplate": "chest",
    "waist": "belt",
    "tassets": "belt",
    "pauldron_left": "left_pauldron",
    "shoulder_left": "left_pauldron",
    "left_shoulder": "left_pauldron",
    "pauldron_right": "right_pauldron",
    "shoulder_right": "right_pauldron",
    "right_shoulder": "right_pauldron",
    "gauntlet_left": "left_gauntlet",
    "bracer_left": "left_gauntlet",
    "left_bracer": "left_gauntlet",
    "gauntlet_right": "right_gauntlet",
    "bracer_right": "right_gauntlet",
    "right_bracer": "right_gauntlet",
    "thigh_left": "left_thigh",
    "thigh_right": "right_thigh",
    "greave_left": "left_greave",
    "shin_left": "left_greave",
    "left_shin": "left_greave",
    "greave_right": "right_greave",
    "shin_right": "right_greave",
    "right_shin": "right_greave",
    "boot_left": "left_boot",
    "foot_left": "left_boot",
    "left_foot": "left_boot",
    "boot_right": "right_boot",
    "foot_right": "right_boot",
    "right_foot": "right_boot",
    "pauldron": "right_pauldron",
    "greave": "right_greave",
    "boot": "right_boot",
    "gauntlet": "right_gauntlet",
}

SLOT_DEFAULT_TARGETS: Dict[str, Tuple[str, str]] = {
    "right_hand": ("RightHand", "RightGripAttachment"),
    "left_hand": ("LeftHand", "LeftGripAttachment"),
    "back": ("UpperTorso", "BodyBackAttachment"),
    "front": ("UpperTorso", "BodyFrontAttachment"),
    "head": ("Head", "HatAttachment"),
    "hair": ("Head", "HairAttachment"),
    "face": ("Head", "FaceFrontAttachment"),
    "waist": ("LowerTorso", "WaistCenterAttachment"),
    "waist_back": ("LowerTorso", "WaistBackAttachment"),
    "waist_front": ("LowerTorso", "WaistFrontAttachment"),
    "hip_left": ("LowerTorso", "WaistCenterAttachment"),
    "hip_right": ("LowerTorso", "WaistCenterAttachment"),
    "left_collar": ("UpperTorso", "LeftCollarAttachment"),
    "right_collar": ("UpperTorso", "RightCollarAttachment"),
    "shoulder_pet": ("UpperTorso", "RightCollarAttachment"),
    "left_shoulder": ("LeftUpperArm", "LeftShoulderAttachment"),
    "right_shoulder": ("RightUpperArm", "RightShoulderAttachment"),
    "left_foot": ("LeftFoot", "LeftFootAttachment"),
    "right_foot": ("RightFoot", "RightFootAttachment"),
}

VALID_ATTACH_MODES: Tuple[str, ...] = (
    "accessory_rigid",
    "tool_grip",
    "motor6d_weapon",
    "holster_back",
    "holster_hip",
    "shield_back",
    "armor_set",
    "two_hand_ik",
    "verify",
)

ATTACH_MODE_ALIASES: Dict[str, str] = {
    "rigid": "accessory_rigid",
    "bone": "accessory_rigid",
    "accessory": "accessory_rigid",
    "skinned": "armor_set",
    "skinned_armor": "armor_set",
    "armor": "armor_set",
    "armature": "armor_set",
    "two_handed_ik": "two_hand_ik",
}


def _normalize_attach_mode(mode: Optional[str], default: str = "accessory_rigid") -> str:
    raw = (mode or default).strip().lower()
    return ATTACH_MODE_ALIASES.get(raw, raw)


def _norm_vec3(val: Optional[Iterable[float]], default: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> List[float]:
    if val is None:
        return [float(default[0]), float(default[1]), float(default[2])]
    seq = list(val)
    if len(seq) != 3:
        raise ValueError(f"Expected 3-element vector, got {seq!r}")
    return [round(float(seq[0]), 6), round(float(seq[1]), 6), round(float(seq[2]), 6)]


def _rot_mat9_to_deg3(m9: Iterable[float]) -> List[float]:
    vals = [float(v) for v in m9]
    if len(vals) != 9:
        raise ValueError(f"Expected 9-element rotation matrix, got {vals!r}")
    r00, r01, r02, r10, r11, r12, _r20, _r21, r22 = vals
    if r02 >= 0.99999:
        ry = math.pi * 0.5
        rx = math.atan2(r10, r11)
        rz = 0.0
    elif r02 <= -0.99999:
        ry = -math.pi * 0.5
        rx = math.atan2(-r10, r11)
        rz = 0.0
    else:
        ry = math.asin(max(-1.0, min(1.0, r02)))
        rx = math.atan2(-r12, r22)
        rz = math.atan2(-r01, r00)
    return [round(math.degrees(rx), 4), round(math.degrees(ry), 4), round(math.degrees(rz), 4)]


def _cframe_luau_expr(pos: List[float], rot_deg: List[float]) -> str:
    px, py, pz = (float(pos[0]), float(pos[1]), float(pos[2]))
    rx, ry, rz = (math.radians(float(rot_deg[0])), math.radians(float(rot_deg[1])), math.radians(float(rot_deg[2])))
    if abs(rx) < 1e-6 and abs(ry) < 1e-6 and abs(rz) < 1e-6:
        return f"CFrame.new({px:.6g}, {py:.6g}, {pz:.6g})"
    return f"CFrame.new({px:.6g}, {py:.6g}, {pz:.6g}) * CFrame.Angles({rx:.6g}, {ry:.6g}, {rz:.6g})"


def _resolve_armor_slot(slot_name: str) -> str:
    key = (slot_name or "").strip().lower().replace("-", "_")
    return ARMOR_SLOT_ALIASES.get(key, key)


class AttachmentEngine:
    """R15 attachment catalog, validators, Blender sidecar loader & Luau attach compiler."""

    def __init__(self, skills_dir: Path | str, archive_dir: Optional[Path | str] = None) -> None:
        self.skills_dir = Path(skills_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else None

    @staticmethod
    def all_official_attachment_names() -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for limb_map in R15_ATTACHMENTS.values():
            for att_name in limb_map:
                if att_name not in seen:
                    seen.add(att_name)
                    out.append(att_name)
        return out

    def get_catalog(
        self,
        filter_limb: Optional[str] = None,
        filter_preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the official R15 attachment catalog, socket presets, armor slots & valid modes."""
        if filter_limb:
            limbs = {k: v for k, v in R15_ATTACHMENTS.items() if k.lower() == filter_limb.strip().lower()}
        else:
            limbs = R15_ATTACHMENTS

        if filter_preset:
            presets = {k: v for k, v in SOCKET_PRESETS.items() if k.lower() == filter_preset.strip().lower()}
        else:
            presets = SOCKET_PRESETS

        return {
            "ok": True,
            "r15_attachments": limbs,
            "official_attachment_count": sum(len(v) for v in limbs.values()),
            "unique_attachment_names": self.all_official_attachment_names(),
            "socket_presets": presets,
            "armor_slots": ARMOR_SLOTS,
            "armor_slot_aliases": ARMOR_SLOT_ALIASES,
            "valid_modes": list(VALID_ATTACH_MODES),
        }

    def validate_r15_attachment(
        self,
        limb_part: str,
        attachment_name: str,
    ) -> Dict[str, Any]:
        """Check whether `(limb_part, attachment_name)` matches the official R15 attachment catalog."""
        if limb_part not in R15_ATTACHMENTS:
            return {
                "ok": False,
                "valid_limb": False,
                "valid_attachment": False,
                "error": f"Unknown R15 limb part '{limb_part}'. Expected one of {sorted(R15_ATTACHMENTS.keys())}.",
            }
        limb_map = R15_ATTACHMENTS[limb_part]
        if attachment_name not in limb_map:
            return {
                "ok": False,
                "valid_limb": True,
                "valid_attachment": False,
                "limb_part": limb_part,
                "expected_attachments": list(limb_map.keys()),
                "error": f"Attachment '{attachment_name}' is not in official R15 catalog for '{limb_part}'.",
            }
        return {
            "ok": True,
            "valid_limb": True,
            "valid_attachment": True,
            "limb_part": limb_part,
            "attachment_name": attachment_name,
            "spec": limb_map[attachment_name],
        }

    def load_blender_sidecar(self, sidecar: str | Path | Dict[str, Any]) -> Dict[str, Any]:
        """Parse and validate a Blender attachment sidecar JSON file or dictionary."""
        if isinstance(sidecar, dict):
            data = dict(sidecar)
        else:
            p = Path(sidecar)
            if not p.is_file():
                return {"ok": False, "error": f"Attachment sidecar file not found: {p}"}
            data = json.loads(p.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            return {"ok": False, "error": "Sidecar payload must be a JSON object."}

        attachments = data.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            return {"ok": False, "error": "Sidecar missing non-empty 'attachments' array."}

        warnings: List[str] = []
        validated_atts: List[Dict[str, Any]] = []
        for idx, entry in enumerate(attachments):
            if not isinstance(entry, dict) or not entry.get("name"):
                return {"ok": False, "error": f"Sidecar attachment at index {idx} missing 'name'."}
            t_limb = entry.get("target_limb") or data.get("target_limb")
            t_att = entry.get("target_limb_attachment") or data.get("target_limb_attachment")
            if t_limb and t_att:
                check = self.validate_r15_attachment(str(t_limb), str(t_att))
                if not check["ok"]:
                    warnings.append(check["error"])
            pos = _norm_vec3(entry.get("pos"), (0.0, 0.0, 0.0))
            raw_rot = entry.get("rot_deg")
            if raw_rot is not None and len(list(raw_rot)) == 9:
                rot_deg = _rot_mat9_to_deg3(raw_rot)
            elif raw_rot is not None:
                rot_deg = _norm_vec3(raw_rot, (0.0, 0.0, 0.0))
            elif entry.get("rot_matrix") is not None:
                rot_deg = _rot_mat9_to_deg3(entry["rot_matrix"])
            elif isinstance(entry.get("cframe"), (list, tuple)) and len(entry["cframe"]) == 12:
                rot_deg = _rot_mat9_to_deg3(entry["cframe"][3:])
            else:
                rot_deg = [0.0, 0.0, 0.0]
            validated_atts.append({
                "name": str(entry["name"]),
                "role": str(entry.get("role", "primary" if idx == 0 else "secondary")),
                "target_limb": t_limb,
                "target_limb_attachment": t_att,
                "pos": pos,
                "rot_deg": rot_deg,
                "cframe": entry.get("cframe"),
            })

        return {
            "ok": True,
            "schema": data.get("schema", "sharp.attachment_sidecar.v1"),
            "prop_name": data.get("prop_name"),
            "prop_kind": data.get("prop_kind"),
            "attachment_mode": data.get("attachment_mode", "rigid"),
            "slot": data.get("slot"),
            "rig_height_studs": data.get("rig_height_studs"),
            "prop_dimensions_studs": data.get("prop_dimensions_studs"),
            "target_limb": data.get("target_limb"),
            "target_limb_attachment": data.get("target_limb_attachment"),
            "mesh_stats": data.get("mesh_stats"),
            "attachments": validated_atts,
            "warnings": warnings,
        }

    def validate_attachment_spec(
        self,
        *,
        mode: str,
        slot: Optional[str] = None,
        preset: Optional[str] = None,
        limb_part: Optional[str] = None,
        limb_attachment: Optional[str] = None,
        rig_height_studs: Optional[float] = None,
        item_size_studs: Optional[List[float]] = None,
        sidecar: Optional[str | Path | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate mode, slot, preset, R15 target attachment, scale, and optional Blender sidecar."""
        norm_mode = _normalize_attach_mode(mode, "accessory_rigid")
        if norm_mode not in VALID_ATTACH_MODES:
            return {
                "ok": False,
                "error": f"Unknown mode '{mode}'. Valid modes: {', '.join(VALID_ATTACH_MODES)}.",
            }

        issues: List[str] = []
        warnings: List[str] = []
        parsed_sidecar: Optional[Dict[str, Any]] = None

        if sidecar is not None:
            parsed_sidecar = self.load_blender_sidecar(sidecar)
            if not parsed_sidecar["ok"]:
                issues.append(parsed_sidecar["error"])
            else:
                warnings.extend(parsed_sidecar.get("warnings", []))

        if preset and preset.strip().lower() not in SOCKET_PRESETS:
            issues.append(f"Unknown preset '{preset}'. Available: {sorted(SOCKET_PRESETS.keys())}.")

        if norm_mode == "armor_set" and slot and slot.strip().lower() != "all":
            resolved = _resolve_armor_slot(slot)
            if resolved not in ARMOR_SLOTS:
                issues.append(f"Unknown armor slot '{slot}'. Available: {sorted(ARMOR_SLOTS.keys())}.")

        if limb_part and limb_attachment:
            chk = self.validate_r15_attachment(limb_part, limb_attachment)
            if not chk["ok"]:
                warnings.append(chk["error"])

        if rig_height_studs is not None and item_size_studs is not None and len(item_size_studs) == 3:
            if rig_height_studs <= 0:
                issues.append("rig_height_studs must be > 0.")
            else:
                max_dim = max(abs(float(x)) for x in item_size_studs)
                ratio = max_dim / float(rig_height_studs)
                if ratio > 1.8:
                    warnings.append(
                        f"Scale mismatch warning: item max dimension ({max_dim:.2f} studs) is {ratio:.2f}x rig height ({rig_height_studs:.2f} studs)."
                    )
                elif max_dim > 0 and ratio < 0.02:
                    warnings.append(
                        f"Scale mismatch warning: item max dimension ({max_dim:.3f} studs) is tiny ({ratio:.4f}x rig height)."
                    )

        return {
            "ok": len(issues) == 0,
            "mode": norm_mode,
            "issues": issues,
            "warnings": warnings,
            "sidecar": parsed_sidecar,
        }

    def _resolve_attach_params(
        self,
        *,
        mode: str,
        slot: Optional[str],
        preset: Optional[str],
        limb_part: Optional[str],
        limb_attachment: Optional[str],
        item_attachment: Optional[str],
        offset_pos: Optional[Iterable[float]],
        offset_rot_deg: Optional[Iterable[float]],
        foregrip_offset_pos: Optional[Iterable[float]],
        foregrip_offset_rot_deg: Optional[Iterable[float]],
        sidecar_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        preset_key = (preset or "").strip().lower()
        preset_cfg = SOCKET_PRESETS.get(preset_key, {})

        resolved_limb = limb_part
        resolved_limb_att = limb_attachment
        resolved_item_att = item_attachment
        pos = [0.0, 0.0, 0.0]
        rot = [0.0, 0.0, 0.0]
        tool_grip_pos = [0.0, 0.0, 0.0]
        tool_grip_rot = [-90.0, 0.0, 0.0]
        ik_cfg: Dict[str, Any] = dict(preset_cfg.get("two_hand_ik") or {})

        # Apply sidecar primary/foregrip defaults if provided
        sidecar_primary: Optional[Dict[str, Any]] = None
        sidecar_foregrip: Optional[Dict[str, Any]] = None
        if sidecar_data and sidecar_data.get("ok"):
            atts = sidecar_data.get("attachments", [])
            if atts:
                sidecar_primary = atts[0]
                for a in atts[1:]:
                    if "foregrip" in a["name"].lower() or "offhand" in a["name"].lower() or "nock" in a["name"].lower():
                        sidecar_foregrip = a
                        break
            if not resolved_limb:
                resolved_limb = sidecar_data.get("target_limb") or (sidecar_primary or {}).get("target_limb")
            if not resolved_limb_att:
                resolved_limb_att = sidecar_data.get("target_limb_attachment") or (sidecar_primary or {}).get("target_limb_attachment")
            if not resolved_item_att and sidecar_primary:
                resolved_item_att = sidecar_primary["name"]

        norm_slot = (slot or "").strip().lower()
        if mode == "holster_back":
            hol = (preset_cfg.get("holster") or {}).get("back")
            if hol:
                resolved_limb = resolved_limb or hol["limb_part"]
                resolved_limb_att = resolved_limb_att or hol["limb_attachment"]
                resolved_item_att = resolved_item_att or hol["item_attachment"]
                pos = list(hol["offset_pos"])
                rot = list(hol["offset_rot_deg"])
            else:
                resolved_limb = resolved_limb or "UpperTorso"
                resolved_limb_att = resolved_limb_att or "BodyBackAttachment"
                resolved_item_att = resolved_item_att or "HolsterBackAttachment"
                pos = [0.15, 0.1, 0.12]
                rot = [0.0, 0.0, -32.0]
        elif mode == "holster_hip":
            side_key = "hip_right" if "right" in norm_slot else "hip_left"
            hol = (preset_cfg.get("holster") or {}).get(side_key)
            if hol:
                resolved_limb = resolved_limb or hol["limb_part"]
                resolved_limb_att = resolved_limb_att or hol["limb_attachment"]
                resolved_item_att = resolved_item_att or hol["item_attachment"]
                pos = list(hol["offset_pos"])
                rot = list(hol["offset_rot_deg"])
            else:
                x_sign = 1.0 if side_key == "hip_right" else -1.0
                resolved_limb = resolved_limb or "LowerTorso"
                resolved_limb_att = resolved_limb_att or "WaistCenterAttachment"
                resolved_item_att = resolved_item_att or "HolsterHipAttachment"
                pos = [1.08 * x_sign, -0.05, 0.15]
                rot = [55.0, 0.0, 8.0 * x_sign]
        elif mode == "shield_back":
            hol = (SOCKET_PRESETS["shield"].get("holster") or {})["back"]
            resolved_limb = resolved_limb or hol["limb_part"]
            resolved_limb_att = resolved_limb_att or hol["limb_attachment"]
            resolved_item_att = resolved_item_att or hol["item_attachment"]
            pos = list(hol["offset_pos"])
            rot = list(hol["offset_rot_deg"])
        elif mode == "armor_set":
            armor_key = _resolve_armor_slot(norm_slot or "chest")
            armor_cfg = ARMOR_SLOTS.get(armor_key, ARMOR_SLOTS["chest"])
            resolved_limb = resolved_limb or armor_cfg["limb_part"]
            resolved_limb_att = resolved_limb_att or armor_cfg["limb_attachment"]
            resolved_item_att = resolved_item_att or armor_cfg["item_attachment"]
            pos = list(armor_cfg["offset_pos"])
            rot = list(armor_cfg["offset_rot_deg"])
        else:
            if preset_cfg:
                resolved_limb = resolved_limb or preset_cfg["limb_part"]
                resolved_limb_att = resolved_limb_att or preset_cfg["limb_attachment"]
                resolved_item_att = resolved_item_att or preset_cfg["item_attachment"]
                pos = list(preset_cfg.get("offset_pos", [0.0, 0.0, 0.0]))
                rot = list(preset_cfg.get("offset_rot_deg", [0.0, 0.0, 0.0]))
                tg = preset_cfg.get("tool_grip") or {}
                tool_grip_pos = list(tg.get("pos", [0.0, 0.0, 0.0]))
                tool_grip_rot = list(tg.get("rot_deg", [-90.0, 0.0, 0.0]))
            elif norm_slot in SLOT_DEFAULT_TARGETS:
                dl, dla = SLOT_DEFAULT_TARGETS[norm_slot]
                resolved_limb = resolved_limb or dl
                resolved_limb_att = resolved_limb_att or dla

        resolved_limb = resolved_limb or "RightHand"
        resolved_limb_att = resolved_limb_att or (
            next(iter(R15_ATTACHMENTS.get(resolved_limb, {})), "RightGripAttachment")
        )
        resolved_item_att = resolved_item_att or "GripAttachment"

        if sidecar_primary is not None and offset_pos is None and offset_rot_deg is None:
            # Sidecar defines the attachment local offset on the item directly;
            # store item_att_pos/rot directly so item attachment keeps sidecar CFrame.
            item_att_pos = list(sidecar_primary["pos"])
            item_att_rot = list(sidecar_primary["rot_deg"])
            use_direct_item_att = True
        else:
            use_direct_item_att = False
            item_att_pos = [0.0, 0.0, 0.0]
            item_att_rot = [0.0, 0.0, 0.0]

        if offset_pos is not None:
            pos = _norm_vec3(offset_pos)
        if offset_rot_deg is not None:
            rot = _norm_vec3(offset_rot_deg)

        # Resolve foregrip & IK chain defaults
        fg_name = ik_cfg.get("foregrip_attachment", "ForegripAttachment")
        fg_pos = list(ik_cfg.get("foregrip_pos", [0.0, -0.55, 0.0]))
        fg_rot = list(ik_cfg.get("foregrip_rot_deg", [0.0, 0.0, 0.0]))
        if sidecar_foregrip is not None and foregrip_offset_pos is None:
            fg_name = sidecar_foregrip["name"]
            fg_pos = list(sidecar_foregrip["pos"])
            fg_rot = list(sidecar_foregrip["rot_deg"])
        if foregrip_offset_pos is not None:
            fg_pos = _norm_vec3(foregrip_offset_pos)
        if foregrip_offset_rot_deg is not None:
            fg_rot = _norm_vec3(foregrip_offset_rot_deg)

        limb_att_spec = R15_ATTACHMENTS.get(resolved_limb, {}).get(
            resolved_limb_att, {"pos": [0.0, 0.0, 0.0], "rot_deg": [0.0, 0.0, 0.0]}
        )

        return {
            "limb_part": resolved_limb,
            "limb_attachment": resolved_limb_att,
            "limb_attachment_default_pos": list(limb_att_spec["pos"]),
            "limb_attachment_default_rot": list(limb_att_spec["rot_deg"]),
            "item_attachment": resolved_item_att,
            "rel_offset_pos": pos,
            "rel_offset_rot_deg": rot,
            "use_direct_item_att": use_direct_item_att,
            "item_att_pos": item_att_pos,
            "item_att_rot": item_att_rot,
            "tool_grip_pos": tool_grip_pos,
            "tool_grip_rot_deg": tool_grip_rot,
            "ik": {
                "chain_root": ik_cfg.get("chain_root", "LeftUpperArm"),
                "end_effector": ik_cfg.get("end_effector", "LeftHand"),
                "foregrip_attachment": fg_name,
                "foregrip_pos": fg_pos,
                "foregrip_rot_deg": fg_rot,
                "pole_limb": ik_cfg.get("pole_limb", "UpperTorso"),
                "pole_pos": list(ik_cfg.get("pole_pos", [-1.5, 0.0, 1.1])),
            },
        }

    def compile_verify_luau(
        self,
        rig_path: str = "Workspace.Rig",
        item_path: Optional[str] = None,
        required_slots: Optional[List[str]] = None,
        expected_rig_height: float = 5.0,
    ) -> str:
        """Compile a read-only Edit-mode Luau verification script inspecting rig & equipment health."""
        official_names = self.all_official_attachment_names()
        slot_targets: List[Dict[str, str]] = []
        for s in required_slots or []:
            key = s.strip().lower()
            if key in SLOT_DEFAULT_TARGETS:
                lp, la = SLOT_DEFAULT_TARGETS[key]
                slot_targets.append({"slot": key, "limb": lp, "attachment": la})
            elif _resolve_armor_slot(key) in ARMOR_SLOTS:
                ac = ARMOR_SLOTS[_resolve_armor_slot(key)]
                slot_targets.append({"slot": key, "limb": ac["limb_part"], "attachment": ac["limb_attachment"]})

        core_checks = [
            {"limb": limb, "attachment": att}
            for limb, atts in R15_ATTACHMENTS.items()
            for att, meta in atts.items()
            if meta["category"] in ("accessory", "grip")
        ]

        return f"""--!strict
local HttpService = game:GetService("HttpService")

local TARGET_RIG_PATH = {json.dumps(rig_path)}
local TARGET_ITEM_PATH = {json.dumps(item_path or "")}
local EXPECTED_RIG_HEIGHT = {float(expected_rig_height)}
local OFFICIAL_R15_SET: {{ [string]: boolean }} = {{ {", ".join(f"[{json.dumps(n)}] = true" for n in official_names)} }}
local CORE_R15_CHECKS: {{ any }} = HttpService:JSONDecode({json.dumps(json.dumps(core_checks))})
local REQUIRED_SLOT_CHECKS: {{ any }} = HttpService:JSONDecode({json.dumps(json.dumps(slot_targets))})

local function resolveInstance(pathStr: string): Instance?
	if pathStr == "" then
		return nil
	end
	local curr: Instance = game
	local first = true
	for seg in string.gmatch(pathStr, "[^%.]+") do
		if first and seg == "game" then
			first = false
			continue
		end
		local nxt: Instance? = nil
		if first and curr == game then
			local okSvc, svc = pcall(function()
				return game:GetService(seg)
			end)
			nxt = if okSvc then svc else curr:FindFirstChild(seg)
		else
			nxt = curr:FindFirstChild(seg)
		end
		first = false
		if not nxt then
			return nil
		end
		curr = nxt
	end
	return curr
end

local rig = resolveInstance(TARGET_RIG_PATH)
if not rig then
	return HttpService:JSONEncode({{
		ok = false,
		mode = "verify",
		error = "Rig not found at path: " .. TARGET_RIG_PATH,
	}})
end

local rootPart = if rig:IsA("Model")
	then (rig.PrimaryPart or rig:FindFirstChild("HumanoidRootPart") or rig:FindFirstChildWhichIsA("BasePart"))
	elseif rig:IsA("BasePart") then rig
	else nil

local rootCf = if rootPart and rootPart:IsA("BasePart") then rootPart.CFrame else CFrame.identity

local rigExtentY = EXPECTED_RIG_HEIGHT
if rig:IsA("Model") then
	local okBox, _, sz = pcall(function()
		return rig:GetBoundingBox()
	end)
	if okBox and typeof(sz) == "Vector3" then
		rigExtentY = sz.Y
	end
end

local itemInst = if TARGET_ITEM_PATH ~= "" then resolveInstance(TARGET_ITEM_PATH) else nil

local issues: {{ string }} = {{}}
local warnings: {{ string }} = {{}}
local attachmentWorldOffsets: {{ any }} = {{}}
local physicsFlags: {{ any }} = {{}}
local conflictingJoints: {{ any }} = {{}}
local missingSlots: {{ any }} = {{}}
local ikControls: {{ any }} = {{}}

local function collectAttachments(container: Instance, originLabel: string)
	for _, desc in ipairs(container:GetDescendants()) do
		if desc:IsA("Attachment") then
			local p = desc.Parent
			local parentName = if p then p.Name else ""
			local wp = desc.WorldPosition
			local rel = rootCf:PointToObjectSpace(wp)
			table.insert(attachmentWorldOffsets, {{
				origin = originLabel,
				name = desc.Name,
				parentPart = parentName,
				path = desc:GetFullName(),
				localPos = {{ desc.Position.X, desc.Position.Y, desc.Position.Z }},
				worldPos = {{ wp.X, wp.Y, wp.Z }},
				offsetFromRoot = {{ rel.X, rel.Y, rel.Z }},
				inOfficialR15Catalog = OFFICIAL_R15_SET[desc.Name] == true,
			}})
		end
	end
end

collectAttachments(rig, "rig")
if itemInst and not itemInst:IsDescendantOf(rig) then
	collectAttachments(itemInst, "item")
end

-- Check official R15 slots on present limbs
for _, chk in ipairs(CORE_R15_CHECKS) do
	local limb = rig:FindFirstChild(chk.limb, true)
	if limb and limb:IsA("BasePart") then
		if not limb:FindFirstChild(chk.attachment) then
			table.insert(missingSlots, {{
				kind = "r15_core",
				limb = chk.limb,
				attachment = chk.attachment,
			}})
		end
	end
end

for _, req in ipairs(REQUIRED_SLOT_CHECKS) do
	local limb = rig:FindFirstChild(req.limb, true)
	if not limb or not limb:IsA("BasePart") then
		table.insert(missingSlots, {{
			kind = "required_slot_missing_limb",
			slot = req.slot,
			limb = req.limb,
			attachment = req.attachment,
		}})
		table.insert(issues, "Missing R15 limb '" .. req.limb .. "' for slot '" .. req.slot .. "'.")
	elseif not limb:FindFirstChild(req.attachment) then
		table.insert(missingSlots, {{
			kind = "required_slot_missing_attachment",
			slot = req.slot,
			limb = req.limb,
			attachment = req.attachment,
		}})
		table.insert(issues, "Missing attachment '" .. req.attachment .. "' on '" .. req.limb .. "'.")
	end
end

-- Check equipment physics flags & competing joints
local R15_CORE_PARTS: {{ [string]: boolean }} = {{
	HumanoidRootPart = true, LowerTorso = true, UpperTorso = true, Head = true,
	LeftUpperArm = true, LeftLowerArm = true, LeftHand = true,
	RightUpperArm = true, RightLowerArm = true, RightHand = true,
	LeftUpperLeg = true, LeftLowerLeg = true, LeftFoot = true,
	RightUpperLeg = true, RightLowerLeg = true, RightFoot = true,
}}

local function inspectEquipPart(part: BasePart)
	local hasPhys = part.CustomPhysicalProperties ~= nil
	table.insert(physicsFlags, {{
		name = part.Name,
		path = part:GetFullName(),
		anchored = part.Anchored,
		massless = part.Massless,
		canCollide = part.CanCollide,
		hasCustomPhysicalProperties = hasPhys,
	}})
	if part.Anchored then
		table.insert(issues, "Attached equipment part '" .. part:GetFullName() .. "' is Anchored=true (blocks Motor6D/RigidConstraint motion).")
	end
	if not part.Massless then
		table.insert(warnings, "Equipment part '" .. part:GetFullName() .. "' has Massless=false (can bias character physics).")
	end
	if part.CanCollide then
		table.insert(warnings, "Equipment part '" .. part:GetFullName() .. "' has CanCollide=true (may collide with character/world).")
	end
end

for _, desc in ipairs(rig:GetDescendants()) do
	if desc:IsA("BasePart") then
		local parentInst = desc.Parent
		local isEquip = (not R15_CORE_PARTS[desc.Name])
			or (parentInst ~= nil and (parentInst:IsA("Accessory") or parentInst:IsA("Tool")))
		if isEquip and (desc.Parent ~= rig or not R15_CORE_PARTS[desc.Name]) then
			inspectEquipPart(desc)
		end
	end
end
if itemInst and not itemInst:IsDescendantOf(rig) then
	if itemInst:IsA("BasePart") then
		inspectEquipPart(itemInst)
	else
		for _, desc in ipairs(itemInst:GetDescendants()) do
			if desc:IsA("BasePart") then
				inspectEquipPart(desc)
			end
		end
	end
end

-- Detect welds/constraints that fight each other on the same target part
local partBinders: {{ [BasePart]: {{ any }} }} = {{}}
local function recordBinder(targetPart: BasePart?, kind: string, inst: Instance, partner: BasePart?)
	if not targetPart then
		return
	end
	local list = partBinders[targetPart]
	if not list then
		list = {{}}
		partBinders[targetPart] = list
	end
	table.insert(list, {{ kind = kind, name = inst.Name, path = inst:GetFullName(), partner = if partner then partner.Name else "" }})
end

local function scanBinders(container: Instance)
	for _, desc in ipairs(container:GetDescendants()) do
		if desc:IsA("RigidConstraint") then
			local p0 = if desc.Attachment0 and desc.Attachment0.Parent and desc.Attachment0.Parent:IsA("BasePart")
				then desc.Attachment0.Parent else nil
			local p1 = if desc.Attachment1 and desc.Attachment1.Parent and desc.Attachment1.Parent:IsA("BasePart")
				then desc.Attachment1.Parent else nil
			if desc.Enabled then
				recordBinder(p0, "RigidConstraint", desc, p1)
			end
			if not p0 or not p1 then
				table.insert(conflictingJoints, {{
					kind = "dangling_rigid_constraint",
					path = desc:GetFullName(),
					message = "RigidConstraint missing Attachment0 or Attachment1 BasePart.",
				}})
				table.insert(issues, "Dangling RigidConstraint at " .. desc:GetFullName())
			end
		elseif desc:IsA("Motor6D") then
			if desc.Enabled then
				recordBinder(desc.Part1, "Motor6D", desc, desc.Part0)
			end
			if desc.Part1 and desc.Part1.Anchored then
				table.insert(conflictingJoints, {{
					kind = "anchored_motor6d_part1",
					path = desc:GetFullName(),
					part1 = desc.Part1:GetFullName(),
				}})
				table.insert(issues, "Motor6D Part1 is Anchored: " .. desc.Part1:GetFullName())
			end
		elseif desc:IsA("Weld") or desc:IsA("WeldConstraint") then
			if desc.Enabled then
				recordBinder(desc.Part1, desc.ClassName, desc, desc.Part0)
			end
		elseif desc:IsA("IKControl") then
			table.insert(ikControls, {{
				name = desc.Name,
				path = desc:GetFullName(),
				enabled = desc.Enabled,
				weight = desc.Weight,
				smoothTime = desc.SmoothTime,
				hasChainRoot = desc.ChainRoot ~= nil,
				hasEndEffector = desc.EndEffector ~= nil,
				hasTarget = desc.Target ~= nil,
			}})
			if desc.Enabled and (not desc.ChainRoot or not desc.EndEffector or not desc.Target) then
				table.insert(issues, "Enabled IKControl missing ChainRoot/EndEffector/Target: " .. desc:GetFullName())
			end
		end
	end
end

scanBinders(rig)
if itemInst and not itemInst:IsDescendantOf(rig) then
	scanBinders(itemInst)
end

for part, binders in pairs(partBinders) do
	if #binders > 1 then
		local hasMotor = false
		local hasWeld = false
		local hasRigid = false
		for _, b in ipairs(binders) do
			if b.kind == "Motor6D" then hasMotor = true end
			if b.kind == "Weld" or b.kind == "WeldConstraint" then hasWeld = true end
			if b.kind == "RigidConstraint" then hasRigid = true end
		end
		if (hasMotor and (hasWeld or hasRigid)) or #binders > 1 then
			table.insert(conflictingJoints, {{
				kind = "competing_joints",
				targetPart = part:GetFullName(),
				binders = binders,
			}})
			table.insert(issues, "Multiple constraints/joints target '" .. part:GetFullName() .. "' (fighting welds).")
		end
	end
end

-- Scale mismatch analysis vs rig height
local itemExtentMax = 0
local scaleMismatch = {{
	rigHeightStuds = rigExtentY,
	expectedClassicR15Height = EXPECTED_RIG_HEIGHT,
	rigScaleRatio = rigExtentY / math.max(0.001, EXPECTED_RIG_HEIGHT),
	itemMaxDimStuds = 0,
	itemToRigRatio = 0,
	status = "ok",
}}

if rigExtentY < 1.0 or rigExtentY > 25.0 then
	scaleMismatch.status = "warn_rig_scale"
	table.insert(warnings, string.format("Rig height %.2f studs differs significantly from standard R15 (%.2f studs).", rigExtentY, EXPECTED_RIG_HEIGHT))
end

local measureTarget = itemInst
if measureTarget then
	local sz = Vector3.zero
	if measureTarget:IsA("BasePart") then
		sz = measureTarget.Size
	elseif measureTarget:IsA("Model") then
		local okM, _, bsz = pcall(function() return measureTarget:GetBoundingBox() end)
		if okM and typeof(bsz) == "Vector3" then sz = bsz end
	end
	itemExtentMax = math.max(sz.X, sz.Y, sz.Z)
	scaleMismatch.itemMaxDimStuds = itemExtentMax
	scaleMismatch.itemToRigRatio = itemExtentMax / math.max(0.001, rigExtentY)
	if itemExtentMax > rigExtentY * 1.8 then
		scaleMismatch.status = "error_item_oversized"
		table.insert(issues, string.format("Item max dimension (%.2f studs) is %.2fx rig height (possible 100x Blender scale bug).", itemExtentMax, scaleMismatch.itemToRigRatio))
	elseif itemExtentMax > 0 and itemExtentMax < rigExtentY * 0.02 then
		scaleMismatch.status = "warn_item_tiny"
		table.insert(warnings, string.format("Item max dimension (%.3f studs) is very small vs rig height (%.2f studs).", itemExtentMax, rigExtentY))
	end
end

return HttpService:JSONEncode({{
	ok = true,
	mode = "verify",
	passed = (#issues == 0),
	rigPath = rig:GetFullName(),
	itemPath = if itemInst then itemInst:GetFullName() else nil,
	issues = issues,
	warnings = warnings,
	attachmentWorldOffsets = attachmentWorldOffsets,
	physicsFlags = physicsFlags,
	conflictingJoints = conflictingJoints,
	missingSlots = missingSlots,
	scaleMismatch = scaleMismatch,
	ikControls = ikControls,
}})
"""

    def compile_inspect_attachment_fit_luau(
        self,
        rig_path: str = "Workspace.Rig",
        item_path: str = "",
        test_pose: str = "raised_arm",
        clearance_margin_studs: float = 0.02,
    ) -> str:
        """Compile read-only Edit-mode Luau computing OBB limb clearance/penetration in rest and action poses."""
        pose_key = (test_pose or "raised_arm").strip().lower().replace("-", "_").replace(" ", "_")
        margin = max(0.0, float(clearance_margin_studs))
        return f"""--!strict
local HttpService = game:GetService("HttpService")

local TARGET_RIG_PATH = {json.dumps(rig_path)}
local TARGET_ITEM_PATH = {json.dumps(item_path or "")}
local TEST_POSE = {json.dumps(pose_key)}
local CLEARANCE_MARGIN = {margin:.6g}

local function resolveInstance(pathStr: string): Instance?
	if pathStr == "" then
		return nil
	end
	local curr: Instance = game
	local first = true
	for seg in string.gmatch(pathStr, "[^%.]+") do
		if first and seg == "game" then
			first = false
			continue
		end
		local nxt: Instance? = nil
		if first and curr == game then
			local okSvc, svc = pcall(function()
				return game:GetService(seg)
			end)
			nxt = if okSvc then svc else curr:FindFirstChild(seg)
		else
			nxt = curr:FindFirstChild(seg)
		end
		first = false
		if not nxt then
			return nil
		end
		curr = nxt
	end
	return curr
end

local rig = resolveInstance(TARGET_RIG_PATH)
if not rig then
	return HttpService:JSONEncode({{
		ok = false,
		rigPath = TARGET_RIG_PATH,
		itemPath = if TARGET_ITEM_PATH ~= "" then TARGET_ITEM_PATH else nil,
		testPose = TEST_POSE,
		error = "Rig not found at path: " .. TARGET_RIG_PATH,
	}})
end

local itemInst: Instance? = nil
if TARGET_ITEM_PATH ~= "" then
	itemInst = resolveInstance(TARGET_ITEM_PATH) or rig:FindFirstChild(TARGET_ITEM_PATH, true)
	if not itemInst and TARGET_ITEM_PATH ~= "Workspace.EquipmentItem" then
		return HttpService:JSONEncode({{
			ok = false,
			rigPath = rig:GetFullName(),
			itemPath = TARGET_ITEM_PATH,
			testPose = TEST_POSE,
			error = "Item not found at path: " .. TARGET_ITEM_PATH,
		}})
	end
end

local R15_CORE_SET: {{ [string]: boolean }} = {{
	HumanoidRootPart = true, LowerTorso = true, UpperTorso = true, Head = true,
	LeftUpperArm = true, LeftLowerArm = true, LeftHand = true,
	RightUpperArm = true, RightLowerArm = true, RightHand = true,
	LeftUpperLeg = true, LeftLowerLeg = true, LeftFoot = true,
	RightUpperLeg = true, RightLowerLeg = true, RightFoot = true,
}}

local CHECK_LIMBS: {{ string }} = {{
	"LowerTorso", "UpperTorso", "Head",
	"LeftUpperArm", "LeftLowerArm", "LeftHand",
	"RightUpperArm", "RightLowerArm", "RightHand",
	"LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
	"RightUpperLeg", "RightLowerLeg", "RightFoot",
}}

local limbParts: {{ [string]: BasePart }} = {{}}
for _, limbName in ipairs(CHECK_LIMBS) do
	local found = rig:FindFirstChild(limbName, true)
	if found and found:IsA("BasePart") then
		limbParts[limbName] = found
	end
end
local hrpInst = rig:FindFirstChild("HumanoidRootPart", true)
local rootPart: BasePart? = if hrpInst and hrpInst:IsA("BasePart")
	then hrpInst
	elseif rig:IsA("Model") and rig.PrimaryPart then rig.PrimaryPart
	else rig:FindFirstChildWhichIsA("BasePart", true)

if not rootPart then
	return HttpService:JSONEncode({{
		ok = false,
		rigPath = rig:GetFullName(),
		itemPath = if itemInst then itemInst:GetFullName() else nil,
		testPose = TEST_POSE,
		error = "Rig has no BasePart.",
	}})
end

local equipParts: {{ BasePart }} = {{}}
local equipSeen: {{ [BasePart]: boolean }} = {{}}
local function addEquipPart(p: BasePart)
	if not equipSeen[p] then
		equipSeen[p] = true
		table.insert(equipParts, p)
	end
end

local function isInRig(inst: Instance?): boolean
	return inst ~= nil and (inst == rig or inst:IsDescendantOf(rig))
end

local function addPartnerModelOrParts(partner: BasePart)
	if partner:IsA("Terrain") or isInRig(partner) then
		return
	end
	local container: Instance = partner
	local cur: Instance? = partner.Parent
	while cur and cur ~= workspace and cur ~= game and cur ~= rig do
		if cur:IsA("Model") or cur:IsA("Accessory") or cur:IsA("Tool") then
			if not rig:IsDescendantOf(cur) then
				container = cur
			end
			break
		end
		cur = cur.Parent
	end
	if container:IsA("BasePart") and not container:IsA("Terrain") and not isInRig(container) then
		addEquipPart(container)
	end
	for _, sub in ipairs(container:GetDescendants()) do
		if sub:IsA("BasePart") and not sub:IsA("Terrain") and not isInRig(sub) then
			addEquipPart(sub)
		end
	end
end

if itemInst then
	if itemInst:IsA("BasePart") then
		addEquipPart(itemInst)
	else
		for _, d in ipairs(itemInst:GetDescendants()) do
			if d:IsA("BasePart") then
				addEquipPart(d)
			end
		end
	end
else
	for _, d in ipairs(rig:GetDescendants()) do
		if d:IsA("BasePart") then
			local par = d.Parent
			local isEquip = (not R15_CORE_SET[d.Name])
				or (par ~= nil and (par:IsA("Accessory") or par:IsA("Tool")))
			if isEquip and (d.Parent ~= rig or not R15_CORE_SET[d.Name]) then
				addEquipPart(d)
			end
		end
	end
	if #equipParts == 0 then
		for _, d in ipairs(workspace:GetDescendants()) do
			local p0: Instance? = nil
			local p1: Instance? = nil
			if d:IsA("Motor6D") and d.Enabled then
				p0 = d.Part0
				p1 = d.Part1
			elseif d:IsA("Weld") and d.Enabled then
				p0 = d.Part0
				p1 = d.Part1
			elseif d:IsA("WeldConstraint") and d.Enabled then
				p0 = d.Part0
				p1 = d.Part1
			elseif d:IsA("RigidConstraint") and d.Enabled and d.Attachment0 and d.Attachment1 then
				p0 = d.Attachment0.Parent
				p1 = d.Attachment1.Parent
			end
			if p0 and p1 and p0:IsA("BasePart") and p1:IsA("BasePart") then
				local in0 = isInRig(p0)
				local in1 = isInRig(p1)
				if in0 and not in1 then
					addPartnerModelOrParts(p1)
				elseif in1 and not in0 then
					addPartnerModelOrParts(p0)
				end
			end
		end
	end
end

-- Build attachment/joint graph so equipment parts inherit host limb kinematics across poses
local equipParentMap: {{ [BasePart]: BasePart }} = {{}}
local equipPeerLinks: {{ [BasePart]: {{ BasePart }} }} = {{}}
local function addPeerLink(a: BasePart, b: BasePart)
	local list = equipPeerLinks[a]
	if not list then
		list = {{}}
		equipPeerLinks[a] = list
	end
	table.insert(list, b)
end
local function recordJointPair(child: BasePart, parent: BasePart, allowOverwrite: boolean)
	if R15_CORE_SET[parent.Name] and parent.Name ~= "HumanoidRootPart" and isInRig(parent) then
		equipParentMap[child] = parent
	elseif allowOverwrite or not equipParentMap[child] then
		equipParentMap[child] = parent
	end
end
local function scanJointLinks(container: Instance)
	for _, d in ipairs(container:GetDescendants()) do
		if d:IsA("Motor6D") and d.Part0 and d.Part1 and d.Enabled then
			if equipSeen[d.Part1] or not R15_CORE_SET[d.Part1.Name] then
				recordJointPair(d.Part1, d.Part0, true)
			end
			if equipSeen[d.Part0] and equipSeen[d.Part1] then
				addPeerLink(d.Part0, d.Part1)
				addPeerLink(d.Part1, d.Part0)
			end
		elseif d:IsA("Weld") and d.Part0 and d.Part1 and d.Enabled then
			if equipSeen[d.Part0] and equipSeen[d.Part1] then
				addPeerLink(d.Part0, d.Part1)
				addPeerLink(d.Part1, d.Part0)
			elseif equipSeen[d.Part1] then
				recordJointPair(d.Part1, d.Part0, false)
			elseif equipSeen[d.Part0] then
				recordJointPair(d.Part0, d.Part1, false)
			end
		elseif d:IsA("WeldConstraint") and d.Part0 and d.Part1 and d.Enabled then
			if equipSeen[d.Part0] and equipSeen[d.Part1] then
				addPeerLink(d.Part0, d.Part1)
				addPeerLink(d.Part1, d.Part0)
			elseif equipSeen[d.Part1] then
				recordJointPair(d.Part1, d.Part0, false)
			elseif equipSeen[d.Part0] then
				recordJointPair(d.Part0, d.Part1, false)
			end
		elseif d:IsA("RigidConstraint") and d.Enabled and d.Attachment0 and d.Attachment1 then
			local p0 = d.Attachment0.Parent
			local p1 = d.Attachment1.Parent
			if p0 and p1 and p0:IsA("BasePart") and p1:IsA("BasePart") then
				if equipSeen[p0] and equipSeen[p1] then
					addPeerLink(p0, p1)
					addPeerLink(p1, p0)
				elseif equipSeen[p0] then
					recordJointPair(p0, p1, false)
				elseif equipSeen[p1] then
					recordJointPair(p1, p0, false)
				end
			end
		end
	end
end
scanJointLinks(rig)
local hasExternalEquip = false
for _, ep in ipairs(equipParts) do
	if not isInRig(ep) then
		hasExternalEquip = true
		break
	end
end
if hasExternalEquip then
	scanJointLinks(workspace)
elseif itemInst and not itemInst:IsDescendantOf(rig) then
	scanJointLinks(itemInst)
end

local function findHostLimb(ep: BasePart): BasePart?
	local visited: {{ [BasePart]: boolean }} = {{}}
	local queue: {{ BasePart }} = {{ ep }}
	visited[ep] = true
	local head = 1
	while head <= #queue and head <= 64 do
		local cur = queue[head]
		head += 1
		local nxt = equipParentMap[cur]
		if nxt then
			if R15_CORE_SET[nxt.Name] and nxt.Name ~= "HumanoidRootPart" and isInRig(nxt) then
				return nxt
			end
			if not visited[nxt] then
				visited[nxt] = true
				table.insert(queue, nxt)
			end
		end
		local peers = equipPeerLinks[cur]
		if peers then
			for _, peer in ipairs(peers) do
				if not visited[peer] then
					visited[peer] = true
					table.insert(queue, peer)
				end
			end
		end
	end
	return nil
end

local equipHost: {{ [BasePart]: BasePart? }} = {{}}
local equipLocalFromHost: {{ [BasePart]: CFrame }} = {{}}
for _, ep in ipairs(equipParts) do
	local h = findHostLimb(ep)
	equipHost[ep] = h
	if h then
		equipLocalFromHost[ep] = h.CFrame:ToObjectSpace(ep.CFrame)
	end
end

local function getActionPoseTransforms(poseKey: string): {{ [string]: CFrame }}
	if poseKey == "slash_windup" then
		return {{
			UpperTorso = CFrame.Angles(math.rad(6), math.rad(-24), 0),
			RightUpperArm = CFrame.Angles(math.rad(-38), math.rad(-22), math.rad(-20)),
			RightLowerArm = CFrame.Angles(math.rad(-50), 0, 0),
			LeftUpperArm = CFrame.Angles(math.rad(24), 0, math.rad(12)),
		}}
	elseif poseKey == "block_guard" then
		return {{
			UpperTorso = CFrame.Angles(math.rad(-14), math.rad(-26), 0),
			LeftUpperArm = CFrame.Angles(math.rad(68), math.rad(36), math.rad(12)),
			LeftLowerArm = CFrame.Angles(math.rad(-84), 0, 0),
		}}
	elseif poseKey == "overhead_reach" then
		return {{
			RightUpperArm = CFrame.Angles(math.rad(145), 0, math.rad(-10)),
			LeftUpperArm = CFrame.Angles(math.rad(145), 0, math.rad(10)),
		}}
	elseif poseKey == "crouch" then
		return {{
			LowerTorso = CFrame.new(0, -0.35, 0) * CFrame.Angles(math.rad(-12), 0, 0),
			LeftUpperLeg = CFrame.Angles(math.rad(42), 0, 0),
			LeftLowerLeg = CFrame.Angles(math.rad(-82), 0, 0),
			RightUpperLeg = CFrame.Angles(math.rad(42), 0, 0),
			RightLowerLeg = CFrame.Angles(math.rad(-82), 0, 0),
		}}
	end
	-- Default raised_arm pose
	return {{
		UpperTorso = CFrame.Angles(math.rad(-8), math.rad(12), 0),
		RightUpperArm = CFrame.Angles(math.rad(82), math.rad(-10), math.rad(-18)),
		RightLowerArm = CFrame.Angles(math.rad(-25), 0, 0),
		LeftUpperArm = CFrame.Angles(math.rad(72), math.rad(10), math.rad(18)),
		LeftLowerArm = CFrame.Angles(math.rad(-28), 0, 0),
	}}
end

local function computeRigPoseCFrames(poseMap: {{ [string]: CFrame }}): {{ [string]: CFrame }}
	local out: {{ [string]: CFrame }} = {{}}
	out[rootPart.Name] = rootPart.CFrame

	local adj: {{ [string]: {{ {{ child: string, c0: CFrame, c1: CFrame }} }} }} = {{}}
	for _, d in ipairs(rig:GetDescendants()) do
		if d:IsA("Motor6D") and d.Part0 and d.Part1 and R15_CORE_SET[d.Part0.Name] and R15_CORE_SET[d.Part1.Name] then
			local list = adj[d.Part0.Name]
			if not list then
				list = {{}}
				adj[d.Part0.Name] = list
			end
			table.insert(list, {{ child = d.Part1.Name, c0 = d.C0, c1 = d.C1 }})
		elseif d:IsA("AnimationConstraint") and d.Attachment0 and d.Attachment1 then
			local p0 = d.Attachment0.Parent
			local p1 = d.Attachment1.Parent
			if p0 and p1 and p0:IsA("BasePart") and p1:IsA("BasePart") and R15_CORE_SET[p0.Name] and R15_CORE_SET[p1.Name] then
				local list = adj[p0.Name]
				if not list then
					list = {{}}
					adj[p0.Name] = list
				end
				table.insert(list, {{ child = p1.Name, c0 = d.Attachment0.CFrame, c1 = d.Attachment1.CFrame }})
			end
		end
	end

	local queue: {{ string }} = {{ rootPart.Name }}
	local idx = 1
	while idx <= #queue do
		local pName = queue[idx]
		idx += 1
		local parentCf = out[pName]
		local edges = adj[pName]
		if parentCf and edges then
			for _, edge in ipairs(edges) do
				if not out[edge.child] then
					local tf = poseMap[edge.child] or CFrame.identity
					out[edge.child] = parentCf * edge.c0 * tf * edge.c1:Inverse()
					table.insert(queue, edge.child)
				end
			end
		end
	end

	for limbName, part in pairs(limbParts) do
		if not out[limbName] then
			out[limbName] = part.CFrame
		end
	end
	return out
end

local function obbSignedGap(cfA: CFrame, sizeA: Vector3, cfB: CFrame, sizeB: Vector3): (number, Vector3)
	local axesA = {{ cfA.RightVector, cfA.UpVector, cfA.LookVector }}
	local axesB = {{ cfB.RightVector, cfB.UpVector, cfB.LookVector }}
	local halfA = sizeA * 0.5
	local halfB = sizeB * 0.5
	local delta = cfB.Position - cfA.Position
	local maxGap = -1e9
	local bestAxis = Vector3.yAxis

	local function testAxis(rawAxis: Vector3)
		local mag = rawAxis.Magnitude
		if mag < 1e-5 then
			return
		end
		local axis = rawAxis / mag
		local d = math.abs(delta:Dot(axis))
		local pA = halfA.X * math.abs(axesA[1]:Dot(axis))
			+ halfA.Y * math.abs(axesA[2]:Dot(axis))
			+ halfA.Z * math.abs(axesA[3]:Dot(axis))
		local pB = halfB.X * math.abs(axesB[1]:Dot(axis))
			+ halfB.Y * math.abs(axesB[2]:Dot(axis))
			+ halfB.Z * math.abs(axesB[3]:Dot(axis))
		local gap = d - (pA + pB)
		if gap > maxGap then
			maxGap = gap
			bestAxis = if delta:Dot(axis) < 0 then -axis else axis
		end
	end

	for i = 1, 3 do
		testAxis(axesA[i])
		testAxis(axesB[i])
	end
	for i = 1, 3 do
		for j = 1, 3 do
			testAxis(axesA[i]:Cross(axesB[j]))
		end
	end
	return maxGap, bestAxis
end

local poseCases: {{ {{ name: string, transforms: {{ [string]: CFrame }} }} }} = {{
	{{ name = "rest", transforms = {{}} }},
	{{ name = TEST_POSE, transforms = getActionPoseTransforms(TEST_POSE) }},
}}

local penetrations: {{ any }} = {{}}
local recommendedOffsets: {{ any }} = {{}}
local minClearanceStuds = 1e9
local checkedPairs = 0

local function r4(n: number): number
	return math.round(n * 10000) / 10000
end

for _, poseCase in ipairs(poseCases) do
	local limbCfs = computeRigPoseCFrames(poseCase.transforms)
	for _, ep in ipairs(equipParts) do
		local host = equipHost[ep]
		local hostName = if host then host.Name else nil
		local equipCf = if (hostName and limbCfs[hostName] and equipLocalFromHost[ep])
			then (limbCfs[hostName] * equipLocalFromHost[ep])
			else ep.CFrame

		for _, limbName in ipairs(CHECK_LIMBS) do
			if limbName ~= hostName and limbParts[limbName] and limbCfs[limbName] then
				checkedPairs += 1
				local gap, pushAxis = obbSignedGap(limbCfs[limbName], limbParts[limbName].Size, equipCf, ep.Size)
				if gap < minClearanceStuds then
					minClearanceStuds = gap
				end
				if gap < -CLEARANCE_MARGIN then
					local penDepth = -gap
					local pushWorld = pushAxis * (penDepth + CLEARANCE_MARGIN)
					local pushLocal = if (hostName and limbCfs[hostName])
						then limbCfs[hostName]:VectorToObjectSpace(pushWorld)
						else pushWorld
					table.insert(penetrations, {{
						pose = poseCase.name,
						itemPart = ep.Name,
						itemPath = ep:GetFullName(),
						hostLimb = hostName,
						limb = limbName,
						penetrationStuds = r4(penDepth),
						clearanceStuds = r4(gap),
						axisWorld = {{ r4(pushAxis.X), r4(pushAxis.Y), r4(pushAxis.Z) }},
					}})
					table.insert(recommendedOffsets, {{
						pose = poseCase.name,
						itemPart = ep.Name,
						hostLimb = hostName,
						collidingLimb = limbName,
						offsetWorld = {{ r4(pushWorld.X), r4(pushWorld.Y), r4(pushWorld.Z) }},
						offsetLocal = {{ r4(pushLocal.X), r4(pushLocal.Y), r4(pushLocal.Z) }},
						suggestedMarginStuds = CLEARANCE_MARGIN,
					}})
				end
			end
		end
	end
end

if checkedPairs == 0 then
	minClearanceStuds = 0
end

return HttpService:JSONEncode({{
	ok = true,
	rigPath = rig:GetFullName(),
	itemPath = if itemInst then itemInst:GetFullName() else nil,
	testPose = TEST_POSE,
	clearanceMarginStuds = CLEARANCE_MARGIN,
	checkedPairs = checkedPairs,
	posesTested = {{ "rest", TEST_POSE }},
	fit_passed = (#penetrations == 0),
	penetrations = penetrations,
	minClearanceStuds = r4(minClearanceStuds),
	recommendedOffsets = recommendedOffsets,
}})
"""

    def compile_attach_luau(
        self,
        rig_path: str = "Workspace.Rig",
        item_path: str = "Workspace.EquipmentItem",
        mode: str = "accessory_rigid",
        slot: Optional[str] = None,
        preset: Optional[str] = None,
        limb_part: Optional[str] = None,
        limb_attachment: Optional[str] = None,
        item_attachment: Optional[str] = None,
        offset_pos: Optional[Iterable[float]] = None,
        offset_rot_deg: Optional[Iterable[float]] = None,
        foregrip_offset_pos: Optional[Iterable[float]] = None,
        foregrip_offset_rot_deg: Optional[Iterable[float]] = None,
        ik_weight: float = 1.0,
        ik_smooth_time: float = 0.08,
        ik_type: str = "Transform",
        create_pole: bool = True,
        attach_primary_in_ik: bool = True,
        replace_existing_welds: bool = True,
        clone_item: bool = False,
        armor_slot_map: Optional[Dict[str, str]] = None,
        sidecar_path: Optional[str] = None,
        sidecar_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compile Edit-mode Luau for attaching, configuring, or verifying R15 equipment & IKControls."""
        norm_mode = _normalize_attach_mode(mode, "accessory_rigid")
        if norm_mode not in VALID_ATTACH_MODES:
            raise ValueError(f"Unsupported mode '{mode}'. Valid: {', '.join(VALID_ATTACH_MODES)}")

        if norm_mode == "verify":
            req_slots = [slot] if slot else None
            return self.compile_verify_luau(
                rig_path=rig_path,
                item_path=item_path or None,
                required_slots=req_slots,
            )

        parsed_sidecar: Optional[Dict[str, Any]] = None
        if sidecar_data is not None:
            parsed_sidecar = self.load_blender_sidecar(sidecar_data)
        elif sidecar_path:
            parsed_sidecar = self.load_blender_sidecar(sidecar_path)

        effective_slot = slot or (str(parsed_sidecar["slot"]) if (parsed_sidecar and parsed_sidecar.get("slot")) else None)

        resolved = self._resolve_attach_params(
            mode=norm_mode,
            slot=effective_slot,
            preset=preset,
            limb_part=limb_part,
            limb_attachment=limb_attachment,
            item_attachment=item_attachment,
            offset_pos=offset_pos,
            offset_rot_deg=offset_rot_deg,
            foregrip_offset_pos=foregrip_offset_pos,
            foregrip_offset_rot_deg=foregrip_offset_rot_deg,
            sidecar_data=parsed_sidecar,
        )

        # Build Luau CFrame expressions
        limb_att_cf_expr = _cframe_luau_expr(
            resolved["limb_attachment_default_pos"],
            resolved["limb_attachment_default_rot"],
        )
        if resolved["use_direct_item_att"]:
            item_att_cf_expr = _cframe_luau_expr(
                resolved["item_att_pos"],
                resolved["item_att_rot"],
            )
            rel_offset_cf_expr = f"({item_att_cf_expr}):Inverse()"
        else:
            rel_offset_cf_expr = _cframe_luau_expr(
                resolved["rel_offset_pos"],
                resolved["rel_offset_rot_deg"],
            )
            item_att_cf_expr = f"({rel_offset_cf_expr}):Inverse()"

        tool_grip_cf_expr = _cframe_luau_expr(
            resolved["tool_grip_pos"],
            resolved["tool_grip_rot_deg"],
        )
        if offset_pos is not None or offset_rot_deg is not None:
            if norm_mode == "tool_grip":
                tool_grip_cf_expr = _cframe_luau_expr(
                    resolved["rel_offset_pos"],
                    resolved["rel_offset_rot_deg"],
                )

        ik_info = resolved["ik"]
        foregrip_cf_expr = _cframe_luau_expr(ik_info["foregrip_pos"], ik_info["foregrip_rot_deg"])
        pole_cf_expr = _cframe_luau_expr(ik_info["pole_pos"], [0.0, 0.0, 0.0])

        armor_entries: List[Dict[str, Any]] = []
        if norm_mode == "armor_set":
            if armor_slot_map:
                for raw_slot, piece_path in armor_slot_map.items():
                    ak = _resolve_armor_slot(raw_slot)
                    ac = ARMOR_SLOTS.get(ak, ARMOR_SLOTS["chest"])
                    la_spec = R15_ATTACHMENTS[ac["limb_part"]][ac["limb_attachment"]]
                    armor_entries.append({
                        "slot": ak,
                        "itemPath": piece_path,
                        "limbPart": ac["limb_part"],
                        "limbAttachment": ac["limb_attachment"],
                        "limbPos": la_spec["pos"],
                        "limbRot": la_spec["rot_deg"],
                        "itemAttachment": ac["item_attachment"],
                        "offsetPos": ac["offset_pos"],
                        "offsetRot": ac["offset_rot_deg"],
                    })
            elif not effective_slot or effective_slot.strip().lower() == "all":
                for ak, ac in ARMOR_SLOTS.items():
                    la_spec = R15_ATTACHMENTS[ac["limb_part"]][ac["limb_attachment"]]
                    armor_entries.append({
                        "slot": ak,
                        "itemPath": "",
                        "limbPart": ac["limb_part"],
                        "limbAttachment": ac["limb_attachment"],
                        "limbPos": la_spec["pos"],
                        "limbRot": la_spec["rot_deg"],
                        "itemAttachment": ac["item_attachment"],
                        "offsetPos": ac["offset_pos"],
                        "offsetRot": ac["offset_rot_deg"],
                    })
            else:
                ak = _resolve_armor_slot(effective_slot)
                ac = ARMOR_SLOTS.get(ak, ARMOR_SLOTS["chest"])
                la_spec = R15_ATTACHMENTS[ac["limb_part"]][ac["limb_attachment"]]
                armor_entries.append({
                    "slot": ak,
                    "itemPath": item_path,
                    "limbPart": ac["limb_part"],
                    "limbAttachment": ac["limb_attachment"],
                    "limbPos": la_spec["pos"],
                    "limbRot": la_spec["rot_deg"],
                    "itemAttachment": ac["item_attachment"],
                    "offsetPos": ac["offset_pos"],
                    "offsetRot": ac["offset_rot_deg"],
                })

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")

local TARGET_RIG_PATH = {json.dumps(rig_path)}
local TARGET_ITEM_PATH = {json.dumps(item_path)}
local ATTACH_MODE = {json.dumps(norm_mode)}
local LIMB_PART_NAME = {json.dumps(resolved["limb_part"])}
local LIMB_ATT_NAME = {json.dumps(resolved["limb_attachment"])}
local ITEM_ATT_NAME = {json.dumps(resolved["item_attachment"])}
local REPLACE_EXISTING_WELDS = {"true" if replace_existing_welds else "false"}
local CLONE_ITEM = {"true" if clone_item else "false"}

local LIMB_ATT_DEFAULT_CF = {limb_att_cf_expr}
local ITEM_ATT_CF = {item_att_cf_expr}
local TOOL_GRIP_CF = {tool_grip_cf_expr}

local IK_CHAIN_ROOT_NAME = {json.dumps(ik_info["chain_root"])}
local IK_END_EFFECTOR_NAME = {json.dumps(ik_info["end_effector"])}
local IK_FOREGRIP_NAME = {json.dumps(ik_info["foregrip_attachment"])}
local IK_FOREGRIP_CF = {foregrip_cf_expr}
local IK_POLE_LIMB_NAME = {json.dumps(ik_info["pole_limb"])}
local IK_POLE_CF = {pole_cf_expr}
local IK_WEIGHT = {max(0.0, min(1.0, float(ik_weight))):.6g}
local IK_SMOOTH_TIME = {max(0.0, float(ik_smooth_time)):.6g}
local IK_TYPE_NAME = {json.dumps(ik_type)}
local IK_CREATE_POLE = {"true" if create_pole else "false"}
local IK_ATTACH_PRIMARY = {"true" if attach_primary_in_ik else "false"}
local ARMOR_ENTRIES: {{ any }} = HttpService:JSONDecode({json.dumps(json.dumps(armor_entries))})

local function resolveInstance(pathStr: string): Instance?
	if pathStr == "" then
		return nil
	end
	local curr: Instance = game
	local first = true
	for seg in string.gmatch(pathStr, "[^%.]+") do
		if first and seg == "game" then
			first = false
			continue
		end
		local nxt: Instance? = nil
		if first and curr == game then
			local okSvc, svc = pcall(function()
				return game:GetService(seg)
			end)
			nxt = if okSvc then svc else curr:FindFirstChild(seg)
		else
			nxt = curr:FindFirstChild(seg)
		end
		first = false
		if not nxt then
			return nil
		end
		curr = nxt
	end
	return curr
end

local function configureEquipmentPhysics(rootInst: Instance)
	local parts: {{ BasePart }} = {{}}
	if rootInst:IsA("BasePart") then
		table.insert(parts, rootInst)
	end
	for _, d in ipairs(rootInst:GetDescendants()) do
		if d:IsA("BasePart") then
			table.insert(parts, d)
		end
	end
	local lowDensity = PhysicalProperties.new(0.01, 0, 0, 1, 1)
	for _, p in ipairs(parts) do
		p.Anchored = false
		p.Massless = true
		p.CanCollide = false
		p.CanTouch = false
		p.CanQuery = false
		pcall(function()
			p.CustomPhysicalProperties = lowDensity
		end)
	end
end

local function getPrimaryHandle(itemInst: Instance): BasePart?
	if itemInst:IsA("BasePart") then
		return itemInst
	end
	local h = itemInst:FindFirstChild("Handle")
	if h and h:IsA("BasePart") then
		return h
	end
	if itemInst:IsA("Model") and itemInst.PrimaryPart then
		return itemInst.PrimaryPart
	end
	return itemInst:FindFirstChildWhichIsA("BasePart", true)
end

local function weldModelPartsToHandle(itemInst: Instance, handle: BasePart)
	for _, d in ipairs(itemInst:GetDescendants()) do
		if d:IsA("BasePart") and d ~= handle then
			local already = false
			for _, c in ipairs(d:GetChildren()) do
				if c:IsA("WeldConstraint") and ((c.Part0 == handle and c.Part1 == d) or (c.Part1 == handle and c.Part0 == d)) then
					already = true
					break
				end
			end
			if not already then
				local wc = Instance.new("WeldConstraint")
				wc.Name = "SharpSubPartWeld"
				wc.Part0 = handle
				wc.Part1 = d
				wc.Parent = handle
			end
		end
	end
end

local function ensureAttachment(part: BasePart, attName: string, defaultCf: CFrame): (Attachment, boolean)
	local existing = part:FindFirstChild(attName)
	if existing and existing:IsA("Attachment") then
		return existing, false
	end
	local att = Instance.new("Attachment")
	att.Name = attName
	att.CFrame = defaultCf
	att.Parent = part
	return att, true
end

local function cleanupCompetingJoints(rigModel: Instance, handle: BasePart, keepName: string?)
	if not REPLACE_EXISTING_WELDS then
		return 0
	end
	local removed = 0
	local containers: {{ Instance }} = if handle:IsDescendantOf(rigModel) then {{ rigModel }} else {{ rigModel, handle }}
	for _, container in ipairs(containers) do
		for _, d in ipairs(container:GetDescendants()) do
			if (d:IsA("Weld") or d:IsA("RigidConstraint") or d:IsA("Motor6D")) and d.Name ~= keepName then
				if d:IsA("Weld") or d:IsA("Motor6D") then
					if d.Part1 == handle or d.Name == "RightGrip" then
						d:Destroy()
						removed += 1
					end
				elseif d:IsA("RigidConstraint") then
					local a0 = d.Attachment0
					local a1 = d.Attachment1
					if (a0 and a0.Parent == handle) or (a1 and a1.Parent == handle) then
						d:Destroy()
						removed += 1
					end
				end
			end
		end
	end
	return removed
end

local function attachViaRigidConstraint(rigModel: Instance, limbPart: BasePart, limbAttName: string, limbDefaultCf: CFrame, itemInst: Instance, itemAttName: string, itemAttCf: CFrame): {{ [string]: any }}
	local handle = getPrimaryHandle(itemInst)
	assert(handle ~= nil, "Item '" .. itemInst:GetFullName() .. "' contains no BasePart.")
	configureEquipmentPhysics(itemInst)
	weldModelPartsToHandle(itemInst, handle)

	local limbAtt, createdLimbAtt = ensureAttachment(limbPart, limbAttName, limbDefaultCf)
	local itemAtt, createdItemAtt = ensureAttachment(handle, itemAttName, itemAttCf)
	if not createdItemAtt and itemAttCf ~= CFrame.identity then
		itemAtt.CFrame = itemAttCf
	end

	local removed = cleanupCompetingJoints(rigModel, handle, "SharpRigidAttach_" .. itemAttName)

	local targetCf = limbPart.CFrame * limbAtt.CFrame * itemAtt.CFrame:Inverse()
	if itemInst:IsA("Model") then
		itemInst:PivotTo(targetCf)
	else
		handle.CFrame = targetCf
	end

	if not itemInst:IsDescendantOf(rigModel) then
		itemInst.Parent = rigModel
	end

	local rc = handle:FindFirstChild("SharpRigidAttach_" .. itemAttName)
	local rigid: RigidConstraint
	if rc and rc:IsA("RigidConstraint") then
		rigid = rc
	else
		local newRc = Instance.new("RigidConstraint")
		newRc.Name = "SharpRigidAttach_" .. itemAttName
		newRc.Parent = handle
		rigid = newRc
	end
	rigid.Attachment0 = itemAtt
	rigid.Attachment1 = limbAtt
	rigid.Enabled = true

	return {{
		jointType = "RigidConstraint",
		limbPart = limbPart.Name,
		limbAttachment = limbAtt.Name,
		itemAttachment = itemAtt.Name,
		createdLimbAttachment = createdLimbAtt,
		createdItemAttachment = createdItemAtt,
		removedCompetingJoints = removed,
	}}
end

local function attachViaMotor6D(rigModel: Instance, limbPart: BasePart, limbAttName: string, limbDefaultCf: CFrame, itemInst: Instance, itemAttName: string, itemAttCf: CFrame): {{ [string]: any }}
	local handle = getPrimaryHandle(itemInst)
	assert(handle ~= nil, "Weapon '" .. itemInst:GetFullName() .. "' contains no BasePart.")
	configureEquipmentPhysics(itemInst)
	weldModelPartsToHandle(itemInst, handle)

	if itemInst:IsA("Tool") then
		itemInst.RequiresHandle = false
	end

	local limbAtt, createdLimbAtt = ensureAttachment(limbPart, limbAttName, limbDefaultCf)
	local itemAtt, createdItemAtt = ensureAttachment(handle, itemAttName, itemAttCf)
	if not createdItemAtt and itemAttCf ~= CFrame.identity then
		itemAtt.CFrame = itemAttCf
	end

	local motorName = "SharpWeaponMotor_" .. handle.Name
	local removed = cleanupCompetingJoints(rigModel, handle, motorName)

	-- Exact C0/C1 matching RigidConstraint rest alignment:
	-- Part1.CFrame = Part0.CFrame * C0 * Transform * C1:Inverse()
	local c0 = limbAtt.CFrame
	local c1 = itemAtt.CFrame
	local targetCf = limbPart.CFrame * c0 * c1:Inverse()
	if itemInst:IsA("Model") then
		itemInst:PivotTo(targetCf)
	else
		handle.CFrame = targetCf
	end

	if not itemInst:IsDescendantOf(rigModel) then
		itemInst.Parent = rigModel
	end

	local existing = limbPart:FindFirstChild(motorName)
	local motor: Motor6D
	if existing and existing:IsA("Motor6D") then
		motor = existing
	else
		motor = Instance.new("Motor6D")
		motor.Name = motorName
		motor.Parent = limbPart
	end
	motor.Part0 = limbPart
	motor.Part1 = handle
	motor.C0 = c0
	motor.C1 = c1
	motor.Enabled = true

	return {{
		jointType = "Motor6D",
		motorName = motor.Name,
		limbPart = limbPart.Name,
		limbAttachment = limbAtt.Name,
		itemAttachment = itemAtt.Name,
		createdLimbAttachment = createdLimbAtt,
		createdItemAttachment = createdItemAtt,
		removedCompetingJoints = removed,
	}}
end

local function findArmorPiece(container: Instance, slotName: string, limbName: string): Instance?
	local targetSlot = string.lower((string.gsub(slotName, "_", "")))
	local targetLimb = string.lower(limbName)
	for _, ch in ipairs(container:GetChildren()) do
		local cNorm = string.lower((string.gsub(ch.Name, "[_%-%s]", "")))
		if cNorm == targetSlot or cNorm == targetLimb then
			return ch
		end
	end
	return nil
end

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpEquipmentAttach", "Sharp MCP: Attach Equipment (" .. ATTACH_MODE .. ")")
local ok, resOrErr = xpcall(function()
	local rig = resolveInstance(TARGET_RIG_PATH)
	assert(rig ~= nil, "Rig not found at path: " .. TARGET_RIG_PATH)

	local itemRaw = if TARGET_ITEM_PATH ~= "" then resolveInstance(TARGET_ITEM_PATH) else nil
	local item = if (itemRaw and CLONE_ITEM) then itemRaw:Clone() else itemRaw

	if ATTACH_MODE == "armor_set" then
		assert(#ARMOR_ENTRIES > 0, "No armor entries provided for armor_set mode.")
		local attachedPieces: {{ any }} = {{}}
		for _, entry in ipairs(ARMOR_ENTRIES) do
			local pieceInst: Instance? = nil
			if entry.itemPath ~= "" then
				local found = resolveInstance(entry.itemPath)
				pieceInst = if (found and CLONE_ITEM) then found:Clone() else found
			elseif item then
				pieceInst = findArmorPiece(item, entry.slot, entry.limbPart)
				if not pieceInst and #ARMOR_ENTRIES == 1 then
					pieceInst = item
				end
			end
			if pieceInst then
				local lp = rig:FindFirstChild(entry.limbPart, true)
				if lp and lp:IsA("BasePart") then
					local lDef = CFrame.new(entry.limbPos[1], entry.limbPos[2], entry.limbPos[3])
						* CFrame.Angles(math.rad(entry.limbRot[1]), math.rad(entry.limbRot[2]), math.rad(entry.limbRot[3]))
					local oDef = CFrame.new(entry.offsetPos[1], entry.offsetPos[2], entry.offsetPos[3])
						* CFrame.Angles(math.rad(entry.offsetRot[1]), math.rad(entry.offsetRot[2]), math.rad(entry.offsetRot[3]))
					local info = attachViaRigidConstraint(rig, lp, entry.limbAttachment, lDef, pieceInst, entry.itemAttachment, oDef:Inverse())
					info.slot = entry.slot
					table.insert(attachedPieces, info)
				end
			end
		end
		return {{ mode = ATTACH_MODE, rig = rig:GetFullName(), attachedCount = #attachedPieces, pieces = attachedPieces }}
	end

	assert(item ~= nil, "Item not found at path: " .. TARGET_ITEM_PATH)

	if ATTACH_MODE == "tool_grip" then
		local tool: Tool
		if item:IsA("Tool") then
			tool = item
		else
			tool = Instance.new("Tool")
			tool.Name = item.Name
			tool.Parent = item.Parent or rig
			if item:IsA("Model") then
				local primary = getPrimaryHandle(item)
				for _, child in ipairs(item:GetChildren()) do
					child.Parent = tool
				end
				if primary then
					primary.Name = "Handle"
				end
				item:Destroy()
			else
				item.Parent = tool
			end
		end
		local handle = getPrimaryHandle(tool)
		assert(handle ~= nil, "Tool must contain a BasePart Handle.")
		handle.Name = "Handle"
		if handle.Parent ~= tool then
			handle.Parent = tool
		end
		configureEquipmentPhysics(tool)
		weldModelPartsToHandle(tool, handle)
		tool.RequiresHandle = true
		tool.Grip = TOOL_GRIP_CF
		if not tool:IsDescendantOf(rig) then
			tool.Parent = rig
		end
		return {{
			mode = ATTACH_MODE,
			toolPath = tool:GetFullName(),
			requiresHandle = tool.RequiresHandle,
			handleName = handle.Name,
		}}
	end

	local limbInst = rig:FindFirstChild(LIMB_PART_NAME, true)
	assert(limbInst ~= nil and limbInst:IsA("BasePart"), "R15 limb BasePart not found: " .. LIMB_PART_NAME)

	if ATTACH_MODE == "motor6d_weapon" then
		local info = attachViaMotor6D(rig, limbInst, LIMB_ATT_NAME, LIMB_ATT_DEFAULT_CF, item, ITEM_ATT_NAME, ITEM_ATT_CF)
		info.mode = ATTACH_MODE
		return info
	end

	if ATTACH_MODE == "two_hand_ik" then
		local primaryInfo: any = nil
		if IK_ATTACH_PRIMARY then
			primaryInfo = attachViaMotor6D(rig, limbInst, LIMB_ATT_NAME, LIMB_ATT_DEFAULT_CF, item, ITEM_ATT_NAME, ITEM_ATT_CF)
		end
		local handle = getPrimaryHandle(item)
		assert(handle ~= nil, "Weapon item has no BasePart Handle for foregrip Attachment.")
		local foregripAtt, createdForegrip = ensureAttachment(handle, IK_FOREGRIP_NAME, IK_FOREGRIP_CF)

		local poleAtt: Attachment? = nil
		if IK_CREATE_POLE then
			local poleLimb = rig:FindFirstChild(IK_POLE_LIMB_NAME, true)
			if poleLimb and poleLimb:IsA("BasePart") then
				local pAtt = ensureAttachment(poleLimb, "SharpOffHandPoleAttachment", IK_POLE_CF)
				poleAtt = pAtt
			end
		end

		local controller: Instance? = rig:FindFirstChildOfClass("Humanoid") or rig:FindFirstChildOfClass("AnimationController")
		assert(controller ~= nil, "Rig must have a Humanoid or AnimationController for IKControl.")
		if not controller:FindFirstChildOfClass("Animator") then
			local anim = Instance.new("Animator")
			anim.Parent = controller
		end

		local chainRoot = rig:FindFirstChild(IK_CHAIN_ROOT_NAME, true)
		local endEffector = rig:FindFirstChild(IK_END_EFFECTOR_NAME, true)
		assert(chainRoot ~= nil and endEffector ~= nil, "IK chain joints not found on rig.")

		local ikApplied = false
		local ikTypeApplied = false
		local ikOptionalProps: {{ [string]: boolean }} = {{}}
		local existingIk = controller:FindFirstChild("SharpTwoHandIK")
		if existingIk then
			existingIk:Destroy()
		end

		local okCreate, ikOrErr = pcall(function()
			return Instance.new("IKControl")
		end)
		if okCreate and ikOrErr then
			local ik = ikOrErr :: any
			ik.Name = "SharpTwoHandIK"
			ik.ChainRoot = chainRoot
			ik.EndEffector = endEffector
			ik.Target = foregripAtt
			if poleAtt then
				ik.Pole = poleAtt
			end
			ik.Weight = IK_WEIGHT
			ik.SmoothTime = IK_SMOOTH_TIME
			ik.Enabled = true
			ikTypeApplied = pcall(function()
				local enumType = (Enum :: any).IKControlType
				local okNamed, valNamed = pcall(function()
					return enumType[IK_TYPE_NAME]
				end)
				if okNamed and valNamed ~= nil then
					ik.Type = valNamed
				else
					ik.Type = enumType.Transform
				end
			end)
			ikOptionalProps.EndEffectorOffset = pcall(function()
				ik.EndEffectorOffset = CFrame.identity
			end)
			ikOptionalProps.Priority = pcall(function()
				ik.Priority = 1
			end)
			ik.Parent = controller
			ikApplied = true
		end

		return {{
			mode = ATTACH_MODE,
			rig = rig:GetFullName(),
			ikApplied = ikApplied,
			ikTypeApplied = ikTypeApplied,
			ikOptionalProps = ikOptionalProps,
			foregripAttachment = foregripAtt:GetFullName(),
			createdForegripAttachment = createdForegrip,
			poleAttachment = if poleAtt then poleAtt:GetFullName() else nil,
			primaryAttachment = primaryInfo,
		}}
	end

	-- accessory_rigid | holster_back | holster_hip | shield_back
	local info = attachViaRigidConstraint(rig, limbInst, LIMB_ATT_NAME, LIMB_ATT_DEFAULT_CF, item, ITEM_ATT_NAME, ITEM_ATT_CF)
	info.mode = ATTACH_MODE
	return info
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""
