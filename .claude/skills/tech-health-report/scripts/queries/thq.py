"""Shared query transport for the Tech Health scripts (venn-apps Log Analytics, via the az CLI login).
If TH_CACHE_DIR is set, a result is reused when the exact query text was run before (sha256 of the text), and every
live result is saved there, but only for settled windows: a query whose dates end less than SETTLE_H hours ago, or that
uses ago()/now(), always runs live and is never saved, so late-arriving data can't be frozen into the cache. TH_LOG, when set, gets one line per query: label-free sha, rows, seconds, cached or live."""
import datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
WS = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"

SETTLE_H = 12   # a window that ended less than this long ago may still be ingesting: run it live and don't save it
def settled(kql):
    """True when every date in the query is fixed and the latest ended SETTLE_H+ hours ago, so the result can't change."""
    if re.search(r"\b(ago|now)\s*\(", kql): return False
    ds = [dt.datetime.fromisoformat(d.replace("Z", "+00:00")) for d in re.findall(r"datetime\(\s*([0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9:.]+)?Z?)\s*\)", kql)]
    if not ds: return False
    last = max(d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc) for d in ds)
    return last <= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=SETTLE_H)

def q(kql):
    t0 = time.time(); key = hashlib.sha256(kql.encode("utf-8")).hexdigest()[:16]
    cdir = os.environ.get("TH_CACHE_DIR"); cp = os.path.join(cdir, key + ".json") if cdir and settled(kql) else None
    if cp and os.path.exists(cp):
        with open(cp, encoding="utf-8") as f: rows = json.load(f)["rows"]
        _log(key, len(rows), time.time() - t0, "cached"); return rows
    az = shutil.which("az") or shutil.which("az.cmd")
    if not az: sys.exit("az CLI not found; run `az login` first")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f: json.dump({"query": kql}, f); bf = f.name
    try: p = subprocess.run([az, "rest", "--method", "post", "--url", f"https://api.loganalytics.io/v1/workspaces/{WS}/query",
                             "--resource", "https://api.loganalytics.io", "--body", f"@{bf}", "-o", "json"], capture_output=True, timeout=900)
    finally: os.unlink(bf)
    if p.returncode: sys.exit(p.stderr.decode("utf-8", "replace")[-1500:])
    try: txt = p.stdout.decode("utf-8")
    except UnicodeDecodeError: txt = p.stdout.decode("cp1252")
    resp = json.loads(txt); t = resp["tables"][0]; cols = [c["name"] for c in t["columns"]]; rows = [dict(zip(cols, r)) for r in t["rows"]]
    if "error" in resp:  # PartialError: the server ran out of budget and returned some rows anyway
        msg = json.dumps(resp["error"])[:600]
        print(f"WARNING: partial query result ({len(rows)} rows), not cached: {msg}", file=sys.stderr)
        _log(key, len(rows), time.time() - t0, "PARTIAL"); return rows
    if cp:
        os.makedirs(cdir, exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f: json.dump({"query": kql, "pulled": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows}, f)
    _log(key, len(rows), time.time() - t0, "live"); return rows

def _log(key, n, secs, how):
    lp = os.environ.get("TH_LOG")
    if lp:
        with open(lp, "a", encoding="utf-8") as f: f.write(json.dumps({"q": key, "rows": n, "s": round(secs, 1), "how": how}) + "\n")
