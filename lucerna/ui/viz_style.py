"""Presentation-only restyling of the Plotly figures produced by the (protected) chart engine.

`charts.figure` decides *what* is drawn: traces, values, categories, order, axes and hover text. This module only
changes *how it looks*: every colour that came from the engine's palette is swapped, slot for slot, for the
dashboard's brand palette; backgrounds become transparent; grids, fonts, legends and tooltips follow the dashboard
design tokens; marks get the finishing details (rounded bar ends, thin separators, donut hole, soft area fills).
No data, label, category order, scale or hover value is changed.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go

from ..quant.palette import CATEGORICAL, DIVERGING, INK, OTHER, SURFACE
from .brand import color as C
from .titles import axis_label

FONT = "Inter, 'Segoe UI', Vazirmatn, 'Noto Sans Arabic', system-ui, sans-serif"
_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")


def engine_mode(design: dict) -> str:
    """The engine palette the figure is built with; its colours are then swapped slot for slot."""
    return "dark" if design["mode"] == "dark" else "light"


def _colour_map(mode: str, d: dict) -> dict[str, str]:
    cat = d["categorical"]
    neutral = C.mix(d["muted"], d["solid"], 0.35)
    div = d["diverging"]
    m = {c.upper(): cat[i % len(cat)] for i, c in enumerate(CATEGORICAL[mode])}
    m[OTHER[mode].upper()] = neutral
    m[SURFACE[mode].upper()] = d["solid"]
    ink = INK[mode]
    m.update({ink["primary"].upper(): d["ink"], ink["secondary"].upper(): d["ink2"], ink["muted"].upper(): d["muted"]})
    m.update({DIVERGING["neg"].upper(): div[0], DIVERGING["neg2"].upper(): div[1], DIVERGING["pos2"].upper(): div[-2], DIVERGING["pos"].upper(): div[-1],
              DIVERGING["mid"][mode].upper(): div[len(div) // 2]})
    return m


def _scale(colors: list[str]) -> list[list]:
    n = len(colors) - 1
    return [[i / n, c] for i, c in enumerate(colors)]


def _swap(obj, cmap: dict, d: dict, grid_src: str):
    """Recursively replace engine colours in a plotly JSON structure."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "colorscale" and isinstance(v, (list, tuple)) and v:
                first = str(v[0][1]).upper() if isinstance(v[0], (list, tuple)) else ""
                out[k] = _scale(d["diverging"]) if first == DIVERGING["neg"].upper() else _scale(d["sequential"])
            else:
                out[k] = _swap(v, cmap, d, grid_src)
        return out
    if isinstance(obj, (list, tuple)):
        return [_swap(x, cmap, d, grid_src) for x in obj]
    if isinstance(obj, str):
        u = obj.upper()
        if u in cmap:
            return cmap[u]
        if u == grid_src:
            return d["grid"]
        m = _RGBA.fullmatch(obj.replace(" ", ""))
        if m:
            r, g, b, a = int(m[1]), int(m[2]), int(m[3]), float(m[4])
            if (r, g, b) == (71, 120, 232):                 # forecast interval band → second brand colour
                return C.rgba(d["categorical"][1], a)
            if (r, g, b) == (123, 135, 148):                # sankey links → neutral
                return C.rgba(d["muted"], a)
        return obj
    return obj


def _text_on(fill: str, d: dict) -> str:
    try:
        return "#FFFFFF" if C.contrast("#FFFFFF", fill) >= C.contrast("#0B1020", fill) else "#0B1020"
    except Exception:  # noqa: BLE001
        return d["ink"]


def restyle(fig: go.Figure, v: dict, d: dict, *, labels: dict | None = None, height: int | None = None, present: bool = False) -> go.Figure:
    """Return a new figure with the dashboard's design applied. `v` is the visual spec (read only)."""
    mode = engine_mode(d)
    cmap = _colour_map(mode, d)
    grid_src = INK[mode]["grid"].upper()
    raw = fig.to_plotly_json()
    data = _swap(raw.get("data", []), cmap, d, grid_src)
    layout = _swap(raw.get("layout", {}), cmap, d, grid_src)
    t = v.get("type")
    for tr in data:
        tt = tr.get("type")
        if tt == "bar":
            mk = tr.setdefault("marker", {})
            mk.setdefault("cornerradius", 4)
        elif tt == "pie":
            tr["hole"] = 0.64
            cols = (tr.get("marker") or {}).get("colors") or []
            tr.setdefault("textfont", {})["color"] = [_text_on(c, d) for c in cols] or d["ink"]
            tr.setdefault("marker", {}).setdefault("line", {})["color"] = d["solid"]
            tr["textfont"]["size"] = 11
        elif tt == "scatter":
            line = tr.get("line") or {}
            if tr.get("stackgroup") and line.get("color"):
                tr["fillcolor"] = C.rgba(line["color"], 0.30 if d["mode"] == "dark" else 0.22)
            elif t == "line" and line.get("dash") is None and tr.get("mode", "").startswith("lines") and line.get("color") == d["categorical"][0] \
                    and len(data) <= 3 and tr.get("fill") is None:
                tr["fill"] = "tozeroy"                     # soft area under a single trend line
                tr["fillcolor"] = C.rgba(line["color"], 0.14 if d["mode"] == "dark" else 0.09)
        elif tt == "heatmap":
            tr["colorbar"] = {**(tr.get("colorbar") or {}), "tickfont": {"color": d["muted"]}, "outlinewidth": 0, "thickness": 8}
        elif tt in ("treemap",):
            tr.setdefault("textfont", {})["color"] = [_text_on(c, d) for c in (tr.get("marker") or {}).get("colors", [])] or d["ink"]
        elif tt == "sankey":
            tr.setdefault("textfont", {})["color"] = d["ink"]
    out = go.Figure(data=data, layout=layout)
    out.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title=None,
        font=dict(family=FONT, size=12, color=d["ink2"]),
        legend=dict(font=dict(color=d["ink2"], size=11), bgcolor="rgba(0,0,0,0)", itemsizing="constant"),
        hoverlabel=dict(bgcolor=d["solid"], bordercolor=d["line"] if d["line"].startswith("#") else d["accent"],
                        font=dict(color=d["ink"], size=12, family=FONT), align="left"),
        margin=dict(l=6, r=10, t=8, b=6),
        transition=dict(duration=0),
    )
    out.update_xaxes(gridcolor=d["grid"], linecolor=d["grid"], tickfont=dict(color=d["muted"], size=11), title_font=dict(color=d["muted"], size=11),
                     zerolinecolor=d["grid"])
    out.update_yaxes(gridcolor=d["grid"], linecolor="rgba(0,0,0,0)", tickfont=dict(color=d["muted"], size=11), title_font=dict(color=d["muted"], size=11),
                     zerolinecolor=d["grid"])
    for k in list(layout):
        if re.fullmatch(r"[xy]axis\d*", k):
            ttl = ((layout[k] or {}).get("title") or {}).get("text") if isinstance((layout[k] or {}).get("title"), dict) else None
            if ttl:
                out.layout[k].title.text = axis_label(ttl, labels or {})
    if layout.get("map"):
        out.update_layout(map_style="carto-darkmatter" if d["mode"] == "dark" else "carto-positron")
    if height:
        out.update_layout(height=height)
    elif present and out.layout.height:
        out.update_layout(height=int(out.layout.height * 1.15))
    return out
