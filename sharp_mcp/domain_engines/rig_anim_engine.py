"""Rig Probing, Animation Quality Analysis, Procedural Presets & Compiler Engine (`roblox-animation`).

Embeds and extends:
- `probe_rig.luau` (exports live Motor6D / Bone / AnimationConstraint rest poses to rig_spec.json)
- `blender_bake_to_roblox.py` (`clip_to_luau` and `clip_to_rbxmx` compilers for KeyframeSequence Pose trees
  and CurveAnimation Vector3Curve/RotationCurve/MarkerCurve hierarchies)
- `studio_test_anim.luau` (instant preview via `AnimationClipProvider:RegisterAnimationClip` and
  `Animator:LoadAnimation` with track caching)
- `analyze_clip` (3D R15 FK foot-sliding estimate, loop seam delta, frame rotation pops/overspeed,
  root motion check, priority/loop sanity, and joint overlap check)
- `generate_procedural_preset` / `generate_procedural_presets` (9 non-robotic clips with anticipation,
  overshoot, follow-through, and overlapping joint phase lag)
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_R15_PARENTS: Dict[str, Optional[str]] = {
    "HumanoidRootPart": None,
    "LowerTorso": "HumanoidRootPart",
    "UpperTorso": "LowerTorso",
    "Head": "UpperTorso",
    "LeftUpperArm": "UpperTorso",
    "LeftLowerArm": "LeftUpperArm",
    "LeftHand": "LeftLowerArm",
    "RightUpperArm": "UpperTorso",
    "RightLowerArm": "RightUpperArm",
    "RightHand": "RightLowerArm",
    "LeftUpperLeg": "LowerTorso",
    "LeftLowerLeg": "LeftUpperLeg",
    "LeftFoot": "LeftLowerLeg",
    "RightUpperLeg": "LowerTorso",
    "RightLowerLeg": "RightUpperLeg",
    "RightFoot": "RightLowerLeg",
}

VALID_PRIORITIES: Tuple[str, ...] = (
    "Core",
    "Idle",
    "Movement",
    "Action",
    "Action2",
    "Action3",
    "Action4",
)

# Classic blocky R15 joint offsets (studs) matching builtin_r15_spec for 3D FK analysis.
_R15_JOINT_OFFSETS: Dict[str, Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]] = {
    "LowerTorso": ("HumanoidRootPart", (0.0, -1.0, 0.0), (0.0, -0.2, 0.0)),
    "UpperTorso": ("LowerTorso", (0.0, 0.2, 0.0), (0.0, -0.8, 0.0)),
    "Head": ("UpperTorso", (0.0, 0.8, 0.0), (0.0, -0.6, 0.0)),
    "LeftUpperArm": ("UpperTorso", (-1.0, 0.6, 0.0), (0.5, 0.4, 0.0)),
    "LeftLowerArm": ("LeftUpperArm", (0.0, -0.5, 0.0), (0.0, 0.35, 0.0)),
    "LeftHand": ("LeftLowerArm", (0.0, -0.35, 0.0), (0.0, 0.15, 0.0)),
    "RightUpperArm": ("UpperTorso", (1.0, 0.6, 0.0), (-0.5, 0.4, 0.0)),
    "RightLowerArm": ("RightUpperArm", (0.0, -0.5, 0.0), (0.0, 0.35, 0.0)),
    "RightHand": ("RightLowerArm", (0.0, -0.35, 0.0), (0.0, 0.15, 0.0)),
    "LeftUpperLeg": ("LowerTorso", (-0.5, -0.2, 0.0), (0.0, 0.55, 0.0)),
    "LeftLowerLeg": ("LeftUpperLeg", (0.0, -0.55, 0.0), (0.0, 0.35, 0.0)),
    "LeftFoot": ("LeftLowerLeg", (0.0, -0.35, 0.0), (0.0, 0.15, 0.0)),
    "RightUpperLeg": ("LowerTorso", (0.5, -0.2, 0.0), (0.0, 0.55, 0.0)),
    "RightLowerLeg": ("RightUpperLeg", (0.0, -0.55, 0.0), (0.0, 0.35, 0.0)),
    "RightFoot": ("RightLowerLeg", (0.0, -0.35, 0.0), (0.0, 0.15, 0.0)),
}

PRESET_ALIASES: Dict[str, str] = {
    "idle": "idle_breathing",
    "breathing": "idle_breathing",
    "walk_cycle": "walk",
    "run_cycle": "run",
    "sprint": "run",
    "sword_combo": "sword_combo_3hit",
    "combo_3hit": "sword_combo_3hit",
    "sword_3hit": "sword_combo_3hit",
    "bow": "bow_draw_release",
    "bow_draw": "bow_draw_release",
    "block": "shield_block",
    "shield": "shield_block",
    "hit": "hit_react",
    "hit_reaction": "hit_react",
    "hurt": "hit_react",
    "die": "death",
    "wave": "emote_wave",
    "emote": "emote_wave",
}

PROCEDURAL_PRESET_CATALOG: Dict[str, Dict[str, Any]] = {
    "idle_breathing": {
        "name": "Idle_Breathing",
        "kind": "idle",
        "duration": 2.4,
        "loop": True,
        "priority": "Idle",
        "description": "Calm chest breathing with phase-lagged arm/head settle and grounded stance.",
    },
    "walk": {
        "name": "Walk_Locomotion",
        "kind": "walk",
        "duration": 1.0,
        "loop": True,
        "priority": "Movement",
        "description": "Cyclic R15 walk with pelvic bob, counter-rotated torso, knee cushioning, and elbow lag.",
    },
    "run": {
        "name": "Run_Locomotion",
        "kind": "run",
        "duration": 0.65,
        "loop": True,
        "priority": "Movement",
        "description": "Forward-leaning sprint cycle with high knee drive, double-bob hips, and arm pump overlap.",
    },
    "sword_combo_3hit": {
        "name": "Sword_Combo_3Hit",
        "kind": "attack",
        "duration": 2.15,
        "loop": False,
        "priority": "Action2",
        "description": "3-hit melee combo with windup anticipation, whip follow-through, overshoot, and hit markers.",
    },
    "bow_draw_release": {
        "name": "Bow_Draw_Release",
        "kind": "attack",
        "duration": 1.4,
        "loop": False,
        "priority": "Action2",
        "description": "Archer stance draw with chest brace, draw tension, crisp release recoil, and settle.",
    },
    "shield_block": {
        "name": "Shield_Block",
        "kind": "block",
        "duration": 0.8,
        "loop": False,
        "priority": "Action",
        "description": "Tucked anticipation into braced forward shield raise with damped guard settle.",
    },
    "hit_react": {
        "name": "Hit_React",
        "kind": "hit_react",
        "duration": 0.65,
        "loop": False,
        "priority": "Action3",
        "description": "Sharp chest knockback, delayed head whip, knee absorb, and recovery bounce.",
    },
    "death": {
        "name": "Death_Collapse",
        "kind": "death",
        "duration": 1.3,
        "loop": False,
        "priority": "Action4",
        "description": "Stagger recoil, knee buckle, sequential limb drop, and damped ground settle.",
    },
    "emote_wave": {
        "name": "Emote_Wave",
        "kind": "emote",
        "duration": 1.5,
        "loop": False,
        "priority": "Action",
        "description": "Torso lean anticipation, elbow-led arm raise, 2-cycle wrist-lagged wave, and settle.",
    },
}


# ---------------------------------------------------------------------------
# Pure-Python 3D math & R15 forward kinematics helpers
# ---------------------------------------------------------------------------

def _euler_deg_to_mat3(rx_deg: float, ry_deg: float, rz_deg: float) -> List[float]:
    rx, ry, rz = math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        cy * cz,
        -cy * sz,
        sy,
        sx * sy * cz + cx * sz,
        -sx * sy * sz + cx * cz,
        -sx * cy,
        -cx * sy * cz + sx * sz,
        cx * sy * sz + sx * cz,
        cx * cy,
    ]


def _mat3_mul(a: List[float], b: List[float]) -> List[float]:
    return [
        a[0] * b[0] + a[1] * b[3] + a[2] * b[6],
        a[0] * b[1] + a[1] * b[4] + a[2] * b[7],
        a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
        a[3] * b[0] + a[4] * b[3] + a[5] * b[6],
        a[3] * b[1] + a[4] * b[4] + a[5] * b[7],
        a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
        a[6] * b[0] + a[7] * b[3] + a[8] * b[6],
        a[6] * b[1] + a[7] * b[4] + a[8] * b[7],
        a[6] * b[2] + a[7] * b[5] + a[8] * b[8],
    ]


def _mat3_vec(m: List[float], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
        m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
        m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
    )


def _mat3_geodesic_deg(r1: List[float], r2: List[float]) -> float:
    # trace(R1^T * R2) = sum_ij R1_ij * R2_ij
    tr = sum(r1[i] * r2[i] for i in range(9))
    cos_theta = max(-1.0, min(1.0, (tr - 1.0) * 0.5))
    return math.degrees(math.acos(cos_theta))


def _cf_mul(
    p1: Tuple[float, float, float],
    r1: List[float],
    p2: Tuple[float, float, float],
    r2: List[float],
) -> Tuple[Tuple[float, float, float], List[float]]:
    rv = _mat3_vec(r1, p2)
    return (p1[0] + rv[0], p1[1] + rv[1], p1[2] + rv[2]), _mat3_mul(r1, r2)


def _solve_r15_world_frames(
    poses: Dict[str, Dict[str, List[float]]],
) -> Dict[str, Tuple[Tuple[float, float, float], List[float]]]:
    """Compute world-space (pos, rot9) for R15 parts via Part1 = Part0 * C0 * Pose * C1^-1."""
    ident_rot = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    root_pose = poses.get("HumanoidRootPart") or {"pos": [0.0, 0.0, 0.0], "rot": ident_rot}
    rp = root_pose["pos"]
    world: Dict[str, Tuple[Tuple[float, float, float], List[float]]] = {
        "HumanoidRootPart": ((float(rp[0]), 3.0 + float(rp[1]), float(rp[2])), list(root_pose["rot"])),
    }

    order = [
        "LowerTorso", "UpperTorso", "Head",
        "LeftUpperArm", "LeftLowerArm", "LeftHand",
        "RightUpperArm", "RightLowerArm", "RightHand",
        "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
        "RightUpperLeg", "RightLowerLeg", "RightFoot",
    ]
    for bone in order:
        p0_name, c0_pos, c1_pos = _R15_JOINT_OFFSETS[bone]
        p0_pos, p0_rot = world.get(p0_name, ((0.0, 3.0, 0.0), ident_rot))
        pose = poses.get(bone)
        if pose:
            pose_pos = (float(pose["pos"][0]), float(pose["pos"][1]), float(pose["pos"][2]))
            pose_rot = list(pose["rot"])
        else:
            pose_pos = (0.0, 0.0, 0.0)
            pose_rot = ident_rot

        # Part0 * C0 (C0 rot = I)
        j_pos, j_rot = _cf_mul(p0_pos, p0_rot, c0_pos, ident_rot)
        # * Pose
        a_pos, a_rot = _cf_mul(j_pos, j_rot, pose_pos, pose_rot)
        # * C1^-1 (C1 rot = I, so C1^-1 pos = -c1_pos)
        b_pos, b_rot = _cf_mul(a_pos, a_rot, (-c1_pos[0], -c1_pos[1], -c1_pos[2]), ident_rot)
        world[bone] = (b_pos, b_rot)
    return world


def _ease_in_out_cubic(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return 4.0 * u * u * u if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) * 0.5


def _sample_channel(tracks: List[Tuple[float, float]], t: float) -> float:
    """Smooth cosine/cubic Hermite interpolation through `(time, value)` control points."""
    if not tracks:
        return 0.0
    if t <= tracks[0][0]:
        return tracks[0][1]
    if t >= tracks[-1][0]:
        return tracks[-1][1]
    for i in range(len(tracks) - 1):
        t0, v0 = tracks[i]
        t1, v1 = tracks[i + 1]
        if t0 <= t <= t1:
            span = max(1e-6, t1 - t0)
            u = (t - t0) / span
            # Catmull-Rom tangent slopes for organic anticipation/overshoot continuity
            p_prev = tracks[i - 1] if i > 0 else (t0 - span, v0)
            p_next = tracks[i + 2] if i + 2 < len(tracks) else (t1 + span, v1)
            m0 = 0.5 * ((v1 - v0) / span + (v0 - p_prev[1]) / max(1e-6, t0 - p_prev[0])) * span
            m1 = 0.5 * ((p_next[1] - v1) / max(1e-6, p_next[0] - t1) + (v1 - v0) / span) * span
            u2 = u * u
            u3 = u2 * u
            h00 = 2.0 * u3 - 3.0 * u2 + 1.0
            h10 = u3 - 2.0 * u2 + u
            h01 = -2.0 * u3 + 3.0 * u2
            h11 = u3 - u2
            return h00 * v0 + h10 * m0 + h01 * v1 + h11 * m1
    return tracks[-1][1]


def _clamp_phase_lag(t: float, lag: float, duration: float, loop: bool) -> float:
    shifted = t - lag
    if loop:
        return shifted % duration
    return max(0.0, min(duration, shifted))


class RigAnimationEngine:
    def __init__(self, skills_dir: Path | str, archive_dir: Optional[Path | str] = None) -> None:
        self.skills_dir = Path(skills_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else None
        self.skill_path = self._resolve_skill_path()

    def _resolve_skill_path(self) -> Path:
        p = self.skills_dir / "roblox-animation"
        if p.is_dir():
            return p
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / "roblox-animation"
        if bundled.is_dir():
            return bundled
        if self.archive_dir:
            return self.archive_dir / "01_roblox_animation" / "skill"
        return p

    def _read_script(self, script_name: str) -> str:
        return (self.skill_path / "scripts" / script_name).read_text(encoding="utf-8")

    def _load_baker_module(self) -> Any:
        py_path = self.skill_path / "scripts" / "blender_bake_to_roblox.py"
        spec = importlib.util.spec_from_file_location("sharp_blender_bake_to_roblox", py_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        prev_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = prev_bytecode
        return mod

    @staticmethod
    def _euler_deg_to_rot9(rx_deg: float, ry_deg: float, rz_deg: float) -> List[float]:
        return [round(v, 6) for v in _euler_deg_to_mat3(rx_deg, ry_deg, rz_deg)]

    @classmethod
    def normalize_clip_dict(cls, raw_clip: Dict[str, Any], default_name: str = "SharpAnimation") -> Dict[str, Any]:
        """Normalizes a baked clip or shorthand keyframe spec into the canonical `clip_to_luau` / `clip_to_rbxmx` schema."""
        if "rootName" in raw_clip and "parents" in raw_clip and "frames" in raw_clip:
            clip = dict(raw_clip)
            clip.setdefault("name", default_name)
            clip.setdefault("loop", bool(raw_clip.get("looped", False)))
            clip.setdefault("priority", "Action")
            clip.setdefault("fps", 30.0)
            clip.setdefault("markers", [])
            return clip

        name = str(raw_clip.get("name", default_name))
        loop = bool(raw_clip.get("loop", raw_clip.get("looped", False)))
        priority = str(raw_clip.get("priority", "Action"))
        fps = float(raw_clip.get("fps", 30.0))
        root_name = str(raw_clip.get("rootName", "HumanoidRootPart"))
        parents = dict(raw_clip.get("parents") or DEFAULT_R15_PARENTS)
        markers = list(raw_clip.get("markers") or [])

        raw_frames = raw_clip.get("frames") or raw_clip.get("keyframes") or [
            {"t": 0.0, "poses": {"RightUpperArm": {"rot_deg": [-35.0, 0.0, 15.0]}}},
            {"t": 0.25, "poses": {"RightUpperArm": {"rot_deg": [65.0, -20.0, -10.0]}}},
            {"t": 0.5, "poses": {"RightUpperArm": {"rot_deg": [0.0, 0.0, 0.0]}}},
        ]
        norm_frames: List[Dict[str, Any]] = []
        for idx, fr in enumerate(raw_frames):
            t_val = float(fr.get("t", fr.get("time", idx * 0.25)))
            raw_poses = fr.get("poses") or {}
            norm_poses: Dict[str, Dict[str, List[float]]] = {}
            for b_name, p_spec in raw_poses.items():
                if b_name not in parents:
                    parents[b_name] = root_name
                pos = [float(x) for x in p_spec.get("pos", [0.0, 0.0, 0.0])]
                if "rot" in p_spec and len(p_spec["rot"]) == 9:
                    rot = [float(x) for x in p_spec["rot"]]
                elif "rot_deg" in p_spec and len(p_spec["rot_deg"]) == 3:
                    rot = cls._euler_deg_to_rot9(
                        float(p_spec["rot_deg"][0]),
                        float(p_spec["rot_deg"][1]),
                        float(p_spec["rot_deg"][2]),
                    )
                elif "rot" in p_spec and len(p_spec["rot"]) == 3:
                    rot = cls._euler_deg_to_rot9(
                        float(p_spec["rot"][0]),
                        float(p_spec["rot"][1]),
                        float(p_spec["rot"][2]),
                    )
                else:
                    rot = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
                norm_poses[b_name] = {"pos": pos, "rot": rot}
            if not norm_poses:
                norm_poses[root_name] = {
                    "pos": [0.0, 0.0, 0.0],
                    "rot": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                }
            norm_frames.append({"t": t_val, "poses": norm_poses})

        return {
            "name": name,
            "loop": loop,
            "priority": priority,
            "fps": fps,
            "rootName": root_name,
            "parents": parents,
            "frames": norm_frames,
            "markers": markers,
        }

    # ------------------------------------------------------------------
    # Procedural Non-Robotic Animation Presets
    # ------------------------------------------------------------------

    @staticmethod
    def list_procedural_presets() -> Dict[str, Any]:
        """List all procedural R15 animation presets and aliases."""
        return {
            "ok": True,
            "presets": PROCEDURAL_PRESET_CATALOG,
            "aliases": PRESET_ALIASES,
        }

    @classmethod
    def _resolve_preset_key(cls, preset_name: str) -> str:
        key = (preset_name or "").strip().lower().replace("-", "_").replace(" ", "_")
        key = PRESET_ALIASES.get(key, key)
        if key not in PROCEDURAL_PRESET_CATALOG:
            raise ValueError(
                f"Unknown preset '{preset_name}'. Valid presets: {', '.join(PROCEDURAL_PRESET_CATALOG.keys())}"
            )
        return key

    def generate_procedural_preset(
        self,
        preset_name: str = "idle_breathing",
        fps: float = 30.0,
        intensity: float = 1.0,
        clip_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a normalize_clip_dict-compatible clip with anticipation, overshoot & joint overlap."""
        key = self._resolve_preset_key(preset_name)
        meta = PROCEDURAL_PRESET_CATALOG[key]
        fps_val = max(12.0, min(120.0, float(fps)))
        amp = max(0.1, min(2.0, float(intensity)))
        duration = float(meta["duration"])
        loop = bool(meta["loop"])
        n_frames = max(12, int(round(duration * fps_val)) + 1)
        times = [round(duration * i / (n_frames - 1), 5) for i in range(n_frames)]

        frames: List[Dict[str, Any]] = []
        markers: List[Dict[str, Any]] = []

        def make_pose(
            rot_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
            pos: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        ) -> Dict[str, List[float]]:
            return {
                "pos": [round(pos[0], 6), round(pos[1], 6), round(pos[2], 6)],
                "rot": self._euler_deg_to_rot9(*rot_deg),
            }

        if key == "idle_breathing":
            # Phase-lagged breathing wave: LowerTorso settles slightly opposite UpperTorso inhale,
            # Head and arms lag 0.14s..0.28s for soft secondary overlap; feet remain planted.
            for idx, t in enumerate(times):
                ph = 2.0 * math.pi * (t / duration) if idx < n_frames - 1 else 0.0
                breath = math.sin(ph)
                breath_lag1 = math.sin(ph - 0.45)
                breath_lag2 = math.sin(ph - 0.85)
                sway = math.sin(ph * 0.5) if False else math.sin(ph) * 0.6

                lt_y = -0.02 * amp * (1.0 - math.cos(ph))
                lt_roll = 1.4 * amp * sway
                ut_pitch = 3.2 * amp * breath
                ut_yaw = 1.8 * amp * math.sin(ph - 0.3)
                head_pitch = -2.2 * amp * breath_lag1
                head_yaw = -1.6 * amp * math.sin(ph - 0.6)

                lua_rx = -4.0 - 3.0 * amp * breath_lag1
                lua_rz = 8.0 + 2.2 * amp * breath_lag1
                lla_rx = -14.0 - 4.0 * amp * breath_lag2
                lh_rx = -4.0 - 3.5 * amp * math.sin(ph - 1.15)

                rua_rx = -4.0 - 3.0 * amp * breath_lag1
                rua_rz = -8.0 - 2.2 * amp * breath_lag1
                rla_rx = -14.0 - 4.0 * amp * breath_lag2
                rh_rx = -4.0 - 3.5 * amp * math.sin(ph - 1.15)

                # Slight knee flex compensating LowerTorso y drop so feet stay flat at Y=0
                knee_bend = max(0.0, -lt_y * 28.0)
                poses = {
                    "HumanoidRootPart": make_pose(),
                    "LowerTorso": make_pose((0.5 * amp * breath, 0.0, lt_roll), (0.0, lt_y, 0.0)),
                    "UpperTorso": make_pose((ut_pitch, ut_yaw, -0.8 * amp * sway)),
                    "Head": make_pose((head_pitch, head_yaw, 0.6 * amp * sway)),
                    "LeftUpperArm": make_pose((lua_rx, 0.0, lua_rz)),
                    "LeftLowerArm": make_pose((lla_rx, 0.0, 0.0)),
                    "LeftHand": make_pose((lh_rx, 0.0, 0.0)),
                    "RightUpperArm": make_pose((rua_rx, 0.0, rua_rz)),
                    "RightLowerArm": make_pose((rla_rx, 0.0, 0.0)),
                    "RightHand": make_pose((rh_rx, 0.0, 0.0)),
                    "LeftUpperLeg": make_pose((knee_bend * 0.5, 0.0, -lt_roll * 0.4)),
                    "LeftLowerLeg": make_pose((-knee_bend, 0.0, 0.0)),
                    "LeftFoot": make_pose((knee_bend * 0.5, 0.0, 0.0)),
                    "RightUpperLeg": make_pose((knee_bend * 0.5, 0.0, -lt_roll * 0.4)),
                    "RightLowerLeg": make_pose((-knee_bend, 0.0, 0.0)),
                    "RightFoot": make_pose((knee_bend * 0.5, 0.0, 0.0)),
                }
                frames.append({"t": t, "poses": poses})

        elif key in ("walk", "run"):
            is_run = key == "run"
            stride_hip = (46.0 if is_run else 30.0) * amp
            knee_lift = (74.0 if is_run else 48.0) * amp
            arm_swing = (56.0 if is_run else 32.0) * amp
            torso_lean = (-13.0 if is_run else -5.5) * amp
            bob_amp = (0.16 if is_run else 0.08) * amp
            torso_twist = (11.0 if is_run else 6.5) * amp

            for idx, t in enumerate(times):
                ph = 2.0 * math.pi * (t / duration) if idx < n_frames - 1 else 0.0
                # Left leg forward at ph=pi/2, Right leg forward at ph=3*pi/2
                l_sin = math.sin(ph)
                r_sin = math.sin(ph + math.pi)
                l_cos = math.cos(ph)
                r_cos = math.cos(ph + math.pi)

                # Knee flex peaks during swing-through (cos > 0) + slight cushion on heel strike
                l_knee = -max(8.0, knee_lift * max(0.0, l_cos) + 12.0 * max(0.0, l_sin))
                r_knee = -max(8.0, knee_lift * max(0.0, r_cos) + 12.0 * max(0.0, r_sin))
                l_hip_rx = stride_hip * l_sin - l_knee * 0.35
                r_hip_rx = stride_hip * r_sin - r_knee * 0.35
                l_foot_rx = -0.35 * l_hip_rx - 0.55 * l_knee + (12.0 * amp * max(0.0, -l_sin))
                r_foot_rx = -0.35 * r_hip_rx - 0.55 * r_knee + (12.0 * amp * max(0.0, -r_sin))

                # Double-frequency pelvis bob + gentle lateral hip drop
                lt_y = bob_amp * (math.sin(2.0 * ph - 0.4) - 0.35)
                lt_yaw = -torso_twist * 0.45 * l_sin
                lt_roll = 3.5 * amp * l_sin
                # UpperTorso counter-rotates with phase lag
                ut_yaw = torso_twist * math.sin(ph - 0.25)
                ut_pitch = torso_lean + (2.5 * amp * math.sin(2.0 * ph - 0.6))
                head_pitch = -torso_lean * 0.72 + 2.0 * amp * math.sin(2.0 * ph - 1.0)
                head_yaw = -ut_yaw * 0.65

                # Arms swing opposite to legs with elbow & wrist follow-through lag
                l_arm_lag = math.sin(ph - 0.22)
                r_arm_lag = math.sin(ph + math.pi - 0.22)
                l_elb_lag = math.sin(ph - 0.55)
                r_elb_lag = math.sin(ph + math.pi - 0.55)
                l_wrist_lag = math.sin(ph - 0.90)
                r_wrist_lag = math.sin(ph + math.pi - 0.90)

                base_elbow = -58.0 if is_run else -20.0
                poses = {
                    "HumanoidRootPart": make_pose(),
                    "LowerTorso": make_pose((2.0 * amp, lt_yaw, lt_roll), (0.0, lt_y, 0.0)),
                    "UpperTorso": make_pose((ut_pitch, ut_yaw, -lt_roll * 0.6)),
                    "Head": make_pose((head_pitch, head_yaw, 0.0)),
                    "LeftUpperArm": make_pose((arm_swing * r_arm_lag, 0.0, 8.0 if is_run else 5.0)),
                    "LeftLowerArm": make_pose((base_elbow + (24.0 if is_run else 14.0) * max(-0.4, r_elb_lag), 0.0, 0.0)),
                    "LeftHand": make_pose((10.0 * amp * r_wrist_lag, 0.0, 0.0)),
                    "RightUpperArm": make_pose((arm_swing * l_arm_lag, 0.0, -8.0 if is_run else -5.0)),
                    "RightLowerArm": make_pose((base_elbow + (24.0 if is_run else 14.0) * max(-0.4, l_elb_lag), 0.0, 0.0)),
                    "RightHand": make_pose((10.0 * amp * l_wrist_lag, 0.0, 0.0)),
                    "LeftUpperLeg": make_pose((l_hip_rx, 0.0, -lt_roll * 0.5)),
                    "LeftLowerLeg": make_pose((l_knee, 0.0, 0.0)),
                    "LeftFoot": make_pose((l_foot_rx, 0.0, 0.0)),
                    "RightUpperLeg": make_pose((r_hip_rx, 0.0, -lt_roll * 0.5)),
                    "RightLowerLeg": make_pose((r_knee, 0.0, 0.0)),
                    "RightFoot": make_pose((r_foot_rx, 0.0, 0.0)),
                }

                # Clamp LowerTorso vertical offset so minimum foot center never plunges underground
                world_f = _solve_r15_world_frames(poses)
                min_foot_y = min(world_f["LeftFoot"][0][1], world_f["RightFoot"][0][1])
                ground_corr = max(0.0, 0.15 - min_foot_y)
                if ground_corr > 0.0:
                    poses["LowerTorso"] = make_pose((2.0 * amp, lt_yaw, lt_roll), (0.0, lt_y + ground_corr, 0.0))
                frames.append({"t": t, "poses": poses})

            markers = [
                {"t": round(duration * 0.25, 4), "name": "FootstepL", "value": "left"},
                {"t": round(duration * 0.75, 4), "name": "FootstepR", "value": "right"},
            ]

        else:
            # Expressive spline-keyed action clips with explicit anticipation, overshoot & lagged follow-through.
            tracks, markers = self._get_action_spline_tracks(key, duration, amp)
            for t in times:
                lt_y = _sample_channel(tracks.get("LowerTorso.y", [(0.0, 0.0), (duration, 0.0)]), t)
                lt_rx = _sample_channel(tracks.get("LowerTorso.rx", [(0.0, 0.0), (duration, 0.0)]), t)
                lt_ry = _sample_channel(tracks.get("LowerTorso.ry", [(0.0, 0.0), (duration, 0.0)]), t)
                lt_rz = _sample_channel(tracks.get("LowerTorso.rz", [(0.0, 0.0), (duration, 0.0)]), t)

                # Secondary joint phase lag for organic overlap
                t_torso = _clamp_phase_lag(t, 0.04, duration, False)
                t_arm = _clamp_phase_lag(t, 0.06, duration, False)
                t_forearm = _clamp_phase_lag(t, 0.10, duration, False)
                t_hand = _clamp_phase_lag(t, 0.13, duration, False)
                t_head = _clamp_phase_lag(t, 0.08, duration, False)

                def ch(name: str, eval_t: float, default: float = 0.0) -> float:
                    pts = tracks.get(name)
                    return _sample_channel(pts, eval_t) if pts else default

                poses = {
                    "HumanoidRootPart": make_pose(),
                    "LowerTorso": make_pose((lt_rx, lt_ry, lt_rz), (0.0, lt_y, 0.0)),
                    "UpperTorso": make_pose((ch("UpperTorso.rx", t_torso), ch("UpperTorso.ry", t_torso), ch("UpperTorso.rz", t_torso))),
                    "Head": make_pose((ch("Head.rx", t_head), ch("Head.ry", t_head), ch("Head.rz", t_head))),
                    "LeftUpperArm": make_pose((ch("LeftUpperArm.rx", t_arm), ch("LeftUpperArm.ry", t_arm), ch("LeftUpperArm.rz", t_arm, 8.0))),
                    "LeftLowerArm": make_pose((ch("LeftLowerArm.rx", t_forearm, -16.0), ch("LeftLowerArm.ry", t_forearm), ch("LeftLowerArm.rz", t_forearm))),
                    "LeftHand": make_pose((ch("LeftHand.rx", t_hand), ch("LeftHand.ry", t_hand), ch("LeftHand.rz", t_hand))),
                    "RightUpperArm": make_pose((ch("RightUpperArm.rx", t_arm), ch("RightUpperArm.ry", t_arm), ch("RightUpperArm.rz", t_arm, -8.0))),
                    "RightLowerArm": make_pose((ch("RightLowerArm.rx", t_forearm, -16.0), ch("RightLowerArm.ry", t_forearm), ch("RightLowerArm.rz", t_forearm))),
                    "RightHand": make_pose((ch("RightHand.rx", t_hand), ch("RightHand.ry", t_hand), ch("RightHand.rz", t_hand))),
                    "LeftUpperLeg": make_pose((ch("LeftUpperLeg.rx", t), ch("LeftUpperLeg.ry", t), ch("LeftUpperLeg.rz", t))),
                    "LeftLowerLeg": make_pose((ch("LeftLowerLeg.rx", t), 0.0, 0.0)),
                    "LeftFoot": make_pose((ch("LeftFoot.rx", t), 0.0, 0.0)),
                    "RightUpperLeg": make_pose((ch("RightUpperLeg.rx", t), ch("RightUpperLeg.ry", t), ch("RightUpperLeg.rz", t))),
                    "RightLowerLeg": make_pose((ch("RightLowerLeg.rx", t), 0.0, 0.0)),
                    "RightFoot": make_pose((ch("RightFoot.rx", t), 0.0, 0.0)),
                }
                frames.append({"t": t, "poses": poses})

            # Lock final frame of non-loop clips smoothly if near neutral (except death)
            if key != "death" and frames:
                neutral_tail = frames[-1]["poses"]
                for b in list(neutral_tail.keys()):
                    if b == "HumanoidRootPart":
                        neutral_tail[b] = make_pose()

        return {
            "name": clip_name or meta["name"],
            "loop": loop,
            "priority": meta["priority"],
            "fps": fps_val,
            "rootName": "HumanoidRootPart",
            "parents": dict(DEFAULT_R15_PARENTS),
            "frames": frames,
            "markers": markers,
        }

    @staticmethod
    def _get_action_spline_tracks(
        key: str,
        duration: float,
        amp: float,
    ) -> Tuple[Dict[str, List[Tuple[float, float]]], List[Dict[str, Any]]]:
        """Author keyframe splines with anticipation, overshoot, and damped settle."""
        d = duration

        if key == "sword_combo_3hit":
            # Hit 1 (0.0-0.55): windup back right -> diagonal slash across -> overshoot
            # Hit 2 (0.55-1.10): coil left -> backhand slash right -> overshoot
            # Hit 3 (1.10-1.80): crouch coil overhead -> heavy cleave -> follow-through -> recover
            tracks = {
                "LowerTorso.y": [(0.0, 0.0), (0.14 * d, -0.10 * amp), (0.28 * d, -0.05 * amp), (0.45 * d, -0.08 * amp), (0.68 * d, -0.16 * amp), (0.85 * d, -0.06 * amp), (1.0 * d, 0.0)],
                "LowerTorso.ry": [(0.0, 0.0), (0.12 * d, -22.0 * amp), (0.26 * d, 24.0 * amp), (0.42 * d, 28.0 * amp), (0.56 * d, -28.0 * amp), (0.72 * d, -18.0 * amp), (0.84 * d, 18.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.ry": [(0.0, 0.0), (0.12 * d, -28.0 * amp), (0.26 * d, 34.0 * amp), (0.36 * d, -12.0 * amp), (0.55 * d, -32.0 * amp), (0.72 * d, 16.0 * amp), (0.84 * d, 28.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.rx": [(0.0, 0.0), (0.12 * d, 8.0 * amp), (0.26 * d, -14.0 * amp), (0.52 * d, -8.0 * amp), (0.70 * d, 16.0 * amp), (0.83 * d, -26.0 * amp), (1.0 * d, 0.0)],
                "Head.ry": [(0.0, 0.0), (0.12 * d, 18.0 * amp), (0.28 * d, -18.0 * amp), (0.55 * d, 14.0 * amp), (0.83 * d, -10.0 * amp), (1.0 * d, 0.0)],
                "RightUpperArm.rx": [(0.0, -5.0), (0.13 * d, -44.0 * amp), (0.26 * d, 76.0 * amp), (0.33 * d, 84.0 * amp), (0.43 * d, 24.0 * amp), (0.56 * d, 62.0 * amp), (0.72 * d, -94.0 * amp), (0.85 * d, 68.0 * amp), (0.91 * d, 76.0 * amp), (1.0 * d, -5.0)],
                "RightUpperArm.ry": [(0.0, 0.0), (0.13 * d, -34.0 * amp), (0.26 * d, 48.0 * amp), (0.43 * d, 32.0 * amp), (0.56 * d, -42.0 * amp), (0.72 * d, 8.0 * amp), (0.85 * d, 22.0 * amp), (1.0 * d, 0.0)],
                "RightUpperArm.rz": [(0.0, -8.0), (0.13 * d, -32.0 * amp), (0.26 * d, 16.0 * amp), (0.56 * d, -26.0 * amp), (0.72 * d, -12.0 * amp), (0.85 * d, 8.0 * amp), (1.0 * d, -8.0)],
                "RightLowerArm.rx": [(0.0, -16.0), (0.12 * d, -62.0 * amp), (0.25 * d, -14.0 * amp), (0.42 * d, -48.0 * amp), (0.56 * d, -18.0 * amp), (0.71 * d, -54.0 * amp), (0.84 * d, -12.0 * amp), (1.0 * d, -16.0)],
                "RightHand.rx": [(0.0, 0.0), (0.12 * d, 22.0 * amp), (0.26 * d, -34.0 * amp), (0.56 * d, 28.0 * amp), (0.71 * d, 26.0 * amp), (0.85 * d, -38.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperArm.rx": [(0.0, -8.0), (0.12 * d, 22.0 * amp), (0.26 * d, -38.0 * amp), (0.56 * d, 28.0 * amp), (0.71 * d, -32.0 * amp), (0.84 * d, 30.0 * amp), (1.0 * d, -8.0)],
                "LeftLowerArm.rx": [(0.0, -18.0), (0.26 * d, -48.0 * amp), (0.56 * d, -28.0 * amp), (0.84 * d, -45.0 * amp), (1.0 * d, -18.0)],
                "LeftUpperLeg.rx": [(0.0, 0.0), (0.14 * d, 16.0 * amp), (0.45 * d, 14.0 * amp), (0.70 * d, 24.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerLeg.rx": [(0.0, 0.0), (0.14 * d, -30.0 * amp), (0.45 * d, -26.0 * amp), (0.70 * d, -44.0 * amp), (1.0 * d, 0.0)],
                "LeftFoot.rx": [(0.0, 0.0), (0.14 * d, 14.0 * amp), (0.45 * d, 12.0 * amp), (0.70 * d, 20.0 * amp), (1.0 * d, 0.0)],
                "RightUpperLeg.rx": [(0.0, 0.0), (0.14 * d, 12.0 * amp), (0.45 * d, 10.0 * amp), (0.70 * d, 18.0 * amp), (1.0 * d, 0.0)],
                "RightLowerLeg.rx": [(0.0, 0.0), (0.14 * d, -26.0 * amp), (0.45 * d, -22.0 * amp), (0.70 * d, -36.0 * amp), (1.0 * d, 0.0)],
                "RightFoot.rx": [(0.0, 0.0), (0.14 * d, 14.0 * amp), (0.45 * d, 12.0 * amp), (0.70 * d, 18.0 * amp), (1.0 * d, 0.0)],
            }
            markers = [
                {"t": round(0.18 * d, 4), "name": "HitStart", "value": "slash_1"},
                {"t": round(0.30 * d, 4), "name": "HitEnd", "value": "slash_1"},
                {"t": round(0.49 * d, 4), "name": "Hit2Start", "value": "slash_2"},
                {"t": round(0.61 * d, 4), "name": "Hit2End", "value": "slash_2"},
                {"t": round(0.76 * d, 4), "name": "Hit3Start", "value": "cleave_3"},
                {"t": round(0.89 * d, 4), "name": "Hit3End", "value": "cleave_3"},
            ]
            return tracks, markers

        if key == "bow_draw_release":
            tracks = {
                "LowerTorso.y": [(0.0, 0.0), (0.15 * d, -0.05 * amp), (0.58 * d, -0.04 * amp), (0.72 * d, -0.06 * amp), (0.84 * d, -0.03 * amp), (1.0 * d, 0.0)],
                "LowerTorso.ry": [(0.0, 0.0), (0.20 * d, 16.0 * amp), (0.62 * d, 18.0 * amp), (0.74 * d, 10.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.ry": [(0.0, 0.0), (0.20 * d, 42.0 * amp), (0.62 * d, 48.0 * amp), (0.74 * d, 20.0 * amp), (0.86 * d, 24.0 * amp), (1.0 * d, 0.0)],
                "Head.ry": [(0.0, 0.0), (0.20 * d, -54.0 * amp), (0.62 * d, -62.0 * amp), (0.74 * d, -28.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperArm.rx": [(0.0, -5.0), (0.20 * d, 78.0 * amp), (0.62 * d, 84.0 * amp), (0.74 * d, 92.0 * amp), (0.84 * d, 74.0 * amp), (1.0 * d, -5.0)],
                "LeftUpperArm.ry": [(0.0, 0.0), (0.20 * d, -36.0 * amp), (0.62 * d, -42.0 * amp), (0.74 * d, -28.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerArm.rx": [(0.0, -14.0), (0.20 * d, -10.0), (0.62 * d, -8.0), (0.74 * d, -18.0 * amp), (1.0 * d, -14.0)],
                "RightUpperArm.rx": [(0.0, -5.0), (0.15 * d, 42.0 * amp), (0.58 * d, 66.0 * amp), (0.66 * d, 68.0 * amp), (0.74 * d, 42.0 * amp), (0.84 * d, 22.0 * amp), (1.0 * d, -5.0)],
                "RightUpperArm.ry": [(0.0, 0.0), (0.20 * d, 24.0 * amp), (0.58 * d, 56.0 * amp), (0.74 * d, 74.0 * amp), (0.85 * d, 42.0 * amp), (1.0 * d, 0.0)],
                "RightLowerArm.rx": [(0.0, -14.0), (0.22 * d, -58.0 * amp), (0.58 * d, -96.0 * amp), (0.66 * d, -98.0 * amp), (0.74 * d, -52.0 * amp), (1.0 * d, -14.0)],
                "RightHand.rx": [(0.0, 0.0), (0.58 * d, -18.0 * amp), (0.74 * d, 24.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperLeg.rx": [(0.0, 0.0), (0.25 * d, 12.0 * amp), (0.74 * d, 14.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperLeg.ry": [(0.0, 0.0), (0.20 * d, -16.0 * amp), (0.62 * d, -18.0 * amp), (0.74 * d, -10.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerLeg.rx": [(0.0, 0.0), (0.25 * d, -22.0 * amp), (0.74 * d, -26.0 * amp), (1.0 * d, 0.0)],
                "LeftFoot.rx": [(0.0, 0.0), (0.25 * d, 10.0 * amp), (0.74 * d, 12.0 * amp), (1.0 * d, 0.0)],
                "RightUpperLeg.rx": [(0.0, 0.0), (0.25 * d, 10.0 * amp), (0.74 * d, 12.0 * amp), (1.0 * d, 0.0)],
                "RightUpperLeg.ry": [(0.0, 0.0), (0.20 * d, -16.0 * amp), (0.62 * d, -18.0 * amp), (0.74 * d, -10.0 * amp), (1.0 * d, 0.0)],
                "RightLowerLeg.rx": [(0.0, 0.0), (0.25 * d, -18.0 * amp), (0.74 * d, -22.0 * amp), (1.0 * d, 0.0)],
                "RightFoot.rx": [(0.0, 0.0), (0.25 * d, 8.0 * amp), (0.74 * d, 10.0 * amp), (1.0 * d, 0.0)],
            }
            markers = [
                {"t": round(0.18 * d, 4), "name": "DrawStart", "value": "bow"},
                {"t": round(0.58 * d, 4), "name": "FullDraw", "value": "bow"},
                {"t": round(0.68 * d, 4), "name": "Release", "value": "arrow"},
            ]
            return tracks, markers

        if key == "shield_block":
            # Braced guard stance: LowerTorso drops & pitches into the shield while knees/ankles
            # maintain exact sagittal compensation (L1=1.10, L2=0.70) so feet stay planted (<0.01 studs).
            tracks = {
                "LowerTorso.y": [(0.0, 0.0), (0.16 * d, -0.0066 * amp), (0.44 * d, -0.0617 * amp), (0.60 * d, -0.0429 * amp), (0.80 * d, -0.0519 * amp), (1.0 * d, 0.0)],
                "LowerTorso.rx": [(0.0, 0.0), (0.16 * d, 3.0 * amp), (0.44 * d, -5.0 * amp), (0.60 * d, -3.5 * amp), (0.80 * d, -4.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.rx": [(0.0, 0.0), (0.16 * d, 6.0 * amp), (0.44 * d, -14.0 * amp), (0.60 * d, -10.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.ry": [(0.0, 0.0), (0.16 * d, 12.0 * amp), (0.44 * d, -28.0 * amp), (0.60 * d, -22.0 * amp), (1.0 * d, 0.0)],
                "Head.ry": [(0.0, 0.0), (0.46 * d, 24.0 * amp), (0.62 * d, 18.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperArm.rx": [(0.0, -5.0), (0.16 * d, -22.0 * amp), (0.42 * d, 68.0 * amp), (0.54 * d, 56.0 * amp), (0.80 * d, 58.0 * amp), (1.0 * d, -5.0)],
                "LeftUpperArm.ry": [(0.0, 0.0), (0.42 * d, 38.0 * amp), (0.56 * d, 32.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerArm.rx": [(0.0, -14.0), (0.16 * d, -32.0 * amp), (0.42 * d, -88.0 * amp), (0.56 * d, -78.0 * amp), (1.0 * d, -14.0)],
                "LeftHand.ry": [(0.0, 0.0), (0.44 * d, -28.0 * amp), (0.58 * d, -22.0 * amp), (1.0 * d, 0.0)],
                "RightUpperArm.rx": [(0.0, -5.0), (0.42 * d, -24.0 * amp), (0.80 * d, -18.0 * amp), (1.0 * d, -5.0)],
                "RightLowerArm.rx": [(0.0, -14.0), (0.42 * d, -52.0 * amp), (1.0 * d, -14.0)],
                "LeftUpperLeg.rx": [(0.0, 0.0), (0.16 * d, 1.0 * amp), (0.44 * d, 17.0 * amp), (0.60 * d, 13.5 * amp), (0.80 * d, 15.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerLeg.rx": [(0.0, 0.0), (0.16 * d, -10.29 * amp), (0.44 * d, -31.07 * amp), (0.60 * d, -25.84 * amp), (0.80 * d, -28.45 * amp), (1.0 * d, 0.0)],
                "LeftFoot.rx": [(0.0, 0.0), (0.16 * d, 6.29 * amp), (0.44 * d, 19.07 * amp), (0.60 * d, 15.84 * amp), (0.80 * d, 17.45 * amp), (1.0 * d, 0.0)],
                "RightUpperLeg.rx": [(0.0, 0.0), (0.16 * d, 1.0 * amp), (0.44 * d, 17.0 * amp), (0.60 * d, 13.5 * amp), (0.80 * d, 15.0 * amp), (1.0 * d, 0.0)],
                "RightLowerLeg.rx": [(0.0, 0.0), (0.16 * d, -10.29 * amp), (0.44 * d, -31.07 * amp), (0.60 * d, -25.84 * amp), (0.80 * d, -28.45 * amp), (1.0 * d, 0.0)],
                "RightFoot.rx": [(0.0, 0.0), (0.16 * d, 6.29 * amp), (0.44 * d, 19.07 * amp), (0.60 * d, 15.84 * amp), (0.80 * d, 17.45 * amp), (1.0 * d, 0.0)],
            }
            markers = [
                {"t": round(0.14 * d, 4), "name": "BlockAnticipation", "value": "windup"},
                {"t": round(0.42 * d, 4), "name": "BlockReady", "value": "active"},
            ]
            return tracks, markers

        if key == "hit_react":
            tracks = {
                "LowerTorso.y": [(0.0, 0.0), (0.12 * d, -0.08 * amp), (0.34 * d, -0.14 * amp), (0.64 * d, 0.03 * amp), (1.0 * d, 0.0)],
                "LowerTorso.rx": [(0.0, 0.0), (0.14 * d, 14.0 * amp), (0.38 * d, 18.0 * amp), (0.72 * d, -4.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.rx": [(0.0, 0.0), (0.14 * d, 26.0 * amp), (0.34 * d, 32.0 * amp), (0.68 * d, -8.0 * amp), (1.0 * d, 0.0)],
                "UpperTorso.ry": [(0.0, 0.0), (0.18 * d, -18.0 * amp), (0.45 * d, -12.0 * amp), (0.75 * d, 6.0 * amp), (1.0 * d, 0.0)],
                "Head.rx": [(0.0, 0.0), (0.16 * d, 34.0 * amp), (0.40 * d, 38.0 * amp), (0.72 * d, -12.0 * amp), (1.0 * d, 0.0)],
                "LeftUpperArm.rx": [(0.0, -5.0), (0.18 * d, 24.0 * amp), (0.44 * d, 18.0 * amp), (1.0 * d, -5.0)],
                "LeftUpperArm.rz": [(0.0, 8.0), (0.18 * d, 36.0 * amp), (0.44 * d, 28.0 * amp), (1.0 * d, 8.0)],
                "RightUpperArm.rx": [(0.0, -5.0), (0.18 * d, 20.0 * amp), (0.44 * d, 14.0 * amp), (1.0 * d, -5.0)],
                "RightUpperArm.rz": [(0.0, -8.0), (0.18 * d, -34.0 * amp), (0.44 * d, -26.0 * amp), (1.0 * d, -8.0)],
                "LeftUpperLeg.rx": [(0.0, 0.0), (0.28 * d, 18.0 * amp), (1.0 * d, 0.0)],
                "LeftLowerLeg.rx": [(0.0, 0.0), (0.28 * d, -34.0 * amp), (1.0 * d, 0.0)],
                "LeftFoot.rx": [(0.0, 0.0), (0.28 * d, 16.0 * amp), (1.0 * d, 0.0)],
            }
            markers = [
                {"t": round(0.12 * d, 4), "name": "Impact", "value": "hit"},
                {"t": round(0.36 * d, 4), "name": "PeakRecoil", "value": "recoil"},
            ]
            return tracks, markers

        if key == "death":
            tracks = {
                "LowerTorso.y": [(0.0, 0.0), (0.16 * d, -0.06 * amp), (0.42 * d, -0.65), (0.72 * d, -1.65), (0.86 * d, -1.52), (1.0 * d, -1.62)],
                "LowerTorso.rx": [(0.0, 0.0), (0.16 * d, 14.0 * amp), (0.44 * d, 42.0), (0.72 * d, 82.0), (0.86 * d, 76.0), (1.0 * d, 84.0)],
                "UpperTorso.rx": [(0.0, 0.0), (0.18 * d, 24.0 * amp), (0.48 * d, 28.0), (0.76 * d, 12.0), (0.90 * d, 4.0), (1.0 * d, 8.0)],
                "UpperTorso.ry": [(0.0, 0.0), (0.25 * d, -14.0), (0.75 * d, 18.0), (1.0 * d, 14.0)],
                "Head.rx": [(0.0, 0.0), (0.22 * d, 26.0), (0.55 * d, -18.0), (0.82 * d, 22.0), (1.0 * d, 12.0)],
                "LeftUpperArm.rz": [(0.0, 8.0), (0.25 * d, 42.0), (0.72 * d, 74.0), (0.88 * d, 62.0), (1.0 * d, 68.0)],
                "RightUpperArm.rz": [(0.0, -8.0), (0.25 * d, -38.0), (0.72 * d, -68.0), (0.88 * d, -56.0), (1.0 * d, -64.0)],
                "LeftLowerArm.rx": [(0.0, -14.0), (0.50 * d, -32.0), (0.84 * d, -8.0), (1.0 * d, -12.0)],
                "RightLowerArm.rx": [(0.0, -14.0), (0.50 * d, -28.0), (0.84 * d, -10.0), (1.0 * d, -14.0)],
                "LeftUpperLeg.rx": [(0.0, 0.0), (0.30 * d, 32.0), (0.72 * d, 14.0), (1.0 * d, 8.0)],
                "LeftLowerLeg.rx": [(0.0, 0.0), (0.30 * d, -64.0), (0.72 * d, -24.0), (1.0 * d, -12.0)],
                "RightUpperLeg.rx": [(0.0, 0.0), (0.32 * d, 26.0), (0.72 * d, 10.0), (1.0 * d, 6.0)],
                "RightLowerLeg.rx": [(0.0, 0.0), (0.32 * d, -52.0), (0.72 * d, -18.0), (1.0 * d, -10.0)],
            }
            markers = [
                {"t": round(0.16 * d, 4), "name": "Stagger", "value": "hit"},
                {"t": round(0.72 * d, 4), "name": "Grounded", "value": "floor"},
            ]
            return tracks, markers

        # emote_wave
        tracks = {
            "LowerTorso.y": [(0.0, 0.0), (0.14 * d, -0.04 * amp), (0.35 * d, 0.015 * amp), (0.82 * d, 0.0), (1.0 * d, 0.0)],
            "LowerTorso.rz": [(0.0, 0.0), (0.14 * d, 3.0 * amp), (0.36 * d, -4.5 * amp), (0.78 * d, -3.5 * amp), (1.0 * d, 0.0)],
            "UpperTorso.rz": [(0.0, 0.0), (0.14 * d, 5.0 * amp), (0.36 * d, -8.0 * amp), (0.76 * d, -6.0 * amp), (1.0 * d, 0.0)],
            "Head.rz": [(0.0, 0.0), (0.36 * d, 10.0 * amp), (0.76 * d, 8.0 * amp), (1.0 * d, 0.0)],
            "RightUpperArm.rx": [(0.0, -5.0), (0.14 * d, -18.0 * amp), (0.34 * d, 118.0 * amp), (0.48 * d, 128.0 * amp), (0.78 * d, 118.0 * amp), (1.0 * d, -5.0)],
            "RightUpperArm.rz": [(0.0, -8.0), (0.14 * d, 4.0 * amp), (0.34 * d, -42.0 * amp), (0.50 * d, -32.0 * amp), (0.65 * d, -48.0 * amp), (0.80 * d, -34.0 * amp), (1.0 * d, -8.0)],
            "RightLowerArm.rx": [(0.0, -14.0), (0.16 * d, -36.0 * amp), (0.38 * d, -48.0 * amp), (0.52 * d, -20.0 * amp), (0.66 * d, -54.0 * amp), (0.80 * d, -22.0 * amp), (1.0 * d, -14.0)],
            "RightHand.rz": [(0.0, 0.0), (0.38 * d, -24.0 * amp), (0.52 * d, 26.0 * amp), (0.66 * d, -28.0 * amp), (0.80 * d, 22.0 * amp), (1.0 * d, 0.0)],
            "LeftUpperArm.rz": [(0.0, 8.0), (0.45 * d, 14.0 * amp), (1.0 * d, 8.0)],
            "LeftUpperLeg.rz": [(0.0, 0.0), (0.14 * d, -3.0 * amp), (0.36 * d, 4.5 * amp), (0.78 * d, 3.5 * amp), (1.0 * d, 0.0)],
            "RightUpperLeg.rz": [(0.0, 0.0), (0.14 * d, -3.0 * amp), (0.36 * d, 4.5 * amp), (0.78 * d, 3.5 * amp), (1.0 * d, 0.0)],
        }
        markers = [
            {"t": round(0.35 * d, 4), "name": "WaveStart", "value": "wave"},
            {"t": round(0.65 * d, 4), "name": "WavePeak", "value": "wave"},
        ]
        return tracks, markers

    def generate_procedural_presets(
        self,
        preset_names: Optional[List[str]] = None,
        fps: float = 30.0,
        intensity: float = 1.0,
    ) -> Dict[str, Any]:
        """Generate multiple procedural clips keyed by name (for compile_animation_from_clips_luau)."""
        names = preset_names or list(PROCEDURAL_PRESET_CATALOG.keys())
        clips: Dict[str, Dict[str, Any]] = {}
        for pname in names:
            clip = self.generate_procedural_preset(pname, fps=fps, intensity=intensity)
            clips[clip["name"]] = clip
        return {"ok": True, "count": len(clips), "clips": clips}

    # ------------------------------------------------------------------
    # Animation Quality Analyzer
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_expected_kind(name: str, expected_kind: Optional[str]) -> str:
        canonical = {"idle", "walk", "run", "attack", "block", "hit_react", "death", "emote", "generic"}
        if expected_kind:
            raw = expected_kind.strip().lower()
            if raw in canonical:
                return raw
            preset_key = PRESET_ALIASES.get(raw, raw)
            if preset_key in PROCEDURAL_PRESET_CATALOG:
                return str(PROCEDURAL_PRESET_CATALOG[preset_key]["kind"])
            low = raw
        else:
            low = (name or "").strip().lower()
            preset_key = PRESET_ALIASES.get(low, low)
            if preset_key in PROCEDURAL_PRESET_CATALOG:
                return str(PROCEDURAL_PRESET_CATALOG[preset_key]["kind"])
        for kw, kind in (
            ("idle", "idle"),
            ("breath", "idle"),
            ("walk", "walk"),
            ("run", "run"),
            ("sprint", "run"),
            ("jog", "walk"),
            ("death", "death"),
            ("die", "death"),
            ("hit", "hit_react"),
            ("hurt", "hit_react"),
            ("block", "block"),
            ("shield", "block"),
            ("emote", "emote"),
            ("wave", "emote"),
            ("sword", "attack"),
            ("slash", "attack"),
            ("combo", "attack"),
            ("bow", "attack"),
            ("attack", "attack"),
        ):
            if kw in low:
                return kind
        return expected_kind.strip().lower() if expected_kind else "generic"

    def analyze_clip(
        self,
        clip_data: Dict[str, Any],
        expected_kind: Optional[str] = None,
        max_ang_vel_deg_s: float = 950.0,
        max_frame_step_deg: float = 48.0,
    ) -> Dict[str, Any]:
        """Analyze an animation clip for foot sliding, loop seam delta, pops, root motion & priority/loop sanity."""
        clip = self.normalize_clip_dict(clip_data)
        frames = clip["frames"]
        parents = clip["parents"]
        loop = bool(clip["loop"])
        priority = str(clip["priority"])
        fps = float(clip["fps"])
        kind = self._infer_expected_kind(clip["name"], expected_kind)

        issues: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # 1. Priority / loop / timing sanity
        if priority not in VALID_PRIORITIES:
            issues.append({
                "check": "priority_sanity",
                "message": f"Invalid AnimationPriority '{priority}'. Expected one of {VALID_PRIORITIES}.",
            })
        if fps <= 0 or fps > 240:
            issues.append({"check": "fps_sanity", "message": f"Invalid fps {fps}."})
        if len(frames) < 2:
            issues.append({"check": "frame_count", "message": "Clip needs at least 2 frames."})
            return {
                "ok": False,
                "passed": False,
                "quality_score": 0,
                "clip_name": clip["name"],
                "issues": issues,
                "warnings": warnings,
                "metrics": {},
            }

        times = [float(fr["t"]) for fr in frames]
        duration = times[-1] - times[0]
        if duration <= 0 or any(times[i + 1] <= times[i] for i in range(len(times) - 1)):
            issues.append({"check": "monotonic_timestamps", "message": "Keyframe timestamps must strictly increase."})

        if kind == "idle":
            if not loop:
                warnings.append({"check": "loop_sanity", "message": "Idle clip usually has loop=True."})
            if priority not in ("Idle", "Core"):
                warnings.append({"check": "priority_sanity", "message": f"Idle clip has priority '{priority}'; expected 'Idle'."})
        elif kind in ("walk", "run"):
            if not loop:
                issues.append({"check": "loop_sanity", "message": f"Locomotion '{kind}' clip should have loop=True."})
            if priority != "Movement":
                warnings.append({"check": "priority_sanity", "message": f"Locomotion clip has priority '{priority}'; expected 'Movement'."})
        elif kind in ("attack", "hit_react", "death", "emote", "block"):
            if loop and kind != "block":
                warnings.append({"check": "loop_sanity", "message": f"One-shot '{kind}' clip usually has loop=False."})
            if priority in ("Core", "Idle"):
                warnings.append({"check": "priority_sanity", "message": f"Action '{kind}' clip priority '{priority}' may be overridden by Idle/Movement."})

        # 2. Loop seam delta (first vs last frame)
        ident_rot = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        first_poses = frames[0]["poses"]
        last_poses = frames[-1]["poses"]
        all_bones = sorted(set(parents.keys()) | set(first_poses.keys()) | set(last_poses.keys()))

        seam_max_deg = 0.0
        seam_max_studs = 0.0
        seam_worst_joint = ""
        for b in all_bones:
            p0 = first_poses.get(b, {"pos": [0.0, 0.0, 0.0], "rot": ident_rot})
            p1 = last_poses.get(b, {"pos": [0.0, 0.0, 0.0], "rot": ident_rot})
            d_deg = _mat3_geodesic_deg(p0["rot"], p1["rot"])
            d_pos = math.sqrt(sum((float(p1["pos"][k]) - float(p0["pos"][k])) ** 2 for k in range(3)))
            if d_deg > seam_max_deg:
                seam_max_deg = d_deg
                seam_worst_joint = b
            if d_pos > seam_max_studs:
                seam_max_studs = d_pos
                if not seam_worst_joint:
                    seam_worst_joint = b

        if loop and (seam_max_deg > 5.0 or seam_max_studs > 0.08):
            issues.append({
                "check": "loop_seam_delta",
                "joint": seam_worst_joint,
                "angle_deg": round(seam_max_deg, 3),
                "pos_studs": round(seam_max_studs, 4),
                "message": f"Loop seam mismatch on '{seam_worst_joint}' ({seam_max_deg:.2f} deg, {seam_max_studs:.3f} studs).",
            })

        # 3. Rotation pops / over-speed rotation & joint overlap spread
        max_step_deg = 0.0
        max_ang_vel = 0.0
        overspeed_events: List[Dict[str, Any]] = []
        pop_events: List[Dict[str, Any]] = []
        animated_joints: List[str] = []
        peak_vel_times: List[float] = []
        joint_steps_by_bone: Dict[str, List[float]] = {}

        for b in all_bones:
            steps: List[float] = []
            vels: List[float] = []
            total_motion = 0.0
            peak_vel = 0.0
            peak_t = times[0]
            for i in range(len(frames) - 1):
                dt = max(1e-5, times[i + 1] - times[i])
                p_a = frames[i]["poses"].get(b)
                p_b = frames[i + 1]["poses"].get(b)
                if not p_a and not p_b:
                    steps.append(0.0)
                    vels.append(0.0)
                    continue
                r_a = p_a["rot"] if p_a else ident_rot
                r_b = p_b["rot"] if p_b else ident_rot
                d_deg = _mat3_geodesic_deg(r_a, r_b)
                vel = d_deg / dt
                steps.append(d_deg)
                vels.append(vel)
                total_motion += d_deg
                if vel > peak_vel:
                    peak_vel = vel
                    peak_t = 0.5 * (times[i] + times[i + 1])
                if d_deg > max_step_deg:
                    max_step_deg = d_deg
                if vel > max_ang_vel:
                    max_ang_vel = vel
                if d_deg > max_frame_step_deg or vel > max_ang_vel_deg_s:
                    overspeed_events.append({
                        "joint": b,
                        "frame": i + 1,
                        "t": round(times[i + 1], 4),
                        "step_deg": round(d_deg, 2),
                        "ang_vel_deg_s": round(vel, 1),
                    })
            joint_steps_by_bone[b] = steps
            nonzero = [s for s in steps if s > 0.1]
            if total_motion > 1.5 and b != "HumanoidRootPart":
                animated_joints.append(b)
                peak_vel_times.append(peak_t)
            if len(nonzero) >= 3:
                med = statistics.median(nonzero)
                for idx, st in enumerate(steps):
                    if st > 20.0 and st > max(22.0, 3.5 * med):
                        pop_events.append({
                            "joint": b,
                            "frame": idx + 1,
                            "t": round(times[idx + 1], 4),
                            "step_deg": round(st, 2),
                            "median_deg": round(med, 2),
                        })

        if overspeed_events:
            issues.append({
                "check": "overspeed_rotation",
                "count": len(overspeed_events),
                "sample": overspeed_events[:5],
                "message": f"Detected {len(overspeed_events)} over-speed rotation step(s) (max {max_step_deg:.1f} deg/frame, {max_ang_vel:.0f} deg/s).",
            })
        if pop_events and not overspeed_events:
            warnings.append({
                "check": "rotation_pop",
                "count": len(pop_events),
                "sample": pop_events[:5],
                "message": f"Detected {len(pop_events)} sudden single-frame rotation spike(s).",
            })

        # 4. Root / LowerTorso motion check
        lt_ys: List[float] = []
        lt_xz: List[Tuple[float, float]] = []
        lt_rots: List[List[float]] = []
        hrp_pos_list: List[Tuple[float, float, float]] = []
        for fr in frames:
            lt = fr["poses"].get("LowerTorso", {"pos": [0.0, 0.0, 0.0], "rot": ident_rot})
            hrp = fr["poses"].get("HumanoidRootPart", {"pos": [0.0, 0.0, 0.0], "rot": ident_rot})
            lt_ys.append(float(lt["pos"][1]))
            lt_xz.append((float(lt["pos"][0]), float(lt["pos"][2])))
            lt_rots.append(lt["rot"])
            hrp_pos_list.append((float(hrp["pos"][0]), float(hrp["pos"][1]), float(hrp["pos"][2])))

        lt_bob = max(lt_ys) - min(lt_ys)
        lt_rot_span = max(_mat3_geodesic_deg(lt_rots[0], r) for r in lt_rots)
        hrp_span = max(
            math.sqrt(sum((p[k] - hrp_pos_list[0][k]) ** 2 for k in range(3)))
            for p in hrp_pos_list
        )
        has_root_motion = (lt_bob >= 0.012) or (lt_rot_span >= 1.5) or (hrp_span >= 0.03)
        overlap_spread = (max(peak_vel_times) - min(peak_vel_times)) if len(peak_vel_times) >= 2 else 0.0

        # Frozen / 0-motion negative check (idle/any clip with no movement at all)
        if len(animated_joints) == 0 and not has_root_motion:
            issues.append({
                "check": "frozen_static_clip",
                "message": "Clip has no animated joint rotation or root/torso motion across frames (completely frozen pose).",
            })

        if kind in ("walk", "run") and not has_root_motion:
            issues.append({
                "check": "missing_root_motion",
                "message": "Locomotion clip lacks LowerTorso vertical bob / pelvic twist / root motion (looks robotic/floating).",
            })
        elif len(animated_joints) >= 3 and not has_root_motion:
            if kind in ("attack", "hit_react", "death", "block") or overlap_spread < 0.015:
                issues.append({
                    "check": "missing_root_motion",
                    "message": "Multi-joint clip locks LowerTorso/HumanoidRootPart completely static (add hip counter-weight or bob).",
                })
            else:
                warnings.append({
                    "check": "missing_root_motion",
                    "message": "Upper-body clip has static LowerTorso/HumanoidRootPart; add subtle hip counter-weight or bob.",
                })

        # 5. 3D FK foot sliding estimate
        foot_world_traj: Dict[str, List[Tuple[float, float, float]]] = {"LeftFoot": [], "RightFoot": []}
        for fr in frames:
            wf = _solve_r15_world_frames(fr["poses"])
            foot_world_traj["LeftFoot"].append(wf["LeftFoot"][0])
            foot_world_traj["RightFoot"].append(wf["RightFoot"][0])

        is_loco = kind in ("walk", "run")
        check_planted_feet = kind in ("idle", "block", "emote", "other")
        foot_metrics: Dict[str, Any] = {}
        max_foot_slide = 0.0
        for fname, pts in foot_world_traj.items():
            ys = [p[1] for p in pts]
            min_y = min(ys)
            y_span = max(ys) - min_y
            stance_tol = 0.05 if is_loco else 0.16
            stance_indices = [i for i, y in enumerate(ys) if y <= min_y + stance_tol]
            step_slides: List[float] = []
            lateral_slips: List[float] = []
            z_vel_pairs: List[Tuple[int, float]] = []
            for idx in range(len(stance_indices) - 1):
                a, b_idx = stance_indices[idx], stance_indices[idx + 1]
                if b_idx != a + 1:
                    continue
                dx = pts[b_idx][0] - pts[a][0]
                dz = pts[b_idx][2] - pts[a][2]
                dt = max(1e-5, times[b_idx] - times[a])
                horiz = math.hypot(dx, dz)
                step_slides.append(horiz)
                lateral_slips.append(abs(dx))
                z_vel_pairs.append((a, dz / dt))

            total_stance_slide = sum(step_slides)
            max_step_slide = max(step_slides) if step_slides else 0.0
            max_lat_slip = max(lateral_slips) if lateral_slips else 0.0
            # Detect strong Z velocity reversal within consecutive grounded frames
            z_reversals = 0
            for k in range(len(z_vel_pairs) - 1):
                f_a, v_a = z_vel_pairs[k]
                f_b, v_b = z_vel_pairs[k + 1]
                if f_b == f_a + 1 and (v_a * v_b < -0.9):
                    z_reversals += 1

            effective_slide = max_lat_slip if is_loco else max_step_slide
            if effective_slide > max_foot_slide:
                max_foot_slide = effective_slide

            foot_metrics[fname] = {
                "min_y_studs": round(min_y, 4),
                "lift_span_y_studs": round(y_span, 4),
                "stance_frames": len(stance_indices),
                "total_stance_slide_studs": round(total_stance_slide, 4),
                "max_step_slide_studs": round(max_step_slide, 4),
                "max_lateral_slip_studs": round(max_lat_slip, 4),
                "stance_z_reversals": z_reversals,
            }
            if check_planted_feet and (total_stance_slide > 0.35 or max_step_slide > 0.09):
                issues.append({
                    "check": "foot_sliding",
                    "joint": fname,
                    "slide_studs": round(total_stance_slide, 4),
                    "message": f"{fname} slides {total_stance_slide:.3f} studs while planted in '{clip['name']}'.",
                })
            elif is_loco and (max_lat_slip > 0.12 or z_reversals > 1):
                issues.append({
                    "check": "foot_sliding",
                    "joint": fname,
                    "lateral_slip_studs": round(max_lat_slip, 4),
                    "stance_reversals": z_reversals,
                    "message": f"{fname} slips laterally ({max_lat_slip:.3f} studs) or oscillates during stance.",
                })

        # 6. Overlapping action / non-robotic check
        if len(animated_joints) >= 3 and overlap_spread < 0.015:
            issues.append({
                "check": "robotic_lockstep",
                "overlap_spread_sec": round(overlap_spread, 4),
                "message": "All animated joints peak simultaneously (robotic lockstep); add 1-3 frame phase lag for overlapping follow-through.",
            })

        score = 100
        score -= 22 * len(issues)
        score -= 6 * len(warnings)
        score = max(0, min(100, score))

        return {
            "ok": True,
            "passed": len(issues) == 0,
            "quality_score": score,
            "clip_name": clip["name"],
            "inferred_kind": kind,
            "fps": fps,
            "duration_sec": round(duration, 4),
            "frame_count": len(frames),
            "loop": loop,
            "priority": priority,
            "issues": issues,
            "warnings": warnings,
            "metrics": {
                "loop_seam_max_deg": round(seam_max_deg, 3),
                "loop_seam_max_studs": round(seam_max_studs, 4),
                "loop_seam_worst_joint": seam_worst_joint,
                "max_step_deg": round(max_step_deg, 3),
                "max_angular_velocity_deg_s": round(max_ang_vel, 2),
                "overspeed_count": len(overspeed_events),
                "pop_count": len(pop_events),
                "lower_torso_bob_studs": round(lt_bob, 4),
                "lower_torso_rot_span_deg": round(lt_rot_span, 3),
                "has_root_motion": has_root_motion,
                "animated_joint_count": len(animated_joints),
                "joint_overlap_spread_sec": round(overlap_spread, 4),
                "max_foot_slide_studs": round(max_foot_slide, 4),
                "feet": foot_metrics,
            },
        }

    # ------------------------------------------------------------------
    # Luau Compilers (Probe, Clip Build, Track-Cached Playback, RBXMX)
    # ------------------------------------------------------------------

    def compile_probe_rig_luau(self, rig_path: str = "Workspace.Rig") -> str:
        probe_src = self._read_script("probe_rig.luau")
        return f"""--!strict
local TARGET_RIG_PATH = {json.dumps(rig_path)}
{probe_src}
"""

    def compile_playback_test_luau(
        self,
        rig_path: str = "Workspace.Rig",
        clip_name: str = "SharpAnimation",
        folder_name: str = "Animations",
        play_now: bool = True,
        fade_time: float = 0.12,
    ) -> str:
        """Generate Edit/Play-safe Luau using Animator:LoadAnimation (never Humanoid:LoadAnimation) + track caching."""
        return f"""--!strict
local AnimationClipProvider = game:GetService("AnimationClipProvider")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local TARGET_RIG_PATH = {json.dumps(rig_path)}
local TARGET_CLIP_NAME = {json.dumps(clip_name)}
local ANIM_FOLDER_NAME = {json.dumps(folder_name)}
local PLAY_NOW = {"true" if play_now else "false"}
local FADE_TIME = {max(0.0, float(fade_time)):.4g}

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
assert(rig ~= nil and rig:IsA("Model"), "Target rig Model not found: " .. TARGET_RIG_PATH)

local animFolder = ReplicatedStorage:FindFirstChild(ANIM_FOLDER_NAME)
assert(animFolder ~= nil, "Animations folder missing: ReplicatedStorage." .. ANIM_FOLDER_NAME)
local clipInst = animFolder:FindFirstChild(TARGET_CLIP_NAME)
assert(clipInst ~= nil and clipInst:IsA("AnimationClip"), "AnimationClip not found: " .. TARGET_CLIP_NAME)

local controller: Instance? = rig:FindFirstChildOfClass("Humanoid") or rig:FindFirstChildOfClass("AnimationController")
assert(controller ~= nil, "Target rig must contain a Humanoid or AnimationController.")

local animator = controller:FindFirstChildOfClass("Animator")
if not animator then
	local created = Instance.new("Animator")
	created.Parent = controller
	animator = created
end
assert(animator ~= nil, "Failed to resolve Animator.")

-- Track cache keyed by Animator -> cacheKey so repeated plays never call LoadAnimation redundantly
local trackCache: {{ [Animator]: {{ [string]: AnimationTrack }} }} = setmetatable({{}}, {{ __mode = "k" }}) :: any

local function getOrLoadCachedTrack(anim: Animator, key: string, animationObj: Animation, priority: Enum.AnimationPriority, looped: boolean): (AnimationTrack, boolean)
	local perAnimator = trackCache[anim]
	if not perAnimator then
		perAnimator = {{}}
		trackCache[anim] = perAnimator
	end
	local cached = perAnimator[key]
	if cached and cached.Animation and cached.Animation.AnimationId == animationObj.AnimationId then
		return cached, true
	end
	local loaded = anim:LoadAnimation(animationObj)
	loaded.Priority = priority
	loaded.Looped = looped
	perAnimator[key] = loaded
	return loaded, false
end

local regId = AnimationClipProvider:RegisterAnimationClip(clipInst)
local animObj = rig:FindFirstChild("_SharpPreviewAnim_" .. TARGET_CLIP_NAME)
if not (animObj and animObj:IsA("Animation")) then
	local createdAnim = Instance.new("Animation")
	createdAnim.Name = "_SharpPreviewAnim_" .. TARGET_CLIP_NAME
	createdAnim.Parent = rig
	animObj = createdAnim
end
local animation = animObj :: Animation
animation.AnimationId = regId

local track, cacheHit = getOrLoadCachedTrack(animator, TARGET_CLIP_NAME, animation, clipInst.Priority, clipInst.Loop)
if PLAY_NOW then
	for _, playing in ipairs(animator:GetPlayingAnimationTracks()) do
		if playing ~= track and playing.Priority == track.Priority then
			playing:Stop(FADE_TIME)
		end
	end
	track:Play(FADE_TIME)
end

return HttpService:JSONEncode({{
	ok = true,
	rigPath = rig:GetFullName(),
	clipName = TARGET_CLIP_NAME,
	registeredId = regId,
	trackCached = cacheHit,
	isPlaying = track.IsPlaying,
	length = track.Length,
	priority = tostring(track.Priority),
	looped = track.Looped,
	evaluationThrottled = animator.EvaluationThrottled,
}})
"""

    def compile_animation_from_clips_luau(
        self,
        clips_data: Dict[str, Any],
        rig_path: str = "Workspace.Rig",
        anim_format: str = "KeyframeSequence",
        register_preview_clip: bool = True,
        stage_in_animsaves: bool = True,
        install_track_cache_helper: bool = True,
    ) -> str:
        bake_mod = self._load_baker_module()
        test_anim_src = self._read_script("studio_test_anim.luau")

        clips_map: Dict[str, Any]
        if "clips" in clips_data and isinstance(clips_data["clips"], dict):
            clips_map = clips_data["clips"]
        else:
            c_name = str(clips_data.get("name", "DefaultClip"))
            clips_map = {c_name: clips_data}

        clip_builders_luau: List[str] = []
        for clip_name, raw_spec in clips_map.items():
            norm_clip = self.normalize_clip_dict(raw_spec, default_name=str(clip_name))
            builder_src = bake_mod.clip_to_luau(
                norm_clip,
                mode=anim_format,
                target_folder_name="Animations",
                register_preview=register_preview_clip,
            )
            clip_builders_luau.append(
                f"""	do
		local builderOut = (function()
{builder_src}
		end)()
		local folder = ReplicatedStorage:FindFirstChild("Animations")
		local createdInst = if folder then folder:FindFirstChild({json.dumps(norm_clip["name"])}) else nil
		if STAGE_ANIMSAVES and animSaves and createdInst then
			local old = animSaves:FindFirstChild(createdInst.Name)
			if old then old:Destroy() end
			createdInst:Clone().Parent = animSaves
		end
		table.insert(createdClips, {{
			name = {json.dumps(norm_clip["name"])},
			format = {json.dumps(anim_format)},
			keyframeCount = {len(norm_clip["frames"])},
			builderResult = builderOut,
			stagedPath = if (STAGE_ANIMSAVES and animSaves) then (animSaves:GetFullName() .. "." .. {json.dumps(norm_clip["name"])}) else nil,
		}})
	end"""
            )

        builders_joined = "\n".join(clip_builders_luau)
        cache_helper_block = ""
        if install_track_cache_helper:
            cache_helper_src = """--!strict
-- SharpAnimTrackCache: Animator:LoadAnimation track-caching runtime helper
local SharpAnimTrackCache = {}
local _cache: { [Animator]: { [string]: AnimationTrack } } = setmetatable({}, { __mode = "k" }) :: any

function SharpAnimTrackCache.GetOrLoad(animator: Animator, key: string, anim: Animation): AnimationTrack
	local bucket = _cache[animator]
	if not bucket then
		bucket = {}
		_cache[animator] = bucket
	end
	local existing = bucket[key]
	if existing and existing.Animation and existing.Animation.AnimationId == anim.AnimationId then
		return existing
	end
	local track = animator:LoadAnimation(anim)
	bucket[key] = track
	return track
end

function SharpAnimTrackCache.Clear(animator: Animator)
	local bucket = _cache[animator]
	if bucket then
		for _, track in pairs(bucket) do
			pcall(function() track:Stop(0.1) end)
		end
		_cache[animator] = nil
	end
end

return SharpAnimTrackCache
"""
            cache_helper_block = f"""
	local animFolder = ReplicatedStorage:FindFirstChild("Animations")
	if animFolder then
		local prevCache = animFolder:FindFirstChild("SharpAnimTrackCache")
		if prevCache then prevCache:Destroy() end
		local mod = Instance.new("ModuleScript")
		mod.Name = "SharpAnimTrackCache"
		mod.Source = {json.dumps(cache_helper_src)}
		mod.Parent = animFolder
	end"""

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local TARGET_RIG_PATH = {json.dumps(rig_path)}
local STAGE_ANIMSAVES = {"true" if stage_in_animsaves else "false"}

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpRigAnimationCompile", "Sharp MCP: Compile Animation Clip")
local ok, resOrErr = xpcall(function()
	local animSaves = ServerStorage:FindFirstChild("RBX_ANIMSAVES")
	if STAGE_ANIMSAVES and not animSaves then
		animSaves = Instance.new("Model")
		animSaves.Name = "RBX_ANIMSAVES"
		animSaves.Parent = ServerStorage
	end

	local createdClips = {{}}
{builders_joined}
{cache_helper_block}

	return {{
		createdClips = createdClips,
		targetRigPath = TARGET_RIG_PATH,
		studioTestHelperAvailable = {"true" if len(test_anim_src) > 0 else "false"},
		trackCacheInstalled = {"true" if install_track_cache_helper else "false"},
	}}
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

    def export_clips_to_rbxmx(
        self,
        clips_data: Dict[str, Any],
        output_rbxmx_path: str,
        clip_name: str = "SharpAnimation",
    ) -> Dict[str, Any]:
        """Exports a complete KeyframeSequence (with full Pose hierarchy & KeyframeMarkers) .rbxmx file via `clip_to_rbxmx`."""
        bake_mod = self._load_baker_module()
        out_path = Path(output_rbxmx_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if "clips" in clips_data and isinstance(clips_data["clips"], dict) and clips_data["clips"]:
            first_key = next(iter(clips_data["clips"]))
            raw_clip = clips_data["clips"][first_key]
            clip_name = str(first_key)
        else:
            raw_clip = clips_data
            clip_name = str(raw_clip.get("name", clip_name))

        norm_clip = self.normalize_clip_dict(raw_clip, default_name=clip_name)
        xml_content = bake_mod.clip_to_rbxmx(norm_clip)
        out_path.write_text(xml_content, encoding="utf-8")

        return {
            "ok": True,
            "rbxmx_path": str(out_path),
            "clip_name": norm_clip["name"],
            "keyframe_count": len(norm_clip["frames"]),
            "joint_count": len(norm_clip["parents"]),
            "open_cloud_upload_hint": {
                "server": "Roblox_Studio",
                "tool": "open_cloud_invoke",
                "endpoint": "/assets/v1/assets",
                "assetType": "Animation",
            },
        }
