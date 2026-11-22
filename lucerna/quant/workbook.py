"""Workbook intelligence: what each sheet is, which one is the main analytical dataset, and how sheets relate.

Deterministic rules only. Every decision carries a reason that is shown to the user and stored with the
dataset, so "why was this sheet chosen?" always has an answer.

Sheet roles
    survey        record-level microdata (one row per respondent / household / interview / case)
    monitoring    aggregated monitoring counts (one row per place × period with count columns)
    sampling_frame  list of locations/units with population estimates used to plan collection
    indicator_map indicator definitions (numerator, denominator, source)
    codebook      variable dictionary / XLSForm survey or choices sheet
    lookup        small reference list (codes and names)
    documentation free text (README, notes, disclaimers)
    other_table   a data table that fits none of the above
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

ANALYTICAL_ROLES = ("survey", "monitoring", "sampling_frame", "other_table")
ROLE_LABELS = {
    "survey": "Survey / record-level data", "monitoring": "Aggregated monitoring counts", "sampling_frame": "Sampling frame",
    "indicator_map": "Indicator definitions", "codebook": "Codebook / data dictionary", "lookup": "Reference list",
    "documentation": "Documentation", "other_table": "Other data table",
}
NAME_HINTS = {
    "documentation": r"read.?me|about|note|instruction|disclaimer|cover|guide|method|changelog|contents|info",
    "codebook": r"code.?book|dictionary|variables?\b|metadata|xlsform|^survey$|choices|labels?|data.?dict",
    "indicator_map": r"indicator|logframe|framework|kpi.?def|results?.?matrix|pmf",
    "lookup": r"lookup|look.?up|\blist\b|^ref|reference|pcode|admin.?codes|codes$|mapping",
    "sampling_frame": r"sampl|frame|master.?list|population|census|baseline.?list|site.?list|settlement.?list",
    "monitoring": r"daily|weekly|monthly|count|fmc|tally|monitor|tracking|movement.?log|inflow|outflow|summary|aggregate",
    "survey": r"survey|fms|data$|raw|main|responses?|interview|household|hh|records|submissions?|microdata|clean",
}
CODEBOOK_COLS = r"^(variable|var|var_name|name|field|column|question|question_name|label|type|list_name|choices?|allowed|values?|description|definition)(_\w+)?$"
INDICATOR_COLS = r"indicator|numerator|denominator|definition|baseline|target|source"
COUNT_COL = r"individual|persons?|people|count|total|number|_n$|families|households|arrivals|returnees|deportees|inflow|outflow|males?|females?|children"
POP_COL = r"population|pop_|_pop|estimated|estimate|households_total|est_"


@dataclass
class SheetInfo:
    name: str
    rows: int
    cols: int
    role: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0
    is_primary: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role_label"] = ROLE_LABELS[self.role]
        return d


def _text_share(df: pd.DataFrame) -> float:
    s = df.astype("string").stack()
    if s.empty:
        return 0.0
    return float((s.str.len() > 60).mean())


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        v = pd.to_numeric(df[c].astype("string").str.replace(",", "", regex=False), errors="coerce")
        nn = df[c].notna().sum()
        if nn and v.notna().sum() / nn >= .9:
            out.append(c)
    return out


def _has_date(df: pd.DataFrame) -> bool:
    for c in df.columns:
        if re.search(r"date|day|month|period|week", str(c).lower()):
            s = df[c].dropna().astype(str).head(200)
            if len(s) and s.str.match(r"^\d{4}-\d{1,2}(-\d{1,2})?|^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}").mean() > .7:
                return True
    return False


def _unique_key(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if re.search(r"(^|_)(id|uuid|code|key)$|^id_|_id$", str(c).lower()):
            s = df[c].dropna()
            if len(s) >= max(5, .9 * len(df)) and s.nunique() / len(s) >= .97:
                return c
    return None


def classify_sheet(name: str, df: pd.DataFrame, other_columns: set[str] | None = None) -> SheetInfo:
    """Return the role of one sheet with the evidence for it."""
    rows, cols = df.shape
    low = name.lower().strip()
    colnames = [str(c).lower() for c in df.columns]
    scores: dict[str, float] = {r: 0.0 for r in ROLE_LABELS}
    why: dict[str, list[str]] = {r: [] for r in ROLE_LABELS}

    def add(role, pts, reason):
        scores[role] += pts
        why[role].append(reason)

    for role, pat in NAME_HINTS.items():
        if re.search(pat, low):
            add(role, 2.0, f"sheet name '{name}' suggests {ROLE_LABELS[role].lower()}")

    # documentation: one or two columns of long text, or very few cells
    text_share = _text_share(df)
    if cols <= 2 and text_share > .3:
        add("documentation", 4, f"{cols} column(s) of mostly long text ({text_share:.0%} of cells over 60 characters)")
    if rows * cols <= 12 and not _numeric_cols(df):
        add("documentation", 1.5, "very few cells and no numeric columns")

    # codebook: dictionary-like column names, and/or a column whose values are column names of other sheets
    cb_cols = [c for c in colnames if re.search(CODEBOOK_COLS, c)]
    if len(cb_cols) >= 2:
        add("codebook", 2.5, f"dictionary-style columns: {', '.join(cb_cols[:4])}")
    if other_columns:
        for c in df.columns:
            vals = set(df[c].dropna().astype(str).str.strip().str.lower())
            if len(vals) >= 5:
                hit = len(vals & other_columns) / len(vals)
                if hit >= .5:
                    add("codebook", 5, f"{hit:.0%} of the values in '{c}' are column names of other sheets (it describes their variables)")
                    break

    # indicator map
    ind_cols = [c for c in colnames if re.search(INDICATOR_COLS, c)]
    if len(ind_cols) >= 2 and rows <= 300 and any(re.search(r"indicator|numerator|denominator", c) for c in colnames):
        add("indicator_map", 3 + .5 * len(ind_cols), f"indicator-definition columns: {', '.join(ind_cols[:4])}")

    numeric = _numeric_cols(df)
    count_cols = [c for c in numeric if re.search(COUNT_COL, str(c).lower())]
    pop_cols = [c for c in numeric if re.search(POP_COL, str(c).lower())]
    dated = _has_date(df)
    key = _unique_key(df)

    # lookup: small, few columns, code-name pairs
    if rows <= 120 and cols <= 4 and not count_cols:
        add("lookup", 2.5, f"small reference table ({rows} rows × {cols} columns) without measures")

    # sampling frame: locations + population estimates
    if pop_cols:
        add("sampling_frame", 3, f"population-estimate columns: {', '.join(pop_cols[:3])}")
    if any(re.search(r"settlement|site|village|location|community|camp", c) for c in colnames) and not dated:
        add("sampling_frame", 1, "one row per location, no interview dates")

    # monitoring counts: dated rows with several count columns and few categorical respondent attributes
    if dated and len(count_cols) >= 3:
        add("monitoring", 3 + min(2, len(count_cols) / 4), f"dated rows with {len(count_cols)} count columns ({', '.join(count_cols[:3])}…)")
    elif dated and count_cols and rows >= 20:
        add("monitoring", 2, f"dated rows with count column(s) {', '.join(count_cols[:3])}")

    # survey microdata: many rows, many columns, respondent attributes, a unique record key
    respondent = [c for c in colnames if re.search(r"sex|gender|age|respondent|marital|head_of|hh_|household|education|occupation|consent", c)]
    if rows >= 50 and cols >= 8:
        add("survey", 1 + min(3.0, np.log10(rows)), f"{rows:,} rows × {cols} columns")
    if len(respondent) >= 2:
        add("survey", 2 + min(2, len(respondent) / 3), f"respondent-level variables ({', '.join(respondent[:4])})")
    if key and rows >= 50:
        add("survey", 1.5, f"'{key}' identifies each record")
    if dated and rows >= 200 and len(respondent) >= 2:
        add("survey", 1, "interview dates on each record")

    if rows >= 30 and cols >= 3 and numeric:
        add("other_table", 1, "a data table with numeric columns")

    role = max(scores, key=lambda r: scores[r])
    best = scores[role]
    if best <= 0:
        role, best = ("other_table", .5) if rows >= 2 else ("documentation", .5)
        why[role].append("no strong signal; treated as a generic table")
    ranked = sorted(scores.values(), reverse=True)
    margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0)
    conf = round(float(min(.97, .45 + .08 * best + .05 * margin)), 2)
    return SheetInfo(name, int(rows), int(cols), role, conf, why[role])


def _primary_score(info: SheetInfo, df: pd.DataFrame) -> float:
    """How suitable a sheet is as the main analytical dataset. Size and record-level richness dominate."""
    base = {"survey": 10, "monitoring": 6, "other_table": 4, "sampling_frame": 3}.get(info.role, -100)
    return base + 2 * np.log10(max(info.rows, 1)) + .08 * min(info.cols, 80) + info.confidence


KEYISH = r"code|key|province|district|region|country|state|county|site|settlement|camp|village|market|location|(^|_| )id$|_id\b"


def _stem(col) -> str:
    """Column name without a short leading namespace (e.g. 'hh_', 'grp1_', 'loc_'), so 'hh_district' matches 'district'."""
    c = str(col).lower().strip()
    m = re.match(r"^[a-z]{1,4}\d?_(.{4,})$", c)
    return m.group(1) if m else c


def detect_relationships(frames: dict[str, pd.DataFrame], infos: dict[str, SheetInfo]) -> list[dict]:
    """Shared keys between analytical sheets, validated by value overlap (not just matching names)."""
    rels = []
    names = [n for n in frames if infos[n].role in ANALYTICAL_ROLES]

    def norm(s):
        return set(s.dropna().astype(str).str.strip().str.lower().unique()[:5000])

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            da, db_ = frames[a], frames[b]
            for ca in da.columns:
                va = norm(da[ca])
                if not (2 <= len(va) <= 5000):
                    continue
                for cb in db_.columns:
                    same_name = str(ca).lower() == str(cb).lower()
                    similar = same_name or _stem(ca) == _stem(cb)
                    if not similar and not re.search(KEYISH, str(ca).lower() + " " + str(cb).lower()):
                        continue
                    vb = norm(db_[cb])
                    if len(vb) < 2:
                        continue
                    inter = va & vb
                    cover = len(inter) / min(len(va), len(vb))
                    if cover < .6 or len(inter) < 2:
                        continue
                    ua = da[ca].dropna().is_unique
                    ub = db_[cb].dropna().is_unique
                    kind = "one-to-many" if (ua or ub) else "shared dimension"
                    rels.append({"same_name": same_name, "left": a, "left_column": str(ca), "right": b, "right_column": str(cb), "kind": kind,
                                 "matched_values": len(inter), "coverage": round(cover, 3),
                                 "reason": f"{len(inter)} of {min(len(va), len(vb))} distinct values of '{ca}' and '{cb}' match ({cover:.0%})."})
    # keep the strongest link per sheet pair and column
    rels.sort(key=lambda r: (not r["same_name"], -r["coverage"], -r["matched_values"]))
    seen, out = set(), []
    for r in rels:
        k = (r["left"], r["right"], r["left_column"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out[:40]


def analyse(frames: dict[str, pd.DataFrame]) -> dict:
    """Classify every sheet, choose the primary analytical sheet and explain how the others are used."""
    all_cols = {n: {str(c).strip().lower() for c in df.columns} for n, df in frames.items()}
    infos = {}
    for n, df in frames.items():
        others = set().union(*[c for m, c in all_cols.items() if m != n]) if len(frames) > 1 else set()
        infos[n] = classify_sheet(n, df, others)
    candidates = [n for n in frames if infos[n].role in ANALYTICAL_ROLES]
    for n in candidates:
        infos[n].score = round(float(_primary_score(infos[n], frames[n])), 2)
    primary = max(candidates, key=lambda n: infos[n].score) if candidates else None
    explanation = []
    if primary:
        infos[primary].is_primary = True
        p = infos[primary]
        explanation.append(f"'{primary}' was chosen as the main analytical dataset: {ROLE_LABELS[p.role].lower()} with {p.rows:,} rows and "
                           f"{p.cols} columns ({'; '.join(p.reasons[:3])}).")
        for n in candidates:
            if n != primary:
                explanation.append(f"'{n}' ({infos[n].rows:,} rows) was not chosen as the main dataset: it is {ROLE_LABELS[infos[n].role].lower()}.")
    else:
        explanation.append("No sheet contains analysable record-level or count data; only reference or documentation sheets were found.")
    for n, i in infos.items():
        if i.role not in ANALYTICAL_ROLES:
            use = {"codebook": "used to label variables and documented in the methodology, never analysed as data",
                   "indicator_map": "kept as indicator documentation, never analysed as data",
                   "lookup": "kept as a reference list, never analysed as data",
                   "documentation": "kept as documentation, never analysed as data"}[i.role]
            explanation.append(f"'{n}' ({i.rows:,} rows) is {ROLE_LABELS[i.role].lower()}: {use}.")
    rels = detect_relationships(frames, infos)
    linked = []
    if primary:
        for r in rels:
            other = r["right"] if r["left"] == primary else (r["left"] if r["right"] == primary else None)
            if other and other not in [x["sheet"] for x in linked]:
                pcol = r["left_column"] if r["left"] == primary else r["right_column"]
                ocol = r["right_column"] if r["left"] == primary else r["left_column"]
                decision = ("analysed separately and shown alongside the main data (different unit of analysis: rows are not merged, "
                            "so no record is double-counted)")
                linked.append({"sheet": other, "role": infos[other].role, "primary_column": pcol, "other_column": ocol,
                               "kind": r["kind"], "reason": r["reason"], "decision": decision})
                explanation.append(f"'{other}' links to '{primary}' through {pcol} ↔ {ocol} ({r['reason'].rstrip('.')}). It is {decision}.")
    return {"sheets": [infos[n].to_dict() for n in frames], "primary": primary, "relationships": rels, "linked": linked,
            "explanation": explanation}


def codebook_labels(df: pd.DataFrame, target_columns: list[str], target_sheet: str | None = None) -> dict[str, str]:
    """Variable → label pairs from a codebook sheet, only for variables that exist in the target dataset.
    When the codebook has a sheet/table column, only rows describing the target sheet are used."""
    cols = {str(c).lower(): c for c in df.columns}
    sheet_col = next((cols[c] for c in ("sheet", "table", "dataset", "worksheet", "source_sheet") if c in cols), None)
    if sheet_col and target_sheet:
        own = df[df[sheet_col].astype(str).str.strip().str.lower() == target_sheet.strip().lower()]
        if len(own):
            df = own
    var_col = next((cols[c] for c in ("variable", "var", "var_name", "name", "field", "column", "question_name") if c in cols), None)
    lab_col = next((cols[c] for c in ("label", "label::english", "label_en", "description", "question", "definition") if c in cols), None)
    if not var_col or not lab_col:
        return {}
    targets = {str(c).strip().lower(): c for c in target_columns}
    out = {}
    for _, r in df[[var_col, lab_col]].dropna().iterrows():
        k = str(r[var_col]).strip().lower()
        if k in targets and str(r[lab_col]).strip():
            out[targets[k]] = str(r[lab_col]).strip()[:120]
    return out
