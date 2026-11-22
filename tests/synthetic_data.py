"""Generates clearly-labelled SYNTHETIC test datasets and transcripts (never production data).

Run:  python tests/synthetic_data.py      → writes files into tests/fixtures/
Each quantitative dataset has a different structure so the adaptive engine can be tested.
All names, places and quotes are fictional test material.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "fixtures"
PROVINCES = {"Kabul": ["Kabul City", "Paghman", "Bagrami"], "Herat": ["Herat City", "Injil", "Guzara"],
             "Nangarhar": ["Jalalabad", "Behsud", "Surkh Rod"], "Balkh": ["Mazar-i-Sharif", "Dehdadi"]}


def pdm_cash(rng: np.random.Generator) -> pd.DataFrame:
    n = 420
    prov = rng.choice(list(PROVINCES), n, p=[.35, .25, .25, .15])
    dist = [rng.choice(PROVINCES[p]) for p in prov]
    sex = rng.choice(["Female", "Male"], n, p=[.55, .45])
    received = rng.choice(["Yes", "No"], n, p=[.92, .08])
    amount = np.where(received == "Yes", rng.choice([8000, 10000, 12000], n), np.nan)
    delay = np.where(received == "Yes", rng.poisson(4, n), np.nan)
    sat_levels = ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very dissatisfied"]
    sat = rng.choice(sat_levels, n, p=[.25, .4, .15, .12, .08])
    exp_opts = ["food", "rent", "health", "debt", "education", "fuel"]
    expend = [" ".join(sorted(rng.choice(exp_opts, rng.integers(1, 4), replace=False))) for _ in range(n)]
    dates = pd.to_datetime("2026-03-01") + pd.to_timedelta(rng.integers(0, 75, n), unit="D")
    df = pd.DataFrame({
        "hh_id": [f"HH-{10000 + i}" for i in range(n)], "submission_date": dates.strftime("%Y-%m-%d"),
        "consent": rng.choice(["Yes", "No"], n, p=[.985, .015]), "province": prov, "district": dist,
        "respondent_sex": sex, "respondent_age": rng.integers(18, 75, n), "hh_size": rng.integers(2, 13, n),
        "head_of_household_sex": rng.choice(["Female", "Male"], n, p=[.3, .7]),
        "disability_in_hh": rng.choice(["Yes", "No"], n, p=[.18, .82]),
        "received_assistance": received, "transfer_modality": rng.choice(["Hawala", "Mobile money", "Cash in hand"], n, p=[.6, .15, .25]),
        "amount_received_afn": amount, "days_delay": delay,
        "felt_safe_receiving": rng.choice(["Yes", "No"], n, p=[.88, .12]),
        "main_expenditure": expend, "satisfaction": sat,
        "aware_of_cfm": rng.choice(["Yes", "No"], n, p=[.62, .38]),
        "complaint_made": rng.choice(["Yes", "No"], n, p=[.09, .91]),
    })
    # Deliberate quality issues for testing:
    df.loc[5, "province"] = "kabul "
    df.loc[6, "province"] = "KABUL"
    df.loc[11, "respondent_age"] = 999
    df.loc[12, "amount_received_afn"] = -99
    df = pd.concat([df, df.iloc[[20, 21]]], ignore_index=True)  # two exact duplicates
    return df


def wash(rng: np.random.Generator) -> pd.DataFrame:
    n = 360
    sites = {"Camp A": (34.52, 69.17), "Camp B": (34.35, 62.20), "Settlement C": (34.43, 70.45), "Settlement D": (36.70, 67.11)}
    site = rng.choice(list(sites), n)
    lat = [sites[s][0] + rng.normal(0, .01) for s in site]
    lon = [sites[s][1] + rng.normal(0, .01) for s in site]
    season = rng.choice(["Dry", "Wet"], n)
    minutes = np.clip(rng.gamma(2.2, 12, n) + np.where(season == "Dry", 10, 0), 1, 180).round()
    return pd.DataFrame({
        "survey_date": (pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 540, n), unit="D")).strftime("%d/%m/%Y"),
        "site_name": site, "admin1": [{"Camp A": "Kabul", "Camp B": "Herat", "Settlement C": "Nangarhar", "Settlement D": "Balkh"}[s] for s in site],
        "gps_latitude": np.round(lat, 5), "gps_longitude": np.round(lon, 5), "season": season,
        "main_water_source": rng.choice(["Piped", "Protected well", "Unprotected well", "Surface water", "Water trucking"], n, p=[.2, .35, .2, .1, .15]),
        "water_collection_minutes": minutes, "litres_per_person_day": np.round(rng.normal(14, 5, n).clip(2, 40), 1),
        "water_treated": rng.choice(["yes", "no"], n, p=[.4, .6]), "latrine_type": rng.choice(["Improved", "Unimproved", "Open defecation"], n, p=[.55, .35, .1]),
        "handwashing_soap_available": rng.choice(["yes", "no"], n, p=[.58, .42]), "water_point_functional": rng.choice(["yes", "no"], n, p=[.8, .2]),
    })


def returnee_flow(rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range("2025-01-01", "2026-06-30", freq="D")
    rows = []
    rid = 1
    for d in days:
        seasonal = 1 + .5 * np.sin(2 * np.pi * (d.dayofyear / 365))
        for _ in range(rng.poisson(3 * seasonal)):
            g = int(rng.integers(1, 9))
            male = int(rng.integers(0, g + 1))
            rows.append({"record_id": f"FM-{rid:06d}", "crossing_date": d.strftime("%Y-%m-%d"),
                         "border_point": rng.choice(["Islam Qala", "Torkham", "Spin Boldak"], p=[.45, .35, .2]),
                         "origin_country": rng.choice(["Iran", "Pakistan"], p=[.55, .45]),
                         "destination_province": rng.choice(list(PROVINCES), p=[.3, .3, .25, .15]),
                         "returnee_type": rng.choice(["Documented", "Undocumented", "Deportee"], p=[.3, .45, .25]),
                         "group_size": g, "males": male, "females": g - male, "children_under_5": int(rng.integers(0, max(1, g // 2) + 1)),
                         "vulnerabilities": ";".join(sorted(set(rng.choice(["none", "disability", "chronic illness", "unaccompanied child", "female-headed"], int(rng.integers(1, 3)))))),
                         "priority_need": rng.choice(["Food", "Shelter", "Cash", "Health", "Transport"])})
            rid += 1
    return pd.DataFrame(rows)


def food_security(rng: np.random.Generator) -> pd.DataFrame:
    n = 300
    prov = rng.choice(list(PROVINCES), n)
    d = {"household_id": [f"FS-{i:05d}" for i in range(n)], "interview_date": (pd.to_datetime("2026-02-01") + pd.to_timedelta(rng.integers(0, 40, n), unit="D")).strftime("%Y-%m-%d"),
         "province": prov, "hh_head_sex": rng.choice(["Female", "Male"], n, p=[.25, .75]),
         "main_livelihood": rng.choice(["Daily labour", "Agriculture", "Small business", "Remittances", "Assistance"], n), "household_size": rng.integers(2, 14, n)}
    for g, lam in {"cereals": 6.5, "pulses": 2.5, "vegetables": 3, "fruit": 1, "meat_fish": .8, "milk": 1.5, "sugar": 5, "oil": 6}.items():
        d[f"fcs_{g}_days"] = np.clip(rng.poisson(lam, n), 0, 7)
    for s, lam in {"less_preferred": 3, "borrow_food": 1.5, "limit_portion": 2.5, "restrict_adults": 1, "reduce_meals": 2}.items():
        d[f"rcsi_{s}_days"] = np.clip(rng.poisson(lam, n), 0, 7)
    return pd.DataFrame(d)


def baseline_endline(rng: np.random.Generator, endline: bool) -> pd.DataFrame:
    n = 250
    shift = 1 if endline else 0
    return pd.DataFrame({
        "respondent_id": [f"{'E' if endline else 'B'}-{i:04d}" for i in range(n)],
        "survey_round": "Endline" if endline else "Baseline", "survey_date": ("2026-06-15" if endline else "2025-06-15"),
        "district": rng.choice(["Jalalabad", "Behsud", "Surkh Rod"], n), "sex": rng.choice(["Female", "Male"], n),
        "age": rng.integers(18, 65, n), "monthly_income_afn": np.round(rng.lognormal(8.6 + .15 * shift, .5, n), -1),
        "has_savings": rng.choice(["Yes", "No"], n, p=[.22 + .14 * shift, .78 - .14 * shift]),
        "knowledge_score": np.clip(rng.normal(52 + 9 * shift, 14, n), 0, 100).round(),
        "meals_per_day": rng.choice([1, 2, 3], n, p=[.2 - .05 * shift, .5, .3 + .05 * shift]),
    })


TRANSCRIPTS = {
    "SYNTHETIC_FGD_women_Herat.txt": """Title: FGD with women recipients (SYNTHETIC TEST TRANSCRIPT)
Type: FGD
Location: Herat City
Date: 2026-04-12
Group: Female cash recipients

Moderator: Thank you for coming. Can you tell us how you received the cash assistance?

P1 (female, 34): We received the money through the hawala agent near the bazaar. The agent was respectful but the line was very long and we waited from morning until afternoon.

P2 (female, 41): For me it was difficult because I had to travel two hours with my children. The transport cost was almost two hundred afghanis, which is a lot for us.

Moderator: Did anyone feel unsafe when collecting the money?

P3 (female, 28): I did not feel unsafe at the agent, but on the way back some men were watching us and I was afraid someone would take the money.

P1 (female, 34): I felt safe because my brother came with me.

Moderator: What did you spend the money on?

P2 (female, 41): Most of it went to rent. The landlord was asking for three months of rent and we were afraid of being evicted.

P4 (female, 52): We bought flour, oil and rice. The prices in the market have increased so the money finished in less than three weeks.

Moderator: Do you know how to make a complaint?

P3 (female, 28): Nobody told us about a hotline. If there is a number, we do not know it.

P4 (female, 52): I heard there is a number but I do not have a phone, so I cannot call.
""",
    "SYNTHETIC_FGD_men_Nangarhar.txt": """Title: FGD with men recipients (SYNTHETIC TEST TRANSCRIPT)
Type: FGD
Location: Jalalabad
Date: 2026-04-15
Group: Male cash recipients

Facilitator: How was the distribution process this time?

R1: The process was well organised. They called our names and we received the money within one hour.

R2: I disagree, for my family it was not well organised. My name was not on the list even though we were registered, and I had to come back two times.

Facilitator: What did your family use the assistance for?

R3: We paid our debts to the shopkeeper first. Without paying the debt he will not give us food on credit again.

R1: We used it for food and medicine for my mother who is sick.

Facilitator: Is there anything you would recommend to improve the programme?

R2: Please send a message before the distribution day so we do not waste money on transport.

R3: The amount should be bigger for families with many children, because twelve thousand is not enough for a family of ten.
""",
    "SYNTHETIC_KII_community_leader.txt": """Title: KII with community leader (SYNTHETIC TEST TRANSCRIPT)
Type: KII
Location: Guzara
Date: 2026-04-20
Group: Community leader

Interviewer: From your perspective, how did the cash programme affect the community?

KI: The cash helped many families to pay rent and buy food, especially widows. But some families who are very poor were not selected and they come to me to complain.

Interviewer: How are complaints handled?

KI: People bring complaints to me because they do not trust the hotline. I pass the complaints to the NGO staff, but I do not always receive an answer.

Interviewer: Were there any tensions?

KI: There was some tension between families who received and families who did not receive. Nobody was harmed, but people were unhappy with the selection.
""",
}

FABRICATED_QUOTES = [
    {"document": "SYNTHETIC_FGD_women_Herat.txt", "quote": "The hawala agent stole part of our money"},
    {"document": "SYNTHETIC_FGD_men_Nangarhar.txt", "quote": "Everyone in the village was completely satisfied with the programme"},
    {"document": "SYNTHETIC_KII_community_leader.txt", "quote": "The NGO always answers every complaint within one day"},
]


def write_all() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261121)
    paths = []
    p = OUT / "SYNTHETIC_PDM_cash_round1.xlsx"
    with pd.ExcelWriter(p) as xw:
        pdm_cash(rng).to_excel(xw, sheet_name="PDM_data", index=False)
    paths.append(p)
    p = OUT / "SYNTHETIC_WASH_household_survey.csv"; wash(rng).to_csv(p, index=False); paths.append(p)
    p = OUT / "SYNTHETIC_returnee_flow_monitoring.csv"; returnee_flow(rng).to_csv(p, index=False, sep=";"); paths.append(p)
    p = OUT / "SYNTHETIC_food_security.xlsx"; food_security(rng).to_excel(p, index=False); paths.append(p)
    p = OUT / "SYNTHETIC_baseline.csv"; baseline_endline(rng, False).to_csv(p, index=False); paths.append(p)
    p = OUT / "SYNTHETIC_endline.csv"; baseline_endline(rng, True).to_csv(p, index=False); paths.append(p)
    p = OUT / "SYNTHETIC_feedback_records.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(60):
            fh.write(json.dumps({"ticket": f"T{i:03d}", "date": f"2026-0{1 + i % 6}-1{i % 9}", "channel": ["Hotline", "Help desk", "Community leader"][i % 3],
                                 "category": ["Inclusion", "Delay", "Amount", "Staff conduct"][i % 4], "resolved": ["yes", "no"][i % 2]}) + "\n")
    paths.append(p)
    for name, text in TRANSCRIPTS.items():
        p = OUT / name; p.write_text(text, encoding="utf-8"); paths.append(p)
    (OUT / "SYNTHETIC_fabricated_quotes.json").write_text(json.dumps(FABRICATED_QUOTES, indent=2), encoding="utf-8")
    return paths


if __name__ == "__main__":
    for p in write_all():
        print(p.name)
