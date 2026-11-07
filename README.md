# Game Art Plugin (`game-art`)

Plugin para **Antigravity** enfocado en la creación y animación de *pixel art* y *sprites* listos para motores de videojuegos (Unity, Godot, Aseprite, GameMaker) a **cualquier resolución personalizada (`W × H`)**.

## Contenido del Plugin

### 1. Skill: `generate-pixelart`
Ubicada en [`skills/generate-pixelart/`](./skills/generate-pixelart/SKILL.md). Opera en tres modos según lo que pida el usuario:

1. **Entrega de Prompt para IA (Modo por defecto)**:
   - Si pides un *pixel art* sin adjuntar imagen y sin pedir generación directa, entrega un *prompt* técnico optimizado para la resolución exacta `W × H` (densidad de detalle, perspectiva isométrica/`3/4`/lateral, paleta y fondo *chroma-key* sin sangrado).
2. **Conversión y Pulido de Imagen Base**:
   - `scripts/pixelize_sprite.py` recorta el fondo *chroma-key* con *de-spill*, encaja proporcionalmente al tamaño exacto `W × H`, aplica muestreo *medoid* (bordes nítidos sin difuminado), cuantiza la paleta y exporta PNGs `1x` + vista previa *Nearest Neighbor*.
3. **Generación Directa (Bajo petición explícita)**:
   - Ejecuta el flujo completo (híbrido o matriz píxel a píxel con `scripts/render_matrix.py`), incluyendo revisión visual, *spritesheets* y visor HTML interactivo.

### 2. Skill: `animate-pixelart`
Ubicada en [`skills/animate-pixelart/`](./skills/animate-pixelart/SKILL.md). Anima cualquier personaje o criatura *pixel art* a partir de **un único sprite base estático** (`PNG` o `_spec.json`) manteniendo coherencia píxel a píxel sin *flickering*:

- **Inspección de coordenadas (`scripts/png_to_spec.py`)**: Decodifica cualquier PNG `8-bit` sin dependencias externas y genera un mapa ASCII numerado `(x, y)` para ubicar piezas y pivotes con precisión exacta.
- **Motor Cutout Rig (`scripts/rig_animator.py`)**:
  - Descompone el sprite en capas anatómicas con solapamiento en articulaciones, eliminando el contorno exterior pero preservando los detalles internos (ojos, boca, remaches).
  - Pre-escala cada pieza `4×` mediante dos pasadas de **EPX / Scale2x** y aplica rotación **RotSprite**, **Squash & Stretch**, intercambio de piezas (*sprite-swap*) y primitivas procedurales (lenguas, tajos *smear*, polvo, impactos).
  - **Auto-Contorno Selectivo Adaptativo por Tono (*Sel-Out*)**: Normaliza el tono de los píxeles vecinos por luminancia (`selout_auto` / `selout_palette`) para generar bordes coloreados coherentes (verde bosque en piel verde, burdeos en lengua rosa, azul noche en armaduras) evitando bordes negro puro accidentales, además de soportar modo `solid` (tinta cómic) o `none` (*lineless*).
  - Exporta tiras `1x`, *spritesheets* multifila (con espejo horizontal opcional `--mirror-x` para diagonales isométricas `SW -> SE` / `NW -> NE`), hoja de QA visual y visor HTML interactivo con rayos X de capas y pivotes.

## Estructura

```text
game-art/
├── plugin.json
├── README.md
├── assets/
│   └── logo.png
└── skills/
    ├── generate-pixelart/
    │   ├── SKILL.md
    │   ├── references/
    │   │   └── prompt-templates.md
    │   └── scripts/
    │       ├── pixelize_sprite.py
    │       └── render_matrix.py
    └── animate-pixelart/
        ├── SKILL.md
        ├── references/
        │   └── animation-recipes.md
        └── scripts/
            ├── png_to_spec.py
            └── rig_animator.py
```

## Instalación

### Global (en tu máquina)
Clona este repositorio dentro de `~/.gemini/config/plugins/game-art`:

```bash
git clone https://github.com/pbesora/game-art.git ~/.gemini/config/plugins/game-art
```

### Por proyecto (Workspace)
Clónalo o añádelo como submódulo en `.agents/plugins/game-art` en la raíz de tu proyecto.
