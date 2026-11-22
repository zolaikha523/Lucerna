"""Dashboard composition: how the visuals the engine chose are *arranged* on screen. Presentation only.

The engine decides which analyses exist (pages, visuals, measures). This module decides, per page:
- which visual leads the page (the "hero"), based on the dataset's domain and what the page actually contains;
- the reading order of the remaining visuals (by analytical kind, in an order that suits the domain);
- widths, so rows are balanced and a lone half-width chart does not leave a hole;
- the KPI card style and where key findings sit.

Nothing is added, removed or recomputed: every visual in the page spec is shown exactly once. Empty sections cannot
appear because sections are only formed from visuals that exist.
"""
from __future__ import annotations

# reading order of visual kinds, hero candidates (type or type:kind), KPI style and findings placement per domain
PROFILES: dict[str, dict] = {
    "displacement": {"name": "Flow-led", "order": ["flow", "geo", "trend", "composition", "comparison", "distribution", "relationship"],
                     "hero": ["sankey", "map_points", "bar:geo", "line"], "kpi": "strip", "findings": "side"},
    "wash": {"name": "Service-coverage", "order": ["geo", "comparison", "trend", "distribution", "composition", "relationship"],
             "hero": ["map_points", "heatmap", "bar:comparison", "line"], "kpi": "ring", "findings": "side"},
    "food_security": {"name": "Distribution-led", "order": ["distribution", "comparison", "composition", "trend", "geo", "relationship"],
                      "hero": ["stacked100", "histogram", "bar:comparison", "line"], "kpi": "meter", "findings": "bottom"},
    "cash": {"name": "Delivery-and-outcome", "order": ["composition", "comparison", "trend", "geo", "distribution", "relationship"],
             "hero": ["line", "bar:comparison", "bar:composition"], "kpi": "tile", "findings": "side"},
    "pdm": {"name": "Satisfaction-led", "order": ["comparison", "composition", "trend", "distribution", "geo", "relationship"],
            "hero": ["likert", "stacked100", "bar:comparison"], "kpi": "ring", "findings": "side"},
    "market": {"name": "Trend-led", "order": ["trend", "comparison", "geo", "distribution", "composition", "relationship"],
               "hero": ["multiline", "line", "forecast", "box"], "kpi": "tile", "findings": "side"},
    "research": {"name": "Evidence-led", "order": ["comparison", "distribution", "composition", "relationship", "trend", "geo"],
                 "hero": ["likert", "compare_table", "box", "stacked100"], "kpi": "inline", "findings": "bottom"},
    "protection": {"name": "Needs-led", "order": ["comparison", "composition", "geo", "trend", "distribution", "relationship"],
                   "hero": ["multiselect", "heatmap", "bar:comparison"], "kpi": "meter", "findings": "side"},
    "needs_assessment": {"name": "Needs-led", "order": ["comparison", "geo", "composition", "distribution", "trend", "relationship"],
                         "hero": ["multiselect", "heatmap", "bar:geo"], "kpi": "meter", "findings": "side"},
}
DEFAULT = {"name": "Balanced", "order": ["trend", "composition", "comparison", "geo", "distribution", "relationship"],
           "hero": ["line", "bar:composition", "bar"], "kpi": "tile", "findings": "side"}
NEVER_HERO = {"kpi", "text", "methodology", "quality_missing", "table", "stat_summary"}


def profile(plan: dict) -> dict:
    key = (plan.get("domain") or {}).get("key") or "general"
    p = PROFILES.get(key, DEFAULT)
    return {**p, "domain": key}


def _matches(v: dict, cand: str) -> bool:
    t, _, k = cand.partition(":")
    return v.get("type") == t and (not k or v.get("kind") == k)


def arrange(visuals: list[dict], plan: dict, page_index: int) -> dict:
    """{"kpis": [...], "hero": v | None, "rows": [[(v, width), ...], ...], "profile": {...}} for one page."""
    prof = profile(plan)
    kpis = [v for v in visuals if v.get("type") == "kpi"]
    rest = [v for v in visuals if v.get("type") not in ("kpi", "text")]
    hero = None
    for cand in prof["hero"]:
        hero = next((v for v in rest if _matches(v, cand) and v.get("type") not in NEVER_HERO), None)
        if hero:
            break
    if hero is None and page_index == 0:
        hero = next((v for v in rest if v.get("type") not in NEVER_HERO), None)
    others = [v for v in rest if v is not hero]
    rank = {k: i for i, k in enumerate(prof["order"])}
    tail = {"quality": 90, "methodology": 99}
    others = sorted(enumerate(others), key=lambda iv: (tail.get(iv[1].get("kind"), rank.get(iv[1].get("kind"), 50)), iv[0]))
    others = [v for _, v in others]
    rows: list[list[tuple[dict, int]]] = []
    row, used = [], 0
    for v in others:
        w = max(4, min(12, int(v.get("width") or 6)))
        if v.get("type") in ("sankey", "map_points", "choropleth", "heatmap", "likert", "compare_table") or v.get("kind") == "geo" and v.get("top_n"):
            w = 12 if w >= 8 else w
        if used + w > 12 and row:
            rows.append(row)
            row, used = [], 0
        row.append((v, w))
        used += w
    if row:
        rows.append(row)
    # balance: a row with a single narrow chart widens it (no holes); two narrow charts share the row equally
    for r in rows:
        tot = sum(w for _, w in r)
        if tot < 12:
            share = 12 // len(r)
            r[:] = [(v, share) for v, _ in r]
            r[-1] = (r[-1][0], 12 - share * (len(r) - 1))
    return {"kpis": kpis, "hero": hero, "rows": rows, "profile": prof}


def kpi_style(prof: dict, character: dict | None) -> str:
    """KPI card variant: the domain's default, softened for calm/minimal brands."""
    style = prof.get("kpi", "tile")
    if character and character.get("energy") == "muted" and style in ("ring", "meter"):
        return "meter"
    return style
