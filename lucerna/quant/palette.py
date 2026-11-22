"""Lucerna data-visualisation palette.

Categorical slots validated with the six-check palette validator (lightness band, chroma floor,
adjacent CVD separation, normal-vision floor, contrast) for both modes. Slot order is the
CVD-safety mechanism: do not reorder. More than 7 categories fold into "Other".
Slots 7↔8 sit in the 6–8 CVD band, so charts always ship legends / direct labels (secondary encoding).
"""
CATEGORICAL = {
    "light": ["#14A394", "#4778E8", "#EB6834", "#6250D6", "#EDA100", "#E87BA4", "#008300", "#E34948"],
    "dark": ["#13A595", "#5B8AF0", "#D95926", "#9085E9", "#C98500", "#D55181", "#0CA30C", "#E66767"],
}
OTHER = {"light": "#9AA5B1", "dark": "#5E6B7A"}
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
DIVERGING = {"neg": "#d03b3b", "neg2": "#ec8a80", "mid": {"light": "#E3E1DC", "dark": "#3A4557"}, "pos2": "#86b6ef", "pos": "#2a78d6"}
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
SURFACE = {"light": "#FFFFFF", "dark": "#14213A"}
INK = {"light": {"primary": "#101B2D", "secondary": "#4B5563", "muted": "#7B8794", "grid": "#E8ECF1"},
       "dark": {"primary": "#F5F7FA", "secondary": "#C5CDD8", "muted": "#8D99A8", "grid": "#26344D"}}
MAX_CATEGORIES = 7

# ---------------------------------------------------------------- dashboard themes
# Each generated dashboard carries its own theme (independent of the Lucerna app colours).
# Every categorical set below was run through the six-check validator against the theme's own
# chart surface (2026-11-21): all hard gates pass; worst adjacent CVD ΔE ≥ 8.4 except "vibrant"
# (7.2, floor band → charts keep legends/direct labels). Order is the safety mechanism: do not reorder.
CATEGORICAL.update({
    "corporate": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    "executive": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
    "vibrant": ["#14A394", "#4778E8", "#EB6834", "#6250D6", "#EDA100", "#E87BA4", "#008300", "#E34948"],
    "minimal": ["#3d6fa8", "#c8693a", "#2f9c7e", "#b98a1e", "#b0608e", "#5a8f2e", "#7461c2", "#c24f4c"],
})
OTHER.update({"corporate": "#9AA5B1", "executive": "#5E6B6A", "vibrant": "#A4A9B6", "minimal": "#A7A9A6"})
SURFACE.update({"corporate": "#FFFFFF", "executive": "#142320", "vibrant": "#FFFFFF", "minimal": "#FCFCFB"})
INK.update({
    "corporate": {"primary": "#0F1B2D", "secondary": "#465365", "muted": "#7A8696", "grid": "#E6EAF0"},
    "executive": {"primary": "#EEF3F0", "secondary": "#C2CEC8", "muted": "#8FA29A", "grid": "#243833"},
    "vibrant": {"primary": "#1A1440", "secondary": "#4A4566", "muted": "#7C7896", "grid": "#ECEAF6"},
    "minimal": {"primary": "#0B0B0B", "secondary": "#52514E", "muted": "#898781", "grid": "#E1E0D9"},
})
DIVERGING["mid"].update({"corporate": "#E3E1DC", "executive": "#33413D", "vibrant": "#E6E4EF", "minimal": "#F0EFEC"})
SEQUENTIAL = {
    "light": SEQUENTIAL_BLUE, "dark": SEQUENTIAL_BLUE, "corporate": SEQUENTIAL_BLUE,
    "executive": ["#1d3b36", "#1f5248", "#1f6a5b", "#1d836e", "#199e70", "#3db58a", "#6fcaa5", "#a3dcc2", "#d2efe2", "#ecf8f2"],
    "vibrant": ["#e7e3fb", "#cfc7f6", "#b5a9f0", "#9a8ae8", "#806ce0", "#6250d6", "#5141b8", "#41339a", "#32267b", "#241a5d"],
    "minimal": ["#e9eef5", "#d2dcea", "#b6c6dc", "#98aecd", "#7b96be", "#5f7fae", "#3d6fa8", "#335d8d", "#284a71", "#1d3754"],
}
DARK_THEMES = {"dark", "executive"}
