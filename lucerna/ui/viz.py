"""Render dashboard visuals (KPI cards, insight panels, tables and Plotly charts) with
cross-filtering, drill-down and per-visual export."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ..quant import charts, insights
from . import theme, titles, viz_style
from .brand import design as brand_design

PLOTLY_CONFIG = {"displaylogo": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
                 "toImageButtonOptions": {"format": "png", "scale": 2}}
SELECTABLE = {"bar", "donut", "stacked100", "treemap", "multiselect"}


def app_design() -> dict:
    """Chart tokens for charts shown inside the Lucerna app (not inside an organisation dashboard)."""
    if theme.mode() == "dark":
        return brand_design.build(None, "executive", background="navy")
    return brand_design.build(None, "corporate", background="light")


def _fmt_kpi(v: dict, data: charts.VisualData) -> tuple[str, str]:
    val = data.table["value"].iloc[0] if len(data.table) else None
    if data.extra.get("text"):
        return str(val), f"{data.base_n:,} dated records" if data.base_n else ""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—", "No valid values"
    k = v.get("kpi")
    if k in ("pct", "completeness"):
        out = f"{val:.1f}%"
    elif isinstance(val, float) and not float(val).is_integer():
        out = f"{val:,.1f}"
    else:
        out = f"{int(val):,}"
    sub = f"Base n = {data.base_n:,}" if data.base_n is not None and k not in ("count_rows",) else ""
    return out, sub


def drill_state(vid: str) -> list:
    return st.session_state.setdefault(f"drill_{vid}", [])


def render(df: pd.DataFrame, v: dict, *, full: pd.DataFrame, plan: dict | None, key: str, cross_filter_key: str | None = None,
           exportable: bool = True) -> None:
    """Render one visual. `df` is already filtered; `full` is the unfiltered analytic copy (used for stable colours)."""
    t = v["type"]
    vid = v.get("id", key)
    # drill-down path: [(column, value), ...]
    path = drill_state(vid) if v.get("drill") else []
    vv = dict(v)
    if path:
        for col, val in path:
            df = df[df[col].astype("string") == val]
        levels = v["drill"]
        vv["x"] = levels[min(len(path), len(levels) - 1)]
        vv["title"] = f"{v.get('title', '')} — " + " › ".join(val for _, val in path)

    if t == "kpi":
        try:
            data = charts.compute(df, vv, full)
            value, sub = _fmt_kpi(vv, data)
        except charts.Unsupported as e:
            value, sub = "—", str(e)
        st.markdown(theme.kpi(vv.get("title", ""), value, sub, vv.get("icon", "activity"), small=len(str(value)) > 12), unsafe_allow_html=True)
        return

    with st.container(border=True):
        top = st.columns([10, 1]) if exportable else [st.container()]
        with top[0]:
            rd = titles.readable(vv, plan or {}) if t not in ("text",) else {"title": vv.get("title"), "subtitle": None}
            theme.chart_title(rd["title"] or vv.get("title") or charts.VISUAL_TYPES.get(t, t), subtitle=rd.get("subtitle"))
        if t == "text":
            if vv.get("insights") and plan:
                items = insights.generate(df, plan)
                if not items:
                    st.caption("No statements met the evidence threshold (n ≥ 30, and ≥ 10 percentage-point gaps for comparisons) under the current filters.")
                for it in items:
                    tone = {"gap": "warning", "trend": "info", "rate": "teal", "quality": "neutral"}[it["kind"]]
                    st.markdown(f"{theme.pill(it['kind'], tone)} {theme.esc(it['text'])}", unsafe_allow_html=True)
                st.caption("Computed directly from the filtered data; no AI involved. Each statement shows its base.")
            else:
                st.markdown(vv.get("markdown") or "_Empty text panel_")
            return
        try:
            data = charts.compute(df, vv, full)
        except charts.Unsupported as e:
            st.info(str(e), icon=":material/info:")
            return
        except Exception as e:  # noqa: BLE001 — a single broken visual must not break the page
            st.warning(f"This visual could not be computed: {e}")
            return
        if t in ("table", "stat_summary"):
            st.dataframe(data.table, hide_index=True, width="stretch", height=min(420, 38 + 35 * max(1, len(data.table))))
        else:
            try:
                D = app_design()
                fig = charts.figure(vv, data, viz_style.engine_mode(D), full)
            except charts.Unsupported as e:
                st.info(str(e))
                return
            fig = viz_style.restyle(fig, vv, D, labels=(plan or {}).get("labels"))
            selectable = t in SELECTABLE and (cross_filter_key or vv.get("drill"))
            ev = st.plotly_chart(fig, key=f"pl_{key}", config=PLOTLY_CONFIG, theme=None,
                                 on_select="rerun" if selectable else "ignore", selection_mode="points")
            if selectable and ev and ev.get("selection", {}).get("points"):
                _handle_selection(vv, v, ev["selection"]["points"][0], cross_filter_key, vid)
        foot = []
        if data.base_n is not None:
            foot.append(f"Base: n = {data.base_n:,}")
        foot += data.notes
        if foot:
            st.caption(" · ".join(foot))
        if path:
            if st.button("Drill up", key=f"up_{key}", icon=":material/arrow_upward:", type="tertiary"):
                path.pop()
                st.rerun()
        if exportable:
            with top[1].popover("", icon=":material/download:", help="Export this visual"):
                st.download_button("Data (CSV)", data.table.to_csv(index=False).encode("utf-8-sig"), f"{vid}.csv", "text/csv", key=f"csv_{key}")
                for fmt in ("png", "svg"):
                    if st.button(f"Prepare {fmt.upper()}", key=f"prep_{fmt}_{key}"):
                        try:
                            from ..reports.exports import chart_export
                            st.session_state[f"img_{fmt}_{key}"] = chart_export(df, vv, fmt)
                        except Exception as e:  # noqa: BLE001
                            st.caption(f"Static export unavailable: {e}")
                    if st.session_state.get(f"img_{fmt}_{key}"):
                        st.download_button(f"Download {fmt.upper()}", st.session_state[f"img_{fmt}_{key}"], f"{vid}.{fmt}",
                                           "image/png" if fmt == "png" else "image/svg+xml", key=f"dl_{fmt}_{key}")


def _handle_selection(vv: dict, v: dict, point: dict, cross_filter_key: str | None, vid: str) -> None:
    col = vv.get("x")
    label = point.get("label")
    if label is None:
        label = point.get("y") if isinstance(point.get("y"), str) else point.get("x")
    if col is None or label is None:
        return
    label = str(label)
    stamp = f"{vid}:{col}:{label}"
    if st.session_state.get(f"sel_{vid}") == stamp:
        return
    st.session_state[f"sel_{vid}"] = stamp
    if v.get("drill") and vv["x"] != v["drill"][-1]:
        drill_state(vid).append((col, label))
        st.rerun()
    elif cross_filter_key:
        cf = st.session_state.setdefault(cross_filter_key, {})
        cf[col] = {"values": [label]}
        st.rerun()


def grid(df: pd.DataFrame, visuals: list[dict], *, full: pd.DataFrame, plan: dict | None, key: str, cross_filter_key: str | None = None) -> None:
    """Lay visuals out on a 12-column grid using each visual's width."""
    row, used = [], 0
    rows = []
    # consecutive KPI cards share a row evenly (up to 5 per row)
    i = 0
    while i < len(visuals):
        if visuals[i]["type"] == "kpi":
            j = i
            while j < len(visuals) and visuals[j]["type"] == "kpi":
                j += 1
            run = visuals[i:j]
            if row:
                rows.append(row)
                row, used = [], 0
            for k in range(0, len(run), 5):
                chunk = run[k:k + 5]
                rows.append([(v, 1) for v in chunk])
            i = j
            continue
        v = visuals[i]
        i += 1
        w = max(2, min(12, int(v.get("width") or 6)))
        if used + w > 12 and row:
            rows.append(row)
            row, used = [], 0
        row.append((v, w))
        used += w
    if row:
        rows.append(row)
    for ri, r in enumerate(rows):
        widths = [w for _, w in r]
        if all(v["type"] == "kpi" for v, _ in r) and len(r) < 4:
            widths += [1] * (4 - len(r))
        cols = st.columns(widths, gap="small")
        for ci, (v, _) in enumerate(r):
            with cols[ci]:
                render(df, v, full=full, plan=plan, key=f"{key}_{ri}_{ci}_{v.get('id', '')}", cross_filter_key=cross_filter_key)
