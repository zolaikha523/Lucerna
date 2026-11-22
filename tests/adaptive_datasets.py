"""Structurally different SYNTHETIC datasets used to prove the dashboard engine adapts (not IOM-specific).

Every dataset here is invented. Column names, sheet layouts, sizes and domains deliberately differ from each other
and from the DTM-style practice workbook, so a test that passes on all of them cannot rely on hard-coded names.

    python -m tests.adaptive_datasets      # writes tests/fixtures/adaptive/*.xlsx|csv
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "fixtures" / "adaptive"


def _xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------- 1. WASH: multi-sheet, camp/block geography, codebook named "Variables"

def wash_camp_workbook(rng: np.random.Generator) -> bytes:
    n = 1800
    camps = rng.choice(["Camp Alpha", "Camp Beta", "Camp Gamma", "Camp Delta"], n, p=[.35, .3, .2, .15])
    block = [f"{c.split()[1][0]}-{rng.integers(1, 9)}" for c in camps]
    src = rng.choice(["Piped tap", "Protected borehole", "Water trucking", "Unprotected well", "Surface water"], n, p=[.3, .25, .2, .15, .1])
    unsafe = np.isin(src, ["Unprotected well", "Surface water"])
    df = pd.DataFrame({
        "hh_uid": [f"W{i:05d}" for i in range(n)],
        "visit_dt": pd.Timestamp("2026-02-01") + pd.to_timedelta(rng.integers(0, 120, n), unit="D"),
        "camp_name": camps, "block_code": block,
        "hh_members": rng.integers(1, 12, n),
        "head_gender": rng.choice(["Female", "Male"], n, p=[.42, .58]),
        "main_water_source": src,
        "litres_per_person_day": np.round(np.clip(rng.normal(14, 6, n) - unsafe * 4, 1, 45), 1),
        "minutes_to_water_point": np.clip(rng.gamma(2, 9, n) + unsafe * 15, 1, 180).round(),
        "treats_water": rng.choice(["yes", "no"], n, p=[.4, .6]),
        "latrine_type": rng.choice(["Shared pit latrine", "Private pit latrine", "Flush latrine", "Open defecation"], n, p=[.45, .25, .15, .15]),
        "latrine_shared_hh": rng.integers(1, 25, n),
        "handwash_station_soap": rng.choice(["yes", "no"], n, p=[.55, .45]),
        "diarrhoea_child_u5_2wks": np.where(rng.random(n) < .12 + unsafe * .15, "yes", "no"),
        "hygiene_kit_received": rng.choice(["yes", "no", "don't know"], n, p=[.5, .45, .05]),
        "satisfaction_water_service": rng.choice(["Very dissatisfied", "Dissatisfied", "Neutral", "Satisfied", "Very satisfied"], n, p=[.1, .2, .25, .3, .15]),
    })
    df.loc[rng.choice(n, 90, replace=False), "litres_per_person_day"] = np.nan
    variables = pd.DataFrame({"Variable": df.columns, "Description": [
        "Household identifier", "Date of visit", "Camp", "Block within camp", "Number of household members", "Gender of household head",
        "Main source of drinking water", "Litres of water per person per day", "Minutes to reach the water point", "Household treats drinking water",
        "Type of latrine used", "Households sharing the latrine", "Handwashing station with soap", "Child under five with diarrhoea in last two weeks",
        "Received hygiene kit", "Satisfaction with water service"]})
    notes = pd.DataFrame({"Notes": ["SYNTHETIC WASH camp survey — invented data for testing.", "Sampling: systematic by block.",
                                    "Contact: none (synthetic)."]})
    return _xlsx({"Notes": notes, "HH_Data": df, "Variables": variables})


# ---------------------------------------------------------------- 2. Food security: CSV, no dates, inconsistent categories

def food_security_csv(rng: np.random.Generator) -> bytes:
    n = 1200
    reg = rng.choice(["North", "South", "East", "West", "Central"], n)
    messy = {"North": ["North", "north", "NORTH "], "South": ["South", "south"], "East": ["East"], "West": ["West", "west"], "Central": ["Central"]}
    region = [rng.choice(messy[r]) for r in reg]
    sex = rng.choice(["Female", "F", "female", "Male", "M", "male"], n, p=[.3, .1, .05, .35, .12, .08])
    fcs = np.clip(rng.normal(42, 15, n), 0, 112).round(1)
    df = pd.DataFrame({
        "resp_id": np.arange(1, n + 1), "region": region, "district": [f"{r[:2].upper()}-{rng.integers(1, 5)}" for r in region],
        "hoh_sex": sex, "household_size": rng.integers(1, 14, n),
        "fcs_score": fcs, "fcs_group": pd.cut(fcs, [-1, 21, 35, 200], labels=["Poor", "Borderline", "Acceptable"]).astype(str),
        "rcsi_score": rng.integers(0, 57, n), "hhs_category": rng.choice(["None/slight", "Moderate", "Severe"], n, p=[.55, .35, .1]),
        "lcs_strategy": rng.choice(["None", "Stress", "Crisis", "Emergency"], n, p=[.3, .35, .25, .1]),
        "food_expenditure_share": np.clip(rng.normal(0.62, 0.15, n), 0.1, 0.98).round(2),
        "main_income_source": rng.choice(["Casual labour", "Agriculture", "Petty trade", "Remittances", "Assistance", "None"], n),
        "received_food_assistance": rng.choice(["Yes", "No"], n, p=[.35, .65]),
    })
    df.loc[rng.choice(n, 60, replace=False), "rcsi_score"] = np.nan
    return _csv(df)


# ---------------------------------------------------------------- 3. MPCA PDM: rounds, transfer values, multi-select spending, Likert

def mpca_pdm_workbook(rng: np.random.Generator) -> bytes:
    n = 900
    rnd = rng.choice(["PDM round 1", "PDM round 2"], n)
    spend_items = ["food", "rent", "health", "debt", "education", "water"]
    spend = [" ".join(sorted(rng.choice(spend_items, rng.integers(1, 4), replace=False))) for _ in range(n)]
    df = pd.DataFrame({
        "beneficiary_code": [f"B-{i:04d}" for i in range(n)], "pdm_round": rnd,
        "interview_date": np.where(rnd == "PDM round 1", "2026-03-", "2026-07-") + pd.Series(rng.integers(10, 28, n)).astype(str),
        "governorate": rng.choice(["Gov A", "Gov B", "Gov C"], n), "recipient_gender": rng.choice(["woman", "man"], n, p=[.6, .4]),
        "amount_received_usd": rng.choice([120, 150, 180], n), "received_full_amount": rng.choice(["yes", "no"], n, p=[.92, .08]),
        "spent_on": spend, "travel_cost_to_collect": np.clip(rng.normal(3, 2, n), 0, 15).round(2),
        "felt_safe_collecting": rng.choice(["yes", "no"], n, p=[.88, .12]),
        "knows_how_to_complain": rng.choice(["yes", "no"], n, p=[.55, .45]),
        "cash_met_needs": rng.choice(["Not at all", "Partially", "Mostly", "Completely"], n, p=[.1, .45, .35, .1]),
        "preferred_modality": rng.choice(["Cash", "Voucher", "In-kind", "Mixed"], n, p=[.7, .1, .1, .1]),
    })
    for it in spend_items:
        df[f"spent_on/{it}"] = df["spent_on"].str.contains(it).astype(int)
    readme = pd.DataFrame({"About": ["SYNTHETIC multipurpose cash post-distribution monitoring.", "Two rounds; invented values."]})
    return _xlsx({"PDM": df, "ReadMe": readme})


# ---------------------------------------------------------------- 4. General research survey: Likert battery, no dates, no geography

def research_survey_csv(rng: np.random.Generator) -> bytes:
    n = 420
    scale = ["Strongly disagree", "Disagree", "Neither agree nor disagree", "Agree", "Strongly agree"]
    df = pd.DataFrame({"participant": np.arange(n), "age_years": rng.integers(18, 70, n),
                       "gender": rng.choice(["Woman", "Man", "Non-binary", "Prefer not to say"], n, p=[.48, .46, .03, .03]),
                       "study_programme": rng.choice(["Engineering", "Humanities", "Medicine", "Business", "Sciences"], n),
                       "years_enrolled": rng.integers(1, 6, n)})
    for i, stem in enumerate(["The course content was relevant", "Teaching staff were approachable", "Workload was manageable",
                              "Feedback on assignments was useful", "I would recommend this programme"], 1):
        df[f"q{i}_{stem.lower().replace(' ', '_')[:24]}"] = rng.choice(scale, n, p=[.08, .15, .22, .35, .2])
    df["weekly_study_hours"] = np.clip(rng.normal(18, 7, n), 0, 60).round()
    df["open_comment"] = rng.choice(["", "More practical sessions please.", "Library hours are too short.", "Great lecturers.", ""], n)
    return _csv(df)


# ---------------------------------------------------------------- 5. Market price monitoring: long format, week dates, markets x commodities

def market_prices_workbook(rng: np.random.Generator) -> bytes:
    rows = []
    commodities = {"Wheat flour (kg)": 0.6, "Rice (kg)": 1.1, "Vegetable oil (L)": 1.9, "Sugar (kg)": 0.9, "Lentils (kg)": 1.3}
    for wk in pd.date_range("2025-09-01", periods=30, freq="W-MON"):
        for m in ["Central market", "North bazaar", "Border market", "River market"]:
            for c, base in commodities.items():
                rows.append({"week_start": wk, "market": m, "commodity": c, "price_local": round(base * 100 * (1 + rng.normal(0, .05)) *
                             (1 + .01 * (wk - pd.Timestamp("2025-09-01")).days / 7), 1), "traders_interviewed": int(rng.integers(2, 7)),
                             "stock_available": rng.choice(["yes", "no"], p=[.9, .1])})
    prices = pd.DataFrame(rows)
    lookup = pd.DataFrame({"market": ["Central market", "North bazaar", "Border market", "River market"], "zone": ["Urban", "Urban", "Border", "Rural"]})
    return _xlsx({"Prices": prices, "Market_List": lookup})


# ---------------------------------------------------------------- 6. Unfamiliar domain: factory maintenance log (no humanitarian vocabulary)

def maintenance_log_csv(rng: np.random.Generator) -> bytes:
    n = 650
    line = rng.choice(["Line 1", "Line 2", "Line 3"], n)
    df = pd.DataFrame({"ticket": [f"T{i}" for i in range(n)],
                       "opened_at": pd.Timestamp("2026-01-05") + pd.to_timedelta(rng.integers(0, 24 * 200, n), unit="h"),
                       "production_line": line, "machine": [f"{l[-1]}-M{rng.integers(1, 6)}" for l in line],
                       "shift": rng.choice(["Morning", "Evening", "Night"], n), "fault_category": rng.choice(["Electrical", "Hydraulic", "Sensor", "Software", "Wear"], n),
                       "downtime_minutes": np.clip(rng.lognormal(3.6, .8, n), 3, 900).round(),
                       "parts_cost_eur": np.clip(rng.lognormal(4, 1.1, n), 0, 5000).round(2),
                       "resolved_first_visit": rng.choice(["Y", "N"], n, p=[.7, .3])})
    return _csv(df)


# ---------------------------------------------------------------- 7. Too small to analyse

def tiny_csv(rng: np.random.Generator) -> bytes:
    return _csv(pd.DataFrame({"site": ["A", "B", "C", "D", "E", "F"], "score": [3, 5, 2, 4, 4, 1], "visited": ["yes", "no", "yes", "yes", "no", "yes"]}))


# ---------------------------------------------------------------- 8. Invalid / messy values

def invalid_values_csv(rng: np.random.Generator) -> bytes:
    n = 300
    age = rng.integers(15, 80, n).astype(object)
    age[rng.choice(n, 25, replace=False)] = "unknown"
    age[rng.choice(n, 10, replace=False)] = -5
    dates = (pd.Timestamp("2026-04-01") + pd.to_timedelta(rng.integers(0, 60, n), unit="D")).strftime("%Y-%m-%d").to_numpy(dtype=object)
    dates[rng.choice(n, 15, replace=False)] = "31/02/2026"
    df = pd.DataFrame({"id": list(range(n - 20)) + list(range(20)), "age": age, "survey_date": dates,
                       "village": rng.choice(["Ash", "Birch", "Cedar", "ash", " Birch"], n), "income": rng.normal(200, 80, n).round(),
                       "empty_column": [None] * n, "constant_col": ["same"] * n, "has_bednet": rng.choice(["yes", "no", "", "N/A"], n)})
    return _csv(df)


ALL = {
    "SYNTHETIC_WASH_camps.xlsx": wash_camp_workbook, "SYNTHETIC_food_security_regions.csv": food_security_csv,
    "SYNTHETIC_MPCA_PDM_two_rounds.xlsx": mpca_pdm_workbook, "SYNTHETIC_student_experience_survey.csv": research_survey_csv,
    "SYNTHETIC_market_prices.xlsx": market_prices_workbook, "SYNTHETIC_factory_maintenance_log.csv": maintenance_log_csv,
    "SYNTHETIC_tiny.csv": tiny_csv, "SYNTHETIC_invalid_values.csv": invalid_values_csv,
}


def build_all(seed: int = 7) -> dict[str, bytes]:
    return {name: fn(np.random.default_rng(seed + i)) for i, (name, fn) in enumerate(ALL.items())}


def write_all() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in build_all().items():
        (OUT / name).write_bytes(data)
        paths.append(OUT / name)
    return paths


if __name__ == "__main__":
    for p in write_all():
        print(p.relative_to(OUT.parents[1]), p.stat().st_size)
