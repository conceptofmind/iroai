import struct
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
               [0.2119034982, 0.6806995451, 0.1073969566],
               [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
               [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])
M1I, M2I = np.linalg.inv(M1), np.linalg.inv(M2)


def to_lab(rgb):
    c = np.asarray(rgb, float) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return np.cbrt(c @ M1.T) @ M2.T


def lin(L, z):
    return (np.array([L, z.real, z.imag]) @ M2I.T) ** 3 @ M1I.T


def to_rgb(L, z):
    c = np.clip(lin(L, z), 0, 1)
    c = np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
    return tuple(int(v) for v in np.round(c * 255))


def hue(z):
    return np.angle(z, deg=True) % 360


def cmax(L, h):
    u, lo, hi = np.exp(1j * np.radians(h)), 0.0, 0.5
    for _ in range(24):
        m = (lo + hi) / 2
        c = lin(L, m * u)
        lo, hi = (m, hi) if c.min() >= -1e-6 and c.max() <= 1 + 1e-6 else (lo, m)
    return lo


def ramp(L, z, n, light, shadow, shift, tint, lo, hi):
    h = hue(z)
    rel = abs(z) / max(cmax(L, h), 1e-9)
    lo, hi = min(lo, L / 2), max(hi, (L + 1) / 2)
    b = int(np.clip(round((L - lo) / (hi - lo) * (n - 1)), 1, n - 2))
    out = []
    for i in range(n):
        up = i > b
        s = (i - b) / (n - 1 - b) if up else (b - i) / b
        t, deg, sat = (light, shift[0], 0.5) if up else (shadow, shift[1], 0.86)
        d = (t - h + 180) % 360 - 180
        hs = h + np.sign(d) * min(abs(d), deg * s)
        e = 1 - (1 - s) ** 1.3
        Ls = L + (hi - L) * e if up else L - (L - lo) * e
        c = rel * (1 + (sat - rel) * s) * cmax(Ls, hs)
        zs = c * np.exp(1j * np.radians(hs)) + tint * (1 - rel) * s * np.exp(1j * np.radians(t))
        out.append(to_rgb(Ls, min(abs(zs), cmax(Ls, hue(zs))) * np.exp(1j * np.angle(zs))))
    return out, b


def merge(ramps, tol, fixed):
    cols = [c for r in ramps for c in r]
    n, lab = len(ramps[0]), to_lab(np.array(cols))
    D = np.linalg.norm(lab[:, None] - lab[None], axis=-1)
    rep, grp = list(range(len(cols))), {i: {i} for i in range(len(cols))}
    pairs = sorted((D[i, j], i, j) for i in range(len(cols)) for j in range(i) if i // n != j // n and D[i, j] < tol)
    for _, i, j in pairs:
        a, b = rep[i], rep[j]
        if a == b or (a in fixed and b in fixed) or {m // n for m in grp[a]} & {m // n for m in grp[b]}:
            continue
        g = grp[a] | grp[b]
        for r in [x for x in (a, b) if x in fixed] or sorted((a, b), key=lambda x: max(D[x, m] for m in g)):
            if max(D[r, m] for m in g) <= tol and all(
                    (m % n == 0 or lab[rep[m - 1], 0] < lab[r, 0]) and
                    (m % n == n - 1 or lab[rep[m + 1], 0] > lab[r, 0]) for m in g):
                for m in g:
                    rep[m] = r
                del grp[a], grp[b]
                grp[r] = g
                break
    return [[cols[rep[k * n + j]] for j in range(n)] for k in range(len(ramps))]


def extract(path, k):
    im = Image.open(path).convert('RGBA')
    im.thumbnail((256, 256), Image.Resampling.NEAREST)
    px = np.asarray(im).reshape(-1, 4)
    rgb, w = np.unique(px[px[:, 3] > 127, :3], axis=0, return_counts=True)
    if not len(rgb):
        raise ValueError('no opaque pixels in image')
    lab = to_lab(rgb)
    ab = lab[:, 1] + 1j * lab[:, 2]
    rng = np.random.default_rng(0)
    c = ab[[w.argmax()]]
    while len(c) < k:
        d = np.abs(ab[:, None] - c).min(1)
        if d.max() < 0.02:
            break
        c = np.append(c, rng.choice(ab, p=d ** 2 * w / (d ** 2 * w).sum()))
    for _ in range(50):
        lbl = np.abs(ab[:, None] - c).argmin(1)
        c = np.array([np.average(ab[lbl == j], weights=w[lbl == j]) if (lbl == j).any() else c[j]
                      for j in range(len(c))])
    lbl = np.abs(ab[:, None] - c).argmin(1)
    bases = [(np.average(lab[lbl == j, 0], weights=w[lbl == j]), c[j]) for j in range(len(c)) if (lbl == j).any()]
    return sorted(bases, key=lambda b: (abs(b[1]) > 0.03, hue(b[1])))


def save_ase(path, ramps, pal, name):
    h, w = len(ramps), len(ramps[0])
    chunk = lambda t, d: struct.pack('<IH', len(d) + 6, t) + d
    frame = b''.join([
        chunk(0x2007, struct.pack('<HHI8x', 1, 0, 0)),
        chunk(0x2019, struct.pack('<III8x', len(pal), 0, len(pal) - 1) +
              b''.join(struct.pack('<H4BH', 1, *c, 255, len(x)) + x.encode() for x, c in pal)),
        chunk(0x2004, struct.pack('<6HB3xH', 3, 0, 0, 0, 0, 0, 255, len(name)) + name),
        chunk(0x2005, struct.pack('<HhhBHh5x2H', 0, 0, 0, 255, 2, 0, w, h) +
              zlib.compress(bytes(v for row in ramps for c in row for v in (*c, 255))))])
    frame = struct.pack('<IHHH2xI', 16 + len(frame), 0xF1FA, 4, 100, 4) + frame
    Path(path).write_bytes(struct.pack('<IHHHHHIHIIB3xHBBhhHH84x', 128 + len(frame), 0xA5E0, 1, w, h, 32, 1,
                                       100, 0, 0, 0, len(pal), 1, 1, 0, 0, 16, 16) + frame)


def save(ramps, out, scale):
    arr = np.array(ramps, np.uint8)
    Image.fromarray(arr).resize((arr.shape[1] * scale, arr.shape[0] * scale), Image.Resampling.NEAREST).save(f'{out}.png')
    hexes = [[f'{r:02x}{g:02x}{b:02x}' for r, g, b in row] for row in ramps]
    uniq = dict.fromkeys((h, c) for row, hr in zip(ramps, hexes) for c, h in zip(row, hr))
    Path(f'{out}.hex').write_text(''.join(h + '\n' for h, _ in uniq))
    Path(f'{out}.gpl').write_text(f'GIMP Palette\nName: {Path(out).stem}\nColumns: {arr.shape[1]}\n#\n' +
                                  ''.join(f'{r:3d} {g:3d} {b:3d}\t{h}\n' for h, (r, g, b) in uniq))
    save_ase(f'{out}.aseprite', ramps, list(uniq), Path(out).stem.encode())
    tty = sys.stdout.isatty()
    for row, hr in zip(ramps, hexes):
        print(' '.join((f'\x1b[48;2;{r};{g};{b}m  \x1b[0m' if tty else '') + h for (r, g, b), h in zip(row, hr)))
    print(f'{len(uniq)} colors')