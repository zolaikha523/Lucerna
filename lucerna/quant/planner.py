"""Analytical planning and AI Auto Dashboard generation (deterministic rules).

The planner inspects the confirmed mapping and the data, decides which analytical questions the
dataset can answer, and only then creates pages. A page is created only if it has a purpose that
the data supports; every unsupported analysis is recorded as a limitation with the reason.
"""
from __future__ import annotations

import re
import uuid

import pandas as pd

from .charts import likert_order
from .counting import UNIT_LABELS

TOPICS = [
    ("access", "Assistance & Access", "wallet", r"receiv|modality|transfer|amount|cash|voucher|delay|distribut|registr|access|travel|distance|cost|paid|payment"),
    ("use", "Use of Assistance & Expenditure", "package", r"expend|spent|spend|use_of|purchase|bought|debt|rent"),
    ("safety", "Safety, Protection & Accountability", "shield", r"safe|risk|harass|protect|complain|feedback|cfm|hotline|aware|inform|consult|respect"),
    ("satisfaction", "Satisfaction & Perceptions", "circle-check", r"satisf|perce|opinion|quality|rating|trust"),
    ("water", "Water Access", "droplet", r"water|litre|liter|collection|source|treat|borehole|tap|well"),
    ("sanitation", "Sanitation & Hygiene", "hand-heart", r"latrine|toilet|sanitation|hygien|handwash|soap|defecat"),
    ("food", "Food Consumption & Coping", "utensils", r"fcs|food|cereal|pulse|vegetable|fruit|meat|milk|sugar|oil|rcsi|coping|meal|borrow|portion|hunger|diet"),
    ("livelihood", "Livelihoods & Income", "briefcase", r"income|livelihood|employ|job|business|saving|debt|remittance|labour|labor"),
    ("movement", "Movements & Arrivals", "route", r"crossing|arrival|border|origin|destination|returnee|deport|movement|flow|group_size"),
    ("vulnerability", "Vulnerability & Needs", "triangle-alert", r"vulnerab|disab|chronic|unaccompanied|female.?headed|need|priority"),
    ("health", "Health & Nutrition", "heart-pulse", r"health|clinic|ill|disease|vaccin|muac|nutrition|medicine"),
    ("education", "Education", "graduation-cap", r"school|enrol|attend|teacher|learn|education|knowledge|score"),
    ("shelter", "Shelter & NFI", "house", r"shelter|tent|nfi|blanket|housing|winter"),
]
DEMOGRAPHIC_ROLES = {"sex", "age", "age_group", "household_size"}
GEO_ROLES = ["geo_admin1", "geo_admin2", "geo_admin3"]
SECTOR_ICON = {"PDM / Cash & Voucher Assistance": "wallet", "WASH": "droplet", "Food Security": "utensils",
               "Returnee / Flow Monitoring": "route", "Health": "heart-pulse", "Nutrition": "baby", "Protection": "shield",
               "Education": "graduation-cap", "Shelter & NFI": "tent", "Livelihoods": "briefcase", "Baseline / Endline": "arrow-right-left",
               "Accountability (AAP / CFM)": "message-square", "Training Assessment": "graduation-cap"}


def _vid() -> str:
    return uuid.uuid4().hex[:8]


def _yes_condition(col: str) -> dict:
    return {"column": col, "op": "in", "value": ["yes", "true", "1"]}


def classify(df: pd.DataFrame, mapping: dict[str, dict]) -> dict:
    v = {"dates": [], "geo": {}, "lat": None, "lon": None, "origin": None, "destination": None, "sex": None, "age": None,
         "age_group": None, "household_size": None, "ids": [], "binaries": [], "categories": [], "likert": [], "measures": [],
         "multiselect": [], "free_text": [], "pii": [], "round": None, "weight": None}
    for col, m in mapping.items():
        if col not in df.columns or m.get("type") == "ignore":
            continue
        role, typ = m.get("role"), m.get("type")
        s = df[col]
        if re.search(r"consent|__outlier_flag$", col.lower()):
            continue  # administrative/technical fields are not analytical outcomes
        if role in ("personal_name", "phone"):
            v["pii"].append(col); continue
        if role == "identifier":
            v["ids"].append(col); continue
        if typ == "date" or role == "date":
            if pd.api.types.is_datetime64_any_dtype(s) and s.notna().any():
                v["dates"].append(col)
            continue
        if role in GEO_ROLES:
            v["geo"].setdefault(role, col); continue
        if role == "latitude":
            v["lat"] = col; continue
        if role == "longitude":
            v["lon"] = col; continue
        if role == "geo_origin":
            v["origin"] = col; continue
        if role == "geo_destination":
            v["destination"] = col
            v["geo"].setdefault("geo_admin1", col)
            continue
        if role in DEMOGRAPHIC_ROLES and not v[role]:
            v[role] = col; continue
        if role == "round":
            v["round"] = col; continue
        if role == "weight":
            v["weight"] = col; continue
        if typ == "boolean" or role == "binary":
            v["binaries"].append(col); continue
        if typ == "multiselect" or role == "multiselect":
            v["multiselect"].append(col); continue
        if role == "free_text" or typ == "text":
            v["free_text"].append(col); continue
        if typ in ("numeric", "integer") and role in ("measure", None):
            if s.notna().sum() >= 5:
                v["measures"].append(col)
            continue
        if s.notna().any():
            if likert_order(list(s.dropna().astype(str).unique())):
                v["likert"].append(col)
            elif s.nunique() >= 2:
                v["categories"].append(col)
    return v


def _topic_of(col: str) -> str | None:
    low = col.lower()
    for key, _, _, pat in TOPICS:
        if re.search(pat, low):
            return key
    return None


def make_plan(df: pd.DataFrame, mapping: dict[str, dict], *, unit: str = "unknown", sector: str | None = None,
              unit_confirmed: bool = False) -> dict:
    v = classify(df, mapping)
    n = len(df)
    unit_label = UNIT_LABELS.get(unit, "records")
    limitations, questions = [], []
    feas = {}

    dates = v["dates"]
    if dates:
        d = df[dates[0]].dropna()
        span_days = (d.max() - d.min()).days if len(d) else 0
        freq = "day" if span_days <= 45 else ("week" if span_days <= 180 else "month")
        periods = d.dt.to_period({"day": "D", "week": "W", "month": "M"}[freq]).nunique()
        feas["temporal"] = {"possible": periods >= 3, "date": dates[0], "freq": freq, "periods": int(periods), "span_days": int(span_days),
                            "reason": f"{periods} {freq}ly periods between {d.min():%d %b %Y} and {d.max():%d %b %Y}."}
        months = d.dt.to_period("M").nunique()
        feas["forecast"] = {"possible": months >= 12, "reason": f"{months} months of history" + ("" if months >= 12 else " (≥12 needed for a forecast)")}
        feas["seasonality"] = {"possible": months >= 24, "reason": f"{months} months of history" + ("" if months >= 24 else " (≥24 needed for seasonality)")}
        if periods < 3:
            limitations.append(f"Data covers only {periods} {freq}ly period(s); trend analysis is not meaningful.")
    else:
        feas["temporal"] = {"possible": False, "reason": "No date column was confirmed."}
        limitations.append("No date variable: temporal trends and forecasts are not possible.")

    geo_levels = [r for r in GEO_ROLES if r in v["geo"]]
    feas["geographic"] = {"possible": bool(geo_levels), "levels": [v["geo"][r] for r in geo_levels],
                          "reason": "Administrative location columns found." if geo_levels else "No location columns were confirmed."}
    feas["map_points"] = {"possible": bool(v["lat"] and v["lon"]), "reason": "GPS coordinates recorded in the data." if v["lat"] and v["lon"] else "No coordinate columns."}
    feas["choropleth"] = {"possible": False, "reason": "Requires an uploaded official boundary file (GeoJSON); none is attached to this dashboard."}
    if not geo_levels and not (v["lat"] and v["lon"]):
        limitations.append("No geographic variables: geographic comparison and maps are not possible.")
    feas["demographic"] = {"possible": bool(v["sex"] or v["age"] or v["age_group"]),
                           "reason": ", ".join(k for k in ("sex", "age", "age_group", "household_size") if v[k]) or "No sex/age variables."}
    feas["flows"] = {"possible": bool(v["origin"] and (v["destination"] or v["geo"].get("geo_admin1"))),
                     "reason": "Origin and destination columns found." if v["origin"] else "No origin/destination columns."}
    if v["pii"]:
        limitations.append(f"{len(v['pii'])} column(s) look like personal identifiers ({', '.join(v['pii'])}); they are excluded from dashboards.")
    if not unit_confirmed:
        limitations.append(f"The unit of analysis is not confirmed (currently '{unit}'). Counts are labelled as records until it is confirmed.")
    if n < 30:
        limitations.append(f"Only {n} records: percentages are unstable and disaggregation is not advisable.")

    # Analytical questions the data can answer
    if v["binaries"]:
        questions.append(f"What share of {unit_label} report each yes/no outcome ({len(v['binaries'])} outcome variables)?")
    if feas["demographic"]["possible"] and v["binaries"]:
        questions.append("Do outcomes differ between sex / age groups?")
    if feas["geographic"]["possible"]:
        questions.append("How do coverage and outcomes vary across locations?")
    if feas["temporal"]["possible"]:
        questions.append("How have volumes and outcomes changed over time?")
    if feas["flows"]["possible"]:
        questions.append("Where do people move from and to, and in what volumes?")
    if v["likert"]:
        questions.append("How satisfied / in agreement are respondents, and does this vary by group?")
    if len(v["measures"]) >= 2:
        questions.append("Are key numeric measures associated with each other?")

    pages = []
    kpis = [{"id": _vid(), "type": "kpi", "kpi": "count_rows", "title": unit_label.capitalize() if unit_confirmed else "Records", "icon": "users", "width": 3}]
    if v["ids"]:
        kpis.append({"id": _vid(), "type": "kpi", "kpi": "unique", "value": v["ids"][0], "title": f"Unique {v['ids'][0]}", "icon": "hash", "width": 3})
    if dates:
        kpis.append({"id": _vid(), "type": "kpi", "kpi": "date_span", "value": dates[0], "title": "Period covered", "icon": "calendar", "width": 3})
    if geo_levels:
        g = v["geo"][geo_levels[-1] if len(geo_levels) > 1 else geo_levels[0]]
        kpis.append({"id": _vid(), "type": "kpi", "kpi": "n_categories", "value": g, "title": f"{g} covered", "icon": "map-pin", "width": 3})
    for b in sorted(v["binaries"], key=lambda c: (_topic_of(c) is None, c))[: max(0, 8 - len(kpis))]:
        kpis.append({"id": _vid(), "type": "kpi", "kpi": "pct", "condition": _yes_condition(b), "title": f"{b}: yes", "icon": _icon_for(b), "width": 3})
    kpis.append({"id": _vid(), "type": "kpi", "kpi": "completeness", "title": "Data completeness", "icon": "badge-check", "width": 3})

    overview = {"key": "overview", "title": "Overview", "icon": SECTOR_ICON.get(sector or "", "layout-dashboard"),
                "purpose": f"Headline figures for this {sector or 'dataset'}: size, coverage and key outcomes.",
                "visuals": kpis[:8] + [{"id": _vid(), "type": "text", "insights": True, "title": "Key insights", "width": 12}]}
    if geo_levels:
        overview["visuals"].append({"id": _vid(), "type": "bar", "x": v["geo"][geo_levels[0]], "measure": "count", "unit_label": unit_label,
                                    "title": f"{unit_label.capitalize()} by {v['geo'][geo_levels[0]]}", "width": 6, "drill": [v["geo"][r] for r in geo_levels]})
    if feas["temporal"]["possible"]:
        overview["visuals"].append({"id": _vid(), "type": "line", "date": dates[0], "freq": feas["temporal"]["freq"], "measure": "count",
                                    "unit_label": unit_label, "title": f"{unit_label.capitalize()} over time", "width": 6})
    pages.append(overview)

    if feas["demographic"]["possible"]:
        vis = []
        if v["sex"] and (v["age"] or v["age_group"]):
            vis.append({"id": _vid(), "type": "pyramid", "sex": v["sex"], "age": v["age"], "age_group": v["age_group"], "title": "Age and sex profile", "width": 6})
        if v["sex"]:
            vis.append({"id": _vid(), "type": "donut", "x": v["sex"], "title": f"By {v['sex']}", "width": 3 if v["age"] else 6})
        if v["age"]:
            vis.append({"id": _vid(), "type": "histogram", "value": v["age"], "title": f"Distribution of {v['age']}", "width": 3 if v["sex"] else 6})
        if v["household_size"]:
            vis.append({"id": _vid(), "type": "histogram", "value": v["household_size"], "title": f"Distribution of {v['household_size']}", "width": 6})
        other_demo = [c for c in v["categories"] if re.search(r"head|disab|marital|status|type|group", c.lower())][:2]
        for c in other_demo:
            vis.append({"id": _vid(), "type": "bar", "x": c, "measure": "count", "as_pct": True, "title": f"By {c}", "width": 6})
        if v["sex"] and v["binaries"]:
            vis.append({"id": _vid(), "type": "heatmap", "x": v["sex"], "conditions": [{**_yes_condition(b), "label": b} for b in v["binaries"][:8]],
                        "title": f"Key outcomes by {v['sex']} (% yes)", "width": 12})
        pages.append({"key": "demographics", "title": "Population Profile", "icon": "users-round",
                      "purpose": "Who is represented in the data, and whether outcomes differ by sex and age.", "visuals": vis})

    # sector / topic pages
    topic_cols: dict[str, list[str]] = {}
    for c in v["binaries"] + v["categories"] + v["likert"] + v["multiselect"] + v["measures"]:
        k = _topic_of(c)
        if k:
            topic_cols.setdefault(k, []).append(c)
    grp = v["sex"] or (v["geo"].get(geo_levels[0]) if geo_levels else None)
    for key, title, icon, _ in TOPICS:
        cols = topic_cols.get(key, [])
        if not cols:
            continue
        vis = []
        for c in cols:
            if c in v["binaries"]:
                vis.append({"id": _vid(), "type": "kpi", "kpi": "pct", "condition": _yes_condition(c), "title": f"{c}: yes", "icon": icon, "width": 3})
        for c in cols:
            if c in v["binaries"] and grp:
                vis.append({"id": _vid(), "type": "bar", "x": grp, "measure": "pct_condition", "condition": _yes_condition(c),
                            "title": f"{c} — % yes by {grp}", "width": 6})
            elif c in v["likert"]:
                vis.append({"id": _vid(), "type": "likert", "x": c, "by": grp, "title": f"{c}" + (f" by {grp}" if grp else ""), "width": 12})
            elif c in v["multiselect"]:
                vis.append({"id": _vid(), "type": "multiselect", "x": c, "sep": " ", "title": f"{c} (multiple answers)", "width": 6})
            elif c in v["categories"]:
                ncat = df[c].nunique()
                if grp and ncat <= 7 and grp != c:
                    vis.append({"id": _vid(), "type": "stacked100", "x": grp, "color": c, "title": f"{c} by {grp}", "width": 6})
                else:
                    vis.append({"id": _vid(), "type": "bar", "x": c, "measure": "count", "as_pct": True, "title": f"{c}", "width": 6})
            elif c in v["measures"]:
                vis.append({"id": _vid(), "type": "histogram", "value": c, "title": f"Distribution of {c}", "width": 6})
                if grp:
                    vis.append({"id": _vid(), "type": "box", "value": c, "by": grp, "title": f"{c} by {grp}", "width": 6})
        if vis:
            pages.append({"key": key, "title": title, "icon": icon, "purpose": f"Variables related to {title.lower()}.", "visuals": vis[:12]})

    covered = {c for p in pages for vis in p["visuals"] for c in (vis.get("x"), vis.get("value"), vis.get("color"), (vis.get("condition") or {}).get("column"))}
    rest = [c for c in v["binaries"] + v["categories"] + v["likert"] + v["multiselect"] if c not in covered][:10]
    if rest:
        vis = []
        for c in rest:
            if c in v["binaries"]:
                vis.append({"id": _vid(), "type": "bar", "x": grp, "measure": "pct_condition", "condition": _yes_condition(c), "title": f"{c} — % yes by {grp}", "width": 6} if grp
                           else {"id": _vid(), "type": "kpi", "kpi": "pct", "condition": _yes_condition(c), "title": f"{c}: yes", "icon": "percent", "width": 3})
            elif c in v["multiselect"]:
                vis.append({"id": _vid(), "type": "multiselect", "x": c, "sep": ";" if df[c].astype("string").str.contains(";").any() else " ", "title": c, "width": 6})
            elif c in v["likert"]:
                vis.append({"id": _vid(), "type": "likert", "x": c, "by": grp, "title": c, "width": 12})
            else:
                vis.append({"id": _vid(), "type": "bar", "x": c, "measure": "count", "as_pct": True, "title": c, "width": 6})
        pages.append({"key": "other", "title": "Other Indicators", "icon": "list-checks", "purpose": "Remaining analysable variables not covered by a thematic page.", "visuals": vis})

    if geo_levels:
        vis = []
        if len(geo_levels) >= 2:
            vis.append({"id": _vid(), "type": "treemap", "path": [v["geo"][r] for r in geo_levels[:2]], "title": "Geographic distribution", "width": 6})
        lvl = v["geo"][geo_levels[-1]] if len(geo_levels) > 1 else v["geo"][geo_levels[0]]
        vis.append({"id": _vid(), "type": "bar", "x": lvl, "measure": "count", "unit_label": unit_label, "title": f"{unit_label.capitalize()} by {lvl}", "width": 6, "top_n": 20})
        if v["binaries"]:
            vis.append({"id": _vid(), "type": "heatmap", "x": v["geo"][geo_levels[0]], "conditions": [{**_yes_condition(b), "label": b} for b in v["binaries"][:10]],
                        "title": f"Key outcomes by {v['geo'][geo_levels[0]]} (% yes)", "width": 12})
        if v["lat"] and v["lon"]:
            vis.append({"id": _vid(), "type": "map_points", "lat": v["lat"], "lon": v["lon"], "color": v["geo"].get(geo_levels[0]), "title": "Recorded locations", "width": 12})
        pages.append({"key": "geography", "title": "Geographic Analysis", "icon": "map", "purpose": "Coverage and outcome differences across locations.", "visuals": vis})
    elif v["lat"] and v["lon"]:
        pages.append({"key": "geography", "title": "Geographic Analysis", "icon": "map", "purpose": "Recorded GPS locations.",
                      "visuals": [{"id": _vid(), "type": "map_points", "lat": v["lat"], "lon": v["lon"], "title": "Recorded locations", "width": 12}]})

    if feas["flows"]["possible"]:
        dest = v["destination"] or v["geo"].get("geo_admin1")
        via = next((c for c in v["categories"] if re.search(r"border|crossing|point|route", c.lower())), None)
        weight = next((c for c in v["measures"] if re.search(r"group_size|individuals|persons|people", c.lower())), None)
        vis = [{"id": _vid(), "type": "sankey", "source": v["origin"], "via": via, "target": dest, "value": weight,
                "title": "Movement flows" + (f" (weighted by {weight})" if weight else ""), "width": 12}]
        if feas["temporal"]["possible"]:
            vis.append({"id": _vid(), "type": "line", "date": dates[0], "freq": feas["temporal"]["freq"] if feas["temporal"]["freq"] != "day" else "week",
                        "color": v["origin"], "measure": "count", "title": f"Movements over time by {v['origin']}", "width": 12})
        pages.append({"key": "flows", "title": "Flows & Movements", "icon": "arrow-right-left", "purpose": "Origin–destination patterns and volumes.", "visuals": vis})

    if feas["temporal"]["possible"]:
        t = feas["temporal"]
        vis = [{"id": _vid(), "type": "line", "date": t["date"], "freq": t["freq"], "measure": "count", "unit_label": unit_label, "title": f"{unit_label.capitalize()} per {t['freq']}", "width": 12}]
        for b in v["binaries"][:3]:
            vis.append({"id": _vid(), "type": "line", "date": t["date"], "freq": "month" if t["span_days"] > 90 else t["freq"], "measure": "pct_condition",
                        "condition": _yes_condition(b), "title": f"{b} — % yes over time", "width": 6})
        if feas["forecast"]["possible"]:
            vis.append({"id": _vid(), "type": "forecast", "date": t["date"], "freq": "month", "measure": "count", "horizon": 3,
                        "title": "Monthly volume with 3-month forecast", "width": 12})
        pages.append({"key": "trends", "title": "Trends Over Time", "icon": "trending-up", "purpose": "Change over time, with forecasts only where history is sufficient.", "visuals": vis})

    if len(v["measures"]) >= 3:
        pages.append({"key": "relationships", "title": "Relationships", "icon": "activity", "purpose": "Associations between numeric measures (not causation).",
                      "visuals": [{"id": _vid(), "type": "correlation", "columns": v["measures"][:10], "title": "Correlation between numeric measures", "width": 7},
                                  {"id": _vid(), "type": "stat_summary", "columns": v["measures"][:10], "title": "Statistical summary", "width": 5}]})
    elif v["measures"]:
        pages[-1]["visuals"].append({"id": _vid(), "type": "stat_summary", "columns": v["measures"], "title": "Statistical summary", "width": 12})

    pages.append({"key": "quality", "title": "Data Quality", "icon": "scan-search", "purpose": "Completeness and reliability of the data behind every chart.",
                  "visuals": [{"id": _vid(), "type": "kpi", "kpi": "completeness", "title": "Overall completeness", "icon": "badge-check", "width": 3},
                              {"id": _vid(), "type": "kpi", "kpi": "count_rows", "title": "Records analysed", "icon": "database", "width": 3},
                              {"id": _vid(), "type": "quality_missing", "title": "Missing values by column", "width": 12}]})

    filters = []
    for role in ("geo_admin1", "geo_admin2"):
        if role in v["geo"]:
            filters.append({"column": v["geo"][role], "kind": "values"})
    if v["sex"]:
        filters.append({"column": v["sex"], "kind": "values"})
    if v["round"]:
        filters.append({"column": v["round"], "kind": "values"})
    if dates:
        filters.append({"column": dates[0], "kind": "date_range"})

    plan = {"purpose": f"{sector or 'Unclassified'} dataset of {n:,} {unit_label}", "sector": sector, "unit": unit, "unit_label": unit_label,
            "variables": {k: val for k, val in v.items() if val}, "questions": questions, "feasibility": feas, "limitations": limitations,
            "recommended_pages": [p["title"] for p in pages]}
    spec = {"pages": pages, "filters": filters, "theme": "light", "drill": {"geo": [v["geo"][r] for r in geo_levels]}}
    return {"plan": plan, "spec": spec}


def _icon_for(col: str) -> str:
    k = _topic_of(col)
    for key, _, icon, _ in TOPICS:
        if key == k:
            return icon
    return "percent"
