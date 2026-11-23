Generate hue-shifted pixel-art color ramps from hex colors or a reference image. Based on color theory from Color and Light by James Gurney.

Installation:
```bash
uv pip install hueshift-pixel
```

Usage:
```bash
uv run hueshift 3a7bd5 e0533a [options]
uv run hueshift input.png [options]
```

Options (defaults shown):
- `-n 9` shades per ramp (3–16)
- `-k 6` ramps to extract from an image
- `--shift mid` hue shift: `none`, `mid`, `strong`, or `LIGHT,DARK` degrees
- `--light ffd700` / `--shadow 2a0c42` colors highlights and shadows shift toward
- `--merge 0.04` make similar colors in different ramps identical (off by default)
- `--range 0.2 0.96` lightness range (`1` = pure white top)
- `--tint 0.03` warm/cool cast on grays
- `-o palette` writes `palette.png`, `.gpl`, `.hex`, `.aseprite`
- `--scale 16` swatch size in the PNG