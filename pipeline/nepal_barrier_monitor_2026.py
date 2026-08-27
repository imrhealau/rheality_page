"""Live monitoring of the barrier lake left behind by the 26 Aug 2026 outburst.

After the Lhende Khola blockage failed and the surge ran down the Bhote Koshi, a
second impoundment formed upstream, near the confluence of the Chhochen Khola
and the Purepu Tsangpo on the Nepal-China border. On 27 Aug China's Ministry of
Water Resources put it at about 2 million cubic metres and forecast a further
3 million entering over the following three days, with a high risk of breach.
Nepal moved people out of the valley below.

That number currently rests on a single source. Independent measurement of it is
the whole job, and it is measurable: a lake surface is flat, so the shoreline is
an equipotential, and intersecting a radar-derived outline with the DEM gives
stage directly. Integrating the DEM below that level gives volume. Two passes
give the filling rate, which means the lake is its own flow gauge.

Sentinel-1 sees this reach on three tracks. The passes that matter:

  28 Aug 12:21Z  orbit 85  ascending   first post-event look
  31 Aug 00:10Z  orbit 121 descending  after the forecast inflow
   5 Sep 00:18Z  orbit 19  descending

Baseline is same-track by construction. Comparing an ascending scene against a
descending baseline in this terrain compares two different shadow maps, not two
different days.

  .venv/bin/python -u nepal_barrier_monitor_2026.py baseline   # pre-fetch, do this ahead of the pass
  .venv/bin/python -u nepal_barrier_monitor_2026.py check      # has the next scene landed?
  .venv/bin/python -u nepal_barrier_monitor_2026.py measure    # detect, size, and volume the lake

Data: Copernicus Sentinel-1 (ESA) RTC by Microsoft Planetary Computer;
Copernicus DEM GLO-30. No login needed.
"""
import os, sys, json
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "nepal_monitor_cache")
OUT_JSON = os.path.join(DATA, "nepal_barrier_monitor_2026.json")

# Confluence area on the border, generous enough to hold the impoundment
# wherever along the reach it sits.
AOI = [85.30, 28.25, 85.85, 28.75]  # W S E N
GRID_EPSG = "EPSG:32645"
RES = 10.0

EVENT = "2026-08-26"

# Per-track baselines, all pre-event. The track of the scene being measured
# selects its own baseline.
TRACKS = {
    "orbit85":  {"state": "ascending",
                 "pre": ["2026-07-11", "2026-07-23", "2026-08-04", "2026-08-16"]},
    "orbit121": {"state": "descending",
                 "pre": ["2026-07-02", "2026-07-14", "2026-07-26", "2026-08-07"]},
    "orbit19":  {"state": "descending",
                 "pre": ["2026-07-07", "2026-07-19", "2026-07-31", "2026-08-12"]},
}

WATER_DB = -15.0
DROP_DB = -3.0
MAX_SLOPE_DEG = 12.0   # looser than the source-zone study: an impoundment in a
                       # confined reach sits on ground the DEM reads as steep
MIN_PIXELS = 30        # 3000 m2; below this a "lake" is speckle
STAGE_PCT = 90         # shoreline elevation percentile taken as water surface


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _client():
    import pystac_client, planetary_computer
    return pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)


def _grid():
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    l, b, r, t = transform_bounds("EPSG:4326", GRID_EPSG, *AOI)
    l, t = np.floor(l / RES) * RES, np.ceil(t / RES) * RES
    w = int(np.ceil((r - l) / RES)); h = int(np.ceil((t - b) / RES))
    return from_origin(l, t, RES, RES), w, h


def _read_into(href, transform, w, h):
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=GRID_EPSG, transform=transform, width=w,
                       height=h, resampling=Resampling.bilinear,
                       src_nodata=src.nodata if src.nodata is not None else 0,
                       nodata=np.nan) as vrt:
            return vrt.read(1).astype(np.float32)


def _mosaic(items, band, transform, w, h):
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


def _index(cat, start, end):
    by = {}
    for it in cat.search(collections=["sentinel-1-rtc"], bbox=AOI,
                         datetime=f"{start}/{end}").item_collection():
        key = (f"orbit{it.properties['sat:relative_orbit']}",
               it.datetime.strftime("%Y-%m-%d"))
        by.setdefault(key, []).append(it)
    return by


def _date_db(by, track, d, transform, w, h, pol="vv"):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, f"{track}_{d}_{pol}.npy")
    if os.path.exists(f):
        return np.load(f)
    items = by.get((track, d))
    if not items:
        raise SystemExit(f"no {track} scene on {d}")
    arr = _db(_mosaic(items, pol, transform, w, h))
    np.save(f, arr)
    print(f"  {track} {d}: {np.isfinite(arr).mean():.0%} valid, "
          f"median {np.nanmedian(arr):.1f} dB", flush=True)
    return arr


def _dem(cat, transform, w, h):
    f = os.path.join(CACHE, "dem.npy")
    if os.path.exists(f):
        return np.load(f)
    items = list(cat.search(collections=["cop-dem-glo-30"],
                            bbox=AOI).item_collection())
    dem = _mosaic(items, "data", transform, w, h)
    np.save(f, dem)
    print(f"  dem: {np.nanmin(dem):.0f}-{np.nanmax(dem):.0f} m", flush=True)
    return dem


def cmd_baseline():
    """Pre-fetch every pre-event baseline plus the DEM, so the post-event run
    is a single scene download."""
    cat = _client()
    transform, w, h = _grid()
    print(f"grid {w}x{h} @ {RES} m ({GRID_EPSG})", flush=True)
    by = _index(cat, "2026-07-01", EVENT)
    for track, spec in TRACKS.items():
        print(f"{track} ({spec['state']}):", flush=True)
        pre = [_date_db(by, track, d, transform, w, h) for d in spec["pre"]]
        med = np.nanmedian(np.stack(pre), axis=0)
        np.save(os.path.join(CACHE, f"{track}_baseline.npy"), med)
        del pre, med
    _dem(cat, transform, w, h)
    print("baseline ready")


def cmd_check():
    """Has a post-event scene landed?"""
    cat = _client()
    by = _index(cat, EVENT, "2026-09-30")
    if not by:
        print("no post-event scene yet.")
        print("next expected: 28 Aug 12:21Z orbit 85 ascending, then "
              "31 Aug 00:10Z orbit 121, then 5 Sep 00:18Z orbit 19.")
        return 1
    for (track, d), its in sorted(by.items(), key=lambda k: k[0][1]):
        print(f"AVAILABLE  {d}  {track}  n={len(its)}  "
              f"{its[0].properties.get('platform','?')}")
    return 0


def _lonlat(transform, rows, cols):
    from rasterio.transform import xy
    from rasterio.warp import transform as tr
    xs, ys = xy(transform, rows, cols)
    lons, lats = tr(GRID_EPSG, "EPSG:4326", np.atleast_1d(xs), np.atleast_1d(ys))
    return np.array(lons), np.array(lats)


def cmd_measure():
    from affine import Affine
    from scipy import ndimage
    from rasterio.transform import from_origin
    cat = _client()
    transform, w, h = _grid()
    dem = _dem(cat, transform, w, h)
    gy, gx = np.gradient(dem, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))

    by = _index(cat, EVENT, "2026-09-30")
    if not by:
        print("no post-event scene yet, nothing to measure.")
        return
    results = []
    for (track, d), _ in sorted(by.items(), key=lambda k: k[0][1]):
        bf = os.path.join(CACHE, f"{track}_baseline.npy")
        if not os.path.exists(bf):
            print(f"skip {track} {d}: no baseline, run `baseline` first")
            continue
        pre = np.load(bf)
        vv = _date_db(by, track, d, transform, w, h)
        mask = (np.isfinite(vv) & np.isfinite(pre) & (slope <= MAX_SLOPE_DEG)
                & (vv <= WATER_DB) & ((vv - pre) <= DROP_DB))
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        lakes = []
        if n:
            sizes = ndimage.sum_labels(np.ones_like(lab), lab,
                                       index=np.arange(1, n + 1))
            for k in np.where(sizes >= MIN_PIXELS)[0] + 1:
                blob = lab == k
                rr, cc = np.where(blob)
                elev = dem[blob]
                if not np.isfinite(elev).any():
                    continue
                stage = float(np.nanpercentile(elev, STAGE_PCT))
                depth = np.clip(stage - elev, 0, None)
                vol = float(np.nansum(depth) * RES * RES)
                lon, lat = _lonlat(transform, rr.mean(), cc.mean())
                lakes.append({
                    "lat": round(float(lat[0]), 5),
                    "lon": round(float(lon[0]), 5),
                    "area_m2": int(blob.sum()) * int(RES * RES),
                    "stage_m": round(stage, 1),
                    "elev_min_m": round(float(np.nanmin(elev)), 1),
                    "max_depth_m": round(float(np.nanmax(depth)), 1),
                    "volume_m3": int(vol),
                    "mean_vv_db": round(float(np.nanmean(vv[blob])), 2),
                    "mean_drop_db": round(float(np.nanmean((vv - pre)[blob])), 2),
                })
        lakes.sort(key=lambda L: -L["volume_m3"])
        total = sum(L["volume_m3"] for L in lakes)
        print(f"\n{d} {track}: {len(lakes)} new water bodies, "
              f"total {total/1e6:.2f} million m3")
        for L in lakes[:8]:
            print(f"   {L['area_m2']:>9,} m2  {L['volume_m3']/1e6:>6.2f} Mm3  "
                  f"stage {L['stage_m']:>7.1f} m  depth<={L['max_depth_m']:>5.1f} m  "
                  f"{L['lat']:.4f},{L['lon']:.4f}")
        results.append({"date": d, "track": track,
                        "n_bodies": len(lakes),
                        "total_volume_m3": total, "lakes": lakes[:40]})

    out = {
        "generated_utc": now(),
        "subject": ("Barrier lake upstream of Rasuwagadhi following the 26 Aug 2026 "
                    "Lhende Khola outburst, near the Chhochen Khola / Purepu Tsangpo "
                    "confluence on the Nepal-China border."),
        "reference_claim": {
            "source": "China Ministry of Water Resources via CCTV, 27 Aug 2026",
            "volume_m3": 2_000_000,
            "forecast_inflow_m3_3days": 3_000_000,
        },
        "method": (f"Same-track VV log-ratio against a 4-scene pre-event median. New "
                   f"water = VV <= {WATER_DB} dB and at least {-DROP_DB} dB below "
                   f"baseline, slope <= {MAX_SLOPE_DEG} deg, clusters >= "
                   f"{MIN_PIXELS*RES*RES:.0f} m2. Stage = {STAGE_PCT}th percentile of "
                   f"Copernicus DEM elevation over the wetted footprint, on the "
                   f"reasoning that a lake surface is flat so its shoreline is an "
                   f"equipotential. Volume = DEM integrated below that stage."),
        "limits": ("Copernicus DEM GLO-30 is 2011-2015 vintage, so the impoundment "
                   "basin is pre-event topography, which is what the volume "
                   "calculation wants, but the debris dam itself is not in the DEM and "
                   "its crest height is therefore unknown. Freeboard and time to "
                   "overtop cannot be derived from this alone. Volume is sensitive to "
                   "the stage percentile; treat it as an order of magnitude against "
                   "the reported figure, not a survey. Wind roughening can hide a "
                   "small lake, and wet snow above the snow line mimics one."),
        "passes": results,
    }
    json.dump(out, open(OUT_JSON, "w"), indent=2)
    print("\nwrote", OUT_JSON)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"baseline": cmd_baseline, "check": cmd_check,
          "measure": cmd_measure}.get(cmd)
    if not fn:
        sys.exit(__doc__)
    sys.exit(fn() or 0)
