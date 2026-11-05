#!/usr/bin/env python3
"""
pixelize_sprite.py — Convert, chroma-key, grid-snap, and palette-quantize any base image
into an exact WxH pixel-art sprite PNG (with zero mandatory third-party dependencies).
"""

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import zlib

NAMED_PALETTES = {
    "gb": [
        (15, 56, 15),
        (48, 98, 48),
        (139, 172, 15),
        (155, 188, 15),
    ],
    "gameboy": [
        (15, 56, 15),
        (48, 98, 48),
        (139, 172, 15),
        (155, 188, 15),
    ],
    "pico8": [
        (0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81),
        (171, 82, 54), (95, 87, 79), (194, 195, 199), (255, 241, 232),
        (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54),
        (41, 173, 255), (131, 118, 156), (255, 119, 168), (255, 204, 170),
    ],
    "endesga16": [
        (228, 166, 114), (184, 111, 80), (116, 63, 57), (63, 40, 50),
        (158, 40, 53), (229, 59, 68), (251, 146, 43), (255, 231, 98),
        (99, 198, 77), (50, 115, 69), (25, 61, 63), (79, 103, 129),
        (175, 191, 210), (255, 255, 255), (44, 232, 244), (4, 132, 209),
    ],
}

SYMBOL_POOL = (
    "OodgGLHyCcW"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "!@#$%^&*+-=~?"
)


def write_png(path, width, height, rgba_rows):
    """Write an 8-bit RGBA PNG using pure Python stdlib."""
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


def load_image_rgba(path):
    """Load an image into (width, height, list_of_rgba_rows). Uses Pillow if present, else .NET on Windows."""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Input image not found: {abs_path}")

    try:
        from PIL import Image
        im = Image.open(abs_path).convert("RGBA")
        w, h = im.size
        px = list(im.getdata())
        rows = [px[y * w:(y + 1) * w] for y in range(h)]
        return w, h, rows
    except ImportError:
        pass

    if os.name == "nt":
        with tempfile.NamedTemporaryFile(suffix=".rgba", delete=False) as tf:
            raw_bin = tf.name
        try:
            escaped_in = abs_path.replace("'", "''")
            escaped_out = raw_bin.replace("'", "''")
            ps_script = f"""
Add-Type -AssemblyName System.Drawing
$bmp = [System.Drawing.Bitmap]::new('{escaped_in}')
$w = $bmp.Width
$h = $bmp.Height
Write-Output "$w $h"
$rect = [System.Drawing.Rectangle]::new(0, 0, $w, $h)
$data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$bytes = New-Object byte[] ($w * $h * 4)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
$bmp.UnlockBits($data)
$bmp.Dispose()
[System.IO.File]::WriteAllBytes('{escaped_out}', $bytes)
"""
            res = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_script], text=True
            ).strip()
            w, h = map(int, res.splitlines()[-1].split())
            with open(raw_bin, "rb") as f:
                buf = f.read()
            rows = []
            for y in range(h):
                row_off = y * w * 4
                row = []
                for x in range(w):
                    idx = row_off + x * 4
                    row.append((buf[idx + 2], buf[idx + 1], buf[idx], buf[idx + 3]))
                rows.append(row)
            return w, h, rows
        finally:
            if os.path.exists(raw_bin):
                os.remove(raw_bin)

    raise RuntimeError(
        "Pillow (PIL) is required on non-Windows platforms. Install with: pip install Pillow"
    )


def parse_size(size_str, width, height):
    if size_str:
        s = size_str.lower().replace(" ", "")
        if "x" in s:
            w_s, h_s = s.split("x", 1)
            return int(w_s), int(h_s)
        n = int(s)
        return n, n
    if width and height:
        return int(width), int(height)
    raise ValueError("Provide --size WxH (e.g. 32x32, 16x24, 64x64) or both --width and --height.")


def parse_hex_color(s):
    s = s.strip().lstrip("#")
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError(f"Invalid hex color: {s}")


def color_dist_sq(c1, c2):
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    return 2 * dr * dr + 4 * dg * dg + 3 * db * db


def detect_border_bg(w, h, rows):
    """Inspect border pixels; return None if already transparent, else dominant RGB tuple."""
    border = []
    step_x = max(1, w // 32)
    step_y = max(1, h // 32)
    for x in range(0, w, step_x):
        border.append(rows[0][x])
        border.append(rows[h - 1][x])
    for y in range(0, h, step_y):
        border.append(rows[y][0])
        border.append(rows[y][w - 1])

    transparent_count = sum(1 for p in border if p[3] < 32)
    if transparent_count >= len(border) * 0.5:
        return None

    # Quantize border RGB to 16-unit buckets to find dominant background color
    buckets = {}
    for r, g, b, a in border:
        if a >= 32:
            key = (r // 16, g // 16, b // 16)
            buckets.setdefault(key, []).append((r, g, b))
    if not buckets:
        return None
    best = max(buckets.values(), key=len)
    n = len(best)
    return (
        sum(c[0] for c in best) // n,
        sum(c[1] for c in best) // n,
        sum(c[2] for c in best) // n,
    )


def remove_background(w, h, rows, bg_mode, tolerance):
    if bg_mode == "none":
        return rows

    key_rgb = None
    if bg_mode == "auto":
        key_rgb = detect_border_bg(w, h, rows)
        if key_rgb is None:
            return rows
    elif bg_mode == "magenta":
        key_rgb = (255, 0, 255)
    elif bg_mode == "green":
        key_rgb = (0, 255, 0)
    elif bg_mode == "cyan":
        key_rgb = (0, 255, 255)
    elif bg_mode == "white":
        key_rgb = (255, 255, 255)
    elif bg_mode == "black":
        key_rgb = (0, 0, 0)
    else:
        key_rgb = parse_hex_color(bg_mode)

    kr, kg, kb = key_rgb
    is_magenta_key = kr > 200 and kb > 200 and kg < 80
    is_green_key = kg > 200 and kr < 80 and kb < 80
    is_cyan_key = kg > 200 and kb > 200 and kr < 80
    tol_sq = (tolerance * tolerance) * 9

    out = []
    for y in range(h):
        out_row = []
        for x in range(w):
            r, g, b, a = rows[y][x]
            if a < 20:
                out_row.append((0, 0, 0, 0))
                continue

            is_bg = color_dist_sq((r, g, b), key_rgb) <= tol_sq
            if is_magenta_key and (r > 145 and b > 145 and g < 120 and (r + b - 2 * g) > 175):
                is_bg = True
            elif is_green_key and (g > 155 and r < 115 and b < 115 and (2 * g - r - b) > 175):
                is_bg = True
            elif is_cyan_key and (g > 145 and b > 145 and r < 120 and (g + b - 2 * r) > 175):
                is_bg = True

            if is_bg:
                out_row.append((0, 0, 0, 0))
            else:
                # De-spill chroma fringe on dark outline pixels
                if is_magenta_key and r > g and b > g and g < 95:
                    r = min(r, g + 12)
                    b = min(b, g + 14)
                elif is_green_key and g > r and g > b and max(r, b) < 95:
                    g = min(g, max(r, b) + 14)
                elif is_cyan_key and g > r and b > r and r < 95:
                    g = min(g, r + 12)
                    b = min(b, r + 14)
                out_row.append((r, g, b, a))
        out.append(out_row)
    return out


def resample_to_grid(w, h, rows, target_w, target_h, margin, align, fit):
    # Find foreground bounding box
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if rows[y][x][3] >= 128:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    grid = [[(0, 0, 0, 0) for _ in range(target_w)] for _ in range(target_h)]
    if max_x < min_x:
        return grid

    if fit == "none":
        min_x, min_y, max_x, max_y = 0, 0, w - 1, h - 1
        margin = 0

    bw = max_x - min_x + 1
    bh = max_y - min_y + 1
    avail_w = max(1, target_w - 2 * margin)
    avail_h = max(1, target_h - 2 * margin)

    if fit == "stretch":
        tw, th = avail_w, avail_h
        scale_x = bw / tw
        scale_y = bh / th
    else:
        scale = max(bw / avail_w, bh / avail_h)
        tw = max(1, min(avail_w, round(bw / scale)))
        th = max(1, min(avail_h, round(bh / scale)))
        scale_x = bw / tw
        scale_y = bh / th

    off_x = (target_w - tw) // 2
    if align == "bottom":
        off_y = max(0, target_h - margin - th)
    else:
        off_y = (target_h - th) // 2

    for ty in range(th):
        sy0 = int(min_y + ty * scale_y)
        sy1 = max(sy0 + 1, int(min_y + (ty + 1) * scale_y))
        for tx in range(tw):
            sx0 = int(min_x + tx * scale_x)
            sx1 = max(sx0 + 1, int(min_x + (tx + 1) * scale_x))

            if (sx1 - sx0) <= 2 and (sy1 - sy0) <= 2:
                cx = min(w - 1, (sx0 + sx1) // 2)
                cy = min(h - 1, (sy0 + sy1) // 2)
                px = rows[cy][cx]
                if px[3] >= 128:
                    grid[off_y + ty][off_x + tx] = (px[0], px[1], px[2], 255)
                continue

            # Center-core medoid sampling preserves crisp outlines & highlights
            pad_x = (sx1 - sx0) // 4
            pad_y = (sy1 - sy0) // 4
            cx0, cx1 = sx0 + pad_x, max(sx0 + pad_x + 1, sx1 - pad_x)
            cy0, cy1 = sy0 + pad_y, max(sy0 + pad_y + 1, sy1 - pad_y)

            core_samples = []
            all_samples = []
            total = 0
            fg_count = 0
            for sy in range(sy0, min(h, sy1)):
                for sx in range(sx0, min(w, sx1)):
                    total += 1
                    r, g, b, a = rows[sy][sx]
                    if a >= 128:
                        fg_count += 1
                        all_samples.append((r, g, b))
                        if cx0 <= sx < cx1 and cy0 <= sy < cy1:
                            core_samples.append((r, g, b))

            if fg_count > total * 0.42:
                chosen = core_samples if core_samples else all_samples
                chosen.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
                mr, mg, mb = chosen[len(chosen) // 2]
                grid[off_y + ty][off_x + tx] = (mr, mg, mb, 255)

    return grid


def clean_orphans(grid):
    h = len(grid)
    w = len(grid[0])
    to_clear = []
    for y in range(h):
        for x in range(w):
            if grid[y][x][3] == 0:
                continue
            neighbors = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and grid[ny][nx][3] > 0:
                        neighbors += 1
            if neighbors == 0:
                to_clear.append((y, x))
    for y, x in to_clear:
        grid[y][x] = (0, 0, 0, 0)


def quantize_colors(grid, max_colors, palette_spec):
    """Quantize opaque pixels in `grid` to `max_colors` or a named/custom palette."""
    h = len(grid)
    w = len(grid[0])
    opaque = [
        (grid[y][x][0], grid[y][x][1], grid[y][x][2])
        for y in range(h)
        for x in range(w)
        if grid[y][x][3] >= 128
    ]
    if not opaque:
        return grid, []

    if palette_spec and palette_spec.lower() != "auto":
        key = palette_spec.lower()
        if key in NAMED_PALETTES:
            palette = list(NAMED_PALETTES[key])
        else:
            palette = [parse_hex_color(tok) for tok in palette_spec.split(",") if tok.strip()]
    else:
        # Median-cut perceptual color quantization + 4 iterations of k-means snapping
        unique = list(set(opaque))
        if len(unique) <= max_colors:
            palette = sorted(unique, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
        else:
            boxes = [list(opaque)]
            while len(boxes) < max_colors:
                # Pick box with largest weighted channel range (break ties by count)
                best_idx = -1
                best_score = -1
                best_ch = 0
                for idx, box in enumerate(boxes):
                    if len(box) <= 1:
                        continue
                    rs = [c[0] for c in box]
                    gs = [c[1] for c in box]
                    bs = [c[2] for c in box]
                    ranges = [
                        (max(rs) - min(rs)) * 1.1,
                        (max(gs) - min(gs)) * 1.3,
                        (max(bs) - min(bs)) * 1.0,
                    ]
                    ch = ranges.index(max(ranges))
                    if ranges[ch] == 0:
                        continue
                    score = ranges[ch] * (len(box) ** 0.35)
                    if score > best_score:
                        best_score = score
                        best_idx = idx
                        best_ch = ch
                if best_idx == -1:
                    break
                box = boxes.pop(best_idx)
                box.sort(key=lambda c: c[best_ch])
                mid = len(box) // 2
                boxes.append(box[:mid])
                boxes.append(box[mid:])

            palette = []
            for box in boxes:
                n = len(box)
                palette.append((
                    round(sum(c[0] for c in box) / n),
                    round(sum(c[1] for c in box) / n),
                    round(sum(c[2] for c in box) / n),
                ))

            # 3 rounds of k-means refinement for crisp cluster centers
            for _ in range(3):
                clusters = [[] for _ in palette]
                for px in opaque:
                    bi = min(range(len(palette)), key=lambda i: color_dist_sq(px, palette[i]))
                    clusters[bi].append(px)
                for i, cl in enumerate(clusters):
                    if cl:
                        n = len(cl)
                        palette[i] = (
                            round(sum(c[0] for c in cl) / n),
                            round(sum(c[1] for c in cl) / n),
                            round(sum(c[2] for c in cl) / n),
                        )

            palette = sorted(
                list(set(palette)),
                key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2],
            )

    used = set()
    for y in range(h):
        for x in range(w):
            r, g, b, a = grid[y][x]
            if a >= 128:
                best_c = min(palette, key=lambda pc: color_dist_sq((r, g, b), pc))
                grid[y][x] = (best_c[0], best_c[1], best_c[2], 255)
                used.add(best_c)

    final_pal = sorted(used, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    return grid, final_pal


def add_ground_shadow(grid, mode):
    if mode == "none":
        return
    h = len(grid)
    w = len(grid[0])
    min_x, max_x, max_y = w, -1, -1
    for y in range(h):
        for x in range(w):
            if grid[y][x][3] >= 128:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y > max_y: max_y = y
    if max_x < min_x:
        return

    cx = (min_x + max_x) / 2.0
    rx = max(2.0, (max_x - min_x + 1) * 0.46)
    ry = max(1.2, rx * (0.42 if mode == "iso" else 0.28))
    cy = min(h - 1 - math.ceil(ry), max_y - ry * 0.45)

    for y in range(h):
        for x in range(w):
            if grid[y][x][3] > 0:
                continue
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            if dx * dx + dy * dy <= 1.0:
                grid[y][x] = (20, 28, 42, 85)


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


def save_diag_sheet(path, grid):
    h = len(grid)
    w = len(grid[0])
    zoom = max(2, min(12, 384 // max(w, h)))
    prev_zoom = max(1, min(6, 192 // max(w, h)))

    left_w = w * zoom
    left_h = h * zoom
    right_w = max(w * prev_zoom, w + 16)
    total_w = 10 + left_w + 16 + right_w + 16
    total_h = max(left_h + 20, h * prev_zoom * 2 + h + 48)

    canvas = [[(244, 246, 249, 255) for _ in range(total_w)] for _ in range(total_h)]

    for py in range(h):
        for px in range(w):
            fg = grid[py][px]
            chk = (232, 235, 240, 255) if (px + py) % 2 == 0 else (214, 218, 226, 255)
            col = blend(chk, fg)
            for dy in range(zoom):
                for dx in range(zoom):
                    c = col
                    if zoom >= 4 and (dx == 0 or dy == 0):
                        f = 0.74 if (px % 8 == 0 and dx == 0) or (py % 8 == 0 and dy == 0) else 0.89
                        c = (int(c[0] * f), int(c[1] * f), int(c[2] * f), 255)
                    canvas[10 + py * zoom + dy][10 + px * zoom + dx] = c

    rx = 10 + left_w + 16
    for py in range(h * prev_zoom):
        for px in range(w * prev_zoom):
            fg = grid[py // prev_zoom][px // prev_zoom]
            canvas[10 + py][rx + px] = blend((240, 244, 236, 255), fg)
            canvas[20 + h * prev_zoom + py][rx + px] = blend((24, 30, 42, 255), fg)

    ny0 = 30 + h * prev_zoom * 2
    if ny0 + h < total_h and rx + w * 2 + 12 < total_w:
        for py in range(h):
            for px in range(w):
                fg = grid[py][px]
                canvas[ny0 + py][rx + px] = blend((240, 244, 236, 255), fg)
                canvas[ny0 + py][rx + w + 8 + px] = blend((24, 30, 42, 255), fg)

    write_png(path, total_w, total_h, canvas)


def export_matrix_spec(path, grid, palette):
    h = len(grid)
    w = len(grid[0])
    if len(palette) > len(SYMBOL_POOL):
        raise ValueError(f"Palette size ({len(palette)}) exceeds ASCII symbol pool ({len(SYMBOL_POOL)}).")

    rgb_to_sym = {}
    pal_dict = {".": [0, 0, 0, 0]}
    for idx, c in enumerate(palette):
        sym = SYMBOL_POOL[idx]
        if sym == "s":
            sym = SYMBOL_POOL[-1 - idx]
        rgb_to_sym[c] = sym
        pal_dict[sym] = [c[0], c[1], c[2], 255]

    has_shadow = False
    rows_str = []
    for y in range(h):
        chars = []
        for x in range(w):
            r, g, b, a = grid[y][x]
            if a == 0:
                chars.append(".")
            elif a < 200:
                has_shadow = True
                chars.append("s")
            else:
                chars.append(rgb_to_sym[(r, g, b)])
        rows_str.append("".join(chars))

    if has_shadow:
        pal_dict["s"] = [20, 28, 42, 85]

    spec = {
        "name": os.path.splitext(os.path.basename(path))[0],
        "width": w,
        "height": h,
        "palette": pal_dict,
        "frames": [rows_str],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Convert an image into an exact WxH pixel-art sprite.")
    parser.add_argument("--input", "-i", required=True, help="Path to source image (PNG, JPG, BMP, etc.)")
    parser.add_argument("--size", "-s", help="Target sprite size WxH (e.g. 16x16, 32x32, 32x48, 64x64)")
    parser.add_argument("--width", type=int, help="Target width if --size not used")
    parser.add_argument("--height", type=int, help="Target height if --size not used")
    parser.add_argument("--output", "-o", required=True, help="Output native PNG path (e.g. ./frog_32x32.png)")
    parser.add_argument("--preview", help="Optional upscaled preview PNG path")
    parser.add_argument("--upscale", type=int, default=0, help="Integer upscale factor for --preview (0 = auto)")
    parser.add_argument("--diag", help="Optional diagnostic grid sheet PNG path for visual QA")
    parser.add_argument("--export-spec", help="Optional JSON matrix spec path for pixel-level editing")
    parser.add_argument("--bg", default="auto", help="auto|magenta|green|cyan|white|black|none|#RRGGBB")
    parser.add_argument("--tolerance", type=int, default=65, help="Background color removal tolerance (0-150)")
    parser.add_argument("--colors", "-c", type=int, default=16, help="Max opaque colors in quantized palette")
    parser.add_argument("--palette", default="auto", help="auto|gb|pico8|endesga16 or comma-separated #RRGGBB")
    parser.add_argument("--margin", type=int, default=-1, help="Transparent pixel border margin (-1 = auto)")
    parser.add_argument("--align", choices=["center", "bottom"], default="center", help="Vertical alignment")
    parser.add_argument("--fit", choices=["contain", "stretch", "none"], default="contain", help="Crop/fit mode")
    parser.add_argument("--shadow", choices=["none", "iso", "oval"], default="none", help="Optional ground shadow")
    parser.add_argument("--keep-orphans", action="store_true", help="Do not clean isolated 1px noise")
    args = parser.parse_args()

    tw, th = parse_size(args.size, args.width, args.height)
    if tw < 1 or th < 1:
        raise ValueError("Target width and height must be >= 1.")

    margin = args.margin
    if margin < 0:
        min_dim = min(tw, th)
        margin = 0 if min_dim <= 12 else (1 if min_dim <= 48 else 2)

    sw, sh, src_rows = load_image_rgba(args.input)
    fg_rows = remove_background(sw, sh, src_rows, args.bg, args.tolerance)
    grid = resample_to_grid(sw, sh, fg_rows, tw, th, margin, args.align, args.fit)
    if not args.keep_orphans:
        clean_orphans(grid)
    grid, final_pal = quantize_colors(grid, args.colors, args.palette)
    add_ground_shadow(grid, args.shadow)

    write_png(args.output, tw, th, grid)

    if args.preview:
        factor = args.upscale if args.upscale > 0 else max(2, min(16, 384 // max(tw, th)))
        pw, ph = tw * factor, th * factor
        up_rows = [[grid[y // factor][x // factor] for x in range(pw)] for y in range(ph)]
        write_png(args.preview, pw, ph, up_rows)

    if args.diag:
        save_diag_sheet(args.diag, grid)

    if args.export_spec and len(final_pal) <= len(SYMBOL_POOL):
        export_matrix_spec(args.export_spec, grid, final_pal)

    print(
        json.dumps(
            {
                "status": "ok",
                "size": f"{tw}x{th}",
                "colors_used": len(final_pal),
                "output": os.path.abspath(args.output),
                "preview": os.path.abspath(args.preview) if args.preview else None,
                "diag": os.path.abspath(args.diag) if args.diag else None,
                "spec": os.path.abspath(args.export_spec) if args.export_spec else None,
            }
        )
    )


if __name__ == "__main__":
    main()
