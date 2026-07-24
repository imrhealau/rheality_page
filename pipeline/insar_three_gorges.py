#!/usr/bin/env python3
"""Real Sentinel-1 InSAR deformation monitor over the Three Gorges Dam.

Answers the "is the dam moving / failing" question with data: builds a
small-baseline (SBAS) network of Sentinel-1 burst interferograms, has ASF
HyP3 process them in the cloud, then inverts the stack into a line-of-sight
displacement time series and a velocity, referenced to a stable point.

Data: Copernicus Sentinel-1 (ESA), processed by ASF HyP3 (ISCE burst InSAR).
Needs a free NASA Earthdata login in ~/.netrc.

Usage:
  .venv/bin/python -u insar_three_gorges.py submit    # queue the interferograms
  .venv/bin/python -u insar_three_gorges.py status    # check job progress
  .venv/bin/python -u insar_three_gorges.py process   # download + invert -> JSON
"""
import os, sys, json, zipfile, glob, math
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
JOBS = os.path.join(HERE, "data", "hyp3_jobs.json")
INSAR_DIR = os.path.join(HERE, "insar")
OUT = os.path.join(HERE, "data", "three_gorges_insar.json")

# Three Gorges Dam wall, Sandouping. Ascending track 11, burst 011_021659_IW1.
DAM = {"lat": 30.826, "lon": 111.003}
TRACK = 11
DATE_START, DATE_END = "2023-01-01", "2025-12-31"
LOOKS = "10x2"                 # ~25 m pixels; good coherence on the dam/rock
WAVELENGTH = 0.055465          # Sentinel-1 C-band, metres
BATCH_NAME = "threegorges-dam-insar"
# Small AOI around the dam for the inversion (W, S, E, N)
AOI = [110.96, 30.79, 111.05, 30.86]


def build_network():
    """Monthly-subsampled epochs and consecutive + skip-1 interferogram pairs."""
    import asf_search as asf
    r = asf.search(dataset=asf.DATASET.SLC_BURST, intersectsWith=f"POINT({DAM['lon']} {DAM['lat']})",
                   relativeOrbit=TRACK, start=DATE_START, end=DATE_END, maxResults=2000)
    scenes = sorted(((x.properties["sceneName"], x.properties["startTime"][:10]) for x in r),
                    key=lambda s: s[1])
    seen, epochs = set(), []
    for name, d in scenes:
        if d[:7] not in seen:
            seen.add(d[:7]); epochs.append({"scene": name, "date": d})
    pairs = []
    for i in range(len(epochs)):
        for j in (i + 1, i + 2):
            if j < len(epochs):
                pairs.append((epochs[i], epochs[j]))
    return epochs, pairs


def cmd_submit():
    import hyp3_sdk
    epochs, pairs = build_network()
    print(f"{len(epochs)} epochs {epochs[0]['date']}..{epochs[-1]['date']}, {len(pairs)} interferograms")
    h = hyp3_sdk.HyP3()
    print("credits before:", h.check_credits())
    records = []
    for k, (a, b) in enumerate(pairs, 1):
        batch = h.submit_insar_isce_burst_job(
            granule1=a["scene"], granule2=b["scene"], name=BATCH_NAME,
            apply_water_mask=False, looks=LOOKS)
        job = batch.jobs[0]
        records.append({"job_id": job.job_id, "ref": a["date"], "sec": b["date"],
                        "ref_scene": a["scene"], "sec_scene": b["scene"]})
        print(f"  [{k}/{len(pairs)}] {a['date']} -> {b['date']}  {job.job_id}", flush=True)
    os.makedirs(os.path.dirname(JOBS), exist_ok=True)
    json.dump({"batch": BATCH_NAME, "looks": LOOKS, "submitted_utc": now(),
               "epochs": epochs, "jobs": records}, open(JOBS, "w"), indent=2)
    print(f"\nSubmitted {len(records)} jobs. Saved {JOBS}. credits after:", h.check_credits())


def cmd_status():
    import hyp3_sdk
    h = hyp3_sdk.HyP3()
    batch = h.find_jobs(name=BATCH_NAME)
    from collections import Counter
    c = Counter(j.status_code for j in batch)
    print("job status:", dict(c), f"(total {len(batch)})")
    return c


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- processing (run once jobs succeed) ----

def _download():
    import hyp3_sdk
    h = hyp3_sdk.HyP3()
    batch = h.find_jobs(name=BATCH_NAME)
    batch = h.watch(batch) if any(j.running() for j in batch) else batch
    os.makedirs(INSAR_DIR, exist_ok=True)
    got = 0
    for j in batch:
        if not j.succeeded():
            continue
        zips = j.download_files(INSAR_DIR)
        for z in zips:
            if str(z).endswith(".zip"):
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(INSAR_DIR)
                got += 1
    print(f"downloaded/extracted {got} products into {INSAR_DIR}")


def _read_tif(path):
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    with rasterio.open(path) as ds:
        l, b, r, t = transform_bounds("EPSG:4326", ds.crs, *AOI)
        win = from_bounds(l, b, r, t, ds.transform)
        arr = ds.read(1, window=win)
    return arr


def cmd_process():
    import numpy as np
    _download()
    recs = json.load(open(JOBS))
    epochs = [e["date"] for e in recs["epochs"]]
    idx = {d: i for i, d in enumerate(epochs)}

    # gather interferograms: each product dir has *_unw_phase.tif and *_corr.tif;
    # the folder name encodes the ref/sec dates.
    import re
    ifgs = []
    for unw in glob.glob(os.path.join(INSAR_DIR, "*", "*_unw_phase.tif")):
        base = os.path.dirname(unw)
        corr = glob.glob(os.path.join(base, "*_corr.tif"))
        conn = glob.glob(os.path.join(base, "*_conncomp.tif"))
        name = os.path.basename(base)
        # ISCE burst product name: S1_<burst>_IW1_<refdate>_<secdate>_VV_...
        dts = re.findall(r"(\d{8})", name)
        if len(dts) < 2 or not corr:
            continue
        rd = f"{dts[0][:4]}-{dts[0][4:6]}-{dts[0][6:]}"
        sd = f"{dts[1][:4]}-{dts[1][4:6]}-{dts[1][6:]}"
        if rd not in idx or sd not in idx:
            continue
        ifgs.append((rd, sd, unw, corr[0], conn[0] if conn else None))
    print(f"usable interferograms: {len(ifgs)}")
    if len(ifgs) < 8:
        print("Not enough interferograms processed yet; run status/process later.", file=sys.stderr)
        sys.exit(1)

    # common grid from the first ifg
    ph0 = _read_tif(ifgs[0][2])
    H, W = ph0.shape
    n = len(epochs)

    # stable reference pixel: highest mean coherence across the stack
    csum = np.zeros((H, W)); cok = np.zeros((H, W))
    phases, cohs, G_rows = [], [], []
    for rd, sd, unw, corr, conn in ifgs:
        ph = _read_tif(unw); co = _read_tif(corr)
        if ph.shape != (H, W):
            continue
        if conn:
            cc = _read_tif(conn)
            if cc.shape == (H, W):
                co = np.where(cc > 0, co, 0.0)   # zero-weight unreliable unwrapping
        phases.append(ph); cohs.append(co)
        csum += np.nan_to_num(co); cok += (co > 0)
        row = np.zeros(n); row[idx[rd]] = -1; row[idx[sd]] = 1
        G_rows.append(row)
    meanco = np.divide(csum, np.maximum(cok, 1))
    ry, rx = np.unravel_index(np.argmax(meanco), meanco.shape)
    print(f"reference pixel coherence={meanco[ry,rx]:.2f} at ({ry},{rx})")

    # convert phase -> LOS displacement (m), reference spatially to the stable pixel
    disp = []
    for ph in phases:
        d = -ph * WAVELENGTH / (4 * math.pi)
        disp.append(d - d[ry, rx])
    disp = np.array(disp)                       # (n_ifg, H, W)
    coh = np.array(cohs)
    G = np.array(G_rows)                          # (n_ifg, n_epoch)

    # per-pixel SBAS: solve for cumulative displacement at each epoch (ref epoch 0 = 0)
    # weighted least squares, weight = coherence
    A = G[:, 1:]                                  # drop epoch 0 (reference = 0)
    ts = np.full((n, H, W), np.nan)
    dam_mask = coh.mean(0) > 0.4                 # coherent pixels only
    ys, xs = np.where(dam_mask)
    for y, x in zip(ys, xs):
        w = coh[:, y, x]
        dcol = disp[:, y, x]
        good = (w > 0.3) & np.isfinite(dcol)
        if good.sum() < A.shape[1]:
            continue
        Aw = A[good] * w[good, None]
        dw = dcol[good] * w[good]
        m, *_ = np.linalg.lstsq(Aw, dw, rcond=None)
        ts[1:, y, x] = m
        ts[0, y, x] = 0.0

    # dam-area mean time series (mm), and velocity
    dam = _dam_pixels(H, W)
    series = []
    for i, d in enumerate(epochs):
        vals = ts[i][dam & dam_mask]
        vals = vals[~np.isnan(vals)]
        if vals.size:
            series.append({"date": d, "los_mm": round(float(np.median(vals)) * 1000, 2),
                           "n_px": int(vals.size)})
    # linear velocity over the series
    t = np.array([(_ord(s["date"])) for s in series]) / 365.25
    y = np.array([s["los_mm"] for s in series])
    vel = float(np.polyfit(t - t[0], y, 1)[0])   # mm/yr
    resid = y - np.polyval(np.polyfit(t - t[0], y, 1), t - t[0])
    out = {
        "generated_utc": now(),
        "target": {"name": "Three Gorges Dam", **DAM, "track": TRACK, "burst": "011_021659_IW1"},
        "source": {"mission": "Sentinel-1 (ESA Copernicus)",
                   "processor": "ASF HyP3 ISCE burst InSAR", "looks": LOOKS,
                   "attribution": "Contains modified Copernicus Sentinel data 2023-2025, processed by ASF HyP3"},
        "method": {"network": f"{len(ifgs)} small-baseline burst interferograms, monthly epochs",
                   "inversion": "per-pixel weighted least-squares SBAS, referenced to the highest-coherence stable pixel",
                   "series": "median line-of-sight displacement over coherent dam-area pixels",
                   "limitation": "line-of-sight, one ascending track; steep-gorge layover limits coherence on parts of the wall"},
        "summary": {"epochs": len(series), "velocity_mm_yr": round(vel, 2),
                    "scatter_mm": round(float(np.std(resid)), 2),
                    "los_min_mm": round(float(y.min()), 2), "los_max_mm": round(float(y.max()), 2)},
        "series": series,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"\nWrote {OUT}")
    print(f"  {len(series)} epochs, velocity {vel:+.2f} mm/yr, scatter {out['summary']['scatter_mm']} mm")


def _dam_pixels(H, W):
    """Boolean mask of pixels near the dam wall within the AOI grid."""
    import numpy as np
    # dam sits roughly centre of the AOI; take the central band
    m = np.zeros((H, W), bool)
    y0, y1 = int(H * 0.35), int(H * 0.65)
    x0, x1 = int(W * 0.30), int(W * 0.70)
    m[y0:y1, x0:x1] = True
    return m


def _ord(d):
    y, m, dd = map(int, d.split("-"))
    return datetime(y, m, dd).toordinal()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"submit": cmd_submit, "status": cmd_status, "process": cmd_process}.get(cmd, cmd_status)()
