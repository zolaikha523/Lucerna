"""Dashboard canvas styling (system C: visualization theme, combined with system B: organisation brand).

The theme chooses the base (light or dark, background family, radius and density). The organisation's logo chooses
the colours. `brand.design.build` merges both into one token set; this module turns those tokens into the CSS of
the dashboard viewer. It is independent of the Lucerna application theme (`theme.py`), which never leaks into a
dashboard: the app sidebar and header are hidden on the canvas.
"""
from __future__ import annotations

import streamlit as st

from . import theme as app_theme
from .brand import color as C
from .brand import design

THEMES = {
    "corporate": {"label": "Corporate Light", "desc": "Premium light neutral page with glass cards. Suits reports to donors and management."},
    "executive": {"label": "Executive Dark", "desc": "Deep navy canvas with luminous, brand-coloured charts. Suits briefings and large screens."},
    "vibrant": {"label": "Modern Vibrant", "desc": "Violet-blue night canvas with bright accents. Suits public-facing and communication products."},
    "minimal": {"label": "Research & Minimal", "desc": "Quiet, print-like paper with hairlines and no decoration. Suits research and academic outputs."},
}


def swatch_html(key: str, d: dict | None = None) -> str:
    """Small preview of a theme (optionally with a brand applied)."""
    d = d or design.build(None, key)
    bg = design.css_background(d)
    dots = "".join(f'<span style="display:inline-block;width:13px;height:13px;border-radius:50%;background:{c};margin-right:4px"></span>'
                   for c in d["categorical"][:6])
    return (f'<div style="border-radius:14px;padding:12px;background:{bg};border:1px solid {d["line"] if d["line"].startswith("#") else "rgba(255,255,255,.1)"};">'
            f'<div style="background:{d["header"]};color:{d["header_ink"]};border-radius:9px;padding:6px 10px;font-weight:600;font-size:.8rem;margin-bottom:8px">'
            f'{THEMES.get(key, {}).get("label", key)}</div>'
            f'<div style="background:{d["surface"]};border:1px solid {d["line"]};border-radius:9px;padding:8px 10px">{dots}</div></div>')


def palette_strip(colors: list[str], size: int = 22, labels: list[str] | None = None) -> str:
    cells = []
    for i, c in enumerate(colors):
        lab = labels[i] if labels and i < len(labels) else c
        cells.append(f'<div title="{app_theme.esc(lab)}" style="flex:1;min-width:{size}px;height:{size}px;background:{c};"></div>')
    return f'<div style="display:flex;border-radius:8px;overflow:hidden;border:1px solid rgba(127,127,127,.25)">{"".join(cells)}</div>'


def inject(d: dict, presentation: bool = False, bg_css: str | None = None, *, header_style: str = "brand") -> None:
    """Full-screen dashboard canvas from design tokens `d`: hide the app chrome, apply background, glass and motion."""
    dark = d["mode"] == "dark"
    minimal = d["theme"] == "minimal"
    r = d["radius"]
    blur = "blur(14px) saturate(130%)" if dark else "blur(10px)"
    shadow = ("none" if minimal else
              ("0 1px 0 rgba(255,255,255,.05) inset, 0 20px 44px -24px rgba(0,0,0,.7)" if dark else "0 1px 2px rgba(16,24,40,.04), 0 14px 34px -18px rgba(16,24,40,.18)"))
    hover_shadow = "none" if minimal else ("0 1px 0 rgba(255,255,255,.07) inset, 0 26px 56px -26px rgba(0,0,0,.8)" if dark else "0 2px 4px rgba(16,24,40,.05), 0 22px 44px -20px rgba(16,24,40,.24)")
    line = d["line"]
    acc, acc_ink, acc_soft = d["accent"], d["accent_ink"], d["accent_soft"]
    status = d["status"]
    cat = d["categorical"]
    head_bg = d["header"] if header_style == "brand" else d["surface"]
    head_ink = d["header_ink"] if header_style == "brand" else d["ink"]
    head_sub = d["header_sub"] if header_style == "brand" else d["muted"]
    on_brand = header_style == "brand" and head_ink == "#FFFFFF"
    chip_bg = "rgba(255,255,255,.96)"
    tab_bg = "rgba(255,255,255,.04)" if dark else "rgba(255,255,255,.7)"
    css = f"""
<style>{app_theme.FONTS_CSS}{app_theme.MOTION_CSS}
:root {{ --ld-ink:{d['ink']}; --ld-ink2:{d['ink2']}; --ld-muted:{d['muted']}; --ld-acc:{acc}; --ld-line:{line}; --ld-surface:{d['surface']};
  --lc-skel-a:{'rgba(255,255,255,.05)' if dark else 'rgba(16,24,40,.05)'}; --lc-skel-b:{'rgba(255,255,255,.11)' if dark else 'rgba(16,24,40,.10)'}; --lc-muted:{d['muted']}; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"], [data-testid="stToolbar"] {{ display:none !important; }}
.stApp {{ background:{bg_css or design.css_background(d)} !important; background-attachment:fixed !important; }}
.stApp, .stApp button, .stApp input, .stApp p, .stApp label, .stApp li {{ font-family:{app_theme.FONT_STACK}; }}
.block-container {{ max-width:{'100%' if presentation else '1600px'} !important; padding:{'0.6rem 2.2rem 2rem' if presentation else '0.9rem 1.6rem 3rem'} !important; }}
.stApp p, .stApp li, .stApp label, .stApp .stMarkdown, .stApp [data-testid="stCaptionContainer"] {{ color:{d['ink2']}; }}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ color:{d['ink']}; }}

/* ---------- identity header */
.ld-head {{ position:relative; overflow:hidden; background:{head_bg}; background-size:180% 180%; border:1px solid {line}; border-radius:{r}; padding:16px 22px;
  display:flex; align-items:center; gap:18px; box-shadow:{shadow}; margin-bottom:10px; animation:lc-rise .45s cubic-bezier(.2,.7,.2,1) both{', lc-drift 26s ease-in-out infinite' if header_style == 'brand' and not minimal else ''}; }}
.ld-head:after {{ content:""; position:absolute; right:-80px; top:-120px; width:320px; height:320px; border-radius:50%;
  background:radial-gradient(circle, {C.rgba(cat[1], .30 if on_brand else .16)}, transparent 70%); pointer-events:none; display:{'none' if minimal else 'block'}; }}
.ld-head .logo {{ flex:none; display:flex; align-items:center; justify-content:center; height:56px; min-width:56px; max-width:190px; padding:{'7px 10px' if on_brand or dark else '0'};
  border-radius:{'12px' if not minimal else '4px'}; background:{chip_bg if (on_brand or dark) else 'transparent'}; box-shadow:{'0 6px 18px -8px rgba(0,0,0,.45)' if on_brand or dark else 'none'}; }}
.ld-head .logo img {{ max-height:42px; max-width:170px; object-fit:contain; display:block; }}
.ld-head .t {{ font-size:{'1.7rem' if presentation else '1.38rem'}; font-weight:{'600' if minimal else '700'}; color:{head_ink}; line-height:1.18; letter-spacing:-.02em; }}
.ld-head .s {{ font-size:.82rem; color:{head_sub}; margin-top:4px; }}
.ld-head .org {{ display:inline-block; font-size:.68rem; letter-spacing:.12em; text-transform:uppercase; font-weight:700; color:{head_sub}; margin-bottom:3px; }}
.ld-head .tag {{ font-size:.86rem; color:{head_ink}; opacity:.9; font-weight:500; margin-top:2px; }}
.ld-head .badge {{ position:relative; margin-left:auto; font-size:.72rem; color:{head_sub}; text-align:right; white-space:nowrap; line-height:1.5; }}
.ld-pagehead {{ margin:10px 0 6px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; animation:lc-fade .4s ease both; }}
.ld-pagehead .pt {{ font-size:1.12rem; font-weight:650; color:{d['ink']}; letter-spacing:-.01em; }}
.ld-pagehead .pp {{ font-size:.84rem; color:{d['muted']}; }}
.ld-pagehead .lay {{ margin-left:auto; font-size:.68rem; text-transform:uppercase; letter-spacing:.1em; color:{d['muted']}; }}

/* ---------- KPI cards (variant set by composition) */
.ld-kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax({'150px' if presentation else '170px'}, 1fr)); gap:12px; margin:4px 0 12px; }}
.ld-kpi {{ position:relative; overflow:hidden; background:{d['surface']}; border:1px solid {line}; border-radius:{r}; padding:14px 16px 13px; box-shadow:{shadow};
  min-height:112px; backdrop-filter:{blur}; -webkit-backdrop-filter:{blur}; transition:transform .2s cubic-bezier(.2,.7,.2,1), box-shadow .2s ease, border-color .2s ease;
  animation:lc-rise .45s cubic-bezier(.2,.7,.2,1) both; }}
.ld-kpis .ld-kpi:nth-child(2) {{ animation-delay:45ms; }} .ld-kpis .ld-kpi:nth-child(3) {{ animation-delay:90ms; }} .ld-kpis .ld-kpi:nth-child(4) {{ animation-delay:135ms; }}
.ld-kpis .ld-kpi:nth-child(5) {{ animation-delay:180ms; }} .ld-kpis .ld-kpi:nth-child(n+6) {{ animation-delay:220ms; }}
.ld-kpi:hover {{ transform:translateY(-2px); box-shadow:{hover_shadow}; }}
.ld-kpi .top {{ display:flex; gap:10px; align-items:center; }}
.ld-kpi .ic {{ width:34px; height:34px; border-radius:{'50%' if d['theme'] in ('corporate', 'vibrant') else '10px'}; display:flex; align-items:center; justify-content:center; flex:none; }}
.ld-kpi .lb {{ font-size:.78rem; color:{d['ink2']}; font-weight:600; line-height:1.25; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.ld-kpi .v {{ font-size:1.85rem; font-weight:700; color:{d['ink']}; margin-top:10px; line-height:1.05; font-variant-numeric:tabular-nums; letter-spacing:-.025em; }}
.ld-kpi .v.sm {{ font-size:1.05rem; margin-top:12px; letter-spacing:0; }}
.ld-kpi .s {{ font-size:.74rem; color:{d['muted']}; margin-top:5px; }}
.ld-kpi.tile:before {{ content:""; position:absolute; left:0; right:0; top:0; height:3px; background:linear-gradient(90deg, var(--k), transparent 85%); }}
.ld-kpi .meter {{ height:5px; border-radius:5px; background:{'rgba(255,255,255,.08)' if dark else 'rgba(16,24,40,.07)'}; margin-top:9px; overflow:hidden; }}
.ld-kpi .meter i {{ display:block; height:100%; border-radius:5px; background:linear-gradient(90deg, var(--k), {C.rgba(cat[1], .9)}); transform-origin:left;
  animation:lc-grow .8s cubic-bezier(.2,.7,.2,1) .15s both; }}
.ld-kpi.ring {{ display:flex; align-items:center; gap:14px; }}
.ld-kpi.ring svg {{ flex:none; }}
.ld-kpi.ring .arc {{ animation:lc-ring 1s cubic-bezier(.2,.7,.2,1) .1s both; }}
.ld-kpi.ring .v {{ margin-top:2px; }}
.ld-kpis.strip {{ gap:0; background:{d['surface']}; border:1px solid {line}; border-radius:{r}; box-shadow:{shadow}; backdrop-filter:{blur}; -webkit-backdrop-filter:{blur}; overflow:hidden;
  animation:lc-rise .45s cubic-bezier(.2,.7,.2,1) both; }}
.ld-kpis.strip .ld-kpi {{ background:transparent; border:none; border-radius:0; box-shadow:none; backdrop-filter:none; -webkit-backdrop-filter:none; border-right:1px solid {line}; animation:lc-fade .5s ease both; }}
.ld-kpis.strip .ld-kpi:last-child {{ border-right:none; }}
.ld-kpis.strip .ld-kpi:hover {{ transform:none; background:{'rgba(255,255,255,.03)' if dark else 'rgba(16,24,40,.02)'}; }}
.ld-kpis.inline {{ gap:0; border-top:1px solid {line}; border-bottom:1px solid {line}; }}
.ld-kpis.inline .ld-kpi {{ background:transparent; border:none; border-radius:0; box-shadow:none; backdrop-filter:none; min-height:0; padding:12px 14px; border-left:1px solid {line}; }}
.ld-kpis.inline .ld-kpi:first-child {{ border-left:none; }}
.ld-kpis.inline .ld-kpi .ic {{ display:none; }}
.ld-kpis.inline .ld-kpi .v {{ font-size:1.55rem; font-weight:600; }}

/* ---------- cards */
[class*="st-key-ldcard_"], [class*="st-key-ldhero_"] {{ background:{d['surface']} !important; border:1px solid {line} !important; border-radius:{r} !important; box-shadow:{shadow};
  padding:14px 16px 8px !important; backdrop-filter:{blur}; -webkit-backdrop-filter:{blur}; transition:box-shadow .25s ease, border-color .25s ease, transform .25s cubic-bezier(.2,.7,.2,1);
  animation:lc-rise .5s cubic-bezier(.2,.7,.2,1) both; }}
[class*="st-key-ldcard_"]:hover, [class*="st-key-ldhero_"]:hover {{ box-shadow:{hover_shadow}; border-color:{C.rgba(acc, .35)} !important; }}
[class*="st-key-ldhero_"] {{ border-top:2px solid {acc} !important; }}
[class*="st-key-ldside_"] {{ background:{d['surface']} !important; border:1px solid {line} !important; border-radius:{r} !important; box-shadow:{shadow};
  padding:14px 16px !important; backdrop-filter:{blur}; -webkit-backdrop-filter:{blur}; animation:lc-rise .5s cubic-bezier(.2,.7,.2,1) .1s both; }}
.ld-ct {{ font-weight:650; font-size:.98rem; color:{d['ink']}; margin:0; line-height:1.3; letter-spacing:-.005em; }}
[class*="st-key-ldhero_"] .ld-ct {{ font-size:1.12rem; }}
.ld-cs {{ font-size:.78rem; color:{d['muted']}; margin:3px 0 0; }}
.ld-lead {{ font-size:.84rem; color:{d['ink2']}; margin:6px 0 2px; padding-left:10px; border-left:2px solid {C.rgba(acc, .65)}; }}
.ld-foot {{ font-size:.72rem; color:{d['muted']}; margin-top:-4px; }}
.ld-ins {{ border-left:2px solid {acc}; padding:3px 0 3px 12px; margin:0 0 12px; animation:lc-rise .4s cubic-bezier(.2,.7,.2,1) both; transition:background .2s ease; border-radius:0 8px 8px 0; }}
.ld-ins:hover {{ background:{C.rgba(acc, .07)}; }}
.ld-ins .h {{ font-size:.87rem; font-weight:650; color:{d['ink']}; }}
.ld-ins .b {{ font-size:.82rem; color:{d['ink2']}; margin-top:2px; }}
.ld-findings {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:4px 18px; }}
.ld-sec {{ font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; font-weight:700; color:{d['muted']}; margin:10px 0 2px; }}
.ld-tag {{ display:inline-block; font-size:.66rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; border-radius:999px; padding:1px 8px; margin-right:6px; }}
.ld-tag.v {{ background:{C.rgba(status['good'], .14)}; color:{status['good']}; }}
.ld-tag.i {{ background:{acc_soft}; color:{C.with_lightness_for_contrast(acc, d['solid'], 4.5)}; }}
.ld-tag.r {{ background:{C.rgba(status['warning'], .16)}; color:{C.with_lightness_for_contrast(status['warning'], d['solid'], 4.5)}; }}
.ld-tag.l {{ background:rgba(137,135,129,.16); color:{d['muted']}; }}
.ld-q {{ display:inline-flex; align-items:center; gap:6px; font-size:.72rem; color:inherit; }}
.ld-q i {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
[data-testid="stPlotlyChart"] {{ background:transparent !important; border:none !important; box-shadow:none !important; padding:0 !important; animation:lc-fade .6s ease both; }}

/* ---------- controls */
[data-testid="stExpander"] details {{ background:{d['surface2']} !important; border-color:{line} !important; border-radius:10px !important; }}
[data-testid="stExpander"] summary p {{ color:{d['ink2']} !important; font-size:.84rem; }}
.stApp [data-testid="stIconMaterial"] {{ color:{d['ink2']}; }}
.stApp [data-testid="stWidgetLabel"] p {{ color:{d['muted']} !important; font-size:.72rem !important; text-transform:uppercase; letter-spacing:.07em; font-weight:600; }}
.stApp button[data-variant="segmented_control"], .stApp [data-testid^="stBaseButton-segmented_control"] {{ border-radius:999px !important; background:{tab_bg} !important; border:1px solid {line} !important;
  margin:2px 3px !important; transition:background .2s ease, border-color .2s ease, transform .12s ease, box-shadow .2s ease; backdrop-filter:{blur}; }}
.stApp button[data-variant="segmented_control"]:hover, .stApp [data-testid^="stBaseButton-segmented_control"]:hover {{ border-color:{C.rgba(acc, .55)} !important; transform:translateY(-1px); }}
.stApp button[data-variant="segmented_control"] p, .stApp [data-testid^="stBaseButton-segmented_control"] p {{ color:{d['ink2']} !important; font-size:.84rem; }}
.stApp button[data-variant="segmented_control"][aria-checked="true"], .stApp [data-testid="stBaseButton-segmented_controlActive"] {{ background:{acc} !important; border-color:{acc} !important;
  box-shadow:0 8px 20px -10px {C.rgba(acc, .9)}; }}
.stApp button[data-variant="segmented_control"][aria-checked="true"] p, .stApp [data-testid="stBaseButton-segmented_controlActive"] p {{ color:{acc_ink} !important; font-weight:600; }}
.stApp [data-testid="stButtonGroup"] [role="radiogroup"] {{ flex-wrap:wrap; gap:0; }}
.stApp [data-testid="stSelectbox"] [role="group"], .stApp [data-testid="stMultiSelect"] [role="group"], .stApp [data-testid="stDateInput"] [role="group"],
.stApp [data-testid="stMultiSelect"] > div > div, .stApp [data-testid="stDateInput"] > div > div, .stApp [data-testid="stTextInput"] input,
.stApp [data-baseweb="select"] > div, .stApp [data-baseweb="input"] > div, .stApp [data-baseweb="base-input"] {{
  background:{d['surface']} !important; border-color:{line} !important; color:{d['ink']} !important; transition:border-color .2s ease, box-shadow .2s ease; }}
.stApp [data-baseweb="select"] > div:focus-within, .stApp [data-baseweb="input"]:focus-within {{ box-shadow:0 0 0 3px {C.rgba(acc, .22)}; border-color:{acc} !important; }}
.stApp [data-testid="stSelectbox"] input, .stApp [data-testid="stMultiSelect"] input, .stApp [data-testid="stDateInput"] input {{ color:{d['ink']} !important; background:transparent !important; }}
.stApp [data-testid="stSelectbox"] [role="group"] *, .stApp [data-testid="stMultiSelect"] [role="group"] *, .stApp [data-testid="stDateInput"] [role="group"] * {{ color:{d['ink2']} !important; opacity:1 !important; }}
.stApp input::placeholder {{ color:{d['muted']} !important; opacity:1 !important; }}
.stApp [data-testid="stSelectbox"] svg, .stApp [data-testid="stMultiSelect"] svg, .stApp [data-testid="stDateInput"] svg {{ fill:{d['muted']} !important; color:{d['muted']} !important; }}
[data-baseweb="popover"] > div, [role="listbox"], [data-baseweb="menu"], [role="dialog"] {{ background:{d['solid']} !important; color:{d['ink']} !important; }}
[data-testid="stPopoverBody"] {{ background:{d['solid']} !important; border:1px solid {line} !important; }}
[data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] label, [data-testid="stPopoverBody"] span {{ color:{d['ink2']}; }}
[role="option"] {{ color:{d['ink']} !important; }}
.stApp [data-baseweb="tag"] {{ background:{acc_soft} !important; animation:lc-rise .25s ease both; }}
.stApp [data-baseweb="tag"] span {{ color:{d['ink']} !important; }}
.stApp .stButton button, .stApp .stDownloadButton button, .stApp [data-testid="stPopover"] button {{ background:{d['surface']} !important; border-color:{line} !important; color:{d['ink']} !important;
  border-radius:10px; backdrop-filter:{blur}; transition:transform .12s ease, border-color .2s ease, background .2s ease; }}
.stApp .stButton button:hover, .stApp .stDownloadButton button:hover, .stApp [data-testid="stPopover"] button:hover {{ border-color:{C.rgba(acc, .6)} !important; transform:translateY(-1px); }}
.stApp .stButton button:active, .stApp [data-testid="stPopover"] button:active {{ transform:scale(.98); }}
.stApp .stButton button p, .stApp .stDownloadButton button p, .stApp [data-testid="stPopover"] button p {{ color:{d['ink']} !important; }}
.stApp [data-testid="stBaseButton-primary"] {{ background:{acc} !important; border-color:{acc} !important; }}
.stApp [data-testid="stBaseButton-primary"] p {{ color:{acc_ink} !important; }}
.stApp [data-testid="stBaseButton-tertiary"] {{ background:transparent !important; border:none !important; }}
.stApp [data-testid="stBaseButton-tertiary"] p {{ color:{C.with_lightness_for_contrast(acc, d['solid'], 4.5)} !important; }}
.stApp [data-testid="stAlert"] {{ background:{d['surface2']} !important; border-radius:12px; }}
.stApp [data-testid="stAlert"] p {{ color:{d['ink']} !important; }}
[data-testid="stDataFrame"] {{ border-radius:10px; overflow:hidden; }}
{'' if dark else '.stApp [data-testid="stDataFrame"] {filter:invert(0.94) hue-rotate(180deg);}'}
@media (max-width: 900px) {{ .ld-head {{ flex-wrap:wrap; }} .ld-head .badge {{ margin-left:0; text-align:left; }} .ld-kpis.strip .ld-kpi {{ border-right:none; border-bottom:1px solid {line}; }} }}
@media print {{ .ld-noprint {{ display:none !important; }} .stApp {{ background:#fff !important; }} }}
</style>"""
    st.markdown(css, unsafe_allow_html=True)


def logo_img(uri: str | None, alt: str = "Organisation logo") -> str:
    """The organisation's own logo, always shown as an <img> data URI (SVG scripts never run in <img>)."""
    if not uri:
        return ""
    return f'<div class="logo"><img alt="{app_theme.esc(alt)}" src="{uri}"/></div>'
