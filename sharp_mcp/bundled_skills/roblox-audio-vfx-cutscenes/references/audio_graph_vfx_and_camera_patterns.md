# Audio Wiring Graph, Particle Flipbook, Highlight Pool & Camera Cutscene Reference

## 1. Built-In Zero-Upload `rbxasset://` Sound & Particle Catalog

| Asset Key | URI (`rbxasset://...`) | Recommended Use |
| :--- | :--- | :--- |
| `UI_ButtonClick` | `rbxasset://sounds/button.wav` | Button clicks, tab switches (`UI` bus) |
| `UI_QuestPing` | `rbxasset://sounds/electronicpingshort.wav` | Quest complete, toast notification, reward claim (`UI` bus) |
| `Combat_SwordSlash` | `rbxasset://sounds/swordslash.wav` | Light melee swing (`SFX` 3D emitter) |
| `Combat_SwordLunge` | `rbxasset://sounds/lunge.wav` | Heavy attack / dash strike (`SFX` 3D emitter) |
| `Movement_Footstep` | `rbxasset://sounds/action_footsteps_plastic.mp3` | Locomotion footstep loop (`SFX` 3D emitter) |
| `VFX_Sparkles` | `rbxasset://textures/particles/sparkles_main.dds` | Hit sparks, loot drop glint, level-up burst |
| `VFX_Smoke` | `rbxasset://textures/particles/smoke_main.dds` | Dash dust cloud, landing puff |
| `VFX_Explosion4x4` | `rbxasset://textures/particles/explosion01_implosion_main.dds` | `FlipbookLayout.FourByFour` (`OneShot`) impact burst |
| `VFX_Fire` | `rbxasset://textures/particles/fire_main.dds` | Torch, fireball trail, burn status |

---

## 2. Modern Audio Wiring Graph Topology

```text
SoundService
└── SharpAudioBuses (Folder)
    ├── AudioDeviceOutput
    ├── MasterFader (AudioFader, Volume = 1.0) ──[Wire]──> AudioDeviceOutput
    ├── BGM_Bus (AudioFader, Volume = 0.7) ──[Wire]──> BGM_Compressor (AudioCompressor) ──[Wire]──> MasterFader
    ├── SFX_Bus (AudioFader, Volume = 0.9) ──[Wire]──> SFX_Reverb (AudioReverb) ──[Wire]──> MasterFader
    ├── UI_Bus  (AudioFader, Volume = 0.85) ──[Wire]──> MasterFader
    └── Ambient_Bus (AudioFader, Volume = 0.6) ──[Wire]──> MasterFader
```

- Every `Wire` connects `wire.SourceInstance = sourceNode` and `wire.TargetInstance = targetNode`.
- For sidechain ducking (e.g., lowering `BGM` when boss dialogue or heavy `SFX` plays), wire the trigger bus to `BGM_Compressor` with `wire.TargetName = "Sidechain"`.

---

## 3. 31-Instance `Highlight` Pool Discipline

- Roblox silently stops rendering any `Highlight` beyond 31 active instances in the place.
- `VfxPresetAndHighlightPool` caps its pool at `28` reusable `Highlight` instances stored under `Workspace._SharpHighlightPool` (leaving 3 slots of headroom for local selection/quest indicators).
- When `FlashTarget(model, fillColor, outlineColor, durationSec)` is called:
  1. Reuses an idle `Highlight` or evicts the oldest active `Highlight` (LRU).
  2. Sets `Adornee = model`, `DepthMode = Enum.HighlightDepthMode.Occluded`, `FillTransparency = 0.25`, `OutlineTransparency = 0.0`.
  3. Smoothly interpolates `FillTransparency -> 1` and releases `Adornee = nil`.
