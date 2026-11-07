---
name: animate-pixelart
description: >-
  Animates any pixel-art character or sprite into game-ready multi-frame strips, spritesheets, and interactive rig inspectors using the Cutout Rig Pixel Art method (anatomical part decomposition, 4x EPX/RotSprite transforms, Squash & Stretch, sprite-swapping, procedural FX, and adaptive hue-matched 1px selective outlining). Use this skill whenever the user asks to animate a pixel-art sprite or create character animations such as idle, walk, run, jump, attack, hit, or multi-directional isometric cycles.
---

# Animate Pixel Art (`animate-pixelart`)

This skill produces fluid, zero-boil pixel-art character animations from a **single static base sprite** (`PNG` or `_spec.json`) at **any target frame size (`W × H`)** using **Cutout Rigging + `4×` EPX RotSprite + Luminance-Normalized Hue-Matched Selective Outlining (*Sel-Out*)**.

## Step 0: Resolve Base Sprite & Action Specifications

1. **Locate or Create the Base Sprite**:
   - **Existing PNG or `_spec.json`**: Use it directly as the rig source. (If the input is a raw high-res AI image rather than a clean pixel-art sprite, quantize/downsample it first with `../generate-pixelart/scripts/pixelize_sprite.py` if available.)
   - **No Sprite Provided Yet**: Coordinate with `generate-pixelart` (respecting its prompt-handoff vs. direct-generation policy) to obtain the clean static rest pose before rigging.
   - **4-Diagonal Isometric (`SW / SE / NW / NE`)**: One front-quarter base (`SW`) automatically yields `SE` via `--mirror-x`; for true rear diagonals (`NW / NE`), derive or generate a rear base sprite (`NW`) and run `--mirror-x` for `NE`.
2. **Choose Action Canvas Headroom (`canvas.width × canvas.height`)**:
   - Preserve `1:1` pixel density of the base sprite—never resize the character's pixels—and expand the transparent frame if needed (e.g., `32×32` base placed at `base_offset: [14, 16]` inside `48×48`) so jump arcs, weapon swings, or tongue whips never clip.
3. **Choose Outline Style (`outline.mode`)**:
   - **`"selout_auto"` (Default — Colored Hue-Matched Sel-Out)**: Automatically normalizes adjacent pixel hues to outline luminance bands (`top_lum: 70`, `side_lum: 54`, `bottom_lum: 26`), synthesizing dark hue-tinted swatches if missing so green/blue/pink surfaces get matching forest-green/navy/burgundy outlines instead of harsh pure black.
   - **`"selout_palette"`**: Same hue-matched Sel-Out restricted strictly to existing dark colors in `palette`.
   - **`"solid"`**: Bold `1px` dark comic-ink outline (e.g., Edmund McMillen style).
   - **`"none"`**: Lineless pixel art.

---

## Step 1: Inspect Exact `(x, y)` Coordinates of the Base Sprite

Run [png_to_spec.py](./scripts/png_to_spec.py) (or `rig_animator.py --inspect`) to print a numbered ASCII coordinate map and bounding box:

```bash
python "<skill_dir>/scripts/png_to_spec.py" \
  --input "<sprite.png_or_spec.json>" \
  --output "<scratch_dir>/<name>_base_spec.json" \
  --inspect
```

Use the `(x, y)` ruler output to identify clean bounding boxes (`bbox: [x0, y0, x1, y1]`), polygons, or symbol filters for each anatomical part (`far_leg`, `torso`, `head`, `arms`, `near_leg`, etc.) and joint pivot coordinates `[px, py]`.

---

## Step 2: Author the Declarative Rig File (`<name>_rig.json`)

Read [animation-recipes.md](./references/animation-recipes.md) for keyframe timing curves, Squash & Stretch ratios, and isometric `2:1` vector rules. Create `<scratch_dir>/<name>_rig.json` following this structure:

```json
{
  "name": "Frog",
  "isometric": true,
  "base_spec": "<scratch_dir>/<name>_base_spec.json",
  "palette": {
    "m": "#4E1426",
    "M": "#84223A",
    "t": "#D64472",
    "T": "#FA749C",
    "p": "#FFC0D4",
    "u": "#DEE4D6AF"
  },
  "canvas": { "width": 48, "height": 48, "base_offset": [14, 16] },
  "strip_outer_symbols": ["O", "o"],
  "ignore_symbols": [".", "s", "u"],
  "outline": {
    "mode": "selout_auto",
    "candidates": ["d", "o", "O", "m"],
    "top_lit_symbols": ["d"],
    "neutral_bias_rgb": [56, 118, 68]
  },
  "shadow": { "enabled": true, "symbol": "s", "cx": 30.0, "cy": 39.5, "rx": 11.5, "ry": 3.6 },
  "parts": [
    {
      "id": "torso",
      "label": "Torso",
      "pivot": [16.0, 19.0],
      "region": { "bbox": [10, 12, 26, 24] }
    },
    {
      "id": "head",
      "label": "Cabeza",
      "pivot": [14.0, 11.0],
      "parent": "torso",
      "inherit_rot": 1.0,
      "region": { "bbox": [1, 2, 27, 13] },
      "extra_pixels": [[14, 13, "G"], [15, 13, "G"]]
    },
    {
      "id": "hind_leg",
      "label": "Anca trasera",
      "pivot": [23.0, 17.0],
      "parent": "torso",
      "inherit_rot": 0.0,
      "region": { "bbox": [21, 14, 30, 26] },
      "variants": {
        "extended": { "offset": [20, 15], "matrix": ["..ddgg..", "..."] }
      }
    }
  ],
  "animations": {
    "jump": {
      "label": "Salto",
      "frames": [
        { "label": "J1 · Reposo", "ms": 180, "poses": {} },
        {
          "label": "J2 · Anticipación",
          "ms": 140,
          "poses": {
            "torso": { "dx": 0.5, "dy": 2.4, "sx": 1.12, "sy": 0.82, "rot": -4 },
            "hind_leg": { "dx": -0.5, "dy": -1.5, "rot": 6 }
          },
          "shadow": { "scale": 1.08 }
        }
      ]
    }
  }
}
```

### Supported `fx` Primitives per Keyframe (`frames[i].fx`)
- **Open mouth / core (`"type": "ellipse"`)**: `{"type": "ellipse", "cx": 23, "cy": 28, "rx": 4.3, "ry": 2.8, "top_symbol": "m", "bottom_symbol": "M", "after_part": "throat"}`
- **Tongue / tentacle / tether (`"type": "line"`)**: `{"type": "line", "x0": 21.5, "y0": 28.5, "x1": 6.0, "y1": 36.3, "radius": 1.15, "top_symbol": "T", "bottom_symbol": "t", "tip_radius": 1, "tip_highlight": "p", "layer": "before_outline"}`
- **Weapon slash smear (`"type": "arc"`)**: `{"type": "arc", "cx": 24, "cy": 24, "r_inner": 9, "r_outer": 15, "deg_start": 120, "deg_end": 230, "symbol": "W", "layer": "before_outline"}`
- **Dust puffs / sparks / drips (`"type": "pixels"`)**: `{"type": "pixels", "points": [[39, 39, "u"]], "only_empty": true, "layer": "after_outline"}`

---

## Step 3: Render, Visually QA (`--diag`), and Deliver

1. **Run [rig_animator.py](./scripts/rig_animator.py)**:
   ```bash
   python "<skill_dir>/scripts/rig_animator.py" \
     --rig "<scratch_dir>/<name>_rig.json" \
     --out-dir "<workspace>" \
     --prefix "<name>_rig" \
     --spritesheet "<workspace>/<name>_spritesheet.png" \
     --diag "<scratch_dir>/<name>_rig_diag.png" \
     --html "<artifact_dir>/<name>_rig_viewer.html"
   ```
   *(Add `--mirror-x` when generating mirrored isometric diagonals like `SW -> SE`.)*

2. **Mandatory Visual QA**:
   - Inspect `<scratch_dir>/<name>_rig_diag.png` using `read_file` before presenting outputs.
   - Verify at both magnified and `1×` scales:
     - Zero clipped pixels at canvas borders during peak jump height or full attack reach.
     - Zero transparent seam cracks between rotated limbs and torso (add `extra_pixels` overlap if needed).
     - Harmonious colored Sel-Out outlines on both light and dark backgrounds (no accidental pure-black edges on shaded slopes unless `solid` mode was requested).
     - Eyes and key focal landmarks remain crisp across every frame.

3. **Deliverables**:
   - Individual `1×` animation strip PNGs (`(W * F) × H`) and the combined multi-row spritesheet PNG in the workspace.
   - When `--html` is generated in `<artifact_dir>`, register it as a `UserFacing: true` artifact so the user can test Combo playback, `0.5×` slow-motion, `Sel-Out ON/OFF`, and `Capas + Pivotes` X-Ray inspection.
