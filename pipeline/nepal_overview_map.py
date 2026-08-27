"""Overview map: the extent of the 26 Aug 2026 failure, and where the second lake sits.

The flood path is not drawn by hand. It is traced down the Copernicus DEM by
steepest descent from the border at Rasuwagadhi, so the corridor on the map is
the one the water actually had to follow, and distance along it is measured
rather than asserted.

The second lake is drawn as a zone, not a pin. Reporting places it at the
Chhochen Khola and Purepu Tsangpo confluence in the upper catchment, and no
source has published a coordinate for it.

  .venv/bin/python -u nepal_overview_map.py
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.patches import Rectangle
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, transform as tr
from scipy import ndimage

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "nepal_overview_cache")
OUT = os.path.abspath(os.path.join(HERE, "..", "research", "nepal-barrier-lake", "img"))
os.makedirs(CACHE, exist_ok=True); os.makedirs(OUT, exist_ok=True)

AOI = [85.05, 27.80, 85.92, 28.82]   # W S E N
RES, EPSG = 30.0, "EPSG:32645"
PLUM, TERRA, MUT = "#33254E", "#CD5A1F", "#6F6488"
RIVER, DAMAGE = "#5B8DB8", "#C62A16"

# Only places with coordinates we have used consistently elsewhere.
MARKS = [
    (85.3789, 28.2817, "Rasuwagadhi / Miteri Bridge"),
    (85.3736, 28.2506, "Timure"),
    (85.3339, 28.1622, "Syabrubesi"),
]
SECOND_LAKE_ZONE = [85.44, 28.46, 85.86, 28.78]   # upper catchment, reported reach


def grid():
    l, b, r, t = transform_bounds("EPSG:4326", EPSG, *AOI)
    l, t = np.floor(l / RES) * RES, np.ceil(t / RES) * RES
    w = int(np.ceil((r - l) / RES)); h = int(np.ceil((t - b) / RES))
    return from_origin(l, t, RES, RES), w, h


def fetch_dem(transform, w, h):
    f = os.path.join(CACHE, "dem.npy")
    if os.path.exists(f):
        return np.load(f)
    import pystac_client, planetary_computer, rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["cop-dem-glo-30"], bbox=AOI).item_collection())
    out = np.full((h, w), np.nan, dtype=np.float32)
    for it in items:
        with rasterio.open(it.assets["data"].href) as src:
            with WarpedVRT(src, crs=EPSG, transform=transform, width=w, height=h,
                           resampling=Resampling.bilinear, src_nodata=-32768,
                           nodata=np.nan) as vrt:
                a = vrt.read(1).astype(np.float32)
        take = np.isnan(out) & np.isfinite(a)
        out[take] = a[take]
    np.save(f, out)
    print(f"dem {np.nanmin(out):.0f}-{np.nanmax(out):.0f} m, "
          f"{np.isfinite(out).mean():.0%} valid", flush=True)
    return out


def block_min(a, k):
    """Downsample by block minimum, which keeps the channel rather than
    averaging it away against the valley walls."""
    h, w = a.shape
    h2, w2 = h // k, w // k
    return np.nanmin(a[:h2 * k, :w2 * k].reshape(h2, k, w2, k), axis=(1, 3))


def fill_pits(dem):
    """Priority flood. Every cell ends at least as high as the lowest path to
    the edge, so steepest descent can no longer strand itself in a hollow."""
    import heapq
    h, w = dem.shape
    filled = np.full((h, w), np.inf, dtype=np.float64)
    done = np.zeros((h, w), bool)
    heap = []
    for r in range(h):
        for c in (0, w - 1):
            if np.isfinite(dem[r, c]):
                filled[r, c] = dem[r, c]; done[r, c] = True
                heapq.heappush(heap, (float(dem[r, c]), r, c))
    for c in range(w):
        for r in (0, h - 1):
            if np.isfinite(dem[r, c]) and not done[r, c]:
                filled[r, c] = dem[r, c]; done[r, c] = True
                heapq.heappush(heap, (float(dem[r, c]), r, c))
    while heap:
        e, r, c = heapq.heappop(heap)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < h and 0 <= cc < w) or done[rr, cc]:
                continue
            if not np.isfinite(dem[rr, cc]):
                continue
            # The epsilon is what makes the result strictly descending toward
            # the outlet. Without it, filled flats are level and a descent trace
            # wanders into them and strands.
            ne = max(float(dem[rr, cc]), e + 1e-3)
            filled[rr, cc] = ne; done[rr, cc] = True
            heapq.heappush(heap, (ne, rr, cc))
    return filled


def descend(dem, r0, c0, max_steps=200000):
    """Steepest descent on a pit-filled surface, with a tiny downhill bias so
    flat filled reaches still resolve to a single path."""
    h, w = dem.shape
    path = [(r0, c0)]
    seen = {(r0, c0)}
    r, c = r0, c0
    for _ in range(max_steps):
        best, br, bc = np.inf, None, None
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if not (0 <= rr < h and 0 <= cc < w) or (rr, cc) in seen:
                    continue
                v = dem[rr, cc]
                if np.isfinite(v) and v < best:
                    best, br, bc = v, rr, cc
        if br is None or best > dem[r, c] + 1e-6:
            break
        r, c = br, bc
        seen.add((r, c))
        path.append((r, c))
        if r >= h - 2 or c <= 1 or r <= 1:
            break
    return np.array(path)


transform, w, h = grid()
print(f"grid {w}x{h} @ {RES} m", flush=True)
dem = fetch_dem(transform, w, h)

xs0, ys0 = transform.c, transform.f
def to_px(lon, lat):
    x, y = tr("EPSG:4326", EPSG, [lon], [lat])
    return int((ys0 - y[0]) / RES), int((x[0] - xs0) / RES)
def to_xy(rr, cc):
    return xs0 + (np.asarray(cc) + 0.5) * RES, ys0 - (np.asarray(rr) + 0.5) * RES

# Trace on a 4x coarser grid. 120 m is ample for a 100 km corridor and it makes
# the priority flood cheap.
K = 4
coarse = block_min(dem, K)
print(f"trace grid {coarse.shape[1]}x{coarse.shape[0]} @ {RES*K:.0f} m", flush=True)
filled = fill_pits(coarse)
print(f"pits filled, raised {np.nansum(filled > coarse + 0.01):,} cells", flush=True)

r0, c0 = to_px(*MARKS[0][:2])
r0, c0 = r0 // K, c0 // K
R = 10
win = filled[r0 - R:r0 + R, c0 - R:c0 + R]
i = np.unravel_index(np.nanargmin(win), win.shape)
r0, c0 = r0 - R + i[0], c0 - R + i[1]
print(f"trace start {coarse[r0, c0]:.0f} m", flush=True)

path = descend(filled, r0, c0)
px, py = to_xy(path[:, 0] * K + K // 2, path[:, 1] * K + K // 2)
seg = np.hypot(np.diff(px), np.diff(py))
cum = np.concatenate([[0], np.cumsum(seg)]) / 1000.0
print(f"traced {len(path):,} cells, {cum[-1]:.1f} km, "
      f"{coarse[path[0,0],path[0,1]]:.0f} to {coarse[path[-1,0],path[-1,1]]:.0f} m",
      flush=True)
i60 = min(int(np.searchsorted(cum, 60.0)), len(cum) - 1)
if cum[-1] < 55:
    print(f"WARNING: trace only reached {cum[-1]:.1f} km, expected ~60+", flush=True)

# drainage backdrop
vwin = int(1800 / RES)
d0 = np.nan_to_num(dem, nan=9999)
lo = ndimage.minimum_filter(d0, size=vwin)
hi = ndimage.maximum_filter(np.nan_to_num(dem, nan=-9999), size=vwin)
# Near the local floor AND genuinely confined. Without the relief test the flat
# Tibetan plateau is trivially within 25 m of its own minimum and the whole of
# it paints in as river.
valley = ((dem - lo) < 25) & ((hi - lo) > 250) & (dem < 5200)

ls = LightSource(azdeg=315, altdeg=42)
shade = ls.hillshade(np.nan_to_num(dem, nan=0.0), vert_exag=1.4, dx=RES, dy=RES)
extent = (transform.c, transform.c + w * RES, transform.f - h * RES, transform.f)

fig, ax = plt.subplots(figsize=(8.6, 9.6), dpi=160)
ax.imshow(shade, cmap="gray", extent=extent, vmin=0, vmax=1.06, interpolation="bilinear")
ax.imshow(np.where(valley, 1.0, np.nan), extent=extent, cmap=ListedColormap([RIVER]),
          vmin=0, vmax=1, alpha=0.55, interpolation="nearest", zorder=2)

ax.plot(px[i60:], py[i60:], color=RIVER, lw=2.0, zorder=3, alpha=0.9)
ax.plot(px[:i60], py[:i60], color=DAMAGE, lw=4.2, zorder=4,
        solid_capstyle="round", path_effects=[pe.withStroke(linewidth=6.6,
                                                            foreground="white")])
ax.scatter(px[i60], py[i60], s=70, color=DAMAGE, zorder=5, edgecolors="white",
           linewidths=1.2)
ax.annotate("about 60 km of valley\ndamaged downstream", (px[i60], py[i60]),
            xytext=(16, -6), textcoords="offset points", fontsize=10,
            color=DAMAGE, weight="bold", zorder=8,
            path_effects=[pe.withStroke(linewidth=3.6, foreground="white")])

for lon, lat, name in MARKS:
    x, y = tr("EPSG:4326", EPSG, [lon], [lat])
    ax.scatter(x, y, marker="o", s=62, c="white", edgecolors=PLUM,
               linewidths=2.0, zorder=7)
    ax.annotate(name, (x[0], y[0]), xytext=(13, 7), textcoords="offset points",
                fontsize=10, color=PLUM, weight="bold", zorder=8,
                path_effects=[pe.withStroke(linewidth=3.6, foreground="white")])

zx0, zy0 = tr("EPSG:4326", EPSG, [SECOND_LAKE_ZONE[0]], [SECOND_LAKE_ZONE[1]])
zx1, zy1 = tr("EPSG:4326", EPSG, [SECOND_LAKE_ZONE[2]], [SECOND_LAKE_ZONE[3]])
ax.add_patch(Rectangle((zx0[0], zy0[0]), zx1[0] - zx0[0], zy1[0] - zy0[0],
                       fill=True, facecolor=TERRA, alpha=0.14, zorder=5))
ax.add_patch(Rectangle((zx0[0], zy0[0]), zx1[0] - zx0[0], zy1[0] - zy0[0],
                       fill=False, edgecolor=TERRA, lw=2.4, ls=(0, (6, 4)), zorder=6))
ax.annotate("second barrier lake\nreported in this reach,\nat the Chhochen Khola /\n"
            "Purepu Tsangpo confluence",
            ((zx0[0] + zx1[0]) / 2, zy1[0]), xytext=(0, -14),
            textcoords="offset points", fontsize=10, color=TERRA, weight="bold",
            ha="center", va="top", zorder=8,
            path_effects=[pe.withStroke(linewidth=3.6, foreground="white")])

sbx, sby = extent[1] - 26000, extent[2] + 5000
ax.plot([sbx, sbx + 20000], [sby, sby], color=PLUM, lw=3.6, solid_capstyle="butt",
        zorder=8)
ax.text(sbx + 10000, sby + 2200, "20 km", ha="center", fontsize=9.5, color=PLUM,
        weight="bold", zorder=8,
        path_effects=[pe.withStroke(linewidth=3.2, foreground="white")])

ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
ax.set_axis_off()
ax.set_title("Where the failure ran, and where the next one is sitting\n"
             "Flood path traced by steepest descent down the Copernicus DEM",
             color=PLUM, fontsize=11.5, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "overview_map.png"), bbox_inches="tight", facecolor="white")
print("wrote overview_map.png")
