"""Deterministic data understanding: types, roles, structure, potential indicators, sector.

Every inference carries a confidence and a reason. Low-confidence inferences are flagged for
user confirmation in the Data Understanding & Mapping screen; nothing uncertain is silently assumed.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "missing", ".", "#n/a"}
YES = {"yes", "y", "true", "1", "1.0", "بلی", "هو", "ho", "yes."}
NO = {"no", "n", "false", "0", "0.0", "نخیر", "نه", "na."}
SEX_VALUES = {"male", "female", "m", "f", "man", "woman", "boy", "girl", "men", "women", "other", "prefer not to say", "non-binary"}

ROLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("latitude", [r"\blat(itude)?\b", r"_lat$", r"gps.*lat", r"latitude"]),
    ("longitude", [r"\blon(g|gitude)?\b", r"_lon(g)?$", r"gps.*lon", r"longitude"]),
    ("geo_origin", [r"origin(?!al)", r"from_province", r"departure"]),
    ("geo_destination", [r"^dest(ination)?\b|^dest(ination)?_", r"destination_(province|district|country|location|city|village|region|area|admin|settlement)",
                         r"intended_(province|district|location|destination)", r"to_province"]),
    ("geo_admin1", [r"province", r"admin ?1", r"\bregion\b", r"\bstate\b", r"governorate", r"wilayat"]),
    ("geo_admin2", [r"district", r"admin ?2", r"county", r"woreda", r"\blga\b"]),
    ("geo_admin3", [r"village", r"admin ?3", r"settlement", r"(?<![a-z])camp(?![a-z])", r"(?<![a-z])block(?![a-z])", r"community", r"location", r"site", r"nahia",
                    r"(?<![a-z])ward(?![a-z])", r"^market(_name|_location)?$"]),
    ("date", [r"date", r"\btime\b", r"timestamp", r"submission", r"start$", r"end$", r"\bmonth\b", r"\bday\b", r"_at$"]),
    ("sex", [r"\bsex\b", r"gender", r"_sex$", r"sex_"]),
    ("age_group", [r"age.?group", r"age.?band", r"age.?cat", r"age_range"]),
    ("age", [r"\bage\b", r"_age$", r"^age", r"age_years"]),
    ("household_size", [r"hh.?size", r"household.?size", r"family.?size", r"members", r"hh_members", r"num.*people"]),
    ("weight", [r"\bweight\b", r"sampling_weight", r"wgt"]),
    ("identifier", [r"\bid\b", r"_id$", r"^id_", r"uuid", r"\bcode\b", r"_code$", r"index", r"serial", r"case.?no", r"registration", r"beneficiary.?no"]),
    ("personal_name", [r"\bname\b", r"first.?name", r"last.?name", r"father", r"respondent.?name", r"full.?name", r"surname"]),
    ("phone", [r"phone", r"mobile", r"contact", r"tel\b", r"msisdn"]),
    ("round", [r"\bround\b", r"\bwave\b", r"\bphase\b", r"baseline|endline|survey.?type", r"period"]),
]

SECTOR_KEYWORDS = {
    "PDM / Cash & Voucher Assistance": ["cash", "transfer", "amount", "received", "voucher", "mpca", "pdm", "distribution", "expenditure", "spent", "afn", "usd", "payment", "delay", "satisfaction", "assistance"],
    "WASH": ["water", "latrine", "sanitation", "hygiene", "handwash", "soap", "borehole", "well", "tap", "liters", "litres", "collection_time", "jerrycan", "toilet", "wash"],
    "Food Security": ["fcs", "rcsi", "hdds", "food", "meal", "cereal", "pulses", "dairy", "coping", "hunger", "hhs", "dietary", "consumption", "lcsi"],
    "Returnee / Flow Monitoring": ["returnee", "arrival", "origin", "destination", "border", "crossing", "movement", "deport", "return", "idp", "displac", "migrant", "flow"],
    "Health": ["health", "clinic", "vaccin", "illness", "disease", "treatment", "facility", "antenatal", "anc", "doctor"],
    "Nutrition": ["muac", "wasting", "stunting", "malnutrition", "breastfeed", "iycf", "sam", "mam", "weight_for"],
    "Protection": ["protection", "safety", "violence", "gbv", "child_labour", "documentation", "tazkira", "harassment", "risk", "referral"],
    "Education": ["school", "enrol", "attendance", "teacher", "student", "learning", "education", "grade"],
    "Shelter & NFI": ["shelter", "nfi", "tent", "blanket", "rent", "housing", "kit", "winterization"],
    "Livelihoods": ["income", "livelihood", "employment", "job", "business", "skills", "debt", "livestock"],
    "Baseline / Endline": ["baseline", "endline", "midline", "survey_round", "wave"],
    "Accountability (AAP / CFM)": ["complaint", "feedback", "hotline", "cfm", "informed", "aap", "consulted"],
    "Training Assessment": ["pre_test", "post_test", "pretest", "posttest", "training", "score", "participant"],
}


@dataclass
class ColumnProfile:
    name: str
    position: int
    inferred_type: str
    inferred_role: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    n: int = 0
    n_missing: int = 0
    pct_missing: float = 0.0
    n_unique: int = 0
    unique_ratio: float = 0.0
    sample_values: list[str] = field(default_factory=list)
    top_values: list[tuple[str, int]] = field(default_factory=list)
    numeric_summary: dict | None = None
    date_range: list[str] | None = None
    multiselect_options: list[str] | None = None
    multiselect_group: str | None = None
    pii_risk: str | None = None
    needs_review: bool = False


def _is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    return str(v).strip().lower() in MISSING_TOKENS


def normalise_missing(s: pd.Series) -> pd.Series:
    return s.map(lambda v: np.nan if _is_missing(v) else v)


def to_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    cleaned = s.astype("string").str.replace(r"[,\s]", "", regex=True).str.replace("%", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def to_datetime(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=False)
    return out


def _role_from_name(name: str) -> tuple[str | None, str | None]:
    low = name.lower().replace("-", "_")
    for role, patterns in ROLE_KEYWORDS:
        for p in patterns:
            if re.search(p, low):
                return role, p
    return None, None


def _multiselect_tokens(s: pd.Series) -> list[str] | None:
    """Detect KoBo/ODK-style select_multiple exports stored as space/;/|/, separated option codes.

    A column is treated as multiple-response only when multi-token values are *combinations of
    options that also appear on their own* (e.g. 'food rent' where 'food' and 'rent' are answers),
    so single-choice labels containing spaces ('Islam Qala', 'Help desk') are not misread."""
    vals = s.dropna().astype(str).str.strip()
    if len(vals) < 10:
        return None
    for sep in (";", "|", ",", " "):
        pattern = re.escape(sep) if sep != " " else r"\s+"
        multi = vals[vals.str.contains(re.escape(sep) if sep != " " else r"\s", regex=True)]
        if len(multi) < max(3, 0.1 * len(vals)):
            continue
        tokens = vals.str.split(pattern, regex=True).explode().str.strip()
        tokens = tokens[tokens != ""]
        distinct = set(tokens)
        if len(distinct) < 2 or len(distinct) > 40 or tokens.str.len().max() > 50:
            continue
        standalone = set(vals[~vals.isin(multi)])
        option_like = standalone | {t for t, c in tokens.value_counts().items() if c >= 3}
        combos = multi.str.split(pattern, regex=True)
        combo_share = combos.map(lambda parts: all(p in standalone for p in parts if p)).mean()
        # space-separated needs strong evidence; explicit separators need moderate evidence
        need = 0.6 if sep == " " else 0.3
        if combo_share >= need and multi.nunique() >= 3:
            return sorted(option_like & distinct, key=lambda t: -int((tokens == t).sum()))[:40]
    return None


COUNT_WORDS = re.compile(r"days|size|number|num_|_num|count|males|females|children|minutes|hours|score|times|meals|per_|amount|litre|liter|income|members|_n$|qty|quantity|age|km|distance")


def profile_column(df: pd.DataFrame, name: str, position: int) -> ColumnProfile:
    raw = normalise_missing(df[name])
    n = len(raw)
    nonnull = raw.dropna()
    n_missing = int(raw.isna().sum())
    n_unique = int(nonnull.astype(str).nunique())
    p = ColumnProfile(name=name, position=position, inferred_type="text", inferred_role="category", confidence=0.5,
                      n=n, n_missing=n_missing, pct_missing=round(100 * n_missing / n, 2) if n else 0.0,
                      n_unique=n_unique, unique_ratio=round(n_unique / max(1, len(nonnull)), 4))
    p.sample_values = [str(x)[:60] for x in nonnull.astype(str).unique()[:6]]
    if len(nonnull) == 0:
        p.inferred_type, p.inferred_role, p.confidence = "empty", "empty", 1.0
        p.reasons.append("All values are missing.")
        p.needs_review = True
        return p

    name_role, pattern = _role_from_name(name)
    sval = nonnull.astype(str).str.strip()
    low = sval.str.lower()
    num = to_numeric(nonnull)
    num_ratio = float(num.notna().mean())

    # --- Booleans / yes-no
    yn = low.isin(YES | NO).mean()
    if n_unique <= 3 and yn >= 0.95:
        p.inferred_type, p.inferred_role, p.confidence = "boolean", "binary", 0.9
        p.reasons.append("Values are yes/no (or 1/0) style.")
    # --- Numeric
    elif num_ratio >= 0.95:
        p.inferred_type = "integer" if (num.dropna() % 1 == 0).all() else "numeric"
        p.inferred_role, p.confidence = "measure", 0.75
        nn = num.dropna()
        p.numeric_summary = {"min": float(nn.min()), "max": float(nn.max()), "mean": float(nn.mean()), "median": float(nn.median())}
        p.reasons.append(f"{num_ratio:.0%} of non-missing values are numeric.")
        if n_unique <= 5 and p.inferred_type == "integer" and not name_role and not COUNT_WORDS.search(name.lower()):
            p.inferred_role, p.confidence = "category", 0.55
            p.reasons.append("Few distinct integer values — may be a coded category (e.g., Likert scale); please confirm.")
            p.needs_review = True
    else:
        dt = to_datetime(nonnull.astype(str))
        dt_ratio = float(dt.notna().mean())
        looks_date = sval.str.contains(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{4}-\d{2}", regex=True).mean() > 0.8
        if dt_ratio >= 0.9 and (looks_date or name_role == "date"):
            p.inferred_type, p.inferred_role, p.confidence = "date", "date", 0.85
            d = dt.dropna()
            p.date_range = [str(d.min().date()), str(d.max().date())]
            p.reasons.append(f"{dt_ratio:.0%} of values parse as dates.")
        else:
            opts = _multiselect_tokens(nonnull)
            if opts:
                p.inferred_type, p.inferred_role, p.confidence = "multiselect", "multiselect", 0.6
                p.multiselect_options = opts
                p.reasons.append(f"Values look like multiple selections of {len(opts)} options.")
                p.needs_review = True
            elif sval.str.len().mean() > 40 and p.unique_ratio > 0.5:
                p.inferred_type, p.inferred_role, p.confidence = "text", "free_text", 0.8
                p.reasons.append("Long, mostly unique text — open-ended responses.")
            else:
                p.inferred_type, p.inferred_role, p.confidence = "categorical", "category", 0.7
                p.reasons.append(f"{n_unique} distinct text values.")

    # --- Name-based roles refine (but do not override incompatible types)
    if name_role:
        compatible = {
            "latitude": p.inferred_type in ("numeric", "integer"), "longitude": p.inferred_type in ("numeric", "integer"),
            "age": p.inferred_type in ("numeric", "integer"), "household_size": p.inferred_type in ("numeric", "integer"),
            "weight": p.inferred_type in ("numeric",), "date": p.inferred_type == "date",
            "sex": p.inferred_type in ("categorical", "boolean"), "identifier": True, "personal_name": p.inferred_type in ("categorical", "text"),
            "phone": True,
        }.get(name_role, p.inferred_type in ("categorical", "text", "boolean", "integer"))
        if compatible:
            p.inferred_role = name_role
            p.confidence = min(0.95, p.confidence + 0.15)
            p.reasons.append(f"Column name matches the '{name_role}' pattern.")
        else:
            p.reasons.append(f"Name suggests '{name_role}', but the values are {p.inferred_type}; please confirm.")
            p.needs_review = True

    # --- Value-based checks
    if p.inferred_role == "category" and low.isin(SEX_VALUES).mean() > 0.9 and n_unique <= 5:
        p.inferred_role, p.confidence = "sex", 0.85
        p.reasons.append("Values are sex/gender categories.")
    if p.inferred_role in ("latitude", "longitude") and p.numeric_summary:
        lim = 90 if p.inferred_role == "latitude" else 180
        if abs(p.numeric_summary["min"]) > lim or abs(p.numeric_summary["max"]) > lim:
            p.reasons.append("Values fall outside valid coordinate range.")
            p.needs_review = True
    if p.inferred_role not in ("identifier",) and p.unique_ratio >= 0.98 and len(nonnull) >= 20 and p.inferred_type in ("categorical", "integer", "text") \
            and sval.str.len().max() <= 40 and p.inferred_role not in ("free_text", "personal_name", "phone", "date"):
        p.inferred_role, p.confidence = "identifier", 0.6
        p.reasons.append("Almost every value is unique — possibly a record identifier.")
        p.needs_review = True
    if p.inferred_role == "identifier":
        p.inferred_type = "identifier"

    # --- PII risk
    if p.inferred_role in ("personal_name", "phone"):
        p.pii_risk = "high"
    elif p.inferred_role in ("latitude", "longitude"):
        p.pii_risk = "medium"
    elif p.inferred_type in ("categorical", "text") and sval.str.contains(r"(?:\+?\d[\d\s-]{8,}\d)|(?:[\w.]+@[\w.]+\.\w+)", regex=True).mean() > 0.3:
        p.pii_risk = "high"
        p.reasons.append("Values look like phone numbers or email addresses.")

    if p.inferred_type in ("categorical", "boolean", "multiselect") or p.inferred_role in ("sex", "geo_admin1", "geo_admin2", "geo_admin3", "age_group", "round"):
        vc = sval.value_counts().head(15)
        p.top_values = [(str(k), int(v)) for k, v in vc.items()]
    if p.confidence < 0.65:
        p.needs_review = True
    return p


def kobo_multiselect_groups(columns: list[str]) -> dict[str, list[str]]:
    """Detect ODK/KoBo 'question/option' or 'question.option' 0/1 dummy columns."""
    groups: dict[str, list[str]] = {}
    for c in columns:
        m = re.match(r"^(.+?)[/.](\w[\w ]*)$", c)
        if m:
            groups.setdefault(m.group(1), []).append(c)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def guess_unit_of_analysis(profiles: list[ColumnProfile], columns: list[str]) -> tuple[str, float, str]:
    names = " ".join(c.lower() for c in columns)
    ids = [p for p in profiles if p.inferred_role == "identifier"]
    if re.search(r"transaction|distribution_id|payment|disburse|voucher_no|event", names):
        return "assistance_event", 0.6, "Columns mention transactions/distributions/payments."
    if re.search(r"respondent_(sex|age|gender)|interview(ee)?_(sex|age)", names):
        return "respondent", 0.55, "Each row has the respondent's own characteristics (one row per interview)."
    if re.search(r"arrival|crossing|movement|border_point|flow", names):
        return "movement", 0.55, "Columns describe arrivals/crossings/movements."
    if re.search(r"visit|monitoring_visit|site_visit", names):
        return "visit", 0.45, "Columns describe visits."
    if re.search(r"case_id|case_no|referral", names):
        return "case", 0.5, "Columns describe cases/referrals."
    if re.search(r"\bhh|household", names):
        hh_ids = [p for p in ids if re.search(r"hh|household", p.name.lower())]
        if hh_ids and hh_ids[0].unique_ratio >= 0.98:
            return "household", 0.75, f"'{hh_ids[0].name}' is unique per row."
        if hh_ids:
            return "individual", 0.5, f"'{hh_ids[0].name}' repeats — rows may be household members."
        return "household", 0.5, "Columns refer to households; please confirm one row = one household."
    if re.search(r"respondent|interview|survey", names):
        return "respondent", 0.45, "Columns refer to respondents/interviews."
    return "unknown", 0.0, "Could not determine what one row represents; please choose."


def guess_sector(columns: list[str], profiles: list[ColumnProfile]) -> list[tuple[str, float]]:
    text = " ".join(c.lower() for c in columns) + " " + " ".join(
        " ".join(v.lower() for v, _ in p.top_values[:5]) for p in profiles)
    scores = {}
    for sector, kws in SECTOR_KEYWORDS.items():
        hits = sum(1 for k in kws if k in text)
        if hits:
            scores[sector] = hits / len(kws)
    total = sum(scores.values()) or 1
    return sorted(((k, round(v / total, 3)) for k, v in scores.items()), key=lambda x: -x[1])


def profile_dataframe(df: pd.DataFrame) -> dict:
    profiles = [profile_column(df, c, i) for i, c in enumerate(df.columns)]
    groups = kobo_multiselect_groups(list(df.columns))
    for g, cols in groups.items():
        for p in profiles:
            if p.name in cols and p.inferred_type in ("boolean", "integer"):
                p.multiselect_group = g
                p.reasons.append(f"Part of multiple-response question '{g}'.")
    unit, unit_conf, unit_reason = guess_unit_of_analysis(profiles, list(df.columns))
    sectors = guess_sector(list(df.columns), profiles)
    return {
        "n_rows": int(len(df)), "n_columns": int(df.shape[1]),
        "columns": [asdict(p) for p in profiles],
        "multiselect_groups": groups,
        "unit_of_analysis": {"value": unit, "confidence": unit_conf, "reason": unit_reason},
        "sector_candidates": sectors,
        "needs_review": [p.name for p in profiles if p.needs_review],
        "pii_columns": [p.name for p in profiles if p.pii_risk == "high"],
    }
