#!/usr/bin/env python3
"""Figure for the Cikarang data center run: LOS velocity map + per-estate series.

Reads data/cikarang_insar.json and data/cikarang_disp.npz, writes
data/cikarang_insar.png.

Three panels: the velocity map, the raw estate series (one point per pass), and
each estate minus the mean of the other two. The third panel is the one that
carries the result: common-mode atmosphere cancels in the difference, so the
residual scatter drops and the gradient between estates is what survives.
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
z = np.load(os.path.join(DATA, "cikarang_disp.npz"), allow_pickle=True)
vel = z["vel"]

import rasterio
from rasterio.warp import transform as warp
tr = rasterio.Affine(*z["transform"])
crs = rasterio.crs.CRS.from_wkt(str(z["crs_wkt"]))
H, W = vel.shape
extent = [tr.c, tr.c + W * tr.a, tr.f + H * tr.e, tr.f]

colors = {"mm2100": "#CD5A1F", "jababeka": "#33254E", "deltamas": "#2E7D6B"}
short = {"mm2100": "MM2100", "jababeka": "Jababeka", "deltamas": "GIIC Deltamas"}
keys = [k for k in ("mm2100", "jababeka", "deltamas") if k in d["sites"]]

t = np.array([(date.fromisoformat(p["date"]) - date.fromisoformat(d["window"]["start"])).days
              for p in d["sites"][keys[0]]["series"]]) / 365.25
tt = [date.fromisoformat(p["date"]) for p in d["sites"][keys[0]]["series"]]
Y = {k: np.array([p["los_mm"] for p in d["sites"][k]["series"]]) for k in keys}


def fit(y):
    A = np.vstack([t, np.ones_like(t)]).T
    c = np.linalg.lstsq(A, y, rcond=None)[0]
    return c[0], A @ c, (y - A @ c).std(ddof=2)


fig = plt.figure(figsize=(13.6, 6.8))

# --- left: velocity map -------------------------------------------------
ax = fig.add_axes([0.035, 0.07, 0.43, 0.83])
lim = max(abs(d["aoi_velocity_mm_yr"]["p5"]), abs(d["aoi_velocity_mm_yr"]["p95"]))
im = ax.imshow(vel, extent=extent, cmap="RdBu", vmin=-lim, vmax=lim, interpolation="nearest")
x0, x1, y0, y1 = extent
for k in keys:
    s = d["sites"][k]
    x, y = warp("EPSG:4326", crs, [s["lon"]], [s["lat"]])
    x, y = x[0], y[0]
    ax.add_patch(plt.Circle((x, y), 400, fill=False, lw=2, color=colors[k]))
    # keep the label inside the panel: flip it left of the marker in the right third
    right = (x - x0) / (x1 - x0) > 0.62
    ax.annotate(short[k], (x, y), xytext=(-12 if right else 12, 10),
                textcoords="offset points", ha="right" if right else "left",
                fontsize=9.5, color=colors[k], weight="bold",
                path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
ax.set_xticks([]); ax.set_yticks([])
ax.set_title("LOS velocity, mm/yr (negative = moving away from the satellite, i.e. sinking)",
             fontsize=9)
cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.01)
cb.ax.tick_params(labelsize=8)

# --- top right: raw series ---------------------------------------------
ax2 = fig.add_axes([0.545, 0.545, 0.40, 0.355])
for k in keys:
    v, trend, rms = fit(Y[k])
    ax2.plot(tt, Y[k], "o", ms=2.6, color=colors[k], alpha=0.45)
    ax2.plot(tt, trend, "-", lw=1.8, color=colors[k],
             label=f"{short[k]}: {v:+.0f} mm/yr, scatter {rms:.0f} mm")
ax2.axhline(0, color="#999", lw=0.8)
ax2.grid(alpha=0.25)
ax2.set_ylabel("LOS displacement, mm", fontsize=9)
ax2.tick_params(labelsize=8)
ax2.legend(fontsize=7.6, loc="upper left", framealpha=0.92, borderpad=0.4)
ax2.set_title(f"Estate median, one point per pass, {d['window']['start']} to {d['window']['end']}"
              f" ({d['window']['epochs']} epochs)", fontsize=9)

# --- bottom right: each estate minus the mean of the other two ----------
ax3 = fig.add_axes([0.545, 0.085, 0.40, 0.355])
for k in keys:
    others = [o for o in keys if o != k]
    diff = Y[k] - np.mean([Y[o] for o in others], axis=0)
    v, trend, rms = fit(diff)
    ax3.plot(tt, diff, "o", ms=2.6, color=colors[k], alpha=0.45)
    ax3.plot(tt, trend, "-", lw=1.8, color=colors[k],
             label=f"{short[k]}: {v:+.0f} mm/yr, scatter {rms:.0f} mm")
ax3.axhline(0, color="#999", lw=0.8)
ax3.grid(alpha=0.25)
ax3.set_ylabel("Difference, mm", fontsize=9)
ax3.tick_params(labelsize=8)
ax3.legend(fontsize=7.6, loc="upper left", framealpha=0.92, borderpad=0.4)
ax3.set_title("Each estate minus the mean of the other two (shared atmosphere cancels)",
              fontsize=9)

fig.suptitle("Cikarang data center cluster: Sentinel-1 ascending track 98. "
             "Contains modified Copernicus Sentinel data, processed by ASF HyP3",
             fontsize=10, y=0.975)
out = os.path.join(DATA, "cikarang_insar.png")
plt.savefig(out, dpi=110)
print("wrote", out)
