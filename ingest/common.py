"""Shared helpers for the pipeline. Python stdlib only."""
import json, pathlib, shutil, urllib.request, datetime, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INTER = DATA / "intermediate"
WARN_BASE = "https://approjects-warn-act-notices.static.hf.space"
UA = {"User-Agent": "warn-dashboard-pipeline (github.com/Abezzam10/warn-dashboard)"}


def today():
    return datetime.date.today().isoformat()


def fetch(url, dest, timeout=180):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path, default=None):
    p = pathlib.Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def dump_json(obj, path):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    return p
