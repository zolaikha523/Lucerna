"""One-click dashboard generator: the 23 required scenarios, run on structurally different SYNTHETIC datasets.

The datasets (tests/adaptive_datasets.py and tests/dtm_workbook.py) differ in domain, column names, sheet layout,
size, and in whether they have dates or locations. Passing here shows the engine adapts across these datasets; it does
not prove it adapts to every real dataset.

Run:  python -m pytest tests/test_dashboard_engine.py -q
"""
from __future__ import annotations

import io
import re
import sys
import unittest
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"
ADAPT = FIX / "adaptive"

from tests.test_lucerna import Base  # noqa: E402

FILES = {
    "wash": "SYNTHETIC_WASH_camps.xlsx", "food": "SYNTHETIC_food_security_regions.csv", "mpca": "SYNTHETIC_MPCA_PDM_two_rounds.xlsx",
    "research": "SYNTHETIC_student_experience_survey.csv", "market": "SYNTHETIC_market_prices.xlsx",
    "unfamiliar": "SYNTHETIC_factory_maintenance_log.csv", "tiny": "SYNTHETIC_tiny.csv", "invalid": "SYNTHETIC_invalid_values.csv",
}
EXPLANATION_SECTIONS = ("what", "findings", "why", "interpretation", "implications", "actions", "limitations", "source")


class TestDashboardEngine(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests import adaptive_datasets, dtm_workbook
        if not all((ADAPT / f).exists() for f in FILES.values()):
            adaptive_datasets.write_all()
        if not (FIX / "SYNTHETIC_DTM_practice_workbook.xlsx").exists():
            (FIX / "SYNTHETIC_DTM_practice_workbook.xlsx").write_bytes(dtm_workbook.build())
        from lucerna.quant import dashboards, generator, store
        cls.store, cls.gen, cls.dash = store, generator, dashboards
        cls.ids, cls.all_ids, cls.dash_ids = {}, {}, {}
        for key, f in FILES.items():                      # scenario 1: upload
            ids = store.import_file(cls.admin, cls.pid, f, (ADAPT / f).read_bytes())
            cls.all_ids[key] = ids
            cls.ids[key] = ids[0]
        ids = store.import_file(cls.admin, cls.pid, "SYNTHETIC_DTM_practice_workbook.xlsx", (FIX / "SYNTHETIC_DTM_practice_workbook.xlsx").read_bytes())
        cls.all_ids["dtm"], cls.ids["dtm"] = ids, ids[0]
        for key, did in cls.ids.items():
            cls.dash_ids[key] = generator.generate(cls.admin, did, theme="corporate")

    # ---------------------------------------------------------------- helpers
    def d(self, key):
        return self.gen.get(self.admin, self.dash_ids[key])

    def titles(self, key):
        return [p["title"] for p in self.d(key)["spec"]["pages"]]

    def visuals(self, key):
        return [v for p in self.d(key)["spec"]["pages"] for v in p["visuals"]]

    def compute_all(self, key, flt=None):
        d = self.d(key)
        fr = self.gen.frames(self.admin, d)
        return d, fr, [(p, v, self.gen.compute_visual(d, v, fr, flt or {})) for p in d["spec"]["pages"] for v in p["visuals"]]

    # ---------------------------------------------------------------- 1–4 upload, multi-sheet, sheet detection, codebook exclusion
    def test_01_upload_creates_datasets_for_every_format(self):
        for key, did in self.ids.items():
            ds = self.store.get_dataset(self.admin, did)
            self.assertGreater(ds["row_count"], 0, key)

    def test_02_multi_sheet_workbooks_import_every_sheet(self):
        self.assertEqual(len(self.all_ids["dtm"]), 8)
        self.assertEqual(len(self.all_ids["wash"]), 3)
        self.assertEqual(len(self.all_ids["market"]), 2)

    def test_03_primary_analytical_sheet_detected_whatever_its_name(self):
        expect = {"dtm": ("FMS_Survey", 10000), "wash": ("HH_Data", 1800), "market": ("Prices", 600), "mpca": ("PDM", 900)}
        for key, (sheet, rows) in expect.items():
            ds = self.store.get_dataset(self.admin, self.ids[key])
            self.assertEqual(ds["source_table"], sheet, key)
            self.assertEqual(ds["row_count"], rows, key)
            self.assertEqual(self.d(key)["plan"]["n"], rows, key)

    def test_04_codebooks_and_documentation_never_become_the_dashboard(self):
        roles = {s["name"]: s["role"] for s in self.store.workbook_info(self.admin, self.ids["dtm"])["sheets"]}
        self.assertEqual(roles["Codebook"], "codebook")
        self.assertEqual(roles["README"], "documentation")
        self.assertEqual({s["name"]: s["role"] for s in self.store.workbook_info(self.admin, self.ids["wash"])["sheets"]}["Variables"], "codebook")
        shown = {c["name"] for c in self.gen.dataset_choices(self.admin, self.pid)}
        self.assertNotIn("Codebook", " ".join(shown))
        self.assertNotIn("Variables", " ".join(shown))
        # codebook labels are applied to the survey's variables instead
        self.assertEqual(self.store.labels(self.ids["wash"]).get("litres_per_person_day"), "Litres of water per person per day")

    # ---------------------------------------------------------------- 5–8 profiling, quality, statistics, domain
    def test_05_profiling_finds_dates_locations_and_rating_scales(self):
        v = {k: self.d(k)["plan"]["variables"] for k in ("wash", "research", "market", "food")}
        self.assertIn("visit_dt", v["wash"]["dates"])
        self.assertIn("camp_name", v["wash"]["geo"]["all"])
        self.assertGreaterEqual(len(v["research"]["likert"]), 5)
        self.assertFalse(v["research"].get("dates"))     # empty entries are left out of the stored plan
        self.assertFalse(v["research"].get("geo", {}).get("all"))
        self.assertIn("week_start", v["market"]["dates"])
        self.assertFalse(v["food"].get("dates"))

    def test_06_quality_flags_planted_problems(self):
        q = self.d("invalid")["plan"]["quality"]["findings"]
        text = " ".join(f["message"] for f in q)
        self.assertIn("repeated value", text)          # 20 duplicate ids
        self.assertRegex(text, r"village.*spelling/case|spelling/case.*village")
        lim = " ".join(self.d("invalid")["plan"]["limitations"])
        self.assertIn("invalid 'survey_date'", lim)     # 31/02/2026 is not a date

    def test_07_statistics_match_independent_calculation(self):
        from scipy import stats as ss
        d, fr, items = self.compute_all("wash")
        df = fr[None]
        # KPI: % of households with soap, computed by hand
        kpi = next(r for p, v, r in items if v["type"] == "kpi" and (v.get("condition") or {}).get("column") == "handwash_station_soap")
        s = df["handwash_station_soap"].dropna().astype(str).str.lower()
        self.assertAlmostEqual(float(kpi[0].table["value"].iloc[0]), 100 * s.isin(["yes", "true", "1"]).mean(), places=6)
        self.assertEqual(kpi[0].base_n, len(s))
        # group comparison: each binary outcome's percentages and chi-square p-value equal an independent scipy calculation
        v = next(v for p, v, r in items if v["type"] == "compare_table" and any(o["kind"] == "binary" for o in v["outcomes"]))
        data = self.gen.compute_visual(d, v, fr)[0]
        o = next(o for o in v["outcomes"] if o["kind"] == "binary")
        row = data.table[data.table["Outcome"] == (o.get("label") or o["column"])].iloc[0]
        g = df[[v["by"], o["column"]]].dropna()
        yes = g[o["column"]].astype(str).str.lower().isin([str(x).lower() for x in (o.get("value") or [])] + ["true", "1"])
        ct = pd.crosstab(g[v["by"]].astype(str), yes)
        p = ss.chi2_contingency(ct.values).pvalue
        self.assertEqual(row["p-value"], "p < 0.001" if p < 0.001 else f"p = {p:.3f}")
        for grp in ct.index:
            self.assertEqual(row[grp], f"{100 * ct.loc[grp, True] / ct.loc[grp].sum():.1f}%")

    def test_08_domain_recognised_from_content_not_file_names(self):
        dom = {k: self.d(k)["plan"]["domain"]["key"] for k in self.ids}
        self.assertEqual(dom["wash"], "wash")
        self.assertEqual(dom["food"], "food_security")
        self.assertEqual(dom["mpca"], "cash")
        self.assertEqual(dom["research"], "research")
        self.assertEqual(dom["market"], "market")
        self.assertEqual(dom["dtm"], "displacement")
        self.assertEqual(dom["unfamiliar"], "general")   # no humanitarian vocabulary: no invented sector
        self.assertEqual(dom["tiny"], "general")

    # ---------------------------------------------------------------- 9–13 visuals, pages, insights, filters, navigation
    def test_09_visuals_chosen_from_the_data(self):
        types = {k: {v["type"] for v in self.visuals(k)} for k in self.ids}
        self.assertIn("likert", types["research"])
        self.assertNotIn("line", types["research"])         # no dates -> no trend charts
        self.assertNotIn("line", types["food"])
        self.assertIn("line", types["market"])
        self.assertTrue(any(v["type"] == "line" and v.get("color") and v.get("measure") == "median" for v in self.visuals("market")))
        # fixed-design panel (same number of price records each week): no flat volume line, prices over time instead
        self.assertFalse(any(v["type"] == "line" and v.get("measure") == "count" for v in self.visuals("market")))
        self.assertNotIn("map_points", types["unfamiliar"])
        self.assertIn("multiselect", types["mpca"] | {"multiselect" if any(v["type"] in ("multiselect", "bar") and "spent" in str(v) for v in self.visuals("mpca")) else ""})
        self.assertIn("pyramid", types["research"])          # age + gender present

    def test_10_multi_page_dashboards_without_empty_pages(self):
        for key in self.ids:
            d, fr, items = self.compute_all(key)
            pages = d["spec"]["pages"]
            self.assertGreaterEqual(len(pages), 2, key)
            for p in pages:
                ok = [1 for pp, v, r in items if pp is p and r[0] is not None]
                self.assertTrue(ok, f"{key}: page '{p['title']}' has nothing that computes")
            errors = [f"{p['title']} / {v['type']}: {r[2]}" for p, v, r in items if r[2] and r[2].startswith("This visual could not be computed")]
            self.assertEqual(errors, [], key)
        self.assertGreaterEqual(len(self.titles("dtm")), 8)
        self.assertLessEqual(len(self.titles("tiny")), 3)

    def test_11_every_explanation_has_all_sections_and_only_real_numbers(self):
        for key in ("wash", "market", "research", "dtm"):
            d, fr, items = self.compute_all(key)
            for p, v, (data, ex, err, vv) in items:
                if ex is None or v["type"] in ("kpi",):
                    continue
                for s in EXPLANATION_SECTIONS:
                    self.assertIn(s, ex, f"{key}/{v['title']}")
                self.assertTrue(ex["what"] and ex["source"]["n"] is not None, f"{key}/{v['title']}")
                # every percentage quoted in a bar chart's findings exists in the computed table
                if v["type"] == "bar" and v.get("measure") == "count" and data is not None and "value" in data.table and not data.table.get("series", pd.Series()).any():
                    col = data.table["value"].dropna()
                    top = sorted(col, reverse=True)
                    vals = {f"{x:.1f}" for x in col} | {f"{sum(top[:k]):.1f}" for k in range(2, 4)}
                    for total in {col.sum(), data.base_n}:      # share of the shown categories, or of every valid answer (top-N charts)
                        shares = sorted((100 * x / total for x in col), reverse=True)
                        vals |= {f"{x:.1f}" for x in shares} | {f"{sum(shares[:k]):.1f}" for k in range(2, 4)}
                    for m in re.findall(r"(\d+\.\d)%", " ".join(ex["findings"])):
                        self.assertIn(m, vals, f"{key}/{v['title']}: {m}% not in data")

    def test_12_filters_change_every_number_consistently(self):
        d, fr, items = self.compute_all("wash", {"camp_name": {"values": ["Camp Alpha"]}})
        n_alpha = int((fr[None]["camp_name"] == "Camp Alpha").sum())
        kpi = next(r for p, v, r in items if v["type"] == "kpi" and v.get("kpi") == "count_rows")
        self.assertEqual(kpi[0].base_n, n_alpha)
        self.assertLess(n_alpha, len(fr[None]))
        # drill-down narrows to one location and moves one level down the hierarchy
        geo = next(v for v in self.visuals("wash") if v.get("drill"))
        data, ex, err, vv = self.gen.compute_visual(d, geo, fr, {}, [(geo["drill"][0], "Camp Beta")])
        self.assertIsNone(err)
        self.assertEqual(vv["x"], geo["drill"][1])

    def test_13_page_navigation_is_unique_and_ordered(self):
        for key in self.ids:
            pages = self.d(key)["spec"]["pages"]
            self.assertEqual(len({p["key"] for p in pages}), len(pages), key)
            self.assertEqual(pages[0]["key"], "overview")
            self.assertEqual(pages[-1]["key"], "quality")

    # ---------------------------------------------------------------- 14–17 themes, save, reopen, edit
    def test_14_all_four_themes_and_branding(self):
        for t in self.gen.THEMES:
            did = self.gen.generate(self.admin, self.ids["food"], theme=t, branding={"title": f"Theme {t}", "subtitle": "SYNTHETIC"})
            d = self.gen.get(self.admin, did)
            self.assertEqual(d["theme"], t)
            self.assertEqual(d["branding"]["title"], f"Theme {t}")
        with self.assertRaises(self.gen.GenerationError):
            self.gen.generate(self.admin, self.ids["food"], theme="neon")
        self.gen.update_meta(self.admin, did, theme="executive")
        self.assertEqual(self.gen.get(self.admin, did)["theme"], "executive")

    def test_15_generated_dashboard_is_saved_with_a_version(self):
        listed = {r["id"] for r in self.gen.list_for_project(self.admin, self.pid)}
        self.assertTrue(set(self.dash_ids.values()) <= listed)
        self.assertEqual(len(self.dash.versions(self.admin, self.dash_ids["wash"])), 1)

    def test_16_reopen_returns_the_same_dashboard(self):
        a = self.d("market")
        b = self.gen.get(self.admin, self.dash_ids["market"])
        self.assertEqual(a["spec"], b["spec"])
        self.assertEqual(a["plan"]["domain"], b["plan"]["domain"])

    def test_17_rename_duplicate_refresh_and_restore(self):
        did = self.gen.generate(self.admin, self.ids["mpca"], theme="vibrant")
        self.gen.update_meta(self.admin, did, name="Renamed SYNTHETIC dashboard")
        self.assertEqual(self.gen.get(self.admin, did)["name"], "Renamed SYNTHETIC dashboard")
        cp = self.dash.duplicate(self.admin, did)
        c = self.gen.get(self.admin, cp)
        self.assertEqual(c["theme"], "vibrant")
        self.assertEqual(c["spec"]["pages"][0]["title"], self.gen.get(self.admin, did)["spec"]["pages"][0]["title"])
        self.gen.refresh(self.admin, did)
        vs = self.dash.versions(self.admin, did)
        self.assertEqual(len(vs), 2)
        self.dash.restore_version(self.admin, did, vs[-1]["id"])
        self.assertEqual(len(self.dash.versions(self.admin, did)), 3)

    # ---------------------------------------------------------------- 18–20 exports
    def _export(self, key, fmt):
        from lucerna.reports import dashboard_export
        d = self.d(key)
        fr = self.gen.frames(self.admin, d)
        return dashboard_export.export(self.admin, d, fr, {}, fmt, lambda v: self.gen.compute_visual(d, v, fr, {}))

    def test_18_pdf_export(self):
        pdf = self._export("wash", "pdf")
        self.assertTrue(pdf.startswith(b"%PDF"))
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(pdf))
        self.assertGreaterEqual(len(r.pages), len(self.titles("wash")))
        self.assertIn("Water Access", "".join(p.extract_text() or "" for p in r.pages))

    def test_19_excel_export(self):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(self._export("market", "xlsx")))
        self.assertIn("About", wb.sheetnames)
        self.assertIn("Insights", wb.sheetnames)
        self.assertGreater(len(wb.sheetnames), 4)

    def test_20_detailed_word_report(self):
        data = self._export("research", "docx")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("Ratings &amp; Perceptions", xml)
        self.assertIn("Limitations", xml)

    # ---------------------------------------------------------------- 21–23 missing, invalid, insufficient data
    def test_21_missing_values_are_reported_not_hidden(self):
        types = {v["type"] for v in self.visuals("wash")}
        self.assertIn("quality_missing", types)          # 90 litres values removed on purpose
        self.assertNotIn("quality_missing", {v["type"] for v in self.visuals("unfamiliar")})   # nothing missing -> no empty chart
        d, fr, items = self.compute_all("wash")
        box = next(r for p, v, r in items if v["type"] == "histogram" and v.get("value") == "litres_per_person_day")
        self.assertEqual(box[0].base_n, int(fr[None]["litres_per_person_day"].notna().sum()))

    def test_22_invalid_values_do_not_break_generation(self):
        d, fr, items = self.compute_all("invalid")
        self.assertEqual([r[2] for p, v, r in items if r[2] and "could not be computed" in r[2]], [])
        self.assertTrue(any(v.get("kpi") == "duplicates" for v in self.visuals("invalid")))

    def test_23_insufficient_data_is_handled_honestly(self):
        tiny = self.d("tiny")
        self.assertNotIn("Group Comparisons", self.titles("tiny"))
        self.assertNotIn("Geographic Analysis", self.titles("tiny"))
        self.assertTrue(any("Only 6 records" in x for x in tiny["plan"]["limitations"]))
        self.assertFalse(tiny["plan"]["feasibility"]["forecast"]["possible"])

    # ---------------------------------------------------------------- adaptivity and no dataset-specific logic
    def test_dashboards_differ_across_datasets(self):
        structures = {k: tuple(self.titles(k)) for k in self.ids}
        self.assertEqual(len(set(structures.values())), len(structures), structures)

    def test_units_are_not_named_until_confirmed(self):
        lim = " ".join(self.d("market")["plan"]["limitations"])
        self.assertIn("has not been confirmed", lim)
        self.assertNotIn("respondents", " ".join(v.get("title", "") for v in self.visuals("market")).lower())

    def test_engine_has_no_dataset_specific_rules(self):
        src = " ".join((ROOT / "lucerna" / "quant" / f).read_text(encoding="utf-8") for f in ("engine.py", "domain.py", "workbook.py", "explain.py", "generator.py"))
        for token in ("FMS_Survey", "FMC_Daily", "fmp_", "IOM", "DTM", "HH_Data", "week_start", "camp_name"):
            self.assertNotIn(token, src, token)


if __name__ == "__main__":
    unittest.main()
