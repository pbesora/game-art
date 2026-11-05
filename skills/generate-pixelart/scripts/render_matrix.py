#!/usr/bin/env python3
"""
render_matrix.py — Validate and render WxH ASCII/JSON pixel-art matrices into
native PNGs, upscaled previews, multi-frame spritesheets, visual QA sheets,
and an interactive HTML inspector widget for any custom sprite dimensions.
"""

import argparse
import json
import os
import struct
import zlib


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
    raise ValueError(f"Invalid palette color value: {val!r}")


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


def build_diag_sheet(path, w, h, frames, palette):
    zoom = max(2, min(12, 320 // max(w, h)))
    f_zoom = max(1, min(5, 140 // max(w, h)))
    num_f = len(frames)

    left_w = w * zoom
    left_h = h * zoom
    fw_px = max(w * f_zoom, w * 2 + 12)
    right_w = num_f * (fw_px + 10)
    total_w = 10 + left_w + 16 + right_w + 10
    total_h = max(left_h + 20, h * f_zoom * 2 + h + 46)

    canvas = [[(244, 246, 249, 255) for _ in range(total_w)] for _ in range(total_h)]

    # Left: Frame 0 magnified with grid
    f0 = frames[0]
    for py in range(h):
        for px in range(w):
            fg = palette[f0[py][px]]
            chk = (232, 235, 240, 255) if (px + py) % 2 == 0 else (214, 218, 226, 255)
            col = blend(chk, fg)
            for dy in range(zoom):
                for dx in range(zoom):
                    c = col
                    if zoom >= 4 and (dx == 0 or dy == 0):
                        fac = 0.74 if (px % 8 == 0 and dx == 0) or (py % 8 == 0 and dy == 0) else 0.89
                        c = (int(c[0] * fac), int(c[1] * fac), int(c[2] * fac), 255)
                    canvas[10 + py * zoom + dy][10 + px * zoom + dx] = c

    # Right: All frames on light, dark, and 1x native
    rx0 = 10 + left_w + 16
    for fi, fr in enumerate(frames):
        fx = rx0 + fi * (fw_px + 10)
        for py in range(h * f_zoom):
            for px in range(w * f_zoom):
                fg = palette[fr[py // f_zoom][px // f_zoom]]
                canvas[10 + py][fx + px] = blend((240, 244, 236, 255), fg)
                canvas[18 + h * f_zoom + py][fx + px] = blend((24, 30, 42, 255), fg)

        ny0 = 26 + h * f_zoom * 2
        if ny0 + h < total_h:
            for py in range(h):
                for px in range(w):
                    fg = palette[fr[py][px]]
                    canvas[ny0 + py][fx + px] = blend((240, 244, 236, 255), fg)
                    if fx + w + 6 + px < total_w:
                        canvas[ny0 + py][fx + w + 6 + px] = blend((24, 30, 42, 255), fg)

    write_png(path, total_w, total_h, canvas)


def generate_html_viewer(path, title, w, h, frames, palette, timeline, is_iso):
    scale = max(1, min(14, 224 // max(w, h)))
    cw = w * scale
    ch = h * scale
    pal_js = {k: list(v) for k, v in palette.items() if k != "."}
    opaque_count = sum(1 for k, v in pal_js.items() if v[3] >= 200)
    if not timeline:
        timeline = [{"frame": i, "ms": 220} for i in range(len(frames))]

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    .pixelated {{ image-rendering: pixelated; image-rendering: crisp-edges; }}
  </style>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3 select-none">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
      <div class="flex items-center gap-2.5">
        <h2 class="text-[var(--foreground)] font-semibold text-base">{title} · {w}×{h} px</h2>
        <span class="px-2 py-0.5 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs font-medium">
          {opaque_count} colores · {len(frames)} {"frame" if len(frames) == 1 else "frames"}
        </span>
      </div>
      <div class="flex items-center gap-1.5">
        <button id="dl1xBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] bg-[var(--background)] hover:opacity-80 text-xs font-medium transition">
          PNG 1× ({w}×{h})
        </button>
        <button id="dlSheetBtn" class="px-2.5 py-1 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 text-xs font-medium transition">
          {"PNG Zoom" if len(frames) == 1 else f"Spritesheet ({w * len(frames)}×{h})"}
        </button>
      </div>
    </div>

    <div class="flex flex-col sm:flex-row items-center sm:items-stretch gap-4">
      <div class="flex flex-col items-center shrink-0">
        <div class="relative rounded-lg border border-[var(--border)] overflow-hidden p-2 bg-[var(--background)] flex items-center justify-center" style="min-width: 180px; min-height: 180px;">
          <canvas id="mainCanvas" width="{cw}" height="{ch}" class="block cursor-crosshair pixelated"></canvas>
          <div class="absolute top-1.5 right-1.5 flex items-center gap-1.5 px-1.5 py-1 rounded bg-[var(--card)]/90 border border-[var(--border)]">
            <span class="text-xs text-[var(--muted-foreground)]">1×</span>
            <canvas id="nativeCanvas" width="{w}" height="{h}" class="pixelated block" style="max-width:48px; max-height:48px;"></canvas>
          </div>
        </div>
        <div id="pixelInfo" class="mt-1.5 text-xs text-[var(--muted-foreground)] font-mono h-4">
          Cursor sobre el sprite para ver (x, y) y #HEX
        </div>
      </div>

      <div class="flex-1 flex flex-col justify-between gap-3 w-full min-w-0">
        <div class="space-y-2.5">
          <div>
            <div class="text-xs font-medium text-[var(--muted-foreground)] mb-1.5">Vista y capas</div>
            <div class="flex flex-wrap items-center gap-1.5">
              <button id="gridBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">
                Cuadrícula {w}×{h}
              </button>
              <button id="isoBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition {'hidden' if not is_iso else ''}">
                Loseta 2:1 ✓
              </button>
              <button id="bgBtn" class="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium transition">
                Fondo: Damero
              </button>
            </div>
          </div>

          <div class="{'hidden' if len(frames) <= 1 else ''}">
            <div class="text-xs font-medium text-[var(--muted-foreground)] mb-1.5">Animación</div>
            <div class="flex flex-wrap items-center gap-1.5" id="animBar">
              <button id="playBtn" class="px-2.5 py-1 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium transition">
                ❚❚ Pausar
              </button>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-[var(--muted-foreground)]">Paleta activa</span>
            <span id="swatchHex" class="text-xs font-mono text-[var(--muted-foreground)]"></span>
          </div>
          <div id="swatches" class="flex flex-wrap gap-1"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const W = {w}, H = {h}, SCALE = {scale};
    const FRAMES = {json.dumps(frames)};
    const PAL = {json.dumps(pal_js)};
    const TIMELINE = {json.dumps(timeline)};
    let showGrid = false;
    let showIso = {"true" if is_iso else "false"};
    let bgMode = 0;
    let playing = FRAMES.length > 1;
    let currentFrame = 0;
    let stepIdx = 0;
    let timerId = null;
    let hoverPx = null;

    const mainCanvas = document.getElementById("mainCanvas");
    const ctx = mainCanvas.getContext("2d");
    const nativeCanvas = document.getElementById("nativeCanvas");
    const nctx = nativeCanvas.getContext("2d");

    function toHex([r, g, b]) {{
      return "#" + [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("").toUpperCase();
    }}

    function renderNative(tctx, fi, ox = 0) {{
      const fr = FRAMES[fi];
      const img = tctx.createImageData(W, H);
      for (let y = 0; y < H; y++) {{
        for (let x = 0; x < W; x++) {{
          const ch = fr[y][x];
          if (ch !== "." && PAL[ch]) {{
            const c = PAL[ch];
            const i = (y * W + x) * 4;
            img.data[i] = c[0]; img.data[i+1] = c[1]; img.data[i+2] = c[2]; img.data[i+3] = c[3];
          }}
        }}
      }}
      tctx.putImageData(img, ox, 0);
    }}

    function draw() {{
      const isLight = document.documentElement.classList.contains("light");
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
        ctx.strokeStyle = "rgba(122, 204, 46, 0.42)";
        ctx.fillStyle = "rgba(122, 204, 46, 0.10)";
        ctx.lineWidth = 1.5;
        const cx = (W * SCALE) / 2, cy = H * SCALE * 0.7, hw = W * SCALE * 0.46, hh = hw / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy - hh); ctx.lineTo(cx + hw, cy); ctx.lineTo(cx, cy + hh); ctx.lineTo(cx - hw, cy);
        ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.restore();
      }}

      nctx.clearRect(0, 0, W, H);
      renderNative(nctx, currentFrame);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(nativeCanvas, 0, 0, W * SCALE, H * SCALE);

      if (showGrid && SCALE >= 3) {{
        ctx.strokeStyle = bgMode === 1 || (!isLight && bgMode === 0) ? "rgba(255,255,255,0.13)" : "rgba(0,0,0,0.13)";
        ctx.lineWidth = 1;
        for (let x = 1; x < W; x++) {{ const p = x * SCALE + 0.5; ctx.beginPath(); ctx.moveTo(p, 0); ctx.lineTo(p, H * SCALE); ctx.stroke(); }}
        for (let y = 1; y < H; y++) {{ const p = y * SCALE + 0.5; ctx.beginPath(); ctx.moveTo(0, p); ctx.lineTo(W * SCALE, p); ctx.stroke(); }}
      }}

      if (hoverPx) {{
        ctx.strokeStyle = "#FACC15";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(hoverPx.x * SCALE + 0.75, hoverPx.y * SCALE + 0.75, Math.max(1, SCALE - 1.5), Math.max(1, SCALE - 1.5));
      }}
    }}

    const wrap = document.getElementById("swatches");
    const seen = new Set();
    Object.entries(PAL).forEach(([k, rgba]) => {{
      if (rgba[3] < 200) return;
      const hex = toHex(rgba);
      if (seen.has(hex)) return;
      seen.add(hex);
      const b = document.createElement("button");
      b.className = "w-5 h-5 rounded border border-[var(--border)]";
      b.style.backgroundColor = hex;
      b.title = hex;
      b.onmouseenter = () => document.getElementById("swatchHex").textContent = hex;
      wrap.appendChild(b);
    }});

    const animBar = document.getElementById("animBar");
    if (FRAMES.length > 1) {{
      FRAMES.forEach((_, idx) => {{
        const fb = document.createElement("button");
        fb.className = "px-2 py-1 rounded-md border border-[var(--border)] text-xs";
        fb.textContent = "F" + (idx + 1);
        fb.onclick = () => {{
          playing = false;
          document.getElementById("playBtn").textContent = "▶ Reproducir";
          clearTimeout(timerId);
          currentFrame = idx;
          draw();
        }};
        animBar.appendChild(fb);
      }});
    }}

    function tick() {{
      clearTimeout(timerId);
      if (!playing) {{ draw(); return; }}
      const st = TIMELINE[stepIdx % TIMELINE.length];
      currentFrame = st.frame % FRAMES.length;
      draw();
      timerId = setTimeout(() => {{ stepIdx = (stepIdx + 1) % TIMELINE.length; tick(); }}, st.ms || 200);
    }}

    document.getElementById("playBtn").onclick = (e) => {{
      playing = !playing;
      e.currentTarget.textContent = playing ? "❚❚ Pausar" : "▶ Reproducir";
      if (playing) tick(); else clearTimeout(timerId);
    }};
    document.getElementById("gridBtn").onclick = (e) => {{ showGrid = !showGrid; e.currentTarget.textContent = showGrid ? `Cuadrícula ${{W}}×${{H}} ✓` : `Cuadrícula ${{W}}×${{H}}`; draw(); }};
    document.getElementById("isoBtn").onclick = (e) => {{ showIso = !showIso; e.currentTarget.textContent = showIso ? "Loseta 2:1 ✓" : "Loseta 2:1"; draw(); }};
    document.getElementById("bgBtn").onclick = (e) => {{ bgMode = (bgMode + 1) % 3; e.currentTarget.textContent = ["Fondo: Damero", "Fondo: Oscuro", "Fondo: Claro"][bgMode]; draw(); }};

    mainCanvas.onmousemove = (e) => {{
      const r = mainCanvas.getBoundingClientRect();
      const x = Math.min(W - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * W)));
      const y = Math.min(H - 1, Math.max(0, Math.floor(((e.clientY - r.top) / r.height) * H)));
      hoverPx = {{ x, y }};
      const ch = FRAMES[currentFrame][y][x];
      document.getElementById("pixelInfo").textContent = (ch === "." || !PAL[ch]) ? `(${{x}}, ${{y}}) · Transparente` : `(${{x}}, ${{y}}) · ${{toHex(PAL[ch])}}`;
      draw();
    }};
    mainCanvas.onmouseleave = () => {{ hoverPx = null; draw(); }};

    function dl(c, name) {{ const a = document.createElement("a"); a.href = c.toDataURL("image/png"); a.download = name; a.click(); }}
    document.getElementById("dl1xBtn").onclick = () => {{
      const c = document.createElement("canvas"); c.width = W; c.height = H;
      renderNative(c.getContext("2d"), currentFrame); dl(c, `sprite_${{W}}x${{H}}.png`);
    }};
    document.getElementById("dlSheetBtn").onclick = () => {{
      if (FRAMES.length === 1) {{
        dl(mainCanvas, `sprite_${{W * SCALE}}x${{H * SCALE}}_zoom.png`);
      }} else {{
        const c = document.createElement("canvas"); c.width = W * FRAMES.length; c.height = H;
        const octx = c.getContext("2d");
        FRAMES.forEach((_, i) => renderNative(octx, i, i * W));
        dl(c, `spritesheet_${{W * FRAMES.length}}x${{H}}.png`);
      }}
    }};

    tick();
  </script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="Render a JSON pixel-art matrix spec to PNGs and HTML.")
    parser.add_argument("--spec", "-s", required=True, help="Path to JSON matrix spec file")
    parser.add_argument("--output", "-o", required=True, help="Output 1x native PNG path")
    parser.add_argument("--frame", type=int, default=0, help="Frame index for single-frame PNG outputs")
    parser.add_argument("--preview", help="Optional upscaled Nearest-Neighbor PNG path")
    parser.add_argument("--upscale", type=int, default=0, help="Integer upscale factor (0 = auto)")
    parser.add_argument("--spritesheet", help="Optional horizontal spritesheet PNG path")
    parser.add_argument("--diag", help="Optional diagnostic visual QA PNG path")
    parser.add_argument("--html", help="Optional interactive HTML inspector output path")
    args = parser.parse_args()

    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    w = int(spec["width"])
    h = int(spec["height"])
    title = spec.get("name", "Sprite")
    is_iso = bool(spec.get("isometric", False))
    timeline = spec.get("timeline")

    palette = {".": (0, 0, 0, 0)}
    for sym, col in spec["palette"].items():
        palette[sym] = parse_color(col)

    frames = spec["frames"]
    if not frames:
        raise ValueError("Spec must include at least one frame in 'frames'.")

    for fi, fr in enumerate(frames):
        if len(fr) != h:
            raise ValueError(f"Frame {fi} has {len(fr)} rows, expected height={h}.")
        for ri, row in enumerate(fr):
            if len(row) != w:
                raise ValueError(f"Frame {fi} row {ri} has length {len(row)}, expected width={w}: {row!r}")
            for ci, ch in enumerate(row):
                if ch not in palette:
                    raise ValueError(f"Unknown palette symbol {ch!r} at frame {fi}, ({ci}, {ri}).")

    f_idx = max(0, min(len(frames) - 1, args.frame))
    base_fr = frames[f_idx]
    native_rows = [[palette[base_fr[y][x]] for x in range(w)] for y in range(h)]
    write_png(args.output, w, h, native_rows)

    if args.preview:
        factor = args.upscale if args.upscale > 0 else max(2, min(16, 384 // max(w, h)))
        pw, ph = w * factor, h * factor
        up_rows = [[native_rows[y // factor][x // factor] for x in range(pw)] for y in range(ph)]
        write_png(args.preview, pw, ph, up_rows)

    if args.spritesheet:
        sheet_rows = []
        for y in range(h):
            row = []
            for fr in frames:
                for x in range(w):
                    row.append(palette[fr[y][x]])
            sheet_rows.append(row)
        write_png(args.spritesheet, w * len(frames), h, sheet_rows)

    if args.diag:
        build_diag_sheet(args.diag, w, h, frames, palette)

    if args.html:
        generate_html_viewer(args.html, title, w, h, frames, palette, timeline, is_iso)

    print(
        json.dumps(
            {
                "status": "ok",
                "size": f"{w}x{h}",
                "frames": len(frames),
                "output": os.path.abspath(args.output),
                "preview": os.path.abspath(args.preview) if args.preview else None,
                "spritesheet": os.path.abspath(args.spritesheet) if args.spritesheet else None,
                "diag": os.path.abspath(args.diag) if args.diag else None,
                "html": os.path.abspath(args.html) if args.html else None,
            }
        )
    )


if __name__ == "__main__":
    main()
