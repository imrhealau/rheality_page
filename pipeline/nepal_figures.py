"""Figures for the Nepal barrier-lake research note.

  .venv/bin/python -u nepal_figures.py
"""
import os, glob, re, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from affine import Affine
from scipy import ndimage

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "nepal2026_cache")
OUT = os.path.abspath(os.path.join(HERE, "..", "research", "nepal-barrier-lake", "img"))
os.makedirs(OUT, exist_ok=True)
RES = 10.0

PLUM, TERRA, MUT, LINE = "#33254E", "#CD5A1F", "#6F6488", "#E4DDF1"
plt.rcParams.update({"font.family": "sans-serif", "axes.edgecolor": MUT,
                     "axes.labelcolor": PLUM, "text.color": PLUM,
                     "xtick.color": MUT, "ytick.color": MUT, "font.size": 10})

# ---------------------------------------------------------------- timeline
PASSES = [("2026-08-04", 85, "asc"), ("2026-08-07", 121, "desc"),
          ("2026-08-12", 19, "desc"), ("2026-08-16", 85, "asc"),
          ("2026-08-19", 121, "desc"), ("2026-08-24", 19, "desc"),
          ("2026-08-28", 85, "asc")]
EVENT = "2026-08-26"


def day(s):
    return int(s[-2:])


fig, ax = plt.subplots(figsize=(9.5, 2.9), dpi=160)
ax.add_patch(Rectangle((24, -1), 4, 2, color=TERRA, alpha=0.10, zorder=0))
for d, orb, direction in PASSES:
    x = day(d)
    future = x > 26
    ax.plot([x, x], [-0.42, 0.42], color=MUT if not future else LINE,
            lw=2.2, solid_capstyle="round", zorder=2)
    ax.text(x, 0.60, f"{x}", ha="center", fontsize=9,
            color=PLUM if not future else MUT)
    ax.text(x, -0.72, f"orbit {orb}\n{direction}", ha="center", fontsize=7.2,
            color=MUT)
ax.axvline(26, color=TERRA, lw=2.4, zorder=3)
ax.text(26.25, 1.14, "collapse 26 Aug", ha="left", color=TERRA, fontsize=9.5,
        weight="bold")
ax.annotate("", xy=(24, -1.12), xytext=(28, -1.12),
            arrowprops=dict(arrowstyle="<->", color=TERRA, lw=1.3))
ax.text(26, -1.30, "4-day gap, no orbital look", ha="center", color=TERRA,
        fontsize=9)
ax.annotate("last look, 00:18Z", xy=(24, 0.50), xytext=(21.6, 1.14),
            ha="center", color=PLUM, fontsize=9,
            arrowprops=dict(arrowstyle="->", color=PLUM, lw=1.1))
ax.set_xlim(2.2, 29.8); ax.set_ylim(-1.65, 1.5)
ax.set_yticks([]); ax.set_xticks([])
for s in ("left", "right", "top"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_visible(False)
ax.set_title("Sentinel-1 passes over the Lhende catchment, August 2026",
             color=PLUM, fontsize=11.5, pad=14)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "timeline.png"), bbox_inches="tight",
            facecolor="white")
print("wrote timeline.png")

# ------------------------------------------------------------ source series
s = json.load(open(os.path.join(DATA, "nepal_source_series_2026.json")))["series"]
dates = [r["date"][5:] for r in s]
src = [r["source_km2"] for r in s]
ctl = [r["control_frac"] * 100 for r in s]

fig, ax = plt.subplots(figsize=(9.5, 4.4), dpi=160)
ax.plot(dates, src, "-o", color=TERRA, lw=2.2, ms=7, label="source zone, 33-40 km upstream, 5100-5600 m",
        zorder=3)
ax2 = ax.twinx()
ax2.plot(dates, ctl, "-s", color=MUT, lw=1.6, ms=5.5, alpha=0.8,
         label="control zone, same elevation and slope band", zorder=2)
ax2.set_ylabel("control zone, % below -15 dB", color=MUT, fontsize=9.5)
ax2.tick_params(axis="y", labelsize=9)
ax.set_ylabel("source zone area below -15 dB (km$^2$)", color=TERRA, fontsize=9.5)
ax.tick_params(axis="y", labelsize=9)
ax.annotate("falls 1.87 km$^2$", xy=(3, src[3]), xytext=(2.55, src[3] - 2.5),
            color=TERRA, fontsize=9,
            arrowprops=dict(arrowstyle="->", color=TERRA, lw=1.2))
ax.annotate("+0.30, the smallest\nmove in the series", xy=(5, src[5]),
            xytext=(3.85, src[5] + 2.1), color=PLUM, fontsize=9,
            arrowprops=dict(arrowstyle="->", color=PLUM, lw=1.2))
ax.set_ylim(5, 17); ax2.set_ylim(8, 24)
ax.grid(axis="y", color=LINE, lw=0.9)
ax.set_axisbelow(True)
for a in (ax, ax2):
    for sp in ("top",): a.spines[sp].set_visible(False)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.8, frameon=False)
ax.set_title("Was a lake filling in the glaciated source zone?\n"
             "Dark-area time series, elevation ceiling removed",
             color=PLUM, fontsize=11.5, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "source_series.png"), bbox_inches="tight",
            facecolor="white")
print("wrote source_series.png")

# ------------------------------------------------------- change distribution
z = np.load(os.path.join(DATA, "nepal2026_stacks.npz"))
transform = Affine(*z["transform"])
dem, pre, ctrl, test = z["dem"], z["vv_pre"], z["vv_control"], z["vv_test"]
gy, gx = np.gradient(dem, RES)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
win = int(2000 / RES)
valley = (dem - ndimage.minimum_filter(np.nan_to_num(dem, nan=9999), size=win)) < 40
m = valley & (slope <= 15) & np.isfinite(pre) & np.isfinite(ctrl) & np.isfinite(test)

fig, ax = plt.subplots(figsize=(9.5, 4.4), dpi=160)
bins = np.linspace(-12, 12, 160)
ax.hist((ctrl - pre)[m], bins=bins, histtype="step", lw=2.0, color=MUT,
        label="12 Aug control minus baseline", density=True)
ax.hist((test - pre)[m], bins=bins, histtype="step", lw=2.2, color=TERRA,
        label="24 Aug test minus baseline", density=True)
ax.axvline(-3, color=PLUM, ls="--", lw=1.3)
ax.text(-3.25, ax.get_ylim()[1] * 0.86, "detection\nthreshold", ha="right",
        fontsize=8.8, color=PLUM)
ax.set_xlabel("VV change from monsoon baseline (dB), valley floor")
ax.set_ylabel("density")
ax.legend(fontsize=9, frameon=False)
ax.grid(axis="y", color=LINE, lw=0.9); ax.set_axisbelow(True)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.set_title("A wetter valley, and nothing in particular\n"
             "48 h before the collapse the whole floor is 0.8 dB darker, "
             "with no water body anywhere in it",
             color=PLUM, fontsize=11.5, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "change_distribution.png"), bbox_inches="tight",
            facecolor="white")
print("wrote change_distribution.png")
print(f"\nvalley px used: {m.sum():,}")
print(f"control dVV: mean {np.nanmean((ctrl-pre)[m]):+.3f} dB, "
      f"p1 {np.nanpercentile((ctrl-pre)[m],1):.2f}")
print(f"test    dVV: mean {np.nanmean((test-pre)[m]):+.3f} dB, "
      f"p1 {np.nanpercentile((test-pre)[m],1):.2f}")

# ------------------------------------------------------------------- rainfall
inflow = json.load(open(os.path.join(DATA, "nepal_inflow_2026.json")))
daily = inflow["daily_mean_mm"]
days = sorted(daily)
vals = [daily[d] for d in days]
labels = [d[5:] for d in days]
# Anything from today onward is forecast rather than observed.
today = inflow["generated_utc"][:10]
obs = [v if d < today else 0 for d, v in zip(days, vals)]
fcst = [v if d >= today else 0 for d, v in zip(days, vals)]

fig, ax = plt.subplots(figsize=(9.5, 4.2), dpi=160)
ax.bar(labels, obs, color=MUT, width=0.72, label="observed")
ax.bar(labels, fcst, color=MUT, width=0.72, alpha=0.40, label="forecast",
       hatch="///", edgecolor=MUT)
ievent = days.index("2026-08-26") if "2026-08-26" in days else None
if ievent is not None:
    ax.axvline(ievent, color=TERRA, lw=2.4, zorder=4)
    ax.text(ievent + 0.15, max(vals) * 0.94, "collapse\n26 Aug", color=TERRA,
            fontsize=9.5, weight="bold", va="top")
for d, tag in (("2026-08-24", "last radar look"),):
    if d in days:
        i = days.index(d)
        ax.annotate(tag, (i, vals[i]), xytext=(-6, 46), ha="right",
                    textcoords="offset points", fontsize=9, color=PLUM,
                    arrowprops=dict(arrowstyle="->", color=PLUM, lw=1.1))
ax.set_ylabel("catchment-mean rainfall (mm/day)")
ax.grid(axis="y", color=LINE, lw=0.9); ax.set_axisbelow(True)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.legend(fontsize=9, frameon=False, loc="upper left")
ax.set_title("There was no water to fill a lake with\n"
             "Rainfall over the contributing catchment, 16-point mean",
             color=PLUM, fontsize=11.5, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "rainfall.png"), bbox_inches="tight", facecolor="white")
print("wrote rainfall.png")

# ------------------------------------------------------- detection limit chart
# The whole argument in one axis: what radar can see, what was there, and how
# big a lake would have had to be to drive the flood that followed.
fig, ax = plt.subplots(figsize=(9.5, 3.4), dpi=160)
ax.set_xscale("log")
ax.set_xlim(200, 1e6)
ax.set_ylim(0, 1)

ax.axvspan(200, 2000, color=MUT, alpha=0.16, zorder=1)
ax.axvspan(1e4, 1e5, color=TERRA, alpha=0.20, zorder=1)

ax.text(630, 0.86, "below what 10 m radar\ncan honestly resolve", ha="center",
        fontsize=9, color=MUT, style="italic")
ax.text(10**4.5, 0.86, "size a lake needed to be\nto drive the flood that followed",
        ha="center", fontsize=9.5, color=TERRA, weight="bold")

# The detectable range, drawn as a bracket, and empty is the whole point.
Y = 0.44
ax.annotate("", xy=(2000, Y), xytext=(1e6, Y),
            arrowprops=dict(arrowstyle="|-|,widthA=0.5,widthB=0.5",
                            color=PLUM, lw=2.0))
ax.text(10**4.35, Y + 0.09,
        "on 24 Aug, 48 h before the collapse, this entire range was empty",
        ha="center", fontsize=11, color=PLUM, weight="bold")
ax.text(10**4.35, Y - 0.13, "at every threshold, and at every elevation",
        ha="center", fontsize=9.5, color=PLUM)

# what the detector actually returned, on the control date rather than the test
ax.scatter([2000], [Y], s=130, marker="o", facecolors="white",
           edgecolors=MUT, linewidths=2.0, zorder=6)
ax.annotate("the only hit in the study was 2,000 m$^2$ on the\n"
            "12 Aug control, so the control ran dirtier than the test",
            xy=(2000, Y), xytext=(2300, 0.14), fontsize=9, color=MUT,
            arrowprops=dict(arrowstyle="->", color=MUT, lw=1.1))

ax.set_yticks([])
ax.set_xlabel("water body area (m$^2$)")
for sp in ("left", "right", "top"): ax.spines[sp].set_visible(False)
ax.set_title("The gap between what was detectable and what was there",
             color=PLUM, fontsize=12, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "detection_limit.png"), bbox_inches="tight",
            facecolor="white")
print("wrote detection_limit.png")
