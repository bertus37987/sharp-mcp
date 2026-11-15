# Game Asset Budgets & Optimization Standards

This guide specifies target poly counts, texture resolutions, and collision requirements for real-time engines (Roblox, Unity, Unreal Engine, Godot).

---

## 1. Triangle Count Budgets

Category | Low-Poly / Stylized | Mid-Poly / Competitive | High-Fidelity Hero
:--- | :--- | :--- | :---
**Consumables / Pickups** (Potion, Denarii, Fruit, Ammo) | 100 – 400 tris | 400 – 800 tris | 1,000 – 2,000 tris
**Melee Weapons** (Gladius, Spatha, Axe, Spear, Dagger) | 600 – 1,500 tris | 1,500 – 3,500 tris | 4,000 – 8,000 tris
**Ranged Weapons** (Bow, Crossbow, Ballista, Sling) | 800 – 2,000 tris | 2,000 – 4,500 tris | 5,000 – 10,000 tris
**Shields** (Scutum, Parma, Buckler) | 400 – 1,200 tris | 1,200 – 2,800 tris | 3,000 – 6,000 tris
**Armor Piece** (Helmet, Chest, Greaves, Pauldrons) | 300 – 900 tris/pc | 900 – 2,200 tris/pc | 2,500 – 5,000 tris/pc
**Full Character Armor Set** (9 rigid pieces) | 3,000 – 7,500 tris | 7,500 – 18,000 tris | 20,000 – 40,000 tris
**Modular Level Props** (Barricade, Column, Crate, Brazier) | 300 – 1,200 tris | 1,200 – 3,000 tris | 3,500 – 8,000 tris
**Architecture / Large Buildings** (Insula, Domus, Temple) | 2,500 – 8,000 tris | 8,000 – 25,000 tris | 30,000 – 80,000 tris

---

## 2. Geometry & Topology Rules

1. **Manifold Only**:
   - No non-manifold edges, T-junctions, or open back-faces unless intentionally modeled as a 2-sided sheet.
   - Run `bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)` to merge accidental overlapping vertices.
2. **Face Normals**:
   - All face normals must point outward.
   - Run `bmesh.ops.recalc_face_normals(bm, faces=bm.faces)` before finalizing.
3. **Pivots & Origin Points**:
   - Environment / Floor Props: Base of object (`Z = 0` / lowest vertex).
   - Weapons: Center of hand grip area (where the character's hand wraps around the hilt).
   - Shields: Inner grip handle or forearm strap center.
   - Projectiles: Tip or balance point, oriented facing along `-Z` axis (standard forward direction).
4. **Collision Hulls (UCX)**:
   - For Unreal/Unity/Roblox custom collision, generate simplified convex hulls prefixed with `UCX_<AssetName>`.
   - Complex geometry (e.g. spiral stairs, arched gates) must use multiple convex decomposition shapes rather than one concave mesh.

---

## 3. Scale & Units Reference

Engine | Unit Standard | 1 Blender Unit Equivalent | Up / Forward Axis
:--- | :--- | :--- | :---
**Roblox Studio** | Studs (Metric option: ~0.28m / stud) | 1 Meter = ~3.57 Studs | Up: `+Y`, Forward: `-Z`
**Unity** | Meters | 1 Blender Unit = 1 Meter | Up: `+Y`, Forward: `+Z`
**Unreal Engine** | Centimeters | 1 Blender Unit = 100 cm | Up: `+Z`, Forward: `+X`
**Godot** | Meters | 1 Blender Unit = 1 Meter | Up: `+Y`, Forward: `-Z`
