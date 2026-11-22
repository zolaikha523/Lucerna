"""Colour science for the presentation layer: sRGB ↔ OKLab/OKLCH, WCAG contrast, perceptual distance, gamut mapping.

Pure functions with no dependencies, so palettes are deterministic and testable.
"""
from __future__ import annotations

import math


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_oklab(rgb) -> tuple[float, float, float]:
    r, g, b = (_lin(c) for c in rgb)
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(x) ** (1 / 3), x) for x in (l_, m_, s_))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_rgb_unclipped(lab) -> tuple[float, float, float]:
    L, a, b = lab
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bb = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return tuple(_gam(x) if x >= 0 else -_gam(-x) for x in (r, g, bb))  # type: ignore[return-value]


def oklch(hex_: str) -> tuple[float, float, float]:
    L, a, b = rgb_to_oklab(hex_to_rgb(hex_))
    return L, math.hypot(a, b), (math.degrees(math.atan2(b, a)) % 360)


def from_oklch(L: float, C: float, h: float) -> str:
    """OKLCH → hex, reducing chroma (not lightness or hue) until the colour fits in sRGB."""
    L = max(0.0, min(1.0, L))
    lo, hi = 0.0, max(0.0, C)
    def fits(c):
        rgb = oklab_to_rgb_unclipped((L, c * math.cos(math.radians(h)), c * math.sin(math.radians(h))))
        return all(-1e-4 <= x <= 1 + 1e-4 for x in rgb), rgb
    ok, rgb = fits(hi)
    if not ok:
        for _ in range(24):
            mid = (lo + hi) / 2
            if fits(mid)[0]:
                lo = mid
            else:
                hi = mid
        rgb = fits(lo)[1]
    return rgb_to_hex(tuple(max(0.0, min(1.0, x)) for x in rgb))


def luminance(hex_: str) -> float:
    r, g, b = (_lin(c) for c in hex_to_rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def delta_e(a: str, b: str) -> float:
    """Perceptual distance in OKLab × 100 (≈ 2 is just noticeable; 8+ is clearly different)."""
    x, y = rgb_to_oklab(hex_to_rgb(a)), rgb_to_oklab(hex_to_rgb(b))
    return 100 * math.dist(x, y)


def hue_gap(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def rgba(hex_: str, alpha: float) -> str:
    r, g, b = (round(c * 255) for c in hex_to_rgb(hex_))
    return f"rgba({r},{g},{b},{alpha:.3f})"


def mix(a: str, b: str, t: float) -> str:
    x, y = rgb_to_oklab(hex_to_rgb(a)), rgb_to_oklab(hex_to_rgb(b))
    return rgb_to_hex(tuple(max(0.0, min(1.0, v)) for v in oklab_to_rgb_unclipped(tuple(p + (q - p) * t for p, q in zip(x, y)))))


def with_lightness_for_contrast(fg: str, bg: str, target: float, step: float = 0.02) -> str:
    """Move fg's OKLCH lightness away from bg until the WCAG contrast reaches target (hue and chroma kept)."""
    L, C, h = oklch(fg)
    darker = luminance(bg) > 0.18
    for _ in range(60):
        if contrast(fg, bg) >= target:
            return fg
        L = L - step if darker else L + step
        if not 0 <= L <= 1:
            break
        fg = from_oklch(L, C, h)
    return "#000000" if darker else "#FFFFFF"


# ---- simulated colour-vision deficiency (Viénot/Brettel matrices on linear RGB), for palette checks
_CVD = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def simulate(hex_: str, kind: str) -> str:
    r, g, b = (_lin(c) for c in hex_to_rgb(hex_))
    m = _CVD[kind]
    out = tuple(max(0.0, min(1.0, m[i][0] * r + m[i][1] * g + m[i][2] * b)) for i in range(3))
    return rgb_to_hex(tuple(_gam(c) for c in out))


def min_cvd_distance(colors: list[str]) -> float:
    """Smallest OKLab distance between neighbouring palette colours under any simulated deficiency."""
    best = 999.0
    for kind in _CVD:
        sim = [simulate(c, kind) for c in colors]
        for i in range(len(sim) - 1):
            best = min(best, delta_e(sim[i], sim[i + 1]))
    return best
