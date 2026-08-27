"""Was optical actually blind? Check Sentinel-2 cloud over the zones that matter.

I justified a radar-only analysis on monsoon cloud without testing it. The 24 Aug
S2 scene reports 38.6% cloud over the whole AOI, which says nothing about the
source zone specifically.

SCL classes: 3 shadow, 6 water, 8/9 cloud, 10 cirrus, 11 snow/ice.
"""
import numpy as np, pystac_client, planetary_computer, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace)

ZONES = {
    "source zone (35-38 km up)":  [85.55, 28.48, 85.68, 28.58],
    "blockage reach (15-25 km)":  [85.38, 28.36, 85.55, 28.48],
    "border / Rasuwagadhi":       [85.33, 28.25, 85.47, 28.36],
}
DATES = ["2026-08-12", "2026-08-24", "2026-08-27"]
RES = 20.0
EPSG = "EPSG:32645"

for d in DATES:
    items = list(cat.search(collections=["sentinel-2-l2a"],
                            bbox=[85.30, 28.25, 85.85, 28.75],
                            datetime=f"{d}/{d}").item_collection())
    if not items:
        print(f"{d}: no scene"); continue
    print(f"\n=== {d}  ({len(items)} scene(s)) ===")
    for zname, zb in ZONES.items():
        l, b, r, t = transform_bounds("EPSG:4326", EPSG, *zb)
        l, t = np.floor(l/RES)*RES, np.ceil(t/RES)*RES
        w = int(np.ceil((r-l)/RES)); h = int(np.ceil((t-b)/RES))
        tf = from_origin(l, t, RES, RES)
        scl = np.full((h, w), 255, dtype=np.uint8)
        for it in items:
            if "SCL" not in it.assets:
                continue
            with rasterio.open(it.assets["SCL"].href) as src:
                with WarpedVRT(src, crs=EPSG, transform=tf, width=w, height=h,
                               resampling=Resampling.nearest,
                               src_nodata=0, nodata=255) as vrt:
                    a = vrt.read(1)
            take = (scl == 255) & (a != 255) & (a != 0)
            scl[take] = a[take]
        valid = scl != 255
        if valid.sum() == 0:
            print(f"  {zname:28s} no coverage"); continue
        s = scl[valid]
        cloud = np.isin(s, [3, 8, 9, 10]).mean()
        clear = 1 - cloud
        water = (s == 6).mean()
        snow = (s == 11).mean()
        verdict = "USABLE" if clear > 0.5 else ("partial" if clear > 0.2 else "blind")
        print(f"  {zname:28s} clear {clear:5.1%}  cloud {cloud:5.1%}  "
              f"snow/ice {snow:5.1%}  water {water:5.2%}   {verdict}")
