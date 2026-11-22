"""Build the Lucerna brand assets (SVG) with text converted to outlines, so they render identically everywhere.

    python tools/build_brand.py            # writes assets/brand/*.svg
    node tools/rasterize_brand.js          # renders the PNG versions (uses the pre-installed Chromium)

The symbol: a rounded tile holding a white "L" whose foot opens into a rising, widening beam of light that points to
a warm point of light: the evidence leads to the decision. Lucerna is Latin for lamp: a single point of evidence lighting the way to a decision.
Wordmark: Inter Display SemiBold (SIL Open Font License), converted to paths.
"""
from __future__ import annotations

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "brand"
FONT_DIRS = [Path("/usr/share/fonts/opentype/inter"), ROOT / "assets" / "fonts"]

NAVY = "#0A1430"
AZURE = "#2F6BFF"
TEAL = "#16C2B0"
SPARK = "#FFC56B"
SLATE = "#5B6B85"
MIST = "#9DB0CC"


def _font(name: str) -> TTFont:
    for d in FONT_DIRS:
        if (d / name).exists():
            return TTFont(str(d / name))
    raise FileNotFoundError(f"{name} not found; install the Inter font family (SIL OFL)")


def text_path(text: str, font_file: str, size: float, x: float, y: float, tracking: float = 0.0) -> tuple[str, float]:
    """SVG path data for `text` with its baseline at y; returns (path, advance width)."""
    f = _font(font_file)
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    upm = f["head"].unitsPerEm
    scale = size / upm
    hmtx = f["hmtx"]
    parts, cx = [], 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        pen = SVGPathPen(gs)
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x + cx, y))
        gs[g].draw(tpen)
        parts.append(pen.getCommands())
        cx += hmtx[g][0] * scale + tracking
    return " ".join(parts), cx - tracking


def symbol_body(size: float = 64, x: float = 0, y: float = 0, gid: str = "lc") -> str:
    s = size / 64
    return f"""<g transform="translate({x} {y}) scale({s})">
  <defs>
    <linearGradient id="{gid}-tile" x1="6" y1="4" x2="60" y2="62" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{AZURE}"/><stop offset="1" stop-color="{TEAL}"/>
    </linearGradient>
    <linearGradient id="{gid}-beam" x1="18" y1="40" x2="45" y2="40" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#FFFFFF" stop-opacity=".45"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#{gid}-tile)"/>
  <rect x="2.5" y="2.5" width="59" height="59" rx="15.5" fill="none" stroke="#FFFFFF" stroke-opacity=".18"/>
  <path d="M14 18.5a4.5 4.5 0 0 1 9 0V40.2L41.6 33.4A2.2 2.2 0 0 1 44.6 35.5V47.8A2.2 2.2 0 0 1 42.4 50H18.5A4.5 4.5 0 0 1 14 45.5Z" fill="url(#{gid}-beam)"/>
  <circle cx="46.5" cy="19.5" r="5.5" fill="{SPARK}"/>
</g>"""


def svg(w: float, h: float, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.1f} {h:.1f}" role="img" aria-label="{title}">'
            f"<title>{title}</title>{body}</svg>\n")


def horizontal(word: str, tag: str, gid: str) -> str:
    sym = symbol_body(64, 0, 0, gid)
    wp, ww = text_path("LUCERNA", "InterDisplay-SemiBold.otf", 31, 82, 37, tracking=3.2)
    tp, tw = text_path("FROM DATA TO DECISIONS", "Inter-Medium.otf", 9.2, 83, 54, tracking=1.55)
    w = 82 + max(ww, tw) + 4
    return svg(w, 64, sym + f'<path d="{wp}" fill="{word}"/><path d="{tp}" fill="{tag}"/>', "Lucerna — From Data to Decisions")


def stacked(word: str, tag: str, gid: str) -> str:
    wp, ww = text_path("LUCERNA", "InterDisplay-SemiBold.otf", 40, 0, 0, tracking=4.4)
    tp, tw = text_path("FROM DATA TO DECISIONS", "Inter-Medium.otf", 11, 0, 0, tracking=2.1)
    w = max(ww, tw, 104) + 8
    wpath, _ = text_path("LUCERNA", "InterDisplay-SemiBold.otf", 40, (w - ww) / 2, 150, tracking=4.4)
    tpath, _ = text_path("FROM DATA TO DECISIONS", "Inter-Medium.otf", 11, (w - tw) / 2, 174, tracking=2.1)
    sym = symbol_body(96, (w - 96) / 2, 0, gid)
    return svg(w, 182, sym + f'<path d="{wpath}" fill="{word}"/><path d="{tpath}" fill="{tag}"/>', "Lucerna — From Data to Decisions")


def mono(color: str) -> str:
    body = f"""<g fill="{color}"><path fill-rule="evenodd" d="M18 2h28a16 16 0 0 1 16 16v28a16 16 0 0 1-16 16H18A16 16 0 0 1 2 46V18A16 16 0 0 1 18 2Z
      M14 18.5a4.5 4.5 0 0 1 9 0V40.2L41.6 33.4A2.2 2.2 0 0 1 44.6 35.5V47.8A2.2 2.2 0 0 1 42.4 50H18.5A4.5 4.5 0 0 1 14 45.5Z
      M46.5 14a5.5 5.5 0 1 0 0 11a5.5 5.5 0 1 0 0-11Z"/></g>"""
    wp, ww = text_path("LUCERNA", "InterDisplay-SemiBold.otf", 31, 82, 37, tracking=3.2)
    tp, tw = text_path("FROM DATA TO DECISIONS", "Inter-Medium.otf", 9.2, 83, 54, tracking=1.55)
    return svg(82 + max(ww, tw) + 4, 64, body + f'<path d="{wp}" fill="{color}"/><path d="{tp}" fill="{color}"/>', "Lucerna")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "lucerna-symbol.svg": svg(64, 64, symbol_body(64, 0, 0, "s"), "Lucerna"),
        "favicon.svg": svg(64, 64, symbol_body(64, 0, 0, "f"), "Lucerna"),
        "lucerna-logo-horizontal-light.svg": horizontal(NAVY, SLATE, "hl"),   # for light backgrounds
        "lucerna-logo-horizontal-dark.svg": horizontal("#FFFFFF", MIST, "hd"),  # for dark backgrounds
        "lucerna-logo-stacked-light.svg": stacked(NAVY, SLATE, "sl"),
        "lucerna-logo-stacked-dark.svg": stacked("#FFFFFF", MIST, "sd"),
        "lucerna-logo-monochrome.svg": mono(NAVY),
        "lucerna-logo-monochrome-white.svg": mono("#FFFFFF"),
    }
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
