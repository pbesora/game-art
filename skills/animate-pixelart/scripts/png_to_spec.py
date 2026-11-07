#!/usr/bin/env python3
"""
png_to_spec.py — Convert any pixel-art PNG (or image) into a clean ASCII/JSON
matrix spec compatible with rig_animator.py and render_matrix.py, and optionally
print a numbered (x, y) ASCII coordinate ruler to help place rig regions & pivots.

Zero external dependencies required for standard 8-bit PNGs (pure stdlib struct/zlib),
with automatic Pillow or Windows .NET System.Drawing fallback for other formats.
"""

import argparse
import json
import os
import struct
import subprocess
import tempfile
import zlib

SYMBOL_POOL = (
    "gGLHCyYwbBrtTpPdcDSkKfvVuUxzXZqQjmJMnN"
    "0123456789"
    "aefiAEFI@#%&*+=?~"
)


def decode_png_stdlib(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")

    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    plte = []
    trns = b""
    idat_chunks = []

    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif ctype == b"PLTE":
            plte = [
                (chunk_data[i], chunk_data[i + 1], chunk_data[i + 2])
                for i in range(0, len(chunk_data), 3)
            ]
        elif ctype == b"tRNS":
            trns = chunk_data
        elif ctype == b"IDAT":
            idat_chunks.append(chunk_data)
        elif ctype == b"IEND":
            break

    if bit_depth != 8 or interlace != 0 or color_type not in (2, 3, 4, 6):
        raise ValueError(f"Unsupported PNG mode for stdlib reader (depth={bit_depth}, color={color_type}, interlace={interlace})")

    bpp_map = {2: 3, 3: 1, 4: 2, 6: 4}
    bpp = bpp_map[color_type]
    stride = width * bpp
    raw = zlib.decompress(b"".join(idat_chunks))

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    rows_bytes = []
    prev = bytearray(stride)
    offset = 0
    for _ in range(height):
        ftype = raw[offset]
        scan = bytearray(raw[offset + 1 : offset + 1 + stride])
        offset += 1 + stride

        recon = bytearray(stride)
        if ftype == 0:
            recon[:] = scan
        elif ftype == 1:
            for i in range(stride):
                left = recon[i - bpp] if i >= bpp else 0
                recon[i] = (scan[i] + left) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                recon[i] = (scan[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = recon[i - bpp] if i >= bpp else 0
                recon[i] = (scan[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = recon[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                recon[i] = (scan[i] + paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"Unknown PNG filter type {ftype}")

        rows_bytes.append(recon)
        prev = recon

    rgba_grid = []
    for row in rows_bytes:
        out_row = []
        if color_type == 6:
            for x in range(width):
                i = x * 4
                out_row.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
        elif color_type == 2:
            tr_rgb = struct.unpack(">HHH", trns[:6]) if len(trns) >= 6 else None
            for x in range(width):
                i = x * 3
                rgb = (row[i], row[i + 1], row[i + 2])
                a = 0 if (tr_rgb and rgb == tr_rgb) else 255
                out_row.append((rgb[0], rgb[1], rgb[2], a))
        elif color_type == 3:
            for x in range(width):
                idx = row[x]
                r, g, b = plte[idx] if idx < len(plte) else (0, 0, 0)
                a = trns[idx] if idx < len(trns) else 255
                out_row.append((r, g, b, a))
        elif color_type == 4:
            for x in range(width):
                v, a = row[x * 2], row[x * 2 + 1]
                out_row.append((v, v, v, a))
        rgba_grid.append(out_row)

    return width, height, rgba_grid


def decode_image(path):
    try:
        return decode_png_stdlib(path)
    except Exception:
        pass

    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        px = list(im.getdata())
        return w, h, [px[y * w : (y + 1) * w] for y in range(h)]
    except Exception:
        pass

    if os.name == "nt":
        tmp_raw = tempfile.mktemp(suffix=".rgba")
        ps = (
            "Add-Type -AssemblyName System.Drawing; "
            f"$b = [System.Drawing.Bitmap]::FromFile('{os.path.abspath(path)}'); "
            "$w = $b.Width; $h = $b.Height; "
            "$ms = New-Object System.IO.MemoryStream; "
            "$bw = New-Object System.IO.BinaryWriter($ms); "
            "$bw.Write([int]$w); $bw.Write([int]$h); "
            "for ($y=0; $y -lt $h; $y++) { for ($x=0; $x -lt $w; $x++) { "
            "$c = $b.GetPixel($x,$y); $bw.Write([byte]$c.R); $bw.Write([byte]$c.G); $bw.Write([byte]$c.B); $bw.Write([byte]$c.A); "
            "} } "
            f"[System.IO.File]::WriteAllBytes('{tmp_raw}', $ms.ToArray()); $b.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
        with open(tmp_raw, "rb") as f:
            buf = f.read()
        os.remove(tmp_raw)
        w, h = struct.unpack("<II", buf[:8])
        grid = []
        off = 8
        for _ in range(h):
            r = []
            for _ in range(w):
                r.append((buf[off], buf[off + 1], buf[off + 2], buf[off + 3]))
                off += 4
            grid.append(r)
        return w, h, grid

    raise RuntimeError(f"Could not decode image: {path}")


def luminance(rgba):
    return 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]


def rgba_to_hex(rgba):
    r, g, b, a = rgba
    if a == 255:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def build_spec_from_rgba(w, h, grid, name="Sprite", alpha_cutoff=16):
    unique_cols = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = grid[y][x]
            if a < alpha_cutoff:
                continue
            c = (r, g, b, a)
            unique_cols[c] = unique_cols.get(c, 0) + 1

    if len(unique_cols) > len(SYMBOL_POOL) + 3:
        raise ValueError(
            f"Sprite has {len(unique_cols)} unique colors (max supported in ASCII spec is {len(SYMBOL_POOL) + 3}). "
            "Quantize first with pixelize_sprite.py."
        )

    # Assign intuitive symbols: semi-transparent dark -> 's' (shadow), darkest opaque -> 'O', second darkest -> 'o', brightest -> 'W'
    col_to_sym = {}
    used_syms = {"."}

    semi_dark = [c for c in unique_cols if c[3] < 200 and luminance(c) < 80]
    if semi_dark:
        shadow_c = min(semi_dark, key=lambda c: c[3])
        col_to_sym[shadow_c] = "s"
        used_syms.add("s")

    opaque_sorted = sorted(
        [c for c in unique_cols if c not in col_to_sym],
        key=lambda c: (luminance(c), c[3]),
    )

    if opaque_sorted and luminance(opaque_sorted[0]) < 55:
        col_to_sym[opaque_sorted[0]] = "O"
        used_syms.add("O")
        opaque_sorted = opaque_sorted[1:]

    if opaque_sorted and luminance(opaque_sorted[0]) < 95:
        col_to_sym[opaque_sorted[0]] = "o"
        used_syms.add("o")
        opaque_sorted = opaque_sorted[1:]

    if opaque_sorted and luminance(opaque_sorted[-1]) > 225:
        col_to_sym[opaque_sorted[-1]] = "W"
        used_syms.add("W")
        opaque_sorted = opaque_sorted[:-1]

    pool_iter = (ch for ch in SYMBOL_POOL if ch not in used_syms)
    for c in opaque_sorted:
        col_to_sym[c] = next(pool_iter)

    palette = {sym: rgba_to_hex(col) for col, sym in col_to_sym.items()}
    rows = []
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        chars = []
        for x in range(w):
            c = grid[y][x]
            if c[3] < alpha_cutoff:
                chars.append(".")
            else:
                sym = col_to_sym[c]
                chars.append(sym)
                if sym != "s":
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
        rows.append("".join(chars))

    spec = {
        "name": name,
        "width": w,
        "height": h,
        "palette": palette,
        "frames": [rows],
        "bbox": [min_x, min_y, max_x, max_y] if max_x >= 0 else [0, 0, w - 1, h - 1],
    }
    return spec


def print_ruler_map(spec, frame_idx=0):
    w = spec["width"]
    h = spec["height"]
    rows = spec["frames"][frame_idx]
    print(f"=== Sprite Coordinate Map: {spec.get('name', 'Sprite')} ({w}x{h}) ===")
    if "bbox" in spec:
        bx0, by0, bx1, by1 = spec["bbox"]
        print(f"Body BBox (excl. shadow): x={bx0}..{bx1} ({bx1 - bx0 + 1}px), y={by0}..{by1} ({by1 - by0 + 1}px)")
    print("Palette:", json.dumps(spec["palette"], ensure_ascii=False))
    tens = "     " + "".join(str((x // 10) % 10) if x % 5 == 0 else " " for x in range(w))
    ones = "     " + "".join(str(x % 10) for x in range(w))
    print(tens)
    print(ones)
    print("    +" + "-" * w + "+")
    for y, r in enumerate(rows):
        print(f"{y:3d} |{r}| {y}")
    print("    +" + "-" * w + "+")


def main():
    parser = argparse.ArgumentParser(description="Convert a pixel-art PNG into a JSON matrix spec and inspect coordinates.")
    parser.add_argument("--input", "-i", required=True, help="Input PNG/image path or existing _spec.json")
    parser.add_argument("--output", "-o", help="Output JSON spec file path")
    parser.add_argument("--name", default="Sprite", help="Display name in spec")
    parser.add_argument("--alpha-cutoff", type=int, default=16, help="Alpha threshold below which pixels become '.'")
    parser.add_argument("--inspect", action="store_true", help="Print numbered (x, y) ASCII ruler grid to stdout")
    args = parser.parse_args()

    if args.input.lower().endswith(".json"):
        with open(args.input, "r", encoding="utf-8") as f:
            spec = json.load(f)
    else:
        w, h, grid = decode_image(args.input)
        spec = build_spec_from_rgba(w, h, grid, name=args.name, alpha_cutoff=args.alpha_cutoff)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)

    if args.inspect or not args.output:
        print_ruler_map(spec)
    else:
        print(json.dumps({"status": "ok", "size": f"{spec['width']}x{spec['height']}", "colors": len(spec["palette"]), "bbox": spec.get("bbox"), "output": os.path.abspath(args.output)}))


if __name__ == "__main__":
    main()
