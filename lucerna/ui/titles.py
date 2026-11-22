"""Human-readable chart titles, subtitles and axis labels: a presentation-only mapping.

The engine's titles are accurate but technical ("Water treated: % yes by Latrine type", "Q1 the course content was r").
This module rewrites them for readers, using only what the dataset itself provides:

- variable labels from the codebook / plan (`plan["labels"]`), else the column name cleaned up;
- the visual's own specification (type, variables, measure, unit, condition);
- never a guessed meaning. When a column name is cut short, the cut is shown with an ellipsis instead of being guessed.

The original engine title is always kept and shown in the chart's "Source & methodology" section.
Titles are phrased as the question the chart answers. Finding-style titles are not generated here: the computed,
verified finding is shown beneath the title by the viewer (from `explain`), so a claim only appears with its evidence.
"""
from __future__ import annotations

import re

ACRONYMS = {"id", "hh", "hoh", "idp", "idps", "afn", "usd", "eur", "gps", "fcs", "rcsi", "hhs", "lcs", "mpca", "cfm", "nfi", "wash", "fmp",
            "fmc", "dtm", "pdm", "un", "ngo", "sms", "gbv", "pss", "sd", "km", "kg", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"}
SHORT_WORDS = {"a", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up",
               "us", "we", "id", "hh"}
TRUNC_LEN = 26          # the engine shortens long survey headers to about this length


def _cap_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def clean(col: str | None, labels: dict | None = None) -> str:
    """Readable label for a column: codebook label if there is one, else the cleaned column name."""
    if not col:
        return ""
    labels = labels or {}
    if labels.get(col):
        return str(labels[col])
    raw = str(col)
    words = [w for w in re.split(r"[_\s]+", raw.strip()) if w]
    if not words:
        return raw
    long_name = len(raw) >= TRUNC_LEN
    fragment = long_name and not raw.endswith("_") and len(words) > 1 and len(words[-1]) <= 2 and words[-1].lower() not in SHORT_WORDS
    if fragment:                            # a one- or two-letter tail of a cut word carries no meaning: drop it
        words = words[:-1]
    truncated = long_name and (fragment or raw.endswith("_") or (len(words[-1]) <= 4 and words[-1].lower() not in SHORT_WORDS | ACRONYMS))
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        out.append(w.upper() if lw in ACRONYMS else (lw if i else _cap_first(lw)))
    text = " ".join(out)
    m = re.match(r"^(Q\d+[a-z]?)\s+(.*)$", text, flags=re.I)
    if m:                                   # survey question numbering: "Q1 · The course content was …"
        text = f"{m[1].upper()} · {_cap_first(m[2])}"
    return text + ("…" if truncated else "")


def _lc(s: str) -> str:
    """Lower-case a label for use mid-sentence, keeping acronyms and question numbers."""
    if not s or re.match(r"^(Q\d+|[A-Z]{2,})\b", s):
        return s
    return s[:1].lower() + s[1:]


def _cond_label(v: dict, labels: dict) -> str:
    c = v.get("condition") or {}
    return clean(c.get("column") or v.get("var"), labels)


def readable(v: dict, plan: dict) -> dict:
    """{"title", "subtitle", "technical"} for one visual. Deterministic; reads the spec only."""
    labels = plan.get("labels") or {}
    unit = (v.get("unit_label") or plan.get("unit_label") or "records").strip()
    t, kind, m = v.get("type"), v.get("kind"), v.get("measure")
    L = lambda c: clean(c, labels)  # noqa: E731
    technical = v.get("title") or ""
    title, sub = None, None
    x, by, val, color = v.get("x"), v.get("by"), v.get("value"), v.get("color")
    is_pct = m == "pct_condition" or v.get("as_pct") or t == "stacked100"
    if t == "bar":
        if m == "pct_condition" and x:
            title = f"How does “{_lc(_cond_label(v, labels))}” vary by {_lc(L(x))}?"
            sub = f"% answering yes, within each {_lc(L(x))} group"
        elif m in ("median", "mean", "sum") and x and val:
            word = {"median": "Median", "mean": "Average", "sum": "Total"}[m]
            title = f"{word} {_lc(L(val))} by {_lc(L(x))}"
            sub = f"{word} per group" + (" · counts sheet" if v.get("ds") else "")
        elif x and kind == "geo":
            title = f"Where are the {unit}? By {_lc(L(x))}"
            sub = (f"Top {v['top_n']} shown · " if v.get("top_n") else "") + f"number of {unit}" + (" · click a bar to drill down" if v.get("drill") else "")
        elif x:
            title = f"What is the breakdown of {_lc(L(x))}?" if kind == "composition" else f"Which {_lc(L(x))} values are most common?"
            sub = ("Top " + str(v["top_n"]) + " shown · " if v.get("top_n") else "") + (f"% of {unit} with an answer" if is_pct else f"number of {unit}")
    elif t == "stacked100" and x and color:
        title = f"How does {_lc(L(color))} differ across {_lc(L(x))}?"
        sub = f"Share within each {_lc(L(x))} group (each bar adds up to 100%)"
    elif t == "likert" and x:
        q = L(x)
        title = f"How was “{q}” rated" + (f", by {_lc(L(by))}?" if by else "?")
        sub = "Share of answers on each side of the scale; neutral answers are split across the centre"
    elif t == "multiselect" and x:
        title = f"{L(x).replace(' (multiple)', '')}: which answers were given most often?"
        sub = "% of respondents choosing each option; several answers were allowed, so totals exceed 100%"
    elif t == "donut" and x:
        title = f"What is the breakdown of {_lc(L(x))}?"
        sub = f"Share of {unit}"
    elif t == "histogram" and val:
        title = f"How is {_lc(L(val))} distributed?"
        sub = "Number of records in each range · solid line = median, dotted line = mean"
    elif t == "box" and val:
        title = f"How does {_lc(L(val))} vary" + (f" by {_lc(L(by))}?" if by else "?")
        sub = "Box = middle 50% of values, line = median, dashed = mean, dots = unusual values"
    elif t == "line":
        per = {"day": "day", "week": "week", "month": "month", "quarter": "quarter", "year": "year"}.get(v.get("freq"), "period")
        if m == "pct_condition":
            title = f"How has “{_lc(_cond_label(v, labels))}” changed over time?"
            sub = f"% answering yes, per {per}"
        elif m in ("median", "mean", "sum") and val:
            word = {"median": "median", "mean": "average", "sum": "total"}[m]
            title = f"How has the {word} {_lc(L(val))} changed over time?"
            sub = f"{_cap_first(word)} per {per}"
        else:
            title = f"How many {unit} were recorded each {per}?" + (f" By {_lc(L(color))}" if color else "")
            sub = f"Number of {unit} per {per}" + (" · dotted line = 3-period moving average" if not color else "")
    elif t == "area_stacked" and color:
        title = f"How has the mix of {_lc(L(color))} changed over time?"
        sub = "Stacked totals per period"
    elif t == "multiline":
        title = "How have the main totals changed over time?"
        sub = "Totals per " + (v.get("freq") or "period") + (" · counts sheet" if v.get("ds") else "")
    elif t == "forecast":
        title = f"What could the next {v.get('horizon', 3)} periods look like?"
        sub = "Projection from past values, not a measured result · shaded bands = 80% and 95% intervals"
    elif t == "heatmap" and x:
        title = f"Which outcomes differ across {_lc(L(x))}?"
        sub = "% answering yes for each outcome, within each group · stronger colour = higher"
    elif t == "correlation":
        title = "Which numeric measures move together?"
        sub = "Spearman correlation: +1 = rise together, −1 = move in opposite directions, 0 = no relationship"
    elif t == "pyramid":
        title = "What is the age and sex profile?"
        sub = f"Number of {unit} in each age group, by sex"
    elif t == "sankey":
        stages = [L(s) for s in (v.get("source"), v.get("via"), v.get("target")) if s]
        title = "Where do movements start and end?" if len(stages) >= 2 else technical
        sub = " → ".join(stages) + (f" · weighted by {_lc(L(v['value']))}" if v.get("value") else "")
    elif t == "map_points":
        title = "Where were the records collected?"
        sub = "Recorded GPS locations" + (f", coloured by {_lc(L(color))}" if color else "")
    elif t == "choropleth":
        title = "How do values compare across areas?"
        sub = "Stronger colour = higher value"
    elif t == "treemap":
        path = [L(p) for p in v.get("path", [])]
        title = f"How are {unit} spread across {_lc(path[0])}?" if path else technical
        sub = " › ".join(path) + " · size = number of records"
    elif t == "quality_missing":
        title = "Which columns have missing values?"
        sub = "% of records with no value, per column"
    elif t == "table":
        title = technical.replace("_", " ")
        sub = "Totals per group" if v.get("agg") == "sum" else None
    elif t == "stat_summary":
        title = "Key statistics for the numeric measures"
        sub = "Count, mean, median, spread and range per measure"
    elif t == "compare_table":
        title = technical.replace(" (significance tests)", "")
        sub = "Statistical tests of differences between groups (p-values with effect sizes)"
    elif t == "kpi":
        title = kpi_label(v, labels)
    elif t == "methodology":
        title = "How this dashboard was made"
        sub = "Data sources, methods and limitations"
    if not title:
        title = _tidy(technical, labels)
    return {"title": title, "subtitle": sub, "technical": technical}


def kpi_label(v: dict, labels: dict | None = None) -> str:
    """KPI card label: the engine label with any raw column name replaced by its readable form."""
    t = v.get("title") or ""
    c = (v.get("condition") or {}).get("column") or v.get("var")
    if v.get("kpi") == "pct" and c:
        lab = clean(c, labels)
        vals = (v.get("condition") or {}).get("value") or []
        yes = all(str(x).lower() in ("yes", "true", "1") for x in vals)
        if yes or not vals:
            return lab
        return f"{lab}: {', '.join(str(x) for x in vals[:2]).lower()}"
    return _tidy(t, labels)


def _tidy(text: str, labels: dict) -> str:
    """Generic clean-up of an engine title: replace raw column names by labels, tidy capitalisation."""
    if not text:
        return text
    for col, lab in sorted((labels or {}).items(), key=lambda kv: -len(kv[0])):
        text = text.replace(col, lab)
    text = re.sub(r"\b([a-z]+(?:_[a-z0-9]+)+)\b", lambda m_: clean(m_[1]).lower(), text)
    return _cap_first(text.replace("  ", " ").strip())


def axis_label(text: str | None, labels: dict) -> str | None:
    """Readable axis title: 'Median of amount_received_afn' → 'Median of amount received (AFN)'."""
    if not text:
        return text
    m = re.match(r"^(Median|Mean|Sum|Unique|Min|Max) of (.+)$", text)
    if m:
        word = {"Mean": "Average", "Sum": "Total"}.get(m[1], m[1])
        return f"{word} {_lc(clean(m[2], labels))}"
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", text):
        return clean(text, labels)
    return text
