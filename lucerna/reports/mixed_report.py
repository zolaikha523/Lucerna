"""Mixed-methods brief: integrated findings from approved evidence links only."""
from __future__ import annotations

from datetime import date

from ..qual import store as qstore
from ..services import mixed, orgs
from . import model as M
from .qual_report import source_label


def build(user, project_id: int, metadata: dict) -> dict:
    proj = orgs.get_project(user, project_id)
    links = mixed.list_links(user, project_id, approved_only=True)
    secs = [M.section("intro", "Purpose and Approach", [
        M.p(metadata.get("purpose") or "Not provided", "metadata"),
        M.p("Quantitative results were computed from survey/monitoring data; qualitative findings come from analyst-approved themes. Each integrated finding "
            "below links one computed result to one theme with an explicit relationship. The two evidence streams are not assumed to involve the same people.", "computed")])]
    if not links:
        secs.append(M.section("findings", "Integrated Findings", [M.callout("No approved evidence links. Create and approve links in Mixed-Methods Intelligence.", "warning")]))
    for i, l in enumerate(links, 1):
        blocks = [M.kv([["Quantitative result", l["quant_statement"]], ["Qualitative theme", l["theme_name"]],
                        ["Relationship", mixed.RELATIONSHIPS[l["relationship"]]]]),
                  M.p(l["integrated_finding"], "analyst")]
        if l.get("analyst_note"):
            blocks.append(M.p(l["analyst_note"], "analyst"))
        for q in qstore.quotes_for_theme(user, l["theme_id"])[:2]:
            blocks.append(M.quote(q["verified_text"], source_label(q)))
        secs.append(M.section(f"link_{l['id']}", f"{i}. {l['theme_name']}", blocks, level=2))
    contra = [l for l in links if l["relationship"] == "contradicts"]
    if contra:
        secs.append(M.section("divergence", "Where the Evidence Diverges", [M.bullets([f"{l['quant_statement']} — vs. theme '{l['theme_name']}'" for l in contra])]))
    return {"title": metadata.get("title") or f"Mixed-Methods Brief: {proj['name']}", "subtitle": "Integrated quantitative and qualitative findings",
            "meta": {"organization": proj.get("org_name"), "Project": proj["name"], "Report date": date.today().isoformat(),
                     "Prepared by": metadata.get("authors") or "Not provided", "Confidentiality": proj.get("classification") or "Restricted",
                     "Report status": "Approved" if metadata.get("_approved") else "DRAFT — not yet approved"},
            "brand": {"primary": proj.get("brand_primary") or "#173B68", "accent": proj.get("brand_accent") or "#18B6A4"}, "sections": secs, "template": "mixed"}
