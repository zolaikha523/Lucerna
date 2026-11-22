"""Comparative analysis between two datasets / rounds with explicit compatibility checks."""
from __future__ import annotations

import pandas as pd

from . import stats
from .transform import condition_mask


def compatibility(a: pd.DataFrame, b: pd.DataFrame, map_a: dict, map_b: dict, meta_a: dict, meta_b: dict) -> dict:
    common = [c for c in a.columns if c in b.columns]
    issues, warnings_, ok = [], [], []
    if meta_a.get("unit_of_analysis") != meta_b.get("unit_of_analysis"):
        issues.append(f"Different units of analysis: '{meta_a.get('unit_of_analysis')}' vs '{meta_b.get('unit_of_analysis')}'. Counts and rates are not comparable.")
    for c in common:
        ta, tb = (map_a.get(c) or {}).get("type"), (map_b.get(c) or {}).get("type")
        if ta != tb:
            warnings_.append(f"'{c}' has type {ta} in A but {tb} in B; excluded from comparison.")
            continue
        if ta in ("categorical", "boolean"):
            va, vb = set(a[c].dropna().astype(str).str.lower()), set(b[c].dropna().astype(str).str.lower())
            if va and vb and len(va & vb) / len(va | vb) < 0.5:
                warnings_.append(f"'{c}' answer categories differ substantially between datasets (overlap {len(va & vb)}/{len(va | vb)}); the question or coding may have changed.")
                continue
        ok.append(c)
    if not common:
        issues.append("The datasets share no column names; map equivalent variables before comparing.")
    return {"comparable_columns": ok, "issues": issues, "warnings": warnings_, "valid": not issues and bool(ok)}


def compare_binary(a: pd.DataFrame, b: pd.DataFrame, column: str, label_a: str = "A", label_b: str = "B", by: str | None = None) -> pd.DataFrame:
    cond = {"column": column, "op": "in", "value": ["yes", "true", "1"]}
    rows = []
    groups = [(None, a, b)] if not by else [(k, a[a[by].astype("string") == k], b[b[by].astype("string") == k])
                                            for k in sorted(set(a[by].dropna().astype(str)) | set(b[by].dropna().astype(str)))]
    for k, ga, gb in groups:
        ra = stats.binary_rate(ga, condition_mask(ga, **cond), ga[column].notna())
        rb = stats.binary_rate(gb, condition_mask(gb, **cond), gb[column].notna())
        t = stats.compare_proportions(ra["numerator"], ra["denominator"], rb["numerator"], rb["denominator"]) if ra["denominator"] and rb["denominator"] else {}
        rows.append({"group": k or "All", "indicator": f"% {column} = yes", f"{label_a} %": ra["pct"], f"{label_a} n": ra["denominator"],
                     f"{label_b} %": rb["pct"], f"{label_b} n": rb["denominator"], "change (pp)": t.get("difference_pp"),
                     "95% CI (pp)": t.get("ci95_pp"), "p-value": t.get("p_value"), "test valid": t.get("valid"), "caveat": t.get("caveat")})
    return pd.DataFrame(rows)


def compare_numeric(a: pd.DataFrame, b: pd.DataFrame, column: str, label_a: str = "A", label_b: str = "B") -> dict:
    sa, sb = pd.to_numeric(a[column], errors="coerce").dropna(), pd.to_numeric(b[column], errors="coerce").dropna()
    da, db_ = stats.describe_numeric(sa), stats.describe_numeric(sb)
    out = {"indicator": column, f"{label_a} mean": da.get("mean"), f"{label_a} median": da.get("median"), f"{label_a} n": da["n_valid"],
           f"{label_b} mean": db_.get("mean"), f"{label_b} median": db_.get("median"), f"{label_b} n": db_["n_valid"]}
    if min(len(sa), len(sb)) >= 5:
        from scipy import stats as sps
        t = sps.ttest_ind(sa, sb, equal_var=False)
        u = sps.mannwhitneyu(sa, sb)
        out.update({"change in mean": (db_["mean"] - da["mean"]) if da.get("mean") is not None else None,
                    "Welch t p-value": float(t.pvalue), "Mann–Whitney p-value": float(u.pvalue)})
    out["note"] = "Independent samples assumed (different respondents in each round). If the same respondents were re-interviewed, a paired test is required."
    return out
