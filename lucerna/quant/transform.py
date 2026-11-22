"""Typed analytical copy + reproducible, approvable transformations.

The original parsed table is stored read-only. The analytical copy is rebuilt deterministically:
    analytic = apply(approved transformations, in order, to typed(original, confirmed mapping))
so any result can be reproduced from the original plus the transformation log.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .profile import NO, YES, normalise_missing, to_datetime, to_numeric


def apply_types(df: pd.DataFrame, mapping: dict[str, dict]) -> pd.DataFrame:
    """mapping: column -> {"type": ..., "role": ...}. Unconvertible values become missing (counted in quality)."""
    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        m = mapping.get(col, {})
        t = m.get("type") or "categorical"
        s = normalise_missing(df[col])
        if t in ("numeric", "integer"):
            out[col] = to_numeric(s)
        elif t == "date":
            out[col] = to_datetime(s.astype("string"))
        elif t == "boolean":
            low = s.astype("string").str.strip().str.lower()
            out[col] = low.map(lambda v: True if v in YES else (False if v in NO else pd.NA)).astype("boolean")
        elif t == "ignore":
            continue
        else:
            out[col] = s.astype("string").str.strip()
            out.loc[out[col] == "", col] = pd.NA
    return out


# ------------------------------------------------------------------ operations
# Each op: fn(df, **params) -> (df, rows_affected, cells_affected). Pure; never touches the original.

def op_trim_whitespace(df, columns=None):
    cells = 0
    for c in columns or [c for c in df.columns if pd.api.types.is_string_dtype(df[c])]:
        if c in df and pd.api.types.is_string_dtype(df[c]):
            before = df[c].copy()
            df[c] = df[c].str.replace(r"\s+", " ", regex=True).str.strip()
            cells += int((before.fillna("") != df[c].fillna("")).sum())
    return df, None, cells


def op_standardize_categories(df, column, mapping: dict[str, str]):
    """mapping: observed value -> standard value (exact match on the observed value)."""
    before = df[column].copy()
    df[column] = df[column].map(lambda v: mapping.get(v, v) if pd.notna(v) else v)
    changed = int((before.fillna("\0") != df[column].fillna("\0")).sum())
    return df, changed, changed


def op_set_missing_codes(df, column, codes: list):
    s = df[column]
    codes_str = {str(c).strip().lower() for c in codes}
    mask = s.astype("string").str.strip().str.lower().isin(codes_str).fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        num_codes = [float(c) for c in codes if re.fullmatch(r"-?\d+(\.\d+)?", str(c).strip())]
        mask = mask | s.isin(num_codes)
    n = int(mask.sum())
    df.loc[mask, column] = pd.NA if not pd.api.types.is_numeric_dtype(s) else np.nan
    return df, n, n


def op_drop_duplicates(df, keys: list[str] | None = None, keep: str = "first"):
    before = len(df)
    df = df.drop_duplicates(subset=keys or None, keep=keep).reset_index(drop=True)
    return df, before - len(df), None


def op_flag_outliers(df, column, method: str = "iqr", k: float = 1.5):
    """Adds a boolean flag column; values are NOT removed or changed."""
    s = df[column].astype(float)
    if method == "iqr":
        q1, q3 = s.quantile(.25), s.quantile(.75)
        iqr = q3 - q1
        flag = (s < q1 - k * iqr) | (s > q3 + k * iqr)
    else:
        med = s.median()
        mad = (s - med).abs().median() or np.nan
        flag = ((s - med).abs() / (1.4826 * mad)) > k
    name = f"{column}__outlier_flag"
    df[name] = flag.fillna(False)
    return df, int(df[name].sum()), None


def op_set_range_invalid(df, column, min_value=None, max_value=None):
    """Values outside [min,max] become missing (e.g., age 999). Requires approval because it changes data."""
    s = df[column]
    mask = pd.Series(False, index=df.index)
    if min_value is not None:
        mask |= s < float(min_value)
    if max_value is not None:
        mask |= s > float(max_value)
    mask = mask.fillna(False)
    n = int(mask.sum())
    df.loc[mask, column] = np.nan
    return df, n, n


def op_recode(df, column, new_column, mapping: dict[str, str]):
    df[new_column] = df[column].map(lambda v: mapping.get(str(v), pd.NA) if pd.notna(v) else pd.NA).astype("string")
    return df, None, int(df[new_column].notna().sum())


def op_bin_numeric(df, column, new_column, edges: list[float], labels: list[str] | None = None):
    labels = labels or [f"{edges[i]:g}–{edges[i + 1]:g}" for i in range(len(edges) - 1)]
    df[new_column] = pd.cut(df[column].astype(float), bins=edges, labels=labels, right=False, include_lowest=True).astype("string")
    return df, None, int(df[new_column].notna().sum())


def op_rename_column(df, column, new_name):
    if new_name in df.columns:
        raise ValueError(f"Column '{new_name}' already exists.")
    return df.rename(columns={column: new_name}), None, None


def op_exclude_rows(df, column, op: str, value: Any):
    """Exclude rows matching a condition (e.g., consent == No). Logged and reversible."""
    mask = condition_mask(df, column, op, value)
    n = int(mask.sum())
    return df.loc[~mask].reset_index(drop=True), n, None


def op_weighted_sum(df, new_column, weights: dict[str, float], min_valid: int | None = None):
    """Derived score = sum(weight × column). Rows missing any component stay missing unless min_valid is set."""
    cols = list(weights)
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    score = sum(sub[c] * float(w) for c, w in weights.items())
    if min_valid is not None:
        score = (sub.fillna(0).mul(pd.Series(weights)).sum(axis=1)).where(sub.notna().sum(axis=1) >= min_valid)
    df[new_column] = score
    return df, None, int(df[new_column].notna().sum())


OPERATIONS = {
    "weighted_sum": (op_weighted_sum, "Create a derived score as a weighted sum of columns"),
    "trim_whitespace": (op_trim_whitespace, "Trim and collapse whitespace in text columns"),
    "standardize_categories": (op_standardize_categories, "Map inconsistent category spellings to a standard value"),
    "set_missing_codes": (op_set_missing_codes, "Treat sentinel codes (e.g. -99, 999, 'don't know') as missing"),
    "drop_duplicates": (op_drop_duplicates, "Remove duplicate records"),
    "flag_outliers": (op_flag_outliers, "Add an outlier flag column (values unchanged)"),
    "set_range_invalid": (op_set_range_invalid, "Set values outside a valid range to missing"),
    "recode": (op_recode, "Create a recoded column"),
    "bin_numeric": (op_bin_numeric, "Create a banded column (e.g. age groups)"),
    "rename_column": (op_rename_column, "Rename a column"),
    "exclude_rows": (op_exclude_rows, "Exclude rows matching a condition"),
}


def condition_mask(df: pd.DataFrame, column: str, op: str, value: Any) -> pd.Series:
    """Structured (non-eval) condition evaluation shared by indicators, rules and filters."""
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")
    s = df[column]
    if op == "notnull":
        return s.notna()
    if op == "isnull":
        return s.isna()
    if op in ("in", "not_in"):
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        if pd.api.types.is_bool_dtype(s):
            target = {str(v).strip().lower() in YES for v in vals}
            m = s.isin(list(target))
        elif pd.api.types.is_numeric_dtype(s):
            m = s.isin([float(v) for v in vals if _is_number(v)])
        else:
            vs = {str(v).strip().lower() for v in vals}
            m = s.astype("string").str.strip().str.lower().isin(vs)
        m = m.fillna(False).astype(bool)
        return m if op == "in" else (~m & s.notna())
    if op == "contains":
        return s.astype("string").str.contains(str(value), case=False, regex=False).fillna(False).astype(bool)
    if op in ("==", "!=", ">", ">=", "<", "<="):
        if pd.api.types.is_datetime64_any_dtype(s):
            v = pd.to_datetime(value)
        elif pd.api.types.is_numeric_dtype(s):
            v = float(value)
        elif pd.api.types.is_bool_dtype(s):
            v = str(value).strip().lower() in YES
        else:
            v = str(value)
            s = s.astype("string")
            if op in ("==", "!="):
                m = s.str.strip().str.lower() == v.strip().lower()
                m = m.fillna(False).astype(bool)
                return m if op == "==" else (~m & s.notna())
        m = {"==": s == v, "!=": s != v, ">": s > v, ">=": s >= v, "<": s < v, "<=": s <= v}[op]
        return m.fillna(False).astype(bool)
    raise ValueError(f"Unsupported operator {op}")


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def apply_operations(df: pd.DataFrame, ops: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
    """ops: [{"operation": name, "params": {...}, "id": ...}] applied in order. Returns df and per-op stats."""
    df = df.copy()
    stats = []
    for o in ops:
        fn = OPERATIONS[o["operation"]][0]
        df, rows, cells = fn(df, **(o.get("params") or {}))
        stats.append({"id": o.get("id"), "operation": o["operation"], "rows_affected": rows, "cells_affected": cells})
    return df, stats
