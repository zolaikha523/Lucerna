"""Lucerna design system for Streamlit (the *application* theme, system A).

Centralised tokens (colour roles, type scale, spacing, radius, elevation, motion) feed one CSS layer used by every
page: login, home, sidebar, navigation, data pages, studio, qualitative, mixed methods, reports and settings.
Dashboards carry their own organisation brand (system B, `brand/`) and visualization theme (system C,
`dash_theme.py`); this file never styles a dashboard canvas.

The native Streamlit theme in `.streamlit/config.toml` is set to the same dark navy tokens, so widgets, menus, dialogs
and tables match without fragile overrides. The optional light mode is a CSS layer on top.
Motion is CSS only (no JavaScript, no timers) and is switched off entirely under `prefers-reduced-motion`.
"""
from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path

import streamlit as st

ICON_DIR = Path(__file__).resolve().parent / "static" / "icons"

# ---------------------------------------------------------------- tokens
BRAND = {"navy": "#0A1430", "azure": "#2F6BFF", "teal": "#16C2B0", "violet": "#8B6CFF", "spark": "#FFC56B", "slate": "#5B6B85", "mist": "#9DB0CC"}
TOKENS = {
    "dark": {"bg": "#070D1C", "bg2": "#0B1530", "surface": "rgba(20,31,58,.62)", "surface_solid": "#111B33", "surface2": "#16233F", "ink": "#EEF3FB",
             "ink2": "#C3CEDF", "muted": "#8E9CB5", "line": "rgba(255,255,255,.08)", "line_solid": "#22304D", "navy": "#0A1430", "deep": "#6E9BFF",
             "teal": "#2CD3C0", "accent": "#6E9BFF", "violet": "#A48CFF",
             "shadow": "0 1px 0 rgba(255,255,255,.04) inset, 0 16px 36px -18px rgba(0,0,0,.65)", "sidebar": "#060B18", "sidebar_ink": "#C9D3E3"},
    "light": {"bg": "#F4F6FB", "bg2": "#EAF0FA", "surface": "rgba(255,255,255,.86)", "surface_solid": "#FFFFFF", "surface2": "#F2F5FA", "ink": "#0D1730",
              "ink2": "#3F4B63", "muted": "#66738A", "line": "#E1E6EF", "line_solid": "#E1E6EF", "navy": "#0A1430", "deep": "#1F4FD1",
              "teal": "#0E9C8D", "accent": "#2F6BFF", "violet": "#6A4FE0",
              "shadow": "0 1px 2px rgba(13,23,48,.04), 0 12px 30px -16px rgba(13,23,48,.16)", "sidebar": "#0A1430", "sidebar_ink": "#D6DEEB"},
}
TYPE = {"display": "2.05rem", "h1": "1.6rem", "h2": "1.32rem", "h3": "1.05rem", "body": ".94rem", "small": ".82rem", "micro": ".72rem"}
SPACE = {"1": "4px", "2": "8px", "3": "12px", "4": "16px", "5": "20px", "6": "24px", "8": "32px", "10": "40px"}
RADIUS = {"sm": "8px", "md": "12px", "lg": "16px", "xl": "22px", "pill": "999px"}
MOTION = {"fast": "120ms", "base": "200ms", "slow": "420ms", "ease": "cubic-bezier(.2,.7,.2,1)"}
STATUS = {"good": ("#22B573", "circle-check"), "warning": ("#E0A030", "triangle-alert"), "critical": ("#E5484D", "circle-x"), "info": ("#5B8DFF", "info")}
FONT_STACK = "'Inter','Vazirmatn','Segoe UI','Noto Sans Arabic',system-ui,sans-serif"


def mode() -> str:
    return st.session_state.get("ui_mode", "dark")


def tokens() -> dict:
    return TOKENS[mode()]


@lru_cache(maxsize=256)
def _icon_svg(name: str) -> str:
    p = ICON_DIR / f"{name}.svg"
    if not p.exists():
        p = ICON_DIR / "info.svg"
    svg = p.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    return " ".join(svg.split())


def icon(name: str, size: int = 18, color: str = "currentColor", stroke: float = 1.8) -> str:
    svg = _icon_svg(name)
    svg = svg.replace('width="24"', f'width="{size}"').replace('height="24"', f'height="{size}"')
    svg = svg.replace('stroke="currentColor"', f'stroke="{color}"').replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return svg.replace("<svg", '<svg aria-hidden="true" focusable="false"', 1)


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


FONTS_CSS = """
@font-face {font-family:'Inter'; src:url('app/static/fonts/inter-latin-400-normal.woff2') format('woff2'); font-weight:400; font-display:swap;}
@font-face {font-family:'Inter'; src:url('app/static/fonts/inter-latin-500-normal.woff2') format('woff2'); font-weight:500; font-display:swap;}
@font-face {font-family:'Inter'; src:url('app/static/fonts/inter-latin-600-normal.woff2') format('woff2'); font-weight:600; font-display:swap;}
@font-face {font-family:'Inter'; src:url('app/static/fonts/inter-latin-700-normal.woff2') format('woff2'); font-weight:700; font-display:swap;}
@font-face {font-family:'Vazirmatn'; src:url('app/static/fonts/vazirmatn-arabic-400-normal.woff2') format('woff2'); font-weight:400; unicode-range:U+0600-06FF,U+0750-077F,U+FB50-FDFF,U+FE70-FEFF;}
@font-face {font-family:'Vazirmatn'; src:url('app/static/fonts/vazirmatn-arabic-600-normal.woff2') format('woff2'); font-weight:600; unicode-range:U+0600-06FF,U+0750-077F,U+FB50-FDFF,U+FE70-FEFF;}
"""

# Shared motion vocabulary (also used by dashboards). Entrance animations run once when an element first appears.
MOTION_CSS = """
@keyframes lc-rise { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
@keyframes lc-fade { from { opacity:0; } to { opacity:1; } }
@keyframes lc-shimmer { 0% { background-position:-480px 0; } 100% { background-position:480px 0; } }
@keyframes lc-drift { 0% { background-position:0% 50%; } 50% { background-position:100% 50%; } 100% { background-position:0% 50%; } }
@keyframes lc-pulse { 0%,100% { opacity:.55; transform:scale(.92); } 50% { opacity:1; transform:scale(1); } }
@keyframes lc-bar { 0% { transform:translateX(-100%); } 100% { transform:translateX(260%); } }
@keyframes lc-grow { from { transform:scaleX(0); } to { transform:scaleX(1); } }
@keyframes lc-ring { from { stroke-dashoffset:var(--lc-ring-len,100); } }
.lc-skel { border-radius:12px; background:linear-gradient(90deg, var(--lc-skel-a) 0px, var(--lc-skel-b) 160px, var(--lc-skel-a) 320px);
  background-size:960px 100%; animation:lc-shimmer 1.4s linear infinite; }
.lc-loader { display:flex; align-items:center; gap:14px; padding:18px 4px; color:var(--lc-muted); font-size:.86rem; animation:lc-fade .3s ease both; }
.lc-loader .mark { position:relative; width:34px; height:34px; flex:none; }
.lc-loader .mark svg { width:34px; height:34px; display:block; }
.lc-loader .mark .sp { animation:lc-pulse 1.3s ease-in-out infinite; transform-origin:46.5px 19.5px; }
.lc-loader .track { position:relative; overflow:hidden; height:3px; width:160px; border-radius:3px; background:var(--lc-skel-a); margin-top:6px; }
.lc-loader .track:after { content:""; position:absolute; inset:0; width:40%; border-radius:3px; background:linear-gradient(90deg,#2F6BFF,#16C2B0); animation:lc-bar 1.2s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) {
  *, *:before, *:after { animation-duration:.001ms !important; animation-iteration-count:1 !important; transition-duration:.001ms !important; scroll-behavior:auto !important; }
  .lc-skel { animation:none !important; }
}
"""


def inject() -> None:
    t = tokens()
    dark = mode() == "dark"
    css = f"""<style>{FONTS_CSS}{MOTION_CSS}
:root {{ --lc-bg:{t['bg']}; --lc-surface:{t['surface']}; --lc-surface-solid:{t['surface_solid']}; --lc-surface2:{t['surface2']}; --lc-ink:{t['ink']};
  --lc-ink2:{t['ink2']}; --lc-muted:{t['muted']}; --lc-line:{t['line']}; --lc-teal:{t['teal']}; --lc-accent:{t['accent']}; --lc-deep:{t['deep']};
  --lc-violet:{t['violet']}; --lc-shadow:{t['shadow']}; --lc-r-sm:{RADIUS['sm']}; --lc-r-md:{RADIUS['md']}; --lc-r-lg:{RADIUS['lg']}; --lc-r-xl:{RADIUS['xl']};
  --lc-fast:{MOTION['fast']}; --lc-base:{MOTION['base']}; --lc-slow:{MOTION['slow']}; --lc-ease:{MOTION['ease']};
  --lc-skel-a:{'rgba(255,255,255,.05)' if dark else 'rgba(13,23,48,.05)'}; --lc-skel-b:{'rgba(255,255,255,.11)' if dark else 'rgba(13,23,48,.10)'}; }}
html, body, .stApp, button, input, textarea, select, p, label, h1, h2, h3, h4, h5, h6, li, td, th {{ font-family:{FONT_STACK}; }}
.stApp {{ background:
   radial-gradient(1100px 600px at 100% -10%, {'rgba(47,107,255,.13)' if dark else 'rgba(47,107,255,.07)'}, transparent 60%),
   radial-gradient(900px 600px at -10% 110%, {'rgba(22,194,176,.08)' if dark else 'rgba(22,194,176,.05)'}, transparent 60%),
   linear-gradient(180deg, {t['bg']} 0%, {t['bg2']} 100%) fixed; color:var(--lc-ink); }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ max-width:1500px; padding-top:1.4rem; padding-bottom:4rem; }}
h1,h2,h3,h4 {{ color:var(--lc-ink); letter-spacing:-.015em; }}
p, li, label, .stMarkdown, [data-testid="stCaptionContainer"] {{ color:var(--lc-ink2); }}
[data-testid="stCaptionContainer"] {{ color:var(--lc-muted) !important; }}
a {{ color:var(--lc-accent); }}

/* ---------- sidebar & navigation */
[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{t['sidebar']} 0%, #08122A 100%); border-right:1px solid rgba(255,255,255,.05); }}
[data-testid="stSidebar"] * {{ color:{t['sidebar_ink']}; }}
[data-testid="stSidebarContent"] {{ display:flex; flex-direction:column; }}
[data-testid="stSidebarHeader"] {{ order:-3; padding-top:1.1rem; }}
[data-testid="stSidebarUserContent"] {{ order:-2; padding-bottom:.25rem !important; padding-top:0 !important; }}
[data-testid="stSidebarNav"] {{ order:-1; }}
[data-testid="stSidebarHeader"] img {{ height:2.05rem !important; max-width:none; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ position:relative; border-radius:10px; margin:1px 8px; padding-left:12px;
   transition:background var(--lc-base) var(--lc-ease), transform var(--lc-fast) var(--lc-ease); }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {{ background:rgba(255,255,255,.05); transform:translateX(2px); }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:active {{ transform:scale(.985); }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{ background:linear-gradient(90deg, rgba(47,107,255,.22), rgba(22,194,176,.10)); }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"]:before {{ content:""; position:absolute; left:0; top:8px; bottom:8px; width:3px;
   border-radius:3px; background:linear-gradient(180deg,#2F6BFF,#16C2B0); animation:lc-fade var(--lc-slow) ease both; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] span {{ color:#FFFFFF !important; font-weight:600; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {{ border-color:rgba(255,255,255,.07); }}
[data-testid="stSidebar"] header, [data-testid="stSidebarNavSectionHeader"] {{ color:#7D8AA3 !important; text-transform:uppercase; letter-spacing:.1em; font-size:.66rem; }}
[data-testid="stSidebar"] [data-testid="stPopover"] button, [data-testid="stSidebar"] .stButton button {{ background:rgba(255,255,255,.05) !important; border-color:rgba(255,255,255,.10) !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background:rgba(255,255,255,.05) !important; border-color:rgba(255,255,255,.10) !important; color:{t['sidebar_ink']} !important; }}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ color:#7D8AA3 !important; font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; font-weight:600; }}

/* ---------- page furniture */
.lc-hero {{ position:relative; overflow:hidden; border-radius:var(--lc-r-xl); padding:28px 32px; margin-bottom:18px; color:#fff;
   background:linear-gradient(120deg,#0B1A3D 0%,#13307A 38%,#1747B8 62%,#0F7F8A 100%); background-size:220% 220%;
   animation:lc-drift 22s ease-in-out infinite, lc-rise var(--lc-slow) var(--lc-ease) both; box-shadow:0 24px 60px -30px rgba(47,107,255,.55); }}
.lc-hero:before {{ content:""; position:absolute; inset:0; background:radial-gradient(520px 260px at 85% 0%, rgba(255,197,107,.20), transparent 60%),
   radial-gradient(600px 300px at 0% 120%, rgba(22,194,176,.28), transparent 60%); pointer-events:none; }}
.lc-hero:after {{ content:""; position:absolute; right:34px; top:30px; width:12px; height:12px; border-radius:50%; background:#FFC56B;
   box-shadow:0 0 0 6px rgba(255,197,107,.16), 0 0 28px 6px rgba(255,197,107,.45); animation:lc-pulse 3.2s ease-in-out infinite; }}
.lc-hero h1 {{ position:relative; color:#fff; margin:0; font-size:{TYPE['h1']}; font-weight:650; letter-spacing:-.02em; }}
.lc-hero p {{ position:relative; color:#D3DEF5; margin:.4rem 0 0; font-size:.95rem; max-width:880px; }}
.lc-eyebrow {{ position:relative; display:flex; align-items:center; gap:8px; font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; color:#9FEDE2; font-weight:600; margin-bottom:8px; }}
.lc-page-title {{ display:flex; align-items:center; gap:12px; margin:0 0 4px; animation:lc-rise var(--lc-slow) var(--lc-ease) both; }}
.lc-page-title .ic {{ width:40px; height:40px; border-radius:12px; display:flex; align-items:center; justify-content:center; flex:none;
   background:linear-gradient(135deg, rgba(47,107,255,.22), rgba(22,194,176,.16)); border:1px solid var(--lc-line); box-shadow:var(--lc-shadow); }}
.lc-page-title h2 {{ margin:0; font-size:{TYPE['h2']}; font-weight:650; color:var(--lc-ink); letter-spacing:-.015em; }}
.lc-sub {{ color:var(--lc-muted); font-size:.92rem; margin:0 0 18px 52px; animation:lc-fade var(--lc-slow) ease both; }}

/* ---------- cards & KPIs */
.lc-kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(176px, 1fr)); gap:12px; margin:2px 0 6px; }}
.lc-kpi {{ position:relative; overflow:hidden; background:var(--lc-surface); border:1px solid var(--lc-line); border-radius:var(--lc-r-lg); padding:16px 18px;
   box-shadow:var(--lc-shadow); min-height:112px; backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
   transition:transform var(--lc-base) var(--lc-ease), box-shadow var(--lc-base) var(--lc-ease), border-color var(--lc-base) ease;
   animation:lc-rise var(--lc-slow) var(--lc-ease) both; }}
.lc-kpis .lc-kpi:nth-child(2) {{ animation-delay:40ms; }} .lc-kpis .lc-kpi:nth-child(3) {{ animation-delay:80ms; }}
.lc-kpis .lc-kpi:nth-child(4) {{ animation-delay:120ms; }} .lc-kpis .lc-kpi:nth-child(n+5) {{ animation-delay:160ms; }}
.lc-kpi:before {{ content:""; position:absolute; left:0; right:0; top:0; height:2px; background:linear-gradient(90deg, var(--lc-k, #2F6BFF), transparent 80%); opacity:.9; }}
.lc-kpi:hover {{ transform:translateY(-2px); border-color:{'rgba(255,255,255,.14)' if dark else '#CBD5E6'}; }}
.lc-kpi .top {{ display:flex; justify-content:space-between; align-items:center; gap:8px; color:var(--lc-muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; font-weight:600; }}
.lc-kpi .ic {{ width:30px; height:30px; border-radius:9px; display:flex; align-items:center; justify-content:center; flex:none; }}
.lc-kpi .v.sm {{ font-size:1.05rem; line-height:1.3; margin-top:12px; }}
.lc-kpi .top span:first-child {{ overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.lc-kpi .v {{ font-size:1.8rem; font-weight:700; color:var(--lc-ink); margin-top:8px; line-height:1.1; font-variant-numeric:tabular-nums; letter-spacing:-.02em; animation:lc-fade .5s ease both; }}
.lc-kpi .s {{ color:var(--lc-muted); font-size:.78rem; margin-top:4px; }}
.lc-card {{ background:var(--lc-surface); border:1px solid var(--lc-line); border-radius:var(--lc-r-lg); padding:16px 18px; box-shadow:var(--lc-shadow); margin-bottom:12px;
   animation:lc-rise var(--lc-slow) var(--lc-ease) both; }}
.lc-card h4 {{ margin:0 0 6px; font-size:.98rem; display:flex; gap:8px; align-items:center; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius:var(--lc-r-lg) !important; }}
.lc-muted {{ color:var(--lc-muted); font-size:.85rem; }}
.lc-pill {{ display:inline-flex; align-items:center; gap:5px; border-radius:999px; padding:2px 10px; font-size:.74rem; font-weight:600; margin:2px 4px 2px 0; border:1px solid transparent; }}
.lc-quote {{ border-left:3px solid var(--lc-teal); background:var(--lc-surface2); padding:12px 16px; border-radius:0 12px 12px 0; margin:8px 0; color:var(--lc-ink); font-size:.96rem; }}
.lc-quote .src {{ color:var(--lc-muted); font-size:.78rem; margin-top:6px; }}
.lc-empty {{ text-align:center; padding:40px 20px; border:1.5px dashed {'rgba(255,255,255,.12)' if dark else '#D5DCE8'}; border-radius:var(--lc-r-xl); background:var(--lc-surface);
   animation:lc-rise var(--lc-slow) var(--lc-ease) both; }}
.lc-empty h4 {{ margin:10px 0 4px; color:var(--lc-ink); }}
.lc-chart-title {{ display:flex; align-items:center; gap:8px; font-weight:600; color:var(--lc-ink); font-size:.96rem; margin:2px 0 0; }}
.lc-chart-sub {{ color:var(--lc-muted); font-size:.8rem; margin:2px 0 4px; }}
.lc-note {{ color:var(--lc-muted); font-size:.75rem; margin-top:-6px; }}
.lc-steps {{ display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 16px; }}
.lc-step {{ display:flex; align-items:center; gap:6px; font-size:.78rem; padding:5px 11px; border-radius:999px; background:var(--lc-surface); border:1px solid var(--lc-line); color:var(--lc-muted); }}
.lc-step.done {{ color:#3FD08A; border-color:rgba(34,181,115,.35); background:rgba(34,181,115,.08); }}

/* ---------- native widgets */
[data-testid="stMetric"] {{ background:var(--lc-surface); border:1px solid var(--lc-line); border-radius:14px; padding:12px 14px; }}
[data-testid="stExpander"] details {{ border-radius:14px; border-color:var(--lc-line); background:var(--lc-surface); }}
[data-testid="stExpander"] summary {{ transition:background var(--lc-base) ease; border-radius:14px; }}
[data-testid="stExpander"] summary:hover {{ background:{'rgba(255,255,255,.03)' if dark else 'rgba(13,23,48,.03)'}; }}
.stTabs [data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid var(--lc-line); }}
.stTabs [data-baseweb="tab"] {{ border-radius:10px 10px 0 0; padding:8px 14px; transition:color var(--lc-base) ease, background var(--lc-base) ease; }}
.stTabs [data-baseweb="tab"]:hover {{ background:{'rgba(255,255,255,.04)' if dark else 'rgba(13,23,48,.04)'}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:linear-gradient(90deg,#2F6BFF,#16C2B0) !important; height:2px; transition:all var(--lc-slow) var(--lc-ease) !important; }}
.stTabs [data-baseweb="tab-panel"] {{ animation:lc-fade var(--lc-slow) ease both; }}
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
   background:linear-gradient(135deg,#2F6BFF 0%,#2563EB 45%,#12A898 100%) !important; background-size:160% 160% !important; border:none !important;
   box-shadow:0 8px 22px -10px rgba(47,107,255,.75); transition:background-position var(--lc-slow) var(--lc-ease), transform var(--lc-fast) var(--lc-ease), box-shadow var(--lc-base) ease; }}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{ background-position:100% 50% !important; box-shadow:0 10px 26px -10px rgba(22,194,176,.75); }}
button[kind="primary"] p, [data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p {{ color:#fff !important; font-weight:600; }}
.stButton button, .stDownloadButton button, [data-testid="stPopover"] button, [data-testid="stFormSubmitButton"] button {{ border-radius:10px;
   transition:transform var(--lc-fast) var(--lc-ease), background var(--lc-base) ease, border-color var(--lc-base) ease, box-shadow var(--lc-base) ease; }}
.stButton button:hover, .stDownloadButton button:hover {{ transform:translateY(-1px); }}
.stButton button:active, .stDownloadButton button:active, [data-testid="stFormSubmitButton"] button:active {{ transform:translateY(0) scale(.98); }}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{ transition:border-color var(--lc-base) ease, box-shadow var(--lc-base) ease; }}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"]:focus-within {{ box-shadow:0 0 0 3px rgba(47,107,255,.22); }}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div {{ background-color:transparent !important; }}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div:has(> input) {{ background-color:rgba(255,255,255,.06) !important; border-radius:10px; }}
[data-testid="stPlotlyChart"] {{ background:transparent; border:none; padding:0; animation:lc-fade .5s ease both; }}
[data-testid="stDataFrame"] {{ border-radius:12px; overflow:hidden; }}
[data-testid="stFileUploaderDropzone"] {{ border-radius:14px; transition:border-color var(--lc-base) ease, background var(--lc-base) ease; }}
[data-testid="stFileUploaderDropzone"]:hover {{ border-color:var(--lc-accent); }}
[data-testid="stAlert"] {{ border-radius:12px; animation:lc-rise var(--lc-base) var(--lc-ease) both; }}
[data-testid="stToast"] {{ border-radius:12px; }}
[role="dialog"] {{ animation:lc-rise var(--lc-base) var(--lc-ease) both; }}
[data-testid="stStatusWidget"] {{ animation:lc-fade var(--lc-base) ease both; }}
footer {{ visibility:hidden; }}
:focus-visible {{ outline:2px solid #5B8DFF !important; outline-offset:2px; }}

/* ---------- sign-in */
.lc-auth-wrap {{ max-width:460px; margin:5vh auto 0; animation:lc-rise .5s var(--lc-ease) both; }}
.lc-auth-brand {{ display:flex; flex-direction:column; align-items:center; text-align:center; margin-bottom:18px; }}
.lc-auth-brand img {{ width:250px; max-width:80%; }}
.lc-auth-brand h3 {{ margin:18px 0 2px; font-size:1.28rem; font-weight:650; color:var(--lc-ink); }}
.lc-auth-brand p {{ margin:0; color:var(--lc-muted); font-size:.9rem; }}
.st-key-lc_auth_box {{ background:var(--lc-surface); border:1px solid var(--lc-line); border-radius:var(--lc-r-xl); padding:22px 24px 14px; box-shadow:0 30px 80px -40px rgba(0,0,0,.7);
   backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); animation:lc-rise .55s var(--lc-ease) .05s both; }}
.st-key-lc_auth_box [data-testid="stForm"] {{ border:none; padding:0; }}
.lc-auth-foot {{ text-align:center; color:var(--lc-muted); font-size:.76rem; margin-top:14px; }}
"""
    if not dark:
        css += f"""
[data-testid="stMain"] p, [data-testid="stMain"] li, [data-testid="stMain"] label, [data-testid="stMain"] span {{ color:var(--lc-ink2); }}
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] h4, [data-testid="stMain"] strong {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button {{ background:#FFFFFF !important; border-color:{t['line']} !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button p {{ color:var(--lc-ink2) !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stMain"] [data-testid="stBaseButton-segmented_controlActive"] {{ background:rgba(47,107,255,.12) !important; border-color:rgba(47,107,255,.45) !important; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color:#1F4FD1 !important; font-weight:600; }}
[data-testid="stMain"] [data-baseweb="select"] div, [data-testid="stMain"] [data-testid="stSelectbox"] div:has(> button),
[data-testid="stMain"] [data-testid="stMultiSelect"] div:has(> button) {{ background-color:transparent !important; }}
[data-testid="stMain"] [data-baseweb="select"] > div {{ background-color:#FFFFFF !important; border-color:#CDD5E3 !important; }}
[data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="textarea"], [data-testid="stMain"] [data-baseweb="base-input"] {{ border-color:#CDD5E3 !important; }}
[data-testid="stMain"] [data-baseweb="select"] svg {{ fill:var(--lc-muted) !important; color:var(--lc-muted) !important; }}
[data-testid="stMain"] [data-testid="stAlertContainer"] {{ background:#FFF8E8 !important; }}
[data-testid="stMain"] [data-testid="stAlertContentInfo"], [data-testid="stMain"] [data-testid="stAlertContentInfo"] * {{ color:#1F3A6B !important; }}
[data-testid="stMain"] [data-testid="stAlertContentWarning"] *, [data-testid="stMain"] [data-testid="stAlertContentError"] *, [data-testid="stMain"] [data-testid="stAlertContentSuccess"] * {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] .stTabs [data-baseweb="tab-list"] {{ border-color:{t['line']}; }}
[data-testid="stMain"] [data-testid="stCheckbox"] span, [data-testid="stMain"] [data-testid="stRadio"] span {{ border-color:#9AA7BC; }}
[data-testid="stMain"] [data-baseweb="input"] > div, [data-testid="stMain"] [data-baseweb="textarea"], [data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] .stNumberInput input, [data-testid="stMain"] .stTextInput input, [data-testid="stMain"] textarea, [data-testid="stMain"] input,
[data-testid="stMain"] [data-baseweb="base-input"] {{ background:#FFFFFF !important; color:var(--lc-ink) !important; border-color:{t['line']} !important; }}
[data-testid="stMain"] .stButton button:not([kind="primary"]), [data-testid="stMain"] .stDownloadButton button, [data-testid="stMain"] [data-testid="stPopover"] button,
[data-testid="stMain"] [data-testid="stBaseButton-secondary"], [data-testid="stMain"] [data-testid="stBaseButton-segmented_control"] {{ background:#FFFFFF !important; color:var(--lc-ink) !important; border-color:{t['line']} !important; }}
[data-testid="stMain"] .stButton button p, [data-testid="stMain"] [data-testid="stPopover"] button p {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] [data-testid="stBaseButton-segmented_controlActive"] {{ background:rgba(47,107,255,.12) !important; color:#1F4FD1 !important; }}
[data-baseweb="popover"] ul, [data-baseweb="menu"], [data-baseweb="popover"] > div {{ background:#FFFFFF !important; color:var(--lc-ink) !important; }}
[role="option"] {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ background:#FFFFFF; }}
[data-testid="stMain"] [data-testid="stExpander"] summary p {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] [data-testid="stDataFrame"], [data-testid="stMain"] [data-testid="stTable"] {{ filter:invert(0.94) hue-rotate(180deg); }}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {{ background:#FFFFFF; }}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] * {{ color:var(--lc-ink2); }}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {{ background:rgba(255,255,255,.7); border-color:{t['line']} !important; }}
[data-testid="stMain"] [data-testid="stAlert"] p {{ color:var(--lc-ink) !important; }}
[data-testid="stMain"] code {{ background:#EEF2F8; color:var(--lc-ink); }}
.stTabs [data-baseweb="tab"] p {{ color:var(--lc-ink2) !important; }}
.stTabs [aria-selected="true"] p {{ color:var(--lc-ink) !important; }}
"""
    st.markdown(css + "</style>", unsafe_allow_html=True)


class embedded:
    """Inside a hub page, sub-sections render a compact heading instead of a full page title."""

    def __enter__(self):
        st.session_state["_embedded"] = True

    def __exit__(self, *exc):
        st.session_state["_embedded"] = False


def page_header(title: str, subtitle: str = "", icon_name: str = "layout-dashboard") -> None:
    t = tokens()
    if st.session_state.get("_embedded"):
        if subtitle:
            st.markdown(f'<p class="lc-muted" style="margin:-2px 0 14px">{esc(subtitle)}</p>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="lc-page-title"><div class="ic">{icon(icon_name, 20, t["teal"])}</div><h2>{esc(title)}</h2></div>'
                + (f'<p class="lc-sub">{esc(subtitle)}</p>' if subtitle else ""), unsafe_allow_html=True)


def hero(title: str, subtitle: str, eyebrow: str = "Lucerna · From Data to Decisions") -> None:
    st.markdown(f'<div class="lc-hero"><div class="lc-eyebrow">{icon("sparkles", 14, "#9FEDE2")}{esc(eyebrow)}</div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>',
                unsafe_allow_html=True)


KPI_COLOURS = ["#5B8DFF", "#2CD3C0", "#A48CFF", "#FFC56B", "#F27AA8", "#46C46E"]


def kpi(label: str, value, sub: str = "", icon_name: str = "activity", color: str | None = None, small: bool = False) -> str:
    c = color or tokens()["teal"]
    return (f'<div class="lc-kpi" role="group" aria-label="{esc(label)}" style="--lc-k:{c}"><div class="top"><span>{esc(label)}</span>'
            f'<span class="ic" style="background:{c}24">{icon(icon_name, 16, c)}</span></div>'
            f'<div class="v{" sm" if small else ""}">{esc(value)}</div><div class="s">{esc(sub)}</div></div>')


def kpi_row(items: list[tuple]) -> None:
    """A responsive row of KPI cards (wraps on narrow screens)."""
    cards = []
    for i, it in enumerate(items):
        it = list(it)
        if len(it) < 5:
            it += [None] * (5 - len(it))
        label, value, sub, ic, color = it[:5]
        cards.append(kpi(label, value, sub or "", ic or "activity", color or KPI_COLOURS[i % len(KPI_COLOURS)], *(it[5:6] or [False])))
    st.markdown('<div class="lc-kpis">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def empty_state(title: str, text: str, icon_name: str = "database") -> None:
    st.markdown(f'<div class="lc-empty">{icon(icon_name, 34, tokens()["muted"], 1.4)}<h4>{esc(title)}</h4><div class="lc-muted">{esc(text)}</div></div>', unsafe_allow_html=True)


def pill(text: str, tone: str = "info") -> str:
    colors = {"good": "#22B573", "warning": "#D9962B", "critical": "#E5484D", "info": "#5B8DFF", "neutral": "#8E9CB5", "teal": "#16C2B0", "violet": "#8B6CFF"}
    c = colors.get(tone, tone)
    return f'<span class="lc-pill" style="background:{c}1F;color:{c};border-color:{c}40">{esc(text)}</span>'


def status_pill(status: str) -> str:
    tone = {"verified": "good", "approved": "good", "applied": "good", "completed": "good", "configured": "info", "rejected": "critical",
            "failed": "critical", "manual_review": "warning", "suggested": "warning", "provisional": "warning", "draft": "neutral",
            "in_review": "info", "proposed": "info", "excluded": "neutral", "pending": "neutral", "running": "info", "queued": "neutral",
            "cancelled": "neutral", "merged": "neutral", "reverted": "neutral"}.get(status, "neutral")
    return pill(status.replace("_", " "), tone)


def chart_title(title: str, icon_name: str | None = None, subtitle: str | None = None) -> None:
    t = tokens()
    st.markdown(f'<div class="lc-chart-title">{icon(icon_name, 16, t["teal"]) if icon_name else ""}{esc(title)}</div>'
                + (f'<div class="lc-chart-sub">{esc(subtitle)}</div>' if subtitle else ""), unsafe_allow_html=True)


def steps(items: list[tuple[str, bool]]) -> None:
    st.markdown('<div class="lc-steps">' + "".join(
        f'<span class="lc-step {"done" if d else ""}">{icon("circle-check" if d else "clock", 13, "#22B573" if d else "#8E9CB5")}{esc(s)}</span>' for s, d in items) + "</div>",
                unsafe_allow_html=True)


def quote_html(text: str, source: str, extra: str = "") -> str:
    return f'<div class="lc-quote">“{esc(text)}”<div class="src">{esc(source)}{(" · " + extra) if extra else ""}</div></div>'


# ---------------------------------------------------------------- loading identity

SYMBOL_SVG = ('<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs><linearGradient id="lcl-t" x1="6" y1="4" x2="60" y2="62" gradientUnits="userSpaceOnUse">'
              '<stop offset="0" stop-color="#2F6BFF"/><stop offset="1" stop-color="#16C2B0"/></linearGradient></defs>'
              '<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#lcl-t)"/>'
              '<path d="M14 18.5a4.5 4.5 0 0 1 9 0V40.2L41.6 33.4A2.2 2.2 0 0 1 44.6 35.5V47.8A2.2 2.2 0 0 1 42.4 50H18.5A4.5 4.5 0 0 1 14 45.5Z" fill="#FFFFFF" fill-opacity=".92"/>'
              '<circle class="sp" cx="46.5" cy="19.5" r="5.5" fill="#FFC56B"/></svg>')


def loader_html(text: str = "Preparing your analysis…") -> str:
    """Lucerna loading identity: the symbol with a pulsing point of light and an indeterminate progress line."""
    return (f'<div class="lc-loader" role="status" aria-live="polite"><div class="mark">{SYMBOL_SVG}</div>'
            f'<div><div>{esc(text)}</div><div class="track"></div></div></div>')


def skeleton_html(height: int = 260, lines: int = 0) -> str:
    bars = "".join(f'<div class="lc-skel" style="height:10px;width:{70 - i * 14}%;margin:8px 0"></div>' for i in range(lines))
    return f'<div aria-hidden="true">{bars}<div class="lc-skel" style="height:{height}px;margin-top:8px"></div></div>'
