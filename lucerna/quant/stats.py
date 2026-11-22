"""Deterministic statistics (pandas / numpy / scipy / statsmodels).

All functions return plain dicts / DataFrames with explicit bases (N), missing counts and,
where a test is run, the test name, assumptions checked and caveats. The LLM is never used here.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sps

MIN_GROUP_N = 5
CAUSATION_NOTE = "Association does not imply causation."


def _f(x) -> float | None:
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def describe_numeric(s: pd.Series, weight: pd.Series | None = None) -> dict:
    s = pd.to_numeric(s, errors="coerce")
    nn = s.dropna()
    out = {"n_valid": int(nn.size), "n_missing": int(s.isna().sum())}
    if nn.empty:
        return out
    mode = nn.mode()
    out.update({
        "mean": _f(nn.mean()), "median": _f(nn.median()), "mode": _f(mode.iloc[0]) if len(mode) else None,
        "min": _f(nn.min()), "max": _f(nn.max()), "std": _f(nn.std(ddof=1)) if nn.size > 1 else None,
        "variance": _f(nn.var(ddof=1)) if nn.size > 1 else None, "sum": _f(nn.sum()),
        "p05": _f(nn.quantile(.05)), "p25": _f(nn.quantile(.25)), "p75": _f(nn.quantile(.75)), "p95": _f(nn.quantile(.95)),
        "skewness": _f(sps.skew(nn)) if nn.size > 2 else None,
    })
    if weight is not None:
        w = pd.to_numeric(weight, errors="coerce").loc[nn.index]
        ok = w.notna() & (w > 0)
        if ok.any():
            out["weighted_mean"] = _f(np.average(nn[ok], weights=w[ok]))
    return out


def frequency(df: pd.DataFrame, column: str, *, multiselect_sep: str | None = None,
              multiselect_columns: list[str] | None = None, weight: str | None = None,
              order: list[str] | None = None) -> dict:
    """Frequency table. Percentages use valid (non-missing) responses as denominator; the base is reported.
    Multiple-response: percentage of respondents selecting each option (totals can exceed 100%)."""
    w = pd.to_numeric(df[weight], errors="coerce").fillna(0) if weight else None
    if multiselect_columns:
        sub = df[multiselect_columns]
        answered = sub.notna().any(axis=1)
        base = int(answered.sum())
        rows = []
        for c in multiselect_columns:
            sel = sub[c].astype("string").str.lower().isin(["1", "true", "yes", "1.0"]) | (sub[c] == 1) | (sub[c] == True)  # noqa: E712
            sel = sel.fillna(False) & answered
            cnt = float(w[sel].sum()) if w is not None else int(sel.sum())
            label = c.split("/")[-1].split(".")[-1]
            rows.append({"value": label, "n": cnt, "pct": round(100 * cnt / (float(w[answered].sum()) if w is not None else base), 2) if base else None})
        table = pd.DataFrame(rows).sort_values("n", ascending=False)
        return {"column": column, "type": "multiple_response", "base_n": base, "n_missing": int(len(df) - base),
                "table": table, "note": "Respondents could select several options; percentages may sum to more than 100%."}
    s = df[column]
    if multiselect_sep is not None:
        valid = s.dropna().astype(str)
        base = int(valid.size)
        tokens = valid.str.split(r"\s+" if multiselect_sep == " " else multiselect_sep, regex=True)
        exploded = tokens.explode().str.strip()
        exploded = exploded[exploded != ""]
        # count each option once per respondent
        per_resp = exploded.groupby(level=0).apply(lambda x: list(dict.fromkeys(x))).explode()
        vc = per_resp.value_counts()
        table = pd.DataFrame({"value": vc.index.astype(str), "n": vc.values})
        table["pct"] = (100 * table["n"] / base).round(2) if base else None
        return {"column": column, "type": "multiple_response", "base_n": base, "n_missing": int(s.isna().sum()),
                "table": table, "note": "Respondents could select several options; percentages may sum to more than 100%."}
    valid_mask = s.notna()
    if w is not None:
        vc = w[valid_mask].groupby(s[valid_mask].astype(str)).sum().sort_values(ascending=False)
        base = float(w[valid_mask].sum())
    else:
        vc = s[valid_mask].astype(str).value_counts()
        base = int(valid_mask.sum())
    table = pd.DataFrame({"value": vc.index.astype(str), "n": vc.values})
    if order:
        table["__o"] = table["value"].map({v: i for i, v in enumerate(order)}).fillna(len(order))
        table = table.sort_values(["__o", "n"], ascending=[True, False]).drop(columns="__o")
    table["pct"] = (100 * table["n"] / base).round(2) if base else None
    return {"column": column, "type": "single", "base_n": base, "n_missing": int((~valid_mask).sum()),
            "weighted": bool(weight), "table": table.reset_index(drop=True)}


def crosstab(df: pd.DataFrame, row: str, col: str, normalize: str = "row") -> dict:
    sub = df[[row, col]].dropna()
    sub = sub.astype({row: "string", col: "string"})
    counts = pd.crosstab(sub[row], sub[col])
    if normalize == "row":
        pct = counts.div(counts.sum(axis=1), axis=0) * 100
    elif normalize == "column":
        pct = counts.div(counts.sum(axis=0), axis=1) * 100
    else:
        pct = counts / counts.values.sum() * 100
    result = {"row": row, "column": col, "n": int(len(sub)), "n_excluded_missing": int(len(df) - len(sub)),
              "counts": counts, "percent": pct.round(2), "normalize": normalize, "test": None}
    if counts.shape[0] >= 2 and counts.shape[1] >= 2 and len(sub) >= 10:
        chi2, p, dof, expected = sps.chi2_contingency(counts.values)
        low = float((expected < 5).mean())
        test = {"name": "Pearson chi-square test of independence", "statistic": _f(chi2), "df": int(dof), "p_value": _f(p),
                "cramers_v": _f(math.sqrt(chi2 / (len(sub) * (min(counts.shape) - 1)))) if min(counts.shape) > 1 else None,
                "assumption_expected_lt5_share": round(low, 3), "valid": low <= 0.2}
        if low > 0.2 and counts.shape == (2, 2):
            _, pf = sps.fisher_exact(counts.values)
            test = {"name": "Fisher's exact test (expected counts too small for chi-square)", "p_value": _f(pf), "valid": True}
        elif low > 0.2:
            test["caveat"] = f"{low:.0%} of cells have expected counts below 5; the chi-square result is unreliable. Combine categories or report descriptively."
        test["note"] = CAUSATION_NOTE
        result["test"] = test
    return result


def _normal(x: pd.Series) -> bool | None:
    if 3 <= len(x) <= 5000:
        return bool(sps.shapiro(x).pvalue > 0.05)
    return None


def compare_groups(df: pd.DataFrame, value: str, group: str) -> dict:
    sub = df[[value, group]].dropna()
    sub[value] = pd.to_numeric(sub[value], errors="coerce")
    sub = sub.dropna()
    groups = {str(k): g[value] for k, g in sub.groupby(group, observed=True)}
    summary = pd.DataFrame([{"group": k, "n": int(v.size), "mean": _f(v.mean()), "median": _f(v.median()),
                             "std": _f(v.std(ddof=1)) if v.size > 1 else None} for k, v in groups.items()])
    out = {"value": value, "group": group, "n": int(len(sub)), "summary": summary, "tests": [], "caveats": []}
    eligible = {k: v for k, v in groups.items() if v.size >= MIN_GROUP_N}
    if len(eligible) < len(groups):
        out["caveats"].append(f"Groups with fewer than {MIN_GROUP_N} observations were excluded from significance testing.")
    if len(eligible) < 2:
        out["caveats"].append("Not enough groups with sufficient observations for a statistical test; results are descriptive only.")
        return out
    vals = list(eligible.values())
    normal = [_normal(v) for v in vals]
    if len(vals) == 2:
        t = sps.ttest_ind(vals[0], vals[1], equal_var=False)
        u = sps.mannwhitneyu(vals[0], vals[1], alternative="two-sided")
        out["tests"].append({"name": "Welch's t-test (difference in means)", "statistic": _f(t.statistic), "p_value": _f(t.pvalue),
                             "appropriate": all(n is not False for n in normal) or min(v.size for v in vals) >= 30})
        out["tests"].append({"name": "Mann–Whitney U (distribution shift, non-parametric)", "statistic": _f(u.statistic), "p_value": _f(u.pvalue), "appropriate": True})
    else:
        a = sps.f_oneway(*vals)
        k = sps.kruskal(*vals)
        out["tests"].append({"name": "One-way ANOVA", "statistic": _f(a.statistic), "p_value": _f(a.pvalue),
                             "appropriate": all(n is not False for n in normal) or min(v.size for v in vals) >= 30})
        out["tests"].append({"name": "Kruskal–Wallis H (non-parametric)", "statistic": _f(k.statistic), "p_value": _f(k.pvalue), "appropriate": True})
    if any(n is False for n in normal):
        out["caveats"].append("At least one group is not normally distributed (Shapiro–Wilk p≤0.05); prefer the non-parametric result for small samples.")
    out["caveats"].append(CAUSATION_NOTE + " Survey data are observational.")
    return out


def compare_proportions(success_a: int, n_a: int, success_b: int, n_b: int) -> dict:
    """Two-proportion z-test with 95% CI for the difference."""
    if min(n_a, n_b) == 0:
        return {"valid": False, "caveat": "One group has no observations."}
    p1, p2 = success_a / n_a, success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b)) if 0 < pooled < 1 else 0
    se_diff = math.sqrt(p1 * (1 - p1) / n_a + p2 * (1 - p2) / n_b)
    out = {"p_a": p1, "p_b": p2, "difference_pp": 100 * (p2 - p1),
           "ci95_pp": [100 * (p2 - p1 - 1.96 * se_diff), 100 * (p2 - p1 + 1.96 * se_diff)], "test": "Two-proportion z-test"}
    if se == 0:
        out.update({"valid": False, "caveat": "Proportions are 0% or 100% in both groups; test not applicable."})
        return out
    z = (p2 - p1) / se
    out.update({"z": z, "p_value": float(2 * (1 - sps.norm.cdf(abs(z)))),
                "valid": min(success_a, n_a - success_a, success_b, n_b - success_b) >= 5})
    if not out["valid"]:
        out["caveat"] = "Fewer than 5 successes or failures in a group; the normal approximation is unreliable."
    return out


def correlation(df: pd.DataFrame, columns: list[str], method: str = "spearman") -> dict:
    sub = df[columns].apply(pd.to_numeric, errors="coerce")
    rows = []
    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            pair = sub[[a, b]].dropna()
            if len(pair) < 10 or pair[a].nunique() < 2 or pair[b].nunique() < 2:
                rows.append({"x": a, "y": b, "n": len(pair), "r": None, "p_value": None, "note": "insufficient data"})
                continue
            r, p = (sps.spearmanr if method == "spearman" else sps.pearsonr)(pair[a], pair[b])
            rows.append({"x": a, "y": b, "n": int(len(pair)), "r": _f(r), "p_value": _f(p)})
    matrix = sub.corr(method=method, min_periods=10)
    return {"method": method, "pairs": pd.DataFrame(rows), "matrix": matrix.round(3), "note": CAUSATION_NOTE}


FREQ_ALIASES = {"day": "D", "week": "W-MON", "month": "MS", "quarter": "QS", "year": "YS"}


def time_series(df: pd.DataFrame, date_col: str, freq: str = "month", value: str | None = None, agg: str = "count",
                window: int = 3) -> pd.DataFrame:
    s = pd.to_datetime(df[date_col], errors="coerce")
    sub = df.assign(__d=s).dropna(subset=["__d"])
    rule = FREQ_ALIASES.get(freq, freq)
    g = sub.set_index("__d")
    kw = {"label": "left", "closed": "left"} if rule.startswith("W") else {}   # a week is Monday–Sunday, labelled by its Monday
    if agg == "count" or value is None:
        ts = g.resample(rule, **kw).size().rename("value")
    else:
        col = pd.to_numeric(g[value], errors="coerce")
        ts = getattr(col.resample(rule, **kw), agg)().rename("value")
    out = ts.to_frame()
    out["moving_average"] = out["value"].rolling(window, min_periods=window).mean()
    out["cumulative"] = out["value"].cumsum() if agg in ("count", "sum") else np.nan
    out["pct_change"] = out["value"].pct_change(fill_method=None) * 100
    out.index.name = "period"
    return out.reset_index()


def seasonality(ts: pd.DataFrame, period: int = 12) -> dict:
    if len(ts) < 2 * period:
        return {"available": False, "reason": f"Seasonality needs at least {2 * period} consecutive periods; {len(ts)} available."}
    from statsmodels.tsa.seasonal import seasonal_decompose
    y = ts.set_index("period")["value"].astype(float).interpolate(limit_direction="both")
    d = seasonal_decompose(y, period=period, model="additive")
    return {"available": True, "trend": d.trend, "seasonal": d.seasonal, "resid": d.resid,
            "strength": _f(max(0.0, 1 - np.nanvar(d.resid) / np.nanvar(d.resid + d.seasonal)))}


def forecast(ts: pd.DataFrame, horizon: int = 3, min_obs: int = 12) -> dict:
    """ETS forecast with 80% and 95% prediction intervals. Refuses when history is too short."""
    y = ts.set_index("period")["value"].astype(float)
    if y.notna().sum() < min_obs:
        return {"available": False, "reason": f"Forecasting needs at least {min_obs} observed periods; only {int(y.notna().sum())} are available."}
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
    y = y.interpolate(limit_direction="both")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ETSModel(y, error="add", trend="add", damped_trend=True).fit(disp=False)
        pred = model.get_prediction(start=len(y), end=len(y) + horizon - 1)
        f95 = pred.summary_frame(alpha=0.05)
        f80 = pred.summary_frame(alpha=0.20)
    idx = pd.date_range(y.index[-1], periods=horizon + 1, freq=pd.infer_freq(y.index) or "MS")[1:]
    fc = pd.DataFrame({"period": idx, "forecast": f95["mean"].values, "lo95": f95["pi_lower"].values, "hi95": f95["pi_upper"].values,
                       "lo80": f80["pi_lower"].values, "hi80": f80["pi_upper"].values})
    return {"available": True, "method": "ETS (additive error, damped additive trend)", "forecast": fc,
            "note": "Forecast values are model projections, not observations. Intervals show uncertainty under the model's assumptions."}


def anomalies(ts: pd.DataFrame, threshold: float = 3.5) -> pd.DataFrame:
    y = ts["value"].astype(float)
    med = y.rolling(5, center=True, min_periods=3).median()
    resid = y - med
    mad = (resid - resid.median()).abs().median()
    if not mad or np.isnan(mad):
        return ts.iloc[0:0].assign(robust_z=[])
    z = 0.6745 * (resid - resid.median()) / mad
    return ts.assign(robust_z=z)[z.abs() > threshold]


def regression(df: pd.DataFrame, y: str, xs: list[str]) -> dict:
    import statsmodels.formula.api as smf
    sub = df[[y] + xs].dropna()
    if len(sub) < max(30, 10 * len(xs)):
        return {"available": False, "reason": f"Regression needs at least {max(30, 10 * len(xs))} complete observations for {len(xs)} predictor(s); {len(sub)} available."}
    terms = []
    for x in xs:
        terms.append(f"Q('{x}')" if pd.api.types.is_numeric_dtype(sub[x]) else f"C(Q('{x}'))")
    model = smf.ols(f"Q('{y}') ~ " + " + ".join(terms), data=sub).fit()
    coefs = pd.DataFrame({"term": model.params.index, "coef": model.params.values, "ci_low": model.conf_int()[0].values,
                          "ci_high": model.conf_int()[1].values, "p_value": model.pvalues.values})
    _, bp_p, _, _ = __import__("statsmodels.stats.diagnostic", fromlist=["het_breuschpagan"]).het_breuschpagan(model.resid, model.model.exog)
    return {"available": True, "n": int(model.nobs), "r2": _f(model.rsquared), "adj_r2": _f(model.rsquared_adj), "coefficients": coefs,
            "diagnostics": {"breusch_pagan_p": _f(bp_p), "heteroskedasticity_suspected": bool(bp_p < 0.05)},
            "note": "Ordinary least squares on observational data: coefficients describe associations, not causal effects."}


def longitudinal(df: pd.DataFrame, id_col: str, period_col: str) -> dict:
    sub = df[[id_col, period_col]].dropna().drop_duplicates()
    periods = sorted(sub[period_col].astype(str).unique())
    counts = sub.groupby(sub[period_col].astype(str))[id_col].nunique().reindex(periods)
    ids_by = {p: set(sub.loc[sub[period_col].astype(str) == p, id_col]) for p in periods}
    retention = []
    for a, b in zip(periods, periods[1:]):
        both = len(ids_by[a] & ids_by[b])
        retention.append({"from": a, "to": b, "in_both": both, "pct_of_from": round(100 * both / len(ids_by[a]), 2) if ids_by[a] else None})
    return {"periods": periods, "unique_ids_per_period": counts.to_dict(), "retention": retention,
            "in_all_periods": len(set.intersection(*ids_by.values())) if ids_by else 0}


def population_pyramid(df: pd.DataFrame, sex_col: str, age_col: str | None = None, age_group_col: str | None = None,
                       edges: list[int] | None = None) -> pd.DataFrame:
    sub = df.copy()
    if age_group_col:
        sub["__ag"] = sub[age_group_col].astype("string")
    else:
        edges = edges or [0, 5, 12, 18, 25, 35, 45, 60, 200]
        labels = [f"{edges[i]}–{edges[i + 1] - 1}" if edges[i + 1] < 200 else f"{edges[i]}+" for i in range(len(edges) - 1)]
        sub["__ag"] = pd.cut(pd.to_numeric(sub[age_col], errors="coerce"), bins=edges, labels=labels, right=False).astype("string")
    sub = sub.dropna(subset=["__ag", sex_col])
    t = pd.crosstab(sub["__ag"], sub[sex_col].astype("string"))
    if not age_group_col:
        t = t.reindex([l for l in labels if l in t.index])
    return t


def binary_rate(df: pd.DataFrame, mask: pd.Series, valid: pd.Series | None = None) -> dict:
    valid = valid if valid is not None else pd.Series(True, index=df.index)
    n = int(valid.sum())
    k = int((mask & valid).sum())
    if n == 0:
        return {"numerator": 0, "denominator": 0, "pct": None}
    p = k / n
    z = 1.96
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"numerator": k, "denominator": n, "pct": 100 * p, "ci95": [100 * (centre - half), 100 * (centre + half)],
            "ci_method": "Wilson score interval (simple random sample assumption)"}
