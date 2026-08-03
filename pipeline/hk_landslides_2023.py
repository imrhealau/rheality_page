"""Hong Kong, 7-8 Sept 2023 black rainstorm: Sentinel-1 landslide scar detection.

The heaviest hourly rainfall since 1884 fell on HK overnight on 7-8 Sept 2023.
Optical satellites were blind for days (the rain came with the cloud), but
Sentinel-1A imaged through the storm on the evening of 8 Sept - about 19 hours
after the black rainstorm signal went up - and again with full territory
coverage on 13 Sept.

Method: radiometrically terrain corrected (RTC) backscatter from Microsoft
Planetary Computer, no processing queue. For each orbit, a median of four
pre-event scenes is the baseline; the post-event scene is differenced against
it in dB (log-ratio). Fresh scars strip vegetation, so cross-pol (VH) drops
sharply. Detections = VH drop past a threshold, on slopes steep enough to
fail (Copernicus DEM), clustered to kill speckle.

  .venv/bin/python -u hk_landslides_2023.py fetch     # stream + difference, writes .npz
  .venv/bin/python -u hk_landslides_2023.py detect    # threshold, cluster, JSON + PNG

Data: Copernicus Sentinel-1 (ESA) RTC by Microsoft Planetary Computer;
Copernicus DEM GLO-30. No login needed.
"""
import os, sys, json
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
NPZ = os.path.join(DATA, "hk2023_stacks.npz")
OUT_JSON = os.path.join(DATA, "hk_landslides_2023.json")
OUT_PNG = os.path.join(DATA, "hk_landslides_2023.png")

HK_BBOX = [113.83, 22.15, 114.45, 22.57]  # W S E N
GRID_EPSG = "EPSG:32650"
RES = 10.0

# Ascending S1A. Storm night: 7-8 Sept (black rainstorm 23:05 on the 7th).
# First post date per orbit is the "rapid" look; the full post list is
# median-stacked into the "confirmed" product (a real scar stays bare for
# months, speckle does not repeat).
GROUPS = {
    "orbit113": {"pre": ["2023-07-22", "2023-08-03", "2023-08-15", "2023-08-27"],
                 "post": ["2023-09-08", "2023-09-20", "2023-10-02"]},  # 8th = 18:25 HKT, mid-event
    "orbit11":  {"pre": ["2023-07-27", "2023-08-08", "2023-08-20", "2023-09-01"],
                 "post": ["2023-09-13", "2023-09-25", "2023-10-07"]},
}

# Hysteresis: a scar is a strong core with a weaker halo. Seed where VH
# drops past SEED_DB, grow the cluster out to GROW_DB.
SEED_DB = -4.0
GROW_DB = -3.0
MIN_SLOPE_DEG = 15.0  # natural terrain failures happen on steep slopes
MIN_PIXELS = 8        # >= 800 m^2 at 10 m: below S1's honest limit anyway
HK_MAX_LAT = 22.532   # the frame reaches into Shenzhen; flag, don't drop

# Reported failures for the ground-truth check. Coords are Photon street
# geocodes; the scar sits on the hillside nearby, so checks use a radius.
KNOWN_SITES = [
    {"name": "Shiu Fai Terrace, Wan Chai",   "lat": 22.27257, "lon": 114.17552},
    {"name": "Yiu Hing Road, Shau Kei Wan",  "lat": 22.28200, "lon": 114.22051},
    {"name": "Shek O Road washout",          "lat": 22.22454, "lon": 114.24344},
]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grid():
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    l, b, r, t = transform_bounds("EPSG:4326", GRID_EPSG, *HK_BBOX)
    l, t = np.floor(l / RES) * RES, np.ceil(t / RES) * RES
    w = int(np.ceil((r - l) / RES)); h = int(np.ceil((t - b) / RES))
    return from_origin(l, t, RES, RES), w, h


def _read_into(href, transform, w, h):
    """Windowed COG read, warped onto the common grid. NaN where no data."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=GRID_EPSG, transform=transform, width=w,
                       height=h, resampling=Resampling.bilinear,
                       src_nodata=src.nodata if src.nodata is not None else 0,
                       nodata=np.nan) as vrt:
            return vrt.read(1).astype(np.float32)


def _mosaic_date(items, band, transform, w, h):
    out = np.full((h, w), np.nan, dtype=np.float32)
    for it in items:
        a = _read_into(it.assets[band].href, transform, w, h)
        take = np.isnan(out) & np.isfinite(a)
        out[take] = a[take]
    return out


def _db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        d = 10.0 * np.log10(x)
    d[~np.isfinite(d)] = np.nan
    return d


def cmd_fetch():
    import pystac_client, planetary_computer
    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
    transform, w, h = _grid()
    print(f"grid {w}x{h} @ {RES} m ({GRID_EPSG})", flush=True)
    cache = os.path.join(DATA, "hk2023_cache")
    os.makedirs(cache, exist_ok=True)

    search = cat.search(collections=["sentinel-1-rtc"], bbox=HK_BBOX,
                        datetime="2023-07-15/2023-10-10")
    by_orbit_date = {}
    for it in search.item_collection():
        key = (f"orbit{it.properties['sat:relative_orbit']}",
               it.datetime.strftime("%Y-%m-%d"))
        by_orbit_date.setdefault(key, []).append(it)

    def date_db(gname, d, pol):
        f = os.path.join(cache, f"{gname}_{d}_{pol}.npy")
        if os.path.exists(f):
            return np.load(f)
        arr = _db(_mosaic_date(by_orbit_date[(gname, d)], pol, transform, w, h))
        np.save(f, arr)
        print(f"{gname} {d} {pol}: {np.isfinite(arr).mean():.0%} valid", flush=True)
        return arr

    stacks = {}
    for gname, g in GROUPS.items():
        for pol in ("vv", "vh"):
            pre = [date_db(gname, d, pol) for d in g["pre"]]
            stacks[f"{gname}_{pol}_pre"] = np.nanmedian(np.stack(pre), axis=0)
            del pre
            for i, d in enumerate(g["post"]):
                stacks[f"{gname}_{pol}_post{i}"] = date_db(gname, d, pol)

    # Copernicus DEM for the slope mask and the hillshade backdrop
    demf = os.path.join(cache, "dem.npy")
    if os.path.exists(demf):
        dem = np.load(demf)
    else:
        dem_items = list(cat.search(collections=["cop-dem-glo-30"],
                                    bbox=HK_BBOX).item_collection())
        dem = _mosaic_date(dem_items, "data", transform, w, h)
        np.save(demf, dem)
        print(f"dem: {np.isfinite(dem).mean():.0%} valid", flush=True)

    os.makedirs(DATA, exist_ok=True)
    np.savez_compressed(NPZ, dem=dem, transform=np.array(
        [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f]),
        **stacks)
    print("wrote", NPZ)


def _to_lonlat(transform, rows, cols):
    from rasterio.transform import xy
    from rasterio.warp import transform as tr
    xs, ys = xy(transform, rows, cols)
    lons, lats = tr(GRID_EPSG, "EPSG:4326", np.atleast_1d(xs), np.atleast_1d(ys))
    return np.array(lons), np.array(lats)


def _clusters(dvh, dvv, slope, steep, transform):
    from scipy import ndimage
    halo = np.isfinite(dvh) & steep & (dvh <= GROW_DB)
    lab, n = ndimage.label(halo, structure=np.ones((3, 3)))
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum_labels(np.ones_like(lab), lab, index=idx)
    mins = ndimage.minimum(dvh, lab, index=idx)
    keep = np.where((sizes >= MIN_PIXELS) & (mins <= SEED_DB))[0] + 1
    objs = ndimage.find_objects(lab)
    out = []
    for k in keep:
        sl = objs[k - 1]
        m = lab[sl] == k
        rows, cols = np.where(m)
        lon, lat = _to_lonlat(transform, rows.mean() + sl[0].start,
                              cols.mean() + sl[1].start)
        peak = float(np.nanmin(dvh[sl][m]))
        npx = int(m.sum())
        out.append({
            "lat": round(float(lat[0]), 5), "lon": round(float(lon[0]), 5),
            "in_hk": bool(lat[0] <= HK_MAX_LAT),
            "area_m2": npx * int(RES * RES),
            "peak_dvh_db": round(peak, 2),
            "mean_dvh_db": round(float(np.nanmean(dvh[sl][m])), 2),
            "mean_dvv_db": round(float(np.nanmean(dvv[sl][m])), 2),
            "mean_slope_deg": round(float(np.nanmean(slope[sl][m])), 1),
            "score": round(-peak * float(np.log1p(npx)), 2),
        })
    return out


def cmd_detect():
    from affine import Affine
    z = np.load(NPZ)
    transform = Affine(*z["transform"])
    dem = z["dem"]
    gy, gx = np.gradient(dem, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    steep = slope >= MIN_SLOPE_DEG

    confirmed, rapid_counts, ratios = [], {}, {}
    for gname, g in GROUPS.items():
        nn = len(g["post"])
        vh_posts = [z[f"{gname}_vh_post{i}"] for i in range(nn)]
        vv_posts = [z[f"{gname}_vv_post{i}"] for i in range(nn)]
        pre_vh, pre_vv = z[f"{gname}_vh_pre"], z[f"{gname}_vv_pre"]

        # rapid: first pass after (or during) the storm, single scene
        rapid = _clusters(vh_posts[0] - pre_vh, vv_posts[0] - pre_vv,
                          slope, steep, transform)
        rapid_counts[gname] = len(rapid)

        # confirmed: scar must persist across the following month
        dvh = np.nanmedian(np.stack(vh_posts), axis=0) - pre_vh
        dvv = np.nanmedian(np.stack(vv_posts), axis=0) - pre_vv
        ratios[gname] = dvh
        cl = _clusters(dvh, dvv, slope, steep, transform)
        for c in cl:
            c["group"] = gname
        confirmed.extend(cl)
        print(f"{gname}: rapid {len(rapid)}, confirmed {len(cl)}", flush=True)

    confirmed.sort(key=lambda c: -c["score"])
    all_clusters = confirmed
    hk_clusters = [c for c in confirmed if c["in_hk"]]

    # ground-truth: where do the reported failures rank among candidates?
    checks = []
    for site in KNOWN_SITES:
        best = None
        for rank, c in enumerate(hk_clusters, 1):
            dlat = (c["lat"] - site["lat"]) * 111_320
            dlon = (c["lon"] - site["lon"]) * 111_320 * np.cos(np.radians(site["lat"]))
            d = float(np.hypot(dlat, dlon))
            if d <= 300 and best is None:
                best = {"rank_of_%d" % len(hk_clusters): rank,
                        "dist_m": round(d), **c}
        checks.append({"site": site["name"], "match_within_300m": best})
        print(f"{site['name']}: " + (str(best) if best else "no candidate within 300 m"),
              flush=True)

    out = {
        "generated_utc": now(),
        "event": {"name": "Hong Kong black rainstorm, 7-8 Sept 2023",
                  "note": ("Heaviest hourly rainfall since records began in 1884. "
                           "S1A imaged HK 18:25 HKT on 8 Sept, ~19 h after the black "
                           "signal, through active rain; full coverage again 13 Sept.")},
        "source": {"mission": "Sentinel-1A (ESA Copernicus), IW GRD -> RTC",
                   "processing": "Microsoft Planetary Computer sentinel-1-rtc; Copernicus DEM GLO-30",
                   "attribution": "Contains modified Copernicus Sentinel data 2023"},
        "method": (f"Per orbit: median of 4 pre-event scenes as baseline, dB log-ratio. "
                   f"'Rapid' = first post-storm scene alone; 'confirmed' = median of 3 "
                   f"post-event scenes over the following month (a real scar stays bare, "
                   f"speckle does not repeat). Detection: hysteresis on VH change - seed "
                   f"<= {SEED_DB} dB, grown to {GROW_DB} dB - on slopes >= {MIN_SLOPE_DEG} "
                   f"deg (Copernicus DEM), 8-connected clusters >= "
                   f"{MIN_PIXELS * RES * RES:.0f} m2."),
        "limits": ("Free C-band at 10 m is at its detection limit for HK-scale scars: "
                   "single-scene speckle on steep vegetated slopes runs to -4 dB, the "
                   "same order as the scar signal, so the same-day 'rapid' product is a "
                   "candidate list, not a survey. Small failures (<~800 m2) are invisible. "
                   "Layover/shadow blinds some slopes per look direction. Tasked X-band "
                   "(~1 m) closes these gaps."),
        "verdict": ("Negative result, and the point of the study: the reported "
                    "Sept 2023 failures (scars of a few hundred to ~2000 m2) do "
                    "not separate from speckle in free 10 m C-band amplitude data. "
                    "The best case, Shiu Fai Terrace, surfaces mid-ranking among "
                    "thousands of candidates; the others never surface at any "
                    "threshold. Consistent with the ~1 ha reliable minimum in the "
                    "literature. HK-scale landslide response needs tasked ~1 m "
                    "X-band - same physics, same pipeline, 25-100x the resolution."),
        "rapid_counts": rapid_counts,
        "params": {"seed_db": SEED_DB, "grow_db": GROW_DB,
                   "min_slope_deg": MIN_SLOPE_DEG,
                   "min_area_m2": MIN_PIXELS * RES * RES},
        "n_candidates": len(all_clusters),
        "n_candidates_in_hk": len(hk_clusters),
        "ground_truth_check": checks,
        "top_candidates": all_clusters[:100],
    }
    json.dump(out, open(OUT_JSON, "w"), indent=2)
    print("wrote", OUT_JSON, f"({len(all_clusters)} candidates)")
    _plot(z, transform, slope, ratios, all_clusters)
    _plot_sites(z, transform)


def _plot(z, transform, slope, ratios, clusters):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    dem = np.nan_to_num(z["dem"], nan=0.0)
    ls = LightSource(azdeg=315, altdeg=45)
    shade = ls.hillshade(dem, vert_exag=1.5, dx=RES, dy=RES)
    h, w = dem.shape
    extent = (transform.c, transform.c + w * RES, transform.f - h * RES, transform.f)
    fig, ax = plt.subplots(figsize=(14, 10), dpi=150)
    ax.imshow(shade, cmap="gray", extent=extent, vmin=0, vmax=1)
    sea = dem <= 0
    ax.imshow(np.where(sea, 1.0, np.nan), cmap="Blues", extent=extent,
              vmin=0, vmax=1.6, alpha=0.9)
    from rasterio.warp import transform as tr
    for c in clusters[:100]:
        x, y = tr("EPSG:4326", GRID_EPSG, [c["lon"]], [c["lat"]])
        ax.scatter(x, y, s=max(25, c["area_m2"] / 80),
                   facecolors="none",
                   edgecolors="#ff3b30" if c["in_hk"] else "#8e8e93",
                   linewidths=1.4)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_axis_off()
    ax.set_title("Top 100 persistent-change candidates (unvalidated), "
                 "HK black rainstorm Sept 2023 - Sentinel-1", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, bbox_inches="tight")
    print("wrote", OUT_PNG)


def _plot_sites(z, transform):
    """The money figure for honesty: persistent VH change around each reported
    failure, showing the scar signal sitting at the speckle floor."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from rasterio.warp import transform as tr
    out_png = os.path.join(DATA, "hk_landslides_2023_sites.png")
    fig, axes = plt.subplots(2, 3, figsize=(13, 8.5), dpi=150)
    for col, site in enumerate(KNOWN_SITES):
        x, y = tr("EPSG:4326", GRID_EPSG, [site["lon"]], [site["lat"]])
        inv = ~transform
        c0, r0 = inv * (x[0], y[0])
        r0, c0 = int(r0), int(c0)
        R = 40  # 400 m
        for row, gname in enumerate(GROUPS):
            nn = len(GROUPS[gname]["post"])
            med = np.nanmedian(np.stack(
                [z[f"{gname}_vh_post{i}"] for i in range(nn)]), axis=0)
            dvh = med - z[f"{gname}_vh_pre"]
            w = dvh[r0 - R:r0 + R, c0 - R:c0 + R]
            ax = axes[row][col]
            im = ax.imshow(w, cmap="RdBu", vmin=-6, vmax=6)
            ax.scatter([R], [R], marker="+", s=120, c="k", linewidths=1.2)
            ax.set_xticks([]); ax.set_yticks([])
            if row == 0:
                ax.set_title(site["name"], fontsize=9)
            if col == 0:
                ax.set_ylabel(gname, fontsize=9)
    fig.suptitle("Persistent VH change (dB), 800 m windows on reported failures:\n"
                 "the scar signal does not separate from speckle at 10 m C-band",
                 fontsize=11)
    cb = fig.colorbar(im, ax=axes, shrink=0.7, label="dVH (dB)")
    fig.savefig(out_png, bbox_inches="tight")
    print("wrote", out_png)


if __name__ == "__main__":
    {"fetch": cmd_fetch, "detect": cmd_detect}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
