# Pixel Art AI Prompt Engineering Reference

When generating a base image (either handing the prompt to the user by default, or invoking `image-generator` when explicitly requested), tailor the prompt to the target canvas dimensions (`W × H`), perspective, and subject colors.

---

## 1. Choosing the Chroma-Key Background Color

Always specify a **single, flat, uniform solid background color** with high contrast against the sprite so chroma-key extraction leaves zero halos:

- **Default**: `uniform flat pure magenta (#FF00FF) background` — best for green, blue, yellow, brown, gray, and metallic subjects.
- **If the subject contains pink, purple, red, or magenta**: switch to `uniform flat pure neon green (#00FF00) background`.
- **If the subject contains both neon green and magenta**: use `uniform flat pure cyan (#00FFFF) background`.

Never ask for a "transparent checkerboard background" in an AI image prompt—AI generators draw literal gray/white squares onto the image.

---

## 2. Calibrating Detail Density to Target Resolution (`W × H`)

AI image models typically render on ~`1024×1024` canvases. To make the image collapse cleanly onto an exact `W × H` pixel grid without turning into unrecognizable noise, adjust the **proportion and detail instructions** based on `min(W, H)`:

| Target Size (`min(W, H)`) | Detail Tier | Structural Prompt Directives |
| :--- | :--- | :--- |
| **`8` – `24` px** (Micro / Icon) | **Tier 1: Iconic Minimal** | Chibi / oversized head-to-body ratio (`1:1`), ultra-bold silhouette, chunky pixel clusters, maximum 6–8 flat color tones, thick readable dark outline, zero fine textures, zero small accessories, simplified 2-pixel eyes. |
| **`25` – `48` px** (Classic Sprite) | **Tier 2: 16-bit Sprite** | Clear readable game-sprite proportions, distinct silhouette, crisp 1px dark selective outlines (colored dark outlines on lit edges), cel-shaded color clusters of 10–14 colors, expressive eyes with 1px white specular highlight, no micro-patterns or thin 1px strands. |
| **`49` – `96` px** (Detailed Sprite / Battler) | **Tier 3: Detailed 16/32-bit** | Classic SNES / GBA / PS1 sprite detail, 16–24 color palette with hue-shifted shadows and highlights, defined clothing folds/armor plates/anatomy, clean pixel clusters, deliberate dithering only if requested. |
| **`97`+ px** (Portrait / Scene / Boss) | **Tier 4: High-Bit Illustration** | Rich pixel art illustration, 24–32+ hue-shifted palette, clear light-source planes, crisp pixel clusters without soft airbrushing or gradients. |

### Non-Square Aspect Ratios (`W ≠ H`)

- Calculate the simplified ratio `W:H` (e.g., `16×24` -> `2:3` vertical; `64×32` -> `2:1` horizontal; `320×180` -> `16:9` widescreen).
- Include the framing guidance in the prompt AND tell the user which aspect ratio setting to select in their generator (e.g., `2:3`, `16:9`, or `1:1` centered with margin if their generator only supports square canvases—`pixelize_sprite.py` automatically crops the bounding box and fits it into `W × H`).

---

## 3. Perspective & Projection Clauses

Insert the exact projection clause matching the user's request:

- **Isometric (`2:1` game grid)**:
  `isometric 3/4 top-down view aligned to a classic 2:1 isometric tactics game grid (like Final Fantasy Tactics, Tactics Ogre, Into the Breach), facing forward-left (south-west), grounded 3D volume`
- **Top-Down RPG (`3/4` overhead)**:
  `classic 2D RPG 3/4 overhead top-down sprite view (like Chrono Trigger, Zelda: A Link to the Past, Pokémon GBA), facing forward`
- **Side View / Platformer**:
  `2D side-view profile game sprite (like Mega Man X, Castlevania GBA, Celeste), clear readable silhouette facing right`
- **Front / UI Inventory Icon**:
  `centered front-facing RPG inventory icon sprite, bold diagonal or symmetrical composition filling 85% of frame`

---

## 4. Master Prompt Template

Assemble the prompt in **English** (image models follow technical pixel-art constraints far more accurately in English), and present it inside a copyable code block:

```text
Clean pixel art game sprite of [SUBJECT & POSE], [PERSPECTIVE CLAUSE].
Designed specifically to read cleanly when downscaled to [W]x[H] pixels: [TIER DIRECTIVES FOR WxH].
[ERA / STYLE, e.g., 16-bit GBA / SNES sprite aesthetic], crisp dark selective outlines, clear top-left light source, hue-shifted cel-shaded pixel clusters, limited palette of ~[N] colors ([OPTIONAL COLOR NOTES]).
Single isolated subject centered with generous margin on a completely flat, uniform solid [CHROMA COLOR NAME] ([HEX]) background.
Strict constraints: NO anti-aliasing, NO soft gradients, NO airbrushing, NO drop shadow on background, NO ground tile or scenery, NO text or watermarks, NO grid lines.
```

### Recommended Generator Settings Note (Include for User)
When delivering the prompt to the user, briefly mention in their language:
1. **Relación de aspecto / Aspect Ratio**: Recommend matching `W:H` (or `1:1` square—the conversion script auto-crops and fits `W×H`).
2. **Formato**: Prefer downloading as **PNG** (lossless) rather than JPG if possible, though `pixelize_sprite.py` cleans JPG chroma fringe automatically.

---

## 5. Built-in Named Palettes Reference

`pixelize_sprite.py` supports automatic perceptual quantization (`--colors N`) as well as preset palettes (`--palette <name>`):

- `auto` (default): Extracts `N` optimal colors from the image using perceptual median-cut + k-means cluster refinement.
- `gb` / `gameboy`: Classic 4-color Game Boy DMG olive greens (`#0F380F`, `#306230`, `#8BAC0F`, `#9BBC0F`).
- `pico8`: Official 16-color PICO-8 fantasy console palette.
- `endesga16`: Versatile 16-color indie game sprite palette with rich warm/cool ramps.
