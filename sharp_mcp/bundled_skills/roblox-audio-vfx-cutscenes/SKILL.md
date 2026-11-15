---
name: roblox-audio-vfx-cutscenes
description: >-
  Build modern Roblox node-based Audio Wiring graphs (AudioPlayer, Wire,
  AudioFader, AudioEqualizer, AudioReverb, AudioCompressor, AudioEmitter,
  AudioListener, AudioDeviceOutput), ParticleEmitter flipbook burst presets,
  31-cap Highlight pools, trauma camera shake, and Catmull-Rom cutscene splines.
  Use whenever the user asks for sound effects, music buses, 3D spatial audio,
  particle effects, hit flashes, camera shake, or cinematic cutscenes.
---

# Roblox Audio Wiring, VFX Flipbooks, Highlight Pooling & Cutscenes (`roblox-audio-vfx-cutscenes`)

Production architecture and `--!strict` Luau modules for Roblox's modern **Audio Wiring API** (`AudioPlayer` -> `Wire` -> `AudioFader` -> `AudioDeviceOutput`), built-in `rbxasset://sounds/*` & `rbxasset://textures/particles/*` zero-upload assets, **31-instance capped `Highlight` pools**, burst `ParticleEmitter` flipbooks, Perlin trauma camera shake, and Catmull-Rom spline cutscenes.

---

## 1. Non-Negotiable Engine Guardrails

1. **`--!strict` Everywhere:** All audio, VFX, and camera scripts MUST begin with `--!strict` on line 1.
2. **Modern Audio Graph API (`AudioPlayer` + `Wire`):**
   - Route audio through structured buses (`Master`, `BGM`, `SFX`, `UI`, `Voice`/`Ambient`) under `SoundService.SharpAudioBuses` using `AudioFader`, `AudioEqualizer`, `AudioCompressor` (sidechain ducking), and `AudioReverb` wired to `AudioDeviceOutput`.
   - For 3D spatial sound, wire `AudioPlayer` -> `AudioEmitter` (parented to an `Attachment` or `BasePart`) and ensure an `AudioListener` is attached to `Workspace.CurrentCamera` or `LocalPlayer.Character.Head` wired to `AudioDeviceOutput`.
   - Use built-in `rbxasset://sounds/*` (`button.wav`, `swordslash.wav`, `lunge.wav`, `electronicpingshort.wav`, `action_footsteps_plastic.mp3`) for instant zero-moderation sound playback in Studio.
3. **Burst `ParticleEmitter` & Flipbook Rules:**
   - For one-shot hit sparks, explosions, and level-up bursts, ALWAYS set `ParticleEmitter.Rate = 0` and trigger `emitter:Emit(burstCount)`.
   - When using sprite-sheet flipbooks (`FlipbookLayout.TwoByTwo`, `FourByFour`, `EightByEight`), the texture dimensions MUST be exact powers of two (`256x256`, `512x512`, `1024x1024`).
4. **Hard 31 `Highlight` Instance Limit:**
   - Roblox enforces a hard engine cap of **31 simultaneous active `Highlight` instances** per client. Exceeding 31 causes newer highlights to silently fail to render.
   - ALWAYS allocate hit-flash and outline `Highlight`s through `VfxPresetAndHighlightPool` (which enforces `MAX_ACTIVE_HIGHLIGHTS = 28` with LRU eviction and automatic fade-out recycling).
5. **Camera Shake & Cutscene Priority:**
   - Bind camera shake at `Enum.RenderPriority.Camera.Value + 1` via `RunService:BindToRenderStep` so it layers cleanly as a delta offset over default Roblox camera scripts without fighting `Camera.CFrame`.
   - For full cutscene splines, save `Camera.CameraType` and `Camera.CFrame` before switching to `Enum.CameraType.Scriptable`, and restore them deterministically on completion or skip.

---

## 2. Canonical Scripts & References

### Scripts (`scripts/`)
- [`scripts/audio_bus_graph_builder.luau`](scripts/audio_bus_graph_builder.luau): `AudioBusGraphBuilder` — Constructs the 4-bus `SoundService.SharpAudioBuses` graph (`BGM`, `SFX`, `UI`, `Ambient` -> `MasterFader` -> `AudioDeviceOutput`), spawns 2D/3D `AudioPlayer` + `AudioEmitter` nodes, and provides built-in `rbxasset://sounds/*` catalog helpers.
- [`scripts/vfx_preset_and_highlight_pool.luau`](scripts/vfx_preset_and_highlight_pool.luau): `VfxPresetAndHighlightPool` — Deterministic `ParticleEmitter` burst presets (`HitSparks`, `ExplosionFlipbook`, `LevelUpNova`, `DashSmoke`) and a 28-slot LRU `Highlight` pool manager.
- [`scripts/camera_shake_and_cutscene.luau`](scripts/camera_shake_and_cutscene.luau): `CameraShakeAndCutscene` — Perlin-noise trauma camera shake (`trauma^2` rotational/translational offset) and Catmull-Rom CFrame spline evaluator with `DepthOfFieldEffect` rack focus.

### References (`references/`)
- [`references/audio_graph_vfx_and_camera_patterns.md`](references/audio_graph_vfx_and_camera_patterns.md): Built-in `rbxasset://` sound & particle catalog, `Wire` pin names (`SourceInstance`, `TargetInstance`, `SourceName`, `TargetName`), and Catmull-Rom spline math.

---

## 3. Execution Workflow via `Sharp` MCP

1. Call `sharp_audio_vfx_cutscenes(action="install", ...)` to install the audio, VFX, and camera modules and construct `SoundService.SharpAudioBuses` plus `Workspace._SharpHighlightPool`.
2. Call `sharp_audio_vfx_cutscenes(action="smoke_test")` to verify 2D/3D audio emitters, burst `ParticleEmitter` presets (`Rate = 0`), LRU 28-slot `Highlight` eviction, trauma camera shake, and spline evaluation.
3. Call `sharp_art_studio(action="create_vfx", vfx_mode="both")` to generate custom palette-matched 4×4 2D UI & 3D World VFX flipbook textures plus `SharpUiVfx.luau` and `SharpWorldVfx.luau`.
4. Call `sharp_media_qa(action="inspect_audio", audio_path=...)` (for SFX/BGM peak, RMS, clipping, DC-offset, silence, and Gemini audio critique) and `sharp_media_qa(action="inspect_video", focus="playtest")` to inspect combined visuals + sound in playtests.
