"""Quantitative report builder: real computed results only."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from ..config import settings
from ..quant import charts, compare, counting, dashboards, insights, planner, store
from ..quant.transform import OPERATIONS
from ..security.rbac import CurrentUser
from ..services import orgs
from . import model as M
from . import narrative, static_charts

TEMPLATES = {
    "pdm": "Post-Distribution Monitoring (PDM) report", "cash": "Cash & MPCA monitoring report", "wash": "WASH assessment report",
    "food_security": "Food security assessment report", "needs": "Needs assessment report", "baseline_endline": "Baseline / endline comparison report",
    "returnee": "Returnee & flow monitoring report", "programme": "Programme monitoring report", "indicators": "Indicator performance report",
    "general": "Analytical report",
}
SECTOR_TEMPLATE = {"PDM / Cash & Voucher Assistance": "pdm", "WASH": "wash", "Food Security": "food_security", "Returnee / Flow Monitoring": "returnee",
                   "Baseline / Endline": "baseline_endline"}


def _visual_blocks(df, v, workdir: Path) -> list[dict]:
    try:
        data = charts.compute(df, v)
    except charts.Unsupported as exc:
        return [M.callout(f"{v.get('title')}: not shown — {exc}", "warning")]
    if v["type"] in ("kpi", "text"):
        return []
    if v["type"] in ("stat_summary", "table"):
        t = data.table
        return [M.table(list(map(str, t.columns)), t.round(2).values.tolist(), v.get("title"))]
    png = workdir / f"{v['id']}.png"
    path = static_charts.render(v, data, str(png))
    if not path:
        return []
    cap = f"Figure: {v.get('title')}."
    if data.base_n is not None:
        cap += f" Base: n = {data.base_n:,}."
    if data.notes:
        cap += " " + " ".join(data.notes)
    return [M.chart(path, cap)]


def build(user: CurrentUser, dataset_id: int, metadata: dict, *, template: str | None = None, dashboard_id: int | None = None,
          compare_dataset_id: int | None = None, include_ai_narrative: bool = False, indicator_ids: list[int] | None = None) -> dict:
    ds = store.get_dataset(user, dataset_id)
    proj = orgs.get_project(user, ds["project_id"])
    df = store.analytic_frame(user, dataset_id)
    mp = store.mapping(dataset_id)
    sector = ds.get("sector_confirmed") or ds.get("sector_guess")
    template = template or SECTOR_TEMPLATE.get(sector, "general")
    res = planner.make_plan(df, mp, unit=ds.get("unit_of_analysis") or "unknown", sector=sector, unit_confirmed=bool(ds.get("unit_confirmed")))
    plan, spec = res["plan"], res["spec"]
    if dashboard_id:
        spec = dashboards.get(user, dashboard_id)["spec"]
    workdir = Path(tempfile.mkdtemp(prefix="lucerna_rep_", dir=settings().temp_dir))
    md = lambda k: M.not_provided(metadata.get(k))
    unit_label = plan["unit_label"]
    secs = []

    # 1 executive summary
    ins = insights.generate(df, plan, limit=6)
    exec_blocks = []
    if metadata.get("executive_summary"):
        exec_blocks.append(M.p(metadata["executive_summary"], "analyst"))
    exec_blocks.append(M.p(f"This report analyses {len(df):,} {unit_label} from the dataset '{ds['name']}'"
                           + (f" covering {plan['feasibility']['temporal']['reason'].split(' between ')[-1].rstrip('.')}" if plan["feasibility"].get("temporal", {}).get("possible") else "")
                           + ". All figures are calculated deterministically from the uploaded data after the documented cleaning steps.", "computed"))
    if ins:
        exec_blocks.append(M.bullets([i["text"] for i in ins]))
    if include_ai_narrative and ins:
        para, err = narrative.guarded_paragraph("Executive summary", [i["text"] for i in ins], project_id=proj["id"], classification=proj.get("classification"))
        exec_blocks.append(M.p(para, "ai_draft") if para else M.callout(err, "warning"))
    secs.append(M.section("executive_summary", "Executive Summary", exec_blocks))
    secs.append(M.section("background", "Background and Context", [M.p(md("background"), "metadata")]))
    secs.append(M.section("objectives", "Objectives", [M.p(md("objectives"), "metadata")]))

    # methodology
    trans = [t for t in store.transformations(dataset_id) if t["status"] == "applied"]
    meth = [M.kv([["Data collection method", md("data_collection")], ["Sampling approach", md("sampling")], ["Sample size (planned)", md("sample_size")],
                  ["Data collection period", md("period")], ["Geographic coverage", md("geography") if metadata.get("geography") else M.not_provided(proj.get("geography"))],
                  ["Unit of analysis", f"{ds.get('unit_of_analysis')} ({'confirmed' if ds.get('unit_confirmed') else 'NOT confirmed by an analyst'})"],
                  ["Weighting", md("weighting")], ["Ethics and consent", md("ethics")]]),
            M.p("Analysis was performed in Lucerna using deterministic statistical routines (pandas, NumPy, SciPy, statsmodels). Percentages use the number "
                "of valid (non-missing) responses as the denominator unless stated otherwise. Confidence intervals, where shown, are Wilson score intervals "
                "assuming simple random sampling; they do not account for clustering or weighting unless weighting is stated above.", "computed")]
    if trans:
        meth.append(M.table(["#", "Cleaning / transformation step", "Rows affected", "Cells affected"],
                            [[t["seq"], t["description"], t.get("rows_affected"), t.get("cells_affected")] for t in trans], "Approved data transformations applied to the analytical copy (the original upload is unchanged)."))
    else:
        meth.append(M.p("No cleaning transformations were applied; the analysis uses the uploaded values after type conversion.", "computed"))
    secs.append(M.section("methodology", "Methodology", meth))

    # dataset overview
    ids = [c for c, m in mp.items() if m.get("role") == "identifier" and c in df]
    hh = next((c for c in ids if "hh" in c.lower() or "household" in c.lower()), None)
    hs = next((c for c, m in mp.items() if m.get("role") == "household_size" and c in df), None)
    cs = counting.count_summary(df, ds.get("unit_of_analysis") or "unknown", ids[0] if ids else None, hh, hs)
    rows = [[k.replace("_", " ").capitalize(), f"{v['value']:,}", v["unit"], v["rule"]] for k, v in cs.items() if k != "notes"]
    ov = [M.table(["Count", "Value", "Unit", "Counting rule"], rows, "Different units are never added together.")]
    if cs["notes"]:
        ov.append(M.bullets(cs["notes"]))
    ov.append(M.p(f"Sector (as {'confirmed' if ds.get('sector_confirmed') else 'detected, not confirmed'}): {sector or 'not determined'}. "
                  f"Source file: {ds['name']} ({ds['column_count']} variables).", "computed"))
    secs.append(M.section("dataset", "Dataset Overview", ov))

    # data quality
    q = store.run_quality(user, dataset_id)
    qb = [M.p(f"Overall completeness is {q['completeness_pct']:.1f}% of cells. {q['duplicate_rows']} fully duplicated record(s) remain in the analytical copy.", "computed")]
    if q["findings"]:
        qb.append(M.table(["Severity", "Variable", "Finding"], [[f["severity"], f.get("column") or "—", f["message"]] for f in q["findings"][:30]], "Automated data-quality checks on the analytical copy."))
    secs.append(M.section("data_quality", "Data Quality", qb))

    # indicators
    inds = [i for i in store.list_indicators(user, proj["id"]) if i.get("dataset_id") == dataset_id and (not indicator_ids or i["id"] in indicator_ids)]
    ib = []
    if inds:
        rows = []
        for ind in inds:
            try:
                r = store.compute_indicator(user, ind["id"])
                val = r.get("value")
                rows.append([ind.get("code") or "", ind["name"], ind["status"], (f"{val:.1f}%" if ind["indicator_type"] == "percentage" and val is not None else (f"{val:,.2f}" if isinstance(val, float) else val)),
                             r.get("numerator") if r.get("numerator") is not None else "—", r.get("denominator") if r.get("denominator") is not None else "—",
                             ind.get("baseline") if ind.get("baseline") is not None else "Not configured", ind.get("target") if ind.get("target") is not None else "Not configured"])
            except Exception as exc:
                rows.append([ind.get("code") or "", ind["name"], ind["status"], f"Not computable: {exc}", "", "", "", ""])
        ib.append(M.table(["Code", "Indicator", "Status", "Actual", "Numerator", "Denominator", "Baseline", "Target"], rows,
                          "Actual values are computed from the data. Baselines and targets are shown only where configured by the project team; provisional indicators are not yet fully defined."))
    else:
        ib.append(M.p("No indicators have been configured for this dataset. Indicator definitions (numerator, denominator, targets) must be configured in Indicator Management; Lucerna does not invent them.", "computed"))
    secs.append(M.section("indicators", "Indicator Results", ib))

    # analytic pages from the dashboard spec
    page_map = {"demographics": "Demographic Analysis", "geography": "Geographic Analysis", "trends": "Temporal Analysis", "flows": "Flows and Movements"}
    finding_pages = []
    for page in spec["pages"]:
        if page["key"] in ("overview", "quality"):
            continue
        blocks = [M.p(page.get("purpose") or "", "computed")] if page.get("purpose") else []
        for v in page["visuals"]:
            blocks += _visual_blocks(df, v, workdir)
        if any(b["kind"] in ("chart", "table") for b in blocks):
            if page["key"] in page_map:
                secs.append(M.section(page["key"], page_map[page["key"]], blocks))
            else:
                finding_pages.append(M.section(page["key"], page["title"], blocks, level=2))

    # comparison
    if compare_dataset_id:
        ds2 = store.get_dataset(user, compare_dataset_id)
        df2 = store.analytic_frame(user, compare_dataset_id)
        comp = compare.compatibility(df, df2, mp, store.mapping(compare_dataset_id), ds, ds2)
        cb = [M.p(f"Comparison of '{ds['name']}' (A) with '{ds2['name']}' (B).", "computed")]
        if comp["issues"]:
            cb.append(M.callout("Comparison not valid: " + " ".join(comp["issues"]), "warning"))
        else:
            if comp["warnings"]:
                cb.append(M.bullets(comp["warnings"]))
            bins = [c for c in comp["comparable_columns"] if mp.get(c, {}).get("type") == "boolean"]
            nums = [c for c in comp["comparable_columns"] if mp.get(c, {}).get("type") in ("numeric", "integer") and mp[c].get("role") == "measure"]
            if bins:
                t = pd.concat([compare.compare_binary(df, df2, c, "A", "B") for c in bins])
                cb.append(M.table(["Indicator", "A %", "A n", "B %", "B n", "Change (pp)", "p-value"],
                                  [[r["indicator"], r["A %"], r["A n"], r["B %"], r["B n"], r["change (pp)"], r["p-value"]] for _, r in t.iterrows()],
                                  "Two-proportion z-tests assume independent samples."))
            if nums:
                rr = [compare.compare_numeric(df, df2, c, "A", "B") for c in nums]
                cb.append(M.table(["Variable", "A mean", "B mean", "A n", "B n", "Welch p-value"],
                                  [[r["indicator"], r["A mean"], r["B mean"], r["A n"], r["B n"], r.get("Welch t p-value")] for r in rr], rr[0]["note"]))
        secs.append(M.section("comparison", "Comparative Analysis", cb))

    secs.append(M.section("findings", "Detailed Findings", [M.p("Findings are grouped by theme. Each figure states its base (n).", "computed")]
                          + ([M.bullets([i["text"] for i in ins])] if ins else [])))
    secs += finding_pages
    secs.append(M.section("interpretation", "Interpretation", [M.p(md("interpretation"), "analyst")]))
    secs.append(M.section("conclusions", "Conclusions", [M.p(md("conclusions"), "analyst")]))
    recs = [r for r in (metadata.get("recommendations") or []) if r.get("action")]
    if recs:
        rb = [M.table(["Priority", "Recommended action", "Supporting finding", "Responsible (as entered)", "Follow-up"],
                      [[r.get("priority", ""), r["action"], r.get("finding", ""), r.get("stakeholder") or "Not assigned", r.get("follow_up", "")] for r in recs])]
    else:
        rb = [M.p("No recommendations have been entered by the analysis team. Lucerna does not generate recommendations automatically from quantitative results.", "computed")]
    secs.append(M.section("recommendations", "Recommendations", rb))
    lims = plan["limitations"] + ([metadata["limitations"]] if metadata.get("limitations") else [])
    secs.append(M.section("limitations", "Limitations", [M.bullets(lims or ["No limitations recorded."]),
                                                         M.p("Statistical associations reported here do not establish causation.", "computed")]))
    dd = [[c, m.get("type"), m.get("role"), "yes" if m.get("confirmed") else "no", f"{100 * df[c].isna().mean():.1f}%" if c in df else "—"] for c, m in mp.items()]
    secs.append(M.section("annex_dictionary", "Annex: Data Dictionary and Calculation Notes",
                          [M.table(["Variable", "Type", "Role", "Mapping confirmed", "Missing"], dd),
                           M.bullets([f"{name}: {desc}" for name, (_, desc) in OPERATIONS.items() if any(t['operation'] == name for t in trans)] or ["No transformations applied."])]))
    approved = metadata.get("_approved", False)
    return {"title": metadata.get("title") or f"{TEMPLATES.get(template, 'Analytical report')}: {proj['name']}", "subtitle": metadata.get("subtitle") or ds["name"],
            "template": template,
            "meta": {"organization": proj.get("org_name"), "Project": proj["name"], "Geographic coverage": metadata.get("geography") or proj.get("geography") or "Not provided",
                     "Reporting period": metadata.get("period") or "Not provided", "Report date": date.today().isoformat(), "Prepared by": metadata.get("authors") or "Not provided",
                     "Confidentiality": metadata.get("classification") or proj.get("classification") or "Restricted",
                     "Report status": "Approved" if approved else "DRAFT — not yet approved",
                     "status_note": None if approved else "This is a draft generated from the data. It has not completed human review and approval."},
            "brand": {"primary": proj.get("brand_primary") or "#173B68", "accent": proj.get("brand_accent") or "#18B6A4", "logo_path": proj.get("logo_path")},
            "sections": secs, "source": {"dataset_id": dataset_id, "dataset_version": ds["version"], "compare_dataset_id": compare_dataset_id}}
