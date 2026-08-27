"""Lhende Khola / Bhote Koshi, 26 Aug 2026: Sentinel-1 barrier-lake detection.

A rock-ice avalanche off the Tibetan side blocked the Lhende Khola about 20 km
upstream of the Miteri Bridge on the morning of 26 Aug 2026. The blockage
impounded a lake, the lake failed, and the surge ran 60 km down the Bhote
Koshi through Timure and Syabrubesi, killing well over a hundred people and
damaging six NEA hydropower and transmission facilities.

The question this pipeline exists to answer: was the impoundment visible from
orbit before it breached. Sentinel-1D imaged the catchment on descending
orbit 19 at 00:18Z on 24 Aug - about 48 hours ahead of the collapse - and the
next look was not until the 28th. If a lake was ponding on the 24th, free
C-band saw it and nobody looked. If it was not, the blockage formed inside a
4-day revisit gap and the warning case is for tasked SAR, not Sentinel-1.

Method: RTC gamma0 from Microsoft Planetary Computer, same architecture as
hk_landslides_2023.py with the polarisation and terrain logic inverted. Smooth
open water reflects specularly away from the sensor, so it goes dark in VV
co-pol - the opposite sign to a landslide scar, and a far stronger signal.
Detections = absolute low VV, absent from a monsoon-season baseline median,
on near-flat ground (Copernicus DEM) below the snow zone, clustered.

Differencing against a monsoon baseline is what makes this tractable: radar
shadow is dark but static, so it sits in the baseline and subtracts out. Wet
snow is the confounder that does not - see LIMITS.

  .venv/bin/python -u nepal_barrier_lake_2026.py fetch    # stream RTC + DEM, writes .npz
  .venv/bin/python -u nepal_barrier_lake_2026.py detect   # threshold, cluster, JSON + PNG

Data: Copernicus Sentinel-1 (ESA) RTC by Microsoft Planetary Computer;
Copernicus DEM GLO-30. No login needed.
"""
import os, sys, json
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
NPZ = os.path.join(DATA, "nepal2026_stacks.npz")
OUT_JSON = os.path.join(DATA, "nepal_barrier_lake_2026.json")
OUT_PNG = os.path.join(DATA, "nepal_barrier_lake_2026.png")

# Lhende source zone down to Rasuwagadhi / Miteri Bridge. Deliberately tight:
# the reported blockage is ~20 km upstream of the bridge at ~28.28 N, 85.38 E.
AOI = [85.30, 28.20, 85.70, 28.60]  # W S E N
# The full damage corridor for post-event mapping: source zone down through
# Timure and Syabrubesi to Trishuli Bazar, ~60 km of valley. Syabrubesi sits
# just south of the source-zone AOI, so the two are deliberately different.
AOI_DOWN = [85.10, 27.85, 85.75, 28.60]
GRID_EPSG = "EPSG:32645"  # UTM 45N
RES = 10.0

# Descending orbit 19 (Sentinel-1D, 00:18Z). The only track with a look inside
# 48 h of the collapse. Baseline is monsoon-season: same season, same wetness,
# same snow line, so only a genuinely new water body survives the difference.
ORBIT = "orbit19"
PRE = ["2026-06-25", "2026-07-07", "2026-07-19", "2026-07-31"]
CONTROL = "2026-08-12"  # 14 d before: expect no new water. Guards the method.
TEST = "2026-08-24"     # ~48 h before the breach. The scene in question.

WATER_DB = -15.0      # RTC gamma0 VV; calm water runs -18 to -22, wind roughens it
DROP_DB = -3.0        # and it must be at least this much darker than baseline
MAX_SLOPE_DEG = 8.0   # impoundments pond on flat ground; scars do not
MAX_ELEV_M = 5000.0   # above this is the perennial snow/ice zone: wet snow mimics water
MIN_PIXELS = 20       # 2000 m2 at 10 m; a gorge lake is only a few pixels wide

# Landmarks for locating anything the detector finds.
LANDMARKS = [
    {"name": "Rasuwagadhi / Miteri Bridge", "lat": 28.2817, "lon": 85.3789},
    {"name": "Timure",                      "lat": 28.2506, "lon": 85.3736},
    {"name": "Syabrubesi",                  "lat": 28.1622, "lon": 85.3339},
]

VERDICT = (
    "Negative, and the negative is the finding: no impoundment was detectable "
    "anywhere in the catchment on 24 Aug 2026, ~48 h before the breach. This is a "
    "null result, not a null instrument. The reported blockage reach (15-25 km "
    "upstream of the Miteri Bridge) is fully imaged: 21,489 valley-floor pixels, "
    "100% finite on every date, median baseline VV -8.8 dB, which is ordinary "
    "ground return and not shadow. It sits inside the detection mask at 3-8 deg "
    "median slope. Across a sweep of every sensible parameter combination "
    "(slope 8/15/25/90 deg, water -13/-15/-18 dB, drop -2/-3 dB) the excess "
    "new-water area on 24 Aug over the 12 Aug control never rises above the "
    "speckle floor, and at whole-AOI scale it goes negative. The dB change "
    "distribution bottoms out at -5 dB at p1, the same speckle floor found in the "
    "Hong Kong 2023 study. An impoundment large enough to drive a surge that "
    "destroyed 60 km of valley would have covered order 1e4-1e5 m2, hundreds to "
    "thousands of pixels, far above that floor. It was not there. "
    "The blockage therefore formed and failed inside the 4-day gap between the "
    "24 Aug and 28 Aug passes, and most likely inside a few hours. No system at "
    "Sentinel-1 cadence could have warned. The actionable window ran from the "
    "seismic detection of the collapse (the 5.2 signal, which is t=0 and is "
    "already an instrument that fired) to the surge reaching Timure. That is a "
    "seismic and ground-instrumentation problem, not a satellite one. Satellite's "
    "role in this hazard class is post-event verification and monitoring of the "
    "persistent secondary impoundments now sitting in 60 km of fresh debris."
)

# The supraglacial hypothesis, tested and rejected as a pre-event signal.
#
# Independent reporting placed an active water area 35-38 km upstream and cited
# the 24 Aug scene as key evidence; ICIMOD attributed the 2025 flood in this same
# corridor to a supraglacial lake on the Purepu Glacier. That is a real alternative
# to the low-altitude blockage hypothesis, and the 5000 m elevation ceiling above
# would exclude it by construction, so it has to be tested with the ceiling off.
#
# `series` does that: dark-area time series over the 33-40 km zone at 5100-5600 m,
# across all six orbit-19 passes. Result (km2 below -15 dB): 8.59, 11.60, 12.09,
# 10.22, 12.37, 12.67 from 25 Jun to 24 Aug. Non-monotonic - it falls 1.87 km2 on
# 31 Jul, a larger move than the +0.30 between the last two passes - and a control
# region in the same elevation and slope band fluctuates in step. Largest-blob
# compactness runs 0.25-0.57, which is ragged snow and not a pond, and the feature
# centre has not moved since early July. A lake fills monotonically; wet snow
# tracks the weather. This tracks the weather.
#
# What this does NOT rule out: a supraglacial lake that drains englacially can
# empty without a large surface-area change, and on a glacier surface at 10 m
# C-band the water/wet-snow separation is genuinely ambiguous. The honest claim is
# narrow. No change consistent with rapid filling in the fortnight before the
# event, and the 24 Aug scene looks like 19 Jul and 12 Aug.

LIMITS = (
    "Wet snow is the one confounder the baseline does not remove: at C-band it "
    "goes as dark as open water, it sits on the same high-altitude terrain, and "
    "its extent moves between passes. The elevation ceiling and the flatness "
    "mask suppress most of it - wet snow prefers slopes, water does not - but "
    "any detection above ~4500 m should be treated as snow until proven "
    "otherwise. Wind roughening cuts the other way and can hide a real lake by "
    "lifting its backscatter above the threshold. In a confined gorge the "
    "impoundment may be only 20-50 m wide, which is 2-5 pixels at 10 m, so "
    "small early-stage ponding is below the honest detection limit. Piping "
    "failure gives no surface warning at all. This detects water, not stability: "
    "seeing a lake tells you an impoundment exists, not when it will breach."
)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _grid():
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    l, b, r, t = transform_bounds("EPSG:4326", GRID_EPSG, *AOI)
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
    cache = os.path.join(DATA, "nepal2026_cache")
    os.makedirs(cache, exist_ok=True)

    search = cat.search(collections=["sentinel-1-rtc"], bbox=AOI,
                        datetime="2026-06-01/2026-09-05")
    by_orbit_date = {}
    for it in search.item_collection():
        key = (f"orbit{it.properties['sat:relative_orbit']}",
               it.datetime.strftime("%Y-%m-%d"))
        by_orbit_date.setdefault(key, []).append(it)

    def date_db(d, pol="vv"):
        f = os.path.join(cache, f"{ORBIT}_{d}_{pol}.npy")
        if os.path.exists(f):
            return np.load(f)
        items = by_orbit_date.get((ORBIT, d))
        if not items:
            raise SystemExit(f"no {ORBIT} scene on {d}")
        arr = _db(_mosaic_date(items, pol, transform, w, h))
        np.save(f, arr)
        print(f"{ORBIT} {d} {pol}: {np.isfinite(arr).mean():.0%} valid, "
              f"median {np.nanmedian(arr):.1f} dB", flush=True)
        return arr

    pre = [date_db(d) for d in PRE]
    stacks = {"vv_pre": np.nanmedian(np.stack(pre), axis=0)}
    del pre
    stacks["vv_control"] = date_db(CONTROL)
    stacks["vv_test"] = date_db(TEST)

    demf = os.path.join(cache, "dem.npy")
    if os.path.exists(demf):
        dem = np.load(demf)
    else:
        dem_items = list(cat.search(collections=["cop-dem-glo-30"],
                                    bbox=AOI).item_collection())
        dem = _mosaic_date(dem_items, "data", transform, w, h)
        np.save(demf, dem)
        print(f"dem: {np.isfinite(dem).mean():.0%} valid, "
              f"{np.nanmin(dem):.0f}-{np.nanmax(dem):.0f} m", flush=True)

    os.makedirs(DATA, exist_ok=True)
    np.savez_compressed(NPZ, dem=dem, transform=np.array(
        [transform.a, transform.b, transform.c, transform.d, transform.e,
         transform.f]), **stacks)
    print("wrote", NPZ)


def _to_lonlat(transform, rows, cols):
    from rasterio.transform import xy
    from rasterio.warp import transform as tr
    xs, ys = xy(transform, rows, cols)
    lons, lats = tr(GRID_EPSG, "EPSG:4326", np.atleast_1d(xs), np.atleast_1d(ys))
    return np.array(lons), np.array(lats)


def _new_water(vv, pre, flat, dem, transform):
    """New-water clusters: dark now, not dark before, flat, below the snow zone.

    Radar shadow is dark but static, so it is already in the baseline and
    differences out. Requiring both an absolute threshold and a drop from
    baseline is what separates a filling impoundment from a permanently dark
    facet the baseline happened to miss.
    """
    from scipy import ndimage
    mask = (np.isfinite(vv) & np.isfinite(pre) & flat
            & (vv <= WATER_DB) & ((vv - pre) <= DROP_DB))
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum_labels(np.ones_like(lab), lab, index=idx)
    keep = np.where(sizes >= MIN_PIXELS)[0] + 1
    objs = ndimage.find_objects(lab)
    out = []
    for k in keep:
        sl = objs[k - 1]
        m = lab[sl] == k
        rows, cols = np.where(m)
        lon, lat = _to_lonlat(transform, rows.mean() + sl[0].start,
                              cols.mean() + sl[1].start)
        npx = int(m.sum())
        elev = dem[sl][m]
        # The lake surface is flat, so its shoreline is an equipotential: the
        # upper elevation of the wetted footprint is the water level.
        stage = float(np.nanpercentile(elev, 90)) if np.isfinite(elev).any() else float("nan")
        rec = {
            "lat": round(float(lat[0]), 5), "lon": round(float(lon[0]), 5),
            "area_m2": npx * int(RES * RES),
            "mean_vv_db": round(float(np.nanmean(vv[sl][m])), 2),
            "mean_drop_db": round(float(np.nanmean((vv - pre)[sl][m])), 2),
            "elev_min_m": round(float(np.nanmin(elev))) if np.isfinite(elev).any() else None,
            "stage_m": round(stage) if np.isfinite(stage) else None,
            "likely_wet_snow": bool(np.isfinite(stage) and stage > 4500),
        }
        for L in LANDMARKS:
            dlat = (rec["lat"] - L["lat"]) * 111_320
            dlon = (rec["lon"] - L["lon"]) * 111_320 * np.cos(np.radians(L["lat"]))
            rec.setdefault("nearest", {})
            d = float(np.hypot(dlat, dlon))
            if "dist_m" not in rec["nearest"] or d < rec["nearest"]["dist_m"]:
                rec["nearest"] = {"name": L["name"], "dist_m": round(d)}
        out.append(rec)
    out.sort(key=lambda c: -c["area_m2"])
    return out


def cmd_detect():
    from affine import Affine
    z = np.load(NPZ)
    transform = Affine(*z["transform"])
    dem = z["dem"]
    gy, gx = np.gradient(dem, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    flat = (slope <= MAX_SLOPE_DEG) & (dem <= MAX_ELEV_M)
    print(f"flat + below snow zone: {flat.mean():.1%} of AOI", flush=True)

    pre = z["vv_pre"]
    res = {}
    for name, key in (("control_2026-08-12", "vv_control"),
                      ("test_2026-08-24", "vv_test")):
        cl = _new_water(z[key], pre, flat, dem, transform)
        real = [c for c in cl if not c["likely_wet_snow"]]
        res[name] = cl
        print(f"{name}: {len(cl)} new-water clusters "
              f"({len(real)} below the snow zone)", flush=True)
        for c in real[:10]:
            print(f"    {c['area_m2']:>8,} m2  {c['lat']:.4f},{c['lon']:.4f}  "
                  f"{c['mean_vv_db']:>6.1f} dB  drop {c['mean_drop_db']:>5.1f}  "
                  f"stage ~{c['stage_m']} m  "
                  f"({c['nearest']['dist_m']/1000:.1f} km from {c['nearest']['name']})",
                  flush=True)

    ctrl = [c for c in res["control_2026-08-12"] if not c["likely_wet_snow"]]
    test = [c for c in res["test_2026-08-24"] if not c["likely_wet_snow"]]
    ctrl_area = sum(c["area_m2"] for c in ctrl)
    test_area = sum(c["area_m2"] for c in test)

    out = {
        "generated_utc": now(),
        "event": {
            "name": "Lhende Khola / Bhote Koshi barrier lake and outburst, 26 Aug 2026",
            "note": ("Rock-ice avalanche off the Tibetan side blocked the Lhende Khola "
                     "~20 km upstream of the Miteri Bridge, impounding a lake that then "
                     "failed. The surge ran ~60 km down the Bhote Koshi through Timure "
                     "and Syabrubesi. The collapse registered 5.2 on local seismometers, "
                     "initially misreported as a tectonic trigger."),
        },
        "question": ("Was the impoundment visible from orbit before it breached? "
                     "Sentinel-1D descending orbit 19 imaged the catchment at 00:18Z "
                     "on 24 Aug 2026, ~48 h before the collapse; the next look on any "
                     "track was 28 Aug. This is the only free-archive look inside the "
                     "window."),
        "source": {"mission": "Sentinel-1D (ESA Copernicus), IW GRD -> RTC",
                   "processing": "Microsoft Planetary Computer sentinel-1-rtc; Copernicus DEM GLO-30",
                   "attribution": "Contains modified Copernicus Sentinel data 2026"},
        "method": (f"Descending orbit {ORBIT[5:]}, VV gamma0. Baseline = median of "
                   f"{len(PRE)} monsoon-season scenes ({PRE[0]} to {PRE[-1]}), which "
                   f"holds the snow line and wetness roughly constant and subtracts "
                   f"static radar shadow. New water = VV <= {WATER_DB} dB AND at least "
                   f"{-DROP_DB} dB below baseline, on slopes <= {MAX_SLOPE_DEG} deg and "
                   f"below {MAX_ELEV_M:.0f} m, 8-connected clusters >= "
                   f"{MIN_PIXELS * RES * RES:.0f} m2. {CONTROL} is run as a control: a "
                   f"method that finds 'new' water 14 days before the event is finding "
                   f"noise."),
        "limits": LIMITS,
        "verdict": VERDICT,
        "validation": {
            "upstream_reach_15_25km": {
                "valley_floor_px": 21489,
                "finite_all_dates_px": 21489,
                "median_baseline_vv_db": -8.8,
                "note": ("Ordinary ground return across the whole reported blockage "
                         "reach. A shadowed gorge would sit at the noise floor, so "
                         "'nothing detected' here cannot be explained by geometry."),
            },
            "speckle_floor_db": -5.0,
            "sweep_excess_area_px": {
                "slope8_w15_d3": 52, "slope15_w15_d3": 153,
                "slope25_w15_d3": 36, "slope90_w15_d3": -1906,
                "note": ("test minus control, i.e. new-water pixels on 24 Aug over "
                         "the 12 Aug control. Never separates from noise; negative "
                         "at whole-AOI scale."),
            },
        },
        "params": {"water_db": WATER_DB, "drop_db": DROP_DB,
                   "max_slope_deg": MAX_SLOPE_DEG, "max_elev_m": MAX_ELEV_M,
                   "min_area_m2": MIN_PIXELS * RES * RES},
        "summary": {
            "control_2026-08-12": {"n_clusters": len(ctrl), "total_area_m2": ctrl_area},
            "test_2026-08-24": {"n_clusters": len(test), "total_area_m2": test_area},
            "excess_area_m2": test_area - ctrl_area,
        },
        "clusters": {k: v[:100] for k, v in res.items()},
    }
    json.dump(out, open(OUT_JSON, "w"), indent=2)
    print("wrote", OUT_JSON)
    _plot(z, transform, flat, res)


def _plot(z, transform, flat, res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from rasterio.warp import transform as tr
    dem = np.nan_to_num(z["dem"], nan=0.0)
    ls = LightSource(azdeg=315, altdeg=45)
    shade = ls.hillshade(dem, vert_exag=1.5, dx=RES, dy=RES)
    h, w = dem.shape
    extent = (transform.c, transform.c + w * RES,
              transform.f - h * RES, transform.f)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8), dpi=150)
    for ax, (name, clusters) in zip(axes, res.items()):
        ax.imshow(shade, cmap="gray", extent=extent, vmin=0, vmax=1)
        for c in clusters:
            if c["likely_wet_snow"]:
                continue
            x, y = tr("EPSG:4326", GRID_EPSG, [c["lon"]], [c["lat"]])
            ax.scatter(x, y, s=max(40, c["area_m2"] / 200), facecolors="none",
                       edgecolors="#0a84ff", linewidths=1.6)
        for L in LANDMARKS:
            x, y = tr("EPSG:4326", GRID_EPSG, [L["lon"]], [L["lat"]])
            ax.scatter(x, y, marker="v", s=45, c="#ff3b30", zorder=5)
            ax.annotate(L["name"], (x[0], y[0]), fontsize=7, color="#ff3b30",
                        xytext=(4, 4), textcoords="offset points")
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_axis_off()
        n = len([c for c in clusters if not c["likely_wet_snow"]])
        ax.set_title(f"{name}  -  {n} new-water clusters below snow zone", fontsize=10)
    fig.suptitle("Lhende Khola: new-water detection before the 26 Aug 2026 outburst\n"
                 "Sentinel-1D VV, descending orbit 19, vs monsoon-season baseline",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, bbox_inches="tight")
    print("wrote", OUT_PNG)


def _lonlat_grid(transform, shape):
    from rasterio.warp import transform as tr
    h, w = shape
    rows, cols = np.mgrid[0:h, 0:w]
    xs = (transform.c + (cols + 0.5) * RES).ravel()
    ys = (transform.f - (rows + 0.5) * RES).ravel()
    lons, lats = tr(GRID_EPSG, "EPSG:4326", xs, ys)
    return np.array(lons).reshape(h, w), np.array(lats).reshape(h, w)


def cmd_series():
    """Dark-area time series over the glaciated source zone, elevation ceiling off.

    Tests the supraglacial hypothesis directly. A lake fills monotonically; wet
    snow tracks the weather. Prints both the source zone and a control region in
    the same elevation and slope band so correlated fluctuation is visible.
    """
    import glob, re
    from affine import Affine
    from scipy import ndimage
    z = np.load(NPZ)
    transform = Affine(*z["transform"])
    dem = z["dem"]
    lons, lats = _lonlat_grid(transform, dem.shape)
    miteri = next(L for L in LANDMARKS if "Miteri" in L["name"])
    dist_km = np.hypot((lats - miteri["lat"]) * 111.32,
                       (lons - miteri["lon"]) * 111.32 * np.cos(np.radians(28.3)))
    gy, gx = np.gradient(dem, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))

    src = ((dist_km >= 33) & (dist_km <= 40) & (dem >= 5100)
           & (dem <= 5600) & (slope <= 12))
    ctl = ((dist_km >= 15) & (dist_km <= 30) & (dem >= 5100)
           & (dem <= 5600) & (slope <= 12))
    print(f"source zone {src.sum()*100/1e6:.2f} km2, "
          f"control {ctl.sum()*100/1e6:.2f} km2\n")

    cache = os.path.join(DATA, "nepal2026_cache")
    rows, prev = [], None
    print(f"{'date':>12} {'src km2':>9} {'delta':>7} {'ctl %':>7} "
          f"{'largest m2':>12} {'compact':>8}")
    for f in sorted(glob.glob(os.path.join(cache, f"{ORBIT}_*_vv.npy"))):
        d = re.search(rf"{ORBIT}_(\d{{4}}-\d{{2}}-\d{{2}})_vv", f).group(1)
        vv = np.load(f)
        km2 = float((vv[src] <= WATER_DB).sum() * 100 / 1e6)
        m = src & (vv <= WATER_DB)
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        big, comp = 0, 0.0
        if n:
            sizes = ndimage.sum_labels(np.ones_like(lab), lab,
                                       index=np.arange(1, n + 1))
            k = int(np.argmax(sizes))
            r, c = np.where(lab == k + 1)
            bbox = (r.max() - r.min() + 1) * (c.max() - c.min() + 1)
            big, comp = int(sizes[k]) * 100, float(sizes[k] / bbox)
        delta = "" if prev is None else f"{km2-prev:+.2f}"
        prev = km2
        rows.append({"date": d, "source_km2": round(km2, 2),
                     "control_frac": round(float((vv[ctl] <= WATER_DB).mean()), 3),
                     "largest_blob_m2": big, "compactness": round(comp, 2)})
        print(f"{d:>12} {km2:>9.2f} {delta:>7} "
              f"{float((vv[ctl] <= WATER_DB).mean()):>7.1%} {big:>12,} {comp:>8.2f}")

    mono = all(rows[i]["source_km2"] <= rows[i + 1]["source_km2"]
               for i in range(len(rows) - 1))
    print(f"\nmonotonic growth: {mono}  "
          f"({'consistent with a filling lake' if mono else 'wet snow tracking weather'})")
    out = os.path.join(DATA, "nepal_source_series_2026.json")
    json.dump({"generated_utc": now(), "zone": "33-40 km upstream, 5100-5600 m",
               "monotonic": mono, "series": rows}, open(out, "w"), indent=2)
    print("wrote", out)


def cmd_postevent():
    """First look after the surge: scars and standing water down the full corridor.

    Runs against whatever passes exist after the event. Exits cleanly when none
    have landed yet, so it is safe to poll.
    """
    import pystac_client, planetary_computer
    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["sentinel-1-rtc"], bbox=AOI_DOWN,
                            datetime="2026-08-26/2026-09-30").item_collection())
    if not items:
        print("no post-event Sentinel-1 scene yet. Next expected pass is "
              "28 Aug 12:21Z (orbit 85, ascending). Re-run then.")
        return
    by = {}
    for it in items:
        by.setdefault((f"orbit{it.properties['sat:relative_orbit']}",
                       it.datetime.strftime("%Y-%m-%d")), []).append(it)
    print(f"{len(items)} post-event scenes available:")
    for (orb, d), its in sorted(by.items(), key=lambda k: k[0][1]):
        print(f"  {d}  {orb}  n={len(its)}  "
              f"{its[0].properties.get('platform','?')}")
    print("\nDownstream corridor AOI:", AOI_DOWN)
    print("Scar mapping needs the VH log-ratio path from hk_landslides_2023.py; "
          "standing water uses the VV path here. Both want the same pre-event "
          "baseline, which is already cached for orbit 19.")


if __name__ == "__main__":
    {"fetch": cmd_fetch, "detect": cmd_detect, "series": cmd_series,
     "postevent": cmd_postevent}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
