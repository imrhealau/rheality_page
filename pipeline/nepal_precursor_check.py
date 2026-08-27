"""Was there a slow precursor in the source zone this year?

ICIMOD attributed the July 2025 Gyirong flood, same corridor, to a supraglacial
lake on the Purepu Glacier that grew from about 0.08 to 0.69 km2 between 9 May
and 6 July 2025. That is a 7.6-fold expansion over two months, and it is the
kind of thing free optical data tracks easily. If 2026 had the same signature,
this event was predictable months out and nobody was looking.

So: Sentinel-2 water area over the source zone across the whole 2026 melt
season, using the spectral test that survived scrutiny in the main study.
Liquid water is dark in both near infrared and shortwave, below about 0.10 in
each. Snow is bright in the near infrared. Cloud shadow is spectrally flat and
sits near 0.12 in both, which is why the scene classification band alone is not
trustworthy here.

  .venv/bin/python -u nepal_precursor_check.py
"""
import os, json
import numpy as np
import pystac_client, planetary_computer, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from scipy import ndimage

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "nepal_precursor_2026.json")

# The glaciated source zone, same box the radar series interrogates.
ZONE = [85.55, 28.48, 85.68, 28.58]
RES, EPSG = 20.0, "EPSG:32645"
NIR_MAX, SWIR_MAX = 0.10, 0.10
MIN_PIXELS = 12          # 4800 m2 at 20 m
MIN_CLEAR = 0.35         # skip scenes too clouded over the zone to mean anything

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace)

l, b, r, t = transform_bounds("EPSG:4326", EPSG, *ZONE)
l, t = np.floor(l / RES) * RES, np.ceil(t / RES) * RES
W = int(np.ceil((r - l) / RES)); H = int(np.ceil((t - b) / RES))
TF = from_origin(l, t, RES, RES)
ZONE_KM2 = W * H * RES * RES / 1e6
print(f"source zone {W}x{H} @ {RES} m = {ZONE_KM2:.1f} km2\n")


def read(href, resamp=Resampling.bilinear, dtype=np.float32):
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=EPSG, transform=TF, width=W, height=H,
                       resampling=resamp, src_nodata=0, nodata=0) as vrt:
            return vrt.read(1).astype(dtype)


items = list(cat.search(collections=["sentinel-2-l2a"], bbox=ZONE,
                        datetime="2026-04-01/2026-09-06").item_collection())
items.sort(key=lambda i: i.datetime)
print(f"{len(items)} Sentinel-2 scenes over the zone, Apr to Sep\n")
print(f"{'date':>12} {'clear':>7} {'water km2':>10} {'largest m2':>12}  note")

rows = []
for it in items:
    d = it.datetime.strftime("%Y-%m-%d")
    try:
        scl = read(it.assets["SCL"].href, Resampling.nearest, np.uint8)
        valid = scl != 0
        if valid.sum() == 0:
            continue
        clear = 1.0 - np.isin(scl, [3, 8, 9, 10])[valid].mean()
        if clear < MIN_CLEAR:
            print(f"{d:>12} {clear:>6.1%} {'-':>10} {'-':>12}  too clouded")
            continue
        nir = read(it.assets["B08"].href) / 10000.0
        swir = read(it.assets["B11"].href) / 10000.0
        water = valid & (nir > 0) & (nir < NIR_MAX) & (swir < SWIR_MAX)
        lab, n = ndimage.label(water, structure=np.ones((3, 3)))
        big = 0
        if n:
            sizes = ndimage.sum_labels(np.ones_like(lab), lab, index=np.arange(1, n + 1))
            keep = sizes[sizes >= MIN_PIXELS]
            big = int(keep.max()) * int(RES * RES) if keep.size else 0
            water &= np.isin(lab, np.where(sizes >= MIN_PIXELS)[0] + 1)
        km2 = float(water.sum()) * RES * RES / 1e6
        rows.append({"date": d, "clear": round(float(clear), 3),
                     "water_km2": round(km2, 4), "largest_m2": big})
        print(f"{d:>12} {clear:>6.1%} {km2:>10.4f} {big:>12,}")
    except Exception as e:
        print(f"{d:>12}  failed: {str(e)[:50]}")

if rows:
    areas = [r["water_km2"] for r in rows]
    print(f"\nusable scenes: {len(rows)}")
    print(f"water area range: {min(areas):.4f} to {max(areas):.4f} km2")
    print(f"2025 Purepu comparison: 0.08 -> 0.69 km2 over two months, a 7.6x growth")
    peak = max(areas)
    if peak < 0.05:
        verdict = ("No supraglacial lake of consequence at any point in the 2026 melt "
                   "season. The 2025 signature is absent, so the mechanism was different "
                   "and there was no slow precursor to catch.")
    else:
        verdict = ("A water body of some size was present. Growth pattern needs "
                   "inspecting before calling it a precursor.")
    print(f"\n{verdict}")
    json.dump({"zone": ZONE, "zone_km2": round(ZONE_KM2, 2),
               "method": (f"Sentinel-2 L2A. Liquid water = NIR < {NIR_MAX} and "
                          f"SWIR < {SWIR_MAX}, clusters >= "
                          f"{MIN_PIXELS*RES*RES:.0f} m2, scenes with at least "
                          f"{MIN_CLEAR:.0%} clear over the zone."),
               "reference_2025": {"lake": "Purepu Glacier supraglacial",
                                  "from_km2": 0.08, "to_km2": 0.69,
                                  "window": "9 May to 6 Jul 2025"},
               "verdict": verdict, "series": rows},
              open(OUT, "w"), indent=2)
    print("wrote", OUT)
