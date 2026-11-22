"""Humanitarian counting logic: never sums different units of analysis together."""
from __future__ import annotations

import pandas as pd

UNIT_LABELS = {
    "household": "households", "individual": "individuals", "respondent": "survey respondents",
    "assistance_event": "assistance events / distribution records", "movement": "movements",
    "visit": "visits", "case": "cases", "beneficiary": "unique beneficiaries", "unknown": "records (unit not confirmed)",
    "other": "records",
}


def count_summary(df: pd.DataFrame, unit: str, id_column: str | None = None, household_id: str | None = None,
                  household_size: str | None = None) -> dict:
    """Return counts with explicit units and the rules used."""
    rows = len(df)
    out = {"records": {"value": rows, "unit": UNIT_LABELS.get(unit, "records"), "rule": "Number of rows in the analytical dataset."}}
    notes = []
    if id_column and id_column in df:
        uniq = int(df[id_column].dropna().nunique())
        out["unique_ids"] = {"value": uniq, "unit": f"unique values of '{id_column}'",
                             "rule": f"Distinct non-missing '{id_column}'."}
        rep = rows - uniq - int(df[id_column].isna().sum())
        if rep > 0:
            notes.append(f"{rep} rows repeat an existing '{id_column}'. If '{id_column}' identifies beneficiaries, these rows are repeat events or possible duplicates — they are not additional beneficiaries.")
    if household_id and household_id in df:
        out["households"] = {"value": int(df[household_id].dropna().nunique()), "unit": "households",
                             "rule": f"Distinct non-missing '{household_id}'."}
    if household_size and household_size in df and unit == "household":
        hs = pd.to_numeric(df[household_size], errors="coerce")
        key = household_id if household_id and household_id in df else None
        base = df.assign(__hs=hs)
        if key:
            base = base.drop_duplicates(subset=[key])
        out["individuals_in_households"] = {
            "value": int(base["__hs"].sum()), "unit": "individuals (reported household members)",
            "rule": f"Sum of '{household_size}' over {'distinct households' if key else 'rows'}; {int(base['__hs'].isna().sum())} household(s) with missing size excluded.",
        }
        notes.append("Individuals are derived from reported household size; they are not individually registered people.")
    if unit == "assistance_event":
        notes.append("Rows are assistance events. The number of events is not the number of people assisted.")
    if unit == "unknown":
        notes.append("The unit of analysis has not been confirmed. Confirm what one row represents before reporting counts as people or households.")
    out["notes"] = notes
    return out


def possible_duplicate_beneficiaries(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Rows sharing all of the chosen identifying keys (exact match after trimming/case-folding)."""
    keys = [k for k in keys if k in df.columns]
    if not keys:
        return df.iloc[0:0]
    norm = df[keys].astype("string").apply(lambda s: s.str.strip().str.lower())
    dup = norm.duplicated(keep=False) & norm.notna().all(axis=1)
    return df.loc[dup].assign(__dup_group=norm[dup].astype(str).agg("|".join, axis=1)).sort_values("__dup_group")
