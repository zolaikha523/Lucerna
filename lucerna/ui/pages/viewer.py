"""Generated Dashboard Viewer — a separate, full-screen environment with no builder controls.

Contains only: identity header, page navigation, filters, KPIs, charts, insights, and export / presentation
controls. Every number is computed by `charts.compute` on the filtered data; every explanation by
`explain.explain` from those numbers.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st

from ...quant import charts, explain, generator
from .. import common, composition, dash_theme, theme, titles, viz_style
from ..brand import color as C
from ..brand import design as brand_design
from ..brand import store as brand_store

PLOTLY_CONFIG = {"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
                 "toImageButtonOptions": {"format": "png", "scale": 2}}
SELECTABLE = {"bar", "stacked100", "treemap", "donut"}
NO_FIGURE = {"kpi", "text", "table", "stat_summary", "compare_table", "methodology"}
CACHE_MAX = 400


# ---------------------------------------------------------------- state helpers

def _did() -> int | None:
    v = st.query_params.get("id") or st.session_state.get("view_dashboard")
    try:
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


def _cache() -> dict:
    c = st.session_state.setdefault("_viewer_cache", {})
    if len(c) > CACHE_MAX:
        c.clear()
    return c


def _fkey(flt: dict) -> str:
    return hashlib.md5(json.dumps(flt, sort_keys=True, default=str).encode()).hexdigest()[:12]




def _ckey(d: dict, v: dict, flt: dict, drill: list) -> tuple:
    return (d["id"], d["version"], d.get("source_version"), v.get("id"), _fkey(flt), tuple(drill))


def computed(d: dict, v: dict, frames: dict, flt: dict, drill: list) -> tuple:
    """(VisualData | None, explanation | None, error message | None), cached per dashboard version, visual, filters and drill path."""
    k = _ckey(d, v, flt, drill)
    c = _cache()
    if k in c:
        return c[k]
    out = generator.compute_visual(d, v, frames, flt, drill)
    c[k] = out
    return out


# ---------------------------------------------------------------- pieces

def _header(d: dict, D: dict, u, present: bool) -> None:
    b = d["branding"]
    br = b.get("brand") or {}
    org = generator.org_identity(d["project_id"]) if b.get("show_org", True) else {}
    plan = d["plan"]
    data, mime = brand_store.logo(d)
    org_name = br.get("org_name") or org.get("name") or ""
    logo = dash_theme.logo_img(brand_store.data_uri(data, mime), f"{org_name} logo" if org_name else "Organisation logo")
    tf = plan.get("feasibility", {}).get("temporal", {})
    sub = b.get("subtitle") or " · ".join(x for x in [
        f"{plan.get('n', 0):,} {plan.get('unit_label', 'records')}", f"source: {plan.get('sheet') or d.get('dataset_name')}",
        (tf.get("reason", "").split(" between ")[-1].rstrip(".") if tf.get("possible") else None), plan.get("domain", {}).get("label")] if x)
    q = (plan.get("quality") or {}).get("findings") or []
    sev = {k: sum(1 for f in q if f.get("severity") == k) for k in ("error", "warning")}
    st_col = D["status"]["negative"] if sev["error"] else (D["status"]["warning"] if sev["warning"] else D["status"]["good"])
    qtxt = (" · ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in sev.items() if n) or "no issues found") if q or plan.get("quality") else None
    qchip = f'<br/><span class="ld-q"><i style="background:{st_col}"></i>Data checks: {theme.esc(qtxt)}</span>' if qtxt else ""
    right = f"Generated {common.fmt_time(d.get('generated_at') or d.get('updated_at'))} · v{d['version']}{qchip}"
    tagline = f'<div class="tag">{theme.esc(br["tagline"])}</div>' if br.get("tagline") else ""
    orgline = theme.esc(org_name) + (" · " + theme.esc(org.get("project")) if org.get("project") else "")
    st.markdown(f'<div class="ld-head">{logo}<div style="position:relative"><div class="org">{orgline}</div>'
                f'<div class="t">{theme.esc(b.get("title") or d["name"])}</div>{tagline}<div class="s">{theme.esc(sub)}</div></div>'
                f'<div class="badge">{right}</div></div>', unsafe_allow_html=True)


def _controls(d: dict, u, tkey: str, frames: dict, flt: dict) -> None:  # noqa: C901
    can_edit = common.can(u, "dashboard.edit", d["project_id"])
    can_export = common.can(u, "export", d["project_id"])
    with st.container(horizontal=True, horizontal_alignment="right", key="ld_controls"):
        if st.button("Back", icon=":material/arrow_back:", key="ld_back", help="Return to Dashboard Studio"):
            st.session_state.pop("present", None)
            common.goto("studio")
        if st.button("Present", icon=":material/slideshow:", key="ld_present", help="Full-screen presentation mode"):
            st.session_state["present"] = True
            st.rerun()
        with st.popover("Design", icon=":material/palette:"):
            keys = list(dash_theme.THEMES)
            sel = st.radio("Visualization theme", keys, index=keys.index(tkey), format_func=lambda k: dash_theme.THEMES[k]["label"], key=f"ld_theme_{d['id']}")
            st.caption(dash_theme.THEMES[sel]["desc"] + " The organisation logo and its colours are kept.")
            br = d["branding"].get("brand") or {}
            bgs = [k for k in brand_design.BACKGROUNDS if k != "image" or br.get("bg_image")]
            cur_bg = br.get("background") or "auto"
            bg = st.selectbox("Background", bgs, index=bgs.index(cur_bg) if cur_bg in bgs else 0, format_func=lambda k: brand_design.BACKGROUNDS[k],
                              key=f"ld_bg_{d['id']}", disabled=not can_edit, help=None if can_edit else "Only editors can change the saved background.")
            if sel != tkey or (can_edit and bg != cur_bg):
                if can_edit:
                    with common.guard():
                        generator.update_meta(u, d["id"], theme=sel if sel != tkey else None,
                                              branding={"brand": {**br, "background": bg}} if bg != cur_bg else None)
                else:
                    st.session_state[f"ld_tprev_{d['id']}"] = sel
                st.rerun()
            if can_edit:
                st.caption("Logo, organisation name, tagline and brand colours are edited in Dashboard Studio › Branding.")
        if can_export:
            with st.popover("Export", icon=":material/download:"):
                _export_menu(d, u, tkey, frames, flt)


def _export_menu(d: dict, u, tkey: str, frames: dict, flt: dict) -> None:
    from ...reports import dashboard_export as dx
    st.caption("Exports use the filters currently applied" + (f": {len(flt)} active." if flt else " (none)."))
    for fmt, label, mime in (("pdf", "Dashboard (PDF)", "application/pdf"), ("xlsx", "Tables & insights (Excel)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                             ("docx", "Detailed report (Word)", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")):
        k = f"ld_exp_{fmt}_{d['id']}"
        if st.button(f"Prepare {label}", key=f"{k}_b", width="stretch"):
            with st.spinner(f"Building {label}…"), common.guard():
                st.session_state[k] = dx.export(u, d, frames, flt, fmt, lambda v: computed(d, v, frames, flt, []))
        if st.session_state.get(k):
            st.download_button(f"Download {label}", st.session_state[k], f"{_slug(d)}.{fmt}", mime, key=f"{k}_dl", width="stretch", type="primary")


def _slug(d: dict) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", d["branding"].get("title") or d["name"]).strip("_")[:60] or "dashboard"


def _filters(d: dict, frames: dict, present: bool) -> dict:
    df = frames[None]
    did = d["id"]
    flt: dict = {}
    fdefs = [f for f in d["spec"].get("filters", []) if f["column"] in df.columns][:5]
    cross = st.session_state.setdefault(f"vx_{did}", {})
    if fdefs and not present:
        cols = st.columns([3] * len(fdefs) + [1.4], vertical_alignment="bottom")
        labels = d["plan"].get("labels", {})
        for i, f in enumerate(fdefs):
            c = f["column"]
            lab = labels.get(c) or c.replace("_", " ").capitalize()
            with cols[i]:
                if f["kind"] == "date_range" and pd.api.types.is_datetime64_any_dtype(df[c]):
                    s = df[c].dropna()
                    if len(s):
                        lo, hi = s.min().date(), s.max().date()
                        val = st.date_input(lab, (lo, hi), min_value=lo, max_value=hi, key=f"vf_{did}_{c}")
                        if isinstance(val, tuple) and len(val) == 2 and (val[0] != lo or val[1] != hi):
                            flt[c] = {"range": [str(pd.Timestamp(val[0]).date()), str(pd.Timestamp(val[1]).date())]}
                else:
                    opts = sorted(df[c].dropna().astype(str).unique())[:300]
                    sel = st.multiselect(lab, opts, key=f"vf_{did}_{c}", placeholder="All")
                    if sel:
                        flt[c] = {"values": sel}
        with cols[-1]:
            if st.button("Clear", icon=":material/filter_alt_off:", key=f"vclear_{did}", width="stretch", disabled=not (flt or cross)):
                for f in fdefs:
                    st.session_state.pop(f"vf_{did}_{f['column']}", None)
                cross.clear()
                st.rerun()
    elif present:
        for f in fdefs:
            val = st.session_state.get(f"vf_{did}_{f['column']}")
            if val and f["kind"] != "date_range":
                flt[f["column"]] = {"values": val}
    if cross:
        chips = " ".join(f'<span class="ld-tag i">{theme.esc(c)} = {theme.esc(", ".join(v["values"]))}</span>' for c, v in cross.items())
        cc = st.columns([8, 1])
        cc[0].markdown(f'<div class="ld-foot" style="margin-top:4px">Selected on a chart: {chips}</div>', unsafe_allow_html=True)
        if cc[1].button("Clear selection", key=f"vxclear_{did}", type="tertiary"):
            cross.clear()
            st.rerun()
    for c, v in cross.items():
        flt.setdefault(c, v)
    return flt


def _kpi_value(v: dict, data, err: str | None) -> tuple[str, str, float | None]:
    """(display value, context line, share 0–100 when the KPI is a percentage). Formatting only."""
    if err or data is None:
        return "—", (err or "")[:90], None
    raw = data.table["value"].iloc[0] if len(data.table) else None
    k = v.get("kpi")
    if data.extra.get("text"):
        return str(raw), f"{data.base_n:,} records with a valid date", None
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "—", "No valid values", None
    pct = k in ("pct", "completeness")
    val = f"{raw:.1f}%" if pct else (f"{raw:,.1f}" if isinstance(raw, float) and not float(raw).is_integer() else f"{int(raw):,}")
    sub = {"pct": f"of {data.base_n:,} with a valid answer", "count_rows": "after filters", "completeness": "of all cells have a value",
           "duplicates": f"of {data.base_n:,} IDs appear more than once"}.get(k, f"n = {data.base_n:,}" if data.base_n is not None else "")
    return val, sub, (float(raw) if pct else None)


def _kpi_html(v: dict, data, err: str | None, idx: int, D: dict, style: str, plan: dict) -> str:
    cat = D["categorical"]
    color = D["accent"] if style in ("inline",) else cat[idx % min(4, len(cat))]
    ink_color = C.with_lightness_for_contrast(color, D["solid"], 3.0)
    val, sub, share = _kpi_value(v, data, err)
    label = titles.kpi_label(v, plan.get("labels"))
    small = " sm" if len(str(val)) > 12 else ""
    ic = theme.icon(v.get("icon", "activity"), 18, ink_color)
    if style == "ring" and share is not None:
        circ = 2 * 3.14159 * 22
        off = circ * (1 - max(0.0, min(100.0, share)) / 100)
        ring = (f'<svg width="58" height="58" viewBox="0 0 58 58" aria-hidden="true"><circle cx="29" cy="29" r="22" fill="none" stroke="{C.rgba(color, .18)}" stroke-width="6"/>'
                f'<circle class="arc" cx="29" cy="29" r="22" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="{circ:.1f}" '
                f'stroke-dashoffset="{off:.1f}" transform="rotate(-90 29 29)" style="--lc-ring-len:{circ:.1f}"/></svg>')
        return (f'<div class="ld-kpi ring" style="--k:{color}" role="group" aria-label="{theme.esc(label)}: {theme.esc(val)}">{ring}<div>'
                f'<div class="lb">{theme.esc(label)}</div><div class="v{small}">{theme.esc(val)}</div><div class="s">{theme.esc(sub)}</div></div></div>')
    meter = f'<div class="meter"><i style="width:{max(0.0, min(100.0, share)):.1f}%"></i></div>' if style == "meter" and share is not None else ""
    cls = "tile" if style in ("tile", "ring", "meter") else ""
    return (f'<div class="ld-kpi {cls}" style="--k:{ink_color if style == "strip" else color}" role="group" aria-label="{theme.esc(label)}: {theme.esc(val)}">'
            f'<div class="top"><div class="ic" style="background:{C.rgba(color, .16 if D["mode"] == "dark" else .12)}">{ic}</div><div class="lb">{theme.esc(label)}</div></div>'
            f'<div class="v{small}">{theme.esc(val)}</div>{meter}<div class="s">{theme.esc(sub)}</div></div>')


def _insight_block(ex: dict, key: str, d: dict, u, technical: str | None = None) -> None:
    def sec(title, body, tag=None, cls="i"):
        if not body:
            return
        t = f'<span class="ld-tag {cls}">{tag}</span>' if tag else ""
        items = body if isinstance(body, list) else [body]
        st.markdown(f'<div class="ld-sec">{t}{theme.esc(title)}</div>' + "".join(f'<div class="ld-foot" style="margin:2px 0 4px;font-size:.82rem">• {theme.esc(x)}</div>' for x in items),
                    unsafe_allow_html=True)
    with st.expander("Insights, method & limitations", icon=":material/lightbulb:"):
        sec("What the data shows", ex.get("what"))
        sec("Key findings", ex.get("findings"), "verified" if ex.get("verified") else "projection", "v" if ex.get("verified") else "r")
        sec("Why this matters", ex.get("why"), "context", "l")
        sec("Analytical interpretation", ex.get("interpretation"), "interpretation", "i")
        sec("Operational implications", ex.get("implications"), "interpretation", "i")
        sec("Recommended follow-up", ex.get("actions"), "for analyst review", "r")
        sec("Limitations", ex.get("limitations"), None)
        s = ex.get("source", {})
        rows = [f"Sheet: {s.get('sheet')}", f"Variables: {', '.join(s.get('variables', [])[:8])}", f"Formula: {s.get('formula')}",
                f"Denominator: {s.get('denominator') or '—'}", f"Filters: {s.get('filters')}"] + s.get("exclusions", []) + [s.get("method")] \
            + ([f"Technical title (engine): {technical}"] if technical else [])
        sec("Source & methodology", rows, None)
        k = f"ai_{key}"
        if st.button("Reword with local AI", key=f"{k}_b", type="tertiary", icon=":material/auto_awesome:",
                     help="Optional. The local model rewrites the verified findings as a paragraph; any sentence with a number not in the findings is discarded."):
            para, err = explain.ai_polish(ex, project_id=d["project_id"], classification=None)
            st.session_state[k] = para or err
        if st.session_state.get(k):
            st.markdown(f'<div class="ld-ins"><div class="h">AI wording (numbers checked against the findings)</div><div class="b">{theme.esc(st.session_state[k])}</div></div>',
                        unsafe_allow_html=True)


def _chart(d: dict, v: dict, frames: dict, flt: dict, D: dict, key: str, u, present: bool, hero: bool = False) -> None:
    did = d["id"]
    drill = st.session_state.setdefault(f"vd_{did}_{v.get('id')}", []) if v.get("drill") else []
    with st.container(key=f"{'ldhero' if hero else 'ldcard'}_{key}"):
        top = st.columns([12, 1]) if not present else [st.container()]
        head = top[0].empty()
        body = st.empty()
        if _ckey(d, v, flt, drill) not in _cache():          # skeleton only while a visual is actually being computed
            head.markdown(theme.skeleton_html(0, 2), unsafe_allow_html=True)
            body.markdown(theme.skeleton_html(220 if not hero else 300), unsafe_allow_html=True)
        data, ex, err, vv = computed(d, v, frames, flt, drill)
        rd = titles.readable(vv, d["plan"])
        title = rd["title"] or charts.VISUAL_TYPES.get(v["type"], v["type"])
        if drill:
            title += " — " + " › ".join(val for _, val in drill)
        lead = ex.get("what") if ex and not present else None
        head.markdown(f'<div class="ld-ct">{theme.esc(title)}</div>' + (f'<div class="ld-cs">{theme.esc(rd["subtitle"])}</div>' if rd.get("subtitle") else "")
                      + (f'<div class="ld-lead">{theme.esc(lead)}</div>' if lead else ""), unsafe_allow_html=True)
        if err:
            body.info(err, icon=":material/info:")
            return
        t = v["type"]
        if t == "methodology":
            body.empty()
            _methodology(d)
            return
        if t in ("table", "stat_summary", "compare_table"):
            body.dataframe(data.table, hide_index=True, width="stretch", height=min(460, 40 + 35 * max(1, len(data.table))))
        else:
            fig = charts.figure(vv, data, viz_style.engine_mode(D), frames.get(v.get("ds"), frames[None]))
            base_h = fig.layout.height or 340
            fig = viz_style.restyle(fig, vv, D, labels=d["plan"].get("labels"),
                                    height=int(base_h * (1.15 if present else 1.0) + (40 if hero and base_h < 400 else 0)))
            selectable = t in SELECTABLE and not v.get("ds")
            ev = body.plotly_chart(fig, key=f"pl_{key}_{_fkey(flt)}_{len(drill)}", config=PLOTLY_CONFIG, theme=None,
                                   on_select="rerun" if selectable else "ignore", selection_mode="points")
            if selectable and ev and ev.get("selection", {}).get("points"):
                _on_select(d, v, vv, ev["selection"]["points"][0], drill)
        foot = []
        if data.base_n is not None:
            foot.append(f"Base: n = {data.base_n:,}")
        foot += [n for n in data.notes if n][:2]
        if v.get("drill") and not drill:
            foot.append("Click a bar to drill down")
        elif t in SELECTABLE and not v.get("ds") and not v.get("drill"):
            foot.append("Click a bar to filter the whole dashboard")
        st.markdown(f'<div class="ld-foot">{theme.esc(" · ".join(foot))}</div>', unsafe_allow_html=True)
        if drill and st.button("Drill up", key=f"up_{key}", icon=":material/arrow_upward:", type="tertiary"):
            drill.pop()
            st.rerun()
        if not present:
            if ex:
                _insight_block(ex, key, d, u, rd.get("technical"))
            if common.can(u, "export", d["project_id"]):
                with top[1].popover("", icon=":material/download:", help="Download this visual"):
                    st.download_button("Data (CSV)", data.table.to_csv(index=False).encode("utf-8-sig"), f"{v.get('id')}.csv", "text/csv", key=f"csv_{key}")
                    if st.button("Prepare PNG", key=f"png_{key}"):
                        try:
                            from ...reports import static_charts
                            st.session_state[f"png_{key}"] = static_charts.to_bytes(vv, data, "png")
                        except Exception as e:  # noqa: BLE001
                            st.caption(f"Static image unavailable for this visual: {e}")
                    if st.session_state.get(f"png_{key}"):
                        st.download_button("Download PNG", st.session_state[f"png_{key}"], f"{v.get('id')}.png", "image/png", key=f"pngdl_{key}")


def _on_select(d: dict, v: dict, vv: dict, point: dict, drill: list) -> None:
    col = vv.get("x")
    label = point.get("label")
    if label is None:
        label = point.get("y") if isinstance(point.get("y"), str) else point.get("x")
    if col is None or label is None:
        return
    stamp = f"{v.get('id')}:{col}:{label}:{len(drill)}"
    if st.session_state.get(f"vsel_{d['id']}") == stamp:
        return
    st.session_state[f"vsel_{d['id']}"] = stamp
    if v.get("drill") and vv["x"] != v["drill"][-1]:
        drill.append((col, str(label)))
    else:
        st.session_state.setdefault(f"vx_{d['id']}", {})[col] = {"values": [str(label)]}
    st.rerun()


def _methodology(d: dict) -> None:
    plan = d["plan"]
    wb = plan.get("workbook") or {}
    dom = plan.get("domain", {})
    lines = [f"Main data: '{plan.get('sheet')}' — {plan.get('n', 0):,} records ({plan.get('unit_label')}"
             + ("" if plan.get("unit_confirmed") else ", unit not yet confirmed") + ")."]
    lines += wb.get("explanation", [])[:8]
    lines.append(f"Likely domain: {dom.get('label')} — {dom.get('reason')}")
    if plan.get("segment"):
        lines.append(f"Main comparison variable chosen automatically: '{plan['segment']}' (2–7 well-populated groups with the most even split).")
    lines.append("All figures are computed deterministically from the data. Explanations are generated by rules from those figures; "
                 "recommendations are suggestions for analyst review, not conclusions.")
    st.markdown("".join(f'<div class="ld-foot" style="font-size:.8rem;margin:4px 0">• {theme.esc(x)}</div>' for x in lines), unsafe_allow_html=True)
    if plan.get("limitations"):
        st.markdown('<div class="ld-sec">Limitations</div>' + "".join(f'<div class="ld-foot" style="font-size:.8rem;margin:3px 0">• {theme.esc(x)}</div>' for x in plan["limitations"]),
                    unsafe_allow_html=True)
    q = plan.get("quality") or {}
    if q.get("findings"):
        st.markdown('<div class="ld-sec">Data-quality checks (at generation)</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(q["findings"]), hide_index=True, width="stretch", height=min(300, 40 + 35 * len(q["findings"])))
    unsupported = [f"{k}: {v.get('reason')}" for k, v in plan.get("feasibility", {}).items() if isinstance(v, dict) and not v.get("possible")]
    if unsupported:
        st.markdown('<div class="ld-sec">Analyses not possible with this data</div>' + "".join(f'<div class="ld-foot" style="font-size:.8rem;margin:3px 0">• {theme.esc(x)}</div>' for x in unsupported),
                    unsafe_allow_html=True)


def _key_findings(d: dict, frames: dict, flt: dict) -> list[dict]:
    k = ("kf", d["id"], d["version"], d.get("source_version"), _fkey(flt))
    c = _cache()
    if k in c:
        return c[k]
    items = []
    for p in d["spec"]["pages"]:
        for v in p["visuals"]:
            if v["type"] in ("kpi", "text", "methodology", "quality_missing") or v.get("ds"):
                continue
            data, ex, err, _ = computed(d, v, frames, flt, [])
            if ex:
                items.append((v, ex))
    c[k] = explain.summary_findings(items, limit=6)
    return c[k]


def _kpi_band(d: dict, kpis: list[dict], frames: dict, flt: dict, D: dict, style: str) -> None:
    if not kpis:
        return
    cards = []
    for i, v in enumerate(kpis):
        data, _, err, _ = computed(d, v, frames, flt, [])
        cards.append(_kpi_html(v, data, err, i, D, style, d["plan"]))
    st.markdown(f'<div class="ld-kpis {style}">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def _grid(d: dict, visuals: list[dict], frames: dict, flt: dict, D: dict, pkey: str, u, present: bool, page_index: int, kpis: bool = True) -> dict:
    lay = composition.arrange(visuals, d["plan"], page_index)
    if kpis:
        _kpi_band(d, lay["kpis"], frames, flt, D, composition.kpi_style(lay["profile"], (brand_store.extracted(d) or {}).get("character")))
    if lay["hero"] is not None:
        _chart(d, lay["hero"], frames, flt, D, f"{pkey}_h_{lay['hero'].get('id', '')}", u, present, hero=True)
    for ri, r in enumerate(lay["rows"]):
        cols = st.columns([w for _, w in r], gap="small")
        for ci, (v, _) in enumerate(r):
            with cols[ci]:
                _chart(d, v, frames, flt, D, f"{pkey}_{ri}_{ci}_{v.get('id', '')}", u, present)
    return lay


def _findings(d: dict, frames: dict, flt: dict, D: dict, wide: bool = False) -> None:
    with st.container(key=f"ldside_{d['id']}"):
        st.markdown(f'<div class="ld-ct" style="margin-bottom:10px">{theme.icon("sparkles", 16, D["accent"])} Key findings</div>', unsafe_allow_html=True)
        items = _key_findings(d, frames, flt)
        if not items:
            st.caption("No finding met the evidence rules under the current filters.")
        body = "".join(f'<div class="ld-ins"><div class="h">{theme.esc(it["title"])}</div><div class="b">{theme.esc(it["text"])}</div></div>' for it in items)
        st.markdown(f'<div class="{"ld-findings" if wide else ""}">{body}</div>', unsafe_allow_html=True)
        st.markdown('<div class="ld-foot">Selected automatically from verified, computed findings (strongest statistical evidence first). No AI involved.</div>',
                    unsafe_allow_html=True)


# ---------------------------------------------------------------- page

def page() -> None:
    u = common.cu()
    did = _did()
    if not did:
        theme.page_header("Dashboard", "No dashboard selected.", "chart-column")
        st.page_link(common.page_ref("studio"), label="Open Dashboard Studio", icon=":material/dashboard_customize:")
        return
    try:
        d = generator.get(u, did)
    except Exception as e:  # noqa: BLE001
        st.error(f"This dashboard cannot be opened: {e}")
        return
    st.session_state["view_dashboard"] = did
    if str(st.query_params.get("id")) != str(did):
        st.query_params["id"] = str(did)
    present = bool(st.session_state.get("present"))
    tkey = st.session_state.get(f"ld_tprev_{did}") or d["theme"]
    D = brand_store.design_for(d, tkey)
    bg_uri = brand_store.background_uri(d) if D["background"] == "image" else None
    prof = composition.profile(d["plan"])
    dash_theme.inject(D, present, brand_design.css_background(D, bg_uri), header_style="plain" if D["theme"] == "minimal" else "brand")
    loading = st.empty()
    loading.markdown(theme.loader_html("Preparing the dashboard…"), unsafe_allow_html=True)
    frames = generator.frames(u, d)
    loading.empty()
    pages = d["spec"]["pages"]
    if not pages:
        st.info("This dashboard has no pages.")
        return

    hc = st.columns([7, 5], vertical_alignment="center") if not present else [st.container()]
    with hc[0]:
        _header(d, D, u, present)
    if d.get("stale") and not present:
        st.warning("The data behind this dashboard has changed since it was generated. Ask an analyst to refresh it in Dashboard Studio.", icon=":material/update:")

    titles_ = [p["title"] for p in pages]
    pk = f"vpage_{did}"
    if st.session_state.get(pk) not in titles_:
        st.session_state[pk] = titles_[0]
    if not present:
        st.segmented_control("Pages", titles_, key=pk, label_visibility="collapsed", required=True)
    flt = _filters(d, frames, present)
    if not present:
        with hc[1]:
            _controls(d, u, tkey, frames, flt)
    idx = titles_.index(st.session_state[pk])
    p = pages[idx]
    st.markdown(f'<div class="ld-pagehead"><span class="pt">{theme.esc(p["title"])}</span>'
                f'<span class="pp">{theme.esc(p.get("purpose", ""))}</span>'
                f'<span class="lay" title="Layout chosen from the dataset\'s domain ({theme.esc(d["plan"].get("domain", {}).get("label", ""))})">{theme.esc(prof["name"])} layout</span></div>',
                unsafe_allow_html=True)
    has_findings = any(v["type"] == "text" and v.get("insights") for v in p["visuals"])
    if has_findings and prof["findings"] == "side" and not present:
        lay = composition.arrange(p["visuals"], d["plan"], idx)
        _kpi_band(d, lay["kpis"], frames, flt, D, composition.kpi_style(prof, (brand_store.extracted(d) or {}).get("character")))
        main, side = st.columns([3.1, 1], gap="medium")
        with main:
            _grid(d, p["visuals"], frames, flt, D, f"p{idx}", u, present, idx, kpis=False)
        with side:
            _findings(d, frames, flt, D)
    else:
        _grid(d, p["visuals"], frames, flt, D, f"p{idx}", u, present, idx)
        if has_findings:
            _findings(d, frames, flt, D, wide=True)

    if present:
        nav = st.columns([1, 1, 6, 1.4], vertical_alignment="center")
        if nav[0].button("Previous", icon=":material/chevron_left:", disabled=idx == 0, key="pr_prev"):
            st.session_state[pk] = titles_[idx - 1]
            st.rerun()
        if nav[1].button("Next", icon=":material/chevron_right:", disabled=idx == len(titles_) - 1, key="pr_next"):
            st.session_state[pk] = titles_[idx + 1]
            st.rerun()
        nav[2].markdown(f'<div class="ld-foot" style="text-align:center">Page {idx + 1} of {len(titles_)}</div>', unsafe_allow_html=True)
        if nav[3].button("Exit presentation", icon=":material/close_fullscreen:", key="pr_exit"):
            st.session_state["present"] = False
            st.rerun()
