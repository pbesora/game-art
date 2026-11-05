# Game Art Plugin (`game-art`)

Plugin para **Antigravity** enfocado en la creación de *pixel art* y *sprites* listos para motores de videojuegos (Unity, Godot, Aseprite, GameMaker) a **cualquier resolución personalizada (`W × H`)**.

## Contenido del Plugin

### Skill: `generate-pixelart`
Ubicada en [`skills/generate-pixelart/`](./skills/generate-pixelart/SKILL.md). Opera en tres modos según lo que pida el usuario:

1. **Entrega de Prompt para IA (Modo por defecto)**:
   - Si pides un *pixel art* sin adjuntar imagen y sin pedir generación directa, la skill **no genera la imagen por su cuenta**: te entrega un *prompt* técnico optimizado para la resolución exacta `W × H` (densidad de detalle, perspectiva isométrica/`3/4`/lateral, paleta y fondo *chroma-key* sin sangrado) para que generes la base en tu herramienta de IA preferida.
2. **Conversión y Pulido de Imagen Base**:
   - Cuando entregas tu imagen generada, `scripts/pixelize_sprite.py` recorta el fondo *chroma-key* con *de-spill*, encaja proporcionalmente al tamaño exacto `W × H`, aplica muestreo *medoid* (bordes nítidos sin difuminado), cuantiza la paleta (`N` colores o presets como `gb`, `pico8`, `endesga16`) y exporta PNGs `1x` + vista previa *Nearest Neighbor*.
3. **Generación Directa (Bajo petición explícita)**:
   - Si indicas explícitamente que genere la imagen/sprite directamente, ejecuta el flujo completo (híbrido o matriz píxel a píxel con `scripts/render_matrix.py`), incluyendo revisión visual, *spritesheets* multicapa y visor HTML interactivo.

## Estructura

```text
game-art/
├── plugin.json
├── README.md
├── assets/
│   └── logo.png
└── skills/
    └── generate-pixelart/
        ├── SKILL.md
        ├── references/
        │   └── prompt-templates.md
        └── scripts/
            ├── pixelize_sprite.py
            └── render_matrix.py
```

## Instalación

### Global (en tu máquina)
Clona este repositorio dentro de `~/.gemini/config/plugins/game-art`:

```bash
git clone https://github.com/pbesora/game-art.git ~/.gemini/config/plugins/game-art
```

### Por proyecto (Workspace)
Clónalo o añádelo como submódulo en `.agents/plugins/game-art` en la raíz de tu proyecto.
