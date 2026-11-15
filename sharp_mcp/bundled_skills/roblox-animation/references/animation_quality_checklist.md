# Roblox Animation Quality Checklist & Runtime Standards

Follow these guidelines when generating, auditing, or playing back R15/R6 animations in Roblox Studio.

## 1. Runtime Playback & Track Caching (Luau)

- **Always use `Animator:LoadAnimation(animation)`** — `Humanoid:LoadAnimation` and `AnimationController:LoadAnimation` are deprecated and create replication/throttling bugs.
- Resolve or create the `Animator` cleanly via `humanoid:FindFirstChildOfClass("Animator")` (or under `AnimationController`).
- **Cache loaded `AnimationTrack` instances** per `(Animator, Animation/Clip)` in a weak-keyed table (`setmetatable({}, { __mode = "k" })`) instead of calling `LoadAnimation` on every swing, jump, or equip. Repeatedly calling `LoadAnimation` leaks toward the ~256 concurrent track limit per `Animator`.
- Use named **Keyframe Markers** (`HitStart`, `HitActive`, `HitEnd`, `StepL`, `StepR`, `Release`, `Impact`, `ComboWindow`) via `track:GetMarkerReachedSignal(name)` instead of brittle `task.wait()` delays.
- Account for `Workspace.ClientAnimatorThrottling` (`EvaluationThrottled` property on distant NPC `Animator`s): gameplay timing/damage stays server-authoritative rather than assuming client tracks always evaluate at 60 Hz.

## 2. Non-Robotic Motion Principles

- **Anticipation**: Counter-rotate before the main action (e.g., wind up the torso & arm slightly backward before a sword slash or bow release).
- **Follow-Through & Overshoot**: Push 10–18% past the target pose at impact/peak, then settle back cleanly with easing instead of linear clamping.
- **Joint Phase Overlap**: Never start and stop `UpperTorso`, `UpperArm`, `LowerArm`, and `Hand` on the exact same keyframe. Lead with `LowerTorso`/`UpperTorso`, trail shoulders by 1–2 frames, elbows by 2–3 frames, and wrists/weapon by 3–4 frames.
- **Counter-Balance**: When one arm swings forward, counter-rotate `UpperTorso` and the opposite leg/hip slightly so the silhouette stays grounded.

## 3. Automated Quality Audit (`RigAnimationEngine.analyze_clip`)

Run `RigAnimationEngine.analyze_clip(clip_data)` before shipping clips to catch:

1. **Foot Sliding (3D FK Check)**: During `walk` and `run` cycles, planted stance feet (`LeftFoot`/`RightFoot`) should remain within roughly `<= 0.12` studs/frame of horizontal world motion relative to their planted phase. Excessive slip means leg swing doesn't match root height/pelvis bounce.
2. **Loop Seam Delta**: For `loop=True` clips (`idle*`, `walk*`, `run*`), the first frame (`t = 0`) and final frame (`t = duration`) should align smoothly (rotation delta `<= 4°`, root translation delta `<= 0.03` studs) to eliminate snap-pops on wrap.
3. **Rotation Pops & Angular Velocity**: Single-frame joint deltas should stay `<= 48°` and angular speed `<= 950°/s` outside explicit impact snaps.
4. **Missing Root / Torso Motion**: Dynamic clips should animate `LowerTorso`/`HumanoidRootPart` (subtle weight drop, twist, or breathing heave) rather than pinning the pelvis rigid.
5. **Priority & Loop Sanity**:
   - `idle_breathing`: `Priority = Idle`, `Loop = true`
   - `walk`, `run`: `Priority = Movement`, `Loop = true`
   - `shield_block`, `sword_combo_3hit`, `bow_draw_release`, `hit_react`, `death`, `emote_wave`: `Priority = Action`..`Action4`, `Loop = false` (enable `track.Looped = true` at runtime for sustained hold poses if desired)

## 4. Built-in Procedural Quality Presets

Use `RigAnimationEngine.generate_procedural_preset(preset_name, fps=30.0, intensity=1.0)` for ready-to-export clips with overlapping anticipation/follow-through and markers:

- `idle_breathing`
- `walk`
- `run`
- `sword_combo_3hit`
- `bow_draw_release`
- `shield_block`
- `hit_react`
- `death`
- `emote_wave`
