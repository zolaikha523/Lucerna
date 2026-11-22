"""Brand-aware dashboard design system, derived deterministically from a logo's colours (or a theme's defaults).

Input: extracted swatches + visualization theme + optional custom colours + background choice.
Output: a complete token set: page background, glass surfaces, text, borders, UI accent, status colours, and
categorical, sequential and diverging chart palettes. Contrast and colour-vision checks are recorded with the result.

Design judgement encoded here (so it is reviewable):
- Logo colours become the *identity* (header, tabs, highlights, first chart series), not the background.
  Backgrounds are deep or near-white neutrals tinted toward the brand hue, so charts stay readable.
- Chart colours keep each brand hue but are moved into a lightness/chroma band that reads well on the chosen
  background. Remaining series use hues spaced as far as possible from the brand hues, alternating light and dark
  steps so neighbours stay distinguishable under colour-vision deficiency.
- A single-colour logo gets an analogous secondary and a split-complementary accent; a monochrome logo gets a
  restrained slate-and-blue system rather than invented colours.
"""
from __future__ import annotations

from functools import lru_cache

from . import color as C

THEME_DEFAULTS = {   # used when no logo is supplied: (seed colours, default background)
    "corporate": (("#2563EB", "#0EA5A4", "#7C5CFF"), "light"),
    "executive": (("#2F7BFF", "#19C6B4", "#8B6CFF"), "navy"),
    "vibrant": (("#7C4DFF", "#14B8A6", "#F59E0B"), "aurora"),
    "minimal": (("#334155", "#3B6EA8", "#B45309"), "paper"),
}
BACKGROUNDS = {
    "auto": "Theme default",
    "navy": "Executive dark navy",
    "deepsea": "Deep blue and teal",
    "aurora": "Violet and blue",
    "brand": "Subtle branded (from the logo)",
    "light": "Premium light neutral",
    "paper": "Quiet paper (print-like)",
    "image": "Your background image",
}
LIGHT_BACKGROUNDS = {"light", "paper"}


def _band(mode: str) -> tuple[float, float, float, float]:
    """(L low, L high, C low, C high) for chart marks on this mode."""
    return (0.62, 0.87, 0.10, 0.19) if mode == "dark" else (0.40, 0.63, 0.10, 0.20)


def _fit(hex_: str, mode: str, L_pref: float | None = None) -> str:
    lo, hi, clo, chi = _band(mode)
    L, Cc, h = C.oklch(hex_)
    L = min(hi, max(lo, L if L_pref is None else L_pref))
    return C.from_oklch(L, min(chi, max(clo, Cc)), h)


def _pick_roles(sw: list[dict]) -> tuple[list[str], str]:
    """Primary, secondary and accent from the logo's chromatic swatches, with the rule that chose them."""
    if not sw:
        return [], "monochrome"
    primary = sw[0]
    rest = sw[1:]
    secondary = next((s for s in rest if C.hue_gap(s["h"], primary["h"]) >= 25 and s["chromatic_share"] >= 0.015), None)
    accent = next((s for s in rest if s is not secondary and min(C.hue_gap(s["h"], primary["h"]), C.hue_gap(s["h"], secondary["h"]) if secondary else 999) >= 40
                   and s["chromatic_share"] >= 0.01), None)
    if accent and not secondary:
        secondary, accent = accent, None
    roles = [primary["hex"]] + ([secondary["hex"]] if secondary else []) + ([accent["hex"]] if accent else [])
    rule = "three logo colours" if accent else ("two logo colours + derived accent" if secondary else "one logo colour + derived companions")
    return roles, rule


def _complete_roles(roles: list[str]) -> list[str]:
    L, Cc, h = C.oklch(roles[0])
    Cc = max(Cc, 0.12)
    L = min(0.72, max(0.55, L))           # derived colours sit mid-range, never muddy
    if len(roles) == 1:
        roles = roles + [C.from_oklch(min(0.8, L + 0.06), Cc * 0.9, (h + 32) % 360)]          # analogous
    if len(roles) == 2:
        h2 = C.oklch(roles[1])[2]
        cands = [(h + 150) % 360, (h + 210) % 360]
        acc_h = max(cands, key=lambda x: C.hue_gap(x, h2))                                     # split complement, away from secondary
        roles = roles + [C.from_oklch(L, Cc, acc_h)]
    return roles[:3]


def _categorical(roles: list[str], mode: str, n: int = 8) -> list[str]:
    lo, hi, clo, chi = _band(mode)
    steps = [(lo + hi) / 2 + 0.05, lo + 0.02, hi - 0.02, (lo + hi) / 2 - 0.03, hi, lo + 0.05, (lo + hi) / 2 + 0.01, lo]   # first series: saturated mid-tone
    out = [_fit(r, mode, steps[i]) for i, r in enumerate(roles)]
    hues = [C.oklch(c)[2] for c in out]
    while len(out) < n:
        cand = max(range(0, 360, 6), key=lambda x: min(C.hue_gap(x, y) for y in hues))
        i = len(out)
        out.append(C.from_oklch(steps[i % len(steps)], (clo + chi) / 2 + 0.02, cand))
        hues.append(cand)
    # neighbours must differ clearly for everyone: move a too-close colour to the nearest lightness in the band that
    # separates it from its neighbour (normal vision ΔE ≥ 14 and simulated CVD ΔE ≥ 8); keep hue and chroma.
    def ok(a: str, b: str) -> tuple[bool, float]:
        de, cvd = C.delta_e(a, b), C.min_cvd_distance([a, b])
        return de >= 14 and cvd >= 8, min(de / 14, cvd / 8)
    for i in range(1, len(out)):
        good, _ = ok(out[i - 1], out[i])
        if good:
            continue
        L0, Cc, h = C.oklch(out[i])
        cands = [lo + k * 0.01 for k in range(int(round((hi - lo) / 0.01)) + 1)]
        scored = []
        for L in cands:
            c = C.from_oklch(L, Cc, h)
            g, score = ok(out[i - 1], c)
            scored.append((not g, abs(L - L0) if g else -score, c))
        out[i] = min(scored)[2]
    return out


def _sequential(base: str, mode: str, n: int = 7) -> list[str]:
    _, Cc, h = C.oklch(base)
    Cc = max(0.08, min(0.2, Cc))
    if mode == "dark":
        return [C.from_oklch(0.30 + i * (0.56 / (n - 1)), 0.04 + (Cc - 0.04) * i / (n - 1), h) for i in range(n)]
    return [C.from_oklch(0.95 - i * (0.57 / (n - 1)), 0.02 + (Cc - 0.02) * i / (n - 1), h) for i in range(n)]


def _diverging(pos: str, neg: str, mode: str, n: int = 7) -> list[str]:
    mid = C.from_oklch(0.42 if mode == "dark" else 0.93, 0.005, 0)
    half = n // 2
    a = [C.mix(_fit(neg, mode), mid, i / half) for i in range(half)]
    b = [C.mix(mid, _fit(pos, mode), (i + 1) / half) for i in range(half)]
    return a + [mid] + b


@lru_cache(maxsize=128)
def _design(seed_key: tuple, mode: str, background: str, theme_key: str, character_label: str) -> dict:
    roles = list(seed_key)
    primary_raw = roles[0]
    Lp, Cp, hp = C.oklch(primary_raw)
    hs = C.oklch(roles[1])[2]
    cat = _categorical(roles, mode)
    if mode == "dark":
        bg = C.from_oklch(0.155, 0.03, hp)
        bg2 = C.from_oklch(0.205, 0.05, hs)
        solid = C.from_oklch(0.215, 0.032, hp)
        surface = C.rgba(C.from_oklch(0.27, 0.035, hp), 0.52)
        surface2 = C.rgba(C.from_oklch(0.31, 0.04, hp), 0.55)
        line = "rgba(255,255,255,.085)"
        ink, ink2, muted = C.from_oklch(0.97, 0.008, hp), C.from_oklch(0.84, 0.02, hp), C.from_oklch(0.70, 0.025, hp)
        grid = "rgba(255,255,255,.07)"
    else:
        bg = C.from_oklch(0.975, 0.007, hp)
        bg2 = C.from_oklch(0.955, 0.015, hs)
        solid = "#FFFFFF"
        surface = "rgba(255,255,255,.84)" if background != "paper" else "rgba(255,255,255,0)"
        surface2 = C.rgba(C.from_oklch(0.965, 0.01, hp), 0.9)
        line = C.from_oklch(0.90, 0.012, hp)
        ink, ink2, muted = C.from_oklch(0.23, 0.03, hp), C.from_oklch(0.40, 0.03, hp), C.from_oklch(0.53, 0.02, hp)
        grid = C.rgba(C.from_oklch(0.4, 0.02, hp), 0.09)
    ink = C.with_lightness_for_contrast(ink, solid, 7.0)
    ink2 = C.with_lightness_for_contrast(ink2, solid, 4.5)
    muted = C.with_lightness_for_contrast(muted, solid, 3.2)
    # UI accent: the brand's own primary, adjusted only as far as needed to be visible as a control (3:1)
    accent = C.with_lightness_for_contrast(primary_raw if Cp >= 0.06 else cat[0], solid, 3.0)
    accent_ink = "#FFFFFF" if C.contrast("#FFFFFF", accent) >= C.contrast("#0B1020", accent) else "#0B1020"
    second = _fit(roles[1], mode)
    third = _fit(roles[2], mode)
    status = {"good": C.with_lightness_for_contrast(C.from_oklch(0.62 if mode == "light" else 0.76, 0.15, 150), solid, 3.0),
              "warning": C.with_lightness_for_contrast(C.from_oklch(0.70 if mode == "light" else 0.82, 0.15, 75), solid, 3.0),
              "negative": C.with_lightness_for_contrast(C.from_oklch(0.58 if mode == "light" else 0.72, 0.17, 25), solid, 3.0)}
    neg_hue = C.oklch(roles[2])[2] if C.hue_gap(C.oklch(roles[2])[2], hp) >= 90 else (hp + 180) % 360
    seq = _sequential(primary_raw if Cp >= 0.06 else cat[0], mode)
    div = _diverging(cat[0], C.from_oklch(0.6, 0.15, neg_hue), mode)
    if mode == "dark":
        header = f"linear-gradient(120deg,{C.rgba(C.from_oklch(0.30, 0.09, hp), .92)} 0%,{C.rgba(C.from_oklch(0.25, 0.07, hs), .88)} 100%)"
    else:
        header = f"linear-gradient(120deg,{C.from_oklch(0.42, min(0.16, max(Cp, 0.09)), hp)} 0%,{C.from_oklch(0.47, 0.12, hs)} 100%)" if background != "paper" else solid
    header_ink = "#FFFFFF" if (mode == "dark" or background != "paper") else ink
    checks = {
        "ink_on_surface": round(C.contrast(ink, solid), 2), "secondary_text": round(C.contrast(ink2, solid), 2),
        "muted_text": round(C.contrast(muted, solid), 2), "accent_on_surface": round(C.contrast(accent, solid), 2),
        "chart_min_contrast": round(min(C.contrast(c, solid) for c in cat[:6]), 2),
        "chart_min_neighbour_distance": round(min(C.delta_e(cat[i], cat[i + 1]) for i in range(len(cat) - 1)), 1),
        "chart_min_cvd_distance": round(C.min_cvd_distance(cat[:6]), 1),
    }
    return {"mode": mode, "background": background, "theme": theme_key, "character": character_label,
            "primary": _fit(primary_raw, mode) if Cp >= 0.06 else cat[0], "primary_raw": primary_raw, "secondary": second, "tertiary": third,
            "accent": accent, "accent_ink": accent_ink, "accent_soft": C.rgba(accent, 0.16 if mode == "dark" else 0.10),
            "bg": bg, "bg2": bg2, "surface": surface, "surface2": surface2, "solid": solid, "line": line, "grid": grid,
            "ink": ink, "ink2": ink2, "muted": muted, "status": status, "categorical": cat, "sequential": seq, "diverging": div,
            "header": header, "header_ink": header_ink, "header_sub": "rgba(255,255,255,.78)" if header_ink == "#FFFFFF" else muted,
            "glow1": C.rgba(_fit(roles[0], "dark"), 0.22 if mode == "dark" else 0.10), "glow2": C.rgba(_fit(roles[1], "dark"), 0.16 if mode == "dark" else 0.08),
            "radius": "6px" if theme_key == "minimal" else "18px", "checks": checks}


def build(extracted: dict | None, theme_key: str, *, custom: dict | None = None, background: str = "auto") -> dict:
    """The design system for one dashboard. Deterministic: the same inputs always give the same tokens."""
    seeds_default, bg_default = THEME_DEFAULTS.get(theme_key, THEME_DEFAULTS["corporate"])
    bg = bg_default if background in (None, "", "auto") else background
    mode = "light" if bg in LIGHT_BACKGROUNDS else "dark"
    custom = {k: v for k, v in (custom or {}).items() if v}
    rule, source, character = "theme defaults", "theme", "Lucerna theme palette"
    roles: list[str] = []
    if extracted and extracted.get("swatches"):
        roles, rule = _pick_roles(extracted["swatches"])
        source, character = "logo", extracted.get("character", {}).get("label", "")
    elif extracted:
        rule, source, character = "monochrome logo: restrained slate and blue", "logo", "Monochrome"
        roles = ["#3B5B8C", "#4F7CAC"]
    if not roles:
        roles = list(seeds_default)
    roles = _complete_roles(roles)
    for i, k in enumerate(("primary", "secondary", "accent")):
        if custom.get(k):
            roles[i] = custom[k]
            source = "custom" if source == "theme" else source + " + custom"
    d = dict(_design(tuple(r.upper() for r in roles), mode, bg, theme_key, character))
    d.update(source=source, rule=rule, roles=roles)
    return d


def css_background(d: dict, image_data_uri: str | None = None) -> str:
    bg, bg2, g1, g2 = d["bg"], d["bg2"], d["glow1"], d["glow2"]
    kind = d["background"]
    if kind == "image" and image_data_uri:
        veil = "rgba(6,10,20,.78)" if d["mode"] == "dark" else "rgba(250,251,253,.86)"
        return f"linear-gradient({veil},{veil}), url('{image_data_uri}') center/cover fixed, {bg}"
    if kind == "paper":
        return bg
    if kind == "light":
        return f"radial-gradient(1100px 520px at 88% -8%, {g1}, transparent 60%), radial-gradient(900px 500px at -5% 105%, {g2}, transparent 60%), linear-gradient(180deg,{bg} 0%,{bg2} 100%)"
    if kind == "deepsea":
        return "radial-gradient(1200px 700px at 85% -10%, rgba(25,198,180,.20), transparent 60%), radial-gradient(1000px 700px at 0% 110%, rgba(47,123,255,.22), transparent 60%), linear-gradient(160deg,#061426 0%,#082033 55%,#06222B 100%)"
    if kind == "aurora":
        return "radial-gradient(1100px 650px at 90% -10%, rgba(139,108,255,.26), transparent 60%), radial-gradient(900px 600px at 5% 105%, rgba(47,123,255,.20), transparent 60%), linear-gradient(160deg,#0B0A24 0%,#11123A 55%,#0A1230 100%)"
    if kind == "brand":
        return f"radial-gradient(1200px 700px at 92% -12%, {g1}, transparent 62%), radial-gradient(1000px 650px at -4% 108%, {g2}, transparent 60%), linear-gradient(160deg,{bg} 0%,{bg2} 100%)"
    # navy
    return f"radial-gradient(1100px 620px at 88% -10%, rgba(47,123,255,.18), transparent 60%), radial-gradient(900px 600px at 0% 110%, {g2}, transparent 60%), linear-gradient(160deg,#070D1C 0%,#0B1730 60%,#081226 100%)"
