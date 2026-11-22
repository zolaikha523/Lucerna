"""Deterministic insight statements. Each statement is generated from computed numbers with
its base (n) and is only emitted when the evidence threshold is met. No LLM involved."""
from __future__ import annotations

import pandas as pd

from . import stats
from .transform import condition_mask

MIN_N = 30
MIN_GAP_PP = 10


def generate(df: pd.DataFrame, plan: dict, limit: int = 8) -> list[dict]:
    v = plan.get("variables", {})
    out = []
    unit = plan.get("unit_label", "records")
    for b in v.get("binaries", [])[:12]:
        cond = {"column": b, "op": "in", "value": ["yes", "true", "1"]}
        valid = df[b].notna()
        r = stats.binary_rate(df, condition_mask(df, **cond), valid)
        if r["denominator"] >= MIN_N:
            out.append({"kind": "rate", "column": b, "value": r["pct"], "n": r["denominator"],
                        "text": f"{r['pct']:.1f}% of {unit} with a valid answer reported '{b}' = yes ({r['numerator']:,} of {r['denominator']:,})."})
        for grp_role in ("sex", "geo"):
            grp = v.get("sex") if grp_role == "sex" else (list(v.get("geo", {}).values()) or [None])[0]
            if not grp or grp not in df:
                continue
            rates = []
            for k, g in df.groupby(df[grp].astype("string"), observed=True):
                gv = g[b].notna()
                if gv.sum() >= MIN_N:
                    rr = stats.binary_rate(g, condition_mask(g, **cond), gv)
                    rates.append((k, rr))
            if len(rates) >= 2:
                hi = max(rates, key=lambda x: x[1]["pct"])
                lo = min(rates, key=lambda x: x[1]["pct"])
                gap = hi[1]["pct"] - lo[1]["pct"]
                if gap >= MIN_GAP_PP:
                    test = stats.compare_proportions(lo[1]["numerator"], lo[1]["denominator"], hi[1]["numerator"], hi[1]["denominator"])
                    sig = test.get("p_value") is not None and test["p_value"] < 0.05 and test.get("valid")
                    out.append({"kind": "gap", "column": b, "group": grp, "gap_pp": gap,
                                "text": f"'{b}' = yes ranges from {lo[1]['pct']:.1f}% in {lo[0]} (n={lo[1]['denominator']}) to {hi[1]['pct']:.1f}% in {hi[0]} (n={hi[1]['denominator']}), a {gap:.1f} percentage-point gap"
                                        + (" (statistically significant, two-proportion z-test p<0.05)." if sig else " (not statistically significant at p<0.05; treat as indicative).")})
    tf = plan.get("feasibility", {}).get("temporal", {})
    if tf.get("possible"):
        ts = stats.time_series(df, tf["date"], "month" if tf.get("span_days", 0) > 90 else tf["freq"])
        if len(ts) >= 4:
            last, prev = ts["value"].iloc[-1], ts["value"].iloc[-2]
            if prev:
                ch = 100 * (last - prev) / prev
                out.append({"kind": "trend", "text": f"The latest period ({ts['period'].iloc[-1]:%b %Y}) recorded {int(last):,} {unit}, {abs(ch):.0f}% {'more' if ch > 0 else 'fewer'} than the previous period ({int(prev):,}). The latest period may be incomplete if data collection is ongoing."})
    miss = (df.isna().mean() * 100)
    high = miss[miss > 20]
    if len(high):
        out.append({"kind": "quality", "text": f"{len(high)} variable(s) have more than 20% missing values (highest: '{high.idxmax()}', {high.max():.0f}%). Results for these variables describe only respondents who answered."})
    out.sort(key=lambda x: {"gap": 0, "trend": 1, "rate": 2, "quality": 3}[x["kind"]])
    return out[:limit]
