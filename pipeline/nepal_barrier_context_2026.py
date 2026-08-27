"""Inflow and DEM uncertainty for the Lhende barrier lake measurement.

Two things the radar measurement on its own cannot supply.

First, inflow. China's Ministry of Water Resources forecast 3 million cubic
metres entering the lake over three days from 27 Aug. That is the least verified
number in the situation and it drives everything. Rainfall over the contributing
catchment gives an independent handle on it, and rainfall is one of the few
observables in a Himalayan monsoon that does not care about cloud.

Second, error bars. The volume figure from `nepal_barrier_monitor_2026.py`
integrates one DEM below a water surface, and reports no uncertainty. Three free
global DEMs cover this catchment from three different epochs. The spread between
them, run through the same impoundment geometry, is an honest error bar rather
than the hand-wave of "order of magnitude".

  .venv/bin/python -u nepal_barrier_context_2026.py inflow
  .venv/bin/python -u nepal_barrier_context_2026.py dem

Precipitation: Open-Meteo (no key, non-commercial terms).
DEMs: Copernicus GLO-30, NASADEM, ALOS World 3D-30m via Planetary Computer.
"""
import os, sys, json
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
OUT_INFLOW = os.path.join(DATA, "nepal_inflow_2026.json")
OUT_DEM = os.path.join(DATA, "nepal_dem_spread_2026.json")

# Contributing catchment above the blockage, sampled on a grid.
CATCH = {"lat": (28.38, 28.72), "lon": (85.42, 85.80), "n": 4}

# Reported blockage vicinity: search box for the valley thalweg seed.
SEED_BOX = [85.45, 28.40, 85.62, 28.52]  # W S E N
DEM_AOI = [85.35, 28.30, 85.80, 28.70]
DEM_RES = 30.0
GRID_EPSG = "EPSG:32645"

# Reference figures to test against.
CN_VOLUME_M3 = 2_000_000
CN_INFLOW_M3_3D = 3_000_000

# Steep glaciated headwater in the middle of a monsoon: thin soils, much bare
# rock and ice, saturated ground. Runoff coefficients run high.
RUNOFF_COEFFS = (0.5, 0.7, 0.9)
CATCHMENT_AREAS_KM2 = (100, 200, 300, 500)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_inflow():
    import requests
    lats = np.linspace(*CATCH["lat"], CATCH["n"])
    lons = np.linspace(*CATCH["lon"], CATCH["n"])
    pts = [(la, lo) for la in lats for lo in lons]
    print(f"sampling {len(pts)} points over the contributing catchment", flush=True)

    series = {}
    elevs = []
    for la, lo in pts:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": round(la, 4), "longitude": round(lo, 4),
            "hourly": "precipitation", "past_days": 10, "forecast_days": 5,
            "timezone": "UTC"}, timeout=60)
        r.raise_for_status()
        d = r.json()
        elevs.append(d.get("elevation"))
        for ts, v in zip(d["hourly"]["time"], d["hourly"]["precipitation"]):
            series.setdefault(ts[:10], []).append(v or 0.0)

    n = len(pts)
    daily = {day: sum(v) / n for day, v in sorted(series.items())}
    print(f"catchment sample elevation {min(elevs):.0f} to {max(elevs):.0f} m\n")
    print(f"{'date':>12} {'mm':>7}   catchment-mean rainfall")
    for day, mm in daily.items():
        bar = "#" * int(round(mm))
        print(f"{day:>12} {mm:7.1f}   {bar}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fwd = {d: v for d, v in daily.items() if d >= today}
    fwd3 = sum(list(fwd.values())[:3])
    print(f"\nnext three days, catchment mean: {fwd3:.1f} mm")
    print(f"China forecast inflow: {CN_INFLOW_M3_3D/1e6:.1f} Mm3 over three days "
          f"= {CN_INFLOW_M3_3D/3/1e6:.2f} Mm3/day\n")

    # Inflow = area x depth x runoff coefficient. Invert it too: what catchment
    # area does the reported inflow imply, given the rainfall actually forecast?
    print(f"{'area km2':>9} " + " ".join(f"{'C='+str(c):>10}" for c in RUNOFF_COEFFS))
    rows = []
    for a in CATCHMENT_AREAS_KM2:
        vals = [a * 1e6 * (fwd3 / 1000.0) * c for c in RUNOFF_COEFFS]
        rows.append({"area_km2": a,
                     "inflow_m3": {str(c): int(v) for c, v in zip(RUNOFF_COEFFS, vals)}})
        print(f"{a:>9} " + " ".join(f"{v/1e6:>9.2f}M" for v in vals))

    implied = {}
    if fwd3 > 0:
        for c in RUNOFF_COEFFS:
            implied[str(c)] = round(CN_INFLOW_M3_3D / ((fwd3 / 1000.0) * c) / 1e6, 1)
        print(f"\nFor the 3 Mm3 forecast to hold on rainfall alone, the catchment "
              f"would need to be:")
        for c, km2 in implied.items():
            print(f"   {km2:>6.1f} km2 at runoff coefficient {c}")
        print("Snow and ice melt contribute on top of rainfall, so a smaller "
              "catchment than these can still deliver it.")

    out = {"generated_utc": now(),
           "source": "Open-Meteo hourly precipitation, no key, non-commercial terms",
           "catchment_sample": {"box": CATCH, "n_points": len(pts),
                                "elev_range_m": [min(elevs), max(elevs)]},
           "daily_mean_mm": {d: round(v, 2) for d, v in daily.items()},
           "next_3_days_mm": round(fwd3, 1),
           "reference": {"cn_inflow_m3_3d": CN_INFLOW_M3_3D,
                         "cn_volume_m3": CN_VOLUME_M3},
           "inflow_scenarios": rows,
           "implied_catchment_km2_for_cn_forecast": implied,
           "limits": ("Open-Meteo is a reanalysis and forecast blend, not a gauge. "
                      "High Himalayan precipitation is poorly constrained by any "
                      "model and orographic gradients are severe over a few km. "
                      "Melt is excluded and is a real term at these elevations in "
                      "late August. Treat this as an order of magnitude cross-check "
                      "on the reported inflow, not a measurement of it.")}
    json.dump(out, open(OUT_INFLOW, "w"), indent=2)
    print("\nwrote", OUT_INFLOW)


def _grid(aoi, res):
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    l, b, r, t = transform_bounds("EPSG:4326", GRID_EPSG, *aoi)
    l, t = np.floor(l / res) * res, np.ceil(t / res) * res
    w = int(np.ceil((r - l) / res)); h = int(np.ceil((t - b) / res))
    return from_origin(l, t, res, res), w, h


def _read(href, transform, w, h, res):
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=GRID_EPSG, transform=transform, width=w, height=h,
                       resampling=Resampling.bilinear,
                       src_nodata=src.nodata if src.nodata is not None else -32768,
                       nodata=np.nan) as vrt:
            return vrt.read(1).astype(np.float32)


def cmd_dem():
    import pystac_client, planetary_computer
    from scipy import ndimage
    from rasterio.transform import xy
    from rasterio.warp import transform as tr
    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
    transform, w, h = _grid(DEM_AOI, DEM_RES)
    print(f"grid {w}x{h} @ {DEM_RES} m", flush=True)

    COLLS = {"cop-dem-glo-30": ("data", "Copernicus GLO-30, TanDEM-X 2011-2015"),
             "nasadem":        ("elevation", "NASADEM, SRTM 2000"),
             "alos-dem":       ("data", "ALOS World 3D-30m, 2006-2011")}
    dems = {}
    for cid, (band, label) in COLLS.items():
        items = list(cat.search(collections=[cid], bbox=DEM_AOI).item_collection())
        if not items:
            print(f"  {cid}: no tiles"); continue
        arr = np.full((h, w), np.nan, dtype=np.float32)
        for it in items:
            a = _read(it.assets[band].href, transform, w, h, DEM_RES)
            take = np.isnan(arr) & np.isfinite(a)
            arr[take] = a[take]
        dems[cid] = arr
        print(f"  {cid:16s} {np.nanmin(arr):.0f}-{np.nanmax(arr):.0f} m, "
              f"{np.isfinite(arr).mean():.0%} valid   [{label}]", flush=True)

    keys = list(dems)
    # Whole-AOI scatter is dominated by steep slopes, where a metre of horizontal
    # misregistration becomes tens of metres of vertical difference. Volume is
    # integrated on the valley floor, so the floor is the population that matters.
    ref0 = dems["cop-dem-glo-30"]
    gy, gx = np.gradient(ref0, DEM_RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    flat = slope <= 10.0
    print(f"\nvalley floor (slope <= 10 deg): {flat.mean():.1%} of AOI")

    print("\npairwise elevation difference (m):")
    pair_stats = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            d = dems[keys[i]] - dems[keys[j]]
            out_rec = {}
            for tag, m in (("all", np.isfinite(d)), ("flat", np.isfinite(d) & flat)):
                out_rec[tag] = {
                    "median": round(float(np.nanmedian(d[m])), 2),
                    "std": round(float(np.nanstd(d[m])), 2),
                    "p5": round(float(np.nanpercentile(d[m], 5)), 2),
                    "p95": round(float(np.nanpercentile(d[m], 95)), 2)}
            pair_stats[f"{keys[i]} - {keys[j]}"] = out_rec
            a, fl = out_rec["all"], out_rec["flat"]
            print(f"  {keys[i][:14]:14s} - {keys[j][:14]:14s}  "
                  f"all: median {a['median']:+6.2f} std {a['std']:5.1f}   |   "
                  f"valley floor: median {fl['median']:+6.2f} std {fl['std']:5.1f}")

    # Same impoundment geometry through each DEM. Seed on the valley thalweg
    # near the reported blockage, fill to a stage, integrate below it.
    ref = dems["cop-dem-glo-30"]
    l, b, r, t = SEED_BOX[0], SEED_BOX[1], SEED_BOX[2], SEED_BOX[3]
    ys, xs = np.mgrid[0:h, 0:w]
    px = transform.c + (xs + 0.5) * DEM_RES
    py = transform.f - (ys + 0.5) * DEM_RES
    lon, lat = tr(GRID_EPSG, "EPSG:4326", px.ravel(), py.ravel())
    lon = np.array(lon).reshape(h, w); lat = np.array(lat).reshape(h, w)
    inbox = (lon >= l) & (lon <= r) & (lat >= b) & (lat <= t) & np.isfinite(ref)
    if not inbox.any():
        print("seed box empty"); return
    flat = np.where(inbox, ref, np.inf)
    sr, sc = np.unravel_index(np.argmin(flat), flat.shape)
    floor = float(ref[sr, sc])
    print(f"\nthalweg seed {lat[sr,sc]:.4f},{lon[sr,sc]:.4f} at {floor:.0f} m")

    # A "fill to stage" that only tests elevation leaks down the whole valley,
    # because nothing stops it at the dam. The dam is the one piece of geometry
    # we do not have. So instead of modelling hydrology, hold the footprint
    # fixed: take the impoundment shape from the reference DEM inside a radius
    # of the seed, then integrate depth under that SAME footprint for each DEM.
    # The spread is then a pure DEM effect, which is the error bar we want.
    RADIUS_M = 4000.0
    dist = np.hypot(px - px[sr, sc], py - py[sr, sc])
    near = dist <= RADIUS_M

    print(f"\nfixed footprint within {RADIUS_M/1000:.0f} km of the seed, shape taken "
          f"from Copernicus, depth integrated under each DEM")
    print(f"\n{'stage':>7} {'area':>9} " + " ".join(f"{k.split('-')[0][:8]:>11}" for k in keys)
          + f" {'spread':>8}")
    vols = []
    for rise in (10, 20, 30, 40, 60):
        stage = floor + rise
        below = near & np.isfinite(ref) & (ref < stage)
        lab, n = ndimage.label(below, structure=np.ones((3, 3)))
        if n == 0 or lab[sr, sc] == 0:
            continue
        foot = lab == lab[sr, sc]
        area = int(foot.sum()) * DEM_RES * DEM_RES
        row = {"rise_m": rise, "stage_m": round(stage, 1),
               "footprint_m2": int(area), "volume_m3": {}}
        vs = []
        for k in keys:
            d = dems[k]
            vol = float(np.nansum(np.clip(stage - d[foot], 0, None)) * DEM_RES * DEM_RES)
            row["volume_m3"][k] = int(vol)
            vs.append(vol)
        vs = np.array(vs, dtype=float)
        spread = (np.nanmax(vs) - np.nanmin(vs)) / np.nanmean(vs)
        row["spread_frac"] = round(float(spread), 3)
        vols.append(row)
        print(f"{'+'+str(rise)+' m':>7} {area/1e6:>7.2f}km2 "
              + " ".join(f"{(v/1e6):>10.2f}M" for v in vs)
              + f" {spread:>7.0%}")

    out = {"generated_utc": now(),
           "aoi": DEM_AOI, "res_m": DEM_RES,
           "dems": {k: COLLS[k][1] for k in keys},
           "pairwise_difference_m": pair_stats,
           "seed": {"lat": round(float(lat[sr, sc]), 5),
                    "lon": round(float(lon[sr, sc]), 5),
                    "valley_floor_m": round(floor, 1)},
           "impoundment_volume_by_dem": vols,
           "note": ("Same fill geometry through three DEMs of different epochs. "
                    "The spread is a floor on volume uncertainty, not a full error "
                    "budget: it excludes error in the radar-derived water outline "
                    "and in the stage estimate, and the debris dam itself is in "
                    "none of these DEMs.")}
    json.dump(out, open(OUT_DEM, "w"), indent=2)
    print("\nwrote", OUT_DEM)


if __name__ == "__main__":
    {"inflow": cmd_inflow, "dem": cmd_dem}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
