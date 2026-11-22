"""Deterministic brand-colour extraction from an uploaded logo (PNG, JPEG or SVG). No AI, no guessing from names.

Transparent pixels, near-white and near-black pixels and greys are set aside. The remaining pixels are grouped by
perceptual hue and lightness, and each group's share of the logo becomes its weight. SVG logos are read as text.
Colours are taken from fill, stroke and stop-color, each weighted by the size of the shape that uses it.
"""
from __future__ import annotations

import io
import math
import re
from collections import defaultdict
from functools import lru_cache

from . import color as C

MAX_BYTES = 2_000_000
NAMED = {"red": "#FF0000", "green": "#008000", "blue": "#0000FF", "orange": "#FFA500", "yellow": "#FFFF00", "purple": "#800080",
         "navy": "#000080", "teal": "#008080", "black": "#000000", "white": "#FFFFFF", "gray": "#808080", "grey": "#808080",
         "maroon": "#800000", "olive": "#808000", "lime": "#00FF00", "aqua": "#00FFFF", "fuchsia": "#FF00FF", "silver": "#C0C0C0"}


class BrandError(ValueError):
    pass


def kind_of(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    head = data[:2048].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head:
        return "svg"
    raise BrandError("Use a PNG, JPEG or SVG image.")


def _classify(samples: list[tuple[str, float]]) -> dict:
    """samples: (hex, weight). Returns chromatic swatches (merged, sorted by share), neutral share and character."""
    total = sum(w for _, w in samples) or 1.0
    chroma, neutral_w, dark_w, light_w = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]), 0.0, 0.0, 0.0
    for hx, w in samples:
        L, Cc, h = C.oklch(hx)
        if Cc < 0.035:
            neutral_w += w
            if L < 0.25:
                dark_w += w
            elif L > 0.93:
                light_w += w
            continue
        key = (int(h // 12), int(L * 4))
        lab = C.rgb_to_oklab(C.hex_to_rgb(hx))
        acc = chroma[key]
        acc[0] += w
        for i in range(3):
            acc[i + 1] += lab[i] * w
    groups = []
    for w, L, a, b in chroma.values():
        hx = C.rgb_to_hex(tuple(max(0.0, min(1.0, x)) for x in C.oklab_to_rgb_unclipped((L / w, a / w, b / w))))
        groups.append([hx, w])
    groups.sort(key=lambda g: -g[1])
    merged: list[list] = []
    for hx, w in groups:
        for m in merged:
            if C.delta_e(hx, m[0]) < 7:
                m[1] += w
                break
        else:
            merged.append([hx, w])
    chromatic_total = sum(w for _, w in merged) or 1.0
    swatches = [{"hex": hx, "share": round(w / total, 4), "chromatic_share": round(w / chromatic_total, 4)} for hx, w in merged if w / total >= 0.004][:8]
    for s in swatches:
        L, Cc, h = C.oklch(s["hex"])
        s.update(L=round(L, 3), C=round(Cc, 3), h=round(h, 1))
    return {"swatches": swatches, "neutral_share": round(neutral_w / total, 3), "dark_share": round(dark_w / total, 3),
            "light_share": round(light_w / total, 3), "character": character(swatches, neutral_w / total)}


def character(swatches: list[dict], neutral_share: float) -> dict:
    """Plain description of the logo's visual character, used for design choices (never for meaning)."""
    if not swatches:
        return {"tone": "monochrome", "temperature": "neutral", "energy": "calm", "label": "Monochrome"}
    top = swatches[:3]
    w = sum(s["chromatic_share"] for s in top) or 1
    mean_c = sum(s["C"] * s["chromatic_share"] for s in top) / w
    warm = sum(s["chromatic_share"] for s in top if s["h"] < 100 or s["h"] > 330) / w
    temperature = "warm" if warm > 0.6 else ("cool" if warm < 0.3 else "balanced")
    energy = "vivid" if mean_c > 0.15 else ("muted" if mean_c < 0.08 else "moderate")
    spread = max((C.hue_gap(a["h"], b["h"]) for a in top for b in top), default=0)
    tone = "multicolour" if len(top) >= 2 and spread > 60 else "single-hue"
    label = f"{energy.capitalize()} {temperature}, {tone}"
    return {"tone": tone, "temperature": temperature, "energy": energy, "label": label}


@lru_cache(maxsize=64)
def _raster(data: bytes) -> dict:
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise BrandError("The image could not be read.") from exc
    if img.width * img.height > 40_000_000:
        raise BrandError("The image is too large.")
    img = img.convert("RGBA")
    img.thumbnail((128, 128))
    counts: dict[str, float] = defaultdict(float)
    for r, g, b, a in (img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()):
        if a < 128:
            continue
        # light quantisation keeps antialiasing from creating thousands of near-identical colours
        counts["#%02X%02X%02X" % (r // 8 * 8, g // 8 * 8, b // 8 * 8)] += 1
    if not counts:
        raise BrandError("The image is fully transparent.")
    return _classify(list(counts.items()))


_COLOR_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)")


def _norm_color(tok: str) -> str | None:
    tok = tok.strip().lower()
    if tok in NAMED:
        return NAMED[tok]
    m = _COLOR_RE.search(tok)
    if not m:
        return None
    if m.group(1):
        return "#" + (m.group(1) if len(m.group(1)) == 6 else "".join(c * 2 for c in m.group(1))).upper()
    return "#%02X%02X%02X" % tuple(min(255, int(x)) for x in m.groups()[1:])


@lru_cache(maxsize=64)
def _svg(data: bytes) -> dict:
    from .svg_safe import parse
    root = parse(data)
    samples: list[tuple[str, float]] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        props = {k.split("}")[-1]: v for k, v in el.attrib.items()}
        for decl in (props.get("style") or "").split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                props[k.strip()] = v.strip()
        size = len(props.get("d", "")) or 60
        if tag in ("rect", "circle", "ellipse"):
            try:
                if tag == "rect":
                    size = float(re.sub(r"[^\d.]", "", props.get("width", "60")) or 60) * float(re.sub(r"[^\d.]", "", props.get("height", "60")) or 60) / 20
                else:
                    r = float(re.sub(r"[^\d.]", "", props.get("r", props.get("rx", "20"))) or 20)
                    size = math.pi * r * r / 20
            except ValueError:
                size = 60
        for k in ("fill", "stroke", "stop-color"):
            c = _norm_color(props.get(k, "")) if props.get(k) else None
            if c:
                samples.append((c, size * (0.35 if k == "stroke" else 1.0)))
    for m in re.finditer(rb"(?:fill|stop-color|stroke)\s*:\s*([^;\"'}]+)", data):
        c = _norm_color(m.group(1).decode("latin-1"))
        if c:
            samples.append((c, 40))
    if not samples:
        samples.append(("#000000", 1))   # SVG default fill is black
    return _classify(samples)


def extract(data: bytes) -> dict:
    """Brand colours found in a logo. Raises BrandError for unreadable or unsupported files."""
    if not data or len(data) > MAX_BYTES:
        raise BrandError("The logo must be smaller than 2 MB.")
    k = kind_of(data)
    out = _svg(bytes(data)) if k == "svg" else _raster(bytes(data))
    return {**out, "format": k}
