"""Structured, traceable explanations for every dashboard visual.

All numbers come from the visual's own computed table (`charts.compute`) or from deterministic tests run here.
Text is assembled from rules; nothing is invented. Each explanation separates:

    what            what the chart shows (description)
    findings        verified findings: numbers read directly from the computed results, each with its base
    why             why the topic matters (generic sector knowledge, not a finding about this data)
    interpretation  analytical interpretation — cautious, labelled as interpretation
    implications    operational implications — what the pattern could mean for programming
    actions         suggested follow-up — recommendations for analysts to review, never conclusions
    limitations     sample size, missing data, multiple answers, association ≠ causation, incomplete periods
    source          sheet, variables, formula, denominator, filters, n

An optional local-AI rewrite (see `ai_polish`) may only rephrase these sections; any sentence that contains a
number not present in the verified findings is discarded.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import domain as dom
from . import stats
from .charts import VisualData, measure_label

SMALL_N = 30


def _pct(x: float | None) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1f}%"


def _num(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    x = float(x)
    if abs(x) >= 100 or x.is_integer():
        return f"{x:,.0f}"
    return f"{x:,.1f}"


def _label(plan: dict, col: str | None) -> str:
    if not col:
        return ""
    return (plan.get("labels") or {}).get(col) or dom.humanise(col)


def _source(v: dict, data: VisualData | None, plan: dict, filters: dict | None) -> dict:
    t = v["type"]
    cols = [c for c in (v.get("x"), v.get("color"), v.get("value"), v.get("by"), v.get("date"), v.get("source"), v.get("via"), v.get("target"),
                        v.get("sex"), v.get("age"), v.get("age_group"), v.get("lat"), v.get("lon"), v.get("y"), (v.get("condition") or {}).get("column"))
            if c] + list(v.get("columns", [])) + list(v.get("path", [])) + [c.get("column") for c in v.get("conditions", [])] + list(v.get("outcomes_cols", []))
    cols = list(dict.fromkeys(cols))
    m = v.get("measure", "count")
    cond = v.get("condition")
    if t == "kpi":
        k = v.get("kpi")
        formula = {"count_rows": "number of rows after filters", "pct": f"records where {cond['column'] if cond else ''} = yes ÷ records with a valid answer × 100",
                   "completeness": "non-missing cells ÷ all cells × 100", "date_span": "earliest and latest valid date",
                   "n_categories": f"distinct values of {v.get('value')}", "unique": f"distinct values of {v.get('value')}",
                   "duplicates": f"records whose {v.get('value')} also appears on another record",
                   "mean": f"mean of {v.get('value')}", "median": f"median of {v.get('value')}", "sum": f"sum of {v.get('value')}"}.get(k, k)
    elif m == "pct_condition":
        formula = f"records with {cond['column']} = yes ÷ records with a valid answer, within each group × 100"
    elif v.get("as_pct") or t in ("stacked100",):
        formula = "records in category ÷ records with a valid answer × 100" + (" (within each group)" if t == "stacked100" else "")
    elif t == "multiselect":
        formula = "respondents selecting the option ÷ respondents answering the question × 100 (answers can sum to more than 100%)"
    elif t in ("histogram", "box"):
        formula = f"distribution of the valid numeric values of {v.get('value')}"
    elif t in ("line", "forecast"):
        formula = f"{m} per {v.get('freq', 'month')}" + (" (3-period moving average shown)" if t == "line" and m != "pct_condition" else "")
    elif t == "multiline":
        formula = f"{v.get('agg', 'sum')} of each column per {v.get('freq', 'day')}"
    elif t == "heatmap":
        formula = "% yes among valid answers in each row group"
    elif t == "correlation":
        formula = "Spearman rank correlation between each pair of measures"
    elif t == "compare_table":
        formula = "% yes (binary outcomes) or median (numeric) by group; chi-square or Kruskal–Wallis / Mann–Whitney tests"
    elif t == "sankey":
        formula = "number of records (or sum of the weight column) for each origin → destination pair"
    elif t == "map_points":
        formula = "recorded coordinates, one marker per valid record"
    else:
        formula = measure_label(v)
    denom = None
    if data is not None and data.base_n is not None:
        denom = f"{data.base_n:,} records with a valid value"
    flt = "; ".join(f"{c} ∈ {', '.join(map(str, f.get('values', [])))}" if f.get("values") else f"{c} between {f['range'][0]} and {f['range'][1]}"
                    for c, f in (filters or {}).items() if f) or "none"
    excl = [f"'{', '.join(vals)}' in {c} excluded from the denominator" for c, vals in (v.get("exclude_values") or {}).items()]
    return {"sheet": v.get("source_sheet") or plan.get("sheet") or plan.get("dataset_name"), "variables": cols, "formula": formula,
            "denominator": denom, "filters": flt, "exclusions": excl, "n": data.base_n if data is not None else None,
            "method": "Deterministic computation in Python (pandas / SciPy). No AI model produced these numbers."}


def fmt_p(p: float | None) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "p = –"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _chi2(table: list[list[int]]) -> tuple[float | None, bool]:
    try:
        from scipy.stats import chi2_contingency
        t = np.array(table, dtype=float)
        t = t[t.sum(axis=1) > 0][:, t.sum(axis=0) > 0]
        if t.shape[0] < 2 or t.shape[1] < 2:
            return None, False
        r = chi2_contingency(t)
        return float(r.pvalue), bool((r.expected_freq >= 5).all())
    except Exception:  # noqa: BLE001
        return None, False


def _sig_text(p: float | None, ok: bool, test: str) -> str:
    if p is None:
        return ""
    if p < 0.05:
        return f" The difference is statistically significant ({test}, {fmt_p(p)}{'' if ok else '; some expected counts are below 5'})."
    return f" The difference is not statistically significant ({test}, {fmt_p(p)}); treat it as indicative."


def explain(v: dict, data: VisualData, plan: dict, df: pd.DataFrame | None = None, filters: dict | None = None) -> dict:
    """Return the structured explanation of one computed visual."""
    t = v["type"]
    L = lambda c: _label(plan, c)  # noqa: E731
    tab = data.table
    topic = v.get("topic") or "general"
    unit = plan.get("unit_label", "records")
    out = {"what": "", "findings": [], "why": dom.WHY.get(topic, dom.WHY["general"]), "interpretation": "", "implications": "",
           "actions": [], "limitations": [], "source": _source(v, data, plan, filters), "verified": True}
    lim = out["limitations"]
    if data.base_n is not None and data.base_n < SMALL_N:
        lim.append(f"Small base (n = {data.base_n}); percentages can change a lot with a few records.")
    lim += [n for n in data.notes if n and "p =" not in n and "p <" not in n]
    try:
        _dispatch(t, v, data, plan, df, out, L, unit)
    except Exception as e:  # noqa: BLE001 — explanation must never break a dashboard
        out["what"] = out["what"] or (v.get("title") or "")
        lim.append(f"Automatic explanation incomplete: {e}")
    if not out["what"]:
        out["what"] = v.get("title") or ""
    out["limitations"] = list(dict.fromkeys(lim))
    return out


def _dispatch(t, v, data, plan, df, out, L, unit):  # noqa: C901 — one rule set per visual type, kept together for traceability
    tab = data.table
    F, A = out["findings"], out["actions"]
    seg_word = L(v.get("x"))
    if t == "kpi":
        out["what"] = f"Headline figure: {v.get('title')}."
        out["why"] = "Headline figures summarise the data; open the related pages for breakdowns."
        return

    if t in ("bar", "stacked100", "donut") and "series" not in tab.columns:
        is_pct = v.get("measure") == "pct_condition"
        if tab.empty:
            return
        if is_pct:
            var = L((v.get("condition") or {}).get("column"))
            out["what"] = f"Share of {unit} answering yes to '{var}', compared across {seg_word.lower()} groups."
            hi, lo = tab.loc[tab["value"].idxmax()], tab.loc[tab["value"].idxmin()]
            gap = float(hi["value"] - lo["value"])
            succ = [[round(r["value"] * r["n"] / 100), r["n"] - round(r["value"] * r["n"] / 100)] for _, r in tab.iterrows() if r["n"]]
            p, ok = _chi2(succ)
            overall_n = int(tab["n"].sum())
            overall = sum(s[0] for s in succ) / overall_n * 100 if overall_n else None
            if overall is not None:
                F.append(f"Overall, {_pct(overall)} of {overall_n:,} {unit} with a valid answer said yes.")
            F.append(f"Highest in {hi['x']}: {_pct(hi['value'])} (n = {int(hi['n']):,}); lowest in {lo['x']}: {_pct(lo['value'])} (n = {int(lo['n']):,}) — "
                     f"a gap of {gap:.1f} percentage points.{_sig_text(p, ok, 'chi-square test')}")
            small = tab[tab["n"] < SMALL_N]
            if len(small):
                out["limitations"].append(f"{len(small)} group(s) have fewer than {SMALL_N} records: {', '.join(small['x'].astype(str).head(5))}.")
            if p is not None and p < 0.05 and gap >= 10:
                out["interpretation"] = (f"The rate differs meaningfully between {seg_word.lower()} groups. Group membership is associated with '{var}', "
                                         "but the data alone do not show why; other differences between the groups may explain it.")
                out["implications"] = f"{lo['x']} has the lowest rate. If '{var}' is a desired outcome, this group may need attention; if it is a risk, focus on {hi['x']}."
                A.append(f"Check with field teams or partners why '{var}' is {_pct(lo['value'])} in {lo['x']} compared with {_pct(hi['value'])} in {hi['x']}.")
                A.append(f"Break the {lo['x']} group down further (e.g. by location or sex) to see where the gap is concentrated.")
            else:
                out["interpretation"] = f"The groups show similar rates for '{var}' or the differences are within what chance could produce."
                out["implications"] = "A single approach across groups may be appropriate for this outcome, subject to other evidence."
                A.append(f"Keep monitoring '{var}' in future rounds to confirm whether the pattern is stable.")
            return
        # distribution of one categorical variable
        total = tab["value"].sum()
        share = tab["value"] / total * 100 if not v.get("as_pct") else tab["value"]
        top = tab.iloc[int(np.argmax(share.values))]
        top3 = float(np.sort(share.values)[::-1][:3].sum())
        k = len(tab)
        counts_word = "records" if v.get("as_pct") else measure_label(v).lower()
        if v.get("measure") in ("mean", "median", "sum"):
            var = L(v.get("value"))
            out["what"] = f"{v.get('measure').title()} of {var.lower()} for each {seg_word.lower()}."
            hi, lo = tab.loc[tab["value"].idxmax()], tab.loc[tab["value"].idxmin()]
            F.append(f"Highest {v['measure']} {var.lower()} in {hi['x']} ({_num(hi['value'])}, n = {int(hi['n']):,}); lowest in {lo['x']} ({_num(lo['value'])}, n = {int(lo['n']):,}).")
            if v["measure"] == "sum":
                F.append(f"The top 3 account for {top3:.1f}% of the total of {_num(total)}.")
            out["interpretation"] = "Differences between groups describe where values are higher or lower; they do not explain why."
            A.append(f"Review the groups with the highest and lowest {var.lower()} with programme staff to understand the drivers.")
            return
        out["what"] = f"How {unit} are distributed across the categories of '{seg_word}'."
        if k >= 2 and float(share.max()) - float(share.min()) < 0.05:
            F.append(f"All {k} categories are equally represented ({_pct(float(share.max()))} each of {data.base_n:,} {unit}); "
                     "this usually reflects a fixed data-collection design rather than a finding.")
            out["interpretation"] = "An even split carries no information about differences between categories."
            return
        F.append(f"'{top['x']}' is the most common category: {_pct(float(share.iloc[int(np.argmax(share.values))]))} of {data.base_n:,} {unit} with a valid answer"
                 + (f" ({int(top['value']):,} {counts_word})." if not v.get("as_pct") else "."))
        if k >= 3:
            F.append(f"The three largest categories together account for {top3:.1f}%; {k} categories are shown.")
        if top3 >= 80 and k >= 4:
            out["interpretation"] = "Responses are concentrated in a few categories; the remaining categories are small and should be interpreted with care."
        elif share.max() < 35 and k >= 4:
            out["interpretation"] = "Responses are spread across many categories; no single answer dominates."
        else:
            out["interpretation"] = f"'{top['x']}' clearly leads, but other categories still represent a substantial share."
        out["implications"] = f"Planning and messaging that relate to '{seg_word}' should reflect the dominant category without ignoring smaller groups."
        if v.get("drill"):
            A.append("Click a bar to drill down to the next geographic level.")
        A.append(f"Compare the distribution of '{seg_word}' across locations or groups before generalising it to all {unit}.")
        return

    if t in ("bar", "stacked100") and "series" in tab.columns:
        col, by = L(v.get("color")), seg_word
        out["what"] = f"Composition of '{col}' within each {by.lower()} group (each bar sums to 100%)."
        if df is not None and v.get("color") in df and v.get("x") in df:
            ct = stats.crosstab(df, v["x"], v["color"], normalize="row")
            test = ct.get("test") or {}
            p = test.get("p_value")
        else:
            p = None
        dom_rows = []
        for g, part in tab.groupby("x", sort=False):
            r = part.loc[part["value"].idxmax()]
            dom_rows.append((g, r["series"], r["value"]))
        for g, s, val in dom_rows[:4]:
            F.append(f"In {g}, the most common answer is '{s}' ({_pct(val)}).")
        overall_top = tab.groupby("series")["n"].sum().idxmax()
        piv = tab[tab["series"] == overall_top].set_index("x")["value"]
        if len(piv) >= 2:
            F.append(f"The share answering '{overall_top}' ranges from {_pct(piv.min())} ({piv.idxmin()}) to {_pct(piv.max())} ({piv.idxmax()})."
                     + _sig_text(p, True, test.get("name", "chi-square test") if p is not None else ""))
        out["interpretation"] = (f"'{col}' is associated with {by.lower()}: the groups answer differently." if p is not None and p < 0.05 else
                                 f"The pattern of '{col}' is broadly similar across {by.lower()} groups, or differences are not statistically clear.")
        out["implications"] = f"Where the composition of '{col}' differs by {by.lower()}, targeting or messaging may need to be group-specific."
        A.append(f"Look at the group with the most different profile on '{col}' and confirm the finding with qualitative evidence.")
        return

    if t == "multiselect":
        var = seg_word
        out["what"] = f"Options selected for '{var}'. Respondents could choose more than one answer, so the bars add up to more than 100%."
        tab2 = tab.sort_values("pct", ascending=False)
        for _, r in tab2.head(3).iterrows():
            F.append(f"'{r['x']}' was selected by {_pct(r['pct'])} of respondents (n = {int(r['n']):,}).")
        out["interpretation"] = f"The leading options show what is most frequently reported for '{var}'; frequency is not the same as severity."
        out["implications"] = f"The top options for '{var}' are candidates for prioritisation, alongside severity and feasibility."
        A.append(f"Cross-check the top options for '{var}' by sex and location before setting priorities.")
        out["limitations"].append("Multiple answers allowed: percentages are of respondents and do not sum to 100%.")
        return

    if t == "histogram":
        d = data.extra.get("describe", {})
        var = L(v.get("value"))
        s = pd.to_numeric(tab["value"], errors="coerce").dropna()
        q1, q3 = s.quantile(.25), s.quantile(.75)
        iqr = q3 - q1
        outl = int(((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum()) if iqr > 0 else 0
        out["what"] = f"Distribution of '{var}' across {len(s):,} {unit} with a valid value."
        F.append(f"Median {_num(d.get('median'))}, mean {_num(d.get('mean'))}; half of the values lie between {_num(q1)} and {_num(q3)}.")
        F.append(f"Range from {_num(s.min())} to {_num(s.max())}.")
        if d.get("mean") and d.get("median") and d["median"] and abs(d["mean"] - d["median"]) / abs(d["median"]) > .2:
            out["interpretation"] = "The mean is pulled away from the median by a long tail of extreme values; the median is the better summary of a typical value."
        else:
            out["interpretation"] = "The distribution is fairly balanced; mean and median tell a similar story."
        if outl:
            F.append(f"{outl:,} value(s) are far outside the typical range (more than 3 × the interquartile range from the quartiles).")
            A.append(f"Check the {outl:,} extreme value(s) of '{var}' for data-entry errors before using averages.")
        out["implications"] = f"Use the median and the spread of '{var}' rather than the average alone when setting thresholds or transfer values."
        return

    if t == "box":
        var, by = L(v.get("value")), L(v.get("by"))
        g = tab.groupby(v["by"])[v["value"]].median().sort_values()
        out["what"] = f"How '{var}' varies between {by.lower()} groups (box = middle 50% of values, line = median)."
        if len(g) >= 2:
            F.append(f"Highest median in {g.index[-1]} ({_num(g.iloc[-1])}); lowest in {g.index[0]} ({_num(g.iloc[0])}).")
        tests = [n for n in data.notes if "p =" in n or "p <" in n]
        if tests:
            F.append(tests[0] + ".")
            p = 0.0 if "p <" in tests[0] else float(tests[0].split("p = ")[1].split()[0].rstrip(";,."))
            if p < 0.05:
                out["interpretation"] = f"'{var}' differs between {by.lower()} groups beyond what chance would explain."
                out["implications"] = f"Group-specific thresholds or support levels for '{var}' may be justified."
                A.append(f"Investigate why {g.index[0]} has the lowest median {var.lower()} with field teams.")
            else:
                out["interpretation"] = f"Differences in '{var}' between {by.lower()} groups are small or not statistically clear."
                out["implications"] = f"A common approach across groups appears reasonable for '{var}'."
        return

    if t in ("line", "area_stacked"):
        pct = v.get("measure") == "pct_condition"
        if "series" in tab.columns:
            tot = tab.groupby("series")["value"].sum().sort_values(ascending=False)
            out["what"] = f"Change over time for each {L(v.get('color')).lower()} group."
            F.append(f"Over the whole period, '{tot.index[0]}' is the largest group ({_num(tot.iloc[0])} {unit}).")
            last = tab[tab["period"] == tab["period"].max()].set_index("series")["value"]
            if len(last):
                F.append(f"In the latest period ({pd.Timestamp(tab['period'].max()):%b %Y}), '{last.idxmax()}' leads with {_num(last.max())}.")
            out["interpretation"] = "Groups that grow faster than others change the composition of the caseload over time."
            A.append("Watch whether the fastest-growing group keeps growing in the next periods before re-allocating resources.")
            return
        s = tab.dropna(subset=["value"]).reset_index(drop=True)
        if len(s) < 2:
            return
        s, edge_note = _complete_periods(s, v, df)
        if edge_note:
            out["limitations"].append(edge_note)
        first, last = s.iloc[0], s.iloc[-1]
        peak = s.loc[s["value"].idxmax()]
        what = ("% yes for '" + L((v.get("condition") or {}).get("column")) + "'") if pct else (measure_label(v).lower() if v.get("measure") != "count" else f"number of {unit}")
        out["what"] = f"How the {what} changes per {v.get('freq', 'month')}."
        fmt = _pct if pct else _num
        ch = (last["value"] - first["value"])
        F.append(f"From {pd.Timestamp(first['period']):%d %b %Y} to {pd.Timestamp(last['period']):%d %b %Y} the value went from {fmt(first['value'])} to {fmt(last['value'])}"
                 + (f" ({ch:+.1f} percentage points)." if pct else (f" ({100 * ch / first['value']:+.0f}%)." if first["value"] else ".")))
        F.append(f"Peak: {fmt(peak['value'])} in {pd.Timestamp(peak['period']):%b %Y}" + ".")
        from scipy.stats import spearmanr
        if len(s) >= 5:
            rho, p = spearmanr(np.arange(len(s)), s["value"])
            if p < 0.05:
                F.append(f"There is a consistent {'upward' if rho > 0 else 'downward'} trend (Spearman ρ = {rho:.2f}, {fmt_p(p)}, {len(s)} periods).")
                out["interpretation"] = f"The {what} has been {'rising' if rho > 0 else 'falling'} steadily rather than fluctuating randomly."
                out["implications"] = ("Capacity and resources linked to this figure may need adjusting if the trend continues." if not pct else
                                       "If this outcome is a target, the trend shows whether the situation is improving or worsening.")
            else:
                out["interpretation"] = f"No consistent trend: the {what} fluctuates without a clear direction (Spearman p = {p:.2f})."
                out["implications"] = "Plan for variability rather than a steady change."
        an = data.extra.get("anomalies")
        if an is not None and len(an):
            F.append(f"{len(an)} period(s) are unusually high or low compared with the rest (robust z-score).")
            A.append("Check the unusual periods against field events (distribution days, border closures, data-collection gaps).")
        out["limitations"].append("The latest period may be incomplete if data collection was still ongoing.")
        A.append("Update this chart each reporting period and compare against the same period last year where available.")
        return

    if t == "multiline":
        tot = tab.groupby("series")["value"].sum().sort_values(ascending=False)
        out["what"] = "Totals per period for several count columns of a related sheet."
        for k, val in tot.head(3).items():
            F.append(f"Total {L(k).lower()}: {_num(val)} over {tab['period'].nunique()} periods.")
        out["interpretation"] = "These are aggregated counts from a separate sheet; they describe volumes, not the characteristics of individual records."
        A.append("Compare these volumes with the main dataset's sample to check that the sample reflects the flows counted.")
        return

    if t == "heatmap":
        m = tab.astype(float)
        if m.size == 0:
            return
        idx = np.unravel_index(np.nanargmax(m.values), m.shape)
        idn = np.unravel_index(np.nanargmin(m.values), m.shape)
        out["what"] = f"% yes for several outcomes (columns) in each {seg_word.lower()} group (rows)."
        F.append(f"Highest: {m.columns[idx[1]]} in {m.index[idx[0]]} ({_pct(m.values[idx])}). Lowest: {m.columns[idn[1]]} in {m.index[idn[0]]} ({_pct(m.values[idn])}).")
        spread = (m.max() - m.min()).sort_values(ascending=False)
        if len(spread):
            F.append(f"'{spread.index[0]}' varies most between groups ({spread.iloc[0]:.1f} percentage points between the highest and lowest group).")
        if len(spread) and spread.iloc[0] >= 10:
            out["interpretation"] = "Outcomes that vary most between groups are where group-specific approaches matter most."
            A.append(f"Prioritise follow-up on '{spread.index[0]}' in the lowest-scoring {seg_word.lower()} groups.")
        else:
            out["interpretation"] = (f"Differences between {seg_word.lower()} groups are small (under 10 percentage points for every outcome); "
                                     "the outcomes look broadly similar across groups.")
            A.append("No group-specific follow-up is indicated by these figures; focus on the overall levels instead.")
        return

    if t == "likert":
        order = data.extra["order"]
        pos = order[-2:] if len(order) >= 4 else order[-1:]
        g = tab[tab["category"].isin(pos)].groupby("group")["pct"].sum().sort_values()
        out["what"] = "Distribution of answers on an ordered scale; negative answers to the left, positive to the right."
        for k, val in g.items():
            F.append(f"{k}: {_pct(val)} positive ({' / '.join(pos)}).")
        out["interpretation"] = "Higher positive shares indicate more favourable views; small differences between groups may not be meaningful."
        A.append("Follow up on the reasons for negative answers through feedback mechanisms or focus groups.")
        return

    if t == "pyramid":
        totals = tab.sum()
        out["what"] = "Age structure by sex."
        tot = totals.sum()
        F.append("; ".join(f"{k}: {_pct(100 * val / tot)}" for k, val in totals.items()) + f" of {int(tot):,} records with age and sex.")
        biggest = tab.sum(axis=1).idxmax()
        F.append(f"The largest age group is {biggest}.")
        out["interpretation"] = "The age–sex structure shows which groups dominate the data and which are under-represented."
        out["implications"] = "Services and messages should fit the dominant age and sex groups while still covering minorities."
        return

    if t == "sankey":
        links = tab.sort_values("value", ascending=False)
        out["what"] = "Volume of movement between origins and destinations; wider bands mean more records."
        tot = links["value"].sum()
        first_stage = links[links["source"].str.startswith(v["source"] + ": ")]
        for _, r in first_stage.head(3).iterrows():
            F.append(f"{r['source'].split(': ', 1)[1]} → {r['target'].split(': ', 1)[1]}: {_num(r['value'])} ({100 * r['value'] / max(1, first_stage['value'].sum()):.1f}% of first-stage flows).")
        out["interpretation"] = "A few corridors carry most of the movement; these are where reception and onward support are most needed."
        out["implications"] = "Align reception capacity, information points and transport support with the main corridors."
        A.append("Compare corridor volumes with the previous period to spot new or shifting routes.")
        return

    if t == "treemap":
        out["what"] = "Nested breakdown of records by location; rectangle size = number of records."
        top = tab.groupby(v["path"][0])["value"].sum().sort_values(ascending=False)
        F.append(f"{top.index[0]} has the most records ({_num(top.iloc[0])}, {100 * top.iloc[0] / top.sum():.1f}%).")
        return

    if t == "map_points":
        out["what"] = "Recorded locations; each marker is a record with valid coordinates."
        F.append(f"{len(tab):,} records with valid coordinates at {tab[[v['lat'], v['lon']]].round(3).drop_duplicates().shape[0]:,} distinct points.")
        out["limitations"].append("Map tiles require an internet connection; without it markers appear on a blank background.")
        return

    if t == "correlation":
        pairs = data.extra.get("pairs")
        out["what"] = "How strongly pairs of numeric measures rise and fall together (−1 to +1)."
        if pairs is not None and len(pairs):
            pr = pairs.dropna(subset=["r"]).assign(a=lambda x: x["r"].abs()).sort_values("a", ascending=False)
            for _, r in pr.head(3).iterrows():
                F.append(f"{L(r['x'])} and {L(r['y'])}: ρ = {r['r']:.2f} ({fmt_p(r['p_value'])}, n = {int(r['n']):,}).")
        out["interpretation"] = "Strong correlations show measures that move together. " + stats.CAUSATION_NOTE
        A.append("Use strongly correlated pairs as hypotheses for further analysis, not as evidence of cause.")
        return

    if t == "compare_table":
        out["what"] = f"Each outcome compared across {L(v.get('by')).lower()} groups, with a significance test."
        sig = tab[tab["Difference"].str.startswith("significant")] if "Difference" in tab else tab.iloc[0:0]
        F.append(f"{len(sig)} of {len(tab)} outcomes differ significantly between groups (p < 0.05).")
        for _, r in sig.head(3).iterrows():
            F.append(f"'{r['Outcome']}' differs significantly ({r['Test']}, {r['p-value']}).")
        out["interpretation"] = "Significant differences show where group membership is associated with outcomes; they do not prove cause."
        out["implications"] = "Outcomes with significant gaps are candidates for targeted or adapted programming."
        A.append("Run the same comparison in the next data round to check whether gaps persist.")
        out["limitations"].append("Many tests are run at once; some 'significant' results can occur by chance. Treat borderline p-values with caution.")
        return

    if t == "forecast":
        fc = data.extra.get("forecast")
        out["what"] = "Observed monthly volume and a statistical projection with 80% and 95% uncertainty bands."
        if fc is not None and len(fc):
            F.append(f"Projection for {pd.Timestamp(fc['period'].iloc[-1]):%b %Y}: {_num(fc['forecast'].iloc[-1])} (95% range {_num(fc['lo95'].iloc[-1])}–{_num(fc['hi95'].iloc[-1])}).")
        out["interpretation"] = "A projection assumes past patterns continue; it cannot anticipate policy changes, shocks or seasonal breaks."
        out["verified"] = False
        out["limitations"].append("This is a projection, not a finding. It is labelled as such and must not be reported as fact.")
        return

    if t == "quality_missing":
        out["what"] = "Share of records with no value, for each column with missing data."
        if len(tab):
            F.append(f"Most missing: '{tab['x'].iloc[0]}' ({_pct(tab['value'].iloc[0])}).")
            hi = tab[tab["value"] > 20]
            if len(hi):
                F.append(f"{len(hi)} column(s) have more than 20% missing values; results for them describe only those who answered.")
        A.append("Check whether high missingness reflects skip logic (expected) or non-response (a quality problem).")
        return


def summary_findings(items: list[tuple[dict, dict]], limit: int = 6) -> list[dict]:
    """Pick the strongest verified findings across visuals for the overview 'Key findings' panel."""
    scored = []
    for v, ex in items:
        if not ex.get("verified") or v["type"] in ("kpi", "methodology", "quality_missing", "text"):
            continue
        for f in ex.get("findings", [])[:2]:
            w = 3 if "statistically significant (" in f and "not statistically" not in f else (2 if "trend" in f else 1)
            scored.append((w, v.get("title"), f))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for w, title, f in scored:
        if title in seen:
            continue
        seen.add(title)
        out.append({"title": title, "text": f, "strength": w})
        if len(out) >= limit:
            break
    return out


def ai_polish(ex: dict, *, project_id: int | None, classification: str | None) -> tuple[str | None, str | None]:
    """Optional: let the local model rewrite the verified findings as one readable paragraph (guarded)."""
    from ..reports.narrative import guarded_paragraph
    facts = ex.get("findings", []) + ([ex["interpretation"]] if ex.get("interpretation") else [])
    if not facts:
        return None, "Nothing to summarise."
    return guarded_paragraph("chart explanation", facts, project_id=project_id, classification=classification)


def _complete_periods(s: pd.DataFrame, v: dict, df: pd.DataFrame | None) -> tuple[pd.DataFrame, str]:
    """For counts and sums, drop a first or last period that the data only partly covers, so a half-week is not read as a drop."""
    if v.get("measure", "count") not in ("count", "sum") or df is None or v.get("date") not in getattr(df, "columns", []) or len(s) < 4:
        return s, ""
    alias = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}.get(v.get("freq", "month"))
    dts = pd.to_datetime(df[v["date"]], errors="coerce").dropna()
    if alias is None or dts.empty or alias == "D":
        return s, ""
    p0 = pd.Timestamp(s["period"].iloc[0]).to_period(alias)
    p1 = pd.Timestamp(s["period"].iloc[-1]).to_period(alias)
    cut_first = dts.min().normalize() > p0.start_time.normalize()
    cut_last = dts.max().normalize() < p1.end_time.normalize()
    if not (cut_first or cut_last):
        return s, ""
    kept = s.iloc[(1 if cut_first else 0):(len(s) - 1 if cut_last else len(s))]
    which = " and ".join(x for x, c in (("first", cut_first), ("last", cut_last)) if c)
    return kept, f"The {which} {v.get('freq', 'month')} is only partly covered by the data, so it is left out of the comparisons above (it is still drawn)."
