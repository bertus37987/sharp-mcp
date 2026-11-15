"""heightmap_generator.py

Offline generator for Roblox Studio Terrain Editor heightmap + exact-RGB colormap PNGs.

Roblox Heightmap / Colormap Rules:
- 1 pixel = 4 studs horizontally; max 4096x4096 pixels (.png / .jpg).
- Heightmap brightness scales linearly across the Studio Import selection region's Y size.
- Colormap MUST use hard edges (zero anti-aliasing) and match Roblox's official 23-material RGB key.

Usage:
    python heightmap_generator.py --size 256 --seed 42 --biome alpine --out-dir ./out
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

# Official 23-material Roblox Terrain ColorMap palette (verified from create.roblox.com/docs/parts/terrain)
ROBLOX_COLORMAP_PALETTE: dict[str, tuple[int, int, int]] = {
    "Air": (255, 255, 255),
    "Asphalt": (115, 123, 107),
    "Basalt": (30, 30, 37),
    "Brick": (138, 86, 62),
    "Cobblestone": (132, 123, 90),
    "Concrete": (127, 102, 63),
    "CrackedLava": (232, 156, 74),
    "Glacier": (101, 176, 234),
    "Grass": (106, 127, 63),
    "Ground": (102, 92, 59),
    "Ice": (129, 194, 224),
    "LeafyGrass": (115, 132, 74),
    "Limestone": (206, 173, 148),
    "Mud": (58, 46, 36),
    "Pavement": (148, 148, 140),
    "Rock": (102, 108, 111),
    "Salt": (198, 189, 181),
    "Sand": (143, 126, 95),
    "Sandstone": (137, 90, 71),
    "Slate": (63, 127, 107),
    "Snow": (195, 199, 218),
    "WoodPlanks": (139, 109, 79),
    "Water": (12, 84, 92),
}

BIOME_PROFILES: dict[str, dict[str, str]] = {
    "alpine": {
        "underwater": "Ground",
        "shore": "Sand",
        "low": "Grass",
        "mid": "LeafyGrass",
        "cliff": "Rock",
        "high": "Snow",
        "plateau": "Cobblestone",
    },
    "meadow": {
        "underwater": "Mud",
        "shore": "Sand",
        "low": "Grass",
        "mid": "LeafyGrass",
        "cliff": "Rock",
        "high": "Grass",
        "plateau": "Pavement",
    },
    "desert": {
        "underwater": "Sandstone",
        "shore": "Sand",
        "low": "Sand",
        "mid": "Sandstone",
        "cliff": "Limestone",
        "high": "Rock",
        "plateau": "Sandstone",
    },
    "volcanic": {
        "underwater": "Basalt",
        "shore": "Ground",
        "low": "Basalt",
        "mid": "Slate",
        "cliff": "Basalt",
        "high": "CrackedLava",
        "plateau": "Brick",
    },
    "arctic": {
        "underwater": "Glacier",
        "shore": "Ice",
        "low": "Snow",
        "mid": "Glacier",
        "cliff": "Rock",
        "high": "Snow",
        "plateau": "Ice",
    },
}

MAX_ROBLOX_HEIGHTMAP_PX = 4096
STUDS_PER_PIXEL = 4


def check_dependencies() -> tuple[bool, dict[str, str]]:
    """Gracefully verify whether Pillow (PIL) and numpy are installed."""
    missing: list[str] = []
    versions: dict[str, str] = {}
    for pkg, import_name in (("pillow", "PIL"), ("numpy", "numpy")):
        if importlib.util.find_spec(import_name) is None:
            missing.append(pkg)
        else:
            mod = __import__(import_name)
            versions[import_name] = str(getattr(mod, "__version__", "installed"))
    if missing:
        return False, {
            "error": f"Missing required packages: {', '.join(missing)}. Install via: pip install {' '.join(missing)}",
            **versions,
        }
    return True, versions


def _require_deps() -> tuple[Any, Any]:
    ok, info = check_dependencies()
    if not ok:
        raise RuntimeError(info["error"])
    import numpy as np
    from PIL import Image

    return np, Image


def _smoothstep(t: Any, np: Any) -> Any:
    c = np.clip(t, 0.0, 1.0)
    return c * c * (3.0 - 2.0 * c)


def _value_noise_2d(size: int, freq: float, seed: int, np: Any) -> Any:
    """Fast deterministic bilinear-smoothstep 2D noise grid in [0, 1]."""
    rng = np.random.default_rng(seed)
    grid_n = max(4, int(round(freq)) + 2)
    lattice = rng.random((grid_n, grid_n), dtype=np.float64)

    coords = np.linspace(0.0, grid_n - 1.000001, size, dtype=np.float64)
    gx, gz = np.meshgrid(coords, coords, indexing="xy")
    ix = np.floor(gx).astype(np.int32)
    iz = np.floor(gz).astype(np.int32)
    fx = _smoothstep(gx - ix, np)
    fz = _smoothstep(gz - iz, np)

    v00 = lattice[iz, ix]
    v10 = lattice[iz, ix + 1]
    v01 = lattice[iz + 1, ix]
    v11 = lattice[iz + 1, ix + 1]

    nx0 = v00 + (v10 - v00) * fx
    nx1 = v01 + (v11 - v01) * fx
    return nx0 + (nx1 - nx0) * fz


def synthesize_heightfield(
    size: int,
    seed: int = 42,
    octaves: int = 5,
    ridge_weight: float = 0.42,
    plateau_radius: float = 0.12,
    plateau_height: float = 0.48,
) -> Any:
    """Generate a normalized [0.0, 1.0] heightmap array of shape (size, size)."""
    np, _ = _require_deps()
    if size < 16 or size > MAX_ROBLOX_HEIGHTMAP_PX:
        raise ValueError(f"--size must be between 16 and {MAX_ROBLOX_HEIGHTMAP_PX}; got {size}.")

    fbm = np.zeros((size, size), dtype=np.float64)
    ridge = np.zeros((size, size), dtype=np.float64)
    amp = 1.0
    amp_sum = 0.0
    base_freq = 4.0

    for oct_idx in range(max(1, min(octaves, 8))):
        freq = base_freq * (2.0**oct_idx)
        n = _value_noise_2d(size, freq, seed + oct_idx * 977, np)
        fbm += n * amp
        r = 1.0 - np.abs(n * 2.0 - 1.0)
        ridge += (r * r) * amp
        amp_sum += amp
        amp *= 0.5

    fbm /= max(amp_sum, 1e-6)
    ridge /= max(amp_sum, 1e-6)
    rw = float(max(0.0, min(1.0, ridge_weight)))
    height = fbm * (1.0 - rw) + ridge * rw

    # Gentle island/basin rim falloff only on edges if helpful; keep terrain rich across map
    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy = (size - 1) * 0.5, (size - 1) * 0.5
    dist_norm = np.sqrt(((xx - cx) / max(size, 1)) ** 2 + ((yy - cy) / max(size, 1)) ** 2)

    if plateau_radius > 0.0:
        r0 = float(plateau_radius)
        r1 = r0 + max(0.06, r0 * 0.85)
        t = _smoothstep((dist_norm - r0) / max(r1 - r0, 1e-6), np)
        height = plateau_height + (height - plateau_height) * t

    h_min = float(height.min())
    h_max = float(height.max())
    if h_max - h_min > 1e-6:
        height = (height - h_min) / (h_max - h_min)

    # Re-apply flat spawn plateau exactly after normalization so plateau stays dead level
    if plateau_radius > 0.0:
        r0 = float(plateau_radius)
        r1 = r0 + max(0.06, r0 * 0.85)
        t = _smoothstep((dist_norm - r0) / max(r1 - r0, 1e-6), np)
        height = plateau_height + (height - plateau_height) * t

    return np.clip(height, 0.0, 1.0)


def classify_biome_colormap(
    height: Any,
    biome: str = "alpine",
    water_level: float = 0.32,
    plateau_radius: float = 0.12,
    slope_threshold: float = 0.016,
) -> tuple[Any, dict[str, int]]:
    """Convert normalized heightfield into a hard-edged exact-RGB Roblox Terrain colormap."""
    np, _ = _require_deps()
    key = biome.lower()
    if key not in BIOME_PROFILES:
        raise ValueError(f"Unknown biome '{biome}'. Supported: {', '.join(sorted(BIOME_PROFILES))}")
    profile = BIOME_PROFILES[key]

    size_y, size_x = height.shape
    grad_y, grad_x = np.gradient(height)
    slope = np.sqrt(grad_x * grad_x + grad_y * grad_y)

    # Default land material
    mat_grid = np.full((size_y, size_x), profile["low"], dtype=object)

    # Elevation bands
    mat_grid[height >= water_level + 0.18] = profile["mid"]
    mat_grid[height >= max(water_level + 0.38, 0.72)] = profile["high"]
    mat_grid[slope >= slope_threshold] = profile["cliff"]
    mat_grid[height <= water_level + 0.035] = profile["shore"]
    mat_grid[height < water_level] = profile["underwater"]

    # Stamp clean plaza material on inner spawn plateau when above water
    if plateau_radius > 0.0:
        yy, xx = np.mgrid[0:size_y, 0:size_x]
        cx, cy = (size_x - 1) * 0.5, (size_y - 1) * 0.5
        dist_norm = np.sqrt(((xx - cx) / max(size_x, 1)) ** 2 + ((yy - cy) / max(size_y, 1)) ** 2)
        inner_mask = (dist_norm <= plateau_radius * 0.88) & (height >= water_level)
        mat_grid[inner_mask] = profile["plateau"]

    rgb = np.zeros((size_y, size_x, 3), dtype=np.uint8)
    counts: dict[str, int] = {}
    for mat_name, color_rgb in ROBLOX_COLORMAP_PALETTE.items():
        mask = mat_grid == mat_name
        count = int(mask.sum())
        if count > 0:
            rgb[mask] = color_rgb
            counts[mat_name] = count

    return rgb, counts


def validate_colormap_colors(rgb_array: Any) -> tuple[bool, list[tuple[int, int, int]]]:
    """Verify every pixel in an RGB array belongs strictly to ROBLOX_COLORMAP_PALETTE."""
    np, _ = _require_deps()
    allowed = set(ROBLOX_COLORMAP_PALETTE.values())
    flat = rgb_array.reshape(-1, 3)
    unique_rows = np.unique(flat, axis=0)
    invalid = [tuple(int(c) for c in row) for row in unique_rows if tuple(int(c) for c in row) not in allowed]
    return len(invalid) == 0, invalid


def generate_terrain_maps(
    out_dir: str | Path,
    size: int = 256,
    seed: int = 42,
    biome: str = "alpine",
    water_level: float = 0.32,
    plateau_radius: float = 0.12,
    plateau_height: float = 0.48,
    bit_depth: str = "both",
    world_height_studs: int = 192,
) -> dict[str, Any]:
    """Generate heightmap PNG(s), exact-RGB colormap PNG, and Studio import manifest JSON."""
    np, Image = _require_deps()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    height = synthesize_heightfield(
        size=size,
        seed=seed,
        plateau_radius=plateau_radius,
        plateau_height=plateau_height,
    )
    colormap_rgb, counts = classify_biome_colormap(
        height=height,
        biome=biome,
        water_level=water_level,
        plateau_radius=plateau_radius,
    )
    palette_ok, invalid_colors = validate_colormap_colors(colormap_rgb)
    if not palette_ok:
        raise AssertionError(f"Generated colormap contains non-Roblox RGB values: {invalid_colors[:5]}")

    files_written: dict[str, str] = {}
    if bit_depth in ("both", "16"):
        hm16 = np.round(height * 65535.0).astype(np.uint16)
        p16 = out_path / "heightmap_16bit.png"
        Image.fromarray(hm16).save(p16, format="PNG")
        files_written["heightmap_16bit"] = str(p16)

    if bit_depth in ("both", "8"):
        hm8 = np.round(height * 255.0).astype(np.uint8)
        p8 = out_path / "heightmap_8bit.png"
        Image.fromarray(hm8).save(p8, format="PNG")
        files_written["heightmap_8bit"] = str(p8)

    p_col = out_path / "colormap.png"
    Image.fromarray(colormap_rgb).save(p_col, format="PNG")
    files_written["colormap"] = str(p_col)

    world_xz = size * STUDS_PER_PIXEL
    total_px = size * size
    manifest = {
        "pixel_size": [size, size],
        "studs_per_pixel": STUDS_PER_PIXEL,
        "recommended_studio_import": {
            "size_studs": {"x": world_xz, "y": world_height_studs, "z": world_xz},
            "position_studs": {"x": 0, "y": world_height_studs // 2, "z": 0},
            "sea_level_tool_y_studs": round(water_level * world_height_studs, 2),
            "spawn_plateau_y_studs": round(plateau_height * world_height_studs, 2),
        },
        "biome": biome.lower(),
        "seed": seed,
        "palette_valid": palette_ok,
        "material_coverage": {
            k: {"pixels": v, "percent": round(100.0 * v / total_px, 2)} for k, v in sorted(counts.items())
        },
        "files": files_written,
    }
    p_manifest = out_path / "terrain_import_manifest.json"
    p_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    files_written["manifest"] = str(p_manifest)
    return manifest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Roblox Terrain heightmap + exact-RGB colormap PNGs.")
    parser.add_argument("--size", type=int, default=256, help="Width/height in pixels (16..4096; 1 px = 4 studs).")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic terrain noise seed.")
    parser.add_argument(
        "--biome",
        type=str,
        default="alpine",
        choices=sorted(BIOME_PROFILES.keys()),
        help="Biome material classification profile.",
    )
    parser.add_argument("--water-level", type=float, default=0.32, help="Normalized [0..1] sea level threshold.")
    parser.add_argument("--plateau-radius", type=float, default=0.12, help="Normalized center spawn plateau radius.")
    parser.add_argument("--plateau-height", type=float, default=0.48, help="Normalized [0..1] plateau height.")
    parser.add_argument("--world-height", type=int, default=192, help="Target Studio import Y span in studs.")
    parser.add_argument("--bit-depth", choices=("both", "16", "8"), default="both", help="Heightmap bit depth output.")
    parser.add_argument("--out-dir", type=str, required=True, help="Output directory for generated PNGs + manifest.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ok, info = check_dependencies()
    if not ok:
        print(json.dumps({"ok": False, "error": info["error"]}))
        return 1
    args = _parse_args(argv)
    manifest = generate_terrain_maps(
        out_dir=args.out_dir,
        size=args.size,
        seed=args.seed,
        biome=args.biome,
        water_level=args.water_level,
        plateau_radius=args.plateau_radius,
        plateau_height=args.plateau_height,
        bit_depth=args.bit_depth,
        world_height_studs=args.world_height,
    )
    print(json.dumps({"ok": True, **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
