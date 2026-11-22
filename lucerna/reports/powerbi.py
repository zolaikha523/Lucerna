"""Power BI interoperability package (ZIP).

Contains a star schema (fact + dimension CSVs), a date table, a data dictionary, Power Query (M)
scripts, DAX measures for configured indicators, relationship definitions, a Lucerna theme JSON,
dashboard page specifications and refresh / RLS guidance.

IMPORTANT: this is NOT a .pbix file. Lucerna does not generate PBIX files because there is no
supported, reliable public method to author them outside Power BI Desktop. Open Power BI Desktop,
run the M scripts (or Get Data → Text/CSV) and paste the DAX measures — see README_POWERBI.md.
"""
from __future__ import annotations

import io
import json
import re
import zipfile

import pandas as pd

from ..quant import dashboards, store
from ..quant.palette import CATEGORICAL
from ..security import audit
from ..security.rbac import CurrentUser, require
from .exports import protect


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "col"


def _dax_condition(cond: dict, table: str) -> str:
    col = f"'{table}'[{cond['column']}]"
    op, val = cond.get("op"), cond.get("value")
    if op in ("in", "not_in"):
        vals = val if isinstance(val, list) else [val]
        items = ", ".join(f'"{v}"' for v in vals)
        expr = f"LOWER({col}) IN {{{items.lower()}}}"
        return expr if op == "in" else f"NOT({expr})"
    if op == "notnull":
        return f"NOT ISBLANK({col})"
    if op in ("==", "!=", ">", ">=", "<", "<="):
        dop = {"==": "=", "!=": "<>"}.get(op, op)
        v = val if isinstance(val, (int, float)) else f'"{val}"'
        return f"{col} {dop} {v}"
    return "TRUE()"


def build_package(user: CurrentUser, dataset_id: int, dashboard_id: int | None = None) -> bytes:
    ds = store.get_dataset(user, dataset_id)
    require(user, "export", ds["project_id"])
    mp = store.mapping(dataset_id)
    df, notes = protect(store.analytic_frame(user, dataset_id), mp, ds["project_id"])
    fact = "Fact_" + _safe(ds["name"])[:40]
    df = df.copy()
    df.insert(0, "lucerna_row_id", range(1, len(df) + 1))
    dims = {}
    for c, m in mp.items():
        if c in df and m.get("role") in ("geo_admin1", "geo_admin2", "geo_admin3", "sex", "age_group", "round", "geo_origin", "geo_destination"):
            vals = sorted(df[c].dropna().astype(str).unique())
            dims[c] = pd.DataFrame({c: vals})
    date_cols = [c for c, m in mp.items() if m.get("type") == "date" and c in df]
    date_table = None
    if date_cols:
        d = pd.to_datetime(df[date_cols[0]], errors="coerce").dropna()
        if len(d):
            rng = pd.date_range(d.min().normalize(), d.max().normalize(), freq="D")
            date_table = pd.DataFrame({"Date": rng, "Year": rng.year, "Quarter": "Q" + rng.quarter.astype(str), "MonthNumber": rng.month,
                                       "Month": rng.strftime("%b"), "YearMonth": rng.strftime("%Y-%m"), "WeekStart": (rng - pd.to_timedelta(rng.weekday, unit="D")).date})
            df[date_cols[0]] = pd.to_datetime(df[date_cols[0]], errors="coerce").dt.date
    inds = [i for i in store.list_indicators(user, ds["project_id"]) if i.get("dataset_id") == dataset_id]
    measures = [f"Records = COUNTROWS('{fact}')"]
    for i in inds:
        nm = (i.get("code") or "") + " " + i["name"]
        nm = nm.strip().replace("]", ")")
        if i["indicator_type"] == "percentage" and i.get("numerator"):
            num = i["numerator"]
            denom = i.get("denominator")
            base = f"NOT ISBLANK('{fact}'[{num['column']}])" + (f" && {_dax_condition(denom, fact)}" if denom else "")
            measures.append(f"[{nm}] = DIVIDE(CALCULATE(COUNTROWS('{fact}'), FILTER('{fact}', {base} && {_dax_condition(num, fact)})), "
                            f"CALCULATE(COUNTROWS('{fact}'), FILTER('{fact}', {base})))")
        elif i["indicator_type"] in ("mean", "median", "sum") and i.get("value_column"):
            fn = {"mean": "AVERAGE", "median": "MEDIAN", "sum": "SUM"}[i["indicator_type"]]
            measures.append(f"[{nm}] = {fn}('{fact}'[{i['value_column']}])")
        elif i["indicator_type"] == "count_unique" and i.get("value_column"):
            measures.append(f"[{nm}] = DISTINCTCOUNT('{fact}'[{i['value_column']}])")
        elif i["indicator_type"] == "count" and i.get("numerator"):
            measures.append(f"[{nm}] = CALCULATE(COUNTROWS('{fact}'), FILTER('{fact}', {_dax_condition(i['numerator'], fact)}))")
        if i.get("target") is not None:
            measures.append(f"[{nm} — Target] = {i['target']}  // configured target (source: {i.get('target_source') or 'not recorded'})")
    rels = [{"from": f"{fact}[{c}]", "to": f"Dim_{_safe(c)}[{c}]", "cardinality": "many-to-one", "crossFilter": "single"} for c in dims]
    if date_table is not None:
        rels.append({"from": f"{fact}[{date_cols[0]}]", "to": "Dim_Date[Date]", "cardinality": "many-to-one", "crossFilter": "single"})
    dictionary = pd.DataFrame([{"column": c, "type": m.get("type"), "role": m.get("role"), "label": m.get("label") or "", "mapping_confirmed": m.get("confirmed"),
                                "missing_pct": round(100 * df[c].isna().mean(), 2) if c in df else None} for c, m in mp.items() if c in df])
    theme = {"name": "Lucerna", "dataColors": CATEGORICAL["light"], "background": "#FFFFFF", "foreground": "#101B2D", "tableAccent": "#173B68",
             "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "color": "#101B2D"}, "label": {"fontFace": "Segoe UI", "color": "#4B5563"}}}

    def m_script(table: str, file: str, date_col: str | None = None) -> str:
        typ = f',\n    Typed = Table.TransformColumnTypes(Promoted, {{{{"{date_col}", type date}}}})' if date_col else ""
        last = "Typed" if date_col else "Promoted"
        return (f"// {table}\nlet\n    FolderPath = \"C:\\\\Lucerna\\\\PowerBI\\\\\",  // change to the folder where you extracted this package\n"
                f"    Source = Csv.Document(File.Contents(FolderPath & \"{file}\"), [Delimiter=\",\", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n"
                f"    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]){typ}\nin\n    {last}\n")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{fact}.csv", df.to_csv(index=False))
        scripts = [m_script(fact, f"{fact}.csv", date_cols[0] if date_cols else None)]
        for c, t in dims.items():
            z.writestr(f"Dim_{_safe(c)}.csv", t.to_csv(index=False))
            scripts.append(m_script(f"Dim_{_safe(c)}", f"Dim_{_safe(c)}.csv"))
        if date_table is not None:
            z.writestr("Dim_Date.csv", date_table.to_csv(index=False))
            scripts.append(m_script("Dim_Date", "Dim_Date.csv", "Date"))
        z.writestr("data_dictionary.csv", dictionary.to_csv(index=False))
        z.writestr("power_query_M_scripts.pq", "\n\n".join(scripts))
        z.writestr("dax_measures.dax", "\n\n".join(measures) + "\n")
        z.writestr("relationships.json", json.dumps(rels, indent=2))
        z.writestr("lucerna_theme.json", json.dumps(theme, indent=2))
        if dashboard_id:
            spec = dashboards.get(user, dashboard_id)["spec"]
            pages = [{"page": p["title"], "purpose": p.get("purpose"), "visuals": [{k: v for k, v in vis.items() if k in ("type", "title", "x", "value", "color", "measure", "condition", "date", "freq", "by")} for vis in p["visuals"]]} for p in spec["pages"]]
            z.writestr("dashboard_page_specification.json", json.dumps(pages, indent=2, default=str))
        z.writestr("README_POWERBI.md", f"""# Lucerna → Power BI package

Dataset: {ds['name']} (version {ds['version']}), {len(df):,} rows.

**This is not a .pbix file.** It is a Power BI-ready data package: star-schema CSVs, Power Query scripts,
DAX measures, relationships and a report theme. Native Lucerna dashboards are separate and are not
converted automatically.

## Steps (Power BI Desktop)
1. Extract this ZIP to a folder, e.g. `C:\\Lucerna\\PowerBI\\` (or on D:).
2. Home → Get data → Blank query → Advanced editor; paste each query from `power_query_M_scripts.pq`
   (edit `FolderPath` first). Name each query as in its first comment line.
3. Model view: create the relationships listed in `relationships.json` (many-to-one, single direction).
   Mark `Dim_Date` as a date table (Table tools → Mark as date table → Date).
4. Modelling → New measure: paste each measure from `dax_measures.dax`.
5. View → Themes → Browse for themes → `lucerna_theme.json`.
6. Use `dashboard_page_specification.json` (if present) as the page plan.

## Refresh
Re-export the package from Lucerna after data changes and overwrite the CSVs in the same folder, then
Home → Refresh. Keep the folder on an encrypted drive with restricted access.

## Row-level security (recommendation)
If the report will be shared beyond the project team, define RLS roles in Power BI (Modelling → Manage roles),
for example filtering `{(list(dims) or ['province'])[0]}` per partner/area, and publish only to a workspace whose access
matches the project's classification. Do not publish humanitarian beneficiary data to "Publish to web".

## Data protection applied to this export
{chr(10).join('- ' + n for n in notes) or '- None (no identifier/coordinate columns detected)'}
""")
    audit.log(user.username, "POWERBI_PACKAGE_EXPORTED", f"dataset #{dataset_id}", "WARNING", project_id=ds["project_id"], object_type="dataset", object_id=dataset_id)
    return buf.getvalue()
