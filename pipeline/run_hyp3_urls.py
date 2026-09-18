#!/usr/bin/env python3
"""Run an insar_*.py `process` step on a machine with no Earthdata login.

Stands in a minimal hyp3_sdk that serves the finished products from a URL list
exported on a machine that has the login (`insar_<site>.py urls`), and
downloads them directly. Useful on a cloud VM with a fast link.

Usage:
  .venv/bin/python -u run_hyp3_urls.py insar_cikarang.py data/hyp3_urls_cikarang.json
"""
import json, os, sys, types
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
script, urls_path = sys.argv[1], sys.argv[2]
URLS = json.load(open(os.path.join(HERE, urls_path)))


class Job:
    def __init__(self, rec):
        self.rec = rec

    def complete(self):
        return True

    def succeeded(self):
        return self.rec["ok"]

    def download_files(self, tmp):
        path = os.path.join(tmp, self.rec["filename"])
        with requests.get(self.rec["url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 22):
                    f.write(chunk)
        return [path]


class HyP3:
    def find_jobs(self, name=None):
        return [Job(r) for r in URLS]

    def watch(self, batch):
        return batch


sys.modules["hyp3_sdk"] = types.SimpleNamespace(HyP3=HyP3)
path = os.path.join(HERE, script)
sys.argv = [script, "process"]
exec(compile(open(path).read(), path, "exec"), {"__name__": "__main__", "__file__": path})
