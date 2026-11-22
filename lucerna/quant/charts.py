"""Visual computation + rendering.

`compute(df, visual)` does the deterministic aggregation (the numbers shown) and returns a
VisualData with the table, base N and notes. `figure(visual, data, mode)` only draws what was
computed, so chart values can be validated against `compute()` in tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import stats
from .palette import CATEGORICAL, DARK_THEMES, DIVERGING, INK, MAX_CATEGORIES, OTHER, SEQUENTIAL, SURFACE
from .transform import condition_mask

LIKERT_SCALES = [
    ["Very dissatisfied", "Dissatisfied", "Neutral", "Satisfied", "Very satisfied"],
    ["Strongly disagree", "Disagree", "Neither agree nor disagree", "Agree", "Strongly agree"],
    ["Very poor", "Poor", "Fair", "Good", "Very good"],
    ["Very unsafe", "Unsafe", "Neutral", "Safe", "Very safe"],
    ["Not at all", "A little", "Somewhat", "Mostly", "Completely"],
]

VISUAL_TYPES = {
    "kpi": "KPI card", "bar": "Bar chart", "stacked100": "100% stacked bar", "likert": "Diverging Likert bar",
    "multiselect": "Multiple-response bar", "donut": "Donut (≤5 categories)", "histogram": "Histogram", "box": "Box plot",
    "line": "Line / trend", "area_stacked": "Stacked area", "forecast": "Forecast with uncertainty", "heatmap": "Heatmap",
    "treemap": "Treemap", "pyramid": "Population pyramid", "scatter": "Scatter plot", "sankey": "Sankey flow",
    "map_points": "Point map", "choropleth": "Choropleth map", "table": "Summary table", "text": "Text / insight panel",
    "correlation": "Correlation matrix", "stat_summary": "Statistical summary", "quality_missing": "Missingness by column",
    "multiline": "Multi-measure trend", "methodology": "Methodology panel", "compare_table": "Group comparison table (with significance tests)",
}
NA_PATTERN = r"^\s*(not applicable|n/?a|na|skip(ped)?|not asked|no answer|don'?t know|refused|prefer not to (say|answer))\b"


class Unsupported(Exception):
    """Raised when the data cannot support a visual. The message is shown instead of a chart."""


@dataclass
class VisualData:
    table: pd.DataFrame
    base_n: int | None = None
    notes: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------- helpers

def likert_order(values: list[str]) -> list[str] | None:
    low = {str(v).strip().lower(): v for v in values}
    for scale in LIKERT_SCALES:
        sl = [s.lower() for s in scale]
        if set(low) <= set(sl) and len(low) >= 3:
            return [low[s] for s in sl if s in low]
    return None


def apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    if not filters:
        return df
    mask = pd.Series(True, index=df.index)
    for col, f in filters.items():
        if col not in df.columns or not f:
            continue
        if "values" in f and f["values"]:
            mask &= df[col].astype("string").isin([str(v) for v in f["values"]]).fillna(False)
        if "range" in f and f["range"]:
            lo, hi = f["range"]
            s = df[col]
            if pd.api.types.is_datetime64_any_dtype(s):
                lo, hi = pd.to_datetime(lo), pd.to_datetime(hi) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            mask &= ((s >= lo) & (s <= hi)).fillna(False)
    return df.loc[mask]


def stable_categories(series_full: pd.Series) -> list[str]:
    """Category order from the FULL (unfiltered) data, so colour follows the entity not its rank."""
    order = likert_order(list(series_full.dropna().astype(str).unique()))
    if order:
        return order
    return list(series_full.dropna().astype(str).value_counts().index)


def color_map(categories: list[str], mode: str = "light") -> dict[str, str]:
    pal = CATEGORICAL[mode]
    cmap = {c: pal[i] for i, c in enumerate(categories[:MAX_CATEGORIES])}
    cmap["Other"] = OTHER[mode]
    return cmap


def _fold(s: pd.Series, keep: list[str]) -> pd.Series:
    s = s.astype("string")
    return s.where(s.isin(keep) | s.isna(), "Other")


def _measure(g: pd.DataFrame, v: dict) -> float | None:
    m = v.get("measure", "count")
    if m == "count":
        return float(len(g))
    if m == "unique":
        return float(g[v["value"]].dropna().nunique())
    if m == "pct_condition":
        cond = v["condition"]
        valid = g[cond["column"]].notna()
        if valid.sum() == 0:
            return None
        return float(100 * (condition_mask(g, **cond) & valid).sum() / valid.sum())
    col = pd.to_numeric(g[v["value"]], errors="coerce").dropna()
    if col.empty:
        return None
    return float({"mean": col.mean, "median": col.median, "sum": col.sum}[m]())


def measure_label(v: dict) -> str:
    m = v.get("measure", "count")
    if m == "count":
        return v.get("unit_label") or "Records"
    if m == "pct_condition":
        return "% of valid responses"
    if m == "unique":
        return f"Unique {v.get('value')}"
    return f"{m.title()} of {v.get('value')}"


# ---------------------------------------------------------------- compute

def compute(df: pd.DataFrame, v: dict, full: pd.DataFrame | None = None) -> VisualData:
    t = v["type"]
    full = df if full is None else full
    need = [c for c in (v.get("x"), v.get("color"), v.get("value"), v.get("date"), v.get("by"), v.get("lat"), v.get("lon"),
                        v.get("source"), v.get("target"), v.get("sex"), v.get("age"), v.get("y")) if c]
    need += [c for c in v.get("path", []) + v.get("columns", []) + v.get("outcomes_cols", []) if c]
    if v.get("condition"):
        need.append(v["condition"]["column"])
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise Unsupported(f"Column(s) not in this dataset: {', '.join(missing)}")
    if len(df) == 0:
        raise Unsupported("No records match the current filters.")
    fn = globals().get(f"_c_{t}")
    if fn is None:
        raise Unsupported(f"Unknown visual type '{t}'.")
    excluded = []
    for col, vals in (v.get("exclude_values") or {}).items():
        if col in df.columns and vals:
            drop = df[col].astype("string").isin([str(x) for x in vals]).fillna(False)
            if drop.any():
                excluded.append(f"{int(drop.sum()):,} record(s) with '{', '.join(map(str, vals[:3]))}' in {col} are excluded from this visual's denominator")
                df = df.loc[~drop]
                full = full.loc[~full[col].astype("string").isin([str(x) for x in vals]).fillna(False)] if col in full.columns else full
    if len(df) == 0:
        raise Unsupported("No applicable records under the current filters.")
    data = fn(df, v, full)
    data.notes = excluded + data.notes
    return data


def not_applicable_values(s: pd.Series) -> list[str]:
    """Values that mean 'question not asked / not applicable' — excluded from denominators, never silently dropped."""
    vals = s.dropna().astype(str).unique()
    return [x for x in vals if re.match(NA_PATTERN, x, flags=re.I)][:5]


def _c_kpi(df, v, full):
    k = v.get("kpi", "count_rows")
    if k == "count_rows":
        val, base = len(df), len(df)
    elif k == "unique":
        val, base = int(df[v["value"]].dropna().nunique()), int(df[v["value"]].notna().sum())
    elif k == "pct":
        r = stats.binary_rate(df, condition_mask(df, **v["condition"]), df[v["condition"]["column"]].notna())
        val, base = r["pct"], r["denominator"]
    elif k in ("mean", "median", "sum"):
        col = pd.to_numeric(df[v["value"]], errors="coerce").dropna()
        val, base = (float(getattr(col, k)()) if len(col) else None), int(col.size)
    elif k == "date_span":
        d = pd.to_datetime(df[v["value"]], errors="coerce").dropna()
        if d.empty:
            raise Unsupported("No valid dates.")
        return VisualData(pd.DataFrame({"value": [f"{d.min():%d %b %Y} – {d.max():%d %b %Y}"]}), int(d.size), extra={"text": True})
    elif k == "n_categories":
        val, base = int(df[v["value"]].dropna().nunique()), int(df[v["value"]].notna().sum())
    elif k == "duplicates":
        s = df[v["value"]].dropna().astype(str)
        val, base = int(s.duplicated(keep=False).sum()), int(s.size)
    elif k == "completeness":
        val = float(100 * (1 - df.isna().sum().sum() / max(1, df.size)))
        base = len(df)
    else:
        raise Unsupported(f"Unknown KPI {k}")
    return VisualData(pd.DataFrame({"value": [val]}), base)


def _c_bar(df, v, full):
    x = v["x"]
    keep = stable_categories(full[x])
    top = int(v.get("top_n") or 12)
    if v.get("color"):
        ckeep = stable_categories(full[v["color"]])[:MAX_CATEGORIES]
        d = df.assign(__c=_fold(df[v["color"]], ckeep))
        rows = []
        for (xv, cv), g in d.dropna(subset=[x, "__c"]).groupby([d[x].astype("string"), "__c"], observed=True):
            rows.append({"x": str(xv), "series": str(cv), "value": _measure(g, v), "n": len(g)})
        tab = pd.DataFrame(rows)
        if tab.empty:
            raise Unsupported("No data for this combination.")
        if v.get("measure", "count") == "count" and v.get("normalize"):
            tab["value"] = 100 * tab["value"] / tab.groupby("x")["value"].transform("sum")
    else:
        rows = [{"x": str(xv), "value": _measure(g, v), "n": len(g)} for xv, g in df.dropna(subset=[x]).groupby(df[x].astype("string"), observed=True)]
        tab = pd.DataFrame(rows)
        if tab.empty:
            raise Unsupported("No non-missing values.")
        if v.get("measure", "count") == "count" and v.get("as_pct"):
            tab["value"] = 100 * tab["value"] / tab["value"].sum()
    order = [c for c in keep if c in set(tab["x"])]
    if v.get("sort", "value") == "value" and not likert_order(order):
        totals = tab.groupby("x")["value"].sum().sort_values(ascending=False)
        order = list(totals.index)
    order = order[:top]
    tab = tab[tab["x"].isin(order)].copy()
    tab["__o"] = tab["x"].map({k: i for i, k in enumerate(order)})
    tab = tab.sort_values("__o").drop(columns="__o")
    notes = []
    small = tab[tab["n"] < 30]
    if v.get("measure") in ("pct_condition", "mean", "median") and len(small):
        notes.append(f"{len(small)} bar(s) are based on fewer than 30 records; interpret with caution.")
    if df[x].astype("string").nunique() > top:
        notes.append(f"Showing the top {top} of {df[x].nunique()} categories.")
    return VisualData(tab.reset_index(drop=True), int(df[x].notna().sum()), notes, {"order": order})


def _c_stacked100(df, v, full):
    v2 = {**v, "measure": "count", "normalize": True}
    return _c_bar(df, v2, full)


def _c_donut(df, v, full):
    data = _c_bar(df, {**v, "measure": "count", "sort": "value", "top_n": 6}, full)
    if len(data.table) > 5:
        raise Unsupported("Too many categories for a donut; use a bar chart.")
    data.table["pct"] = 100 * data.table["value"] / data.table["value"].sum()
    return data


def _c_likert(df, v, full):
    col = v["x"]
    cats = list(full[col].dropna().astype(str).unique())
    order = v.get("order") or likert_order(cats)
    if not order:
        raise Unsupported(f"'{col}' does not match a known ordered scale; set the category order to use a Likert chart.")
    by = v.get("by")
    groups = [("All respondents", df)] if not by else [(str(k), g) for k, g in df.groupby(df[by].astype("string"), observed=True)]
    rows = []
    for name, g in groups:
        s = g[col].astype("string").dropna()
        n = len(s)
        for cat in order:
            rows.append({"group": name, "category": cat, "pct": 100 * (s == cat).sum() / n if n else None, "n": n})
    return VisualData(pd.DataFrame(rows), int(df[col].notna().sum()), extra={"order": order})


def _c_multiselect(df, v, full):
    if v.get("columns"):
        f = stats.frequency(df, v.get("x") or "multiple", multiselect_columns=v["columns"])
    else:
        f = stats.frequency(df, v["x"], multiselect_sep=v.get("sep", " "))
    tab = f["table"].rename(columns={"value": "x"})
    return VisualData(tab.head(int(v.get("top_n") or 15)), f["base_n"], [f["note"]])


def _c_histogram(df, v, full):
    s = pd.to_numeric(df[v["value"]], errors="coerce").dropna()
    if len(s) < 5:
        raise Unsupported("Fewer than 5 numeric values.")
    d = stats.describe_numeric(s)
    return VisualData(pd.DataFrame({"value": s}), int(s.size), extra={"describe": d, "bins": int(v.get("bins") or 0) or None})


def _c_box(df, v, full):
    by = v.get("by")
    sub = df[[v["value"]] + ([by] if by else [])].copy()
    sub[v["value"]] = pd.to_numeric(sub[v["value"]], errors="coerce")
    sub = sub.dropna()
    if len(sub) < 5:
        raise Unsupported("Fewer than 5 numeric values.")
    notes = []
    if by:
        keep = stable_categories(full[by])[:MAX_CATEGORIES]
        sub[by] = _fold(sub[by], keep)
        res = stats.compare_groups(sub, v["value"], by)
        for t in res["tests"]:
            if t.get("appropriate") and t.get("p_value") is not None:
                notes.append(f"{t['name']}: " + ("p < 0.001" if t['p_value'] < 0.001 else f"p = {t['p_value']:.3f}"))
                break
        notes += res["caveats"][:1]
    return VisualData(sub, int(len(sub)), notes)


def _ts(df, v):
    agg = v.get("measure", "count")
    if agg == "pct_condition":
        d = df.assign(__hit=condition_mask(df, **v["condition"]).astype(float).where(df[v["condition"]["column"]].notna()))
        ts = stats.time_series(d, v["date"], v.get("freq", "month"), "__hit", "mean")
        ts["value"] = ts["value"] * 100
        ts["moving_average"] = ts["moving_average"] * 100
        return ts
    return stats.time_series(df, v["date"], v.get("freq", "month"), v.get("value"), "count" if agg == "count" else agg)


def _c_line(df, v, full):
    if v.get("color"):
        keep = stable_categories(full[v["color"]])[:5]
        parts = []
        for k in keep:
            g = df[df[v["color"]].astype("string") == k]
            if len(g):
                parts.append(_ts(g, v).assign(series=k))
        if not parts:
            raise Unsupported("No dated records.")
        tab = pd.concat(parts)
    else:
        tab = _ts(df, v)
    n_periods = tab["period"].nunique()
    if n_periods < 2:
        raise Unsupported("Fewer than two time periods in the data; a trend cannot be shown.")
    notes = []
    if n_periods < 4:
        notes.append(f"Only {n_periods} periods: treat apparent trends with caution.")
    an = stats.anomalies(tab) if not v.get("color") and len(tab) >= 8 else None
    return VisualData(tab, int(pd.to_datetime(df[v["date"]], errors="coerce").notna().sum()), notes,
                      {"anomalies": an})


def _c_area_stacked(df, v, full):
    return _c_line(df, {**v, "measure": "count"}, full)


def _c_forecast(df, v, full):
    tab = _ts(df, v)
    fc = stats.forecast(tab, int(v.get("horizon") or 3), int(v.get("min_obs") or 12))
    if not fc["available"]:
        raise Unsupported(fc["reason"])
    return VisualData(tab, int(len(df)), [fc["note"], f"Method: {fc['method']}"], {"forecast": fc["forecast"]})


def _c_heatmap(df, v, full):
    rows_col = v["x"]
    keep_rows = stable_categories(full[rows_col])[:15]
    if v.get("conditions"):
        out = {}
        for cond in v["conditions"]:
            label = cond.get("label") or cond["column"]
            vals = {}
            for k in keep_rows:
                g = df[df[rows_col].astype("string") == k]
                valid = g[cond["column"]].notna()
                vals[k] = 100 * (condition_mask(g, **{kk: cond[kk] for kk in ("column", "op", "value")}) & valid).sum() / valid.sum() if valid.sum() else np.nan
            out[label] = vals
        mat = pd.DataFrame(out)
        counts = df[rows_col].astype("string").value_counts()
        return VisualData(mat, int(df[rows_col].notna().sum()), ["Cells show % of valid responses in each row group."], {"row_n": counts.to_dict(), "pct": True})
    ct = stats.crosstab(df, rows_col, v["y"], normalize=v.get("normalize", "row"))
    mat = ct["percent"]
    mat = mat.loc[[r for r in keep_rows if r in mat.index]]
    notes = []
    if ct["test"]:
        tst = ct["test"]
        notes.append(f"{tst['name']}: p = {tst['p_value']:.3g}" + (f"; {tst.get('caveat')}" if tst.get("caveat") else ""))
    return VisualData(mat, ct["n"], notes, {"pct": True})


def _c_treemap(df, v, full):
    path = [p for p in v["path"] if p in df.columns]
    sub = df[path].astype("string").dropna()
    if sub.empty:
        raise Unsupported("No complete geographic hierarchy values.")
    tab = sub.groupby(path, observed=True).size().reset_index(name="value")
    return VisualData(tab, int(len(sub)), [f"{len(df) - len(sub)} record(s) with incomplete location excluded."] if len(df) > len(sub) else [])


def _c_pyramid(df, v, full):
    t = stats.population_pyramid(df, v["sex"], age_col=v.get("age"), age_group_col=v.get("age_group"))
    if t.empty or t.shape[1] < 2:
        raise Unsupported("A pyramid needs at least two sex categories with age data.")
    return VisualData(t, int(t.values.sum()))


def _c_scatter(df, v, full):
    sub = df[[v["x"], v["y"]] + ([v["color"]] if v.get("color") else [])].copy()
    sub[v["x"]] = pd.to_numeric(sub[v["x"]], errors="coerce")
    sub[v["y"]] = pd.to_numeric(sub[v["y"]], errors="coerce")
    sub = sub.dropna(subset=[v["x"], v["y"]])
    if len(sub) < 10:
        raise Unsupported("Fewer than 10 complete pairs.")
    c = stats.correlation(sub, [v["x"], v["y"]], "spearman")["pairs"].iloc[0]
    notes = [f"Spearman ρ = {c['r']:.2f} (p = {c['p_value']:.3g}, n = {int(c['n'])}). {stats.CAUSATION_NOTE}"] if c["r"] is not None else []
    if len(sub) > 5000:
        sub = sub.sample(5000, random_state=1)
        notes.append("Showing a random sample of 5,000 points.")
    return VisualData(sub, int(len(sub)), notes)


def _c_sankey(df, v, full):
    steps = [c for c in [v["source"], v.get("via"), v["target"]] if c]
    sub = df[steps].astype("string").dropna()
    if sub.empty:
        raise Unsupported("No complete flows.")
    weight = v.get("value")
    links = []
    for a, b in zip(steps, steps[1:]):
        g = sub.assign(__w=pd.to_numeric(df.loc[sub.index, weight], errors="coerce").fillna(0) if weight else 1).groupby([a, b], observed=True)["__w"].sum().reset_index()
        g.columns = ["source", "target", "value"]
        g["source"] = a + ": " + g["source"]
        g["target"] = b + ": " + g["target"]
        links.append(g)
    tab = pd.concat(links)
    return VisualData(tab, int(len(sub)), [f"Flow width = {'sum of ' + weight if weight else 'number of records'}."])


def _c_map_points(df, v, full):
    sub = df[[v["lat"], v["lon"]] + [c for c in (v.get("color"),) if c]].copy()
    sub[v["lat"]] = pd.to_numeric(sub[v["lat"]], errors="coerce")
    sub[v["lon"]] = pd.to_numeric(sub[v["lon"]], errors="coerce")
    valid = sub[v["lat"]].between(-90, 90) & sub[v["lon"]].between(-180, 180)
    excluded = int((~valid).sum())
    sub = sub[valid]
    if sub.empty:
        raise Unsupported("No valid coordinates in the data.")
    notes = ["Points are the coordinates recorded in the dataset; none are estimated."]
    if excluded:
        notes.append(f"{excluded} record(s) without valid coordinates are not shown.")
    return VisualData(sub, int(len(sub)), notes)


def _c_choropleth(df, v, full):
    geo = v.get("geojson")
    if not geo:
        raise Unsupported("A choropleth needs an administrative boundary file (GeoJSON) uploaded for this project. "
                          "Lucerna does not invent boundaries — upload an official boundary set (e.g., OCHA COD-AB from HDX).")
    key = v.get("feature_name_property", "name")
    names = {str(f["properties"].get(key, "")).strip().lower(): f["properties"].get(key) for f in geo.get("features", [])}
    data = _c_bar(df, {**v, "top_n": 10_000, "sort": "name"}, full).table
    data["match"] = data["x"].str.strip().str.lower().map(names)
    unmatched = data[data["match"].isna()]["x"].tolist()
    notes = []
    if unmatched:
        notes.append(f"{len(unmatched)} location name(s) did not match the boundary file and are not mapped: {', '.join(unmatched[:8])}")
    return VisualData(data.dropna(subset=["match"]), None, notes, {"geojson": geo, "key": key})


def _c_table(df, v, full):
    by = v.get("by")
    cols = v.get("columns") or []
    if not by:
        return VisualData(df[cols].head(int(v.get("limit") or 200)) if cols else df.head(200), len(df))
    rows = []
    for k, g in df.groupby(df[by].astype("string"), observed=True):
        r = {by: k, "records": len(g)}
        for c in cols:
            if pd.api.types.is_numeric_dtype(g[c]) and not pd.api.types.is_bool_dtype(g[c]):
                if v.get("agg") == "sum":
                    r[f"total {c}"] = int(g[c].sum()) if g[c].notna().any() else None
                else:
                    r[f"mean {c}"] = round(float(g[c].mean()), 2) if g[c].notna().any() else None
            elif pd.api.types.is_bool_dtype(g[c]):
                r[f"% {c}"] = round(100 * float(g[c].astype("float").mean()), 1) if g[c].notna().any() else None
        rows.append(r)
    return VisualData(pd.DataFrame(rows).sort_values("records", ascending=False), len(df))


def _c_methodology(df, v, full):
    return VisualData(pd.DataFrame(), len(df))


def _c_text(df, v, full):
    return VisualData(pd.DataFrame(), None, extra={"markdown": v.get("markdown", "")})


def _c_correlation(df, v, full):
    cols = [c for c in v["columns"] if pd.api.types.is_numeric_dtype(df[c])]
    if len(cols) < 2:
        raise Unsupported("At least two numeric columns are needed.")
    c = stats.correlation(df, cols, v.get("method", "spearman"))
    return VisualData(c["matrix"], int(len(df)), [f"{c['method'].title()} correlation. {c['note']}"], {"pairs": c["pairs"]})


def _c_stat_summary(df, v, full):
    rows = []
    for c in v["columns"]:
        d = stats.describe_numeric(df[c])
        rows.append({"variable": c, **{k: (round(val, 2) if isinstance(val, float) else val) for k, val in d.items() if k in
                                       ("n_valid", "n_missing", "mean", "median", "std", "min", "p25", "p75", "max")}})
    return VisualData(pd.DataFrame(rows), int(len(df)))


def _c_quality_missing(df, v, full):
    miss = (100 * df.isna().mean()).sort_values(ascending=False)
    miss = miss[miss > 0].head(25)
    if miss.empty:
        raise Unsupported("No missing values in any column.")
    return VisualData(pd.DataFrame({"x": miss.index, "value": miss.values}), len(df), ["% of records missing a value, by column."])


def _c_multiline(df, v, full):
    cols = [c for c in v["columns"] if c in df.columns]
    parts = []
    for c in cols:
        ts = stats.time_series(df, v["date"], v.get("freq", "day"), c, v.get("agg", "sum"))
        parts.append(ts[["period", "value"]].assign(series=c))
    if not parts:
        raise Unsupported("No numeric columns to plot over time.")
    tab = pd.concat(parts)
    if tab["period"].nunique() < 2:
        raise Unsupported("Fewer than two time periods in the data; a trend cannot be shown.")
    return VisualData(tab, int(pd.to_datetime(df[v["date"]], errors="coerce").notna().sum()),
                      [f"Each line is the {v.get('agg', 'sum')} of the column per {v.get('freq', 'day')}."])


def _c_compare_table(df, v, full):
    """Outcomes compared across the groups of one variable, each with the appropriate significance test."""
    by = v["by"]
    keep = stable_categories(full[by])[:MAX_CATEGORIES]
    sub = df[df[by].astype("string").isin(keep)]
    rows = []
    for o in v.get("outcomes", []):
        col = o["column"]
        if col not in sub.columns:
            continue
        r = {"Outcome": o.get("label") or col}
        if o["kind"] == "binary":
            cond = {"column": col, "op": "in", "value": o.get("value") or ["yes", "true", "1"]}
            counts = []
            for g in keep:
                gg = sub[sub[by].astype("string") == g]
                valid = gg[col].notna()
                hit = int((condition_mask(gg, **cond) & valid).sum())
                n = int(valid.sum())
                r[str(g)] = f"{100 * hit / n:.1f}%" if n else "–"
                counts.append((hit, n))
            obs = [[h, n - h] for h, n in counts if n]
            test = None
            if len(obs) >= 2 and all(sum(x) for x in zip(*obs)):
                from scipy.stats import chi2_contingency
                chi = chi2_contingency(obs)
                test = ("Chi-square", float(chi.pvalue), bool((chi.expected_freq >= 5).all()))
        else:
            res = stats.compare_groups(sub, col, by)
            summ = res["summary"].set_index("group") if len(res["summary"]) else None
            for g in keep:
                r[str(g)] = (f"{summ.loc[str(g), 'median']:,.1f}" if summ is not None and str(g) in summ.index and summ.loc[str(g), "median"] is not None else "–")
            t = next((t for t in res["tests"] if "Kruskal" in t["name"] or "Mann" in t["name"]), None)
            test = (t["name"].split(" (")[0], t["p_value"], True) if t and t.get("p_value") is not None else None
            r["Outcome"] += " (median)"
        if test:
            r["Test"] = test[0]
            r["p-value"] = "p < 0.001" if test[1] < 0.001 else f"p = {test[1]:.3f}"
            r["Difference"] = ("significant (p<0.05)" if test[1] < 0.05 else "not significant") + ("" if test[2] else "; small expected counts")
        else:
            r["Test"], r["p-value"], r["Difference"] = "–", "–", "not testable"
        rows.append(r)
    if not rows:
        raise Unsupported("No outcomes could be compared.")
    return VisualData(pd.DataFrame(rows), int(sub[by].notna().sum()),
                      ["Percentages use valid responses in each group as the denominator. " + stats.CAUSATION_NOTE])


# ---------------------------------------------------------------- figures

def _base_layout(fig, mode: str, title: str | None = None, height: int = 340):
    ink = INK[mode]
    fig.update_layout(
        template="none", height=height, margin=dict(l=8, r=8, t=36 if title else 10, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Vazirmatn, 'Segoe UI', 'Noto Sans Arabic', sans-serif", size=12, color=ink["secondary"]),
        title=dict(text=title, font=dict(size=13, color=ink["primary"]), x=0, xanchor="left") if title else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=ink["secondary"]), title=None),
        hoverlabel=dict(bgcolor=SURFACE[mode], bordercolor=ink["grid"], font=dict(color=ink["primary"], size=12)),
        bargap=0.28, bargroupgap=0.06,
    )
    fig.update_xaxes(showgrid=False, linecolor=ink["grid"], tickfont=dict(color=ink["muted"]), zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=ink["grid"], gridwidth=1, linecolor=ink["grid"], tickfont=dict(color=ink["muted"]), zeroline=False, automargin=True)
    return fig


def _fmt(val: float | None, pct: bool = False) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "–"
    if pct:
        return f"{val:.1f}%"
    if abs(val) >= 1000:
        return f"{val:,.0f}"
    return f"{val:,.2f}".rstrip("0").rstrip(".") if val % 1 else f"{val:,.0f}"


def figure(v: dict, data: VisualData, mode: str = "light", full: pd.DataFrame | None = None):
    import plotly.graph_objects as go
    t = v["type"]
    pal = CATEGORICAL[mode]
    ink = INK[mode]
    surface = SURFACE[mode]
    tab = data.table
    is_pct = v.get("measure") == "pct_condition" or v.get("as_pct") or v.get("normalize") or t == "stacked100"
    title = None
    fig = go.Figure()
    if t == "quality_missing":
        tab = tab.assign(n=data.base_n)
        data = VisualData(tab, data.base_n, data.notes)
        return figure({**v, "type": "bar", "as_pct": True, "orientation": "h", "measure": "count"}, data, mode, full)

    if t in ("bar", "stacked100"):
        horizontal = v.get("orientation") == "h" or (v.get("orientation") != "v" and (tab["x"].str.len().max() > 12 or tab["x"].nunique() > 6))
        if "series" in tab.columns:
            cats = stable_categories(full[v["color"]]) if full is not None and v.get("color") in full else list(tab["series"].unique())
            cmap = color_map(cats, mode)
            for s in [c for c in cats + ["Other"] if c in set(tab["series"])]:
                part = tab[tab["series"] == s]
                kw = dict(y=part["x"], x=part["value"], orientation="h") if horizontal else dict(x=part["x"], y=part["value"])
                fig.add_bar(name=s, marker=dict(color=cmap.get(s, OTHER[mode]), line=dict(color=surface, width=1.5), cornerradius=4),
                            customdata=part[["n"]], hovertemplate=f"%{{{'y' if horizontal else 'x'}}}<br>{s}: %{{{'x' if horizontal else 'y'}:.1f}}{'%' if is_pct else ''}<br>n = %{{customdata[0]}}<extra></extra>", **kw)
            fig.update_layout(barmode="stack" if (v.get("stacked") or t == "stacked100") else "group")
            fig.update_layout(legend_traceorder="normal")
        else:
            color = pal[0] if not v.get("highlight") else [pal[0] if x == v["highlight"] else OTHER[mode] for x in tab["x"]]
            kw = dict(y=tab["x"], x=tab["value"], orientation="h") if horizontal else dict(x=tab["x"], y=tab["value"])
            fig.add_bar(marker=dict(color=color, cornerradius=4), customdata=tab[["n"]],
                        text=[_fmt(x, is_pct) for x in tab["value"]], textposition="outside", cliponaxis=False,
                        textfont=dict(color=ink["secondary"], size=11),
                        hovertemplate=f"%{{{'y' if horizontal else 'x'}}}: %{{{'x' if horizontal else 'y'}:,.1f}}{'%' if is_pct else ''}<br>n = %{{customdata[0]}}<extra></extra>", **kw)
            fig.update_layout(showlegend=False)
        if horizontal:
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=True, gridcolor=ink["grid"], title=measure_label(v) if not is_pct else "%")
        else:
            fig.update_yaxes(title=measure_label(v) if not is_pct else "%")
        if is_pct:
            (fig.update_xaxes if horizontal else fig.update_yaxes)(range=[0, 105] if tab["value"].max() <= 100 else None, ticksuffix="%")
        h = max(260, min(620, 34 * tab["x"].nunique() + 90)) if horizontal else 340
        return _base_layout(fig, mode, title, h)

    if t == "donut":
        cats = stable_categories(full[v["x"]]) if full is not None else list(tab["x"])
        cmap = color_map(cats, mode)
        fig.add_pie(labels=tab["x"], values=tab["value"], hole=.62, sort=False, direction="clockwise",
                    marker=dict(colors=[cmap.get(x, OTHER[mode]) for x in tab["x"]], line=dict(color=surface, width=2)),
                    textinfo="percent", textfont=dict(color="#FFFFFF"), hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>")
        fig.update_layout(showlegend=True, legend=dict(orientation="v", x=1, y=.5))
        return _base_layout(fig, mode, title, 300)

    if t == "likert":
        order = data.extra["order"]
        k = len(order)
        neg = [DIVERGING["neg"], DIVERGING["neg2"]]
        pos = [DIVERGING["pos2"], DIVERGING["pos"]]
        mid = DIVERGING["mid"][mode]
        colors = (neg[: k // 2] if k // 2 <= 2 else neg) + ([mid] if k % 2 else []) + pos[-(k // 2):]
        for i, cat in enumerate(order):
            part = tab[tab["category"] == cat]
            sign = -1 if i < k // 2 else 1
            vals = part["pct"] * sign
            if k % 2 and i == k // 2:
                # neutral split across the axis
                fig.add_bar(name=cat, y=part["group"], x=-part["pct"] / 2, orientation="h", marker=dict(color=colors[i], line=dict(color=surface, width=1.5)),
                            hovertemplate=f"{cat}: %{{customdata:.1f}}%<extra></extra>", customdata=part["pct"], showlegend=False, base=0)
                fig.add_bar(name=cat, y=part["group"], x=part["pct"] / 2, orientation="h", marker=dict(color=colors[i], line=dict(color=surface, width=1.5)),
                            hovertemplate=f"{cat}: %{{customdata:.1f}}%<extra></extra>", customdata=part["pct"], base=0)
                continue
            fig.add_bar(name=cat, y=part["group"], x=vals, orientation="h", marker=dict(color=colors[i], line=dict(color=surface, width=1.5)),
                        customdata=part["pct"], hovertemplate=f"%{{y}} · {cat}: %{{customdata:.1f}}%<extra></extra>")
        fig.update_layout(barmode="relative")
        fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=ink["grid"], zeroline=True, zerolinecolor=ink["muted"])
        fig.update_yaxes(showgrid=False)
        return _base_layout(fig, mode, title, max(220, 46 * tab["group"].nunique() + 120))

    if t == "multiselect":
        fig.add_bar(y=tab["x"], x=tab["pct"], orientation="h", marker=dict(color=pal[1], cornerradius=4), customdata=tab[["n"]],
                    text=[f"{x:.1f}%" for x in tab["pct"]], textposition="outside", cliponaxis=False, textfont=dict(color=ink["secondary"]),
                    hovertemplate="%{y}: %{x:.1f}% of respondents (n = %{customdata[0]})<extra></extra>")
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=ink["grid"], title="% of respondents (multiple answers allowed)")
        fig.update_layout(showlegend=False)
        return _base_layout(fig, mode, title, max(260, 32 * len(tab) + 90))

    if t == "histogram":
        d = data.extra["describe"]
        fig.add_histogram(x=tab["value"], nbinsx=data.extra.get("bins") or None, marker=dict(color=pal[1], line=dict(color=surface, width=1.5)),
                          hovertemplate="%{x}: %{y} records<extra></extra>")
        for name, val, dash in (("Median", d.get("median"), "solid"), ("Mean", d.get("mean"), "dot")):
            if val is not None:
                fig.add_vline(x=val, line=dict(color=ink["primary"], width=1.5, dash=dash),
                              annotation=dict(text=f"{name} {_fmt(val)}", font=dict(size=11, color=ink["secondary"])), annotation_position="top")
        fig.update_layout(showlegend=False, bargap=0.04)
        fig.update_yaxes(title="Records")
        fig.update_xaxes(title=v["value"])
        return _base_layout(fig, mode, title)

    if t == "box":
        by = v.get("by")
        if by:
            cats = stable_categories(full[by])[:MAX_CATEGORIES] if full is not None else list(tab[by].unique())
            cmap = color_map(cats, mode)
            for c in [c for c in cats + ["Other"] if c in set(tab[by])]:
                part = tab[tab[by] == c]
                fig.add_box(y=part[v["value"]], name=c, marker=dict(color=cmap.get(c), size=4), line=dict(width=1.5), boxmean=True)
        else:
            fig.add_box(y=tab[v["value"]], name=v["value"], marker=dict(color=pal[1], size=4), boxmean=True)
        fig.update_layout(showlegend=False)
        fig.update_yaxes(title=v["value"])
        return _base_layout(fig, mode, title)

    if t in ("line", "area_stacked"):
        pct = v.get("measure") == "pct_condition"
        if "series" in tab.columns:
            cats = stable_categories(full[v["color"]])[:5] if full is not None else list(tab["series"].unique())
            cmap = color_map(cats, mode)
            for s in cats:
                part = tab[tab["series"] == s]
                if part.empty:
                    continue
                fig.add_scatter(x=part["period"], y=part["value"], name=s, mode="lines", line=dict(color=cmap[s], width=2),
                                stackgroup="one" if t == "area_stacked" else None,
                                hovertemplate=f"{s}: %{{y:,.1f}}{'%' if pct else ''}<extra></extra>")
        else:
            fig.add_scatter(x=tab["period"], y=tab["value"], name=measure_label(v), mode="lines+markers", line=dict(color=pal[0], width=2),
                            marker=dict(size=8, color=pal[0], line=dict(color=surface, width=2)),
                            hovertemplate=f"%{{y:,.1f}}{'%' if pct else ''}<extra></extra>")
            if v.get("moving_average", True) and tab["moving_average"].notna().any():
                fig.add_scatter(x=tab["period"], y=tab["moving_average"], name="3-period moving average", mode="lines",
                                line=dict(color=ink["muted"], width=2, dash="dot"), hovertemplate="MA: %{y:,.1f}<extra></extra>")
            an = data.extra.get("anomalies")
            if an is not None and len(an):
                fig.add_scatter(x=an["period"], y=an["value"], name="Unusual period", mode="markers",
                                marker=dict(size=11, symbol="circle-open", color=CATEGORICAL[mode][2], line=dict(width=2)),
                                hovertemplate="Unusual value: %{y:,.1f}<extra></extra>")
        fig.update_layout(hovermode="x unified")
        fig.update_yaxes(title="%" if pct else measure_label(v), ticksuffix="%" if pct else None, rangemode="tozero")
        return _base_layout(fig, mode, title)

    if t == "multiline":
        for i, c in enumerate(v["columns"][:MAX_CATEGORIES]):
            part = tab[tab["series"] == c]
            if part.empty:
                continue
            fig.add_scatter(x=part["period"], y=part["value"], name=v.get("labels", {}).get(c, c), mode="lines",
                            line=dict(color=pal[i], width=2), hovertemplate=f"{v.get('labels', {}).get(c, c)}: %{{y:,.0f}}<extra></extra>")
        fig.update_layout(hovermode="x unified")
        fig.update_yaxes(title=v.get("y_title") or "Total", rangemode="tozero")
        return _base_layout(fig, mode, title)

    if t == "forecast":
        fc = data.extra["forecast"]
        fig.add_scatter(x=list(fc["period"]) + list(fc["period"])[::-1], y=list(fc["hi95"]) + list(fc["lo95"])[::-1], fill="toself",
                        fillcolor="rgba(71,120,232,0.12)", line=dict(width=0), name="95% interval", hoverinfo="skip")
        fig.add_scatter(x=list(fc["period"]) + list(fc["period"])[::-1], y=list(fc["hi80"]) + list(fc["lo80"])[::-1], fill="toself",
                        fillcolor="rgba(71,120,232,0.22)", line=dict(width=0), name="80% interval", hoverinfo="skip")
        fig.add_scatter(x=tab["period"], y=tab["value"], name="Observed", mode="lines+markers", line=dict(color=pal[0], width=2), marker=dict(size=7))
        fig.add_scatter(x=fc["period"], y=fc["forecast"], name="Forecast (projection)", mode="lines+markers",
                        line=dict(color=pal[1], width=2, dash="dash"), marker=dict(size=7, symbol="diamond"))
        fig.update_layout(hovermode="x unified")
        fig.update_yaxes(title=measure_label(v), rangemode="tozero")
        return _base_layout(fig, mode, title)

    if t in ("heatmap", "correlation"):
        corr = t == "correlation"
        z = tab.values.astype(float)
        if corr:
            colorscale = [[0, DIVERGING["neg"]], [0.5, DIVERGING["mid"][mode]], [1, DIVERGING["pos"]]]
            zmin, zmax = -1, 1
        else:
            colorscale = [[i / (len(SEQUENTIAL[mode]) - 1), c] for i, c in enumerate(SEQUENTIAL[mode])]
            zmin, zmax = 0, 100 if data.extra.get("pct") else None
        text = [[("–" if np.isnan(x) else (f"{x:.2f}" if corr else f"{x:.0f}%")) for x in row] for row in z]
        fig.add_heatmap(z=z, x=[str(c) for c in tab.columns], y=[str(i) for i in tab.index], colorscale=colorscale, zmin=zmin, zmax=zmax,
                        text=text, texttemplate="%{text}", textfont=dict(size=11), xgap=2, ygap=2,
                        hovertemplate="%{y} · %{x}: %{text}<extra></extra>", colorbar=dict(thickness=10, outlinewidth=0))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(side="top", tickangle=0 if max(len(str(c)) for c in tab.columns) < 14 else -30)
        return _base_layout(fig, mode, title, max(260, 36 * len(tab) + 110))

    if t == "treemap":
        path = [p for p in v["path"] if p in tab.columns]
        labels, parents, values, ids = [], [], [], []
        top = tab.groupby(path[0], observed=True)["value"].sum()
        cats = list(top.sort_values(ascending=False).index)
        cmap = color_map(cats, mode)
        colors = []
        for k, val in top.items():
            ids.append(k); labels.append(k); parents.append(""); values.append(int(val)); colors.append(cmap.get(k, OTHER[mode]))
        if len(path) > 1:
            for _, r in tab.iterrows():
                ids.append(f"{r[path[0]]}/{r[path[1]]}"); labels.append(r[path[1]]); parents.append(r[path[0]]); values.append(int(r["value"]))
                colors.append(cmap.get(r[path[0]], OTHER[mode]))
        fig.add_treemap(ids=ids, labels=labels, parents=parents, values=values, branchvalues="total", marker=dict(colors=colors, line=dict(color=surface, width=2)),
                        textinfo="label+value+percent root", hovertemplate="%{label}: %{value:,} (%{percentRoot:.1%})<extra></extra>")
        return _base_layout(fig, mode, title, 380)

    if t == "pyramid":
        cols = list(tab.columns)
        left, right = cols[0], cols[1]
        fig.add_bar(y=tab.index, x=-tab[left], name=left, orientation="h", marker=dict(color=pal[3], cornerradius=3),
                    customdata=tab[left], hovertemplate=f"%{{y}} · {left}: %{{customdata:,}}<extra></extra>")
        fig.add_bar(y=tab.index, x=tab[right], name=right, orientation="h", marker=dict(color=pal[0], cornerradius=3),
                    hovertemplate=f"%{{y}} · {right}: %{{x:,}}<extra></extra>")
        mx = float(tab[[left, right]].values.max())
        ticks = np.linspace(-mx, mx, 5)
        fig.update_layout(barmode="relative", bargap=0.12)
        fig.update_xaxes(tickvals=ticks, ticktext=[f"{abs(x):,.0f}" for x in ticks], showgrid=True, gridcolor=ink["grid"], title="Records")
        fig.update_yaxes(title="Age group", showgrid=False)
        return _base_layout(fig, mode, title, 360)

    if t == "scatter":
        if v.get("color"):
            cats = stable_categories(full[v["color"]])[:3] if full is not None else []
            cmap = color_map(cats, mode)
            for c in cats:
                part = tab[tab[v["color"]].astype("string") == c]
                fig.add_scatter(x=part[v["x"]], y=part[v["y"]], mode="markers", name=c,
                                marker=dict(size=8, color=cmap[c], opacity=.75, line=dict(color=surface, width=1)))
        else:
            fig.add_scatter(x=tab[v["x"]], y=tab[v["y"]], mode="markers", marker=dict(size=8, color=pal[1], opacity=.6, line=dict(color=surface, width=1)),
                            hovertemplate=f"{v['x']}: %{{x}}<br>{v['y']}: %{{y}}<extra></extra>", showlegend=False)
        fig.update_xaxes(title=v["x"], showgrid=True, gridcolor=ink["grid"])
        fig.update_yaxes(title=v["y"])
        return _base_layout(fig, mode, title)

    if t == "sankey":
        nodes = list(dict.fromkeys(list(tab["source"]) + list(tab["target"])))
        idx = {n: i for i, n in enumerate(nodes)}
        stage_names = [s for s in [v["source"], v.get("via"), v["target"]] if s]
        stage_color = {s: pal[i] for i, s in enumerate(stage_names)}
        fig.add_sankey(arrangement="snap",
                       node=dict(label=[n.split(": ", 1)[1] for n in nodes], pad=14, thickness=14, line=dict(color=surface, width=1),
                                 color=[stage_color.get(n.split(": ", 1)[0], OTHER[mode]) for n in nodes]),
                       link=dict(source=[idx[s] for s in tab["source"]], target=[idx[t_] for t_ in tab["target"]], value=tab["value"],
                                 color="rgba(123,135,148,0.25)", hovertemplate="%{source.label} → %{target.label}: %{value:,}<extra></extra>"))
        return _base_layout(fig, mode, title, 420)

    if t == "map_points":
        lat, lon = v["lat"], v["lon"]
        style = "carto-darkmatter" if mode in DARK_THEMES else "carto-positron"
        if v.get("color"):
            cats = stable_categories(full[v["color"]])[:MAX_CATEGORIES] if full is not None else []
            cmap = color_map(cats, mode)
            col = _fold(tab[v["color"]], cats)
            for c in cats + ["Other"]:
                part = tab[col == c]
                if len(part):
                    fig.add_scattermap(lat=part[lat], lon=part[lon], name=c, mode="markers", marker=dict(size=9, color=cmap.get(c, OTHER[mode]), opacity=.8))
        else:
            fig.add_scattermap(lat=tab[lat], lon=tab[lon], mode="markers", marker=dict(size=9, color=pal[0], opacity=.8), showlegend=False)
        fig.update_layout(map=dict(style=style, center=dict(lat=float(tab[lat].mean()), lon=float(tab[lon].mean())),
                                   zoom=v.get("zoom", 5)))
        return _base_layout(fig, mode, title, 440)

    if t == "choropleth":
        geo, key = data.extra["geojson"], data.extra["key"]
        fig.add_choroplethmap(geojson=geo, locations=tab["match"], z=tab["value"], featureidkey=f"properties.{key}",
                              colorscale=[[i / (len(SEQUENTIAL[mode]) - 1), c] for i, c in enumerate(SEQUENTIAL[mode])],
                              marker_line_color=surface, marker_line_width=1, colorbar=dict(thickness=10, outlinewidth=0),
                              hovertemplate="%{location}: %{z:,.1f}<extra></extra>")
        fig.update_layout(map=dict(style="carto-darkmatter" if mode in DARK_THEMES else "carto-positron", zoom=v.get("zoom", 4.5),
                                   center=v.get("center") or dict(lat=34, lon=66)))
        return _base_layout(fig, mode, title, 460)

    raise Unsupported(f"No figure renderer for {t}")
