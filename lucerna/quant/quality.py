"""Data-quality assessment (read-only). Produces findings and *proposed* transformations;
nothing is changed until a user approves a proposal."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import pandas as pd

ROLE_RANGES = {"age": (0, 120), "household_size": (1, 50), "latitude": (-90, 90), "longitude": (-180, 180)}
SENTINELS = [-99, -999, -9, 999, 9999, -1]
SENTINEL_TEXT = ["don't know", "dont know", "dk", "refused", "prefer not to answer", "not applicable"]


def _norm_key(v: str) -> str:
    v = unicodedata.normalize("NFKC", str(v)).lower().strip()
    v = re.sub(r"[\s_\-.]+", " ", v)
    return v


def inconsistent_categories(s: pd.Series) -> list[dict]:
    """Groups of values that differ only by case/whitespace/punctuation (e.g. 'Kabul', 'kabul ', 'KABUL')."""
    vc = s.dropna().astype(str).value_counts()
    groups = defaultdict(list)
    for val, n in vc.items():
        groups[_norm_key(val)].append((val, int(n)))
    out = []
    for key, members in groups.items():
        if len(members) > 1:
            members.sort(key=lambda x: -x[1])
            out.append({"canonical": members[0][0].strip(), "variants": members})
    return out


def assess(df: pd.DataFrame, mapping: dict[str, dict], id_columns: list[str] | None = None) -> dict:
    n = len(df)
    findings: list[dict] = []
    proposals: list[dict] = []
    col_stats = []

    for col in df.columns:
        s = df[col]
        role = (mapping.get(col) or {}).get("role")
        miss = int(s.isna().sum())
        col_stats.append({"column": col, "missing": miss, "pct_missing": round(100 * miss / n, 2) if n else 0,
                          "role": role, "dtype": str(s.dtype)})
        if n and miss / n > 0.3:
            findings.append({"severity": "warning", "column": col, "type": "high_missingness",
                             "message": f"{miss/n:.0%} of values are missing in '{col}'."})
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            nn = s.dropna()
            sentinel_hits = {v: int((nn == v).sum()) for v in SENTINELS if (nn == v).sum() > 0}
            if sentinel_hits:
                findings.append({"severity": "warning", "column": col, "type": "sentinel_codes",
                                 "message": f"Possible missing-value codes in '{col}': {sentinel_hits}"})
                proposals.append({"operation": "set_missing_codes", "params": {"column": col, "codes": list(sentinel_hits)},
                                  "description": f"Treat {list(sentinel_hits)} in '{col}' as missing"})
            if role in ROLE_RANGES:
                lo, hi = ROLE_RANGES[role]
                bad = int(((nn < lo) | (nn > hi)).sum())
                if bad:
                    findings.append({"severity": "error", "column": col, "type": "invalid_range",
                                     "message": f"{bad} value(s) in '{col}' are outside the valid {role} range {lo}–{hi}."})
                    proposals.append({"operation": "set_range_invalid", "params": {"column": col, "min_value": lo, "max_value": hi},
                                      "description": f"Set {role} values outside {lo}–{hi} in '{col}' to missing"})
            if len(nn) >= 20 and role not in ("identifier", "latitude", "longitude"):
                q1, q3 = nn.quantile(.25), nn.quantile(.75)
                iqr = q3 - q1
                if iqr > 0:
                    out = int(((nn < q1 - 3 * iqr) | (nn > q3 + 3 * iqr)).sum())
                    if out:
                        findings.append({"severity": "info", "column": col, "type": "outliers",
                                         "message": f"{out} extreme value(s) in '{col}' (beyond 3×IQR). Review before analysis; they are not removed automatically."})
                        proposals.append({"operation": "flag_outliers", "params": {"column": col, "method": "iqr", "k": 3.0},
                                          "description": f"Flag extreme values in '{col}' (values unchanged)"})
        elif pd.api.types.is_datetime64_any_dtype(s):
            nn = s.dropna()
            future = int((nn > pd.Timestamp.now() + pd.Timedelta(days=1)).sum())
            old = int((nn < pd.Timestamp("1990-01-01")).sum())
            if future:
                findings.append({"severity": "error", "column": col, "type": "future_dates", "message": f"{future} date(s) in '{col}' are in the future."})
            if old:
                findings.append({"severity": "warning", "column": col, "type": "implausible_dates", "message": f"{old} date(s) in '{col}' are before 1990."})
        elif pd.api.types.is_string_dtype(s) or s.dtype == object:
            ss = s.dropna().astype(str)
            if len(ss) and (ss != ss.str.strip()).any():
                k = int((ss != ss.str.strip()).sum())
                findings.append({"severity": "info", "column": col, "type": "whitespace", "message": f"{k} value(s) in '{col}' have leading/trailing spaces."})
            if role not in ("free_text", "identifier", "personal_name") and s.nunique() <= 200:
                groups = inconsistent_categories(s)
                if groups:
                    mp = {v: g["canonical"] for g in groups for v, _ in g["variants"] if v != g["canonical"]}
                    findings.append({"severity": "warning", "column": col, "type": "inconsistent_categories",
                                     "message": f"{len(groups)} category group(s) in '{col}' differ only by spelling/case, e.g. {groups[0]['variants'][:3]}"})
                    proposals.append({"operation": "standardize_categories", "params": {"column": col, "mapping": mp},
                                      "description": f"Standardise {len(mp)} spelling variant(s) in '{col}'"})
                low = ss.str.strip().str.lower()
                st_hits = [t for t in SENTINEL_TEXT if (low == t).any()]
                if st_hits:
                    findings.append({"severity": "info", "column": col, "type": "dont_know_values",
                                     "message": f"'{col}' contains {st_hits}. Decide whether these are valid answers or missing."})

    # Duplicates
    full_dupes = int(df.duplicated().sum())
    if full_dupes:
        findings.append({"severity": "error", "column": None, "type": "duplicate_rows", "message": f"{full_dupes} fully duplicated row(s)."})
        proposals.append({"operation": "drop_duplicates", "params": {"keys": None}, "description": f"Remove {full_dupes} fully duplicated row(s)"})
    id_dupes = {}
    for idc in id_columns or []:
        if idc in df:
            d = int(df[idc].dropna().duplicated().sum())
            if d:
                id_dupes[idc] = d
                findings.append({"severity": "warning", "column": idc, "type": "duplicate_ids",
                                 "message": f"{d} repeated value(s) in identifier '{idc}'. If one row should be one beneficiary/household, these may be duplicates; if rows are events/members, repeats are expected."})
    if "consent" in " ".join(c.lower() for c in df.columns):
        cc = [c for c in df.columns if "consent" in c.lower()][0]
        no = int(df[cc].astype("string").str.lower().isin(["no", "false", "0", "n"]).sum())
        if no:
            findings.append({"severity": "error", "column": cc, "type": "no_consent",
                             "message": f"{no} record(s) have consent = No. They should normally be excluded from analysis."})
            proposals.append({"operation": "exclude_rows", "params": {"column": cc, "op": "in", "value": ["no", "false", "0", "n"]},
                              "description": f"Exclude {no} record(s) without consent"})

    total_cells = n * max(1, df.shape[1])
    completeness = round(100 * (1 - df.isna().sum().sum() / total_cells), 2) if n else 0.0
    return {
        "n_rows": n, "n_columns": int(df.shape[1]), "completeness_pct": completeness,
        "duplicate_rows": full_dupes, "duplicate_ids": id_dupes,
        "columns": col_stats, "findings": findings, "proposals": proposals,
    }


def validate_rules(df: pd.DataFrame, rules: list[dict]) -> list[dict]:
    """Logical rules: {"name","if":{"column","op","value"}, "then":{"column","op","value"}} → violations count.
    Example: if age < 15 then marital_status in [single]."""
    from .transform import condition_mask
    out = []
    for r in rules:
        try:
            cond = condition_mask(df, **r["if"]) if r.get("if") else pd.Series(True, index=df.index)
            ok = condition_mask(df, **r["then"])
            viol = cond & ~ok & df[r["then"]["column"]].notna()
            out.append({"rule": r.get("name", "rule"), "violations": int(viol.sum()), "rows_checked": int(cond.sum()),
                        "example_rows": [int(i) for i in viol[viol].index[:10]]})
        except Exception as exc:
            out.append({"rule": r.get("name", "rule"), "error": str(exc)})
    return out
