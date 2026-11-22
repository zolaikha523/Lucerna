"""Lucerna automated tests (unit + integration) on SYNTHETIC data.

Run:  python -m pytest tests -q     or     python -m unittest discover -s tests -v
Each test class gets its own temporary data directory and database.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"


def _fresh_env() -> str:
    d = tempfile.mkdtemp(prefix="lucerna_test_")
    for k, sub in (("LUCERNA_DATA_DIR", ""), ("LUCERNA_UPLOAD_DIR", "uploads"), ("LUCERNA_ANALYTIC_DIR", "analytic"), ("LUCERNA_REPORT_DIR", "outputs"),
                   ("LUCERNA_LOG_DIR", "logs"), ("LUCERNA_TEMP_DIR", "tmp"), ("LUCERNA_BACKUP_DIR", "backups")):
        os.environ[k] = str(Path(d) / sub) if sub else d
    os.environ["LUCERNA_DB"] = str(Path(d) / "lucerna.sqlite3")
    os.environ.pop("LUCERNA_EXTERNAL_AI_ENABLED", None)
    from lucerna import config, db
    config.reload_settings()
    db.reset_init_cache()
    db.init()
    return d


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import synthetic_data
        if not (FIX / "SYNTHETIC_PDM_cash_round1.xlsx").exists():
            synthetic_data.write_all()
        cls.tmp = _fresh_env()
        from lucerna.security import auth
        from lucerna.services import orgs
        cls.auth, cls.orgs = auth, orgs
        uid = auth.create_user("admin", "Strong-Pass-2026!", system_role="system_admin")
        cls.admin = auth.to_current(auth.get_user_by_id(uid))
        cls.org = orgs.create_organization(cls.admin, "SYNTHETIC Org A")
        orgs.add_org_member(cls.admin, cls.org, uid, "org_admin")
        cls.pid = orgs.create_project(cls.admin, cls.org, "SYNTHETIC Project A")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def make_user(cls, name: str, role: str | None, org: int | None = None, project: int | None = None):
        uid = cls.auth.create_user(name, "Member-Pass-2026!")
        u = cls.auth.to_current(cls.auth.get_user_by_id(uid))
        cls.orgs.add_org_member(cls.admin, org or cls.org, uid, "member")
        if role:
            cls.orgs.set_project_member(cls.admin, project or cls.pid, uid, role)
        return u


# ============================================================ quantitative

class TestQuantitative(Base):
    DATASETS = ["SYNTHETIC_PDM_cash_round1.xlsx", "SYNTHETIC_WASH_household_survey.csv", "SYNTHETIC_returnee_flow_monitoring.csv",
                "SYNTHETIC_food_security.xlsx", "SYNTHETIC_baseline.csv", "SYNTHETIC_endline.csv", "SYNTHETIC_feedback_records.jsonl"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lucerna.quant import store
        cls.store = store
        cls.ids = {}
        for f in cls.DATASETS:
            ids = store.import_file(cls.admin, cls.pid, f, (FIX / f).read_bytes())
            store.update_mapping(cls.admin, ids[0], {}, confirm_all=True)
            cls.ids[f] = ids[0]

    def test_every_dataset_gets_an_adaptive_dashboard_that_computes(self):
        from lucerna.quant import charts, dashboards
        page_sets = {}
        for f, did in self.ids.items():
            dash_id = dashboards.generate_auto(self.admin, did)
            d = dashboards.get(self.admin, dash_id)
            df = self.store.analytic_frame(self.admin, did)
            errors = []
            for p in d["spec"]["pages"]:
                for v in p["visuals"]:
                    try:
                        data = charts.compute(df, v)
                        if v["type"] not in ("kpi", "text", "table", "stat_summary"):
                            charts.figure(v, data, "light", df)
                    except charts.Unsupported:
                        pass
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"{f} / {p['title']} / {v['type']}: {e}")
            self.assertEqual(errors, [])
            page_sets[f] = tuple(p["title"] for p in d["spec"]["pages"])
            self.assertGreaterEqual(len(page_sets[f]), 2)
        # adaptive: datasets of different types do not all get the same page structure
        self.assertGreaterEqual(len(set(page_sets.values())), 4, page_sets)
        self.assertIn("Mobility & Flows", page_sets["SYNTHETIC_returnee_flow_monitoring.csv"])
        self.assertIn("Geograph", " ".join(page_sets["SYNTHETIC_WASH_household_survey.csv"]))

    def test_bar_chart_values_match_independent_calculation(self):
        from lucerna.quant import charts
        df = self.store.analytic_frame(self.admin, self.ids["SYNTHETIC_WASH_household_survey.csv"])
        col = next(c for c in df.columns if df[c].dtype == "string" and 2 <= df[c].nunique() <= 6)
        data = charts.compute(df, {"type": "bar", "x": col, "measure": "count"})
        expected = df[col].value_counts()
        for _, r in data.table.iterrows():
            self.assertEqual(int(r["value"]), int(expected[r["x"]]))

    def test_percentage_indicator_matches_manual_calculation_and_never_invents_targets(self):
        df = self.store.analytic_frame(self.admin, self.ids["SYNTHETIC_PDM_cash_round1.xlsx"])
        col = next(c for c in df.columns if str(df[c].dtype) == "boolean")
        iid = self.store.save_indicator(self.admin, self.pid, {"name": "SYNTHETIC test %", "indicator_type": "percentage", "definition": "test",
                                                               "numerator": {"column": col, "op": "in", "value": ["yes"]},
                                                               "dataset_id": self.ids["SYNTHETIC_PDM_cash_round1.xlsx"]})
        res = self.store.compute_indicator(self.admin, iid)
        valid = df[col].notna()
        manual = 100 * df.loc[valid, col].astype(bool).sum() / valid.sum()
        self.assertAlmostEqual(res["value"], manual, places=6)
        self.assertEqual(res["denominator"], int(valid.sum()))
        self.assertIsNone(res["target"])
        self.assertIsNone(res["baseline"])
        self.assertNotIn("achievement_pct_of_target", res)
        self.assertEqual(len(res["ci95"]), 2)

    def test_suggested_indicators_are_provisional_without_targets(self):
        from lucerna.quant import indicators
        d = self.store.get_dataset(self.admin, self.ids["SYNTHETIC_PDM_cash_round1.xlsx"])
        sug = indicators.suggest_indicators(self.store.analytic_frame(self.admin, d["id"]), d["profile"])
        self.assertTrue(sug)
        for s in sug:
            self.assertEqual(s["status"], "provisional")
            self.assertNotIn("target", s)
            self.assertNotIn("baseline", s)

    def test_cleaning_never_touches_the_original_and_can_be_reverted(self):
        did = self.ids["SYNTHETIC_PDM_cash_round1.xlsx"]
        orig_before = self.store.original_frame(self.admin, did).copy()
        rows_before = len(self.store.analytic_frame(self.admin, did))
        tid = self.store.propose_transformation(self.admin, did, "drop_duplicates", {}, "test dedupe")
        self.store.decide_transformation(self.admin, tid, True)
        rows_after = len(self.store.analytic_frame(self.admin, did))
        self.assertLessEqual(rows_after, rows_before)
        self.assertTrue(self.store.original_frame(self.admin, did).equals(orig_before))
        self.store.decide_transformation(self.admin, tid, False)   # revert
        self.assertEqual(len(self.store.analytic_frame(self.admin, did)), rows_before)
        statuses = {t["id"]: t["status"] for t in self.store.transformations(did)}
        self.assertEqual(statuses[tid], "reverted")

    def test_quality_detects_planted_issues_in_pdm(self):
        q = self.store.run_quality(self.admin, self.ids["SYNTHETIC_PDM_cash_round1.xlsx"])
        types = {f["type"] for f in q["findings"]}
        self.assertTrue(types, "the PDM fixture contains deliberate issues")
        self.assertTrue(q["proposals"])

    def test_forecast_refused_with_short_history(self):
        import pandas as pd
        from lucerna.quant import stats
        ts = pd.DataFrame({"period": pd.date_range("2026-01-01", periods=6, freq="MS"), "value": [1, 2, 3, 4, 5, 6]})
        r = stats.forecast(ts, 3)
        self.assertFalse(r["available"])

    def test_baseline_endline_comparison_checks_compatibility(self):
        from lucerna.quant import compare
        a, b = self.ids["SYNTHETIC_baseline.csv"], self.ids["SYNTHETIC_endline.csv"]
        res = compare.compatibility(self.store.analytic_frame(self.admin, a), self.store.analytic_frame(self.admin, b),
                                    self.store.mapping(a), self.store.mapping(b), self.store.get_dataset(self.admin, a), self.store.get_dataset(self.admin, b))
        self.assertTrue(res["comparable_columns"])
        wash = self.ids["SYNTHETIC_WASH_household_survey.csv"]
        res2 = compare.compatibility(self.store.analytic_frame(self.admin, a), self.store.analytic_frame(self.admin, wash),
                                     self.store.mapping(a), self.store.mapping(wash), {"unit_of_analysis": "household"}, {"unit_of_analysis": "individual"})
        self.assertFalse(res2["valid"])

    def test_power_bi_package_is_honest(self):
        from lucerna.reports import powerbi
        data = powerbi.build_package(self.admin, self.ids["SYNTHETIC_PDM_cash_round1.xlsx"])
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        self.assertFalse(any(n.lower().endswith(".pbix") for n in names))
        readme = next(n for n in names if "readme" in n.lower())
        text = z.read(readme).decode("utf-8").lower()
        self.assertIn("not", text)
        self.assertIn("pbix", text)

    def test_maps_only_from_valid_coordinates(self):
        from lucerna.quant import charts
        import pandas as pd
        df = pd.DataFrame({"lat": [34.3, 999, None, 34.4], "lon": [62.2, 62.1, 62.0, 500]})
        data = charts.compute(df, {"type": "map_points", "lat": "lat", "lon": "lon"})
        self.assertEqual(len(data.table), 1)


# ============================================================ qualitative

class TestQualitative(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lucerna.qual import store
        cls.q = store
        cls.docs = {f: store.import_document(cls.admin, cls.pid, f, (FIX / f).read_bytes())
                    for f in ["SYNTHETIC_FGD_women_Herat.txt", "SYNTHETIC_FGD_men_Nangarhar.txt", "SYNTHETIC_KII_community_leader.txt"]}

    def seg_containing(self, doc: str, text: str) -> dict:
        return next(s for s in self.q.segments(self.admin, self.docs[doc]) if text in s["text"])

    def test_segments_are_speaker_turns_with_exact_offsets_and_no_labels(self):
        for did in self.docs.values():
            d = self.q.get_document(self.admin, did)
            for s in self.q.segments(self.admin, did):
                self.assertEqual(d["full_text"][s["start_char"]:s["end_char"]], s["text"])
                self.assertNotRegex(s["text"], r"^(P\d+|Moderator|R\d+)\b.*?:")
        roles = {s["speaker_role"] for s in self.q.segments(self.admin, self.docs["SYNTHETIC_FGD_women_Herat.txt"])}
        self.assertIn("moderator", roles)
        self.assertIn("respondent", roles)

    def test_exact_quote_verified(self):
        s = self.seg_containing("SYNTHETIC_FGD_women_Herat.txt", "Nobody told us about a hotline")
        r = self.q.add_quotation(self.admin, self.pid, "Nobody told us about a hotline.", segment_id=s["id"])
        self.assertEqual(r["status"], "verified")
        self.assertEqual(r["verified_text"], "Nobody told us about a hotline.")

    def test_fabricated_quotes_rejected(self):
        for item in json.loads((FIX / "SYNTHETIC_fabricated_quotes.json").read_text(encoding="utf-8")):
            segs = self.q.segments(self.admin, self.docs[item["document"]])
            for s in segs[:5]:
                r = self.q.add_quotation(self.admin, self.pid, item["quote"], segment_id=s["id"])
                self.assertEqual(r["status"], "rejected", item["quote"])

    def test_paraphrase_ellipsis_and_moderator_rejected(self):
        s = self.seg_containing("SYNTHETIC_FGD_women_Herat.txt", "Nobody told us about a hotline")
        self.assertEqual(self.q.add_quotation(self.admin, self.pid, "No one informed us about any hotline", segment_id=s["id"])["status"], "rejected")
        self.assertEqual(self.q.add_quotation(self.admin, self.pid, "Nobody told us ... we do not know it", segment_id=s["id"])["status"], "rejected")
        m = next(x for x in self.q.segments(self.admin, self.docs["SYNTHETIC_FGD_women_Herat.txt"]) if x["speaker_role"] == "moderator")
        self.assertEqual(self.q.add_quotation(self.admin, self.pid, " ".join(m["text"].split()[:6]), segment_id=m["id"])["status"], "rejected")

    def test_speaker_label_cannot_be_part_of_quote(self):
        s = self.seg_containing("SYNTHETIC_FGD_women_Herat.txt", "Nobody told us about a hotline")
        r = self.q.add_quotation(self.admin, self.pid, "P3 (female, 28): Nobody told us about a hotline.", segment_id=s["id"])
        self.assertEqual(r["status"], "rejected")

    def test_wrong_segment_goes_to_manual_review(self):
        segs = self.q.segments(self.admin, self.docs["SYNTHETIC_FGD_women_Herat.txt"])
        right = self.seg_containing("SYNTHETIC_FGD_women_Herat.txt", "Nobody told us about a hotline")
        wrong = next(s for s in segs if s["id"] != right["id"] and s["speaker_role"] == "respondent")
        r = self.q.add_quotation(self.admin, self.pid, "Nobody told us about a hotline.", segment_id=wrong["id"])
        self.assertEqual(r["status"], "manual_review")
        res = self.q.confirm_manual_review(self.admin, r["id"], right["id"], "Nobody told us about a hotline.")
        self.assertEqual(res["status"], "verified")

    def test_ocr_documents_never_auto_verify(self):
        from lucerna import db
        did = self.docs["SYNTHETIC_KII_community_leader.txt"]
        db.execute("UPDATE qual_documents SET requires_verification=1 WHERE id=?", (did,))
        try:
            s = next(x for x in self.q.segments(self.admin, did) if x["speaker_role"] == "respondent" and len(x["text"].split()) > 6)
            r = self.q.add_quotation(self.admin, self.pid, " ".join(s["text"].split()[:7]), segment_id=s["id"])
            self.assertEqual(r["status"], "manual_review")
        finally:
            db.execute("UPDATE qual_documents SET requires_verification=0 WHERE id=?", (did,))

    def test_only_verified_quotes_can_be_approved_and_register_reverifies(self):
        from lucerna import db
        from lucerna.qual.store import QualError
        s = self.seg_containing("SYNTHETIC_FGD_women_Herat.txt", "The transport cost was almost two hundred afghanis")
        ok = self.q.add_quotation(self.admin, self.pid, "The transport cost was almost two hundred afghanis", segment_id=s["id"])
        bad = self.q.add_quotation(self.admin, self.pid, "The transport was free and easy for everyone", segment_id=s["id"])
        with self.assertRaises(QualError):
            self.q.decide_quotation(self.admin, bad["id"], "approved")
        self.q.decide_quotation(self.admin, ok["id"], "approved")
        reg = self.q.verified_register(self.admin, self.pid)
        self.assertIn(ok["id"], [x["id"] for x in reg])
        # tamper with the stored source: the register must drop the quotation
        d = self.q.get_document(self.admin, s["document_id"])
        db.execute("UPDATE qual_documents SET full_text=? WHERE id=?", (d["full_text"].replace("two hundred", "three hundred"), d["id"]))
        try:
            reg2 = self.q.verified_register(self.admin, self.pid)
            self.assertNotIn(ok["id"], [x["id"] for x in reg2])
        finally:
            db.execute("UPDATE qual_documents SET full_text=? WHERE id=?", (d["full_text"], d["id"]))

    def test_ai_coding_job_drops_invalid_references_and_rejects_fabrications(self):
        from lucerna.qual import pipeline  # noqa: F401
        from lucerna.services import jobs
        from tests import fake_llm
        with mock.patch("lucerna.ai.providers.chat_json", fake_llm.fake_chat_json):
            jid = jobs.submit("qual_ai_coding", {"project_id": self.pid, "user_id": self.admin.id}, project_id=self.pid, user_id=self.admin.id, run_inline=True)
        j = jobs.get(jid)
        self.assertEqual(j["status"], "completed", j.get("error"))
        r = j["result"]
        self.assertGreater(r["codes"], 0)
        self.assertGreater(r["invalid_segment_refs"], 0)
        self.assertGreater(r["quotes_rejected"], 0)
        self.assertGreater(r["quotes_verified"], 0)
        self.assertNotIn(fake_llm.FABRICATED, [x["verified_text"] for x in self.q.list_quotations(self.admin, self.pid, "verified")])
        self.assertTrue(all(c["status"] == "suggested" for c in self.q.list_codes(self.admin, self.pid) if c["origin"] == "ai"))
        ai_notes = [n for n in self.q.list_notes(self.admin, self.pid) if n["origin"] == "ai"]
        self.assertTrue(all(n["status"] == "draft" for n in ai_notes))

    def test_ai_failure_is_reported_not_hidden(self):
        from lucerna.ai.providers import AIError
        from lucerna.services import jobs

        def boom(*a, **k):
            raise AIError("Cannot reach Ollama at http://localhost:11434")
        with mock.patch("lucerna.ai.providers.chat_json", boom):
            jid = jobs.submit("qual_ai_coding", {"project_id": self.pid, "user_id": self.admin.id}, project_id=self.pid, user_id=self.admin.id, run_inline=True)
        j = jobs.get(jid)
        self.assertEqual(j["status"], "failed")
        self.assertIn("Ollama", j["error"])


# ============================================================ security

class TestSecurity(Base):
    def test_role_permissions_enforced_in_service_layer(self):
        from lucerna.quant import store
        from lucerna.security.rbac import PermissionDenied
        viewer = self.make_user("viewer1", "viewer")
        collector = self.make_user("collector1", "data_collector")
        data = (FIX / "SYNTHETIC_WASH_household_survey.csv").read_bytes()
        with self.assertRaises(PermissionDenied):
            store.import_file(viewer, self.pid, "x.csv", data)
        did = store.import_file(collector, self.pid, "x.csv", data)[0]
        with self.assertRaises(PermissionDenied):
            store.propose_transformation(collector, did, "drop_duplicates", {})
        with self.assertRaises(PermissionDenied):
            store.delete_dataset(collector, did)

    def test_organisation_and_project_isolation(self):
        from lucerna.quant import store
        from lucerna.security.rbac import PermissionDenied
        org_b = self.orgs.create_organization(self.admin, "SYNTHETIC Org B")
        pid_b = self.orgs.create_project(self.admin, org_b, "SYNTHETIC Project B")
        outsider = self.make_user("outsider", "project_manager", org=org_b, project=pid_b)
        self.assertNotIn(self.pid, [p["id"] for p in self.orgs.list_projects(outsider)])
        with self.assertRaises(PermissionDenied):
            store.list_datasets(outsider, self.pid)
        with self.assertRaises(PermissionDenied):
            self.orgs.get_project(outsider, self.pid)
        with self.assertRaises(Exception):
            self.orgs.set_project_member(self.admin, self.pid, outsider.id, "viewer")   # not a member of org A

    def test_login_lockout_after_repeated_failures(self):
        self.auth.create_user("locky", "Strong-Pass-2026!")
        for _ in range(5):
            with self.assertRaises(self.auth.AuthError):
                self.auth.check_password_login("locky", "wrong-password")
        with self.assertRaises(self.auth.AuthError) as cm:
            self.auth.check_password_login("locky", "Strong-Pass-2026!")
        self.assertIn("Too many failed attempts", str(cm.exception))

    def test_sessions_revocation_and_expiry(self):
        from lucerna import db
        u = self.auth.get_user("admin")
        sid = self.auth.complete_login(u)
        self.assertIsNotNone(self.auth.validate_session(sid))
        self.auth.revoke_session(sid, u["id"], "admin")
        self.assertIsNone(self.auth.validate_session(sid))
        sid2 = self.auth.complete_login(u)
        db.execute("UPDATE sessions SET expires_at=? WHERE id=?", (time.time() - 1, sid2))
        self.assertIsNone(self.auth.validate_session(sid2))

    def test_mfa_only_enabled_after_confirmation_and_disable_needs_password(self):
        from lucerna.security import mfa
        uid = self.auth.create_user("mfauser", "Mfa-User-Pass-2026!")
        secret, codes = self.auth.begin_mfa_enrolment()
        self.assertIsNone(self.auth.get_user_by_id(uid)["mfa_secret"])
        with self.assertRaises(self.auth.AuthError):
            self.auth.confirm_mfa_enrolment(uid, secret, codes, "000000")
        self.assertIsNone(self.auth.get_user_by_id(uid)["mfa_secret"])
        self.auth.confirm_mfa_enrolment(uid, secret, codes, mfa.totp(secret))
        row = self.auth.get_user_by_id(uid)
        self.assertTrue(row["mfa_secret"])
        self.assertTrue(self.auth.verify_second_factor(row, codes[0]))
        self.assertFalse(self.auth.verify_second_factor(self.auth.get_user_by_id(uid), codes[0]))   # single use
        with self.assertRaises(self.auth.AuthError):
            self.auth.disable_mfa(uid, "wrong")

    def test_weak_passwords_rejected(self):
        with self.assertRaises(self.auth.AuthError):
            self.auth.create_user("weak", "password")

    def test_upload_restrictions(self):
        from lucerna.services.files import QUANT_EXT, UploadRejected, validate_upload
        with self.assertRaises(UploadRejected):
            validate_upload("evil.exe", b"MZ\x90\x00", QUANT_EXT)
        with self.assertRaises(UploadRejected):
            validate_upload("fake.xlsx", b"MZ\x90\x00this is not a zip", QUANT_EXT)
        with self.assertRaises(UploadRejected):
            validate_upload("script.csv", b"#!/bin/sh\nrm -rf /", QUANT_EXT)
        with mock.patch.object(__import__("lucerna.config", fromlist=["x"]).settings(), "max_upload_mb", 0):
            with self.assertRaises(UploadRejected):
                validate_upload("big.csv", b"a,b\n1,2\n", QUANT_EXT)

    def test_external_ai_blocked_by_default(self):
        from lucerna.ai import providers
        pid = providers.save_provider(self.admin, name="External test", kind="openai_compatible", base_url="https://api.example.org/v1", model="m")
        with self.assertRaises(providers.PrivacyBlocked) as cm:
            providers.resolve("Internal", pid)
        msg = str(cm.exception)
        self.assertIn("NOT sent", msg)
        self.assertIn("LUCERNA_EXTERNAL_AI_ENABLED", msg)
        with self.assertRaises(providers.AIError):
            providers.save_provider(self.admin, name="Plain http", kind="openai_compatible", base_url="http://api.example.org/v1", model="m")

    def test_external_ai_restricted_project_always_blocked(self):
        from lucerna import config
        from lucerna.ai import providers
        from lucerna.services import bootstrap
        pid = providers.save_provider(self.admin, name="External approved", kind="openai_compatible", base_url="https://api.example.org/v1", model="m")
        providers.approve_external(self.admin, pid, "Reviewed retention and training-exclusion terms on 2026-11-20 by DPO; approved.")
        bootstrap.set_setting("privacy.external_ai_allowed", "1", "admin")
        with mock.patch.object(config.settings(), "external_ai_enabled", True):
            self.assertEqual(providers.resolve("Internal", pid).name, "External approved")
            with self.assertRaises(providers.PrivacyBlocked):
                providers.resolve("Restricted", pid)
        bootstrap.set_setting("privacy.external_ai_allowed", "0", "admin")

    def test_permission_denials_are_audited(self):
        from lucerna.quant import store
        from lucerna.security import audit
        from lucerna.security.rbac import PermissionDenied
        v = self.make_user("viewer2", "viewer")
        with self.assertRaises(PermissionDenied):
            store.save_indicator(v, self.pid, {"name": "x", "indicator_type": "count"})
        self.assertTrue(any(r["action"] == "PERMISSION_DENIED" and r["username"] == "viewer2" for r in audit.recent(50)))


# ============================================================ reports

class TestReports(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from lucerna.qual import store as q
        from lucerna.quant import store
        cls.did = store.import_file(cls.admin, cls.pid, "SYNTHETIC_PDM_cash_round1.xlsx", (FIX / "SYNTHETIC_PDM_cash_round1.xlsx").read_bytes())[0]
        store.update_mapping(cls.admin, cls.did, {}, confirm_all=True)
        doc = q.import_document(cls.admin, cls.pid, "SYNTHETIC_FGD_women_Herat.txt", (FIX / "SYNTHETIC_FGD_women_Herat.txt").read_bytes())
        seg = next(s for s in q.segments(cls.admin, doc) if "Nobody told us about a hotline" in s["text"])
        cid = q.find_or_create_code(cls.admin, cls.pid, "Information gaps")
        q.apply_code(cls.admin, cid, seg["id"])
        cls.tid = q.save_theme(cls.admin, cls.pid, "Accountability gaps", "SYNTHETIC theme", [cid])
        ok = q.add_quotation(cls.admin, cls.pid, "Nobody told us about a hotline.", segment_id=seg["id"], theme_id=cls.tid)
        q.decide_quotation(cls.admin, ok["id"], "approved")
        cls.pending = q.add_quotation(cls.admin, cls.pid, "If there is a number, we do not know it.", segment_id=seg["id"], theme_id=cls.tid)
        q.add_quotation(cls.admin, cls.pid, "The hawala agent stole part of our money", segment_id=seg["id"], theme_id=cls.tid)

    def _docx_text(self, path) -> str:
        import docx
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)

    def test_quantitative_report_all_formats_and_draft_label(self):
        from lucerna.reports import service
        rid = service.create(self.admin, self.pid, "quantitative", "SYNTHETIC PDM report", {"dataset_id": self.did})
        res = service.generate_version(self.admin, rid, "test")
        for fmt in ("docx", "pdf", "xlsx"):
            p = Path(res["paths"][fmt])
            self.assertTrue(p.exists() and p.stat().st_size > 5000, fmt)
        text = self._docx_text(res["paths"]["docx"])
        self.assertIn("DRAFT", text)
        self.assertIn("Not provided", text)
        self.assertTrue(Path(res["paths"]["pdf"]).read_bytes().startswith(b"%PDF"))

    def test_approval_requires_review_steps(self):
        from lucerna.reports import service
        rid = service.create(self.admin, self.pid, "quantitative", "SYNTHETIC approval test", {"dataset_id": self.did})
        service.generate_version(self.admin, rid, formats=("docx",))
        with self.assertRaises(service.ReportError):
            service.approve(self.admin, rid)
        for s in service.REVIEW_STEPS["quantitative"]:
            service.record_review(self.admin, rid, s, "completed", "checked")
        res = service.approve(self.admin, rid)
        self.assertEqual(service.get(self.admin, rid)["status"], "approved")
        self.assertNotIn("DRAFT — not yet approved", self._docx_text(res["paths"]["docx"]))
        service.update_metadata(self.admin, rid, {"dataset_id": self.did, "purpose": "edited"})
        self.assertEqual(service.get(self.admin, rid)["status"], "draft")

    def test_viewer_cannot_approve(self):
        from lucerna.reports import service
        from lucerna.security.rbac import PermissionDenied
        v = self.make_user("viewer_r", "analyst")
        rid = service.create(self.admin, self.pid, "quantitative", "SYNTHETIC perms", {"dataset_id": self.did})
        with self.assertRaises(PermissionDenied):
            service.approve(v, rid)

    def test_qualitative_report_uses_only_approved_verified_quotes(self):
        from lucerna.reports import service
        rid = service.create(self.admin, self.pid, "qualitative", "SYNTHETIC qual report", {})
        res = service.generate_version(self.admin, rid, formats=("docx", "pdf"))
        text = self._docx_text(res["paths"]["docx"])
        self.assertIn("Nobody told us about a hotline.", text)
        self.assertNotIn("hawala agent stole", text)
        self.assertNotIn("If there is a number, we do not know it.", text)   # verified but not approved
        self.assertIn("Not provided", text)

    def test_mixed_report_builds(self):
        from lucerna.reports import service
        from lucerna.services import mixed
        mixed.add_link(self.admin, self.pid, indicator_id=None, theme_id=self.tid, relationship="explains",
                       quant_statement="SYNTHETIC: 40% of households (n=412) did not know how to complain.", integrated_finding="SYNTHETIC finding")
        rid = service.create(self.admin, self.pid, "mixed", "SYNTHETIC brief", {})
        res = service.generate_version(self.admin, rid, formats=("docx",))
        self.assertTrue(Path(res["paths"]["docx"]).exists())

    def test_version_compare(self):
        from lucerna.reports import service
        rid = service.create(self.admin, self.pid, "quantitative", "SYNTHETIC compare", {"dataset_id": self.did})
        service.generate_version(self.admin, rid, formats=("docx",))
        service.update_metadata(self.admin, rid, {"dataset_id": self.did, "background": "A new purpose statement"})
        service.generate_version(self.admin, rid, formats=("docx",))
        vs = service.versions(self.admin, rid)
        diff = service.compare_versions(self.admin, vs[1]["id"], vs[0]["id"])
        self.assertIn("A new purpose statement", diff)

    def test_backup_contains_database(self):
        from lucerna.services import backup
        p = backup.create_backup("admin")
        z = zipfile.ZipFile(p)
        self.assertIn("database/lucerna.sqlite3", z.namelist())


if __name__ == "__main__":
    unittest.main()
