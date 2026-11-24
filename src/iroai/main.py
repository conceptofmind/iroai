import argparse
import os
import re
from pathlib import Path

from .config import SHIFTS
from .core import extract, hue, merge, ramp, save, to_lab


def shift_arg(s):
    if s in SHIFTS:
        return SHIFTS[s]
    v = [float(x) for x in s.split(',')]
    return v[0], v[-1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('src', nargs='+', help='hex colors (e.g. 3a7bd5 e0533a) or one reference image')
    p.add_argument('-n', '--steps', type=int, default=9, help='shades per ramp, 3-16')
    p.add_argument('-k', '--ramps', type=int, default=6, help='ramps to extract from an image')
    p.add_argument('--shift', type=shift_arg, default='mid',
                   help='none | mid | strong | degrees as LIGHT,DARK (e.g. 80,40)')
    p.add_argument('--light', default='ffd700', help='color highlights shift toward (sunlight)')
    p.add_argument('--shadow', default='2a0c42', help='color shadows shift toward (sky-lit shadow)')
    p.add_argument('--tint', type=float, default=0.03, help='light/shadow cast on grays (0 = none)')
    p.add_argument('--range', type=float, nargs=2, default=(0.2, 0.96), metavar=('DARK', 'LIGHT'),
                   help='lightness range 0-1; 1 = pure white top')
    p.add_argument('--merge', type=float, default=0, metavar='TOL',
                   help='make similar colors in different ramps identical (OKLab distance, e.g. 0.04)')
    p.add_argument('-o', '--out', default='palette',
                   help='output path, e.g. forest, out/forest or out/ (folders are created); writes .png .gpl .hex .aseprite')
    p.add_argument('--scale', type=int, default=16, help='swatch size in the PNG')
    a = p.parse_args()
    image = len(a.src) == 1 and Path(a.src[0]).is_file()
    if not 3 <= a.steps <= 16:
        p.error('--steps must be 3-16')
    for s in [a.light, a.shadow] + ([] if image else a.src):
        if not re.fullmatch(r'#?[0-9a-fA-F]{6}', s):
            p.error(f'invalid hex color or missing image: {s}')
    lab = lambda s: to_lab([int(s.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)])
    try:
        bases = extract(a.src[0], a.ramps) if image else [(v[0], complex(*v[1:])) for v in map(lab, a.src)]
    except (OSError, ValueError) as e:
        p.error(str(e))
    lh, sh = (hue(complex(*lab(s)[1:])) for s in (a.light, a.shadow))
    ramps, bs = zip(*(ramp(L, z, a.steps, lh, sh, a.shift, a.tint, *a.range) for L, z in bases))
    if a.merge > 0:
        ramps = merge(ramps, a.merge, {k * a.steps + b for k, b in enumerate(bs)})
    save(ramps, str(Path(a.out, 'palette')) if a.out.endswith(('/', os.sep)) else a.out, a.scale)


if __name__ == '__main__':
    main()