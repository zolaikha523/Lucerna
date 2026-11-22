"""Create a demo workspace filled with SYNTHETIC data (for testing and UI walkthroughs).

    python -m tests.seed_demo            # uses LUCERNA_DB / LUCERNA_DATA_DIR from the environment

Everything created here is fictional and labelled SYNTHETIC. The AI steps use tests/fake_llm.py,
a deterministic keyword stand-in, never a real model.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lucerna import db  # noqa: E402
from lucerna.qual import pipeline, store as qstore  # noqa: E402
from lucerna.quant import dashboards, store  # noqa: E402
from lucerna.reports import service as reports  # noqa: E402
from lucerna.security import auth  # noqa: E402
from lucerna.services import jobs, mixed, orgs  # noqa: E402
from tests import fake_llm, synthetic_data  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
ADMIN = ("admin", "Lucerna-Demo-2026!")


def seed(verbose: bool = True) -> dict:
    db.init()
    synthetic_data.write_all()
    log = print if verbose else (lambda *a, **k: None)
    if auth.user_count() == 0:
        uid = auth.create_user(ADMIN[0], ADMIN[1], full_name="Demo Administrator", system_role="system_admin")
    else:
        uid = auth.get_user(ADMIN[0])["id"]
    u = auth.to_current(auth.get_user_by_id(uid))
    oid = orgs.create_organization(u, "SYNTHETIC Relief Organisation", "SRO")
    orgs.add_org_member(u, oid, uid, "org_admin")
    pid = orgs.create_project(u, oid, "SYNTHETIC Cash & WASH Response 2026", sector="Multi-sector", geography="Herat and Nangarhar (fictional data)",
                              description="Demo project using fictional, synthetic data only.", classification="Restricted")
    out = {"user": u, "org_id": oid, "project_id": pid, "datasets": {}, "dashboards": {}}
    for f in ["SYNTHETIC_PDM_cash_round1.xlsx", "SYNTHETIC_WASH_household_survey.csv", "SYNTHETIC_returnee_flow_monitoring.csv",
              "SYNTHETIC_food_security.xlsx", "SYNTHETIC_baseline.csv", "SYNTHETIC_endline.csv", "SYNTHETIC_feedback_records.jsonl"]:
        rnd = "Baseline" if "baseline" in f else ("Endline" if "endline" in f else "")
        ids = store.import_file(u, pid, f, (FIX / f).read_bytes(), round_label=rnd)
        for i in ids:
            d = store.get_dataset(u, i)
            store.update_mapping(u, i, {}, confirm_all=True, unit_of_analysis=d.get("unit_of_analysis") or "household")
            out["datasets"][f] = i
            out["dashboards"][f] = dashboards.generate_auto(u, i)
        log(f"dataset {f}: {ids}")
    # Multi-sheet displacement-tracking workbook (synthetic; same shape as a DTM practice workbook)
    from tests import dtm_workbook
    from lucerna.quant import generator
    wb_ids = store.import_file(u, pid, "SYNTHETIC_DTM_practice_workbook.xlsx", dtm_workbook.build())
    out["datasets"]["SYNTHETIC_DTM_practice_workbook.xlsx"] = wb_ids[0]
    out["dashboards"]["SYNTHETIC_DTM_practice_workbook.xlsx"] = generator.generate(
        u, wb_ids[0], theme="executive", branding={"title": "Mobility & Displacement Analysis (synthetic data)", "subtitle": "", "show_org": True, "logo": "org"})
    log(f"workbook: {len(wb_ids)} sheets; primary dataset {wb_ids[0]}")
    pdm = out["datasets"]["SYNTHETIC_PDM_cash_round1.xlsx"]
    q = store.run_quality(u, pdm)
    for pr in q["proposals"]:
        tid = store.propose_transformation(u, pdm, pr["operation"], pr["params"], pr["description"])
        store.decide_transformation(u, tid, True)
    df = store.analytic_frame(u, pdm)
    bcol = next((c for c in df.columns if str(df[c].dtype) == "boolean"), None)
    if bcol:
        out["indicator_id"] = store.save_indicator(u, pid, {"code": "1.1", "name": f"% of households: {bcol}", "indicator_type": "percentage",
                                                            "definition": f"Share of households with a valid answer reporting {bcol} = yes.",
                                                            "numerator": {"column": bcol, "op": "in", "value": ["yes"]}, "dataset_id": pdm})
    for f in ["SYNTHETIC_FGD_women_Herat.txt", "SYNTHETIC_FGD_men_Nangarhar.txt", "SYNTHETIC_KII_community_leader.txt"]:
        qstore.import_document(u, pid, f, (FIX / f).read_bytes())
    with mock.patch("lucerna.ai.providers.chat_json", fake_llm.fake_chat_json):
        out["coding_job"] = jobs.submit("qual_ai_coding", {"project_id": pid, "user_id": uid}, project_id=pid, user_id=uid, run_inline=True)
    j = jobs.get(out["coding_job"])
    log("coding job:", j["status"], j.get("result") or j.get("error"))
    for c in qstore.list_codes(u, pid):
        qstore.review_code(u, c["id"], True)
    for t in qstore.list_themes(u, pid):
        qstore.review_theme(u, t["id"], True)
    for qq in qstore.list_quotations(u, pid, "verified")[:8]:
        qstore.decide_quotation(u, qq["id"], "approved")
    ths = qstore.list_themes(u, pid)
    if ths and out.get("indicator_id"):
        mixed.add_link(u, pid, indicator_id=out["indicator_id"], theme_id=ths[0]["id"], relationship="explains",
                       quant_statement="SYNTHETIC: see indicator 1.1 result.", integrated_finding="")
    out["report_quant"] = reports.create(u, pid, "quantitative", "SYNTHETIC PDM report", {"dataset_id": pdm})
    out["report_qual"] = reports.create(u, pid, "qualitative", "SYNTHETIC qualitative assessment", {})
    log("seeded project", pid)
    return out


if __name__ == "__main__":
    seed()
