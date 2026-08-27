"""Is the S2 'water' in the source zone on 24 Aug real water, or snow/shadow?

Discriminator: liquid water is dark in both NIR (B08) and SWIR (B11). Snow and
ice are bright in NIR and dark in SWIR. Cloud shadow is dark in everything but
sits adjacent to cloud. So B08 is what separates water from snow.
"""
import numpy as np, pystac_client, planetary_computer, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin, xy
from rasterio.warp import transform_bounds, transform as tr
from scipy import ndimage

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace)

ZONE = [85.55, 28.48, 85.68, 28.58]
RES, EPSG = 20.0, "EPSG:32645"
l, b, r, t = transform_bounds("EPSG:4326", EPSG, *ZONE)
l, t = np.floor(l/RES)*RES, np.ceil(t/RES)*RES
W = int(np.ceil((r-l)/RES)); H = int(np.ceil((t-b)/RES))
TF = from_origin(l, t, RES, RES)

def read(href, nodata=0, dtype=np.float32, resamp=Resampling.bilinear):
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=EPSG, transform=TF, width=W, height=H,
                       resampling=resamp, src_nodata=nodata, nodata=0) as vrt:
            return vrt.read(1).astype(dtype)

# Copernicus DEM for elevation context
dem_items = list(cat.search(collections=["cop-dem-glo-30"], bbox=ZONE).item_collection())
dem = np.zeros((H, W), np.float32)
for it in dem_items:
    a = read(it.assets["data"].href)
    dem = np.where(dem == 0, a, dem)

for d in ("2026-08-12", "2026-08-24"):
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=ZONE,
                            datetime=f"{d}/{d}").item_collection())
    if not items:
        print(f"{d}: none"); continue
    it = max(items, key=lambda i: 100 - (i.properties.get("eo:cloud_cover") or 100))
    scl = read(it.assets["SCL"].href, dtype=np.uint8, resamp=Resampling.nearest)
    g  = read(it.assets["B03"].href) / 10000.0
    nir = read(it.assets["B08"].href) / 10000.0
    swir = read(it.assets["B11"].href) / 10000.0

    water = scl == 6
    print(f"\n=== {d}  {it.id[:44]} ===")
    print(f"  SCL water px: {water.sum():,} ({water.mean():.2%} of zone)")
    if water.sum() < 20:
        continue
    print(f"  at those px:  B03 {np.median(g[water]):.3f}   "
          f"B08(NIR) {np.median(nir[water]):.3f}   B11(SWIR) {np.median(swir[water]):.3f}")
    # true water: NIR below ~0.10. snow: NIR above ~0.30
    looks_water = water & (nir < 0.10) & (swir < 0.10)
    looks_snow  = water & (nir > 0.30)
    print(f"  of which NIR<0.10 (liquid water):  {looks_water.sum():,} px "
          f"= {looks_water.sum()*400/1e6:.3f} km2")
    print(f"  of which NIR>0.30 (snow/ice):      {looks_snow.sum():,} px "
          f"= {looks_snow.sum()*400/1e6:.3f} km2")
    # where are the genuine-water pixels, and how big is the biggest blob?
    lab, n = ndimage.label(looks_water, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum_labels(np.ones_like(lab), lab, index=np.arange(1, n+1))
        order = np.argsort(sizes)[::-1][:4]
        print(f"  {n} clusters; largest:")
        for k in order:
            if sizes[k] < 5: continue
            rr, cc = np.where(lab == k+1)
            xs, ys = xy(TF, rr.mean(), cc.mean())
            lon, lat = tr(EPSG, "EPSG:4326", [xs], [ys])
            print(f"     {int(sizes[k])*400:>9,} m2  {lat[0]:.4f},{lon[0]:.4f}  "
                  f"elev {dem[lab==k+1].mean():.0f} m  "
                  f"NIR {nir[lab==k+1].mean():.3f}")
