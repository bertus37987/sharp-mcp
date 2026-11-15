# Lighting, Atmosphere, Sky, Clouds, GlobalWind, and PostFX

Cohesive Roblox visuals rely on five coordinated systems: **`Lighting`** (global illumination & time), **`Atmosphere`** (aerial perspective & scattering), **`Clouds`** + **`Sky`** (skyscape & celestial bodies), **`Workspace.GlobalWind`** (dynamic motion), and **`PostEffect`s** (global or camera-local image finishing).

---

## 1. `Lighting` Service & `Lighting.Technology` Security Warning

> **CRITICAL (`RobloxScriptSecurity`)**: `Lighting.Technology` (`Legacy`, `Voxel`, `Compatibility`, `ShadowMap`, `Future`, `Unified`) has **`RobloxScriptSecurity` on BOTH read and write** and is **deprecated**. Any script (even Studio plugins or `execute_luau`) that directly writes `Lighting.Technology = ...` or reads it without `pcall` **will throw a security error and crash**!
> - **In scripts**: Use **`Lighting.LightingStyle`** (`Enum.LightingStyle.Realistic` | `Soft`) + **`Lighting.PrioritizeLightingQuality`** (`boolean`), and wrap any diagnostic check of `Lighting.Technology` in `pcall`.
> - **In Studio UI**: `Technology` (if exposed on legacy templates) or `LightingStyle` is edited manually in the **Explorer -> Lighting -> Properties** panel.
> - Also avoid deprecated no-op properties `Lighting.Outlines` and `Lighting.ShadowColor`.

### Key Scriptable `Lighting` Properties (`Security: None`)
| Property | Type / Range | Notes & Pitfalls |
| :--- | :--- | :--- |
| `ClockTime` / `TimeOfDay` | `0..24` (`float`) / `"HH:MM"` | Linked 1:1 (`SetMinutesAfterMidnight` also syncs both); static unless scripted |
| `GeographicLatitude` | `float` (degrees) | Tilts sun/moon arc without changing `ClockTime`; query vectors via `GetSunDirection()` / `GetMoonDirection()` |
| `Brightness` | `float` | Sun/moon directional light intensity |
| `ExposureCompensation` | `-5..5` (`float`, def `0`) | Pre-tonemap exposure (`+1` = 2× light, `-1` = 0.5× light) |
| `Ambient` | `Color3` (def `0,0,0`) | Hue for sky-occluded / indoor shadow areas |
| `OutdoorAmbient` | `Color3` (def `127,127,127`) | Hue for outdoor unoccluded areas; **clamped `>= Ambient` per channel** when `GlobalShadows = true` (ignored when `GlobalShadows = false`) |
| `ColorShift_Top` / `ColorShift_Bottom` | `Color3` | Subtle warm/cool tint on surfaces facing toward / away from sun/moon |
| `GlobalShadows` | `boolean` | Enables 4×4×4 voxel / shadow-map shadows (`true` recommended) |
| `ShadowSoftness` | `0..1` (`float`, def `0.2`) | Softness when `LightingStyle = Realistic` (or shadow-map capable devices) |
| `LightingStyle` | `Enum.LightingStyle` | `Realistic` (modern PBR/shadow-map) vs `Soft` (flat retro look) |
| `PrioritizeLightingQuality` | `boolean` | `true` preserves shaders/shadows at closer range as quality scales down; `false` prioritizes draw distance |
| `EnvironmentDiffuseScale` / `EnvironmentSpecularScale` | `0..1` (`float`, def `0`) | Sky-based PBR ambient diffuse & metallic reflections; set **`1, 1`** (with `Ambient`/`OutdoorAmbient` near `0,0,0`) for realistic PBR metals |
| `FogStart` / `FogEnd` / `FogColor` | `float` / `Color3` | **HIDDEN AND IGNORED whenever an `Atmosphere` child exists under `Lighting`** |

---

## 2. `Atmosphere` (Parented Under `Lighting`)

`Atmosphere` simulates aerial perspective and physically based sunlight scattering. Adding an `Atmosphere` to `Lighting` disables legacy `FogStart`/`FogEnd`/`FogColor`.

| Property | Effect & Dependencies |
| :--- | :--- |
| `Density` (`float`) | Air particle density obscuring distant terrain/objects (`0.22..0.45` natural; `0.55..0.8` foggy/volcanic). Does not directly tint the skybox, only obscures things in front of it |
| `Offset` (`float`, `0..1`) | Balances horizon silhouette vs seamless sky fade. **Warning**: too low `Offset` causes **skybox ghosting** through distant terrain; too high `Offset` reveals distant LOD popping |
| `Haze` (`float`) | Horizon & distance atmospheric haze. Combine with `Color` for mood |
| `Color` (`Color3`) | Hue of the scattered haze (needs `Haze > 0` to show strongly) |
| `Glare` (`float`) | Directional solar halo around the sun. **REQUIRES `Haze > 0` to have any visible effect!** |
| `Decay` (`Color3`) | Hue transition away from the sun (falls off from `Color` toward `Decay`). **REQUIRES BOTH `Haze > 0` AND `Glare > 0` to have any visible effect!** |

---

## 3. `Clouds` (MUST Parent Under `Workspace.Terrain`!)

> **CRITICAL PITFALL**: A `Clouds` instance **ONLY renders when parented under `Workspace.Terrain`**! Parenting `Clouds` under `Lighting`, `Workspace`, or `ReplicatedStorage` compiles without errors and silently renders nothing.

| Property | Type / Range | Meaning |
| :--- | :--- | :--- |
| `Enabled` | `boolean` | Toggles rendering (useful when swapping multiple `Clouds` presets) |
| `Cover` | `0..1` (`float`) | Sky coverage (`0` = clear, `0.4..0.65` partly cloudy, `0.85..1.0` overcast/storm) |
| `Density` | `0..1` (`float`) | Cloud opacity/thickness (`0.1` wispy, `0.3..0.6` dramatic, `0.8+` heavy storm) |
| `Color` | `Color3` | Base particle tint (also heavily modulated by `Lighting` & `Atmosphere` sun angle) |

---

## 4. `Sky` (Parented Under `Lighting`) & `Workspace.GlobalWind`

### `Sky`
- **Cubemap Faces**: `SkyboxBk`, `SkyboxDn`, `SkyboxFt`, `SkyboxLf`, `SkyboxRt`, `SkyboxUp` (plus `*Content` variants). Also provides environment reflection cubemaps for `ViewportFrame`s.
- **Celestial Bodies**: `CelestialBodiesShown` (`boolean`), `SunTextureId`, `SunAngularSize` (`0..60`, default `21`), `MoonTextureId`, `MoonAngularSize`, `StarCount` (note: `Lighting:GetMoonPhase()` always returns `0.75`).
- **`SkyboxOrientation` (`Vector3` degrees)**: Applied **Y -> X -> Z**. Safe for continuous spin `(30, (y + speed * dt) % 360, 0)` (modulo `360` prevents float drift), **except** it does NOT rotate celestial bodies, `Clouds` under `Terrain`, or indoor mirror cubemaps.

### `Workspace.GlobalWind` (`Vector3`)
- Controls speed and direction of **Terrain animated grass** (`Decoration = true`), **dynamic `Clouds`** drift, `Fire`/`Smoke`, and `ParticleEmitter`s where `WindAffectsDrag = true` and `Drag > 0`.
- For natural gusts, modulate `workspace.GlobalWind = baseWind + math.sin(...) * gust` smoothly (provided by `AtmospherePresets.StartWindGustLoop`).

---

## 5. `PostEffect`s (`Lighting` Global vs `Workspace.CurrentCamera` Local)

| Effect | Key Properties | Parenting & Gotchas |
| :--- | :--- | :--- |
| `BloomEffect` | `Intensity`, `Size`, `Threshold` (`0` = all pixels, `1` = only pure white/HDR) | Global in `Lighting` or per-player in `CurrentCamera`; multiple compose |
| `ColorCorrectionEffect` | `Brightness` (`-1..1`), `Contrast`, `Saturation` (`-1` = B&W), `TintColor` (multiplicative) | Global in `Lighting` or local in `CurrentCamera` (damage flash, underwater tint); multiple compose |
| `ColorGradingEffect` | `TonemapperPreset` (`Enum.TonemapperPreset.Default` \| `Retro`) | **MUST be parented to `Lighting` — ignored under `CurrentCamera` or elsewhere!** Only most recently parented instance in `Lighting` applies |
| `SunRaysEffect` | `Intensity` (`0..1`), `Spread` (`0..1` only; outside range undefined) | Global in `Lighting` or local in `CurrentCamera`; occluded by 3D geometry between camera and sun |
| `BlurEffect` | `Size` (px radius) | `Lighting` or `CurrentCamera` (great for pausing/modal focus); **only 1 applies (largest `Size` wins)** |
| `DepthOfFieldEffect` | `FocusDistance`, `InFocusRadius`, `NearIntensity`, `FarIntensity` | `Lighting` or `CurrentCamera` (NPC dialog / item showcase focus) |

> **Golden Rule**: Put world look-dev (`ColorGradingEffect`, `SunRaysEffect`, subtle `BloomEffect`, world `ColorCorrectionEffect`) in **`Lighting`**; put transient gameplay/UI effects (`BlurEffect` behind menus, red low-HP `ColorCorrectionEffect`, close-up `DepthOfFieldEffect`) in **`Workspace.CurrentCamera`** via a `LocalScript`.
