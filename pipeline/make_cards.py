"""Cover images for the demo gallery cards.

The cards render at 380x210 with object-fit:cover, so a full research figure
gets its title cropped off and its markers shrunk to nothing. These are built
for that box instead: 1140x630, no title (the card supplies its own heading),
and zoomed far enough in that the detections read at thumbnail size.

  .venv/bin/python -u make_cards.py
"""
import os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LightSource
from affine import Affine
from rasterio.warp import transform as tr

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
IMG = os.path.abspath(os.path.join(HERE, "..", "img"))
RES = 10.0
ASPECT = 380 / 210  # the card box
W_PX = 1140

TERRA, PLUM = "#CD5A1F", "#33254E"
SEA = "#7FB2D9"


def frame(ax, transform, dem, centre_lonlat, width_km, epsg):
    """Set axis limits to a card-shaped window centred on a lon/lat point."""
    cx, cy = tr("EPSG:4326", epsg, [centre_lonlat[0]], [centre_lonlat[1]])
    half_w = width_km * 1000 / 2
    half_h = half_w / ASPECT
    ax.set_xlim(cx[0] - half_w, cx[0] + half_w)
    ax.set_ylim(cy[0] - half_h, cy[0] + half_h)


def hillshade_ax(dem, transform, figsize_in=(W_PX / 160, W_PX / ASPECT / 160)):
    fig, ax = plt.subplots(figsize=figsize_in, dpi=160)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ls = LightSource(azdeg=315, altdeg=42)
    shade = ls.hillshade(np.nan_to_num(dem, nan=0.0), vert_exag=1.6, dx=RES, dy=RES)
    h, w = dem.shape
    extent = (transform.c, transform.c + w * RES,
              transform.f - h * RES, transform.f)
    ax.imshow(shade, cmap="gray", extent=extent, vmin=0, vmax=1.05,
              interpolation="bilinear")
    ax.set_axis_off()
    return fig, ax, extent


# ------------------------------------------------------------------ Hong Kong
z = np.load(os.path.join(DATA, "hk2023_stacks.npz"))
transform = Affine(*z["transform"])
dem = z["dem"]
EPSG_HK = "EPSG:32650"

fig, ax, extent = hillshade_ax(dem, transform)
# NaN is sea here as well as non-positive elevation; missing the NaN case
# leaves the harbour rendering as flat grey hillshade.
sea = (~np.isfinite(dem)) | (dem <= 0)
ax.imshow(np.where(sea, 1.0, np.nan), cmap="Blues", extent=extent,
          vmin=0, vmax=1.6, alpha=0.92, interpolation="nearest")

cand = json.load(open(os.path.join(DATA, "hk_landslides_2023.json")))["top_candidates"]
for c in cand:
    if not c.get("in_hk"):
        continue
    x, y = tr("EPSG:4326", EPSG_HK, [c["lon"]], [c["lat"]])
    ax.scatter(x, y, s=max(90, c["area_m2"] / 26), facecolors="none",
               edgecolors=TERRA, linewidths=2.4, alpha=0.95, zorder=4)

# Centre on the harbour: Kowloon, HK Island and the Sai Kung hills, where the
# candidate cloud is densest and the three reported failures sit.
frame(ax, transform, dem, (114.185, 22.290), 30.0, EPSG_HK)
out = os.path.join(IMG, "hk-landslides-map.jpg")
fig.savefig(out, dpi=160, pil_kwargs={"quality": 90}, facecolor="white")
plt.close(fig)
print("wrote", out)

# ---------------------------------------------------------------------- Nepal
z = np.load(os.path.join(DATA, "nepal2026_stacks.npz"))
transform = Affine(*z["transform"])
dem = z["dem"]
EPSG_NP = "EPSG:32645"

fig, ax, extent = hillshade_ax(dem, transform)

# Miteri Bridge and the source zone are 28 km apart along a north-south valley,
# so no landscape crop holds both. Frame the upper catchment, where the study
# actually looked, and put the radar on it: the dark patches we tested and
# rejected as wet snow are what give the card its subject.
dark = np.isfinite(z["vv_test"]) & (z["vv_test"] <= -15.0)
ax.imshow(np.where(dark, 1.0, np.nan), extent=extent,
          cmap=matplotlib.colors.ListedColormap([TERRA]),
          vmin=0, vmax=1, alpha=0.5, interpolation="nearest", zorder=3)

SOURCE = (85.6088, 28.5323)   # the glaciated zone the series interrogates
x, y = tr("EPSG:4326", EPSG_NP, [SOURCE[0]], [SOURCE[1]])
ax.scatter(x, y, s=430, facecolors="none", edgecolors=PLUM, linewidths=3.4,
           zorder=6)
ax.annotate("source zone", (x[0], y[0]), xytext=(-24, 14), ha="right",
            textcoords="offset points", fontsize=17, weight="bold",
            color=PLUM, zorder=7,
            path_effects=[pe.withStroke(linewidth=4.0, foreground="white")])

frame(ax, transform, dem, (85.53, 28.470), 34.0, EPSG_NP)
out = os.path.join(IMG, "nepal-barrier-lake.jpg")
fig.savefig(out, dpi=160, pil_kwargs={"quality": 90}, facecolor="white")
plt.close(fig)
print("wrote", out)
