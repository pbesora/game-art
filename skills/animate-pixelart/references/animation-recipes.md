# Pixel-Art Cutout Rig Animation Recipes (`animate-pixelart`)

Use these proven keyframe curves, Squash & Stretch ratios, and isometric vector conventions when authoring `<name>_rig.json` for `scripts/rig_animator.py`.

---

## 1. Golden Rules for Crisp Cutout Rigging

1. **Action Canvas Headroom (`canvas.width × canvas.height`)**:
   - Never keep a tight `32×32` canvas if the character jumps `10px` into the air or swings a weapon/tongue `15px` forward.
   - Keep the character's **exact `1:1` pixel scale** (do not upscale the base sprite) and place it inside a padded action frame (e.g. `32×32` base inside `48×48` or `64×48`, setting `canvas.base_offset: [ox, oy]`).
2. **Overlap Padding at Joints (`extra_pixels`)**:
   - When carving `head`, `arms`, or `legs` out of `base_frame`, extend the interior hidden end of each limb by `1–2px` (`extra_pixels: [[x, y, sym], ...]`) into the torso socket so +/-`20°` RotSprite rotations never open transparent cracks.
3. **Outline Mode Selection (`outline.mode`)**:
   - **`"selout_auto"` (Default — Colored Hue-Matched Sel-Out)**: Normalizes each adjacent pixel's hue to target luminance bands (`top_lum: 70`, `side_lum: 54`, `bottom_lum: 26`) and synthesizes dark hue-matched outline swatches if missing. Prevents harsh pure-black outlines on green/blue/warm characters while preserving crisp contrast on both light and dark backgrounds.
   - **`"selout_palette"`**: Same luminance-normalized hue matching, restricted strictly to existing dark colors in `palette` (specify `candidates: ["d", "o", "O", "m"]` and optional `top_lit_symbols: ["d"]`).
   - **`"solid"`**: Bold `1px` comic-ink outline (`symbol: "O"`), ideal for Edmund McMillen / *Binding of Isaac* dark-ink aesthetics.
   - **`"none"`**: Lineless pixel art.
4. **Low-Chroma Belly / Sclera Bias (`neutral_bias_rgb`)**:
   - If a green or blue creature has a pale cream/white belly (`chroma < 65`), set `"neutral_bias_rgb": [R, G, B]` (e.g. `[56, 118, 68]` for forest green) so outlines touching the cream belly match the creature's body hue instead of turning brownish-gray.

---

## 2. Projection & Isometric `2:1` Axes

- **Side-View / Platformer**:
  - Forward = `+X` (or `-X`), Up = `-Y`, Ground shadow fixed at `cy`.
- **Isometric `2:1` Diagonals**:
  - Every ground displacement `(dx, dy)` along a tile axis follows a `2:1` slope:
    - **SW (Front-Left)**: `(-2k, +1k)`
    - **SE (Front-Right)**: `(+2k, +1k)` — derive automatically from `SW` via `--mirror-x`!
    - **NW (Back-Left)**: `(-2k, -1k)` — requires a rear-facing base sprite (`back_spec.json`), then `--mirror-x` yields **NE (`+2k, -1k`)**!
  - Vertical jumps move strictly along `-Y` (`dy < 0`) while the ground shadow stays on the ground plane (`shadow.scale` shrinks to `0.55–0.65` at apex).

---

## 3. Standard Action Keyframe Templates

### A. Idle / Breathing (`4` frames, loop ~`650ms`)
| Frame | `ms` | `torso` `(dy, sx, sy)` | Child accents (`head`, `arms`, `throat`) |
| :--- | :---: | :--- | :--- |
| **F1 Neutral** | `180` | `dy: 0, sx: 1.00, sy: 1.00` | Rest |
| **F2 Inhale Rise** | `160` | `dy: -1.0, sx: 0.98, sy: 1.03` | `head.dy: -0.4`, `arms.rot: -4` |
| **F3 Peak Hold** | `170` | `dy: -1.2, sx: 0.97, sy: 1.04` | Optional vocal sac / chest puff `sx: 1.08` |
| **F4 Exhale Settle** | `150` | `dy: 0.5, sx: 1.03, sy: 0.97` | `head.dy: +0.3` |

### B. Snappy Walk Cycle (`4` frames, loop ~`480ms`)
| Frame | `ms` | `torso` | `near_leg` / `far_leg` | `near_arm` / `far_arm` |
| :--- | :---: | :--- | :--- | :--- |
| **F1 Contact A** | `120` | `dy: 0.6, sx: 1.03, sy: 0.97` | Near fwd (`dx:-1.8, dy:0.8, rot:14`), Far back (`dx:1.8, dy:-0.8, rot:-14`) | Opposite swing to legs |
| **F2 Passing Up A** | `115` | `dy: -1.2, sx: 0.98, sy: 1.02` | Near planted (`dx:0, dy:0.5`), Far lifted (`dy:-1.8, rot:6`) | Returning toward center |
| **F3 Contact B** | `120` | `dy: 0.6, sx: 1.03, sy: 0.97` | Near back (`dx:1.8, dy:-0.8, rot:-14`), Far fwd (`dx:-1.8, dy:0.8, rot:14`) | Opposite swing to legs |
| **F4 Passing Up B** | `115` | `dy: -1.2, sx: 0.98, sy: 1.02` | Near lifted (`dy:-1.8, rot:6`), Far planted (`dx:0, dy:0.5`) | Returning toward center |

### C. Elastic Jump / Leap (`8` frames)
1. **J1 Rest (`160ms`)**: Neutral pose.
2. **J2 Anticipation Squat (`135ms`)**: `torso: {dy: +2.4, sx: 1.12, sy: 0.82, rot: -4}`, `shadow.scale: 1.08`. Keep feet planted (`legs.dy: -1.8` relative to lowered torso).
3. **J3 Explosive Launch (`105ms`)**: `torso: {dx: -1.5, dy: -4.5, sx: 1.08, sy: 0.94, rot: +16}`, swap `hind_leg` to `"variant": "extended"`, add takeoff dust (`fx` `pixels` on `"layer": "after_outline"`), `shadow.scale: 0.82`.
4. **J4 High Ascent (`115ms`)**: `torso: {dx: -2.5, dy: -9.5, rot: +10}`, keep `"variant": "extended"`, `shadow.scale: 0.62`.
5. **J5 Apex Hang-Time (`130ms`)**: `torso: {dx: -2.5, dy: -11.5, sx: 1.04, sy: 0.96, rot: 0}`, tuck legs (`variant: "default"`), `shadow.scale: 0.54`.
6. **J6 Nose-Dive Descent (`110ms`)**: `torso: {dx: -1.5, dy: -6.0, rot: -15}`, reach front legs down (`rot: -18`), `shadow.scale: 0.76`.
7. **J7 Impact Squash (`135ms`)**: `torso: {dy: +2.8, sx: 1.16, sy: 0.78, rot: -5}`, landing dust `fx`, `shadow.scale: 1.14`.
8. **J8 Elastic Rebound (`115ms`)**: `torso: {dy: -0.6, sx: 0.97, sy: 1.04, rot: +2}`.

### D. Attack (Melee Slash / Tongue Whip / Bite, `6–8` frames)
- **Asymmetric Timing is Mandatory**:
  - **Windup / Anticipation (`2` frames, `130–150ms` each)**: Pull body *away* from target (`+2px`), coil arm/jaw/sac.
  - **Strike / Smear (`1` ultra-fast frame, `65–80ms`)**: Lunge forward (`-2.5px`), add `"arc"` slash smear or `70%` `"line"` whip on `"layer": "before_outline"`.
  - **Impact Hold (`1` frame, `140–160ms`)**: `100%` extension + `"pixels"` hit sparks on `"layer": "after_outline"`. Give the eye time to register the hit!
  - **Snap Recovery & Settle (`2–3` frames, `85–150ms`)**: Retract weapon/tongue, follow-through squash/gulp, return to neutral.
