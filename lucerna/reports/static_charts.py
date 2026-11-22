"""Static (matplotlib) charts for DOCX/PDF/PNG/SVG export. Values come from charts.compute()."""
from __future__ import annotations

import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..quant.palette import CATEGORICAL, INK, OTHER  # noqa: E402

plt.rcParams.update({"font.family": ["Inter", "DejaVu Sans"], "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#C9D1DB", "axes.labelcolor": INK["light"]["secondary"], "xtick.color": INK["light"]["muted"],
                     "ytick.color": INK["light"]["muted"], "axes.grid": False, "figure.dpi": 150})


def _save(fig, path: str, fmt: str = "png") -> str:
    fig.tight_layout()
    fig.savefig(path, format=fmt, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def render(v: dict, data, path: str, fmt: str = "png") -> str | None:
    t = v["type"]
    tab = data.table
    pal = CATEGORICAL["light"]
    pct = v.get("measure") == "pct_condition" or v.get("as_pct") or v.get("normalize") or t in ("stacked100", "multiselect")
    if t in ("bar", "multiselect", "quality_missing", "donut") and "series" not in tab.columns:
        xcol, ycol = ("x", "pct") if t == "multiselect" else ("x", "value")
        if t == "donut":
            ycol = "pct"
            pct = True
        fig, ax = plt.subplots(figsize=(6.4, max(2.2, 0.32 * len(tab) + 0.8)))
        ax.barh(tab[xcol].astype(str), tab[ycol], color=pal[0] if t != "multiselect" else pal[1], height=0.62)
        ax.invert_yaxis()
        for i, val in enumerate(tab[ycol]):
            if val is not None and not np.isnan(val):
                ax.text(val, i, f" {val:.1f}%" if pct else f" {val:,.0f}", va="center", fontsize=8, color=INK["light"]["secondary"])
        ax.xaxis.grid(True, color="#EEF1F5")
        ax.set_axisbelow(True)
        if pct:
            ax.set_xlim(0, max(100, float(tab[ycol].max()) * 1.12))
        return _save(fig, path, fmt)
    if t in ("bar", "stacked100") and "series" in tab.columns:
        piv = tab.pivot_table(index="x", columns="series", values="value", aggfunc="sum").reindex(list(dict.fromkeys(tab["x"])))
        fig, ax = plt.subplots(figsize=(6.4, max(2.4, 0.36 * len(piv) + 1)))
        left = np.zeros(len(piv))
        for i, c in enumerate(piv.columns):
            vals = piv[c].fillna(0).values
            ax.barh(piv.index.astype(str), vals, left=left, color=pal[i % len(pal)] if c != "Other" else OTHER["light"], label=str(c), height=0.62, edgecolor="white", linewidth=1)
            left += vals
        ax.invert_yaxis()
        ax.legend(ncol=min(4, len(piv.columns)), fontsize=7, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0))
        if pct:
            ax.set_xlim(0, 100)
        return _save(fig, path, fmt)
    if t in ("line", "area_stacked"):
        fig, ax = plt.subplots(figsize=(6.4, 2.8))
        if "series" in tab.columns:
            for i, (k, g) in enumerate(tab.groupby("series", sort=False)):
                ax.plot(g["period"], g["value"], color=pal[i % len(pal)], lw=1.8, label=str(k))
            ax.legend(fontsize=7, frameon=False, ncol=3)
        else:
            ax.plot(tab["period"], tab["value"], color=pal[0], lw=1.8, marker="o", ms=3)
            if tab["moving_average"].notna().any():
                ax.plot(tab["period"], tab["moving_average"], color=INK["light"]["muted"], lw=1.4, ls=":", label="3-period moving average")
                ax.legend(fontsize=7, frameon=False)
        ax.yaxis.grid(True, color="#EEF1F5")
        if v.get("measure") == "pct_condition":
            ax.set_ylabel("%")
        fig.autofmt_xdate()
        return _save(fig, path, fmt)
    if t == "forecast":
        fc = data.extra["forecast"]
        fig, ax = plt.subplots(figsize=(6.4, 2.8))
        ax.fill_between(fc["period"], fc["lo95"], fc["hi95"], color=pal[1], alpha=.12, label="95% interval")
        ax.fill_between(fc["period"], fc["lo80"], fc["hi80"], color=pal[1], alpha=.22, label="80% interval")
        ax.plot(tab["period"], tab["value"], color=pal[0], lw=1.8, marker="o", ms=3, label="Observed")
        ax.plot(fc["period"], fc["forecast"], color=pal[1], lw=1.8, ls="--", marker="D", ms=3, label="Forecast (projection)")
        ax.legend(fontsize=7, frameon=False, ncol=2)
        fig.autofmt_xdate()
        return _save(fig, path, fmt)
    if t == "histogram":
        fig, ax = plt.subplots(figsize=(6.4, 2.6))
        ax.hist(tab["value"], bins=20, color=pal[1], edgecolor="white")
        med = data.extra["describe"].get("median")
        if med is not None:
            ax.axvline(med, color=INK["light"]["primary"], lw=1.2)
            ax.text(med, ax.get_ylim()[1] * .95, f" median {med:,.1f}", fontsize=7)
        ax.set_xlabel(v.get("value_label") or v.get("title", "").replace("Distribution of ", "") or v["value"])
        return _save(fig, path, fmt)
    if t == "pyramid":
        cols = list(tab.columns)[:2]
        fig, ax = plt.subplots(figsize=(6.4, 3))
        ax.barh(tab.index.astype(str), -tab[cols[0]], color=pal[3], label=cols[0])
        ax.barh(tab.index.astype(str), tab[cols[1]], color=pal[0], label=cols[1])
        mx = float(tab[cols].values.max())
        ticks = np.linspace(-mx, mx, 5)
        ax.set_xticks(ticks, [f"{abs(x):,.0f}" for x in ticks])
        ax.legend(fontsize=7, frameon=False)
        return _save(fig, path, fmt)
    if t in ("heatmap", "correlation"):
        z = tab.values.astype(float)
        fig, ax = plt.subplots(figsize=(6.4, max(2.2, 0.4 * len(tab) + 1)))
        im = ax.imshow(z, cmap="RdBu" if t == "correlation" else "Blues", vmin=-1 if t == "correlation" else 0, vmax=1 if t == "correlation" else 100, aspect="auto")
        ax.set_xticks(range(len(tab.columns)), [textwrap.fill(str(c), 18, max_lines=3, placeholder="…") for c in tab.columns], rotation=0, ha="center", fontsize=7)
        ax.set_yticks(range(len(tab.index)), [str(i)[:24] for i in tab.index], fontsize=7)
        for i in range(z.shape[0]):
            for j in range(z.shape[1]):
                if not np.isnan(z[i, j]):
                    ax.text(j, i, f"{z[i, j]:.2f}" if t == "correlation" else f"{z[i, j]:.0f}%", ha="center", va="center", fontsize=7,
                            color="white" if (abs(z[i, j]) > .6 if t == "correlation" else z[i, j] > 60) else INK["light"]["primary"])
        return _save(fig, path, fmt)
    if t == "likert":
        order = data.extra["order"]
        groups = list(dict.fromkeys(tab["group"]))
        fig, ax = plt.subplots(figsize=(6.4, max(1.8, 0.45 * len(groups) + 1)))
        colors = ["#d03b3b", "#ec8a80", "#E3E1DC", "#86b6ef", "#2a78d6"][:len(order)] if len(order) == 5 else plt.cm.RdBu(np.linspace(.15, .85, len(order)))
        left = np.zeros(len(groups))
        for i, cat in enumerate(order):
            vals = np.array([tab[(tab.group == g) & (tab.category == cat)]["pct"].sum() for g in groups])
            ax.barh(groups, vals, left=left, color=colors[i], label=cat, edgecolor="white")
            left += vals
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.legend(ncol=3, fontsize=6.5, frameon=False, loc="lower left", bbox_to_anchor=(0, 1))
        return _save(fig, path, fmt)
    if t == "box":
        by = v.get("by")
        fig, ax = plt.subplots(figsize=(6.4, 2.8))
        if by:
            groups = list(dict.fromkeys(tab[by].astype(str)))[:8]
            ax.boxplot([tab[tab[by].astype(str) == g][v["value"]].dropna() for g in groups], tick_labels=[g[:18] for g in groups], showfliers=False,
                       patch_artist=True, boxprops=dict(facecolor=pal[0] + "55", edgecolor=pal[0]), medianprops=dict(color=INK["light"]["primary"]))
            plt.setp(ax.get_xticklabels(), rotation=20, ha="right", fontsize=7)
        else:
            ax.boxplot([tab[v["value"]].dropna()], showfliers=False)
        ax.set_ylabel(v["value"])
        ax.yaxis.grid(True, color="#EEF1F5")
        return _save(fig, path, fmt)
    if t == "multiline":
        fig, ax = plt.subplots(figsize=(6.4, 2.8))
        for i, (k, g) in enumerate(tab.groupby("series", sort=False)):
            ax.plot(g["period"], g["value"], color=pal[i % len(pal)], lw=1.6, label=str(v.get("labels", {}).get(k, k))[:28])
        ax.legend(fontsize=7, frameon=False, ncol=2)
        ax.yaxis.grid(True, color="#EEF1F5")
        fig.autofmt_xdate()
        return _save(fig, path, fmt)
    if t == "treemap":
        top = tab.groupby(v["path"][0])["value"].sum().sort_values(ascending=False).head(15)
        fig, ax = plt.subplots(figsize=(6.4, max(2.2, 0.32 * len(top) + 0.8)))
        ax.barh(top.index.astype(str), top.values, color=pal[0], height=.62)
        ax.invert_yaxis()
        return _save(fig, path, fmt)
    return None


def to_bytes(v: dict, data, fmt: str = "png") -> bytes:
    """Render a computed visual to image bytes (matplotlib; works offline, no browser needed)."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, f"chart.{fmt}")
        if not render(v, data, p, fmt):
            raise ValueError("This visual type has no static image; export its data table instead.")
        with open(p, "rb") as fh:
            return fh.read()
