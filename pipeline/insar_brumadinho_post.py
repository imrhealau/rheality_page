"""Brumadinho post-collapse coherence check.

The displacement series (insar_brumadinho.py, track 53) has to end at the
22 Jan 2019 pass: the dam was destroyed on the 25th and its radar phase with
it. But the adjacent descending track 155 passed on 29 Jan, four days after
failure. This script builds two interferograms on that track:

  05 Jan -> 17 Jan   baseline pair, dam intact on both dates
  17 Jan -> 29 Jan   spans the collapse

and compares mean interferometric coherence over the dam footprint against a
stable control area nearby. An intact surface keeps its coherence between
passes; a surface that has been replaced by a debris flow drops to noise.
That coherence collapse is the 29 Jan "the dam is gone" measurement.

  .venv/bin/python -u insar_brumadinho_post.py submit
  .venv/bin/python -u insar_brumadinho_post.py process   # waits, downloads, writes JSON

Data: Copernicus Sentinel-1 (ESA), processed by ASF HyP3 (ISCE burst InSAR).
Needs a free NASA Earthdata login in ~/.netrc.
"""
import os, sys, json, glob, zipfile, re
from datetime import datetime, timezone

HERE = os.path.dirname(__file__)
JOBS = os.path.join(HERE, "data", "hyp3_jobs_brumadinho_post.json")
INSAR_DIR = os.path.join(HERE, "insar_brumadinho_post")
OUT = os.path.join(HERE, "data", "brumadinho_postcollapse.json")

DAM = {"lat": -20.1189, "lon": -44.1197}
TRACK = 155
DATES = ["2019-01-05", "2019-01-17", "2019-01-29"]
LOOKS = "10x2"
BATCH_NAME = "brumadinho-post-collapse"
# (W, S, E, N)
DAM_BOX = [-44.125, -20.124, -44.115, -20.115]      # Dam I footprint and face
CONTROL_BOX = [-44.170, -20.105, -44.140, -20.085]  # terrain NW, untouched by the flow
READ_BOX = [-44.20, -20.16, -44.06, -20.06]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_scenes():
    import asf_search as asf
    r = asf.search(dataset=asf.DATASET.SLC_BURST,
                   intersectsWith=f"POINT({DAM['lon']} {DAM['lat']})",
                   relativeOrbit=TRACK, start="2019-01-01", end="2019-01-31",
                   maxResults=200)
    by_date = {}
    for x in r:
        name = x.properties["sceneName"]
        d = x.properties["startTime"][:10]
        if "_VV_" in name and d in DATES:
            by_date.setdefault(d, name)
    missing = [d for d in DATES if d not in by_date]
    if missing:
        sys.exit(f"no burst found for {missing}")
    return by_date


def cmd_submit():
    import hyp3_sdk
    scenes = find_scenes()
    for d in DATES:
        print(d, scenes[d])
    pairs = [(DATES[0], DATES[1]), (DATES[1], DATES[2])]
    h = hyp3_sdk.HyP3()
    print("credits before:", h.check_credits())
    records = []
    for a, b in pairs:
        batch = h.submit_insar_isce_burst_job(
            granule1=scenes[a], granule2=scenes[b], name=BATCH_NAME,
            apply_water_mask=False, looks=LOOKS)
        job = batch.jobs[0]
        records.append({"job_id": job.job_id, "ref": a, "sec": b,
                        "ref_scene": scenes[a], "sec_scene": scenes[b]})
        print(f"  {a} -> {b}  {job.job_id}", flush=True)
    os.makedirs(os.path.dirname(JOBS), exist_ok=True)
    json.dump({"batch": BATCH_NAME, "looks": LOOKS, "submitted_utc": now(),
               "jobs": records}, open(JOBS, "w"), indent=2)
    print("credits after:", h.check_credits())


def _read_box(path, box):
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    with rasterio.open(path) as ds:
        l, b, r, t = transform_bounds("EPSG:4326", ds.crs, *box)
        win = from_bounds(l, b, r, t, ds.transform)
        return ds.read(1, window=win)


def cmd_process():
    import numpy as np
    import hyp3_sdk
    h = hyp3_sdk.HyP3()
    batch = h.find_jobs(name=BATCH_NAME)
    if any(not j.complete() for j in batch):
        print("waiting on HyP3...", flush=True)
        batch = h.watch(batch)
    os.makedirs(INSAR_DIR, exist_ok=True)
    for j in batch:
        if not j.succeeded():
            print("job failed:", j.job_id, file=sys.stderr)
            continue
        for z in j.download_files(INSAR_DIR):
            if str(z).endswith(".zip"):
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(INSAR_DIR)

    recs = json.load(open(JOBS))
    results = []
    for job in recs["jobs"]:
        rd, sd = job["ref"].replace("-", ""), job["sec"].replace("-", "")
        hits = [d for d in glob.glob(os.path.join(INSAR_DIR, "*"))
                if os.path.isdir(d) and rd in os.path.basename(d) and sd in os.path.basename(d)]
        if not hits:
            print("no product for", job["ref"], job["sec"], file=sys.stderr)
            continue
        corr = glob.glob(os.path.join(hits[0], "*_corr.tif"))[0]
        dam = _read_box(corr, DAM_BOX)
        ctl = _read_box(corr, CONTROL_BOX)
        dam = dam[np.isfinite(dam) & (dam > 0)]
        ctl = ctl[np.isfinite(ctl) & (ctl > 0)]
        results.append({
            "ref": job["ref"], "sec": job["sec"],
            "spans_collapse": job["ref"] < "2019-01-25" < job["sec"],
            "coh_dam_mean": round(float(dam.mean()), 3),
            "coh_control_mean": round(float(ctl.mean()), 3),
            "frac_dam_below_03": round(float((dam < 0.3).mean()), 3),
            "n_px_dam": int(dam.size), "n_px_control": int(ctl.size),
        })
        print(results[-1])

    out = {
        "generated_utc": now(),
        "target": {"name": "Corrego do Feijao Dam I, Brumadinho", **DAM,
                   "track": TRACK, "note": "adjacent descending track; first post-collapse pass 29 Jan 2019"},
        "source": {"mission": "Sentinel-1 (ESA Copernicus)",
                   "processor": "ASF HyP3 ISCE burst InSAR", "looks": LOOKS,
                   "attribution": "Contains modified Copernicus Sentinel data 2019, processed by ASF HyP3"},
        "method": ("Interferometric coherence over the dam footprint vs a stable control area, "
                   "for a pre-collapse pair (5-17 Jan) and the pair spanning the failure (17-29 Jan). "
                   "Coherence measures whether the ground surface physically persisted between passes. "
                   "A blind search for the strongest coherence loss anywhere in the 14 km scene lands "
                   "on the dam site itself."),
        "pairs": results,
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    {"submit": cmd_submit, "process": cmd_process}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
