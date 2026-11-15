"""Roblox 9-slice SliceCenter calculator, AI/Figma PNG cleaner, and spritesheet atlas packer.

Handles:
1. Pure-math conversion between Studio 9-Slice Editor edge offsets and Roblox SliceCenter Rects,
   validation against Roblox's 1024x1024 downscaling limit, and atlas ImageRectOffset/Size UVs.
2. Border flood-fill background removal (eliminating opaque black/solid/navy AI backdrops without
   eating enclosed dark sprite outlines), smooth edge feathering, and 1-2px RGB alpha bleeding
   (preventing black-halo fringes under Roblox bilinear filtering).
3. Automatic tight cropping, symmetrical/corner-aware 9-slice SliceCenter detection, and grid
   spritesheet splitting + <=1024x1024 padded atlas packing.

Pillow (PIL) is required for pixel processing; pure math functions work without Pillow.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path
from typing import Any

ROBLOX_MAX_TEXTURE_DIM: int = 1024

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    HAS_PIL = False


def check_pil_available() -> tuple[bool, str]:
    """Return (available, details) for Pillow dependency diagnostics."""
    if HAS_PIL:
        import PIL

        return True, f"Pillow {getattr(PIL, '__version__', 'unknown')} available."
    return False, "Pillow (PIL) is not installed. Install via: pip install pillow"


def _require_pil() -> None:
    if not HAS_PIL:
        raise RuntimeError(
            "Pillow (PIL) is required for image processing in slice_and_atlas_helper.py. "
            "Install with: pip install pillow"
        )


def compute_slice_center_from_offsets(
    width: int,
    height: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> tuple[int, int, int, int]:
    """Convert Studio 9-Slice Editor inward edge offsets into Roblox SliceCenter (minX, minY, maxX, maxY)."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions must be positive, got ({width}, {height}).")
    min_x = max(0, int(left))
    min_y = max(0, int(top))
    max_x = max(min_x + 1, int(width) - max(0, int(right)))
    max_y = max(min_y + 1, int(height) - max(0, int(bottom)))
    max_x = min(max_x, int(width))
    max_y = min(max_y, int(height))
    return (min_x, min_y, max_x, max_y)


def compute_offsets_from_slice_center(
    width: int,
    height: int,
    slice_center: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Convert Roblox SliceCenter (minX, minY, maxX, maxY) into Studio edge offsets (left, top, right, bottom)."""
    min_x, min_y, max_x, max_y = slice_center
    return (int(min_x), int(min_y), int(width - max_x), int(height - max_y))


def validate_slice_center(
    width: int,
    height: int,
    slice_center: tuple[int, int, int, int],
) -> list[str]:
    """Validate SliceCenter coordinates and Roblox 1024x1024 texture cap."""
    issues: list[str] = []
    min_x, min_y, max_x, max_y = slice_center
    if width <= 0 or height <= 0:
        issues.append(f"Invalid dimensions ({width}x{height}).")
        return issues
    if width > ROBLOX_MAX_TEXTURE_DIM or height > ROBLOX_MAX_TEXTURE_DIM:
        issues.append(
            f"Texture {width}x{height} exceeds {ROBLOX_MAX_TEXTURE_DIM}px; Roblox downscaling will shift SliceCenter."
        )
    if min_x < 0 or min_y < 0 or max_x > width or max_y > height:
        issues.append(
            f"SliceCenter {slice_center} falls outside image bounds (0, 0, {width}, {height})."
        )
    if min_x >= max_x:
        issues.append(f"SliceCenter minX ({min_x}) must be < maxX ({max_x}).")
    if min_y >= max_y:
        issues.append(f"SliceCenter minY ({min_y}) must be < maxY ({max_y}).")
    return issues


def format_slice_center_luau(slice_center: tuple[int, int, int, int]) -> str:
    """Format a 4-tuple as a Roblox Luau Rect.new(...) constructor string."""
    min_x, min_y, max_x, max_y = slice_center
    return f"Rect.new({min_x}, {min_y}, {max_x}, {max_y})"


def compute_atlas_uvs(
    rects: dict[str, tuple[int, int, int, int]],
    atlas_size: tuple[int, int],
) -> dict[str, dict[str, Any]]:
    """Compute ImageRectOffset, ImageRectSize, and normalized UVs for sprite rects (x, y, w, h)."""
    aw, ah = atlas_size
    if aw <= 0 or ah <= 0:
        raise ValueError(f"Atlas size must be positive, got {atlas_size}.")
    if aw > ROBLOX_MAX_TEXTURE_DIM or ah > ROBLOX_MAX_TEXTURE_DIM:
        raise ValueError(
            f"Atlas size {aw}x{ah} exceeds Roblox's {ROBLOX_MAX_TEXTURE_DIM}x{ROBLOX_MAX_TEXTURE_DIM} cap."
        )

    out: dict[str, dict[str, Any]] = {}
    for name, (x, y, w, h) in rects.items():
        out[name] = {
            "ImageRectOffset": [int(x), int(y)],
            "ImageRectSize": [int(w), int(h)],
            "LuauOffset": f"Vector2.new({int(x)}, {int(y)})",
            "LuauSize": f"Vector2.new({int(w)}, {int(h)})",
            "UV": {
                "u0": round(x / aw, 6),
                "v0": round(y / ah, 6),
                "u1": round((x + w) / aw, 6),
                "v1": round((y + h) / ah, 6),
            },
        }
    return out


def _rgb_dist(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    return math.sqrt(dr * dr + dg * dg + db * db)


def _get_pixels(rgba: "Image.Image") -> list[tuple[int, int, int, int]]:
    getter = getattr(rgba, "get_flattened_data", None)
    if callable(getter):
        return list(getter())
    return list(rgba.getdata())


def _median_border_rgb(pixels: list[tuple[int, int, int, int]], w: int, h: int, margin: int = 3) -> tuple[int, int, int]:
    samples_r: list[int] = []
    samples_g: list[int] = []
    samples_b: list[int] = []
    step = max(1, min(w, h) // 64)
    for x in range(0, w, step):
        for y in range(min(margin, h)):
            r, g, b, a = pixels[y * w + x]
            if a > 0:
                samples_r.append(r)
                samples_g.append(g)
                samples_b.append(b)
        for y in range(max(0, h - margin), h):
            r, g, b, a = pixels[y * w + x]
            if a > 0:
                samples_r.append(r)
                samples_g.append(g)
                samples_b.append(b)
    for y in range(0, h, step):
        for x in range(min(margin, w)):
            r, g, b, a = pixels[y * w + x]
            if a > 0:
                samples_r.append(r)
                samples_g.append(g)
                samples_b.append(b)
        for x in range(max(0, w - margin), w):
            r, g, b, a = pixels[y * w + x]
            if a > 0:
                samples_r.append(r)
                samples_g.append(g)
                samples_b.append(b)
    if not samples_r:
        return (0, 0, 0)
    samples_r.sort()
    samples_g.sort()
    samples_b.sort()
    mid = len(samples_r) // 2
    return (samples_r[mid], samples_g[mid], samples_b[mid])


def remove_border_background(
    img: "Image.Image",
    tolerance: float = 28.0,
    feather: float = 10.0,
    sample_margin: int = 3,
) -> "Image.Image":
    """Key out outer solid/gradient background via border flood-fill, preserving enclosed dark pixels.

    Uses BFS from image perimeter pixels matching the sampled median border color, followed by a
    1-ring anti-aliased alpha feather on foreground edges bordering the keyed background.
    """
    _require_pil()
    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = _get_pixels(rgba)
    bg_rgb = _median_border_rgb(pixels, w, h, margin=sample_margin)

    total = w * h
    visited = bytearray(total)
    is_bg = bytearray(total)
    queue: deque[int] = deque()

    def try_seed(idx: int) -> None:
        if visited[idx]:
            return
        r, g, b, a = pixels[idx]
        if a == 0 or _rgb_dist((r, g, b), bg_rgb) <= tolerance:
            visited[idx] = 1
            is_bg[idx] = 1
            queue.append(idx)

    for x in range(w):
        try_seed(x)
        try_seed((h - 1) * w + x)
    for y in range(1, h - 1):
        try_seed(y * w)
        try_seed(y * w + (w - 1))

    step_limit = max(14.0, tolerance * 0.7)
    max_bg_dist = tolerance * 1.15
    while queue:
        idx = queue.popleft()
        pr, pg, pb, _ = pixels[idx]
        x = idx % w
        y = idx // w

        neighbors = []
        if x > 0:
            neighbors.append(idx - 1)
        if x + 1 < w:
            neighbors.append(idx + 1)
        if y > 0:
            neighbors.append(idx - w)
        if y + 1 < h:
            neighbors.append(idx + w)

        for nidx in neighbors:
            if visited[nidx]:
                continue
            nr, ng, nb, na = pixels[nidx]
            if na == 0:
                visited[nidx] = 1
                is_bg[nidx] = 1
                queue.append(nidx)
                continue
            d_bg = _rgb_dist((nr, ng, nb), bg_rgb)
            d_step = _rgb_dist((nr, ng, nb), (pr, pg, pb))
            if d_bg <= tolerance or (d_bg <= max_bg_dist and d_step <= step_limit):
                visited[nidx] = 1
                is_bg[nidx] = 1
                queue.append(nidx)

    new_pixels = list(pixels)
    for idx in range(total):
        if is_bg[idx]:
            r, g, b, _ = new_pixels[idx]
            new_pixels[idx] = (r, g, b, 0)

    # Soft feather 1px foreground perimeter adjacent to keyed background
    if feather > 0.0:
        for idx in range(total):
            if is_bg[idx]:
                continue
            r, g, b, a = new_pixels[idx]
            if a == 0:
                continue
            x = idx % w
            y = idx // w
            touches_bg = (
                (x > 0 and is_bg[idx - 1])
                or (x + 1 < w and is_bg[idx + 1])
                or (y > 0 and is_bg[idx - w])
                or (y + 1 < h and is_bg[idx + w])
            )
            if touches_bg:
                d = _rgb_dist((r, g, b), bg_rgb)
                if d < tolerance + feather:
                    t = max(0.0, min(1.0, (d - tolerance * 0.75) / max(1.0, feather)))
                    new_pixels[idx] = (r, g, b, int(round(a * t)))

    out = Image.new("RGBA", (w, h))
    out.putdata(new_pixels)
    return out


def alpha_bleed_rgba(img: "Image.Image", iterations: int = 2) -> "Image.Image":
    """Dilate RGB colors outward from opaque pixels into alpha=0 pixels to prevent dark halos."""
    _require_pil()
    rgba = img.convert("RGBA")
    if iterations <= 0:
        return rgba

    w, h = rgba.size
    pixels = _get_pixels(rgba)
    total = w * h

    # Track pixels that currently carry valid RGB (alpha > 0 initially, or dilated in earlier pass)
    has_color = bytearray(1 if pixels[i][3] > 0 else 0 for i in range(total))
    frontier: list[int] = []

    for i in range(total):
        if has_color[i]:
            continue
        x = i % w
        y = i // w
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and has_color[ny * w + nx]:
                frontier.append(i)
                break

    for _ in range(iterations):
        if not frontier:
            break
        updates: list[tuple[int, tuple[int, int, int, int]]] = []
        next_candidates: set[int] = set()
        for idx in frontier:
            if has_color[idx]:
                continue
            x = idx % w
            y = idx // w
            sum_r = sum_g = sum_b = count = 0
            empty_neighbors: list[int] = []
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nidx = ny * w + nx
                    if has_color[nidx]:
                        nr, ng, nb, _ = pixels[nidx]
                        sum_r += nr
                        sum_g += ng
                        sum_b += nb
                        count += 1
                    else:
                        empty_neighbors.append(nidx)
            if count > 0:
                updates.append((idx, (sum_r // count, sum_g // count, sum_b // count, 0)))
                next_candidates.update(empty_neighbors)

        for idx, val in updates:
            pixels[idx] = val
            has_color[idx] = 1
        frontier = list(next_candidates)

    # Zero-out RGB of untouched deep transparent pixels cleanly or leave consistent
    out = Image.new("RGBA", (w, h))
    out.putdata(pixels)
    return out


def crop_to_alpha_bbox(
    img: "Image.Image",
    padding: int = 2,
    alpha_threshold: int = 8,
) -> tuple["Image.Image", tuple[int, int, int, int]]:
    """Trim outer transparent margin down to the foreground bounding box plus optional padding."""
    _require_pil()
    rgba = img.convert("RGBA")
    w, h = rgba.size
    alpha = rgba.getchannel("A")
    mask = alpha.point(lambda p: 255 if p >= alpha_threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return rgba, (0, 0, w, h)

    x0 = max(0, bbox[0] - padding)
    y0 = max(0, bbox[1] - padding)
    x1 = min(w, bbox[2] + padding)
    y1 = min(h, bbox[3] + padding)
    return rgba.crop((x0, y0, x1, y1)), (x0, y0, x1, y1)


def fit_max_dimension(
    img: "Image.Image",
    max_dim: int = ROBLOX_MAX_TEXTURE_DIM,
) -> tuple["Image.Image", float]:
    """Scale image down proportionally if either side exceeds max_dim; returns (image, scale)."""
    _require_pil()
    w, h = img.size
    largest = max(w, h)
    if largest <= max_dim:
        return img, 1.0
    scale = max_dim / float(largest)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return img.resize((nw, nh), Image.Resampling.LANCZOS), scale


def detect_nine_slice_center(
    img: "Image.Image",
    min_border_px: int = 12,
    edge_offsets: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Detect stable stretchable interior SliceCenter (minX, minY, maxX, maxY) for a 9-slice asset.

    Compares every column against the median central column (and every row against the median
    central row) to isolate corner ornaments and rounded endcaps from flat stretchable bands.
    """
    _require_pil()
    rgba = img.convert("RGBA")
    w, h = rgba.size

    if edge_offsets is not None:
        return compute_slice_center_from_offsets(w, h, *edge_offsets)

    pixels = _get_pixels(rgba)

    def pixel_diff(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> float:
        return (
            abs(p1[0] - p2[0])
            + abs(p1[1] - p2[1])
            + abs(p1[2] - p2[2])
            + abs(p1[3] - p2[3]) * 1.5
        ) / 4.0

    # Horizontal stretchable columns: compare column x against middle column w//2
    # Use 95th-percentile difference across sampled rows so ornate corner brackets don't get diluted
    # by a large flat interior!
    mid_x = w // 2
    y_start = max(1, int(h * 0.04))
    y_end = min(h - 1, int(h * 0.96))
    y_samples = list(range(y_start, max(y_start + 1, y_end)))

    col_diffs: list[float] = []
    for x in range(w):
        row_d = sorted(pixel_diff(pixels[y * w + x], pixels[y * w + mid_x]) for y in y_samples)
        p95_idx = min(len(row_d) - 1, int(len(row_d) * 0.95))
        col_diffs.append(row_d[p95_idx])

    # Vertical stretchable rows: compare row y against middle row h//2
    mid_y = h // 2
    x_start = max(1, int(w * 0.04))
    x_end = min(w - 1, int(w * 0.96))
    x_samples = list(range(x_start, max(x_start + 1, x_end)))

    row_diffs: list[float] = []
    for y in range(h):
        col_d = sorted(pixel_diff(pixels[y * w + x], pixels[mid_y * w + x]) for x in x_samples)
        p95_idx = min(len(col_d) - 1, int(len(col_d) * 0.95))
        row_diffs.append(col_d[p95_idx])

    diff_thresh = 12.0

    # Expand outward from mid_x while columns remain consistent with center rail/interior
    min_x = mid_x
    while min_x > min_border_px and col_diffs[min_x - 1] <= diff_thresh:
        min_x -= 1
    max_x = mid_x
    while max_x < w - min_border_px - 1 and col_diffs[max_x + 1] <= diff_thresh:
        max_x += 1

    # Expand outward from mid_y while rows remain consistent with center rail/interior
    min_y = mid_y
    while min_y > min_border_px and row_diffs[min_y - 1] <= diff_thresh:
        min_y -= 1
    max_y = mid_y
    while max_y < h - min_border_px - 1 and row_diffs[max_y + 1] <= diff_thresh:
        max_y += 1

    # Safety clamp: keep a generous stretchable center strip and minimum corner margins
    margin_x_floor = min(max(min_border_px, int(w * 0.08)), max(1, w // 3))
    margin_y_floor = min(max(min_border_px, int(h * 0.08)), max(1, h // 3))

    min_x = max(min_x, margin_x_floor)
    max_x = min(max_x, w - margin_x_floor)
    min_y = max(min_y, margin_y_floor)
    max_y = min(max_y, h - margin_y_floor)

    # If a gradient button has narrow flat vertical center, guarantee a safe central slice band
    if max_x - min_x < 6:
        min_x = max(margin_x_floor, int(w * 0.42))
        max_x = min(w - margin_x_floor, int(w * 0.58))
        if max_x <= min_x:
            min_x, max_x = w // 3, (2 * w) // 3
    if max_y - min_y < 6:
        min_y = max(margin_y_floor, int(h * 0.44))
        max_y = min(h - margin_y_floor, int(h * 0.56))
        if max_y <= min_y:
            min_y, max_y = h // 3, (2 * h) // 3

    return (int(min_x), int(min_y), int(max_x), int(max_y))


def prepare_nine_slice_png(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_dim: int = 512,
    bg_tolerance: float = 28.0,
    feather: float = 10.0,
    bleed_px: int = 2,
    crop_padding: int = 2,
    edge_offsets: tuple[int, int, int, int] | None = None,
    key_background: bool = True,
) -> dict[str, Any]:
    """Full 9-slice pipeline: key background -> tight crop -> <=max_dim -> alpha bleed -> SliceCenter."""
    _require_pil()
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(src).convert("RGBA")
    orig_size = img.size

    if key_background:
        img = remove_border_background(img, tolerance=bg_tolerance, feather=feather)
        img, crop_box = crop_to_alpha_bbox(img, padding=crop_padding)
    else:
        crop_box = (0, 0, orig_size[0], orig_size[1])

    capped_max_dim = max(16, min(int(max_dim), ROBLOX_MAX_TEXTURE_DIM))
    pre_cap_size = img.size
    img, scale = fit_max_dimension(img, max_dim=capped_max_dim)
    downscaled_for_cap = (pre_cap_size[0] > ROBLOX_MAX_TEXTURE_DIM or pre_cap_size[1] > ROBLOX_MAX_TEXTURE_DIM) or scale < 1.0
    img = alpha_bleed_rgba(img, iterations=bleed_px)
    img.save(dst, format="PNG")

    w, h = img.size
    slice_center = detect_nine_slice_center(img, edge_offsets=edge_offsets)
    offsets = compute_offsets_from_slice_center(w, h, slice_center)
    issues = validate_slice_center(w, h, slice_center)

    return {
        "input": str(src),
        "output": str(dst),
        "original_size": list(orig_size),
        "crop_box": list(crop_box),
        "scale_applied": round(scale, 6),
        "downscaled_for_1024_cap": downscaled_for_cap,
        "width": w,
        "height": h,
        "slice_center": list(slice_center),
        "edge_offsets": {
            "left": offsets[0],
            "top": offsets[1],
            "right": offsets[2],
            "bottom": offsets[3],
        },
        "luau_snippet": {
            "ScaleType": "Enum.ScaleType.Slice",
            "SliceCenter": format_slice_center_luau(slice_center),
        },
        "validation_issues": issues,
    }


def _place_sprite_in_cell(
    sprite: "Image.Image",
    cell_size: int,
    inner_margin: int = 6,
) -> "Image.Image":
    w, h = sprite.size
    target = max(1, cell_size - 2 * inner_margin)
    scale = min(target / max(1, w), target / max(1, h))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = sprite.resize((nw, nh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    ox = (cell_size - nw) // 2
    oy = (cell_size - nh) // 2
    canvas.paste(resized, (ox, oy), resized)
    return canvas


def split_grid_and_pack_atlas(
    input_path: str | Path,
    output_path: str | Path,
    rows: int,
    cols: int,
    names: list[str] | None = None,
    *,
    cell_size: int = 256,
    gutter: int = 4,
    bg_tolerance: float = 30.0,
    feather: float = 10.0,
    bleed_px: int = 2,
    max_atlas_dim: int = ROBLOX_MAX_TEXTURE_DIM,
    key_background: bool = True,
    tight_trim: bool = True,
    trim_padding: int = 2,
    auto_fit_cell_size: bool = True,
    skip_empty_cells: bool = False,
) -> dict[str, Any]:
    """Split an arbitrary RxC grid sheet into tightly trimmed, alpha-bled icons in a <=1024x1024 atlas."""
    _require_pil()
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive.")

    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    capped_atlas_dim = min(int(max_atlas_dim), ROBLOX_MAX_TEXTURE_DIM)
    sheet = Image.open(src).convert("RGBA")
    sw, sh = sheet.size
    seam_trim = min(4, max(0, min(sw // cols, sh // rows) // 10))

    count = rows * cols
    if names is not None:
        if skip_empty_cells and len(names) <= count:
            resolved_names: list[str] | None = list(names)
        elif len(names) != count:
            raise ValueError(f"Expected {count} names for {rows}x{cols} grid, got {len(names)}.")
        else:
            resolved_names = list(names)
    else:
        resolved_names = [f"icon_{i}" for i in range(count)]

    effective_cell_size = int(cell_size)
    atlas_w = cols * effective_cell_size + max(0, cols - 1) * gutter + 2 * gutter
    atlas_h = rows * effective_cell_size + max(0, rows - 1) * gutter + 2 * gutter
    if atlas_w > capped_atlas_dim or atlas_h > capped_atlas_dim:
        if not auto_fit_cell_size:
            raise ValueError(
                f"Computed atlas {atlas_w}x{atlas_h} exceeds max_atlas_dim={capped_atlas_dim}. Reduce cell_size."
            )
        max_w_cell = (capped_atlas_dim - (cols + 1) * gutter) // cols
        max_h_cell = (capped_atlas_dim - (rows + 1) * gutter) // rows
        effective_cell_size = min(effective_cell_size, max_w_cell, max_h_cell)
        if effective_cell_size < 8:
            raise ValueError(
                f"Grid {rows}x{cols} with gutter={gutter} cannot fit within {capped_atlas_dim}x{capped_atlas_dim}."
            )
        atlas_w = cols * effective_cell_size + max(0, cols - 1) * gutter + 2 * gutter
        atlas_h = rows * effective_cell_size + max(0, rows - 1) * gutter + 2 * gutter

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    rects: dict[str, tuple[int, int, int, int]] = {}
    trimmed_cells: dict[str, list[int]] = {}

    name_cursor = 0
    for r in range(rows):
        for c in range(cols):
            cell_x0 = int(round(c * sw / cols))
            cell_x1 = int(round((c + 1) * sw / cols))
            cell_y0 = int(round(r * sh / rows))
            cell_y1 = int(round((r + 1) * sh / rows))

            x0 = cell_x0 + (seam_trim if c > 0 else 0)
            y0 = cell_y0 + (seam_trim if r > 0 else 0)
            x1 = max(x0 + 1, cell_x1 - (seam_trim if c + 1 < cols else 0))
            y1 = max(y0 + 1, cell_y1 - (seam_trim if r + 1 < rows else 0))
            tile = sheet.crop((x0, y0, x1, y1))

            if key_background:
                tile = remove_border_background(tile, tolerance=bg_tolerance, feather=feather)

            alpha_extrema = tile.getchannel("A").getextrema()
            is_empty = alpha_extrema[1] < 8
            if skip_empty_cells and is_empty:
                continue

            if tight_trim:
                tile, _ = crop_to_alpha_bbox(tile, padding=trim_padding)

            sprite_name = (
                resolved_names[name_cursor]
                if resolved_names is not None and name_cursor < len(resolved_names)
                else f"icon_{r}_{c}"
            )
            name_cursor += 1
            trimmed_cells[sprite_name] = list(tile.size)

            inner_margin = max(2, min(6, effective_cell_size // 16))
            fitted = _place_sprite_in_cell(tile, cell_size=effective_cell_size, inner_margin=inner_margin)
            fitted = alpha_bleed_rgba(fitted, iterations=bleed_px)

            dest_x = gutter + c * (effective_cell_size + gutter)
            dest_y = gutter + r * (effective_cell_size + gutter)
            atlas.paste(fitted, (dest_x, dest_y), fitted)
            rects[sprite_name] = (dest_x, dest_y, effective_cell_size, effective_cell_size)

    atlas = alpha_bleed_rgba(atlas, iterations=1)
    atlas.save(dst, format="PNG")

    uvs = compute_atlas_uvs(rects, (atlas_w, atlas_h))
    return {
        "input": str(src),
        "output": str(dst),
        "grid": [rows, cols],
        "atlas_size": [atlas_w, atlas_h],
        "cell_size": effective_cell_size,
        "requested_cell_size": int(cell_size),
        "downscaled_for_1024_cap": effective_cell_size < int(cell_size),
        "gutter": gutter,
        "trimmed_cells": trimmed_cells,
        "sprites": uvs,
    }


def pack_icon_atlas(
    icon_paths: dict[str, str | Path],
    output_path: str | Path,
    *,
    cell_size: int = 128,
    gutter: int = 4,
    bleed_px: int = 2,
    max_atlas_dim: int = ROBLOX_MAX_TEXTURE_DIM,
    key_background: bool = False,
    bg_tolerance: float = 28.0,
    feather: float = 10.0,
    auto_fit_cell_size: bool = True,
) -> dict[str, Any]:
    """Pack individual named icon files into a <=1024x1024 PNG spritesheet with gutter & alpha bleed."""
    _require_pil()
    if not icon_paths:
        raise ValueError("icon_paths cannot be empty.")

    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    capped_atlas_dim = min(int(max_atlas_dim), ROBLOX_MAX_TEXTURE_DIM)
    items = list(icon_paths.items())
    effective_cell_size = int(cell_size)
    cols = max(1, min(len(items), (capped_atlas_dim - gutter) // (effective_cell_size + gutter)))
    rows = math.ceil(len(items) / cols)

    atlas_w = cols * effective_cell_size + max(0, cols - 1) * gutter + 2 * gutter
    atlas_h = rows * effective_cell_size + max(0, rows - 1) * gutter + 2 * gutter
    if atlas_w > capped_atlas_dim or atlas_h > capped_atlas_dim:
        if not auto_fit_cell_size:
            raise ValueError(
                f"Atlas {atlas_w}x{atlas_h} exceeds {capped_atlas_dim}x{capped_atlas_dim}. Reduce cell_size or sprite count."
            )
        side = max(1, math.ceil(math.sqrt(len(items))))
        cols = side
        rows = math.ceil(len(items) / cols)
        max_c = (capped_atlas_dim - (max(cols, rows) + 1) * gutter) // max(cols, rows)
        effective_cell_size = min(effective_cell_size, max_c)
        if effective_cell_size < 8:
            raise ValueError(
                f"Cannot pack {len(items)} sprites inside {capped_atlas_dim}x{capped_atlas_dim}."
            )
        atlas_w = cols * effective_cell_size + max(0, cols - 1) * gutter + 2 * gutter
        atlas_h = rows * effective_cell_size + max(0, rows - 1) * gutter + 2 * gutter

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    rects: dict[str, tuple[int, int, int, int]] = {}

    for idx, (name, path_val) in enumerate(items):
        r = idx // cols
        c = idx % cols
        tile = Image.open(Path(path_val)).convert("RGBA")
        if key_background:
            tile = remove_border_background(tile, tolerance=bg_tolerance, feather=feather)
        tile, _ = crop_to_alpha_bbox(tile, padding=2)
        inner_margin = max(2, min(4, effective_cell_size // 16))
        fitted = _place_sprite_in_cell(tile, cell_size=effective_cell_size, inner_margin=inner_margin)
        fitted = alpha_bleed_rgba(fitted, iterations=bleed_px)

        dest_x = gutter + c * (effective_cell_size + gutter)
        dest_y = gutter + r * (effective_cell_size + gutter)
        atlas.paste(fitted, (dest_x, dest_y), fitted)
        rects[name] = (dest_x, dest_y, effective_cell_size, effective_cell_size)

    atlas = alpha_bleed_rgba(atlas, iterations=1)
    atlas.save(dst, format="PNG")
    uvs = compute_atlas_uvs(rects, (atlas_w, atlas_h))
    return {
        "output": str(dst),
        "atlas_size": [atlas_w, atlas_h],
        "cell_size": effective_cell_size,
        "downscaled_for_1024_cap": effective_cell_size < int(cell_size),
        "gutter": gutter,
        "sprites": uvs,
    }


def _parse_offsets(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    parts = [int(x.strip()) for x in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("--offsets must be four comma-separated ints: left,top,right,bottom")
    return (parts[0], parts[1], parts[2], parts[3])


PROMPT_TEMPLATES: dict[str, dict[str, Any]] = {
    "9slice_panel": {
        "description": "Ornate 9-Slice modal/window frame with corner-only brackets and straight middle spans.",
        "recommended_size": [1024, 1024],
        "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice <raw.png> <out_9slice.png> --max-dim 512",
        "template": (
            "Flat 2D orthographic front-facing game UI modal window frame in a {theme} style, 1:1 square aspect ratio. "
            "Symmetrical rectangular frame with {details}. Decorative corner plates, rivets, or bevel accents strictly "
            "confined to the 4 outer corners (outer 22% of width and height). The middle 56% of the top, bottom, left, "
            "and right border edges are completely straight, uniform thickness, and smoothly repeatable for 9-slice scaling. "
            "The interior center area is a flat, uniform dark slate surface (#161B26) with no inner pattern. "
            "Isolated on a {bg_color} background with a 48px empty margin on all sides. Crisp vector-clean edges, "
            "zero perspective tilt, no outer drop shadow, no glow outside frame border, no transparency checkerboard, "
            "strictly no text, no letters, no numbers."
        ),
    },
    "9slice_tint_button": {
        "description": "Neutral white/silver grayscale 9-slice pill/bevel button for ImageColor3 tinting in Roblox.",
        "recommended_size": [1024, 512],
        "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice <raw.png> <out_button_9slice.png> --max-dim 512",
        "template": (
            "Flat 2D orthographic front-facing game UI rectangular pill button in a {theme} style, centered horizontally. "
            "Rendered strictly in neutral white and silver grayscale (#FFFFFF top specular highlight, #E2E8F0 glossy upper body, "
            "#CBD5E1 lower bevel, #64748B crisp outer border outline) with zero color hue saturation so it can be vertex-tinted "
            "via ImageColor3 in Roblox Studio ({details}). Rounded/beveled corner caps confined to the left and right 24% ends; "
            "the middle 52% horizontal span has completely straight, parallel, uniform top and bottom edges for 9-slice stretching. "
            "Isolated on a {bg_color} background with generous empty margin. Zero perspective tilt, no outer drop shadow, "
            "no transparency checkerboard, strictly no text, no icons, blank button face."
        ),
    },
    "icon_grid_2x2": {
        "description": "2x2 quadrant grid of 4 isolated game UI icons for split-atlas packing.",
        "recommended_size": [1024, 1024],
        "post_process_cmd": 'python slice_and_atlas_helper.py split-atlas <raw.png> <out_atlas.png> --rows 2 --cols 2 --names "coin,gem,sword,chest" --cell-size 256 --gutter 4',
        "template": (
            "Flat 2D orthographic game UI icon sheet arranged in a strict 2x2 quadrant grid (4 distinct icons total) in a {theme} style: "
            "{details}. Each icon is centered inside its quadrant with generous empty padding around it, bold dark-slate outer contour "
            "silhouette, vibrant stylized cel-shaded gradients, and crisp specular highlights. Isolated on a {bg_color} background "
            "across the entire canvas. Strictly NO grid dividing lines, NO boxes or frames around the icons, no outer drop shadows "
            "or glowing halos bleeding into the background, no transparency checkerboard, strictly no text, no numbers."
        ),
    },
    "icon_grid_3x3": {
        "description": "3x3 grid of 9 isolated game UI icons for split-atlas packing.",
        "recommended_size": [1024, 1024],
        "post_process_cmd": "python slice_and_atlas_helper.py split-atlas <raw.png> <out_atlas.png> --rows 3 --cols 3 --cell-size 256 --gutter 4",
        "template": (
            "Flat 2D orthographic game UI icon sheet arranged in a strict 3x3 grid (9 distinct icons total, 3 rows by 3 columns) "
            "in a {theme} style: {details}. Each icon is centered inside its cell with wide uniform {bg_color} background spacing, "
            "bold crisp outer silhouette, consistent top-left lighting, NO grid dividing lines, NO frames, no outer glow, "
            "no transparency checkerboard, strictly no text or numbers."
        ),
    },
    "hud_bar": {
        "description": "Horizontal 9-slice HUD health/XP bar trough and end-caps.",
        "recommended_size": [1024, 256],
        "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice <raw.png> <out_hud_bar.png> --max-dim 512",
        "template": (
            "Flat 2D orthographic horizontal game UI status bar frame in a {theme} style ({details}). Wide horizontal capsule/beveled "
            "trough with decorative end-caps on the far left and far right 18% ends, and a completely straight, uniform horizontal "
            "middle 64% span for 9-slice stretching. Dark recessed inner track (#111622) with stylized outer rim. Isolated on a "
            "{bg_color} background with wide margin, zero perspective, no outer shadow, no text, no numbers."
        ),
    },
    "rarity_frame": {
        "description": "Square 1:1 tintable inventory item slot frame for Common/Rare/Epic/Legendary/Mythic.",
        "recommended_size": [512, 512],
        "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice <raw.png> <out_slot_9slice.png> --max-dim 256",
        "template": (
            "Flat 2D orthographic square 1:1 game UI inventory item slot frame in a {theme} style ({details}), neutral silver/white "
            "grayscale metallic border with ornamental corner notches and straight uniform middle edges, recessed dark center (#182030), "
            "designed for 9-slice scaling and ImageColor3 rarity tinting. Isolated on a {bg_color} background with 40px outer margin, "
            "no outer glow, no text, empty center."
        ),
    },
    "tile_pattern": {
        "description": "Seamless repeating 2D UI background pattern for ScaleType = Tile.",
        "recommended_size": [512, 512],
        "post_process_cmd": "Use directly with ImageLabel.ScaleType = Enum.ScaleType.Tile and TileSize = UDim2.fromOffset(128, 128)",
        "template": (
            "Seamless 2D tileable repeating game UI background pattern in a {theme} style ({details}). Full-bleed edge-to-edge subtle "
            "low-contrast motif in monochrome dark slate tones (#141A26 to #1E2738) so foreground UI text remains 100% legible. "
            "Strictly seamless horizontal and vertical wrap-around edges, flat orthographic 2D texture, no vignette, no text."
        ),
    },
    "loading_backdrop": {
        "description": "16:9 atmospheric game loading splash backdrop with dark calm center for legible overlay UI.",
        "recommended_size": [1024, 576],
        "post_process_cmd": "Import as ImageLabel background under LoadingTransitionTemplate (ScaleType = Crop)",
        "template": (
            "Stylized 16:9 game UI loading screen backdrop illustration in a {theme} style ({details}). "
            "Atmospheric rim-lit silhouette composition with calm low-detail dark central 45% area for foreground text legibility. "
            "No baked text, no logos, no HUD boxes, no fake transparency checkerboard."
        ),
    },
}


def generate_ui_image_prompt(
    template_kind: str = "9slice_panel",
    theme: str = "stylized dark fantasy RPG",
    details: str = "",
    bg_color: str = "single flat uniform solid dark navy (#0B0E17)",
    palette_hexes: list[str] | None = None,
    style_signature: str = "",
) -> dict[str, Any]:
    """Build a Roblox-ready AI image generator prompt and post-processing recipe."""
    if template_kind not in PROMPT_TEMPLATES:
        raise ValueError(
            f"Unknown template_kind '{template_kind}'. Valid: {sorted(PROMPT_TEMPLATES.keys())}"
        )
    spec = PROMPT_TEMPLATES[template_kind]
    default_details = {
        "9slice_panel": "handcrafted dark iron bevels and brushed bronze corner brackets with diamond rivets",
        "9slice_tint_button": "smooth chamfered metallic pill bevels",
        "icon_grid_2x2": "Top-Left: golden embossed coin, Top-Right: cyan mana crystal, Bottom-Left: crossed steel broadswords, Bottom-Right: ornate treasure chest",
        "icon_grid_3x3": "Row 1: gold coin, cyan gem, potion flask; Row 2: broadsword, shield, bow; Row 3: treasure chest, key, crown",
        "hud_bar": "chamfered steel end-caps and sleek recessed track",
        "rarity_frame": "clean beveled corner clasps",
        "tile_pattern": "subtle geometric diamond filigree",
        "loading_backdrop": "layered twilight horizon silhouettes and luminous focal rim-light beams",
    }
    resolved_details = details.strip() or default_details.get(template_kind, "clean stylized bevels")
    resolved_theme = style_signature.strip() or theme
    prompt_text = spec["template"].format(
        theme=resolved_theme,
        details=resolved_details,
        bg_color=bg_color,
    )
    if palette_hexes:
        hex_str = ", ".join(str(h) for h in palette_hexes)
        prompt_text = f"{prompt_text} Exact color palette lock: {hex_str}."
    return {
        "template_kind": template_kind,
        "theme": resolved_theme,
        "details": resolved_details,
        "bg_color": bg_color,
        "palette_hexes": list(palette_hexes or []),
        "prompt": prompt_text,
        "negative_prompt": (
            "muddy gradients, desaturated muddy colors, generic default blue flat UI, "
            "text, letters, numbers, watermark, signature, perspective tilt, 3D angle, isometric, "
            "drop shadow bleeding into background, fake transparency checkerboard, grid divider lines, blurry edges"
        ),
        "recommended_size": spec["recommended_size"],
        "post_process_cmd": spec["post_process_cmd"],
        "description": spec["description"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Roblox 9-slice SliceCenter calculator, image cleaner, atlas packer, and AI prompt builder."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prompt = sub.add_parser("prompt-template", help="Generate a Roblox-ready AI image generator prompt.")
    p_prompt.add_argument(
        "--kind",
        type=str,
        default="9slice_panel",
        choices=sorted(PROMPT_TEMPLATES.keys()),
    )
    p_prompt.add_argument("--theme", type=str, default="stylized dark fantasy RPG")
    p_prompt.add_argument("--details", type=str, default="")
    p_prompt.add_argument("--bg-color", type=str, default="single flat uniform solid dark navy (#0B0E17)")

    p_calc = sub.add_parser("calc-slice", help="Convert Studio edge offsets (L,T,R,B) to SliceCenter.")
    p_calc.add_argument("--width", type=int, required=True)
    p_calc.add_argument("--height", type=int, required=True)
    p_calc.add_argument("--left", type=int, required=True)
    p_calc.add_argument("--top", type=int, required=True)
    p_calc.add_argument("--right", type=int, required=True)
    p_calc.add_argument("--bottom", type=int, required=True)

    p_9 = sub.add_parser("prepare-9slice", help="Key background, crop, alpha-bleed, and compute SliceCenter.")
    p_9.add_argument("input", type=Path)
    p_9.add_argument("output", type=Path)
    p_9.add_argument("--max-dim", type=int, default=512)
    p_9.add_argument("--tolerance", type=float, default=28.0)
    p_9.add_argument("--feather", type=float, default=10.0)
    p_9.add_argument("--bleed", type=int, default=2)
    p_9.add_argument("--offsets", type=str, default=None, help="Optional L,T,R,B override after crop/resize.")
    p_9.add_argument("--no-key", action="store_true", help="Skip background keying (input already RGBA).")

    p_split = sub.add_parser("split-atlas", help="Split RxC grid sheet, key background, alpha-bleed, and pack.")
    p_split.add_argument("input", type=Path)
    p_split.add_argument("output", type=Path)
    p_split.add_argument("--rows", type=int, required=True)
    p_split.add_argument("--cols", type=int, required=True)
    p_split.add_argument("--names", type=str, default=None, help="Comma-separated sprite names.")
    p_split.add_argument("--cell-size", type=int, default=256)
    p_split.add_argument("--gutter", type=int, default=4)
    p_split.add_argument("--tolerance", type=float, default=30.0)
    p_split.add_argument("--feather", type=float, default=10.0)
    p_split.add_argument("--bleed", type=int, default=2)
    p_split.add_argument("--no-key", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "prompt-template":
        res = generate_ui_image_prompt(
            template_kind=args.kind,
            theme=args.theme,
            details=args.details,
            bg_color=args.bg_color,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "calc-slice":
        sc = compute_slice_center_from_offsets(
            args.width, args.height, args.left, args.top, args.right, args.bottom
        )
        issues = validate_slice_center(args.width, args.height, sc)
        print(
            json.dumps(
                {
                    "slice_center": list(sc),
                    "luau": format_slice_center_luau(sc),
                    "issues": issues,
                },
                indent=2,
            )
        )
        return 1 if issues else 0

    if args.cmd == "prepare-9slice":
        res = prepare_nine_slice_png(
            args.input,
            args.output,
            max_dim=args.max_dim,
            bg_tolerance=args.tolerance,
            feather=args.feather,
            bleed_px=args.bleed,
            edge_offsets=_parse_offsets(args.offsets),
            key_background=not args.no_key,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "split-atlas":
        names = [n.strip() for n in args.names.split(",")] if args.names else None
        res = split_grid_and_pack_atlas(
            args.input,
            args.output,
            args.rows,
            args.cols,
            names=names,
            cell_size=args.cell_size,
            gutter=args.gutter,
            bg_tolerance=args.tolerance,
            feather=args.feather,
            bleed_px=args.bleed,
            key_background=not args.no_key,
        )
        print(json.dumps(res, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
