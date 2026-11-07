#!/usr/bin/env python3
"""
rig_animator.py — Cutout Rig Pixel Art Animation Engine for Antigravity (game-art).

Pipeline:
  1. Decomposes a single base sprite (from _spec.json, PNG, or inline ASCII) into
     overlap-padded anatomical parts while stripping outer silhouette outlines and
     preserving interior details (eyes, nostrils, armor seams).
  2. Pre-upscales each part 4x via two passes of EPX (Eric's Pixel Expansion / Scale2x).
  3. Transforms parts per keyframe using hierarchical pivots, Squash & Stretch,
     RotSprite inverse sampling, sprite-swap variants, and procedural FX primitives
     (ellipses, lines/whips, slash arcs, pixel particles).
  4. Re-wraps the posed composite in a crisp 1px outline using Luminance-Normalized
     Hue-Matched Selective Outlining (Sel-Out) so outlines match local material hues
     (e.g. dark forest green around green skin, burgundy around pink tongue) instead
     of collapsing to harsh pure black—or solid ink / lineless when configured.
  5. Exports 1x animation strips, combined multi-row spritesheets (with optional
     horizontal mirroring for isometric SE/NE diagonals), visual QA sheets (--diag),
     and a compact interactive HTML evaluator widget (--html).
"""

import argparse
import json
import math
import os
import struct
import sys
import zlib
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import png_to_spec as pts

AUTO_SYM_POOL = "!$@^&_~`[]{};:,<>|\\"


def write_png(path, width, height, rgba_rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    raw_data = bytearray()
    for row in rgba_rows:
        raw_data.append(0)
        for r, g, b, a in row:
            raw_data.extend((r, g, b, a))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw_data), 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)


def parse_color(val):
    if isinstance(val, (list, tuple)):
        if len(val) == 4:
            return (int(val[0]), int(val[1]), int(val[2]), int(val[3]))
        if len(val) == 3:
            return (int(val[0]), int(val[1]), int(val[2]), 255)
    if isinstance(val, str):
        s = val.strip()
        if s.lower() == "transparent":
            return (0, 0, 0, 0)
        s = s.lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        if len(s) == 8:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    raise ValueError(f"Invalid color value: {val!r}")


def blend(bg, fg):
    fa = fg[3] / 255.0
    if fa <= 0:
        return bg
    if fa >= 1:
        return (fg[0], fg[1], fg[2], 255)
    return (
        int(bg[0] * (1 - fa) + fg[0] * fa),
        int(bg[1] * (1 - fa) + fg[1] * fa),
        int(bg[2] * (1 - fa) + fg[2] * fa),
        255,
    )


def lum_rgb(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def chroma_rgb(r, g, b):
    return max(r, g, b) - min(r, g, b)


# ---------------------------------------------------------------------------
# Geometry & EPX / RotSprite Core
# ---------------------------------------------------------------------------
def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    px, py = x + 0.5, y + 0.5
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def epx_2x(grid):
    h, w = len(grid), len(grid[0])
    out = [["." for _ in range(w * 2)] for _ in range(h * 2)]
    for y in range(h):
        for x in range(w):
            p = grid[y][x]
            a = grid[y - 1][x] if y > 0 else "."
            b = grid[y][x + 1] if x + 1 < w else "."
            c = grid[y][x - 1] if x > 0 else "."
            d = grid[y + 1][x] if y + 1 < h else "."
            p1 = p2 = p3 = p4 = p
            if c == a and c != d and a != b:
                p1 = a
            if a == b and a != c and b != d:
                p2 = b
            if d == c and d != b and c != a:
                p3 = c
            if b == d and b != a and d != c:
                p4 = d
            out[y * 2][x * 2] = p1
            out[y * 2][x * 2 + 1] = p2
            out[y * 2 + 1][x * 2] = p3
            out[y * 2 + 1][x * 2 + 1] = p4
    return out


def epx_4x(grid):
    return epx_2x(epx_2x(grid))


def blit_rotsprite(canvas, part_canvas, grid_4x, pivot_base, base_offset, dx, dy, angle_deg, sx, sy, tag_code):
    cw, ch_h = len(canvas[0]), len(canvas)
    uh, uw = len(grid_4x), len(grid_4x[0])
    ox, oy = base_offset
    px_src, py_src = pivot_base
    px_dst = ox + px_src + dx
    py_dst = oy + py_src + dy

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    sx = max(0.2, float(sx))
    sy = max(0.2, float(sy))

    for cy in range(ch_h):
        for cx in range(cw):
            hits = []
            for sub_y in (-0.25, 0.25):
                for sub_x in (-0.25, 0.25):
                    rx = (cx + sub_x) - px_dst
                    ry = (cy + sub_y) - py_dst
                    ux = (rx * cos_a + ry * sin_a) / sx + px_src
                    uy = (-rx * sin_a + ry * cos_a) / sy + py_src
                    ix = int(round(ux * 4.0))
                    iy = int(round(uy * 4.0))
                    if 0 <= ix < uw and 0 <= iy < uh:
                        v = grid_4x[iy][ix]
                        if v != ".":
                            hits.append(v)
            if len(hits) >= 2:
                val = Counter(hits).most_common(1)[0][0]
                canvas[cy][cx] = val
                part_canvas[cy][cx] = tag_code


# ---------------------------------------------------------------------------
# Auto-Synthesize Hue-Matched Sel-Out Swatches & Outline Engine
# ---------------------------------------------------------------------------
def synthesize_selout_swatches(palette, ignore_syms, existing_candidates, outline_cfg):
    """
    For 'selout_auto': ensures that every distinct chromatic hue family in the
    palette has a matching dark colored outline swatch (~lum 52) and bottom contact
    swatch (~lum 26) so outlines never collapse to pure black!
    """
    candidates = list(existing_candidates)
    used_syms = set(palette.keys()) | {"."}
    sym_iter = (ch for ch in AUTO_SYM_POOL if ch not in used_syms)

    side_lum = float(outline_cfg.get("side_lum", 54.0))
    bot_lum = float(outline_cfg.get("bottom_lum", 26.0))

    # Gather existing dark colors (lum < 95, opaque) as natural candidates if none specified
    if not candidates:
        for sym, rgba in palette.items():
            if sym in ignore_syms or rgba[3] < 220:
                continue
            if lum_rgb(rgba[0], rgba[1], rgba[2]) < 95:
                candidates.append(sym)

    # Check every body color to see if at least one candidate has close hue-darkened match
    body_colors = [
        (sym, rgba)
        for sym, rgba in palette.items()
        if sym not in ignore_syms and rgba[3] >= 220 and lum_rgb(rgba[0], rgba[1], rgba[2]) >= 65
    ]

    for target_l in (side_lum, bot_lum):
        for _, (r, g, b, _) in body_colors:
            lum = max(1.0, lum_rgb(r, g, b))
            # Slightly boost saturation before darkening so outlines look rich, not muddy gray
            avg = (r + g + b) / 3.0
            sr = max(0.0, min(255.0, avg + (r - avg) * 1.25))
            sg = max(0.0, min(255.0, avg + (g - avg) * 1.25))
            sb = max(0.0, min(255.0, avg + (b - avg) * 1.25))
            slum = max(1.0, lum_rgb(sr, sg, sb))
            scale = target_l / slum
            tr = int(round(max(0.0, min(255.0, sr * scale))))
            tg = int(round(max(0.0, min(255.0, sg * scale))))
            tb = int(round(max(0.0, min(255.0, sb * scale))))

            # Check perceptual distance to nearest existing candidate
            best_d = 1e18
            for csym in candidates:
                cr, cg, cb, _ = palette[csym]
                d = math.sqrt(2.0 * (cr - tr) ** 2 + 4.0 * (cg - tg) ** 2 + 3.0 * (cb - tb) ** 2)
                if d < best_d:
                    best_d = d

            # Synthesize a new dark colored outline swatch if no close match exists
            if best_d > 48.0:
                try:
                    nsym = next(sym_iter)
                    palette[nsym] = (tr, tg, tb, 255)
                    candidates.append(nsym)
                except StopIteration:
                    break

    return candidates


def apply_outline(canvas, palette, outline_cfg, ignore_syms, ground_y):
    mode = outline_cfg.get("mode", "selout_auto").lower()
    if mode == "none":
        return [row[:] for row in canvas], set()

    h, w = len(canvas), len(canvas[0])
    out = [row[:] for row in canvas]

    if mode == "solid":
        solid_sym = outline_cfg.get("symbol", "O")
        if solid_sym not in palette:
            palette[solid_sym] = (20, 20, 24, 255)
        for y in range(h):
            for x in range(w):
                if canvas[y][x] != ".":
                    continue
                if (
                    (y > 0 and canvas[y - 1][x] not in ignore_syms)
                    or (y + 1 < h and canvas[y + 1][x] not in ignore_syms)
                    or (x > 0 and canvas[y][x - 1] not in ignore_syms)
                    or (x + 1 < w and canvas[y][x + 1] not in ignore_syms)
                ):
                    out[y][x] = solid_sym
        return out, {solid_sym}

    # Luminance-Normalized Hue-Matched Sel-Out ('selout_auto' or 'selout_palette')
    raw_cands = outline_cfg.get("candidates", [])
    if mode == "selout_auto":
        candidates = synthesize_selout_swatches(palette, ignore_syms, raw_cands, outline_cfg)
    else:
        candidates = list(raw_cands) if raw_cands else [
            s for s, c in palette.items() if s not in ignore_syms and c[3] >= 220 and lum_rgb(c[0], c[1], c[2]) < 110
        ]
    if not candidates:
        candidates = [next(iter(palette.keys()))]

    top_lit_only = set(outline_cfg.get("top_lit_symbols", []))
    neutral_bias = outline_cfg.get("neutral_bias_rgb")  # Optional [r, g, b] tint for low-chroma cream/white parts
    top_lum = float(outline_cfg.get("top_lum", 70.0))
    side_lum = float(outline_cfg.get("side_lum", 54.0))
    bot_lum = float(outline_cfg.get("bottom_lum", 26.0))

    used_outline_syms = set()
    for y in range(h):
        for x in range(w):
            if canvas[y][x] != ".":
                continue
            neighbors = []
            if y > 0 and canvas[y - 1][x] not in ignore_syms:
                neighbors.append(("N", canvas[y - 1][x]))
            if y + 1 < h and canvas[y + 1][x] not in ignore_syms:
                neighbors.append(("S", canvas[y + 1][x]))
            if x > 0 and canvas[y][x - 1] not in ignore_syms:
                neighbors.append(("W", canvas[y][x - 1]))
            if x + 1 < w and canvas[y][x + 1] not in ignore_syms:
                neighbors.append(("E", canvas[y][x + 1]))
            if not neighbors:
                continue

            dirs = {d for d, _ in neighbors}
            nr = sum(palette[c][0] for _, c in neighbors) / len(neighbors)
            ng = sum(palette[c][1] for _, c in neighbors) / len(neighbors)
            nb = sum(palette[c][2] for _, c in neighbors) / len(neighbors)

            if neutral_bias and chroma_rgb(nr, ng, nb) < 65 and lum_rgb(nr, ng, nb) > 150:
                nr, ng, nb = float(neutral_bias[0]), float(neutral_bias[1]), float(neutral_bias[2])

            lum = max(1.0, lum_rgb(nr, ng, nb))
            is_top_lit = ("S" in dirs or "E" in dirs) and ("N" not in dirs) and (lum > 165)
            is_flat_bottom = (
                ("N" in dirs)
                and ("S" not in dirs)
                and ("E" not in dirs)
                and ("W" not in dirs)
                and (y >= ground_y - 4)
            )

            target_lum = bot_lum if is_flat_bottom else (top_lum if is_top_lit else side_lum)
            avg = (nr + ng + nb) / 3.0
            sr = max(0.0, min(255.0, avg + (nr - avg) * 1.15))
            sg = max(0.0, min(255.0, avg + (ng - avg) * 1.15))
            sb = max(0.0, min(255.0, avg + (nb - avg) * 1.15))
            slum = max(1.0, lum_rgb(sr, sg, sb))
            scale = target_lum / slum
            tr, tg, tb = min(255.0, sr * scale), min(255.0, sg * scale), min(255.0, sb * scale)

            best_sym = candidates[0]
            best_dist = 1e18
            for sym in candidates:
                if sym in top_lit_only and not is_top_lit:
                    continue
                cr, cg, cb, _ = palette[sym]
                d = 2.0 * (cr - tr) ** 2 + 4.0 * (cg - tg) ** 2 + 3.0 * (cb - tb) ** 2
                if d < best_dist:
                    best_dist = d
                    best_sym = sym
            out[y][x] = best_sym
            used_outline_syms.add(best_sym)

    return out, used_outline_syms


# ---------------------------------------------------------------------------
# Part Extraction & Procedural FX Primitives
# ---------------------------------------------------------------------------
def strip_outer_silhouette(base_rows, strip_syms, empty_syms):
    h, w = len(base_rows), len(base_rows[0])
    clean = [["." for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            ch = base_rows[y][x]
            if ch in empty_syms:
                continue
            if ch in strip_syms:
                touches_outside = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if nx < 0 or nx >= w or ny < 0 or ny >= h or base_rows[ny][nx] in empty_syms:
                            touches_outside = True
                            break
                    if touches_outside:
                        break
                if touches_outside:
                    continue
            clean[y][x] = ch
    return clean


def build_part_grids(part_def, clean_fill, bw, bh):
    """Returns dict of variant_name -> 4x upscaled grid (with 'default' always present)."""
    grid = [["." for _ in range(bw)] for _ in range(bh)]

    if "matrix" in part_def:
        ox, oy = part_def.get("offset", [0, 0])
        for ry, row in enumerate(part_def["matrix"]):
            for rx, ch in enumerate(row):
                if ch != "." and 0 <= ox + rx < bw and 0 <= oy + ry < bh:
                    grid[oy + ry][ox + rx] = ch
    elif "region" in part_def:
        reg = part_def["region"]
        bbox = reg.get("bbox", [0, 0, bw - 1, bh - 1])
        excl_boxes = reg.get("exclude_bboxes", [])
        poly = reg.get("polygon")
        inc_syms = set(reg["include_symbols"]) if "include_symbols" in reg else None
        exc_syms = set(reg.get("exclude_symbols", []))

        for y in range(max(0, bbox[1]), min(bh, bbox[3] + 1)):
            for x in range(max(0, bbox[0]), min(bw, bbox[2] + 1)):
                ch = clean_fill[y][x]
                if ch == ".":
                    continue
                if inc_syms is not None and ch not in inc_syms:
                    continue
                if ch in exc_syms:
                    continue
                if any(ex0 <= x <= ex1 and ey0 <= y <= ey1 for ex0, ey0, ex1, ey1 in excl_boxes):
                    continue
                if poly and not point_in_poly(x, y, poly):
                    continue
                grid[y][x] = ch

    for px, py, pch in part_def.get("extra_pixels", []):
        if 0 <= px < bw and 0 <= py < bh:
            grid[py][px] = pch

    variants_4x = {"default": epx_4x(grid)}
    for vname, vdef in part_def.get("variants", {}).items():
        vg = [["." for _ in range(bw)] for _ in range(bh)]
        vox, voy = vdef.get("offset", [0, 0])
        for ry, row in enumerate(vdef["matrix"]):
            for rx, ch in enumerate(row):
                if ch != "." and 0 <= vox + rx < bw and 0 <= voy + ry < bh:
                    vg[voy + ry][vox + rx] = ch
        variants_4x[vname] = epx_4x(vg)

    return variants_4x


def apply_fx_primitive(canvas, part_canvas, fx, tag_code="9"):
    h, w = len(canvas), len(canvas[0])
    ftype = fx.get("type")
    only_empty = fx.get("only_empty", False)

    if ftype == "ellipse":
        cx, cy = float(fx["cx"]), float(fx["cy"])
        rx, ry = max(0.5, float(fx["rx"])), max(0.5, float(fx["ry"]))
        top_s = fx["symbol"] if "symbol" in fx else fx["top_symbol"]
        bot_s = fx.get("bottom_symbol", top_s)
        for y in range(int(cy - ry - 1), int(cy + ry + 2)):
            for x in range(int(cx - rx - 1), int(cx + rx + 2)):
                if 0 <= x < w and 0 <= y < h:
                    if only_empty and canvas[y][x] != ".":
                        continue
                    if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                        canvas[y][x] = top_s if y <= cy + 0.3 else bot_s
                        if part_canvas is not None:
                            part_canvas[y][x] = tag_code

    elif ftype == "line":
        x0, y0 = float(fx["x0"]), float(fx["y0"])
        x1, y1 = float(fx["x1"]), float(fx["y1"])
        radius = float(fx.get("radius", 1.1))
        top_s = fx.get("top_symbol", fx.get("symbol", "T"))
        bot_s = fx.get("bottom_symbol", top_s)
        steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0)) * 2))
        for i in range(steps + 1):
            t = i / steps
            cx = x0 + (x1 - x0) * t
            cy = y0 + (y1 - y0) * t
            for py in range(int(cy - radius - 1), int(cy + radius + 2)):
                for px in range(int(cx - radius - 1), int(cx + radius + 2)):
                    if 0 <= px < w and 0 <= py < h:
                        if (px - cx) ** 2 + (py - cy) ** 2 <= radius ** 2:
                            canvas[py][px] = top_s if py <= cy else bot_s
                            if part_canvas is not None:
                                part_canvas[py][px] = tag_code
        if fx.get("tip_radius", 0) > 0:
            tr = int(round(float(fx["tip_radius"])))
            tx, ty = int(round(x1)), int(round(y1))
            hi_s = fx.get("tip_highlight", top_s)
            for dy in range(-tr, tr + 1):
                for dx in range(-tr, tr + 1):
                    px, py = tx + dx, ty + dy
                    if 0 <= px < w and 0 <= py < h:
                        canvas[py][px] = hi_s if (dx <= 0 and dy <= 0) else (top_s if dy <= 0 else bot_s)
                        if part_canvas is not None:
                            part_canvas[py][px] = tag_code

    elif ftype == "arc":
        cx, cy = float(fx["cx"]), float(fx["cy"])
        r_in, r_out = float(fx["r_inner"]), float(fx["r_outer"])
        a0, a1 = float(fx["deg_start"]), float(fx["deg_end"])
        sym = fx["symbol"]
        for y in range(int(cy - r_out - 1), int(cy + r_out + 2)):
            for x in range(int(cx - r_out - 1), int(cx + r_out + 2)):
                if 0 <= x < w and 0 <= y < h:
                    if only_empty and canvas[y][x] != ".":
                        continue
                    dist = math.hypot(x - cx, y - cy)
                    if r_in <= dist <= r_out:
                        ang = math.degrees(math.atan2(y - cy, x - cx))
                        # Normalize angle into [a0, a0+360)
                        rel = (ang - a0) % 360.0
                        span = (a1 - a0) % 360.0 or 360.0
                        if rel <= span:
                            canvas[y][x] = sym
                            if part_canvas is not None:
                                part_canvas[y][x] = tag_code

    elif ftype == "pixels":
        for pt in fx.get("points", []):
            px, py, sym = int(pt[0]), int(pt[1]), pt[2]
            if 0 <= px < w and 0 <= py < h:
                if not only_empty or canvas[py][px] in (".", "s"):
                    canvas[py][px] = sym


def draw_ground_shadow(canvas, cx, cy, rx, ry, sym):
    h, w = len(canvas), len(canvas[0])
    rx = max(1.0, rx)
    ry = max(1.0, ry)
    for y in range(h):
        for x in range(w):
            if canvas[y][x] == ".":
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    canvas[y][x] = sym


# ---------------------------------------------------------------------------
# Interactive HTML Evaluator Builder (Antigravity Generative UI Compliant)
# ---------------------------------------------------------------------------
TINT_CYCLE = [
    [56, 189, 248],
    [34, 197, 94],
    [251, 191, 36],
    [96, 165, 250],
    [251, 146, 60],
    [163, 230, 53],
    [168, 85, 247],
    [244, 63, 94],
]


def build_html_evaluator(path, title, cw, ch, is_iso, palette, part_meta, anim_results, outline_syms):
    scale = max(2, min(8, 192 // max(cw, ch)))
    disp_w, disp_h = cw * scale, ch * scale

    bundle = {
        "palette": {k: list(v) for k, v in palette.items() if k != "."},
        "parts_meta": part_meta,
        "outline_syms": sorted(list(outline_syms)),
        "anims": anim_results,
    }
    json_str = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    iso_default = "true" if is_iso else "false"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>{title} · Cutout Rig ({cw}×{ch})</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    .pixelated {{ image-rendering: pixelated; image-rendering: crisp-edges; }}
  </style>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3 select-none">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="text-[var(--foreground)] font-semibold text-base">{title} · Cutout Rig ({cw}×{ch})</h2>
        <span class="px-2 py-0.5 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs font-medium">
          EPX 4× + Sel-Out Adaptativo
        </span>
      </div>
      <div class="flex items-center gap-1.5">
        <button id="dlSeqBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] bg-[var(--background)] hover:opacity-80 text-xs font-medium transition">
          Tira Activa PNG
        </button>
        <button id="dlSheetBtn" class="px-2.5 py-1 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 text-xs font-medium transition">
          Spritesheet Completo
        </button>
      </div>
    </div>

    <div class="flex flex-col sm:flex-row items-center sm:items-stretch gap-4">
      <div class="flex flex-col items-center shrink-0">
        <div class="relative rounded-lg border border-[var(--border)] overflow-hidden p-2 bg-[var(--background)] flex items-center justify-center">
          <canvas id="mainCanvas" width="{disp_w}" height="{disp_h}" class="block cursor-crosshair pixelated"></canvas>
          <div id="poseBadge" class="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-[var(--card)]/90 border border-[var(--border)] text-xs font-mono text-[var(--foreground)]"></div>
          <div class="absolute top-1.5 right-1.5 flex items-center gap-1.5 px-1.5 py-1 rounded bg-[var(--card)]/90 border border-[var(--border)]">
            <span class="text-xs text-[var(--muted-foreground)]">1×</span>
            <canvas id="nativeCanvas" width="{cw}" height="{ch}" class="pixelated block"></canvas>
          </div>
        </div>
        <div id="pixelInfo" class="mt-1.5 text-xs text-[var(--muted-foreground)] font-mono h-4 truncate max-w-[220px]">
          Cursor sobre el sprite: (x,y) + pieza
        </div>
      </div>

      <div class="flex-1 flex flex-col justify-between gap-2.5 w-full min-w-0">
        <div>
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-[var(--muted-foreground)]">Secuencia</span>
            <span id="frameCounter" class="text-xs font-mono text-[var(--muted-foreground)]"></span>
          </div>
          <div id="modeBar" class="flex flex-wrap gap-1.5"></div>
        </div>

        <div>
          <div class="flex flex-wrap items-center justify-between gap-1.5 mb-1.5">
            <div class="flex items-center gap-1.5">
              <button id="playBtn" class="px-2.5 py-1 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium transition">❚❚ Pausar</button>
              <button id="prevBtn" class="px-2 py-1 rounded-md border border-[var(--border)] text-xs font-medium">◀</button>
              <button id="nextBtn" class="px-2 py-1 rounded-md border border-[var(--border)] text-xs font-medium">▶</button>
            </div>
            <button id="slowBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">🐢 0.5× Lento</button>
          </div>
          <input id="scrubber" type="range" min="0" max="1" value="0" class="w-full accent-[var(--primary)] cursor-pointer" />
        </div>

        <div>
          <div class="text-xs font-medium text-[var(--muted-foreground)] mb-1">Inspector del Rig</div>
          <div class="flex flex-wrap items-center gap-1.5">
            <button id="outlineBtn" class="px-2.5 py-1 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)] border border-[var(--border)] text-xs font-medium transition">Sel-Out 1px ✓</button>
            <button id="xrayBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">Capas + Pivotes</button>
            <button id="isoBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">Loseta 2:1</button>
            <button id="gridBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">Red</button>
            <button id="bgBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">Fondo: Damero</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const DATA = {json_str};
    const W = {cw}, H = {ch}, SCALE = {scale};
    const PAL = DATA.palette;
    const OUT_SYMS = new Set(DATA.outline_syms);
    const ANIM_KEYS = Object.keys(DATA.anims);

    let mode = ANIM_KEYS.length > 1 ? "__combo__" : ANIM_KEYS[0];
    let stepIdx = 0;
    let playing = true;
    let slowMo = false;
    let useOutline = true;
    let showXray = false;
    let showIso = {iso_default};
    let showGrid = false;
    let bgMode = 0;
    let hoverPx = null;
    let timerId = null;

    const mainCanvas = document.getElementById("mainCanvas");
    const ctx = mainCanvas.getContext("2d");
    const nativeCanvas = document.getElementById("nativeCanvas");
    const nctx = nativeCanvas.getContext("2d");
    const scrubber = document.getElementById("scrubber");

    const modeBar = document.getElementById("modeBar");
    if (ANIM_KEYS.length > 1) {{
      const cb = document.createElement("button");
      cb.dataset.mode = "__combo__";
      cb.className = "mode-btn px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium";
      cb.textContent = "⚡ Combo";
      modeBar.appendChild(cb);
    }}
    ANIM_KEYS.forEach(k => {{
      const b = document.createElement("button");
      b.dataset.mode = k;
      b.className = "mode-btn px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium";
      b.textContent = `${{DATA.anims[k].label}} (${{DATA.anims[k].outlined.length}}f)`;
      modeBar.appendChild(b);
    }});

    function getPlaylist() {{
      if (mode !== "__combo__") {{
        return DATA.anims[mode].outlined.map((_, i) => ({{ animKey: mode, fi: i }}));
      }}
      const list = [];
      ANIM_KEYS.forEach(k => DATA.anims[k].outlined.forEach((_, i) => list.push({{ animKey: k, fi: i }})));
      return list;
    }}

    function toHex([r, g, b]) {{
      return "#" + [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("").toUpperCase();
    }}

    function renderFrame(tctx, animKey, fi, outlinedFlag, xrayFlag) {{
      const seq = DATA.anims[animKey];
      const fr = outlinedFlag ? seq.outlined[fi] : seq.raw[fi];
      const pf = seq.parts[fi];
      const img = tctx.createImageData(W, H);
      for (let y = 0; y < H; y++) {{
        for (let x = 0; x < W; x++) {{
          const ch = fr[y][x];
          if (ch !== "." && PAL[ch]) {{
            let [r, g, b, a] = PAL[ch];
            if (xrayFlag) {{
              const pc = pf[y][x];
              if (DATA.parts_meta[pc]) {{
                const [tr, tg, tb] = DATA.parts_meta[pc].tint;
                r = Math.round(r * 0.42 + tr * 0.58);
                g = Math.round(g * 0.42 + tg * 0.58);
                b = Math.round(b * 0.42 + tb * 0.58);
              }}
            }}
            const i = (y * W + x) * 4;
            img.data[i] = r; img.data[i+1] = g; img.data[i+2] = b; img.data[i+3] = a;
          }}
        }}
      }}
      return img;
    }}

    function setToggle(el, active) {{
      el.classList.toggle("bg-[var(--secondary)]", active);
      el.classList.toggle("text-[var(--secondary-foreground)]", active);
      el.classList.toggle("font-semibold", active);
    }}

    function draw() {{
      const isLight = document.documentElement.classList.contains("light");
      const pl = getPlaylist();
      stepIdx = ((stepIdx % pl.length) + pl.length) % pl.length;
      const cur = pl[stepIdx];
      const seq = DATA.anims[cur.animKey];
      scrubber.max = Math.max(0, pl.length - 1);
      scrubber.value = stepIdx;

      if (bgMode === 0) {{
        const c1 = isLight ? "#EAEEF3" : "#1E2430";
        const c2 = isLight ? "#DCE2EA" : "#161B24";
        for (let y = 0; y < H; y++) {{
          for (let x = 0; x < W; x++) {{
            ctx.fillStyle = (x + y) % 2 === 0 ? c1 : c2;
            ctx.fillRect(x * SCALE, y * SCALE, SCALE, SCALE);
          }}
        }}
      }} else {{
        ctx.fillStyle = bgMode === 1 ? "#141923" : "#F3F6EE";
        ctx.fillRect(0, 0, W * SCALE, H * SCALE);
      }}

      if (showIso) {{
        ctx.save();
        ctx.strokeStyle = "rgba(86, 179, 54, 0.45)";
        ctx.fillStyle = "rgba(86, 179, 54, 0.10)";
        ctx.lineWidth = 1.5;
        const cx = W * SCALE * 0.54, cy = H * SCALE * 0.80, hw = W * SCALE * 0.38, hh = hw * 0.5;
        ctx.beginPath();
        ctx.moveTo(cx, cy - hh); ctx.lineTo(cx + hw, cy); ctx.lineTo(cx, cy + hh); ctx.lineTo(cx - hw, cy);
        ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.restore();
      }}

      nctx.clearRect(0, 0, W, H);
      nctx.putImageData(renderFrame(nctx, cur.animKey, cur.fi, useOutline, false), 0, 0);

      const tmp = document.createElement("canvas");
      tmp.width = W; tmp.height = H;
      tmp.getContext("2d").putImageData(renderFrame(nctx, cur.animKey, cur.fi, useOutline, showXray), 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(tmp, 0, 0, W * SCALE, H * SCALE);

      if (showGrid) {{
        ctx.strokeStyle = bgMode === 1 || (!isLight && bgMode === 0) ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.12)";
        ctx.lineWidth = 1;
        for (let x = 1; x < W; x++) {{ const p = x * SCALE + 0.5; ctx.beginPath(); ctx.moveTo(p, 0); ctx.lineTo(p, H * SCALE); ctx.stroke(); }}
        for (let y = 1; y < H; y++) {{ const p = y * SCALE + 0.5; ctx.beginPath(); ctx.moveTo(0, p); ctx.lineTo(W * SCALE, p); ctx.stroke(); }}
      }}

      if (showXray) {{
        const pivs = seq.pivots[cur.fi];
        ctx.save();
        for (const [k, [px, py]] of Object.entries(pivs)) {{
          const sx = px * SCALE, sy = py * SCALE;
          ctx.strokeStyle = "#0F172A"; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(sx - 4, sy); ctx.lineTo(sx + 4, sy); ctx.moveTo(sx, sy - 4); ctx.lineTo(sx, sy + 4); ctx.stroke();
          ctx.strokeStyle = "#FACC15"; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(sx - 4, sy); ctx.lineTo(sx + 4, sy); ctx.moveTo(sx, sy - 4); ctx.lineTo(sx, sy + 4); ctx.stroke();
        }}
        ctx.restore();
      }}

      if (hoverPx) {{
        ctx.strokeStyle = "#FACC15"; ctx.lineWidth = 1.5;
        ctx.strokeRect(hoverPx.x * SCALE + 0.75, hoverPx.y * SCALE + 0.75, SCALE - 1.5, SCALE - 1.5);
      }}

      document.getElementById("poseBadge").textContent = seq.labels[cur.fi];
      document.getElementById("frameCounter").textContent = `Frame ${{stepIdx + 1}} / ${{pl.length}}`;
      document.querySelectorAll(".mode-btn").forEach(b => setToggle(b, b.dataset.mode === mode));
      setToggle(document.getElementById("slowBtn"), slowMo);
      const ob = document.getElementById("outlineBtn");
      ob.textContent = useOutline ? "Sel-Out 1px ✓" : "Sel-Out OFF";
      setToggle(ob, useOutline);
      setToggle(document.getElementById("xrayBtn"), showXray);
      setToggle(document.getElementById("isoBtn"), showIso);
      setToggle(document.getElementById("gridBtn"), showGrid);
    }}

    function scheduleTick() {{
      clearTimeout(timerId);
      if (!playing) return;
      const pl = getPlaylist();
      const cur = pl[stepIdx % pl.length];
      const ms = DATA.anims[cur.animKey].ms[cur.fi] * (slowMo ? 2.2 : 1.0);
      timerId = setTimeout(() => {{
        stepIdx = (stepIdx + 1) % pl.length;
        draw();
        scheduleTick();
      }}, ms);
    }}

    function setPlaying(val) {{
      playing = val;
      document.getElementById("playBtn").textContent = playing ? "❚❚ Pausar" : "▶ Reproducir";
      scheduleTick();
    }}

    document.querySelectorAll(".mode-btn").forEach(b => b.addEventListener("click", () => {{ mode = b.dataset.mode; stepIdx = 0; draw(); scheduleTick(); }}));
    document.getElementById("playBtn").addEventListener("click", () => setPlaying(!playing));
    document.getElementById("prevBtn").addEventListener("click", () => {{ setPlaying(false); const n = getPlaylist().length; stepIdx = (stepIdx - 1 + n) % n; draw(); }});
    document.getElementById("nextBtn").addEventListener("click", () => {{ setPlaying(false); const n = getPlaylist().length; stepIdx = (stepIdx + 1) % n; draw(); }});
    scrubber.addEventListener("input", (e) => {{ setPlaying(false); stepIdx = Number(e.target.value); draw(); }});
    document.getElementById("slowBtn").addEventListener("click", () => {{ slowMo = !slowMo; draw(); if (playing) scheduleTick(); }});
    document.getElementById("outlineBtn").addEventListener("click", () => {{ useOutline = !useOutline; draw(); }});
    document.getElementById("xrayBtn").addEventListener("click", () => {{ showXray = !showXray; draw(); }});
    document.getElementById("isoBtn").addEventListener("click", () => {{ showIso = !showIso; draw(); }});
    document.getElementById("gridBtn").addEventListener("click", () => {{ showGrid = !showGrid; draw(); }});
    document.getElementById("bgBtn").addEventListener("click", (e) => {{
      bgMode = (bgMode + 1) % 3;
      e.currentTarget.textContent = ["Fondo: Damero", "Fondo: Noche", "Fondo: Día"][bgMode];
      draw();
    }});

    mainCanvas.addEventListener("mousemove", (e) => {{
      const r = mainCanvas.getBoundingClientRect();
      const x = Math.min(W - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * W)));
      const y = Math.min(H - 1, Math.max(0, Math.floor(((e.clientY - r.top) / r.height) * H)));
      hoverPx = {{ x, y }};
      const cur = getPlaylist()[stepIdx];
      const seq = DATA.anims[cur.animKey];
      const fr = useOutline ? seq.outlined[cur.fi] : seq.raw[cur.fi];
      const rawCh = seq.raw[cur.fi][y][x];
      const ch = fr[y][x];
      const pc = seq.parts[cur.fi][y][x];
      const infoEl = document.getElementById("pixelInfo");
      if (ch === "." || !PAL[ch]) {{
        infoEl.textContent = `(${{x}}, ${{y}}) · Transparente`;
      }} else {{
        let lname = DATA.parts_meta[pc] ? DATA.parts_meta[pc].name : "";
        if (!lname) lname = (rawCh === "." && OUT_SYMS.has(ch)) ? "Sel-Out Adaptativo" : "Sombra / FX";
        infoEl.textContent = `(${{x}},${{y}}) ${{toHex(PAL[ch])}} · ${{lname}}`;
      }}
      draw();
    }});
    mainCanvas.addEventListener("mouseleave", () => {{ hoverPx = null; draw(); }});

    function dl(c, name) {{ const a = document.createElement("a"); a.download = name; a.href = c.toDataURL("image/png"); a.click(); }}
    document.getElementById("dlSeqBtn").addEventListener("click", () => {{
      const cur = getPlaylist()[stepIdx];
      const seq = DATA.anims[cur.animKey];
      const c = document.createElement("canvas"); c.width = W * seq.outlined.length; c.height = H;
      const cx = c.getContext("2d");
      seq.outlined.forEach((_, i) => cx.putImageData(renderFrame(cx, cur.animKey, i, useOutline, false), i * W, 0));
      dl(c, `${{cur.animKey}}_${{c.width}}x${{H}}.png`);
    }});
    document.getElementById("dlSheetBtn").addEventListener("click", () => {{
      const maxF = Math.max(...ANIM_KEYS.map(k => DATA.anims[k].outlined.length));
      const c = document.createElement("canvas"); c.width = W * maxF; c.height = H * ANIM_KEYS.length;
      const cx = c.getContext("2d");
      ANIM_KEYS.forEach((k, ri) => DATA.anims[k].outlined.forEach((_, fi) => cx.putImageData(renderFrame(cx, k, fi, useOutline, false), fi * W, ri * H)));
      dl(c, `spritesheet_${{c.width}}x${{c.height}}.png`);
    }});

    draw();
    scheduleTick();
  </script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Diagnostic Visual QA Sheet
# ---------------------------------------------------------------------------
def save_diag_sheet(path, cw, ch, palette, anim_results):
    z = max(2, min(4, 160 // max(cw, ch)))
    max_f = max(len(v["outlined"]) for v in anim_results.values())
    cell_w = max(cw * z, cw * 2 + 10) + 6
    row_h = ch * z + ch + 22
    w_img = 10 + max_f * cell_w + 4
    h_img = 10 + len(anim_results) * row_h

    diag = [[(242, 245, 240, 255) for _ in range(w_img)] for _ in range(h_img)]
    for ri, (_, seq) in enumerate(anim_results.items()):
        y_top = 10 + ri * row_h
        bg_main = (28, 34, 46, 255) if ri % 2 == 1 else (235, 240, 230, 255)
        for fi, fr in enumerate(seq["outlined"]):
            x_left = 10 + fi * cell_w
            for py in range(ch * z):
                for px in range(cw * z):
                    fg = palette[fr[py // z][px // z]]
                    diag[y_top + py][x_left + px] = blend(bg_main, fg)
            ny = y_top + ch * z + 6
            for py in range(ch):
                for px in range(cw):
                    fg = palette[fr[py][px]]
                    diag[ny + py][x_left + px] = blend((238, 242, 234, 255), fg)
                    if x_left + cw + 6 + px < w_img:
                        diag[ny + py][x_left + cw + 6 + px] = blend((26, 32, 44, 255), fg)

    write_png(path, w_img, h_img, diag)


# ---------------------------------------------------------------------------
# Main Execution Engine
# ---------------------------------------------------------------------------
def resolve_part_transform(pid, parts_by_id, frame_poses, memo):
    if pid in memo:
        return memo[pid]
    pdef = parts_by_id[pid]
    local = frame_poses.get(pid, {})
    dx = float(local.get("dx", 0.0))
    dy = float(local.get("dy", 0.0))
    rot = float(local.get("rot", 0.0))
    sx = float(local.get("sx", 1.0))
    sy = float(local.get("sy", 1.0))

    parent_id = pdef.get("parent")
    if parent_id and parent_id in parts_by_id:
        pdx, pdy, prot, psx, psy = resolve_part_transform(parent_id, parts_by_id, frame_poses, memo)
        inh_rot = float(pdef.get("inherit_rot", 1.0))
        inh_scale = bool(pdef.get("inherit_scale", True))
        dx += pdx
        dy += pdy
        rot += prot * inh_rot
        if inh_scale:
            sx *= psx
            sy *= psy

    memo[pid] = (dx, dy, rot, sx, sy)
    return memo[pid]


def mirror_frames_h(frames_list):
    return [[row[::-1] for row in fr] for fr in frames_list]


def main():
    parser = argparse.ArgumentParser(description="Animate a pixel-art sprite using Cutout Rig + EPX RotSprite + Adaptive Sel-Out.")
    parser.add_argument("--rig", "-r", help="Path to declarative JSON rig file")
    parser.add_argument("--inspect", help="Inspect a PNG or _spec.json and print numbered (x, y) coordinate ruler")
    parser.add_argument("--out-dir", help="Directory to export per-animation 1x PNG strips")
    parser.add_argument("--prefix", default="rig", help="Filename prefix for per-animation strips")
    parser.add_argument("--spritesheet", help="Output path for combined multi-row PNG spritesheet")
    parser.add_argument("--mirror-x", action="store_true", help="Also generate horizontally mirrored animations (e.g. SW -> SE)")
    parser.add_argument("--export-spec", help="Optional path to export flattened multi-frame _spec.json")
    parser.add_argument("--diag", help="Output path for visual QA diagnostic sheet PNG")
    parser.add_argument("--html", help="Output path for interactive HTML evaluator widget")
    args = parser.parse_args()

    if args.inspect:
        if args.inspect.lower().endswith(".json"):
            with open(args.inspect, "r", encoding="utf-8") as f:
                spec = json.load(f)
        else:
            w, h, grid = pts.decode_image(args.inspect)
            spec = pts.build_spec_from_rgba(w, h, grid)
        pts.print_ruler_map(spec)
        return

    if not args.rig:
        parser.error("Provide --rig <rig.json> or --inspect <sprite.png|spec.json>.")

    rig_dir = os.path.dirname(os.path.abspath(args.rig))
    with open(args.rig, "r", encoding="utf-8") as f:
        rig = json.load(f)

    # Load base sprite & palette
    palette = {".": (0, 0, 0, 0)}
    base_rows = None
    if "base_spec" in rig:
        bs_path = rig["base_spec"]
        if not os.path.isabs(bs_path):
            bs_path = os.path.join(rig_dir, bs_path)
        if bs_path.lower().endswith(".json"):
            with open(bs_path, "r", encoding="utf-8") as f:
                bs = json.load(f)
        else:
            w_in, h_in, g_in = pts.decode_image(bs_path)
            bs = pts.build_spec_from_rgba(w_in, h_in, g_in)
        for sym, col in bs["palette"].items():
            palette[sym] = parse_color(col)
        base_rows = bs["frames"][int(rig.get("base_frame_index", 0))]

    for sym, col in rig.get("palette", {}).items():
        palette[sym] = parse_color(col)

    if "base_frame" in rig:
        base_rows = rig["base_frame"]

    if not base_rows:
        raise ValueError("Rig must provide 'base_spec' or 'base_frame'.")

    bh, bw = len(base_rows), len(base_rows[0])
    canvas_cfg = rig.get("canvas", {})
    cw = int(canvas_cfg.get("width", bw))
    ch = int(canvas_cfg.get("height", bh))
    base_offset = tuple(canvas_cfg.get("base_offset", [(cw - bw) // 2, (ch - bh) // 2]))

    ignore_syms = set(rig.get("ignore_symbols", [".", "s", "u"]))
    ignore_syms.add(".")
    strip_syms = set(rig.get("strip_outer_symbols", ["O", "o"]))

    clean_fill = strip_outer_silhouette(base_rows, strip_syms, ignore_syms)

    # Prepare parts in Z-order
    parts_list = rig.get("parts", [])
    parts_by_id = {p["id"]: p for p in parts_list}
    part_grids_4x = {}
    part_codes = {}
    part_meta = {}

    for idx, pdef in enumerate(parts_list):
        pid = pdef["id"]
        code = str(idx + 1) if idx < 8 else chr(ord("A") + idx - 8)
        part_codes[pid] = code
        part_meta[code] = {
            "name": pdef.get("label", pid),
            "tint": TINT_CYCLE[idx % len(TINT_CYCLE)],
        }
        part_grids_4x[pid] = build_part_grids(pdef, clean_fill, bw, bh)
    part_meta["9"] = {"name": "FX Procedural", "tint": [244, 63, 94]}

    outline_cfg = rig.get("outline", {"mode": "selout_auto"})
    shadow_cfg = rig.get("shadow", {"enabled": False})
    ground_y = float(shadow_cfg.get("cy", base_offset[1] + bh - 2))

    anim_results = {}
    all_outline_syms = set()

    for anim_key, anim_def in rig.get("animations", {}).items():
        default_ms = int(anim_def.get("fps_default_ms", 120))
        anim_label = anim_def.get("label", anim_key)
        out_frames, raw_frames, part_frames, piv_frames, ms_list, labels_list = [], [], [], [], [], []

        for fi, fdef in enumerate(anim_def.get("frames", [])):
            raw_c = [["." for _ in range(cw)] for _ in range(ch)]
            part_c = [["." for _ in range(cw)] for _ in range(ch)]
            poses = fdef.get("poses", {})
            fx_list = fdef.get("fx", [])
            memo = {}

            for pdef in parts_list:
                pid = pdef["id"]
                if poses.get(pid, {}).get("hidden", False):
                    continue
                dx, dy, rot, sx, sy = resolve_part_transform(pid, parts_by_id, poses, memo)
                vname = poses.get(pid, {}).get("variant", "default")
                g4x = part_grids_4x[pid].get(vname, part_grids_4x[pid]["default"])
                blit_rotsprite(
                    raw_c, part_c, g4x, pdef["pivot"], base_offset,
                    dx, dy, rot, sx, sy, part_codes[pid]
                )
                # Interleaved FX right after a specific part (e.g. open mouth cavity after throat, before head!)
                for fx in fx_list:
                    if fx.get("after_part") == pid:
                        apply_fx_primitive(raw_c, part_c, fx, tag_code="9")

            for fx in fx_list:
                if not fx.get("after_part") and fx.get("layer", "before_outline") == "before_outline":
                    apply_fx_primitive(raw_c, part_c, fx, tag_code="9")

            outlined_c, used_out = apply_outline(raw_c, palette, outline_cfg, ignore_syms, ground_y)
            all_outline_syms |= used_out

            for fx in fx_list:
                if fx.get("layer") == "after_outline":
                    apply_fx_primitive(outlined_c, None, fx, tag_code="9")

            if shadow_cfg.get("enabled", False):
                f_sh = fdef.get("shadow", {})
                sh_scale = float(f_sh.get("scale", 1.0))
                sh_dx = float(f_sh.get("dx", 0.0))
                sh_dy = float(f_sh.get("dy", 0.0))
                sh_sym = shadow_cfg.get("symbol", "s")
                if sh_sym not in palette:
                    palette[sh_sym] = (20, 26, 38, 85)
                scx = float(shadow_cfg.get("cx", base_offset[0] + bw * 0.5)) + sh_dx
                scy = float(shadow_cfg.get("cy", base_offset[1] + bh - 2)) + sh_dy
                srx = float(shadow_cfg.get("rx", bw * 0.35)) * sh_scale
                sry = float(shadow_cfg.get("ry", 3.2)) * sh_scale
                draw_ground_shadow(outlined_c, scx, scy, srx, sry, sh_sym)
                draw_ground_shadow(raw_c, scx, scy, srx, sry, sh_sym)

            world_pivs = {}
            for pdef in parts_list:
                pid = pdef["id"]
                dx, dy, _, _, _ = resolve_part_transform(pid, parts_by_id, poses, memo)
                world_pivs[pid] = [
                    round(base_offset[0] + pdef["pivot"][0] + dx, 1),
                    round(base_offset[1] + pdef["pivot"][1] + dy, 1),
                ]

            out_frames.append(["".join(r) for r in outlined_c])
            raw_frames.append(["".join(r) for r in raw_c])
            part_frames.append(["".join(r) for r in part_c])
            piv_frames.append(world_pivs)
            ms_list.append(int(fdef.get("ms", default_ms)))
            labels_list.append(fdef.get("label", f"{anim_label} F{fi + 1}"))

        anim_results[anim_key] = {
            "label": anim_label,
            "outlined": out_frames,
            "raw": raw_frames,
            "parts": part_frames,
            "pivots": piv_frames,
            "ms": ms_list,
            "labels": labels_list,
        }

        if args.mirror_x:
            m_key = f"{anim_key}_mirror"
            anim_results[m_key] = {
                "label": f"{anim_label} (Espejo)",
                "outlined": mirror_frames_h(out_frames),
                "raw": mirror_frames_h(raw_frames),
                "parts": mirror_frames_h(part_frames),
                "pivots": [{k: [round(cw - 1 - vx, 1), vy] for k, (vx, vy) in pv.items()} for pv in piv_frames],
                "ms": list(ms_list),
                "labels": [f"{lb} ↔" for lb in labels_list],
            }

    # Export individual strips
    exported_strips = []
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        for akey, seq in anim_results.items():
            frs = seq["outlined"]
            strip_w = cw * len(frs)
            s_path = os.path.join(args.out_dir, f"{args.prefix}_{akey}_{strip_w}x{ch}.png")
            rows = []
            for y in range(ch):
                row = []
                for fr in frs:
                    for x in range(cw):
                        row.append(palette[fr[y][x]])
                rows.append(row)
            write_png(s_path, strip_w, ch, rows)
            exported_strips.append(os.path.abspath(s_path))

    # Export combined multi-row spritesheet
    if args.spritesheet:
        max_f = max(len(seq["outlined"]) for seq in anim_results.values())
        sheet_rows = []
        for seq in anim_results.values():
            frs = seq["outlined"]
            for y in range(ch):
                row = []
                for fi in range(max_f):
                    if fi < len(frs):
                        for x in range(cw):
                            row.append(palette[frs[fi][y][x]])
                    else:
                        row.extend([(0, 0, 0, 0)] * cw)
                sheet_rows.append(row)
        write_png(args.spritesheet, cw * max_f, ch * len(anim_results), sheet_rows)

    # Export flattened _spec.json compatible with render_matrix.py
    if args.export_spec:
        flat_frames = []
        flat_timeline = []
        for seq in anim_results.values():
            flat_frames.extend(seq["outlined"])
            flat_timeline.extend(seq["ms"])
        out_spec = {
            "name": rig.get("name", "Rigged Sprite"),
            "width": cw,
            "height": ch,
            "isometric": bool(rig.get("isometric", False)),
            "palette": {k: pts.rgba_to_hex(v) for k, v in palette.items() if k != "."},
            "frames": flat_frames,
            "timeline": flat_timeline,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.export_spec)), exist_ok=True)
        with open(args.export_spec, "w", encoding="utf-8") as f:
            json.dump(out_spec, f, indent=2, ensure_ascii=False)

    if args.diag:
        save_diag_sheet(args.diag, cw, ch, palette, anim_results)

    if args.html:
        build_html_evaluator(
            args.html,
            rig.get("name", "Sprite"),
            cw, ch,
            bool(rig.get("isometric", False)),
            palette,
            part_meta,
            anim_results,
            all_outline_syms,
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "canvas": f"{cw}x{ch}",
                "animations": {k: len(v["outlined"]) for k, v in anim_results.items()},
                "strips": exported_strips,
                "spritesheet": os.path.abspath(args.spritesheet) if args.spritesheet else None,
                "diag": os.path.abspath(args.diag) if args.diag else None,
                "html": os.path.abspath(args.html) if args.html else None,
            }
        )
    )


if __name__ == "__main__":
    main()
