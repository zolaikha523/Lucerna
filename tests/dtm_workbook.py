"""SYNTHETIC multi-sheet displacement-tracking workbook with the same shape as the DTM practice workbook.

Sheets (row counts match the practice file): FMS_Survey 10,000 · FMC_Daily 224 · Sampling_Frame 443 ·
Inflow_Sources 112 · Codebook 55 · plus README, Indicator_Map and Province_Lookup reference sheets.

Every value is generated. Names of provinces and border crossings are real places used only as labels;
counts, people and coordinates are fictional test material and must never be cited as real figures.
Planted data-quality issues (for testing): impossible ages, duplicate survey IDs, invalid dates,
inconsistent spellings and missing values.

Run:  python -m tests.dtm_workbook   → tests/fixtures/SYNTHETIC_DTM_practice_workbook.xlsx
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "fixtures" / "SYNTHETIC_DTM_practice_workbook.xlsx"

FMPS = [  # code, name, province, approx lat, lon, country side, weight
    ("FMP-01", "Islam Qala", "Herat", 34.66, 61.07, "Iran", .30),
    ("FMP-02", "Milak", "Nimroz", 31.02, 61.86, "Iran", .18),
    ("FMP-03", "Torkham", "Nangarhar", 34.10, 71.09, "Pakistan", .24),
    ("FMP-04", "Spin Boldak", "Kandahar", 30.99, 66.39, "Pakistan", .16),
    ("FMP-05", "Dand-e-Patan", "Paktya", 33.73, 70.04, "Pakistan", .05),
    ("FMP-06", "Ghulam Khan", "Khost", 33.20, 70.25, "Pakistan", .04),
    ("FMP-07", "Kabul Airport", "Kabul", 34.56, 69.21, "Other", .03),
]
PROVINCES = ["Herat", "Nimroz", "Nangarhar", "Kandahar", "Kabul", "Balkh", "Paktya", "Khost", "Helmand", "Farah",
             "Badghis", "Ghor", "Kunduz", "Baghlan", "Faryab", "Laghman", "Kunar", "Ghazni", "Zabul", "Uruzgan"]
DISTRICTS = {p: [f"{p} District {i}" for i in range(1, 6)] for p in PROVINCES}
REGION = {"Herat": "West", "Nimroz": "South-West", "Farah": "West", "Badghis": "West", "Ghor": "West", "Nangarhar": "East",
          "Laghman": "East", "Kunar": "East", "Kandahar": "South", "Helmand": "South", "Zabul": "South", "Uruzgan": "South",
          "Kabul": "Central", "Ghazni": "South-East", "Paktya": "South-East", "Khost": "South-East", "Balkh": "North",
          "Kunduz": "North-East", "Baghlan": "North-East", "Faryab": "North"}


def fms_survey(rng: np.random.Generator) -> pd.DataFrame:
    n = 10_000
    fmp_idx = rng.choice(len(FMPS), n, p=[f[6] for f in FMPS])
    fmp = [FMPS[i] for i in fmp_idx]
    # seasonal volume: more interviews in the second half of the year
    month_w = np.array([5, 5, 6, 7, 8, 8, 9, 10, 11, 11, 10, 10], float)
    month = rng.choice(12, n, p=month_w / month_w.sum())
    day = rng.integers(1, 29, n)
    dates = pd.to_datetime({"year": 2024, "month": month + 1, "day": day})
    direction = rng.choice(["Inflow", "Outflow"], n, p=[.78, .22])
    country = np.array([f[5] if f[5] != "Other" else rng.choice(["Turkey", "UAE", "Saudi Arabia"]) for f in fmp], dtype=object)
    inflow = direction == "Inflow"
    ttype = np.where(inflow,
                     np.where(country == "Iran", rng.choice(["Deportee", "Returnee - undocumented", "Returnee - documented"], n, p=[.48, .32, .20]),
                              rng.choice(["Returnee - undocumented", "Returnee - documented", "Deportee", "Circular migrant"], n, p=[.40, .30, .15, .15])),
                     rng.choice(["Out-migrant", "Circular migrant", "Seasonal worker"], n, p=[.5, .3, .2]))
    sex = np.where(np.isin(ttype, ["Deportee"]), rng.choice(["Male", "Female"], n, p=[.93, .07]), rng.choice(["Male", "Female"], n, p=[.62, .38]))
    age = np.clip(rng.gamma(5.5, 5.2, n).round(), 14, 85).astype(int)
    hh_head = np.where(age > 22, rng.choice(["Yes", "No"], n, p=[.6, .4]), "No")
    with_family = np.where(ttype == "Deportee", rng.choice(["Yes", "No"], n, p=[.15, .85]), rng.choice(["Yes", "No"], n, p=[.55, .45]))
    group_size = np.where(with_family == "Yes", rng.integers(2, 11, n), 1)
    u5 = np.where(with_family == "Yes", rng.binomial(2, .45, n), 0)
    c517 = np.where(with_family == "Yes", rng.binomial(4, .4, n), 0)
    fem_grp = np.where(with_family == "Yes", rng.binomial(group_size, .45), (sex == "Female").astype(int))
    dest = np.array([f[2] if rng.random() < .45 else rng.choice(PROVINCES) for f in fmp], dtype=object)
    dest_d = np.array([rng.choice(DISTRICTS[p]) for p in dest], dtype=object)
    origin = np.where(rng.random(n) < .7, dest, rng.choice(PROVINCES, n))
    reason_return = np.where(ttype == "Deportee", "Deported / forced return",
                             rng.choice(["Loss of employment abroad", "Lack of legal documents", "Family reunification", "Fear of arrest",
                                         "High cost of living abroad", "Improved security at home", "Other"], n,
                                        p=[.24, .21, .17, .13, .12, .08, .05]))
    reason_return = np.where(inflow, reason_return, "Not applicable (outflow)")
    reason_leave = np.where(~inflow, rng.choice(["Economic / seeking work", "Insecurity", "Family reunification", "Education", "Health care"], n,
                                                p=[.62, .14, .12, .06, .06]), "Not applicable (inflow)")
    intended = np.where(inflow, rng.choice(["Permanent", "More than 6 months", "Less than 6 months", "Transit", "Don't know"], n,
                                           p=[.46, .18, .14, .07, .15]), rng.choice(["More than 6 months", "Less than 6 months", "Don't know"], n, p=[.5, .3, .2]))
    months_abroad = np.where(inflow, np.clip(rng.exponential(30, n).round(), 0, 240), np.nan)
    tazkira = rng.choice(["Yes", "No"], n, p=[.71, .29])
    passport = np.where(ttype == "Returnee - documented", "Yes", rng.choice(["Yes", "No"], n, p=[.2, .8]))
    vuln_opts = ["disability", "chronic_illness", "elderly", "unaccompanied_minor", "pregnant_lactating", "female_headed_household"]
    vuln = []
    for i in range(n):
        if rng.random() < .58:
            vuln.append("none")
        else:
            k = rng.integers(1, 3)
            vuln.append(" ".join(sorted(rng.choice(vuln_opts, k, replace=False, p=[.2, .25, .15, .08, .12, .2]))))
    need_opts = ["food", "cash", "shelter", "health", "transportation", "employment", "documentation", "nfi"]
    needs = [" ".join(sorted(rng.choice(need_opts, rng.integers(1, 4), replace=False, p=[.22, .2, .14, .1, .1, .12, .07, .05]))) for _ in range(n)]
    assisted = np.where(inflow & (ttype == "Deportee"), rng.choice(["Yes", "No"], n, p=[.42, .58]),
                        np.where(inflow, rng.choice(["Yes", "No"], n, p=[.18, .82]), "No"))
    debt = rng.choice(["Yes", "No"], n, p=[.47, .53])
    debt_amt = np.where(debt == "Yes", (rng.lognormal(10.3, .7, n) // 500 * 500), np.nan)
    cash = (rng.lognormal(8.2, 1.0, n) // 100 * 100)
    edu = rng.choice(["None", "Primary", "Secondary", "Higher"], n, p=[.42, .28, .23, .07])
    occ = rng.choice(["Daily labourer", "Construction", "Agriculture", "Unemployed", "Trader", "Driver", "Other"], n, p=[.34, .19, .14, .13, .08, .06, .06])
    transport = rng.choice(["Bus", "Private car", "On foot", "Taxi", "Truck"], n, p=[.45, .18, .12, .15, .10])
    shelter_dest = np.where(inflow, rng.choice(["Own house", "Rented house", "With relatives", "Informal settlement", "No shelter arranged"], n,
                                               p=[.3, .2, .3, .12, .08]), "Not applicable (outflow)")
    df = pd.DataFrame({
        "survey_id": [f"FMS-{i:06d}" for i in range(1, n + 1)],
        "survey_date": dates.dt.strftime("%Y-%m-%d"),
        "enumerator_code": rng.choice([f"EN-{i:02d}" for i in range(1, 41)], n),
        "fmp_code": [f[0] for f in fmp], "fmp_name": [f[1] for f in fmp], "fmp_province": [f[2] for f in fmp],
        "fmp_latitude": [round(f[3] + rng.normal(0, .01), 5) for f in fmp], "fmp_longitude": [round(f[4] + rng.normal(0, .01), 5) for f in fmp],
        "flow_direction": direction, "traveller_type": ttype, "country_of_departure": country,
        "province_of_origin": origin, "destination_province": dest, "destination_district": dest_d,
        "intended_duration_of_stay": intended,
        "respondent_sex": sex, "respondent_age": age, "marital_status": rng.choice(["Married", "Single", "Widowed", "Divorced"], n, p=[.58, .36, .05, .01]),
        "head_of_household": hh_head, "travelling_with_family": with_family, "group_size": group_size,
        "children_under5_in_group": u5, "children_5_17_in_group": c517, "females_in_group": fem_grp,
        "education_level": edu, "occupation_before_travel": occ, "months_abroad": months_abroad,
        "reason_for_return": reason_return, "reason_for_leaving": reason_leave,
        "has_tazkira": tazkira, "has_passport": passport,
        "vulnerabilities": vuln, "priority_needs": needs,
        "received_assistance_at_border": assisted, "has_debt": debt, "debt_amount_afn": debt_amt, "cash_on_hand_afn": cash,
        "transport_mode": transport, "shelter_at_destination": shelter_dest,
        "consent_given": "Yes", "respondent_phone": [f"07{rng.integers(10_000_000, 99_999_999)}" for _ in range(n)],
    })
    # ---- planted quality issues
    bad_age = rng.choice(n, 25, replace=False)
    df.loc[bad_age[:15], "respondent_age"] = 999
    df.loc[bad_age[15:], "respondent_age"] = -1
    dup = rng.choice(np.arange(100, n), 40, replace=False)
    df.loc[dup, "survey_id"] = df.loc[dup - 50, "survey_id"].values
    df.loc[rng.choice(n, 10, replace=False), "survey_date"] = "2024-13-45"
    sp = rng.choice(np.where(df["destination_province"] == "Herat")[0], 30, replace=False)
    df.loc[sp[:15], "destination_province"] = "herat "
    df.loc[sp[15:], "destination_province"] = "HERAT"
    for col, share in (("education_level", .04), ("months_abroad", .06), ("marital_status", .02), ("shelter_at_destination", .03)):
        df.loc[rng.choice(n, int(n * share), replace=False), col] = None
    return df


def fmc_daily(rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range("2024-12-01", periods=32, freq="D")
    rows = []
    for d in days:
        for code, name, prov, *_rest in FMPS:
            w = _rest[-1]
            inflow = int(rng.poisson(2600 * w * (1.25 if d.dayofweek in (5, 6) else 1)))
            out = int(rng.poisson(700 * w))
            dep = int(inflow * (.45 if _rest[2] == "Iran" else .12))
            undoc = int((inflow - dep) * .55)
            males = int(inflow * .68)
            children = int(inflow * .22)
            rows.append({"date": d.strftime("%Y-%m-%d"), "fmp_code": code, "fmp_name": name, "fmp_province": prov,
                         "inflow_individuals": inflow, "outflow_individuals": out, "deportees": dep,
                         "returnees_undocumented": undoc, "returnees_documented": inflow - dep - undoc,
                         "males": males, "females": inflow - males, "children_under18": children,
                         "unaccompanied_minors": int(rng.binomial(max(children, 1), .01)),
                         "fmp_operational": "Yes" if rng.random() > .03 else "No"})
    return pd.DataFrame(rows)


def sampling_frame(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i in range(443):
        p = PROVINCES[i % len(PROVINCES)]
        pop = int(rng.lognormal(8.0, .9))
        rows.append({"settlement_code": f"SET-{i + 1:04d}", "province": p, "district": rng.choice(DISTRICTS[p]),
                     "settlement_name": f"Settlement {i + 1:03d}", "region": REGION[p],
                     "latitude": round(30 + rng.random() * 7, 4), "longitude": round(61 + rng.random() * 10, 4),
                     "estimated_population": pop, "estimated_returnees": int(pop * rng.uniform(.02, .25)),
                     "estimated_idps": int(pop * rng.uniform(0, .18)), "selected_for_fms": rng.choice(["Yes", "No"], p=[.35, .65])})
    return pd.DataFrame(rows)


def inflow_sources(rng: np.random.Generator) -> pd.DataFrame:
    sources = [("Iran", s) for s in ("Tehran", "Khorasan Razavi", "Isfahan", "Kerman", "Fars", "Sistan-Baluchestan", "Qom")] + \
              [("Pakistan", s) for s in ("Khyber Pakhtunkhwa", "Balochistan", "Sindh", "Punjab", "Islamabad")] + \
              [("Turkey", "Istanbul"), ("Turkey", "Van")]
    rows = []
    for country, region in sources:
        for m in range(1, 9):
            rows.append({"month": f"2024-{m + 4:02d}", "source_country": country, "source_region": region,
                         "returnees_individuals": int(rng.lognormal(7.4 if country != "Turkey" else 5.5, .6)),
                         "share_deported_pct": round(float(rng.uniform(20, 70) if country == "Iran" else rng.uniform(5, 30)), 1)})
    return pd.DataFrame(rows)  # 14 sources × 8 months = 112


CODEBOOK_LABELS = {
    "survey_id": "Unique interview identifier", "survey_date": "Date of interview", "enumerator_code": "Enumerator code",
    "fmp_code": "Flow monitoring point code", "fmp_name": "Flow monitoring point name", "fmp_province": "Province of the flow monitoring point",
    "fmp_latitude": "FMP latitude (decimal degrees)", "fmp_longitude": "FMP longitude (decimal degrees)",
    "flow_direction": "Direction of travel", "traveller_type": "Type of traveller", "country_of_departure": "Country the traveller departed from",
    "province_of_origin": "Province of origin in Afghanistan", "destination_province": "Intended destination province",
    "destination_district": "Intended destination district", "intended_duration_of_stay": "Intended duration of stay",
    "respondent_sex": "Sex of respondent", "respondent_age": "Age of respondent (years)", "marital_status": "Marital status",
    "head_of_household": "Respondent is head of household", "travelling_with_family": "Travelling with family members",
    "group_size": "Number of people travelling together", "children_under5_in_group": "Children under 5 in the group",
    "children_5_17_in_group": "Children 5–17 in the group", "females_in_group": "Females in the group",
    "education_level": "Highest education level", "occupation_before_travel": "Occupation before travel",
    "months_abroad": "Months spent abroad", "reason_for_return": "Main reason for return", "reason_for_leaving": "Main reason for leaving",
    "has_tazkira": "Has a national ID (tazkira)", "has_passport": "Has a passport", "vulnerabilities": "Vulnerabilities in the group (multiple)",
    "priority_needs": "Priority needs (multiple)", "received_assistance_at_border": "Received assistance at the border",
    "has_debt": "Household has debt", "debt_amount_afn": "Debt amount (AFN)", "cash_on_hand_afn": "Cash on hand (AFN)",
    "transport_mode": "Mode of transport", "shelter_at_destination": "Shelter arrangement at destination",
    "consent_given": "Informed consent given", "respondent_phone": "Respondent phone (personal data — do not share)",
}
FMC_LABELS = {"date": "Date of count", "inflow_individuals": "Individuals entering", "outflow_individuals": "Individuals leaving",
              "deportees": "Deportees counted", "returnees_undocumented": "Undocumented returnees", "returnees_documented": "Documented returnees",
              "males": "Males counted", "females": "Females counted", "children_under18": "Children under 18 counted",
              "unaccompanied_minors": "Unaccompanied minors", "fmp_name": "FMP name (counts sheet)", "fmp_code": "FMP code (counts sheet)",
              "fmp_province": "FMP province (counts sheet)",
              "fmp_operational": "FMP open and counting on that day"}


def codebook(fms: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in fms.columns:
        s = fms[c].dropna()
        typ = "integer" if pd.api.types.is_integer_dtype(s) else ("decimal" if pd.api.types.is_float_dtype(s) else
                                                                 ("select_multiple" if c in ("vulnerabilities", "priority_needs") else
                                                                  ("date" if "date" in c else "select_one" if s.nunique() <= 12 else "text")))
        vals = "; ".join(map(str, sorted(s.astype(str).str.split(" ").explode().unique())[:10])) if typ.startswith("select") else ""
        rows.append({"sheet": "FMS_Survey", "variable": c, "label": CODEBOOK_LABELS[c], "type": typ, "allowed_values": vals,
                     "notes": "Personal data" if c == "respondent_phone" else ""})
    for c, lab in list(FMC_LABELS.items())[: 55 - len(rows)]:
        rows.append({"sheet": "FMC_Daily", "variable": c, "label": lab, "type": "date" if c == "date" else ("text" if "fmp" in c else "integer"),
                     "allowed_values": "", "notes": ""})
    return pd.DataFrame(rows)


def readme() -> pd.DataFrame:
    lines = [
        "SYNTHETIC DISPLACEMENT TRACKING PRACTICE WORKBOOK",
        "All records in this workbook are computer-generated for software testing. They are not real people or real counts.",
        "Shape mirrors a flow-monitoring practice workbook: survey microdata, daily counts, sampling frame, inflow sources and a codebook.",
        "FMS_Survey: one row per interviewed traveller at a flow monitoring point (FMP).",
        "FMC_Daily: one row per FMP per day with aggregated headcounts.",
        "Sampling_Frame: list of settlements with estimated populations used to plan data collection.",
        "Inflow_Sources: monthly returnee estimates by country and region of departure.",
        "Codebook: variable definitions for FMS_Survey and FMC_Daily.",
        "Indicator_Map: indicator definitions with numerators and denominators.",
        "Province_Lookup: province names and regions.",
        "Known planted issues (for testing): impossible ages, duplicate IDs, invalid dates, inconsistent province spelling, missing values.",
    ]
    return pd.DataFrame({"About this workbook": lines})


def indicator_map() -> pd.DataFrame:
    rows = [
        ("IND-01", "% of inflow travellers who are deportees", "traveller_type = Deportee", "flow_direction = Inflow", "FMS_Survey"),
        ("IND-02", "% of travellers with a national ID", "has_tazkira = Yes", "all valid responses", "FMS_Survey"),
        ("IND-03", "% of inflow travellers who received assistance at the border", "received_assistance_at_border = Yes", "flow_direction = Inflow", "FMS_Survey"),
        ("IND-04", "% of groups with at least one vulnerability", "vulnerabilities != none", "all valid responses", "FMS_Survey"),
        ("IND-05", "% of travellers with debt", "has_debt = Yes", "all valid responses", "FMS_Survey"),
        ("IND-06", "Daily inflow of individuals", "sum(inflow_individuals)", "per day", "FMC_Daily"),
        ("IND-07", "Share of deportees in daily inflow", "sum(deportees)", "sum(inflow_individuals)", "FMC_Daily"),
        ("IND-08", "% of returnees intending to stay permanently", "intended_duration_of_stay = Permanent", "flow_direction = Inflow", "FMS_Survey"),
    ]
    return pd.DataFrame(rows, columns=["indicator_code", "indicator", "numerator", "denominator", "source_sheet"])


def province_lookup() -> pd.DataFrame:
    return pd.DataFrame({"province_code": [f"AF{i + 1:02d}" for i in range(len(PROVINCES))], "province": PROVINCES,
                         "region": [REGION[p] for p in PROVINCES]})


def build(seed: int = 20261121) -> bytes:
    rng = np.random.default_rng(seed)
    fms = fms_survey(rng)
    sheets = {"README": readme(), "FMS_Survey": fms, "FMC_Daily": fmc_daily(rng), "Sampling_Frame": sampling_frame(rng),
              "Inflow_Sources": inflow_sources(rng), "Codebook": codebook(fms), "Indicator_Map": indicator_map(),
              "Province_Lookup": province_lookup()}
    assert len(sheets["Codebook"]) == 55 and len(sheets["FMC_Daily"]) == 224 and len(sheets["Inflow_Sources"]) == 112
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")
