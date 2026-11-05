---
name: generate-pixelart
description: >-
  Creates pixel-art prompts, game-ready sprites, spritesheets, and interactive pixel inspectors at any custom resolution (WxH).
  By default, delivers a tailored AI image generation prompt for the user unless the user explicitly asks to generate the image directly or provides a base image to convert.
---

# Generate Pixel Art (`generate-pixelart`)

This skill produces authentic, grid-accurate pixel-art sprites and spritesheets of **any user-requested dimensions (`W × H`)**, combining precision AI prompt engineering, chroma-key downsampling, perceptual palette quantization, and pixel-level matrix refinement.

## Core Execution Policy (Check First!)

Before running any tool, determine which of the **three modes** applies to the user's request:

1. **Mode A — Prompt Handoff (DEFAULT when no input image is provided)**
   - **Condition**: The user asks for a pixel art / sprite **without** explicitly asking you to generate the image directly, and **has not** supplied an input image file.
   - **Rule**: **DO NOT** invoke `image-generator` and **DO NOT** generate PNG files yet.
   - **Action**: Follow **Workflow A** below to craft and deliver a copy-ready AI image prompt tailored to their exact `W × H` target size, view, palette, and chroma-key background, then offer to convert the resulting image into the final `W × H` sprite once they share it.

2. **Mode B — Base Image Conversion & Polish**
   - **Condition**: The user provides an existing image (generated from Mode A's prompt or attached/referenced in the workspace) and wants it turned into a `W × H` pixel-art sprite.
   - **Action**: Skip image generation and run **Workflow B** directly on their image.

3. **Mode C — Direct Sprite Generation (ONLY when explicitly requested)**
   - **Condition**: The user **explicitly instructs** you to generate the image/sprite directly (e.g., *"genérala tú directamente"*, *"haz la imagen directamente"*, *"generate the sprite directly"*).
   - **Action**: Run **Workflow C** to generate the sprite end-to-end at the requested `W × H` size.

---

## Step 0: Resolve Sprite Specifications

Extract or confirm the target parameters (ask concisely only if critical details like the subject or dimensions are completely missing):

- **Dimensions (`W × H`)**: Any integer width and height (e.g., `16x16`, `24x24`, `32x32`, `16x24`, `48x64`, `64x64`, `128x128`, `320x180`). Never hardcode `32x32`—always pass the user's exact `WxH`.
- **View / Projection**: Isometric `2:1`, RPG `3/4` top-down, 2D side-view, or front/UI icon.
- **Style & Palette**: Color count (e.g., `4`, `8`, `12`, `16`, `32`) or named preset (`gb`, `pico8`, `endesga16`), plus outline style (selective colored outline vs. dark black outline).
- **Deliverables**: Single `1x` PNG + Nearest-Neighbor preview PNG, multi-frame spritesheet, and/or interactive HTML inspector.

---

## Workflow A: Prompt Handoff (Default Mode)

1. Read [prompt-templates.md](./references/prompt-templates.md) to select:
   - The **Detail Tier** matching `min(W, H)` (`8–24px`, `25–48px`, `49–96px`, or `97+px`).
   - The **Chroma-Key Background** (`#FF00FF` magenta by default; `#00FF00` neon green if the subject has pink/red/purple tones; `#00FFFF` cyan if both).
   - The **Perspective Clause** (`isometric 2:1`, `top-down 3/4`, `side-view`, or `icon`).
2. Output the engineered prompt inside a clean code block (in English for best AI image model adherence), accompanied by a brief note in the user's language covering:
   - Recommended aspect ratio (`W:H` or `1:1` square) and saving as PNG if supported.
   - How to continue: once they generate the image and pass its path (or drop it into the workspace), you will chroma-key, snap, quantize, and polish it to exact `W × H` RGBA PNGs.

---

## Workflow B: Convert & Polish a Base Image (`W × H`)

1. **Run the pixelizer script** ([pixelize_sprite.py](./scripts/pixelize_sprite.py)) to remove the background, de-spill edges, crop & fit proportionally into `W × H`, medoid-sample each cell, and quantize the palette:
   ```bash
   python "<skill_dir>/scripts/pixelize_sprite.py" \
     --input "<source_image>" \
     --size "<W>x<H>" \
     --colors <N> \
     --palette <auto|gb|pico8|endesga16|#HEX,...> \
     --shadow <none|iso|oval> \
     --output "<workspace>/<name>_<W>x<H>.png" \
     --preview "<workspace>/<name>_preview.png" \
     --diag "<scratch_dir>/<name>_diag.png" \
     --export-spec "<scratch_dir>/<name>_spec.json"
   ```
2. **Mandatory Visual QA**: Inspect `<scratch_dir>/<name>_diag.png` using `read_file`. Check:
   - Are outer outlines continuous without missing gaps or `2px` clumps?
   - Did eyes, mouth, or key focal details survive downscaling cleanly at `1x`?
   - Was all background chroma fringe removed (`--tolerance` can be tuned between `40` and `95` if needed)?
3. **Pixel-Level Polish & Animation (Recommended for `W, H <= 64` or when animations are requested)**:
   - Open `<scratch_dir>/<name>_spec.json` and refine individual ASCII cells in `frames[0]` (restore crisp `1px` eye highlights, selective outlines, clean curves, or add extra animation frames `frames[1..k]`).
   - Render final assets with [render_matrix.py](./scripts/render_matrix.py):
     ```bash
     python "<skill_dir>/scripts/render_matrix.py" \
       --spec "<scratch_dir>/<name>_spec.json" \
       --output "<workspace>/<name>_<W>x<H>.png" \
       --preview "<workspace>/<name>_preview.png" \
       --spritesheet "<workspace>/<name>_spritesheet.png" \
       --diag "<scratch_dir>/<name>_polished_diag.png" \
       --html "<artifact_dir>/<name>_viewer.html"
     ```
   - Re-verify `<name>_polished_diag.png` with `read_file` before presenting to the user.

---

## Workflow C: Direct Generation (Explicit Request Only)

Only run this workflow when the user **explicitly asks** you to generate the image/sprite directly:

- **For `min(W, H) >= 24` (Hybrid Pipeline — Preferred)**:
  1. Read [prompt-templates.md](./references/prompt-templates.md) and build the resolution-calibrated chroma-key prompt.
  2. Invoke the `image-generator` subagent with that prompt to produce a clean isolated base image in `<scratch_dir>/`.
  3. Execute **Workflow B** (`pixelize_sprite.py` -> visual QA via `read_file` -> pixel polish & optional animation frames via `render_matrix.py`) at the exact requested `W × H`.
- **For Micro Sprites (`W, H <= 24`, simple UI icons, tiles, or pure geometric sprites)**:
  1. Author the JSON spec (`width: W`, `height: H`, `palette`, `frames`) directly in `<scratch_dir>/<name>_spec.json`.
  2. Run [render_matrix.py](./scripts/render_matrix.py) with `--diag` and inspect via `read_file`, iterating on pixel coordinates until silhouettes and clusters read cleanly at both `1x` and magnified scales.

---

## Output & Delivery Checklist

- Always deliver the **exact `1x` (`W × H`) transparent RGBA PNG** alongside an **integer Nearest-Neighbor upscaled preview PNG** (never blurred/bilinear).
- When multiple frames are created, also export the horizontal **`(W * frames) × H` spritesheet PNG**.
- Optionally generate the compact interactive inspector (`--html` in `render_matrix.py`) when helpful for inspecting grid alignment, `2:1` isometric tiles, color HEX swatches, or frame playback.
