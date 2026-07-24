#!/usr/bin/env python3
"""Three Gorges Dam anomaly monitor, built on real Sentinel-2 data.

Pulls Sentinel-2 L2A scenes over the near-dam reach of the Three Gorges
reservoir from the open AWS COG archive (Element84 Earth Search, no
credentials), measures the reservoir water surface on each cloud-free pass
with the NDWI water index, then flags statistical anomalies against a fitted
seasonal baseline.

What this detects: reservoir water-extent and surface anomalies (unexpected
drawdown or rise, new inundation). What it does NOT detect: millimetre
structural deformation of the dam wall itself. That is the Sentinel-1 InSAR
extension, which needs SLC interferometric processing.

Output: data/three_gorges.json (time series + anomaly flags + provenance),
consumed by the Live Monitor tab on the site.

Run:  .venv/bin/python -u three_gorges.py
"""
import os, json, math, sys
from datetime import datetime, timezone

# --- GDAL tuning for efficient windowed reads over HTTP COGs ---
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from rasterio.enums import Resampling
from pystac_client import Client

# --- Area of interest: the near-dam reach of the reservoir ---
# Three Gorges Dam wall sits at ~30.826 N, 111.003 E (Sandouping, Hubei).
# This bbox covers the dam and a stretch of reservoir just upstream, where
# the water surface widens and narrows with the operating level. Pinned to a
# single Sentinel-2 tile (49RDQ) that fully images the AOI, so no mosaicking.
AOI = {
    "name": "Three Gorges Dam and reservoir reach",
    "dam_lat": 30.826, "dam_lon": 111.003,
    "bbox": [110.88, 30.77, 111.06, 30.89],  # W, S, E, N
}
TILE = "MGRS-49RDQ"
STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
DATE_RANGE = "2023-01-01/2025-07-01"
MAX_CLOUD = 60            # scene-level cloud cap; SCL does the per-pixel work
DECIM = 6                 # read 10 m bands decimated x6 -> ~60 m grid (fast)
NATIVE_RES = 10.0
PIXEL_RES = NATIVE_RES * DECIM
PIX_AREA_KM2 = (PIXEL_RES * PIXEL_RES) / 1e6
MIN_VALID_FRAC = 0.80     # discard passes with too little cloud-free coverage
                          # (partial cloud undercounts water and fakes anomalies)
NDWI_WATER = 0.0          # McFeeters NDWI > 0 marks open water

OUT = os.path.join(os.path.dirname(__file__), "data", "three_gorges.json")

# Sentinel-2 Scene Classification codes treated as valid ground/water.
# Excluded: 0 nodata, 1 saturated, 2 dark, 3 cloud shadow, 8/9 cloud, 10 cirrus.
SCL_VALID = {4, 5, 6, 7, 11}   # veg, bare, water, unclassified, snow
SCL_WATER = 6


def read_window(ds, out_wh, resampling):
    """Windowed read of a COG over the AOI, resampled to the common grid."""
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", ds.crs, *AOI["bbox"], densify_pts=21)
    win = from_bounds(left, bottom, right, top, ds.transform)
    return ds.read(1, window=win, out_shape=out_wh,
                   resampling=resampling).astype(np.float32)


def measure_scene(item):
    """Return (water_km2, valid_frac) for one Sentinel-2 pass, or None."""
    a = item.assets
    gk = "green" if "green" in a else next((k for k in a if "b03" in k.lower()), None)
    nk = "nir" if "nir" in a else next((k for k in a if k.lower() in ("b08", "nir08")), None)
    sk = "scl" if "scl" in a else next((k for k in a if "scl" in k.lower()), None)
    if not (gk and nk and sk):
        return None
    with rasterio.open(a[gk].href) as g:
        left, bottom, right, top = transform_bounds("EPSG:4326", g.crs, *AOI["bbox"])
        win = from_bounds(left, bottom, right, top, g.transform)
        h, w = max(1, int(win.height // DECIM)), max(1, int(win.width // DECIM))
        green = read_window(g, (h, w), Resampling.bilinear)
    with rasterio.open(a[nk].href) as n:
        nir = read_window(n, (h, w), Resampling.bilinear)
    with rasterio.open(a[sk].href) as s:
        scl = read_window(s, (h, w), Resampling.nearest).astype(np.int16)

    valid = np.isin(scl, list(SCL_VALID))
    valid_frac = float(valid.mean())
    if valid_frac < MIN_VALID_FRAC:
        return None

    denom = green + nir
    ndwi = np.where(denom > 0, (green - nir) / np.maximum(denom, 1e-6), -1.0)
    water = valid & ((ndwi > NDWI_WATER) | (scl == SCL_WATER))
    return float(water.sum()) * PIX_AREA_KM2, valid_frac


def harmonic_baseline(doy, y):
    """Fit annual + semi-annual seasonal cycle; return expected values."""
    t = np.asarray(doy, float) / 365.25 * 2 * math.pi
    X = np.column_stack([
        np.ones_like(t), np.sin(t), np.cos(t), np.sin(2 * t), np.cos(2 * t)])
    coef, *_ = np.linalg.lstsq(X, np.asarray(y, float), rcond=None)
    return X @ coef


def main():
    print(f"Searching Sentinel-2 L2A over {AOI['name']} (tile {TILE}, {DATE_RANGE})...")
    client = Client.open(STAC_URL)
    items = list(client.search(
        collections=[COLLECTION], bbox=AOI["bbox"], datetime=DATE_RANGE,
        query={"eo:cloud_cover": {"lt": MAX_CLOUD}, "grid:code": {"eq": TILE}},
        max_items=600).items())
    print(f"  {len(items)} candidate scenes on tile {TILE}")

    # Keep the least-cloudy scene per calendar month to bound runtime.
    best = {}
    for it in items:
        key = it.datetime.strftime("%Y-%m")
        cc = it.properties.get("eo:cloud_cover", 100)
        if key not in best or cc < best[key][0]:
            best[key] = (cc, it)
    chosen = sorted((v[1] for v in best.values()), key=lambda it: it.datetime)
    print(f"  {len(chosen)} scenes selected (clearest per month)")

    series = []
    for i, it in enumerate(chosen, 1):
        d = it.datetime.strftime("%Y-%m-%d")
        try:
            res = measure_scene(it)
        except Exception as e:
            print(f"  [{i}/{len(chosen)}] {d}  skipped ({type(e).__name__}: {e})")
            continue
        if res is None:
            print(f"  [{i}/{len(chosen)}] {d}  skipped (too cloudy)")
            continue
        water_km2, vf = res
        series.append({"date": d, "doy": it.datetime.timetuple().tm_yday,
                       "water_km2": round(water_km2, 3),
                       "valid_frac": round(vf, 3),
                       "cloud": round(it.properties.get("eo:cloud_cover", 0), 1)})
        print(f"  [{i}/{len(chosen)}] {d}  water={water_km2:6.2f} km2  valid={vf:.0%}", flush=True)

    if len(series) < 8:
        print("Not enough clear scenes to fit a baseline.", file=sys.stderr)
        sys.exit(1)

    doy = [s["doy"] for s in series]
    y = np.array([s["water_km2"] for s in series])
    expected = harmonic_baseline(doy, y)
    resid = y - expected
    med = float(np.median(resid))
    mad = float(np.median(np.abs(resid - med))) or 1e-6
    z = 0.6745 * (resid - med) / mad  # robust z-score

    for s, e, r, zz in zip(series, expected, resid, z):
        s["expected_km2"] = round(float(e), 3)
        s["residual_km2"] = round(float(r), 3)
        s["z"] = round(float(zz), 2)
        s["anomaly"] = bool(abs(zz) >= 3.0)

    anomalies = [s for s in series if s["anomaly"]]
    out = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aoi": AOI, "tile": TILE,
        "source": {
            "mission": "Sentinel-2 L2A (ESA Copernicus)",
            "archive": "Element84 Earth Search STAC on AWS Open Data (no credentials)",
            "stac": STAC_URL, "collection": COLLECTION,
            "date_range": DATE_RANGE, "resolution_m": PIXEL_RES,
        },
        "method": {
            "water_index": "NDWI = (B03 - B08) / (B03 + B08), McFeeters 1996; water where NDWI > 0",
            "cloud_mask": "Sentinel-2 SCL; scenes below 80% cloud-free AOI coverage discarded",
            "baseline": "annual + semi-annual harmonic regression of water area vs day-of-year",
            "anomaly": "robust z-score (MAD) of the residual; flagged at |z| >= 3",
            "limitation": "optical water-extent monitor, not millimetre structural deformation (Sentinel-1 InSAR extension)",
        },
        "summary": {
            "scenes": len(series),
            "water_km2_min": round(float(y.min()), 2),
            "water_km2_max": round(float(y.max()), 2),
            "water_km2_mean": round(float(y.mean()), 2),
            "anomalies": len(anomalies),
        },
        "series": series,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {OUT}")
    print(f"  {len(series)} clear passes, {len(anomalies)} anomaly(ies); "
          f"water {out['summary']['water_km2_min']}-{out['summary']['water_km2_max']} km2")


if __name__ == "__main__":
    main()
