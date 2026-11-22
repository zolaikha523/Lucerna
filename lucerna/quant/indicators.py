"""Indicator engine: configured definitions → deterministic values with numerator, denominator,
N, missing and disaggregations. Targets/baselines are only ever user-supplied."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import pandas as pd

from .stats import binary_rate
from .transform import condition_mask

TYPES = {
    "percentage": "Share of the denominator population meeting the numerator condition (%)",
    "count": "Number of records meeting a condition",
    "count_unique": "Number of distinct values of a column (e.g. unique beneficiaries)",
    "mean": "Average of a numeric column",
    "median": "Median of a numeric column",
    "sum": "Sum of a numeric column",
    "ratio": "Sum of numerator column / sum of denominator column",
}


class IndicatorConfigError(Exception):
    pass


@dataclass
class IndicatorDef:
    name: str
    indicator_type: str
    numerator: dict | None = None        # {"column","op","value"} condition
    denominator: dict | None = None      # condition; None = all rows with valid numerator column
    value_column: str | None = None
    ratio_denominator_column: str | None = None
    disaggregations: list[str] = field(default_factory=list)
    unit: str | None = None
    target: float | None = None
    baseline: float | None = None

    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True, default=str).encode()).hexdigest()[:16]


def validate_definition(d: IndicatorDef, df: pd.DataFrame) -> list[str]:
    """Return problems; an empty list means the indicator is computable. Missing pieces → 'provisional'."""
    p = []
    if d.indicator_type not in TYPES:
        p.append(f"Unknown indicator type '{d.indicator_type}'.")
    if d.indicator_type in ("percentage", "count") and not d.numerator:
        p.append("A numerator condition is required.")
    if d.indicator_type in ("mean", "median", "sum", "count_unique", "ratio") and not d.value_column:
        p.append("A value column is required.")
    if d.indicator_type == "ratio" and not d.ratio_denominator_column:
        p.append("A denominator column is required for a ratio.")
    for cond in (d.numerator, d.denominator):
        if cond and cond.get("column") not in df.columns:
            p.append(f"Column '{cond.get('column')}' is not in the dataset.")
    for c in [d.value_column, d.ratio_denominator_column, *d.disaggregations]:
        if c and c not in df.columns:
            p.append(f"Column '{c}' is not in the dataset.")
    if d.indicator_type in ("mean", "median", "sum", "ratio") and d.value_column in df.columns and not pd.api.types.is_numeric_dtype(df[d.value_column]):
        p.append(f"'{d.value_column}' is not numeric; confirm its type in Data Understanding.")
    return p


def _compute_once(d: IndicatorDef, df: pd.DataFrame) -> dict:
    t = d.indicator_type
    if t == "percentage":
        num_col = d.numerator["column"]
        valid = condition_mask(df, **d.denominator) if d.denominator else df[num_col].notna()
        if d.denominator:
            valid = valid & df[num_col].notna()
        r = binary_rate(df, condition_mask(df, **d.numerator), valid)
        return {"value": r["pct"], "numerator": r["numerator"], "denominator": r["denominator"],
                "n_valid": r["denominator"], "n_missing": int(len(df) - r["denominator"]), "ci95": r.get("ci95")}
    if t == "count":
        base = condition_mask(df, **d.denominator) if d.denominator else pd.Series(True, index=df.index)
        k = int((condition_mask(df, **d.numerator) & base).sum())
        return {"value": k, "numerator": k, "denominator": None, "n_valid": int(base.sum()), "n_missing": 0}
    s = df[d.value_column]
    base = condition_mask(df, **d.denominator) if d.denominator else pd.Series(True, index=df.index)
    s = s[base]
    if t == "count_unique":
        return {"value": int(s.dropna().nunique()), "numerator": None, "denominator": None, "n_valid": int(s.notna().sum()), "n_missing": int(s.isna().sum())}
    s = pd.to_numeric(s, errors="coerce")
    nn = s.dropna()
    if t == "ratio":
        den = pd.to_numeric(df.loc[base, d.ratio_denominator_column], errors="coerce")
        ok = s.notna() & den.notna()
        dsum = float(den[ok].sum())
        return {"value": (float(s[ok].sum()) / dsum) if dsum else None, "numerator": float(s[ok].sum()), "denominator": dsum,
                "n_valid": int(ok.sum()), "n_missing": int((~ok).sum())}
    val = {"mean": nn.mean, "median": nn.median, "sum": nn.sum}[t]() if len(nn) else None
    return {"value": None if val is None else float(val), "numerator": None, "denominator": None,
            "n_valid": int(nn.size), "n_missing": int(s.isna().sum())}


def compute(d: IndicatorDef, df: pd.DataFrame) -> dict:
    problems = validate_definition(d, df)
    if problems:
        raise IndicatorConfigError("; ".join(problems))
    overall = _compute_once(d, df)
    dis = {}
    for col in d.disaggregations:
        rows = []
        for key, g in df.groupby(df[col].astype("string"), dropna=True):
            r = _compute_once(d, g)
            r["group"] = str(key)
            rows.append(r)
        dis[col] = rows
    out = {"indicator": d.name, "type": d.indicator_type, "unit": d.unit, **overall, "disaggregations": dis,
           "target": d.target, "baseline": d.baseline, "config_hash": d.config_hash()}
    if d.target is not None and overall.get("value") is not None:
        out["achievement_pct_of_target"] = 100 * overall["value"] / d.target if d.target else None
    return out


def suggest_indicators(df: pd.DataFrame, profile: dict) -> list[dict]:
    """Provisional suggestions from binary/yes-no columns and key measures. Never includes targets/baselines."""
    out = []
    for c in profile["columns"]:
        name = c["name"]
        if name not in df.columns:
            continue
        if c.get("final_type", c["inferred_type"]) == "boolean" or c["inferred_role"] == "binary":
            out.append({"name": f"% reporting '{name}' = yes", "indicator_type": "percentage",
                        "numerator": {"column": name, "op": "in", "value": ["yes", "true", "1"]},
                        "denominator": None, "status": "provisional",
                        "reason": "Yes/no question detected. Confirm the wording, the population (denominator) and whether 'yes' is the desired outcome."})
        elif c["inferred_role"] == "measure" and c["inferred_type"] in ("numeric", "integer"):
            out.append({"name": f"Average {name}", "indicator_type": "mean", "value_column": name, "status": "provisional",
                        "reason": "Numeric measure detected. Confirm the unit and whether mean or median is the appropriate statistic."})
    return out[:25]
