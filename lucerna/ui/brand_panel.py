"""Organisation branding panel for Dashboard Studio: logo upload, colour extraction, palette preview and save.

Used in two places: the Generate tab (brand a new dashboard) and My dashboards › Branding (edit an existing one).
The panel only collects choices and shows a live, deterministic preview; files are stored when the user saves.
"""
from __future__ import annotations

import streamlit as st

from ..quant import generator
from . import common, dash_theme, theme
from .brand import color as C
from .brand import design, extract, store
from .brand.extract import BrandError

LOGO_TYPES = ["png", "jpg", "jpeg", "svg"]


@st.cache_data(show_spinner=False, max_entries=64)
def _extract(data: bytes) -> dict:
    return extract.extract(data)


def _check_row(label: str, value: float, target: float, unit: str = ":1") -> str:
    ok = value >= target
    col = "#22B573" if ok else "#E0A030"
    return (f'<div style="display:flex;justify-content:space-between;gap:10px;font-size:.8rem;padding:3px 0;border-bottom:1px solid rgba(127,127,127,.15)">'
            f'<span>{theme.esc(label)}</span><span style="color:{col};font-weight:600">{value:g}{unit} {"✓" if ok else "below " + str(target) + unit}</span></div>')


def preview_html(D: dict, org: str, title: str, tagline: str, logo_uri: str | None, bg_uri: str | None = None) -> str:
    """A miniature dashboard built from the tokens, so the effect of a logo is visible before saving."""
    bg = design.css_background(D, bg_uri)
    cat = D["categorical"]
    on_brand = D["header_ink"] == "#FFFFFF"
    logo = (f'<div style="background:{"rgba(255,255,255,.96)" if on_brand or D["mode"] == "dark" else "transparent"};border-radius:9px;padding:4px 7px;display:flex;align-items:center">'
            f'<img src="{logo_uri}" style="max-height:28px;max-width:90px;object-fit:contain"/></div>') if logo_uri else ""
    head = D["header"] if D["theme"] != "minimal" else D["surface"]
    hink = D["header_ink"] if D["theme"] != "minimal" else D["ink"]
    kpis = "".join(
        f'<div style="flex:1;background:{D["surface"]};border:1px solid {D["line"]};border-radius:10px;padding:8px 10px;position:relative;overflow:hidden">'
        f'<div style="position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,{cat[i]},transparent)"></div>'
        f'<div style="font-size:.62rem;color:{D["ink2"]}">Indicator {i + 1}</div><div style="font-size:1.05rem;font-weight:700;color:{D["ink"]}">{v}</div></div>'
        for i, v in enumerate(["1,284", "62.4%", "18.0"]))
    vals = [86, 64, 52, 38, 27, 18]
    bars = "".join(f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0"><div style="width:44px;font-size:.6rem;color:{D["muted"]}">Group {chr(65 + i)}</div>'
                   f'<div style="height:9px;width:{v}%;background:{cat[i]};border-radius:0 4px 4px 0"></div></div>' for i, v in enumerate(vals))
    line_pts = " ".join(f"{i * 24},{60 - y}" for i, y in enumerate([12, 20, 18, 30, 34, 42, 40, 50]))
    trend = (f'<svg viewBox="0 0 170 64" style="width:100%;height:64px"><polyline points="{line_pts}" fill="none" stroke="{cat[0]}" stroke-width="2.4" stroke-linecap="round"/>'
             f'<polyline points="{" ".join(f"{i * 24},{64 - y}" for i, y in enumerate([8, 10, 16, 14, 20, 22, 28, 26]))}" fill="none" stroke="{cat[1]}" stroke-width="2.4" stroke-linecap="round"/></svg>')
    return (f'<div style="border-radius:16px;padding:12px;background:{bg};border:1px solid rgba(127,127,127,.25);font-family:{theme.FONT_STACK}">'
            f'<div style="display:flex;align-items:center;gap:10px;background:{head};border-radius:11px;padding:9px 12px;border:1px solid {D["line"]}">{logo}'
            f'<div><div style="font-size:.56rem;letter-spacing:.12em;text-transform:uppercase;color:{D["header_sub"] if D["theme"] != "minimal" else D["muted"]};font-weight:700">{theme.esc(org or "Organisation")}</div>'
            f'<div style="font-size:.9rem;font-weight:700;color:{hink}">{theme.esc(title or "Dashboard title")}</div>'
            + (f'<div style="font-size:.66rem;color:{hink};opacity:.85">{theme.esc(tagline)}</div>' if tagline else "") + '</div></div>'
            f'<div style="display:flex;gap:8px;margin:9px 0">{kpis}</div>'
            f'<div style="display:flex;gap:8px"><div style="flex:1.2;background:{D["surface"]};border:1px solid {D["line"]};border-radius:10px;padding:8px 10px">'
            f'<div style="font-size:.7rem;font-weight:650;color:{D["ink"]};margin-bottom:4px">Which groups are most common?</div>{bars}</div>'
            f'<div style="flex:1;background:{D["surface"]};border:1px solid {D["line"]};border-radius:10px;padding:8px 10px">'
            f'<div style="font-size:.7rem;font-weight:650;color:{D["ink"]};margin-bottom:4px">How has it changed over time?</div>{trend}</div></div>'
            f'<div style="display:flex;gap:6px;margin-top:9px">'
            + "".join(f'<span style="font-size:.6rem;padding:2px 8px;border-radius:999px;background:{C.rgba(D["status"][k], .16)};color:{D["status"][k]}">{k}</span>'
                      for k in ("good", "warning", "negative")) + '</div></div>')


def panel(u, pid: int, key: str, theme_key: str, current: dict | None = None, *, default_title: str = "") -> dict:
    """Render the branding controls. Returns the pending choices (files not stored yet):
    {"title", "subtitle", "show_org", "logo", "logo_bytes", "org_name", "tagline", "background", "bg_bytes", "custom", "use_logo_colours", "extracted"}."""
    cur = current or {}
    br = cur.get("brand") or {}
    org = generator.org_identity(pid)
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        c1, c2 = st.columns(2)
        org_name = c1.text_input("Organisation name", value=br.get("org_name") or org.get("name") or "", key=f"{key}_org",
                                 help="Shown in the dashboard header. Defaults to the organisation that owns this project.")
        tagline = c2.text_input("Tagline (optional)", value=br.get("tagline") or "", key=f"{key}_tag", placeholder="e.g. Protecting people on the move")
        c3, c4 = st.columns(2)
        title = c3.text_input("Dashboard title", value=cur.get("title") or "", placeholder=default_title, key=f"{key}_title")
        subtitle = c4.text_input("Subtitle", value=cur.get("subtitle") or "", placeholder="e.g. Round 3 · January–June", key=f"{key}_sub")
        show_org = st.checkbox("Show the organisation and project name in the header", value=cur.get("show_org", True), key=f"{key}_showorg")
        opts = ["org", "custom", "none"]
        cur_logo = cur.get("logo", "org") if cur.get("logo", "org") in opts else "org"
        logo_choice = st.radio("Logo", opts, index=opts.index(cur_logo), horizontal=True, key=f"{key}_logo",
                               format_func={"org": "Organisation logo", "custom": "Upload a logo for this dashboard", "none": "No logo"}.get)
        logo_bytes = None
        if logo_choice == "custom":
            f = st.file_uploader("Logo: PNG, JPG/JPEG (under 1 MB) or SVG (under 2 MB)", type=LOGO_TYPES, key=f"{key}_logofile",
                                 help="SVG files are checked and cleaned: scripts, event handlers, external links and embedded web content are removed.")
            logo_bytes = f.getvalue() if f is not None else None
        st.caption("Use only logos your organisation is entitled to use. Lucerna never adds an organisation's logo or claims affiliation on its own.")
        bgs = list(design.BACKGROUNDS)
        cur_bg = br.get("background") or "auto"
        background = st.selectbox("Dashboard background", bgs, index=bgs.index(cur_bg) if cur_bg in bgs else 0, format_func=design.BACKGROUNDS.get, key=f"{key}_bg")
        bg_bytes = None
        if background == "image":
            bf = st.file_uploader("Background photo (PNG or JPEG, under 4 MB)", type=["png", "jpg", "jpeg"], key=f"{key}_bgfile",
                                  help="Shown behind a dark or light veil so charts stay readable. Metadata is removed.")
            bg_bytes = bf.getvalue() if bf is not None else None
            if bg_bytes is None and not br.get("bg_image"):
                st.caption("No background photo yet: the theme background is used until one is uploaded.")
        use_logo = st.toggle("Build the colour system from the logo", value=br.get("use_logo_colours", True), key=f"{key}_uselogo",
                             help="Off: the theme's own Lucerna palette is used, and the logo is still shown.")
        custom = dict(br.get("custom") or {})
        with st.expander("Custom brand colours (optional)", icon=":material/colorize:", expanded=bool(custom)):
            st.caption("Set any of these to override what was read from the logo. Charts and text still pass the contrast checks.")
            cc = st.columns(3)
            for i, (k, lab) in enumerate((("primary", "Primary"), ("secondary", "Secondary"), ("accent", "Accent"))):
                on = cc[i].checkbox(lab, value=bool(custom.get(k)), key=f"{key}_c_{k}_on")
                val = cc[i].color_picker(f"{lab} colour", value=custom.get(k) or ["#2F6BFF", "#16C2B0", "#8B6CFF"][i], key=f"{key}_c_{k}",
                                         label_visibility="collapsed", disabled=not on)
                custom[k] = val.upper() if on else None
        custom = {k: v for k, v in custom.items() if v}

    extracted, err, logo_uri = None, None, None
    if logo_choice == "custom" and logo_bytes:
        try:
            extracted = _extract(logo_bytes)
            kind = extract.kind_of(logo_bytes)
            shown = logo_bytes if kind != "svg" else _clean_svg(logo_bytes)
            logo_uri = store.data_uri(shown, {"png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml"}[kind])
        except BrandError as e:
            err = str(e)
    elif logo_choice == "custom" and br.get("extracted") and cur.get("logo") == "custom":
        extracted = br["extracted"]
        data, mime = store.logo({"branding": cur, "project_id": pid})
        logo_uri = store.data_uri(data, mime)
    elif logo_choice == "org":
        data, mime = store.logo({"branding": {"logo": "org"}, "project_id": pid})
        logo_uri = store.data_uri(data, mime)
        if data:
            try:
                extracted = _extract(data)
            except BrandError:
                extracted = None
    bg_uri = store.data_uri(bg_bytes, "image/jpeg" if bg_bytes and bg_bytes[:3] == b"\xff\xd8\xff" else "image/png") if bg_bytes else \
        (store.background_uri({"branding": cur}) if background == "image" else None)
    eff_bg = background if (background != "image" or bg_uri) else "auto"
    D = design.build(extracted if use_logo else None, theme_key, custom=custom, background=eff_bg)

    with right:
        if err:
            st.error(err, icon=":material/error:")
        elif logo_choice == "custom" and not logo_bytes and not br.get("extracted"):
            st.caption("Upload a logo to see the colours Lucerna reads from it.")
        if extracted and use_logo:
            sw = extracted.get("swatches") or []
            st.markdown('<div class="lc-muted" style="margin-bottom:4px">Colours found in the logo (share of coloured area)</div>', unsafe_allow_html=True)
            if sw:
                st.markdown("".join(
                    f'<span style="display:inline-flex;align-items:center;gap:6px;margin:0 10px 6px 0;font-size:.78rem"><span style="width:18px;height:18px;border-radius:5px;'
                    f'background:{s["hex"]};border:1px solid rgba(127,127,127,.35)"></span>{s["hex"]} · {s["chromatic_share"]:.0%}</span>' for s in sw[:6]), unsafe_allow_html=True)
            else:
                st.caption("The logo has no strong colours (monochrome); a restrained slate-and-blue system is used instead of invented colours.")
            ch = extracted.get("character", {})
            st.caption(f"Visual character: {ch.get('label', '—')}. Role rule: {D['rule']}.")
        st.markdown(preview_html(D, org_name, title or default_title, tagline, logo_uri if logo_choice != "none" else None, bg_uri), unsafe_allow_html=True)
        st.markdown('<div class="lc-muted" style="margin:8px 0 3px">Chart palette (categorical, then sequential and diverging)</div>', unsafe_allow_html=True)
        st.markdown(dash_theme.palette_strip(D["categorical"], 20), unsafe_allow_html=True)
        sc = st.columns(2)
        sc[0].markdown(dash_theme.palette_strip(D["sequential"], 12), unsafe_allow_html=True)
        sc[1].markdown(dash_theme.palette_strip(D["diverging"], 12), unsafe_allow_html=True)
        with st.expander("Accessibility checks", icon=":material/accessibility_new:"):
            ck = D["checks"]
            st.markdown(_check_row("Main text contrast", ck["ink_on_surface"], 7.0) + _check_row("Secondary text contrast", ck["secondary_text"], 4.5)
                        + _check_row("Muted text contrast", ck["muted_text"], 3.0) + _check_row("Accent / controls contrast", ck["accent_on_surface"], 3.0)
                        + _check_row("Weakest chart colour vs. card", ck["chart_min_contrast"], 3.0)
                        + _check_row("Neighbouring chart colours (ΔE)", ck["chart_min_neighbour_distance"], 14.0, "")
                        + _check_row("Same, under colour-vision deficiency (ΔE)", ck["chart_min_cvd_distance"], 8.0, ""), unsafe_allow_html=True)
            st.caption("Contrast is WCAG 2.x relative-luminance contrast. ΔE is OKLab distance × 100, checked under simulated protanopia, deuteranopia "
                       "and tritanopia. Charts always keep legends and labels, so colour is never the only cue.")
    return {"title": title.strip(), "subtitle": subtitle.strip(), "show_org": show_org, "logo": logo_choice, "logo_bytes": logo_bytes, "org_name": org_name.strip(),
            "tagline": tagline.strip(), "background": background, "bg_bytes": bg_bytes, "custom": custom, "use_logo_colours": use_logo, "extracted": extracted, "design": D}


@st.cache_data(show_spinner=False, max_entries=32)
def _clean_svg(data: bytes) -> bytes:
    from .brand import svg_safe
    return svg_safe.sanitize(data)


def to_branding(u, pid: int, choice: dict, current: dict | None = None) -> dict:
    """Store files and turn the panel's choices into the `branding` dict saved with the dashboard."""
    cur = current or {}
    br = dict(cur.get("brand") or {})
    out = {"title": choice["title"] or None, "subtitle": choice["subtitle"], "show_org": choice["show_org"], "logo": choice["logo"]}
    if choice["logo"] == "custom" and choice.get("logo_bytes"):
        res = store.store_logo(u, pid, choice["logo_bytes"])
        out.update(res["keys"])
        br.update(extracted=res["extracted"], logo_sha=res["sha"])
    elif choice["logo"] == "custom" and not (cur.get("logo_path") or cur.get("logo_svg")):
        out["logo"] = "none"
    if choice["logo"] != "custom":
        br.pop("extracted", None)
    if choice["background"] == "image" and choice.get("bg_bytes"):
        br["bg_image"] = store.store_background(u, pid, choice["bg_bytes"])
    br.update(org_name=choice["org_name"], tagline=choice["tagline"], background=choice["background"], custom=choice["custom"],
              use_logo_colours=choice["use_logo_colours"])
    out["brand"] = br
    return {k: v for k, v in out.items() if v is not None}


def editor_dialog_body(u, d: dict) -> None:
    """Edit the branding of an existing dashboard (My dashboards › Branding)."""
    choice = panel(u, d["project_id"], f"be_{d['id']}", d["theme"], d["branding"], default_title=d["name"])
    if st.button("Save branding", type="primary", icon=":material/save:", key=f"be_save_{d['id']}"):
        with common.guard("Branding saved. It stays with this dashboard through theme changes, duplication and export."):
            b = to_branding(u, d["project_id"], choice, d["branding"])
            if not b.get("title"):
                b["title"] = d["branding"].get("title") or d["name"]
            generator.update_meta(u, d["id"], branding=b)
            st.rerun()
