# Playback APIs, Priorities, Events & Runtime Luau Architecture

## 1. `KeyframeSequence` vs. `CurveAnimation`

Both inherit from `AnimationClip` and work with `AnimationClipProvider:RegisterAnimationClip(clip)` and `Animator:LoadAnimation()`.

### `KeyframeSequence` (Universal, XML `.rbxmx` Open Cloud Friendly)
```text
KeyframeSequence (Loop: bool, Priority: Enum.AnimationPriority)
└── Keyframe (Name, Time: number)
    ├── KeyframeMarker (Name: eventName, Value: paramString)   -- optional
    └── Pose (Name = "HumanoidRootPart", Weight = 1, CFrame)
        └── Pose (Name = "LowerTorso", Weight = 1, CFrame, EasingStyle, EasingDirection)
            └── ...
```
- **EasingStyle values**: `Linear (0)`, `Constant (1)`, `Elastic (2)`, `Cubic (3, legacy)`, `Bounce (4)`, `CubicV2 (5)`.
- **Root Pose Rule**: For Humanoid rigs, the root `Pose` MUST be named `"HumanoidRootPart"` with child `"LowerTorso"` (R15) or `"Torso"` (R6).

### `CurveAnimation` (Smooth Hermite/Bezier, Lower Memory, Partial-Rig Tolerant)
```text
CurveAnimation (Loop: bool, Priority: Enum.AnimationPriority)
├── HumanoidRootPart (Folder — nested mirroring rig hierarchy!)
│   └── LowerTorso (Folder)
│       ├── Position (Vector3Curve)   -- v3:X()/Y()/Z():SetKeys({ FloatCurveKey.new(t, v, mode) })
│       ├── Rotation (RotationCurve)  -- rc:InsertKey(RotationCurveKey.new(t, cf, mode)) (avoid :SetKeys which throws Variant cast failed)
│       └── UpperTorso (Folder)
│           └── ...
├── [FaceControlName] (FloatCurve)    -- optional facial animation
└── [EventName] (MarkerCurve)         -- one MarkerCurve per event name (mc.Name = "HitStart"); mc:InsertMarkerAtTime(t, paramStr)
```
- `FloatCurveKey.new(time, value, Enum.KeyInterpolationMode.Cubic)` (or `Linear`, `Constant`).
- `RotationCurveKey.new(time, cframe, Enum.KeyInterpolationMode.Cubic)`.
- Advantage: Supports partial hierarchies cleanly without failing if a character lacks an optional bone.

---

## 2. Animation Priority & Layering Rules

`Enum.AnimationPriority` (evaluation precedence from lowest to highest; note `.Value` integers in `.rbxmx` XML differ from evaluation rank!):
1. `Core` (lowest precedence; `.Value = 1000`) — fallback base
2. `Idle` (`.Value = 0`) — standing/breathing loops
3. `Movement` (`.Value = 1`) — walk, run, swim, climb, strafe
4. `Action` (`.Value = 2`) — equipped hold, shield block, weapon draw
5. `Action2` (`.Value = 3`) — quick swings, reloads, combo hits
6. `Action3` (`.Value = 4`) — heavy finishers, arrow/spear release, dodges
7. `Action4` (highest precedence; `.Value = 5`) — cutscenes, QA override, hit-stun/death

### Partial-Body Overlays (Swinging While Walking!)
To swing a sword or raise a shield while the player's **legs keep walking**:
- In your `Movement` (Walk/Run) clip, author **all 15 R15 joints** (`Weight = 1`).
- In your upper-body `Action`/`Action2` clip (slash, block, bow draw), **omit leg poses** (or set leg `Pose.Weight = 0` / exclude leg folders in `CurveAnimation`).
- Because `Action` only touches torso/head/arms and has higher priority than `Movement`, Roblox automatically blends the upper-body slash cleanly over the lower-body walk cycle!

---

## 3. Eliminating Default `Animate` Script Conflicts

A common Roblox animation bug is playing a custom `Idle` or `Walk` track while the default `StarterCharacterScripts` / character `Animate` script ALSO plays Roblox's built-in `Idle`/`Walk` tracks—resulting in blended half-animations.

Choose one of two clean solutions:
1. **Replace IDs inside `Animate` (Simplest for standard locomotion)**:
   - Play Solo -> copy `Workspace.<YourName>.Animate` -> paste into `StarterPlayer.StarterCharacterScripts`.
   - Swap `AnimationId` on child `Animation` instances (`idle.Animation1`, `idle.Animation2`, `walk.WalkAnim`, `run.RunAnim`, `jump.JumpAnim`, `fall.FallAnim`).
2. **Custom State Machine (Best for class/weapon-specific locomotion)**:
   - Destroy or disable the character's default `Animate` `LocalScript` (note: Roblox injects `Animate` shortly *after* `CharacterAdded`, so wait for `character:FindFirstChild("Animate")` or watch `ChildAdded` and destroy/disable it cleanly).
   - Drive Idle / Walk / Run / Jump / Crouch exclusively from your own locomotion module using `Humanoid.MoveDirection.Magnitude` and `Humanoid:GetState()`, stopping previous state tracks with `track:Stop(0.15)` before calling `nextTrack:Play(0.15)`.

---

## 4. Animation Events (`KeyframeMarker` & `MarkerCurve`)

Never hardcode `task.wait(0.28)` for sword hitboxes or projectile spawns (breaks when `AdjustSpeed()` changes!).
- In Blender, add timeline markers (`add_animation_marker(rig, frame, "HitStart")` — name `"HitStart"` or `"HitStart: value"`).
- In `KeyframeSequence`, markers map to `KeyframeMarker` children (`Name = eventName`, `Value = paramStr`). In `CurveAnimation`, create one `MarkerCurve` per event name (`mc.Name = eventName`) and call `mc:InsertMarkerAtTime(t, paramStr)` — `GetMarkerReachedSignal(eventName)` matches `MarkerCurve.Name`, not `.Value`.
- Connect in Luau:
  ```lua
  track:GetMarkerReachedSignal("HitStart"):Connect(function(param)
      enableWeaponHitbox(true)
  end)
  track:GetMarkerReachedSignal("HitEnd"):Connect(function(param)
      enableWeaponHitbox(false)
  end)
  ```
- Also use `track.Ended` (fires when a non-looped track finishes), `track.Stopped` (fires on `Stop()` or completion), and `track.DidLoop`.

---

## 5. Local Studio Testing (`AnimationClipProvider`) vs. Published IDs

- **Instant Local Studio Preview (No Cloud Upload)**:
  ```lua
  local AnimationClipProvider = game:GetService("AnimationClipProvider")
  local clipId = AnimationClipProvider:RegisterAnimationClip(keyframeSeqOrCurveAnim)
  local anim = Instance.new("Animation")
  anim.AnimationId = clipId
  local track = animator:LoadAnimation(anim)
  track:Play()
  ```
  *(Note: `KeyframeSequenceProvider:RegisterKeyframeSequence()` is **deprecated** — always use `AnimationClipProvider:RegisterAnimationClip()`. Registered hashes are session-temporary for Studio Edit/Playtest.)*

---

## 6. Client-Server Replication Rules

- **Player Characters & Client Network-Owned Models**:
  - Load and play animations in a **`LocalScript`** on the **Client** (`player.Character`).
  - Roblox automatically replicates `Animator` tracks played by the network owner to the server and all other clients with zero input lag!
- **Server-Owned NPCs, Bosses & World Objects (Doors, Chests)**:
  - Load and play animations in a **`Script`** on the **Server**.
  - **Gotcha**: Playing an animation locally on a client for a server-owned NPC will NOT replicate to anyone else.
- **Avoid Deprecated Calls**: Always call `animator:LoadAnimation(anim)`, NEVER `humanoid:LoadAnimation(anim)` or `animController:LoadAnimation(anim)`.
