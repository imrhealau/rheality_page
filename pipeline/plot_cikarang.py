#!/usr/bin/env python3
"""Figure for the Cikarang data center run.

Left: LOS velocity map, with the eight verified data center sites and the three
estate centre points the first pass used. Top right: the verified sites, which
are flat. Bottom right: the Jababeka estate centre point against the mean of the
verified sites, which is the one moving thing in the scene and is 6.2 km from
the nearest data hall.

Reads data/cikarang_insar.json, data/cikarang_sites.json and
data/cikarang_disp.npz, writes data/cikarang_insar.png.
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
d = json.load(open(os.path.join(DATA, "cikarang_insar.json")))
sj = json.load(open(os.path.join(DATA, "cikarang_sites.json")))
z = np.load(os.path.join(DATA, "cikarang_disp.npz"), allow_pickle=True)
vel = z["vel"]

import rasterio
from rasterio.warp import transform as warp
tr = rasterio.Affine(*z["transform"])
crs = rasterio.crs.CRS.from_wkt(str(z["crs_wkt"]))
H, W = vel.shape
extent = [tr.c, tr.c + W * tr.a, tr.f + H * tr.e, tr.f]

S = sj["sites"]
DC = [k for k in S if not k.endswith("_pt")]
PT = [k for k in S if k.endswith("_pt")]
SHORT = {"dci_h1": "DCI H1", "pdg_jc3": "PDG JC3", "msft_jkt05": "MS JKT05",
         "msft_jkt11": "MS JKT11", "aws_giic": "AWS", "hyperspace": "Hyperspace",
         "stt_jkt1": "STT JKT1", "gtn": "EdgeConneX JKT01"}
BLUE, PLUM, TERRA = "#2E6E8E", "#33254E", "#CD5A1F"

tt = [date.fromisoformat(p["date"]) for p in S[DC[0]]["r400"]["series"]]
t = np.array([(x - tt[0]).days for x in tt]) / 365.25
A = np.vstack([t, np.ones_like(t)]).T
ser = lambda k: np.array([p["los_mm"] for p in S[k]["r400"]["series"]])


def fit(y):
    c = np.linalg.lstsq(A, y, rcond=None)[0]
    return c[0], A @ c, (y - A @ c).std(ddof=2)


fig = plt.figure(figsize=(13.6, 6.8))

# --- left: velocity map -------------------------------------------------
ax = fig.add_axes([0.035, 0.07, 0.43, 0.83])
lim = max(abs(d["aoi_velocity_mm_yr"]["p5"]), abs(d["aoi_velocity_mm_yr"]["p95"]))
im = ax.imshow(vel, extent=extent, cmap="RdBu", vmin=-lim, vmax=lim, interpolation="nearest")
x0, x1, y0, y1 = extent


def xy(k):
    X, Y = warp("EPSG:4326", crs, [S[k]["lon"]], [S[k]["lat"]])
    return X[0], Y[0]


for k in DC:
    x, y = xy(k)
    ax.plot([x], [y], "o", ms=6, mfc="none", mec=BLUE, mew=1.8)
for k, lab, dx, dy, ha in [("dci_h1", "DCI H1", 10, 8, "left"),
                           ("gtn", "EdgeConneX JKT01", 10, 8, "left"),
                           ("pdg_jc3", "GIIC cluster, 6 sites", -12, -16, "right")]:
    x, y = xy(k)
    ax.annotate(lab, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha,
                fontsize=9, color=BLUE, weight="bold",
                path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
kp = "jababeka_pt"
x, y = xy(kp)
ax.add_patch(plt.Circle((x, y), 400, fill=False, lw=2.2, color=TERRA))
ax.annotate("Jababeka estate point\n(first pass, no data hall here)", (x, y),
            xytext=(12, 10), textcoords="offset points", fontsize=9, color=TERRA,
            weight="bold", path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
ax.set_xticks([]); ax.set_yticks([])
ax.set_title("LOS velocity, mm/yr (negative = moving away from the satellite, i.e. sinking)",
             fontsize=9)
cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01)
cb.ax.tick_params(labelsize=8)

# --- top right: the verified data center sites --------------------------
ax2 = fig.add_axes([0.545, 0.545, 0.40, 0.355])
cmap = plt.get_cmap("tab10")
for i, k in enumerate(DC):
    y = ser(k)
    v, trend, rms = fit(y)
    ax2.plot(tt, y, "-", lw=0.9, alpha=0.5, color=cmap(i))
    ax2.plot(tt, trend, "-", lw=2.0, color=cmap(i),
             label=f"{SHORT[k]} {v:+.1f}")
ax2.axhline(0, color="#999", lw=0.8)
ax2.set_ylim(-70, 70)
ax2.grid(alpha=0.25); ax2.tick_params(labelsize=8)
ax2.set_ylabel("LOS displacement, mm", fontsize=9)
ax2.legend(fontsize=7, ncol=4, loc="lower left", framealpha=0.92, borderpad=0.35,
           columnspacing=0.9, handlelength=1.2)
ax2.set_title("Eight verified data center sites, mm/yr: none clears its own noise", fontsize=9)

# --- bottom right: the estate point against the data centers ------------
ax3 = fig.add_axes([0.545, 0.085, 0.40, 0.355])
dcmean = np.mean([ser(k) for k in DC], axis=0)
for k, col, lab in [(kp, TERRA, "Jababeka estate point")]:
    y = ser(k)
    v, trend, rms = fit(y)
    ax3.plot(tt, y, "o", ms=2.6, alpha=0.45, color=col)
    ax3.plot(tt, trend, "-", lw=2.0, color=col, label=f"{lab}: {v:+.1f} mm/yr")
v, trend, rms = fit(dcmean)
ax3.plot(tt, dcmean, "o", ms=2.6, alpha=0.45, color=BLUE)
ax3.plot(tt, trend, "-", lw=2.0, color=BLUE, label=f"Mean of the 8 data centers: {v:+.1f} mm/yr")
ax3.axhline(0, color="#999", lw=0.8)
ax3.set_ylim(-70, 70)
ax3.grid(alpha=0.25); ax3.tick_params(labelsize=8)
ax3.set_ylabel("LOS displacement, mm", fontsize=9)
ax3.legend(fontsize=7.6, loc="lower left", framealpha=0.92, borderpad=0.4)
ax3.set_title("The moving ground is 6.2 km from the nearest data hall", fontsize=9)

fig.suptitle("Cikarang data center cluster: Sentinel-1 ascending track 98. "
             "Contains modified Copernicus Sentinel data, processed by ASF HyP3",
             fontsize=10, y=0.975)
out = os.path.join(DATA, "cikarang_insar.png")
plt.savefig(out, dpi=110)
print("wrote", out)
