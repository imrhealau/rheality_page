#!/usr/bin/env python3
"""Sentinel-1 InSAR over the Cikarang data center cluster, Bekasi, Indonesia.

Question: how fast is the ground moving under the industrial estates where
Greater Jakarta's data centers are being built? Published InSAR studies put
parts of Cikarang at up to ~11 cm/yr of subsidence from groundwater pumping.
A data center cares about two numbers: how fast its site sinks, and how
unevenly (differential settlement is what cracks slabs and shears pipework).

Estates (industrial-estate level, not building footprints):
  MM2100 Industrial Town (DCI Indonesia JK1-JK3)
  Jababeka Industrial Estate (Datacomm Cikarang)
  GIIC Kota Deltamas (Princeton Digital JC3/JC4, EDGNEX, under construction)

Ascending track 98, bursts 098_210452_IW2 + 098_210453_IW2 merged per pair
(HyP3 multi-burst), every 12-day pass, consecutive and skip-one pairs. Same
coherence-weighted SBAS as the Srinagarind and Brumadinho runs. Each
interferogram is referenced to the median of the coherent pixels in the
southern upland strip of the box, so rates are relative to that strip.

Data: Copernicus Sentinel-1 (ESA), processed by ASF HyP3 (ISCE burst InSAR).
Submitting needs a free NASA Earthdata login in ~/.netrc; processing can run
anywhere from the exported product URLs (run_hyp3_urls.py).

Usage:
  .venv/bin/python -u insar_cikarang.py submit
  .venv/bin/python -u insar_cikarang.py status
  .venv/bin/python -u insar_cikarang.py urls      # product URLs -> data/hyp3_urls_cikarang.json
  .venv/bin/python -u insar_cikarang.py process   # stream products, invert -> JSON
"""
import os
import time, sys, json, re, math, zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
JOBS = os.path.join(DATA, "hyp3_jobs_cikarang.json")
URLS = os.path.join(DATA, "hyp3_urls_cikarang.json")
STACK = os.path.join(DATA, "cikarang_stack.npz")
OUT = os.path.join(DATA, "cikarang_insar.json")
NPZ = os.path.join(DATA, "cikarang_disp.npz")
BATCH_NAME = "cikarang-datacenter-insar"

TRACK, BURSTS = 98, ["098_210452_IW2", "098_210453_IW2"]
DATE_START, DATE_END = "2024-09-01", "2026-09-17"
AOI = [107.05, -6.40, 107.23, -6.25]        # W, S, E, N, about 20 x 17 km
REF_BAND_LAT = -6.377                       # reference strip: coherent pixels south of this
SITES = {
    "mm2100": {"name": "MM2100 Industrial Town", "lat": -6.302, "lon": 107.093,
               "tenants": "DCI Indonesia JK1-JK3"},
    "jababeka": {"name": "Jababeka Industrial Estate", "lat": -6.294, "lon": 107.145,
                 "tenants": "Datacomm Cikarang"},
    "deltamas": {"name": "GIIC Kota Deltamas", "lat": -6.355, "lon": 107.190,
                 "tenants": "Princeton Digital JC3/JC4, EDGNEX (under construction)"},
}
SITE_RADIUS_M = 400
LOOKS = "10x2"
WAVELENGTH = 0.055465
COH_MIN, MEAN_COH_MIN = 0.3, 0.4


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ord(d):
    return datetime.strptime(d, "%Y-%m-%d").toordinal()


def build_network():
    import asf_search as asf, collections
    rows = []
    for b in BURSTS:
        r = asf.search(dataset=asf.DATASET.SLC_BURST, fullBurstID=b,
                       start=DATE_START, end=DATE_END, maxResults=2000)
        rows += [(x.properties["startTime"][:10], b, x.properties["sceneName"])
                 for x in r if "_VV_" in x.properties["sceneName"]]
    by_date = collections.defaultdict(dict)
    for d, b, name in rows:
        by_date[d][b] = name
    # only passes that cover both bursts, so every interferogram has one footprint
    epochs = [{"date": d, "scenes": [by_date[d][b] for b in BURSTS]}
              for d in sorted(by_date) if len(by_date[d]) == len(BURSTS)]
    pairs = [(epochs[i], epochs[j]) for i in range(len(epochs))
             for j in (i + 1, i + 2) if j < len(epochs)]
    return epochs, pairs, len(by_date) - len(epochs)


def cmd_submit():
    import hyp3_sdk
    epochs, pairs, dropped = build_network()
    records, existing = [], set()
    if os.path.exists(JOBS):
        records = json.load(open(JOBS)).get("jobs", [])
        existing = {(j["ref"], j["sec"]) for j in records}
    new = [(a, b) for a, b in pairs if (a["date"], b["date"]) not in existing]
    print(f"{len(epochs)} epochs {epochs[0]['date']}..{epochs[-1]['date']} "
          f"({dropped} partial passes dropped), {len(pairs)} pairs, {len(new)} new to submit")
    h = hyp3_sdk.HyP3()
    before = h.check_credits()
    for k, (a, b) in enumerate(new, 1):
        job = h.submit_insar_isce_multi_burst_job(
            reference=a["scenes"], secondary=b["scenes"], name=BATCH_NAME,
            apply_water_mask=False, looks=LOOKS).jobs[0]
        records.append({"job_id": job.job_id, "ref": a["date"], "sec": b["date"]})
        if k % 20 == 0 or k == len(new):
            print(f"  [{k}/{len(new)}] {a['date']} -> {b['date']}", flush=True)
    os.makedirs(DATA, exist_ok=True)
    json.dump({"batch": BATCH_NAME, "track": TRACK, "bursts": BURSTS, "looks": LOOKS,
               "submitted_utc": now(), "epochs": [{"date": e["date"]} for e in epochs],
               "jobs": records}, open(JOBS, "w"), indent=2)
    print(f"credits {before} -> {h.check_credits()}")


def cmd_status():
    import hyp3_sdk, collections
    b = hyp3_sdk.HyP3().find_jobs(name=BATCH_NAME)
    c = collections.Counter(j.status_code for j in b)
    print(f"{BATCH_NAME}: {dict(c)} (total {len(b)})")
    return c


def cmd_urls():
    import hyp3_sdk
    b = hyp3_sdk.HyP3().find_jobs(name=BATCH_NAME)
    out = [{"url": j.files[0]["url"], "filename": j.files[0]["filename"], "ok": j.succeeded()}
           for j in b if j.complete()]
    json.dump(out, open(URLS, "w"))
    print(f"{len(out)} complete of {len(b)}, {sum(o['ok'] for o in out)} succeeded -> {URLS}")


def _grids(transform, crs, shape):
    """Distance in metres from every pixel to each site, plus pixel latitudes."""
    import numpy as np
    from rasterio.warp import transform as warp
    H, W = shape
    cols, rows = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    xs = transform.c + cols * transform.a + rows * transform.b
    ys = transform.f + cols * transform.d + rows * transform.e
    dist = {}
    for k, s in SITES.items():
        dx, dy = warp("EPSG:4326", crs, [s["lon"]], [s["lat"]])
        dist[k] = np.hypot(xs - dx[0], ys - dy[0])   # HyP3 products are UTM, so metres
    _, lat = warp(crs, "EPSG:4326", xs.ravel().tolist(), ys.ravel().tolist())
    return dist, np.array(lat).reshape(H, W)


def cmd_process():
    import numpy as np, hyp3_sdk, rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    recs = json.load(open(JOBS))
    epochs = [e["date"] for e in recs["epochs"]]
    idx = {d: i for i, d in enumerate(epochs)}
    grid, phases, cohs, rows = {}, [], [], []

    if os.path.exists(STACK):
        z = np.load(STACK, allow_pickle=True)
        phases, cohs, rows = list(z["phases"]), list(z["cohs"]), list(z["rows"])
        grid.update(transform=rasterio.Affine(*z["transform"]),
                    crs=rasterio.crs.CRS.from_wkt(str(z["crs_wkt"])),
                    shape=tuple(int(v) for v in z["shape"]))
        print(f"loaded cropped stack: {len(phases)} interferograms")
        jobs = []
    else:
        h = hyp3_sdk.HyP3()
        batch = h.find_jobs(name=BATCH_NAME)
        if any(not j.complete() for j in batch):
            batch = h.watch(batch)
        jobs = [j for j in batch if j.succeeded()]
        print(f"{len(jobs)} succeeded of {len(batch)}")

    tmp = os.path.join(HERE, "insar_cikarang")
    os.makedirs(tmp, exist_ok=True)

    def read_win(src):
        l, b, r_, t = transform_bounds("EPSG:4326", src.crs, *AOI)
        win = from_bounds(l, b, r_, t, src.transform).round_offsets().round_lengths()
        if not grid:
            grid.update(transform=src.window_transform(win), crs=src.crs,
                        shape=(int(win.height), int(win.width)))
        return src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")

    n = len(epochs)
    for k, j in enumerate(jobs, 1):
        zp = None
        try:
            for attempt in range(4):
                try:
                    zp = str(j.download_files(tmp)[0])
                    break
                except Exception as e:
                    print(f"  download retry {attempt + 1} for job {k}: {e!r}"[:200], flush=True)
                    for f in os.listdir(tmp):
                        os.remove(os.path.join(tmp, f))
                    time.sleep(10 * (attempt + 1))
            if zp is None:
                continue
            names = zipfile.ZipFile(zp).namelist()
            pick = lambda suf: next((f"/vsizip/{zp}/{x}" for x in names if x.endswith(suf)), None)
            unw, corr, conn = pick("_unw_phase.tif"), pick("_corr.tif"), pick("_conncomp.tif")
            dts = re.findall(r"_(\d{8})_(\d{8})_VV_", os.path.basename(zp))
            if not (unw and corr and dts):
                continue
            rd, sd = (f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dts[0])
            if rd not in idx or sd not in idx:
                continue
            with rasterio.open(unw) as src:
                ph = read_win(src)
            with rasterio.open(corr) as src:
                co = np.nan_to_num(read_win(src))
            if conn:
                with rasterio.open(conn) as src:
                    cc = read_win(src)
                co = np.where(np.nan_to_num(cc) > 0, co, 0.0)
            if ph.shape != grid["shape"]:
                continue
            phases.append(ph); cohs.append(co)
            row = np.zeros(n); row[idx[rd]] = -1; row[idx[sd]] = 1
            rows.append(row)
        finally:
            if zp and os.path.exists(zp):
                os.remove(zp)
        if k % 25 == 0 or k == len(jobs):
            print(f"  read {k}/{len(jobs)} ({len(phases)} usable)", flush=True)
    if len(phases) < 20:
        sys.exit("not enough interferograms")
    if not os.path.exists(STACK):
        np.savez_compressed(STACK, phases=np.array(phases), cohs=np.array(cohs),
                            rows=np.array(rows), transform=np.array(grid["transform"])[:6],
                            crs_wkt=grid["crs"].to_wkt(), shape=np.array(grid["shape"]))

    H, W = grid["shape"]
    coh = np.array(cohs)
    meanco = coh.sum(0) / np.maximum((coh > 0).sum(0), 1)
    dist, lat = _grids(grid["transform"], grid["crs"], (H, W))

    disp = np.array([-p * WAVELENGTH / (4 * math.pi) for p in phases])
    # reference each interferogram to the median of its coherent pixels in the southern strip
    band = lat < REF_BAND_LAT
    for i in range(len(disp)):
        m = band & (coh[i] > 0.5) & np.isfinite(disp[i])
        disp[i] -= np.median(disp[i][m]) if m.sum() >= 50 else np.nan
    print(f"reference strip: {int((band & (meanco > 0.5)).sum())} coherent pixels south of {REF_BAND_LAT}")

    R = np.array(rows)
    A = R[:, 1:]
    pair_ref, pair_sec = np.argmin(R, axis=1), np.argmax(R, axis=1)
    ts = np.full((n, H, W), np.nan, "float32")
    ys, xs = np.where(meanco > MEAN_COH_MIN)
    print(f"inverting {len(ys)} coherent pixels")
    for y, x in zip(ys, xs):
        w, dcol = coh[:, y, x], disp[:, y, x]
        good = (w > COH_MIN) & np.isfinite(dcol)
        # keep the epochs still connected to the first one; leave stranded ones blank
        par = list(range(n))
        def root(e):
            while par[e] != e:
                par[e] = par[par[e]]; e = par[e]
            return e
        for gi in np.where(good)[0]:
            par[root(pair_ref[gi])] = root(pair_sec[gi])
        conn = np.array([root(e) == root(0) for e in range(n)])
        if conn.sum() < 0.8 * n:
            continue
        cols = np.where(conn[1:])[0]
        use = good & conn[pair_ref] & conn[pair_sec]
        if use.sum() < len(cols):
            continue
        try:
            m, *_ = np.linalg.lstsq(A[use][:, cols] * w[use, None], dcol[use] * w[use], rcond=None)
        except np.linalg.LinAlgError:
            continue
        ts[0, y, x] = 0.0
        ts[1 + cols, y, x] = m

    tyr = (np.array([_ord(d) for d in epochs]) - _ord(epochs[0])) / 365.25
    valid = np.isfinite(ts).sum(0) >= 0.8 * n
    vel = np.full((H, W), np.nan)
    G1 = np.column_stack([np.ones_like(tyr), tyr])
    for y, x in zip(*np.where(valid)):
        col = ts[:, y, x] * 1000
        g = np.isfinite(col)
        if g.sum() >= 10:
            vel[y, x] = np.linalg.lstsq(G1[g], col[g], rcond=None)[0][1]
    np.savez_compressed(NPZ, dates=np.array(epochs), disp=ts, meancoh=meanco, vel=vel,
                        lat=lat.astype("float32"),
                        transform=np.array(grid["transform"]).reshape(-1)[:6],
                        crs_wkt=grid["crs"].to_wkt())

    def series(mask):
        out = []
        for i, d in enumerate(epochs):
            v = ts[i][mask]; v = v[np.isfinite(v)]
            if v.size:
                out.append({"date": d, "los_mm": round(float(np.median(v)) * 1000, 2),
                            "n_px": int(v.size)})
        return out

    def fit(s):
        t = np.array([(_ord(p["date"]) - _ord(epochs[0])) / 365.25 for p in s])
        y = np.array([p["los_mm"] for p in s])
        G = np.column_stack([np.ones_like(t), t])
        m, *_ = np.linalg.lstsq(G, y, rcond=None)
        r = y - G @ m
        s2 = (r @ r) / max(len(y) - 2, 1)
        cov = s2 * np.linalg.inv(G.T @ G)
        return {"velocity_mm_yr": round(float(m[1]), 2),
                "velocity_sigma": round(float(np.sqrt(cov[1, 1])), 2),
                "scatter_mm": round(float(np.sqrt(s2)), 2)}

    sites = {}
    for k, s in SITES.items():
        mask = valid & (dist[k] <= SITE_RADIUS_M)
        v = vel[mask]; v = v[np.isfinite(v)]
        entry = {**s, "n_px": int(mask.sum())}
        if v.size >= 10:
            ser = series(mask)
            entry.update(fit(ser))
            # differential settlement: spread of pixel rates across the estate
            entry["rate_p10_p90_mm_yr"] = [round(float(np.percentile(v, 10)), 1),
                                           round(float(np.percentile(v, 90)), 1)]
            entry["series"] = ser
        sites[k] = entry

    vv = vel[np.isfinite(vel)]
    out = {
        "generated_utc": now(),
        "target": {"name": "Cikarang data center cluster, Bekasi, Indonesia",
                   "track": TRACK, "bursts": BURSTS, "flight": "ascending", "aoi": AOI},
        "source": {"mission": "Sentinel-1 (ESA Copernicus)",
                   "processor": "ASF HyP3 ISCE multi-burst InSAR", "looks": LOOKS,
                   "attribution": "Contains modified Copernicus Sentinel data 2024-2026, processed by ASF HyP3"},
        "method": {"network": f"{len(phases)} two-burst interferograms, every 12-day pass, consecutive + skip-one",
                   "inversion": "per-pixel coherence-weighted least-squares SBAS",
                   "reference": f"each interferogram referenced to the median of coherent pixels south of latitude {REF_BAND_LAT}; rates are relative to that strip",
                   "site_pixels": f"coherent pixels within {SITE_RADIUS_M} m of an estate point (estate level, not building footprints)",
                   "limitations": "one look direction (line of sight only; vertical subsidence reads as about 0.8x in LOS); "
                                  "no tropospheric correction, and free InSAR is not yet validated for humid tropical ground "
                                  "(Puerto Rico GNSS check: tens of mm/yr error over 7 months), so trust rates well above that level; "
                                  "the reference strip may itself move"},
        "window": {"start": epochs[0], "end": epochs[-1], "epochs": n},
        "aoi_velocity_mm_yr": {"n_px": int(vv.size),
                               "p5": round(float(np.percentile(vv, 5)), 1),
                               "median": round(float(np.median(vv)), 1),
                               "p95": round(float(np.percentile(vv, 95)), 1)},
        "sites": sites,
    }
    json.dump(out, open(OUT, "w"), indent=2)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print(f"\nwrote {OUT}")
    print(f"AOI LOS velocity p5/median/p95: {out['aoi_velocity_mm_yr']}")
    for k, s in sites.items():
        if "velocity_mm_yr" in s:
            print(f"{s['name']} ({s['n_px']} px): {s['velocity_mm_yr']:+.1f} ± {s['velocity_sigma']} mm/yr, "
                  f"pixel spread p10..p90 {s['rate_p10_p90_mm_yr']}, scatter {s['scatter_mm']} mm")
        else:
            print(f"{s['name']}: too few coherent pixels ({s['n_px']})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"submit": cmd_submit, "status": cmd_status, "urls": cmd_urls,
     "process": cmd_process}.get(cmd, cmd_status)()
