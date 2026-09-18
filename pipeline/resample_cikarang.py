#!/usr/bin/env python3
"""Re-extract the Cikarang stack at independently verified facility coordinates.

The first pass sampled three estate centre points. Estates here are thousands of
hectares, so an estate centre is not the ground under a data hall: OpenStreetMap
and PeeringDB put the actual buildings up to 2.2 km from those points, and the
scene has a strong gradient over that distance. This re-samples the same
inverted stack at the verified building coordinates and writes
data/cikarang_sites.json.

Sources for each coordinate are carried in SITES and printed with the result.
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio.warp import transform as warp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

SITES = [
    # key, label, lat, lon, estate, source
    ("dci_h1",      "DCI Indonesia H1 (JK1 to JK3)", -6.299731, 107.089244,
     "MM2100 Industrial Town", "PeeringDB fac/8167, Jalan Jawa Blok GG5-1"),
    ("pdg_jc3",     "Princeton Digital JC3",         -6.3747,   107.1903,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("msft_jkt05",  "Microsoft JKT05",               -6.3723,   107.1929,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("msft_jkt11",  "Microsoft JKT11",               -6.3742,   107.1933,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("aws_giic",    "Amazon Web Services, GIIC",     -6.3784,   107.1899,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("hyperspace",  "Digital Hyperspace Jakarta",    -6.3702,   107.1920,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("stt_jkt1",    "STT Jakarta 1",                 -6.3740,   107.2011,
     "GIIC Kota Deltamas", "OpenStreetMap telecom=data_center"),
    ("gtn",         "GTN Data Center",               -6.3460,   107.1671,
     "Jababeka / Sertajaya", "OpenStreetMap telecom=data_center"),
    # kept for continuity with the first pass, and labelled as what they are
    ("mm2100_pt",   "MM2100 estate centre point",    -6.302,    107.093,
     "MM2100 Industrial Town", "first pass estate point, not a building"),
    ("jababeka_pt", "Jababeka estate centre point",  -6.294,    107.145,
     "Jababeka Industrial Estate", "first pass estate point, not a building"),
    ("deltamas_pt", "Kota Deltamas estate point",    -6.355,    107.19,
     "GIIC Kota Deltamas", "first pass estate point, not a building"),
]
RADII = (250.0, 400.0)

z = np.load(os.path.join(DATA, "cikarang_disp.npz"), allow_pickle=True)
disp, vel, meancoh = z["disp"] * 1000.0, z["vel"], z["meancoh"]  # disp is stored in metres, vel in mm/yr
dates = [str(s) for s in z["dates"]]
tr = rasterio.Affine(*z["transform"])
crs = rasterio.crs.CRS.from_wkt(str(z["crs_wkt"]))
H, W = vel.shape
t = np.array([(np.datetime64(d) - np.datetime64(dates[0])) / np.timedelta64(1, "D")
              for d in dates]) / 365.25
A = np.vstack([t, np.ones_like(t)]).T
Ainv_xx = np.linalg.inv(A.T @ A)[0, 0]

ys, xs = np.mgrid[0:H, 0:W]
px_x = tr.c + (xs + 0.5) * tr.a
px_y = tr.f + (ys + 0.5) * tr.e
ok = np.isfinite(vel)

out = {"generated_utc": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
       "note": "same inverted stack as cikarang_insar.json, re-sampled at verified coordinates",
       "window": {"start": dates[0], "end": dates[-1], "epochs": len(dates)},
       "radii_m": list(RADII), "sites": {}}

for key, label, lat, lon, estate, src in SITES:
    X, Y = warp("EPSG:4326", crs, [lon], [lat])
    d2 = (px_x - X[0]) ** 2 + (px_y - Y[0]) ** 2
    rec = {"label": label, "lat": lat, "lon": lon, "estate": estate, "coord_source": src}
    for r in RADII:
        m = ok & (d2 <= r * r)
        n = int(m.sum())
        key_r = f"r{int(r)}"
        if n < 5:
            rec[key_r] = {"n_px": n, "note": "too few coherent pixels"}
            continue
        series = np.nanmedian(disp[:, m], axis=1)
        c = np.linalg.lstsq(A, series, rcond=None)[0]
        resid = series - A @ c
        rms = float(resid.std(ddof=2))
        rec[key_r] = {
            "n_px": n,
            "velocity_mm_yr": round(float(c[0]), 2),
            "velocity_sigma": round(float(rms * np.sqrt(Ainv_xx)), 2),
            "scatter_mm": round(rms, 2),
            "pixel_rate_p10_p90": [round(float(np.percentile(vel[m], 10)), 1),
                                   round(float(np.percentile(vel[m], 90)), 1)],
            "mean_coherence": round(float(np.nanmean(meancoh[m])), 3),
            "series": [{"date": d, "los_mm": round(float(v), 2)} for d, v in zip(dates, series)],
        }
    out["sites"][key] = rec
    r4 = rec.get("r400", {})
    if "velocity_mm_yr" in r4:
        print(f"{label:34s} {r4['velocity_mm_yr']:+7.1f} +- {r4['velocity_sigma']:.1f} mm/yr "
              f"({r4['n_px']:4d} px, coh {r4['mean_coherence']:.2f}, scatter {r4['scatter_mm']:.0f} mm)")
    else:
        print(f"{label:34s} {r4.get('note','no data')} ({r4.get('n_px',0)} px)")

# pairwise differences at 400 m, which is the quantity the study actually claims
keys = [k for k in out["sites"] if "velocity_mm_yr" in out["sites"][k].get("r400", {})]
pairs = {}
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        ya = np.array([p["los_mm"] for p in out["sites"][a]["r400"]["series"]])
        yb = np.array([p["los_mm"] for p in out["sites"][b]["r400"]["series"]])
        c = np.linalg.lstsq(A, ya - yb, rcond=None)[0]
        resid = (ya - yb) - A @ c
        rms = float(resid.std(ddof=2))
        pairs[f"{a}-{b}"] = {"rate_mm_yr": round(float(c[0]), 2),
                             "sigma": round(float(rms * np.sqrt(Ainv_xx)), 2),
                             "scatter_mm": round(rms, 2)}
out["pairs_r400"] = pairs
p = os.path.join(DATA, "cikarang_sites.json")
json.dump(out, open(p, "w"), indent=1)
print("\nwrote", p)
