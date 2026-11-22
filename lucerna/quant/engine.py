"""Universal adaptive dashboard engine.

Builds a multi-page dashboard specification for ANY tabular dataset from what the data actually contains.
There are no sector templates: pages are assembled from analytical modules that switch on only when the
variables and data quality support them, and the page names, KPIs and charts follow the variables found.

Modules (each produces a page only if it has enough substance):
    Executive overview · Profile of records (demographics) · Topic pages (variables grouped by meaning or
    questionnaire section) · Change over time · Geography · Flows (origin → destination) · Group comparisons
    (with significance tests) · Relationships between measures · Related sheets (validated links) ·
    Data quality & methodology

Every visual is computed deterministically by `charts.compute`; `explain.explain` produces its narrative.
"""
from __future__ import annotations

import math
import re
import uuid

import numpy as np
import pandas as pd

from . import domain as dom
from . import quality as qquality
from .charts import likert_order, not_applicable_values
from .counting import UNIT_LABELS

MAX_CHARTS_PER_PAGE = 8
YES_VALUES = ["yes", "true", "1"]
POPULATION_HINT = r"trav(el)?ler|respondent|beneficiar|population|household_type|hh_type|displacement_status|resident|cohort|(^|_)arm($|_)|programme|program|strat"
SEGMENT_HINT = r"type|group|category|status|direction|modality|cohort|population|respondent_type|strata|stratum|arm|treatment|condition|sector|programme|program|round|wave|phase|class|level"
MIN_RECORDS_FOR_BREAKDOWNS = 30
FREE_TEXT_NAMES = r"comment|remark|explain|specify|(^|_)notes?$|open_(answer|response|text)|verbatim"
NOT_OUTCOME = r"consent|enumerator|interviewer|surveyor|uuid|_index|^index|^start$|^end$|^today$|deviceid|__"


def _vid() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- variable understanding

class Vars:
    """Roles of every usable column, derived from the (confirmed or inferred) mapping and the values."""

    def __init__(self, df: pd.DataFrame, mapping: dict[str, dict], labels: dict[str, str]):
        self.df, self.labels = df, labels
        self.dates, self.geo, self.origin, self.destination = [], [], [], []
        self.lat = self.lon = self.sex = self.age = self.age_group = self.hh_size = self.weight = self.round = None
        self.ids, self.pii, self.binaries, self.categories, self.likert, self.multiselect, self.measures, self.free_text = ([] for _ in range(8))
        self.na_values: dict[str, list[str]] = {}
        n = len(df)
        for col, m in mapping.items():
            if col not in df.columns or m.get("type") == "ignore" or re.search(NOT_OUTCOME, col.lower()):
                continue
            role, typ = m.get("role"), m.get("type")
            s = df[col]
            if s.notna().sum() == 0:
                continue
            if role in ("personal_name", "phone"):
                self.pii.append(col); continue
            if role == "identifier" or typ == "identifier":
                self.ids.append(col); continue
            if typ == "date" or role == "date":
                if pd.api.types.is_datetime64_any_dtype(s) and s.notna().sum() >= max(3, .2 * n):
                    self.dates.append(col)
                continue
            if role == "latitude":
                self.lat = col; continue
            if role == "longitude":
                self.lon = col; continue
            if role == "geo_origin":
                self.origin.append(col); continue
            if role == "geo_destination":
                self.destination.append(col); continue
            if role in ("geo_admin1", "geo_admin2", "geo_admin3"):
                self.geo.append((role, col)); continue
            if role == "sex" and not self.sex:
                self.sex = col; continue
            if role == "age" and not self.age and pd.api.types.is_numeric_dtype(s):
                self.age = col; continue
            if role == "age_group" and not self.age_group:
                self.age_group = col; continue
            if role == "household_size" and not self.hh_size and pd.api.types.is_numeric_dtype(s):
                self.hh_size = col; continue
            if role == "weight":
                self.weight = col; continue
            if role == "round":
                self.round = col; continue
            if typ == "boolean" or role == "binary" or pd.api.types.is_bool_dtype(s):
                self.binaries.append(col); continue
            if typ == "multiselect" or role == "multiselect":
                self.multiselect.append(col); continue
            if role == "free_text" or typ == "text" or (re.search(FREE_TEXT_NAMES, col.lower()) and not pd.api.types.is_numeric_dtype(s)):
                self.free_text.append(col); continue
            if pd.api.types.is_numeric_dtype(s) and typ in ("numeric", "integer") and role in ("measure", None, "category"):
                if s.notna().sum() >= 5 and s.nunique() > 2:
                    self.measures.append(col)
                continue
            vals = s.dropna().astype(str)
            na = not_applicable_values(vals)
            if na:
                self.na_values[col] = na
            nun = vals[~vals.isin(na)].nunique()
            if nun < 2:
                continue
            if likert_order(list(vals[~vals.isin(na)].unique())):
                self.likert.append(col)
            elif nun <= 60 or nun / max(1, len(vals)) < .2:
                self.categories.append(col)
            else:
                self.free_text.append(col)
        if self.age and not self.age_group:
            self.age_group = None

    def scale(self, col: str) -> list[str] | None:
        """Ordered levels (negative to positive) of a rating-scale column."""
        vals = self.df[col].dropna().astype(str)
        return likert_order(list(vals[~vals.isin(self.na_values.get(col, []))].unique()))

    def label(self, col: str | None) -> str:
        if not col:
            return ""
        return self.labels.get(col) or dom.humanise(col)

    def nlevels(self, col: str) -> int:
        vals = self.df[col].dropna().astype(str)
        return int(vals[~vals.isin(self.na_values.get(col, []))].nunique())

    def excl(self, *cols) -> dict:
        return {c: self.na_values[c] for c in cols if c and c in self.na_values}


def _entropy(s: pd.Series) -> float:
    p = s.value_counts(normalize=True)
    if len(p) <= 1:
        return 0.0
    return float(-(p * np.log(p)).sum() / math.log(len(p)))


def _yes_rate(s: pd.Series) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    if pd.api.types.is_bool_dtype(s):
        return float(100 * s.astype(bool).mean())
    return float(100 * s.astype(str).str.strip().str.lower().isin(YES_VALUES).mean())


def _geo_hierarchy(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Order geographic columns from coarse to fine; keep a chain where each finer level nests in the coarser one."""
    cols = sorted(cols, key=lambda c: df[c].nunique())
    chain = [cols[0]] if cols else []
    for c in cols[1:]:
        parent = chain[-1]
        sub = df[[parent, c]].dropna().astype(str)
        if sub.empty or df[c].nunique() <= df[parent].nunique():
            continue
        nest = sub.groupby(c)[parent].nunique().le(1).mean()
        if nest >= .95:
            chain.append(c)
    return chain


def _segment(v: Vars, exclude: set[str]) -> str | None:
    """The grouping variable that best splits the records for comparisons (2–7 groups, well populated)."""
    best, best_score = None, 0.0
    df = v.df
    geo_cols = [c for _, c in v.geo]
    for c in v.categories + geo_cols + ([v.sex] if v.sex else []):
        if not c or c in exclude:
            continue
        k = v.nlevels(c)
        if not 2 <= k <= 7:
            continue
        s = df[c].dropna().astype(str)
        s = s[~s.isin(v.na_values.get(c, []))]
        cover = len(s) / max(1, len(df))
        if cover < .6 or s.value_counts().min() < 30:
            continue
        # population characteristics (type, group, sex, location) make better comparison groups than outcomes of a theme
        population = bool(re.search(POPULATION_HINT, c.lower()))
        outcome_like = not population and c not in geo_cols and c != v.sex and dom.topic_of(c, v.labels.get(c)) not in (None, "demographics")
        score = _entropy(s) * cover + (1.2 if re.search(SEGMENT_HINT, c.lower()) else 0) + (.3 if c == v.sex else 0) + \
            (.6 if population else 0) + (.4 if c in geo_cols else 0) - (1.0 if outcome_like else 0)
        if score > best_score:
            best, best_score = c, score
    return best


def _binary_score(df: pd.DataFrame, col: str, seg: str | None) -> float:
    r = _yes_rate(df[col])
    if r is None:
        return -1
    score = min(r, 100 - r)
    if seg and seg in df:
        g = df.groupby(df[seg].astype("string"), observed=True)[col].apply(_yes_rate).dropna()
        if len(g) >= 2:
            score += (g.max() - g.min())
    return score


# ---------------------------------------------------------------- visual builders

def _yes(col: str) -> dict:
    return {"column": col, "op": "in", "value": YES_VALUES}


class Builder:
    def __init__(self, v: Vars, unit_label: str, seg: str | None, sheet: str):
        self.v, self.unit, self.seg, self.sheet = v, unit_label, seg, sheet
        self.signatures: set = set()

    def add(self, out: list, vis: dict, topic: str = "general", kind: str = "distribution") -> None:
        sig = (vis["type"], vis.get("x"), vis.get("value"), vis.get("by"), vis.get("color"), (vis.get("condition") or {}).get("column"),
               vis.get("date"), vis.get("freq"), vis.get("measure"), vis.get("kpi"), tuple(vis.get("columns", [])), tuple(vis.get("path", [])), vis.get("ds"))
        if sig in self.signatures:
            return
        self.signatures.add(sig)
        vis.setdefault("id", _vid())
        vis["topic"], vis["kind"] = topic, kind
        vis.setdefault("source_sheet", self.sheet)
        out.append(vis)

    def var_visuals(self, col: str, topic: str, with_segment: bool = True) -> list[dict]:
        v, seg, L = self.v, self.seg if with_segment else None, self.v.label
        out: list[dict] = []
        seg = seg if seg != col else None
        if col in v.binaries:
            if seg:
                self.add(out, {"type": "bar", "x": seg, "measure": "pct_condition", "condition": _yes(col), "orientation": "h",
                               "title": f"{L(col)}: % yes by {L(seg)}", "width": 6, "var": col, "exclude_values": v.excl(seg)}, topic, "comparison")
            else:
                self.add(out, {"type": "kpi", "kpi": "pct", "condition": _yes(col), "title": f"{L(col)}: yes", "icon": "percent", "width": 3, "var": col},
                         topic, "kpi")
        elif col in v.likert:
            self.add(out, {"type": "likert", "x": col, "by": seg, "title": f"{L(col)}" + (f" by {L(seg)}" if seg else ""), "width": 12, "var": col,
                           "exclude_values": v.excl(col)}, topic, "comparison" if seg else "distribution")
        elif col in v.multiselect:
            sep = ";" if v.df[col].astype("string").str.contains(";").any() else (" " if not v.df[col].astype("string").str.contains(",").any() else ",")
            self.add(out, {"type": "multiselect", "x": col, "sep": sep, "title": f"{L(col)} (multiple answers allowed)", "width": 6, "var": col},
                     topic, "distribution")
        elif col in v.categories:
            k = v.nlevels(col)
            if seg and 2 <= k <= 6:
                self.add(out, {"type": "stacked100", "x": seg, "color": col, "title": f"{L(col)} by {L(seg)}", "width": 6, "var": col,
                               "exclude_values": v.excl(col, seg)}, topic, "comparison")
            else:
                self.add(out, {"type": "bar", "x": col, "measure": "count", "as_pct": True, "orientation": "h", "top_n": 12,
                               "title": f"{L(col)}", "width": 6, "var": col, "unit_label": self.unit, "exclude_values": v.excl(col)}, topic, "distribution")
        elif col in v.measures:
            self.add(out, {"type": "histogram", "value": col, "title": f"Distribution of {L(col)}", "width": 6, "var": col}, topic, "distribution")
            if seg:
                self.add(out, {"type": "box", "value": col, "by": seg, "title": f"{L(col)} by {L(seg)}", "width": 6, "var": col,
                               "exclude_values": v.excl(seg)}, topic, "comparison")
        return out


# ---------------------------------------------------------------- pages

def _pack(visuals: list[dict]) -> list[dict]:
    """Give charts widths that fill 12-column rows (KPIs are laid out by the viewer)."""
    charts_ = [x for x in visuals if x["type"] != "kpi"]
    half = [x for x in charts_ if x.get("width", 6) < 12]
    if len(half) % 2 == 1:
        half[-1]["width"] = 12
    return visuals


def _page(key: str, title: str, icon: str, purpose: str, visuals: list[dict]) -> dict:
    return {"key": key, "title": title, "icon": icon, "purpose": purpose, "visuals": _pack(visuals)}


def _substantive(p: dict) -> bool:
    return sum(1 for x in p["visuals"] if x["type"] not in ("kpi", "text")) >= 2 or \
        (sum(1 for x in p["visuals"] if x["type"] not in ("kpi", "text")) >= 1 and sum(1 for x in p["visuals"] if x["type"] == "kpi") >= 2)


def build(df: pd.DataFrame, mapping: dict[str, dict], *, labels: dict[str, str] | None = None, unit: str = "unknown",
          unit_confirmed: bool = False, dataset_name: str = "", sheet: str = "", sheet_names: list[str] | None = None,
          workbook: dict | None = None, linked: list[dict] | None = None, mapping_confirmed: bool = False) -> dict:
    labels = labels or {}
    v = Vars(df, mapping, labels)
    L = v.label
    n = len(df)
    values = {c: list(df[c].dropna().astype(str).value_counts().index[:6]) for c in (v.categories + v.likert)[:40]}
    d = dom.recognise(list(df.columns), labels, values, sheet_names)
    # an unconfirmed guess never names the counts: they stay "records" until an analyst confirms what one row is
    unit_label = UNIT_LABELS.get(unit, "records") if unit_confirmed and unit != "unknown" else "records"
    limitations, questions, feas = [], [], {}

    # geography
    geo_cols = [c for _, c in v.geo]
    hier = _geo_hierarchy(df, geo_cols) if geo_cols else []
    if not hier and v.destination:
        hier = _geo_hierarchy(df, v.destination)
    geo1 = hier[0] if hier else None
    exclude_seg = set(hier) | set(v.origin) | set(v.destination)
    seg = _segment(v, exclude_seg)
    B = Builder(v, unit_label, seg, sheet or dataset_name)

    # time
    tf = {"possible": False, "reason": "No date column with enough valid dates."}
    if v.dates:
        best_date = max(v.dates, key=lambda c: df[c].notna().sum())
        s = df[best_date].dropna()
        span = int((s.max() - s.min()).days)
        freq = "day" if span <= 45 else ("week" if span <= 200 else "month")
        periods = int(s.dt.to_period({"day": "D", "week": "W", "month": "M"}[freq]).nunique())
        months = int(s.dt.to_period("M").nunique())
        per = s.dt.normalize().value_counts()
        # fixed-design data (the same number of records on every collection date, e.g. weekly price panels) has no volume story to tell
        constant = bool(periods >= 3 and 3 <= len(per) <= len(s) / 2 and per.std(ddof=0) / per.mean() < .02)
        if constant:
            limitations.append(f"Every collection date has the same number of records ({int(per.iloc[0]):,}), so volume-over-time charts are not shown.")
        tf = {"possible": periods >= 3, "constant_volume": constant, "date": best_date, "freq": freq, "periods": periods, "span_days": span, "months": months,
              "reason": f"{periods} {freq}ly periods between {s.min():%d %b %Y} and {s.max():%d %b %Y}."}
        if periods < 3:
            limitations.append(f"Dates cover only {periods} {freq}ly period(s); trends are not shown.")
        invalid = int(df[best_date].isna().sum())
        if invalid:
            limitations.append(f"{invalid:,} record(s) have a missing or invalid '{best_date}' and are left out of time charts.")
    else:
        limitations.append("No usable date variable: change over time cannot be analysed.")
    feas["temporal"] = tf
    feas["forecast"] = {"possible": tf.get("months", 0) >= 12, "reason": f"{tf.get('months', 0)} months of history (12 or more needed)."}
    feas["geographic"] = {"possible": bool(hier), "levels": hier, "reason": "Location columns: " + ", ".join(hier) if hier else "No location columns."}
    feas["map_points"] = {"possible": bool(v.lat and v.lon), "reason": "Coordinates recorded in the data." if v.lat and v.lon else "No coordinate columns."}
    feas["flows"] = {"possible": bool(v.origin and (v.destination or geo1)), "reason": "Origin and destination columns found." if v.origin else "No origin column."}
    feas["demographic"] = {"possible": bool(v.sex or v.age or v.age_group),
                           "reason": ", ".join(x for x in (v.sex, v.age, v.age_group, v.hh_size) if x) or "No sex or age variables."}
    feas["comparisons"] = {"possible": bool(seg), "reason": f"Records split by '{L(seg)}' ({v.nlevels(seg)} groups)." if seg else
                           "No grouping variable with 2–7 well-populated groups."}
    feas["choropleth"] = {"possible": False, "reason": "Needs an administrative boundary file (GeoJSON); none is attached."}
    if not hier and not (v.lat and v.lon):
        limitations.append("No geographic variables: maps and location comparisons are not possible.")
    if v.pii:
        limitations.append(f"{len(v.pii)} column(s) hold personal data ({', '.join(v.pii)}) and are excluded from all visuals.")
    if not unit_confirmed:
        guess = f" (best guess: {UNIT_LABELS[unit]})" if unit in UNIT_LABELS else ""
        limitations.append(f"What one record represents has not been confirmed by an analyst{guess}; counts are labelled as records.")
    if not mapping_confirmed:
        limitations.append("Variable types were detected automatically and have not yet been confirmed by an analyst.")
    if n < MIN_RECORDS_FOR_BREAKDOWNS:
        limitations.append(f"Only {n} records: percentages are unstable and breakdowns are not advisable.")
    if v.weight:
        limitations.append(f"A weight column ('{v.weight}') exists; charts show unweighted results unless stated.")

    # outcomes and topics
    used_demo = {x for x in (v.sex, v.age, v.age_group, v.hh_size) if x}
    outcome_cols = [c for c in v.binaries + v.likert + v.multiselect + v.categories + v.measures
                    if c not in used_demo and c not in exclude_seg and c != seg and c != v.round]
    topics: dict[str, list[str]] = {}
    unknown = []
    for c in outcome_cols:
        t = dom.topic_of(c, labels.get(c))
        if t:
            topics.setdefault(t, []).append(c)
        else:
            unknown.append(c)
    # a battery of three or more items answered on the same rating scale stays together on one "Ratings & Perceptions" page
    scales: dict[tuple, list[str]] = {}
    for c in v.likert:
        if c in outcome_cols:
            scales.setdefault(tuple(v.scale(c) or ()), []).append(c)
    battery = [c for cols in scales.values() if len(cols) >= 3 for c in cols]
    if battery:
        for t in list(topics):
            topics[t] = [c for c in topics[t] if c not in battery]
        unknown = [c for c in unknown if c not in battery]
        topics["ratings"] = battery
    for p, cols in dom.prefix_groups(unknown).items():
        cols = [c for c in cols if c in unknown]
        if len(cols) >= 3:
            topics[f"section_{p}"] = cols
            unknown = [c for c in unknown if c not in cols]

    pages: list[dict] = []

    # ---- Executive overview
    ov: list[dict] = []
    B.add(ov, {"type": "kpi", "kpi": "count_rows", "title": unit_label.capitalize() if unit_confirmed else "Records analysed", "icon": "users", "width": 3}, "general", "kpi")
    if tf["possible"]:
        B.add(ov, {"type": "kpi", "kpi": "date_span", "value": tf["date"], "title": "Period covered", "icon": "calendar", "width": 3}, "time", "kpi")
    if hier:
        lvl = hier[-1] if len(hier) > 1 else hier[0]
        B.add(ov, {"type": "kpi", "kpi": "n_categories", "value": lvl, "title": f"{L(lvl)} covered", "icon": "map-pin", "width": 3}, "geography", "kpi")
    ranked_bin = sorted([c for c in v.binaries if c in outcome_cols], key=lambda c: -_binary_score(df, c, seg))
    for c in ranked_bin[:3]:
        B.add(ov, {"type": "kpi", "kpi": "pct", "condition": _yes(c), "title": f"{L(c)}", "icon": "percent", "width": 3, "var": c},
              dom.topic_of(c, labels.get(c)) or "general", "kpi")
    for c in sorted([c for c in v.likert if c in outcome_cols], key=lambda c: -df[c].notna().sum())[:max(0, 3 - len(ranked_bin[:3]))]:
        order = v.scale(c)
        if order and len(order) >= 4:
            B.add(ov, {"type": "kpi", "kpi": "pct", "condition": {"column": c, "op": "in", "value": order[-2:]},
                       "title": f"{L(c)}: {order[-2].lower()} or {order[-1].lower()}", "icon": "gauge", "width": 3, "var": c,
                       "exclude_values": v.excl(c)}, dom.topic_of(c, labels.get(c)) or "ratings", "kpi")
    key_measure = next((c for c in v.measures if c in outcome_cols and re.search(r"amount|income|price|cost|score|size|total|value|count|number|days|time|litre|liter|debt|cash|expend", c.lower())), None)
    if key_measure:
        B.add(ov, {"type": "kpi", "kpi": "median", "value": key_measure, "title": f"Median {L(key_measure).lower()}", "icon": "sigma", "width": 3, "var": key_measure},
              dom.topic_of(key_measure, labels.get(key_measure)) or "general", "kpi")
    B.add(ov, {"type": "text", "insights": True, "title": "Key findings", "width": 12}, "general", "summary")
    if tf["possible"]:
        if not tf.get("constant_volume"):
            B.add(ov, {"type": "line", "date": tf["date"], "freq": tf["freq"] if tf["freq"] != "day" or tf["periods"] <= 62 else "week", "measure": "count",
                       "unit_label": unit_label, "title": f"{unit_label.capitalize()} per {tf['freq']}", "width": 6}, "time", "trend")
    if seg:
        B.add(ov, {"type": "bar", "x": seg, "measure": "count", "as_pct": True, "orientation": "h", "unit_label": unit_label,
                   "title": f"{unit_label.capitalize()} by {L(seg)}", "width": 6, "var": seg, "exclude_values": v.excl(seg)}, "general", "composition")
    if hier:
        B.add(ov, {"type": "bar", "x": hier[0], "measure": "count", "unit_label": unit_label, "orientation": "h", "top_n": 12,
                   "title": f"{unit_label.capitalize()} by {L(hier[0])}", "width": 6, "drill": hier, "var": hier[0]}, "geography", "geo")
    if ranked_bin and seg is None and not tf["possible"]:
        B.add(ov, {"type": "bar", "x": ranked_bin[0], "measure": "count", "as_pct": True, "title": L(ranked_bin[0]), "width": 6, "var": ranked_bin[0]},
              "general", "distribution")
    lead_cat = next((c for c in v.categories if c in outcome_cols and 2 <= v.nlevels(c) <= 12), None)
    if lead_cat and sum(1 for x in ov if x["type"] not in ("kpi", "text")) < 2:
        B.add(ov, {"type": "bar", "x": lead_cat, "measure": "count", "as_pct": True, "orientation": "h", "title": L(lead_cat), "width": 6,
                   "var": lead_cat, "exclude_values": v.excl(lead_cat)}, dom.topic_of(lead_cat) or "general", "distribution")
    pages.append(_page("overview", "Executive Overview", "layout-dashboard",
                       f"Headline figures for this {d['label'].lower() if d['key'] != 'general' else 'dataset'}: size, coverage and the most informative outcomes.", ov))

    # ---- Profile of records
    prof: list[dict] = []
    if v.sex and (v.age or v.age_group):
        B.add(prof, {"type": "pyramid", "sex": v.sex, "age": v.age, "age_group": v.age_group, "title": f"Age and {L(v.sex).lower()} profile", "width": 6}, "demographics", "composition")
    if v.sex:
        B.add(prof, {"type": "bar", "x": v.sex, "measure": "count", "as_pct": True, "title": f"{L(v.sex)}", "width": 6, "var": v.sex}, "demographics", "composition")
    if v.age:
        B.add(prof, {"type": "histogram", "value": v.age, "title": f"Distribution of {L(v.age).lower()}", "width": 6, "var": v.age}, "demographics", "distribution")
    if v.age_group and not v.age:
        B.add(prof, {"type": "bar", "x": v.age_group, "measure": "count", "as_pct": True, "sort": "name", "title": L(v.age_group), "width": 6, "var": v.age_group}, "demographics", "composition")
    if v.hh_size:
        B.add(prof, {"type": "histogram", "value": v.hh_size, "title": f"Distribution of {L(v.hh_size).lower()}", "width": 6, "var": v.hh_size}, "demographics", "distribution")
    demo_extra = [c for c in v.categories if c in outcome_cols and re.search(r"marital|head|educat|disab|ethnic|religio|language|occupation|status", c.lower())][:3]
    for c in demo_extra:
        for x in B.var_visuals(c, "demographics"):
            prof.append(x)
        if c in outcome_cols:
            outcome_cols.remove(c)
        for t_ in topics.values():
            if c in t_:
                t_.remove(c)
    if v.sex and ranked_bin:
        B.add(prof, {"type": "heatmap", "x": v.sex, "conditions": [{**_yes(b), "label": L(b)} for b in ranked_bin[:8]],
                     "title": f"Key outcomes by {L(v.sex).lower()} (% yes)", "width": 12}, "demographics", "comparison")
    if prof:
        p = _page("profile", "Who Is Represented", "users-round", f"Characteristics of the {unit_label} in the data and whether results differ between groups.", prof)
        if _substantive(p):
            pages.append(p)
            questions.append(f"Who are the {unit_label} represented in the data?")

    # ---- Flows
    if feas["flows"]["possible"]:
        fl: list[dict] = []
        dest = (v.destination[0] if v.destination else geo1)
        if dest and dest in v.destination and len(v.destination) > 1:
            dest = min(v.destination, key=lambda c: df[c].nunique())
        orig = min(v.origin, key=lambda c: df[c].nunique())
        weight = next((c for c in v.measures if re.search(r"group_size|individuals|persons|people|number_of", c.lower())), None)
        via = geo1 if geo1 and geo1 not in (orig, dest) and df[geo1].nunique() <= 12 else None
        B.add(fl, {"type": "sankey", "source": orig, "via": via, "target": dest, "value": weight,
                   "title": f"Flows: {L(orig)} → " + (f"{L(via)} → " if via else "") + f"{L(dest)}" + (f" (weighted by {L(weight).lower()})" if weight else ""),
                   "width": 12}, "movement", "flow")
        for c in v.origin + v.destination:
            B.add(fl, {"type": "bar", "x": c, "measure": "count", "as_pct": True, "orientation": "h", "top_n": 12, "title": f"Top {L(c)}", "width": 6, "var": c},
                  "movement", "distribution")
        if tf["possible"] and seg:
            if not tf.get("constant_volume"):
                B.add(fl, {"type": "line", "date": tf["date"], "freq": "month" if tf["span_days"] > 90 else tf["freq"], "color": seg, "measure": "count",
                           "title": f"{unit_label.capitalize()} over time by {L(seg)}", "width": 12}, "movement", "trend")
        for c in topics.pop("movement", [])[:6]:
            fl += B.var_visuals(c, "movement")
        p = _page("flows", "Mobility & Flows", "route", "Where records come from and go to, and in what volumes.", fl[:MAX_CHARTS_PER_PAGE + 2])
        if _substantive(p):
            pages.append(p)
            questions.append("Where do people or goods come from and go to, and in what volumes?")

    # ---- Topic pages
    order = [k for k, *_ in dom.TOPICS]
    topic_keys = sorted(topics, key=lambda k: (order.index(k) if k in order else 99, k))
    leftovers: list[str] = list(unknown)
    for tk in topic_keys:
        cols = topics[tk]
        if not cols:
            continue
        if len(cols) == 1 and cols[0] not in v.likert:
            leftovers += cols
            continue
        title, icon = dom.topic_meta(tk) if not tk.startswith("section_") else (f"Section {tk.split('_', 1)[1].upper()}", "list-checks")
        vis: list[dict] = []
        bins = [c for c in cols if c in v.binaries]
        for c in sorted(bins, key=lambda c: -_binary_score(df, c, seg))[:4]:
            B.add(vis, {"type": "kpi", "kpi": "pct", "condition": _yes(c), "title": L(c), "icon": icon, "width": 3, "var": c}, tk, "kpi")
        for c in cols:
            vis += B.var_visuals(c, tk)
        if len(bins) >= 3 and seg:
            B.add(vis, {"type": "heatmap", "x": seg, "conditions": [{**_yes(b), "label": L(b)} for b in bins[:10]],
                        "title": f"{title}: % yes by {L(seg)}", "width": 12}, tk, "comparison")
        chart_vis = [x for x in vis if x["type"] != "kpi"]
        kpis = [x for x in vis if x["type"] == "kpi"]
        parts = [chart_vis[i:i + MAX_CHARTS_PER_PAGE] for i in range(0, max(1, len(chart_vis)), MAX_CHARTS_PER_PAGE)]
        for i, part in enumerate(parts):
            p = _page(f"topic_{tk}_{i}", title + (f" ({i + 1})" if len(parts) > 1 else ""), icon,
                      dom.WHY.get(tk, f"Variables in questionnaire section {tk.split('_', 1)[-1].upper()}."), (kpis if i == 0 else []) + part)
            if _substantive(p):
                pages.append(p)
            else:
                leftovers += [x.get("var") for x in part if x.get("var")]
        questions.append(f"What do the data show about {title.lower()}?")
    leftovers = [c for c in dict.fromkeys(leftovers) if c]
    if leftovers:
        vis = []
        for c in leftovers[:12]:
            vis += B.var_visuals(c, dom.topic_of(c, labels.get(c)) or "general")
        p = _page("other", "Additional Findings", "list-checks", "Variables that do not belong to a larger theme.", vis[:MAX_CHARTS_PER_PAGE])
        if _substantive(p):
            pages.append(p)
        else:
            pages[0]["visuals"] += [x for x in vis if x["type"] != "kpi"][:2]

    # ---- Change over time
    if tf["possible"]:
        tv: list[dict] = []
        freq = tf["freq"]
        fine = {"month": "week", "week": "day", "day": "day"}[freq] if tf["span_days"] <= 400 else freq
        if not tf.get("constant_volume"):
            B.add(tv, {"type": "line", "date": tf["date"], "freq": fine, "measure": "count", "unit_label": unit_label,
                       "title": f"{unit_label.capitalize()} per {fine} (with 3-period moving average)", "width": 12}, "time", "trend")
        if seg:
            if not tf.get("constant_volume"):
                B.add(tv, {"type": "line", "date": tf["date"], "freq": "month" if tf["span_days"] > 90 else freq, "color": seg, "measure": "count",
                           "title": f"{unit_label.capitalize()} per {('month' if tf['span_days'] > 90 else freq)} by {L(seg)}", "width": 6}, "time", "trend")
        for b in ranked_bin[:3]:
            B.add(tv, {"type": "line", "date": tf["date"], "freq": "month" if tf["span_days"] > 90 else freq, "measure": "pct_condition",
                       "condition": _yes(b), "title": f"{L(b)}: % yes over time", "width": 6, "var": b}, "time", "trend")
        if key_measure:
            B.add(tv, {"type": "line", "date": tf["date"], "freq": "month" if tf["span_days"] > 90 else freq, "measure": "median", "value": key_measure,
                       "title": f"Median {L(key_measure).lower()} over time", "width": 6, "var": key_measure}, "time", "trend")
            if seg:
                B.add(tv, {"type": "line", "date": tf["date"], "freq": "month" if tf["span_days"] > 90 else freq, "measure": "median", "value": key_measure,
                           "color": seg, "title": f"Median {L(key_measure).lower()} over time by {L(seg)}", "width": 12, "var": key_measure}, "time", "trend")
        if feas["forecast"]["possible"]:
            B.add(tv, {"type": "forecast", "date": tf["date"], "freq": "month", "measure": "count", "horizon": 3,
                       "title": "Monthly volume with a 3-month projection", "width": 12}, "time", "trend")
        p = _page("trends", "Change Over Time", "trending-up", "How volumes and outcomes change over time; projections only where history is long enough.", tv)
        if _substantive(p):
            pages.append(p)
            questions.append("How have volumes and outcomes changed over time?")

    # ---- Geography
    if hier or (v.lat and v.lon):
        gv: list[dict] = []
        if hier:
            if len(hier) >= 2:
                B.add(gv, {"type": "treemap", "path": hier[:2], "title": f"{unit_label.capitalize()} by {L(hier[0])} and {L(hier[1])}", "width": 6}, "geography", "geo")
            lvl = hier[-1]
            B.add(gv, {"type": "bar", "x": lvl, "measure": "count", "unit_label": unit_label, "orientation": "h", "top_n": 15,
                       "title": f"{unit_label.capitalize()} by {L(lvl)}", "width": 6, "var": lvl, "drill": hier if len(hier) > 1 and lvl == hier[0] else None}, "geography", "geo")
            if seg and df[hier[0]].nunique() <= 25:
                B.add(gv, {"type": "stacked100", "x": hier[0], "color": seg, "title": f"{L(seg)} within each {L(hier[0]).lower()}", "width": 6,
                           "var": seg, "exclude_values": v.excl(seg)}, "geography", "comparison")
            if ranked_bin:
                B.add(gv, {"type": "heatmap", "x": hier[0], "conditions": [{**_yes(b), "label": L(b)} for b in ranked_bin[:8]],
                           "title": f"Key outcomes by {L(hier[0])} (% yes)", "width": 12}, "geography", "comparison")
            if key_measure:
                B.add(gv, {"type": "bar", "x": hier[0], "measure": "median", "value": key_measure, "orientation": "h",
                           "title": f"Median {L(key_measure).lower()} by {L(hier[0])}", "width": 6, "var": key_measure}, "geography", "comparison")
        if v.lat and v.lon:
            B.add(gv, {"type": "map_points", "lat": v.lat, "lon": v.lon, "color": seg or (hier[0] if hier else None), "title": "Recorded locations", "width": 12},
                  "geography", "geo")
        p = _page("geography", "Geographic Analysis", "map", "Coverage and differences across locations.", gv)
        if _substantive(p):
            pages.append(p)
            questions.append("How do coverage and outcomes vary across locations?")

    # ---- Group comparisons
    if seg:
        outs = [{"column": b, "kind": "binary", "label": L(b)} for b in ranked_bin[:10]]
        outs += [{"column": m, "kind": "numeric", "label": L(m)} for m in v.measures if m in outcome_cols][:5]
        cv: list[dict] = []
        if outs:
            B.add(cv, {"type": "compare_table", "by": seg, "outcomes": outs, "outcomes_cols": [o["column"] for o in outs],
                       "title": f"Do outcomes differ by {L(seg).lower()}? (significance tests)", "width": 12, "exclude_values": v.excl(seg)}, "general", "comparison")
        second = v.sex if v.sex and v.sex != seg else (hier[0] if hier and df[hier[0]].nunique() <= 7 else None)
        if second and outs:
            B.add(cv, {"type": "compare_table", "by": second, "outcomes": outs, "outcomes_cols": [o["column"] for o in outs],
                       "title": f"Do outcomes differ by {L(second).lower()}? (significance tests)", "width": 12}, "general", "comparison")
        for m in [m for m in v.measures if m in outcome_cols][:2]:
            B.add(cv, {"type": "box", "value": m, "by": seg, "title": f"{L(m)} by {L(seg)}", "width": 6, "var": m, "exclude_values": v.excl(seg)}, "general", "comparison")
        p = _page("compare", "Group Comparisons", "git-compare", f"Whether outcomes differ between groups of {L(seg).lower()}, with tests that say if gaps are statistically meaningful.", cv)
        if _substantive(p) or (outs and len(cv) >= 1 and len(outs) >= 3):
            pages.append(p)
            questions.append(f"Do outcomes differ by {L(seg).lower()}?")

    # ---- Relationships
    meas = [m for m in v.measures if m in outcome_cols or m in (v.age, v.hh_size)]
    if len(meas) >= 3:
        rv = []
        B.add(rv, {"type": "correlation", "columns": meas[:10], "title": "How numeric measures move together (Spearman correlation)", "width": 7}, "general", "relationship")
        B.add(rv, {"type": "stat_summary", "columns": meas[:10], "title": "Statistical summary", "width": 5}, "general", "distribution")
        try:
            c = df[meas[:10]].apply(pd.to_numeric, errors="coerce").corr(method="spearman").abs()
            np.fill_diagonal(c.values, 0)
            a, b = np.unravel_index(np.nanargmax(c.values), c.shape)
            B.add(rv, {"type": "scatter", "x": meas[a], "y": meas[b], "color": seg if seg and v.nlevels(seg) <= 3 else None,
                       "title": f"{L(meas[a])} and {L(meas[b])}", "width": 12}, "general", "relationship")
        except ValueError:
            pass
        pages.append(_page("relationships", "Relationships Between Measures", "activity", "Associations between numeric measures. Association is not causation.", rv))
        questions.append("Are key numeric measures associated with each other?")

    # ---- Related sheets
    for ln in linked or []:
        lp = _linked_page(ln)
        if lp:
            pages.append(lp)

    # ---- Too few records: breakdowns, tests and trends would mislead, so only descriptive pages remain
    if n < MIN_RECORDS_FOR_BREAKDOWNS:
        dropped = [p["title"] for p in pages if p["key"] in ("trends", "geography", "compare", "relationships")]
        pages = [p for p in pages if p["key"] not in ("trends", "geography", "compare", "relationships")]
        if dropped:
            limitations.append(f"Only {n} records, so these pages were not generated: {', '.join(dropped)}.")

    # ---- Quality & methodology
    qv: list[dict] = []
    B.add(qv, {"type": "kpi", "kpi": "completeness", "title": "Cell completeness", "icon": "badge-check", "width": 3}, "quality", "kpi")
    B.add(qv, {"type": "kpi", "kpi": "count_rows", "title": "Records analysed", "icon": "database", "width": 3}, "quality", "kpi")
    if v.ids:
        B.add(qv, {"type": "kpi", "kpi": "duplicates", "value": v.ids[0], "title": f"Records sharing an ID ({v.ids[0]})", "icon": "copy", "width": 3}, "quality", "kpi")
    if df.isna().any().any():
        B.add(qv, {"type": "quality_missing", "title": "Missing values by column", "width": 6}, "quality", "quality")
    B.add(qv, {"type": "methodology", "title": "Data sources, methods and limitations", "width": 6}, "quality", "methodology")
    pages.append(_page("quality", "Data Quality & Methodology", "scan-search", "How reliable the data behind every chart is, and how the dashboard was built.", qv))

    try:
        mp = {c: m for c, m in mapping.items() if c in df.columns}
        q = qquality.assess(df, mp, v.ids[:1])
        quality = {"score": q.get("score"), "findings": [{k: f.get(k) for k in ("severity", "column", "check", "message", "count")} for f in q.get("findings", [])][:40]}
    except Exception as e:  # noqa: BLE001 — quality summary must never block generation
        quality = {"score": None, "findings": [], "error": str(e)}

    filters = []
    for c in hier[:2]:
        filters.append({"column": c, "kind": "values"})
    if seg:
        filters.append({"column": seg, "kind": "values"})
    if v.sex and v.sex != seg:
        filters.append({"column": v.sex, "kind": "values"})
    if v.round:
        filters.append({"column": v.round, "kind": "values"})
    if tf["possible"]:
        filters.append({"column": tf["date"], "kind": "date_range"})

    variables = {"dates": v.dates, "geo": {"hierarchy": hier, "all": geo_cols}, "origin": v.origin, "destination": v.destination,
                 "lat": v.lat, "lon": v.lon, "sex": v.sex, "age": v.age, "age_group": v.age_group, "household_size": v.hh_size,
                 "ids": v.ids, "binaries": v.binaries, "categories": v.categories, "likert": v.likert, "multiselect": v.multiselect,
                 "measures": v.measures, "free_text": v.free_text, "pii": v.pii, "segment": seg, "round": v.round, "weight": v.weight,
                 "not_applicable": v.na_values}
    plan = {"purpose": f"{d['label']} — {n:,} {unit_label}", "domain": d, "sector": d["label"], "unit": unit, "unit_label": unit_label,
            "unit_confirmed": unit_confirmed, "mapping_confirmed": mapping_confirmed, "dataset_name": dataset_name, "sheet": sheet,
            "variables": {k: val for k, val in variables.items() if val}, "labels": {c: lab for c, lab in labels.items() if c in df.columns},
            "questions": questions, "feasibility": feas, "limitations": limitations, "quality": quality, "workbook": workbook or {},
            "segment": seg, "recommended_pages": [p["title"] for p in pages], "n": n,
            "engine": "universal-adaptive-v1"}
    spec = {"pages": pages, "filters": filters, "theme": "corporate", "drill": {"geo": hier}}
    return {"plan": plan, "spec": spec}


def _linked_page(ln: dict) -> dict | None:
    """A compact page for a related sheet (e.g. daily counts next to survey records). Never merged into the main data."""
    df, mapping, name = ln["df"], ln["mapping"], ln["name"]
    v = Vars(df, mapping, ln.get("labels", {}))
    B = Builder(v, "records", None, name)
    counts = [c for c in v.measures if re.search(r"individual|person|people|count|total|number|families|households|arrivals|returnee|deportee|inflow|outflow|male|female|children|population|estimat", c.lower())]
    counts = [c for c in counts if not re.search(r"pct|percent|share|rate|ratio|avg|mean|median|_per_|lat|lon", c.lower())]
    vis: list[dict] = []
    ds = ln["dataset_id"]
    B.add(vis, {"type": "kpi", "kpi": "count_rows", "title": f"Rows in {name}", "icon": "table", "width": 3, "ds": ds}, "general", "kpi")
    for c in counts[:3]:
        B.add(vis, {"type": "kpi", "kpi": "sum", "value": c, "title": f"Total {v.label(c).lower()}", "icon": "sigma", "width": 3, "ds": ds, "var": c}, "general", "kpi")
    date = max(v.dates, key=lambda c: df[c].notna().sum()) if v.dates else None
    if date and counts:
        s = df[date].dropna()
        span = (s.max() - s.min()).days if len(s) else 0
        freq = "day" if span <= 62 else ("week" if span <= 200 else "month")
        B.add(vis, {"type": "multiline", "date": date, "freq": freq, "columns": counts[:5], "labels": {c: v.label(c) for c in counts[:5]},
                    "title": f"{name}: totals per {freq}", "width": 12, "ds": ds}, "time", "trend")
    cat = next((c for c in v.categories + [c for _, c in v.geo] if 2 <= v.nlevels(c) <= 25), None)
    if cat and counts:
        B.add(vis, {"type": "bar", "x": cat, "measure": "sum", "value": counts[0], "orientation": "h", "top_n": 15,
                    "title": f"{v.label(counts[0])} by {v.label(cat)}", "width": 6, "ds": ds, "var": counts[0]}, "general", "composition")
    if len(counts) >= 2 and cat:
        B.add(vis, {"type": "table", "by": cat, "columns": counts[:4], "title": f"{name}: summary by {v.label(cat)}", "width": 6, "ds": ds, "agg": "sum"},
              "general", "composition")
    p = _page(f"linked_{ds}", f"Related Data: {dom.humanise(name)}", "link", ln.get("reason") or f"Related sheet '{name}', analysed separately.", vis)
    return p if _substantive(p) else None
