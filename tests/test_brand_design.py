"""Presentation-layer tests for the design transformation: logo colour extraction, brand palettes, SVG safety,
brand persistence, readable titles, chart restyling and composition. All logos are fictional (SYNTHETIC).

Run:  python -m pytest tests/test_brand_design.py -q
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOGOS = ROOT / "tests" / "fixtures" / "logos"
GREEN_ORANGE, BLUE_RED, PURPLE_GOLD, MALICIOUS = (LOGOS / f for f in (
    "SYNTHETIC_logo_green_orange.png", "SYNTHETIC_logo_blue_red.jpg", "SYNTHETIC_logo_purple_gold.svg", "SYNTHETIC_logo_malicious.svg"))

from tests.test_lucerna import Base  # noqa: E402


def _hue_family(hex_: str) -> str:
    from lucerna.ui.brand import color as C
    L, Cc, h = C.oklch(hex_)
    if Cc < 0.035:
        return "neutral"
    for name, lo, hi in (("red", 0, 40), ("orange", 40, 80), ("yellow", 80, 110), ("green", 110, 170), ("cyan", 170, 220), ("blue", 220, 290), ("purple", 290, 340)):
        if lo <= h < hi:
            return name
    return "red"


class TestExtraction(unittest.TestCase):
    def test_three_logos_give_their_own_colours(self):
        from lucerna.ui.brand import extract
        fams = {}
        for f in (GREEN_ORANGE, BLUE_RED, PURPLE_GOLD):
            out = extract.extract(f.read_bytes())
            self.assertTrue(out["swatches"], f.name)
            fams[f.name] = [_hue_family(s["hex"]) for s in out["swatches"][:3]]
        self.assertEqual(fams[GREEN_ORANGE.name][:2], ["green", "orange"])
        self.assertEqual(fams[BLUE_RED.name][0], "blue")
        self.assertIn("red", fams[BLUE_RED.name][:3])
        self.assertEqual(fams[PURPLE_GOLD.name][0], "purple")
        self.assertTrue({"orange", "yellow"} & set(fams[PURPLE_GOLD.name][:3]))

    def test_white_transparent_and_black_are_ignored(self):
        import io

        from PIL import Image

        from lucerna.ui.brand import extract
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(100):
            for y in range(100):
                if x < 30:
                    img.putpixel((x, y), (255, 255, 255, 255))
                elif x < 50:
                    img.putpixel((x, y), (0, 0, 0, 255))
                elif x < 60:
                    img.putpixel((x, y), (220, 40, 40, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        out = extract.extract(buf.getvalue())
        self.assertEqual(len(out["swatches"]), 1)
        self.assertEqual(_hue_family(out["swatches"][0]["hex"]), "red")

    def test_rejects_unsupported_and_oversized(self):
        from lucerna.ui.brand import extract
        with self.assertRaises(extract.BrandError):
            extract.extract(b"GIF89a....")
        with self.assertRaises(extract.BrandError):
            extract.extract(b"\x89PNG\r\n\x1a\n" + b"0" * 2_100_000)

    def test_deterministic(self):
        from lucerna.ui.brand import extract
        a = extract._raster.__wrapped__(GREEN_ORANGE.read_bytes())
        b = extract._raster.__wrapped__(GREEN_ORANGE.read_bytes())
        self.assertEqual(a, b)


class TestSvgSafety(unittest.TestCase):
    def test_malicious_svg_is_cleaned(self):
        from lucerna.ui.brand import svg_safe
        clean = svg_safe.sanitize(MALICIOUS.read_bytes()).decode().lower()
        for bad in ("<script", "onload", "onclick", "javascript:", "foreignobject", "href", "@import", "<iframe"):
            self.assertNotIn(bad, clean, bad)

    def test_entities_and_doctype_rejected(self):
        from lucerna.ui.brand import extract, svg_safe
        bomb = b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'
        with self.assertRaises(extract.BrandError):
            svg_safe.parse(bomb)

    def test_non_svg_xml_rejected(self):
        from lucerna.ui.brand import extract, svg_safe
        with self.assertRaises(extract.BrandError):
            svg_safe.parse(b"<html><body>hi</body></html>")


class TestDesignSystem(unittest.TestCase):
    def _all(self):
        from lucerna.ui.brand import design, extract
        out = {}
        for f in (GREEN_ORANGE, BLUE_RED, PURPLE_GOLD):
            ex = extract.extract(f.read_bytes())
            for theme in ("corporate", "executive", "vibrant", "minimal"):
                out[(f.name, theme)] = design.build(ex, theme)
        for theme in ("corporate", "executive", "vibrant", "minimal"):
            out[("none", theme)] = design.build(None, theme)
        return out

    def test_accessibility_checks_pass_for_every_logo_and_theme(self):
        for k, d in self._all().items():
            c = d["checks"]
            with self.subTest(k):
                self.assertGreaterEqual(c["ink_on_surface"], 7.0)
                self.assertGreaterEqual(c["secondary_text"], 4.5)
                self.assertGreaterEqual(c["muted_text"], 3.0)
                self.assertGreaterEqual(c["accent_on_surface"], 3.0)
                self.assertGreaterEqual(c["chart_min_contrast"], 3.0)
                self.assertGreaterEqual(c["chart_min_neighbour_distance"], 14.0)
                self.assertGreaterEqual(c["chart_min_cvd_distance"], 8.0)

    def test_logos_give_visibly_different_identities(self):
        from lucerna.ui.brand import color as C
        ds = self._all()
        for theme in ("corporate", "executive"):
            a, b, c = (ds[(f.name, theme)] for f in (GREEN_ORANGE, BLUE_RED, PURPLE_GOLD))
            for x, y in ((a, b), (a, c), (b, c)):
                # identity = the brand's role colours together (two navy-ish primaries can still be told apart by their secondaries)
                self.assertGreater(C.delta_e(x["accent"], y["accent"]) + C.delta_e(x["secondary"], y["secondary"]), 30)
                self.assertNotEqual(x["categorical"][:3], y["categorical"][:3])
                self.assertNotEqual(x["bg"], y["bg"])     # backgrounds are tinted toward each brand

    def test_logo_colour_not_used_for_everything(self):
        for k, d in self._all().items():
            with self.subTest(k):
                self.assertGreaterEqual(len(set(d["categorical"])), 8)
                self.assertNotEqual(d["bg"], d["primary_raw"])
                self.assertNotEqual(d["ink"], d["primary_raw"])

    def test_custom_colours_override_logo(self):
        from lucerna.ui.brand import design, extract
        ex = extract.extract(GREEN_ORANGE.read_bytes())
        d = design.build(ex, "executive", custom={"primary": "#C2185B"})
        self.assertEqual(d["roles"][0], "#C2185B")
        self.assertIn("custom", d["source"])

    def test_monochrome_logo_gets_restrained_system(self):
        from lucerna.ui.brand import design
        d = design.build({"swatches": [], "character": {"label": "Monochrome"}}, "corporate")
        self.assertEqual(d["source"], "logo")
        self.assertIn("monochrome", d["rule"])

    def test_deterministic(self):
        from lucerna.ui.brand import design, extract
        ex = extract.extract(BLUE_RED.read_bytes())
        self.assertEqual(design.build(ex, "vibrant", background="brand"), design.build(ex, "vibrant", background="brand"))


class TestTitles(unittest.TestCase):
    def test_clean_labels(self):
        from lucerna.ui.titles import clean
        self.assertEqual(clean("amount_received_afn"), "Amount received AFN")
        self.assertEqual(clean("x", {"x": "Codebook label"}), "Codebook label")
        self.assertTrue(clean("q1_the_course_content_was_r").endswith("…"))      # cut-off name shown as cut, not guessed
        self.assertNotIn("relevant", clean("q1_the_course_content_was_r"))

    def test_readable_keeps_technical_title(self):
        from lucerna.ui.titles import readable
        v = {"type": "bar", "x": "latrine_type", "measure": "pct_condition", "condition": {"column": "water_treated"},
             "title": "Water treated: % yes by Latrine type", "kind": "comparison"}
        r = readable(v, {"labels": {}})
        self.assertEqual(r["technical"], v["title"])
        self.assertIn("latrine type", r["title"])
        self.assertIn("water treated", r["title"].lower())
        self.assertTrue(r["subtitle"])

    def test_every_visual_type_gets_a_title(self):
        from lucerna.quant.charts import VISUAL_TYPES
        from lucerna.ui.titles import readable
        for t in VISUAL_TYPES:
            self.assertTrue(readable({"type": t, "title": "Engine title"}, {})["title"], t)


class TestPersistenceAndRendering(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lucerna.quant import dashboards, generator, store
        cls.gen, cls.dash = generator, dashboards
        fix = ROOT / "tests" / "fixtures"
        cls.ds = store.import_file(cls.admin, cls.pid, "SYNTHETIC_WASH_household_survey.csv", (fix / "SYNTHETIC_WASH_household_survey.csv").read_bytes())[0]

    def _branded(self, logo: Path, theme: str) -> int:
        from lucerna.ui import brand_panel
        choice = {"title": f"Brand test {logo.stem}", "subtitle": "", "show_org": True, "logo": "custom", "logo_bytes": logo.read_bytes(),
                  "org_name": "SYNTHETIC Org", "tagline": "Synthetic tagline", "background": "auto", "bg_bytes": None, "custom": {}, "use_logo_colours": True}
        branding = brand_panel.to_branding(self.admin, self.pid, choice)
        return self.gen.generate(self.admin, self.ds, theme=theme, branding=branding)

    def test_two_dashboards_keep_independent_brands(self):
        from lucerna.ui.brand import store
        a, b = self._branded(GREEN_ORANGE, "corporate"), self._branded(PURPLE_GOLD, "executive")
        da, db_ = self.gen.get(self.admin, a), self.gen.get(self.admin, b)
        Da, Db = store.design_for(da, da["theme"]), store.design_for(db_, db_["theme"])
        self.assertNotEqual(Da["accent"], Db["accent"])
        self.assertEqual(store.logo(db_)[1], "image/svg+xml")
        self.assertEqual(store.logo(da)[1], "image/png")
        self.assertIsNotNone(self.gen.logo_bytes(da))        # PNG logo also reaches PDF/Word exports
        self.assertIsNone(self.gen.logo_bytes(db_))          # SVG logos are screen-only (documented limitation)
        raw = db_["branding"]["logo_svg"]
        self.assertNotIn("/", raw)                           # only a file name is stored, never a path

    def test_brand_survives_theme_change_rename_and_duplicate(self):
        from lucerna.ui.brand import store
        did = self._branded(BLUE_RED, "corporate")
        before = store.design_for(self.gen.get(self.admin, did), "corporate")["roles"]
        self.gen.update_meta(self.admin, did, theme="executive")
        self.gen.update_meta(self.admin, did, name="Renamed", branding={"title": "Renamed"})
        d = self.gen.get(self.admin, did)
        self.assertEqual(d["theme"], "executive")
        self.assertEqual(store.design_for(d, d["theme"])["roles"], before)
        self.assertEqual(d["branding"]["brand"]["org_name"], "SYNTHETIC Org")
        nid = self.dash.duplicate(self.admin, did)
        self.gen.update_meta(self.admin, nid, theme=d["theme"], branding=d["branding"])
        dup = self.gen.get(self.admin, nid)
        self.assertEqual(store.design_for(dup, dup["theme"])["roles"], before)
        self.assertEqual(store.logo(dup)[0], store.logo(d)[0])

    def test_restyle_changes_look_not_data(self):
        from lucerna.quant import charts, generator
        from lucerna.ui import viz_style
        from lucerna.ui.brand import store
        did = self._branded(GREEN_ORANGE, "executive")
        d = self.gen.get(self.admin, did)
        frames = generator.frames(self.admin, d)
        D = store.design_for(d, d["theme"])
        checked = 0
        for p in d["spec"]["pages"]:
            for v in p["visuals"]:
                if v["type"] in ("kpi", "text", "table", "stat_summary", "compare_table", "methodology"):
                    continue
                data, ex, err, vv = generator.compute_visual(d, v, frames)
                if err or data is None:
                    continue
                fig = charts.figure(vv, data, viz_style.engine_mode(D), frames[None])
                out = viz_style.restyle(fig, vv, D, labels=d["plan"].get("labels"))
                self.assertEqual(out.layout.paper_bgcolor, "rgba(0,0,0,0)")
                self.assertEqual(out.layout.plot_bgcolor, "rgba(0,0,0,0)")
                self.assertEqual(len(out.data), len(fig.data))
                import json
                for t0, t1 in zip(json.loads(fig.to_json())["data"], json.loads(out.to_json())["data"]):
                    for attr in ("x", "y", "values", "labels", "z", "base", "text", "customdata"):
                        self.assertEqual(t0.get(attr), t1.get(attr), f"{v['type']}.{attr}")
                checked += 1
        self.assertGreater(checked, 10)

    def test_composition_shows_every_visual_once(self):
        from lucerna.ui import composition
        did = self._branded(PURPLE_GOLD, "vibrant")
        d = self.gen.get(self.admin, did)
        for i, p in enumerate(d["spec"]["pages"]):
            lay = composition.arrange(p["visuals"], d["plan"], i)
            shown = lay["kpis"] + ([lay["hero"]] if lay["hero"] else []) + [v for r in lay["rows"] for v, _ in r]
            expected = [v for v in p["visuals"] if v["type"] != "text"]
            self.assertEqual(sorted(id(v) for v in shown), sorted(id(v) for v in expected))
            for r in lay["rows"]:
                self.assertEqual(sum(w for _, w in r), 12)

    def test_domains_get_different_layouts(self):
        from lucerna.ui import composition
        names = {composition.profile({"domain": {"key": k}})["name"] for k in ("displacement", "wash", "food_security", "cash", "research")}
        self.assertEqual(len(names), 5)


if __name__ == "__main__":
    unittest.main()
