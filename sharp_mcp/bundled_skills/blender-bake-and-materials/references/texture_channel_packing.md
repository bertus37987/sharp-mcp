# Texture Channel Packing & Engine Formats

Standard channel assignments for real-time engines to reduce memory overhead and texture fetch calls.

---

## 1. Engine Channel Formats

Engine / Standard | Map 1 (Albedo) | Map 2 (Normal) | Map 3 (Packed Material / PBR)
:--- | :--- | :--- | :---
**Roblox Studio** (`SurfaceAppearance`) | `ColorMap` (RGB, sRGB) | `NormalMap` (OpenGL Tangent, Non-Color) | Individual `MetalnessMap` & `RoughnessMap`
**Unreal Engine 5** (`ORM / RMA`) | Base Color (RGB, sRGB) | Normal (`+Y` OpenGL, Non-Color) | **R**: Ambient Occlusion, **G**: Roughness, **B**: Metallic
**Unity (HDRP / URP Mask)** | Base Color (RGB, sRGB) | Normal (`+Y` OpenGL, Non-Color) | **R**: Metallic, **G**: Occlusion, **B**: Detail Mask, **A**: Smoothness (1 - Roughness)
**glTF 2.0 / Godot 4** | `baseColorTexture` (sRGB) | `normalTexture` (Non-Color) | `metallicRoughnessTexture`: **B**: Metallic, **G**: Roughness

---

## 2. Normal Map Tangent Space Standards

- **OpenGL Standard** (`+Y` Up): Blender, Roblox Studio, Unreal Engine (modern), Godot, Unity, Maya.
- **DirectX Standard** (`-Y` Down): 3ds Max, legacy Unreal Engine.
- If normal map appears inside-out or lighting is inverted on the top/bottom: invert the Green (`Y`) channel in shader nodes.
