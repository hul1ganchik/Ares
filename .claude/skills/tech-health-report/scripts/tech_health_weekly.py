#!/usr/bin/env python3
"""Tech Health v1 weekly run. Pulls fleet tables once from the venn-apps Log Analytics workspace, computes every
number the Tech Health page shows for each account, and writes the db documents to upload (no model needed).

Usage
  python tech_health_weekly.py --accounts <key> [--week 2026-10-05] [--out /tmp/techhealth] [--backfill 5]

  --week      Monday that starts the reported week (default: the last full Mon-Sun week before today, UTC)
  --backfill  how many weeks of weekly rows to (re)write, ending with --week (default 5; the page trends whatever is stored)

Auth: if AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET are set (cloud routine), a client-credentials token
is used; otherwise the local `az` CLI login. Values are never printed.

Output (in --out):
  weeks.json    {docs: [{collection, doc_id, data}]}  one doc per account per week  -> collection "weeks"
  reports.json  {docs: [...]}                          one doc per account for --week -> collection "reports"
  feed.csv      one row per account for the CSM sheet (written without insights; the routine adds the chip text)
  run.json      run id, windows, completeness checks, timings
  facts_<acct>.json  compact numbers for the insight writer (the only file a model needs to read)
Exit code 2 if a completeness check fails (row count != exact scalar).
"""
import argparse, csv, datetime as dt, json, os, re, shutil, statistics as st, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from collections import Counter, defaultdict

WORKSPACE = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"
VERSION = "tech-health-weekly 1.2.3"
MIN_DAYS_P, MIN_N_P = 5, 50          # period (28 d) scoring floor
MIN_DAYS_W, MIN_N_W = 3, 50          # weekly floor
SHARED_IP_USERS = 20                 # a public IP used by this many users is an egress/gateway, not a home
BANDS = [(0, 100, "Under 100 ms"), (100, 150, "100 to 150 ms"), (150, 175, "150 to 175 ms"), (175, 200, "175 to 200 ms"),
         (200, 250, "200 to 250 ms"), (250, 10 ** 9, "250 ms and over")]

# ------------------------------------------------------------------ transport
_token = {"v": None, "exp": 0}
def _sp_token():
    if _token["v"] and time.time() < _token["exp"] - 120: return _token["v"]
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": os.environ["AZURE_CLIENT_ID"],
                                   "client_secret": os.environ["AZURE_CLIENT_SECRET"], "scope": "https://api.loganalytics.io/.default"}).encode()
    req = urllib.request.Request(f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token", data=body)
    with urllib.request.urlopen(req, timeout=60) as r: j = json.load(r)
    _token.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)))
    return _token["v"]

def _tables(txt):
    t = json.loads(txt)["tables"][0]; cols = [c["name"] for c in t["columns"]]
    return [dict(zip(cols, r)) for r in t["rows"]]

CACHE = {"dir": None}
SETTLE_H = 12   # a window that ended less than this long ago may still be ingesting: run it live and don't save it
def settled(kql):
    """True when every date in the query is fixed and the latest ended SETTLE_H+ hours ago, so the result can't change."""
    if re.search(r"\b(ago|now)\s*\(", kql): return False
    ds = [dt.datetime.fromisoformat(d.replace("Z", "+00:00")) for d in re.findall(r"datetime\(\s*([0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9:.]+)?Z?)\s*\)", kql)]
    if not ds: return False
    last = max(d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc) for d in ds)
    return last <= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=SETTLE_H)

def kql(query, label):
    """Run one query. With --cache-dir, a saved result is reused when its query text matches exactly
    (account-specific queries differ in text, so they run live); every complete live result is saved. Windows that
    ended under SETTLE_H hours ago are never reused or saved (see settled)."""
    t0 = time.time()
    cp = os.path.join(CACHE["dir"], label + ".json") if CACHE["dir"] and settled(query) else None
    if cp and os.path.exists(cp):
        with open(cp, encoding="utf-8") as f: c = json.load(f)
        if c.get("query") == query:
            TIMINGS[label] = 0.0; CACHED.append(label)
            print(f"  {label}: {len(c['rows'])} rows, cached {c.get('pulled_utc', '')}", flush=True)
            return c["rows"]
    if all(os.environ.get(k) for k in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")):
        req = urllib.request.Request(f"https://api.loganalytics.io/v1/workspaces/{WORKSPACE}/query",
                                     data=json.dumps({"query": query}).encode(),
                                     headers={"Authorization": "Bearer " + _sp_token(), "Content-Type": "application/json", "Prefer": "wait=600"})
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=900) as r: raw = r.read()
                break
            except Exception as e:
                if attempt == 2: sys.exit(f"query {label} failed: {e}")
                time.sleep(20)
    else:
        az = shutil.which("az") or shutil.which("az.cmd")
        if not az: sys.exit("No AZURE_* credentials and no az CLI. Set the env vars or run `az login`.")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"query": query}, f); bf = f.name
        try:
            p = subprocess.run([az, "rest", "--method", "post", "--url", f"https://api.loganalytics.io/v1/workspaces/{WORKSPACE}/query",
                                "--resource", "https://api.loganalytics.io", "--body", f"@{bf}", "-o", "json"], capture_output=True, timeout=900)
        finally: os.unlink(bf)
        if p.returncode: sys.exit(f"query {label} failed: " + p.stderr.decode("utf-8", "replace")[-800:])
        raw = p.stdout
    try: txt = raw.decode("utf-8")
    except UnicodeDecodeError: txt = raw.decode("cp1252")
    rows = _tables(txt)
    if "error" in json.loads(txt):  # PartialError: the server ran out of budget and returned some rows anyway
        print(f"  WARNING: {label} returned a partial result ({len(rows)} rows), not cached: {json.dumps(json.loads(txt)['error'])[:400]}", file=sys.stderr, flush=True)
        cp = None
    if cp:
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"label": label, "query": query, "pulled_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": rows}, f)
    TIMINGS[label] = round(time.time() - t0, 1)
    print(f"  {label}: {len(rows)} rows, {TIMINGS[label]} s", flush=True)
    return rows
TIMINGS = {}
CACHED = []

BASE = """let ws = datetime({ws}); let we = datetime({we});
let base = AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId);
"""
Q_SS = BASE + """base | where Name == 'Session Score'
| extend HF = todouble(Measurements['Device.memoryHardFaults']), Fz = todouble(Measurements['Stability.unresponsiveApps']),
  Cpu = todouble(Measurements['Device.cpuLoad']), P = todouble(Measurements['Container.pcgLatency']), Net = todouble(Measurements['Device.networkLatency']),
  ND = todouble(Measurements['Device.networkDisconnects']), PD = todouble(Measurements['Container.pcgDisconnects']), {bucket}
| summarize N=count(), Days=dcount(startofday(TimeGenerated)), HF500=countif(HF>=500), HF2000=countif(HF>=2000), Fz1=countif(Fz>=1), Cpu90=countif(Cpu>=90),
  PcgN=countif(P>0), PcgP50=percentile(iff(P>0,P,real(null)),50), NetP50=percentile(iff(Net>0,Net,real(null)),50), Nd1=countif(ND>0), Pd1=countif(PD>0)
  by U, Acct, B"""
Q_SS_SCALAR = BASE + "base | where Name == 'Session Score' | extend {bucket} | summarize by U, Acct, B | count"
Q_START = BASE + """base | where Name == 'Container started'
| summarize Starts=count(), RamMiB=max(todouble(Measurements['TotalPhysicalMemory'])), Cpu=take_any(tostring(Properties.CpuName)),
  Cores=max(toint(Properties.CpuNumberOfCores)), FreeMin=min(todouble(Measurements['SystemDriveTotalFreeSpace'])),
  WifiStarts=countif(toint(Properties.WifiSignalStrength) > 0), FreeRamP50=percentile(todouble(Measurements['AvailablePhysicalMemory']), 50) by U, Acct"""
Q_LAUNCH = BASE + """let L = materialize(base | where Name == 'App launched'
| extend App = tostring(Properties.appName), Lat = todouble(Measurements.timeToLaunchApp)
| where isnotempty(App) and App != 'Workplace.ReadyBlueTest.exe' | project U, Acct, App, Lat);
let P = L | where Acct !in ({targets}) | summarize n=count(), u=dcount(U), P90=percentile(Lat,90) by App | where n >= 200 and u >= 25;
L | join kind=inner P on App | summarize Launches=count(), OverR=countif(Lat > P90 and Lat > 5000) by U, Acct"""
Q_ROAM = """let ws = datetime({ws}); let we = datetime({we});
AppTraces | where TimeGenerated >= ws and TimeGenerated < we and Message has 'PCG health'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId), Site = extract(@'PublicIp:\\s*([0-9]+\\.[0-9]+\\.[0-9]+)\\.[0-9]+', 1, Message)
| where isnotempty(Site)
| summarize Sites = dcount(Site) by U, Acct, H = bin(TimeGenerated, 1h)
| extend {bucket_h}
| summarize Hours = count(), RoamHours = countif(Sites >= 2) by U, Acct, B"""
Q_APPS = BASE + """base | where Name == 'App launched'
| extend App = tostring(Properties.appName), Path = tolower(tostring(Properties.appPath))
| where isnotempty(App) and App != 'Workplace.ReadyBlueTest.exe' and App !startswith 'Workplace' and App !in~ ('File Explorer', 'explorer.exe')
| summarize Launches = count(), Web = countif(Path has 'chrome.exe' or Path has 'msedge.exe' or Path has 'firefox.exe') by U, Acct, App"""
Q_LOOP = BASE + """base | where Name == 'PCG connection failed'
| summarize F = count() by U, Acct, W5 = bin(TimeGenerated, 5m), D = startofday(TimeGenerated)
| summarize LoopWindows = countif(F >= 5), LoopDays = dcountif(D, F >= 5) by U, Acct"""
# main IP = the user's most-used address that fewer than 5 users of the same account share; only users with no such address fall back to a shared one.
# A shared US exit (VPN, proxy) can out-count a user's own home address, which counted Philippines users as US.
Q_IP = BASE + """let ipb = base | where isnotempty(ClientIP) and ClientIP != '0.0.0.0';
let ipu = ipb | summarize AcctIpUsers = dcount(U) by ClientIP, Acct;
ipb | summarize E = count(), Country = take_any(ClientCountryOrRegion) by U, Acct, ClientIP
| join kind=inner ipu on ClientIP, Acct | extend R = iff(AcctIpUsers < 5, 1e12, 0.0) + E
| summarize arg_max(R, ClientIP, Country) by U, Acct | project-away R"""

# ------------------------------------------------------------------ helpers
def p90(v):
    v = sorted(x for x in v if x is not None); return v[int(0.9 * (len(v) - 1))] if v else None

def ram_tier(r):
    mib = r.get("RamMiB")
    if not mib: return None
    gb = mib / 1024; tol = 2.5 if "AMD" in (r.get("Cpu") or "") else 1.0
    for s in (8, 16, 24, 32, 48, 64):
        if s - tol <= gb <= s + 0.3: return s
    return round(gb)

def rate(n, d): return round(100 * n / d, 1) if d else None

def band_split(vals):
    return [{"band": lab, "users": sum(lo <= v < hi for v in vals), "pct": rate(sum(lo <= v < hi for v in vals), len(vals))} for lo, hi, lab in BANDS]

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--accounts", required=True); ap.add_argument("--week")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "techhealth")); ap.add_argument("--backfill", type=int, default=5)
    ap.add_argument("--cache-dir", help="reuse saved query results whose text matches; save every live result")
    a = ap.parse_args()
    if a.cache_dir: os.makedirs(a.cache_dir, exist_ok=True); CACHE["dir"] = a.cache_dir
    accts = [x.strip().lower() for x in a.accounts.split(",") if x.strip()]
    today = dt.datetime.now(dt.timezone.utc).date()
    week = dt.date.fromisoformat(a.week) if a.week else today - dt.timedelta(days=today.weekday() + 7)
    assert week.weekday() == 0, "--week must be a Monday"
    wend = week + dt.timedelta(days=7)
    cur = (week - dt.timedelta(days=21), wend); prev = (cur[0] - dt.timedelta(days=28), cur[0])
    wstart = wend - dt.timedelta(days=7 * a.backfill)
    os.makedirs(a.out, exist_ok=True)
    run_id = "th-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tq = ",".join(f"'{x}'" for x in accts)
    print(f"{VERSION} run {run_id}: week {week}, period {cur[0]}..{cur[1]}, prior {prev[0]}..{prev[1]}, weekly {wstart}..{wend}", flush=True)
    checks = {}

    # ---- pulls
    wk_bucket = f"B = toint((datetime({wend}) - TimeGenerated) / 7d)"
    SSW = kql(Q_SS.format(ws=wstart, we=wend, bucket=wk_bucket), "weekly_session")
    sc = kql(Q_SS_SCALAR.format(ws=wstart, we=wend, bucket=wk_bucket), "weekly_session_scalar")[0]["Count"]
    checks["weekly_session"] = [len(SSW), sc]
    RW = kql(Q_ROAM.format(ws=wstart, we=wend, bucket_h=f"B = toint((datetime({wend}) - H) / 7d)"), "weekly_roaming")
    P = {}
    for name, (ws, we) in (("cur", cur), ("prev", prev)):
        ss = kql(Q_SS.format(ws=ws, we=we, bucket="B = 0"), f"{name}_session")
        sc = kql(Q_SS_SCALAR.format(ws=ws, we=we, bucket="B = 0"), f"{name}_session_scalar")[0]["Count"]
        checks[f"{name}_session"] = [len(ss), sc]
        P[name] = {"ss": {r["U"]: r for r in ss},
                   "start": {r["U"]: r for r in kql(Q_START.format(ws=ws, we=we), f"{name}_start")},
                   "launch": {r["U"]: r for r in kql(Q_LAUNCH.format(ws=ws, we=we, targets=tq), f"{name}_launch")},
                   "roam": {r["U"]: r for r in kql(Q_ROAM.format(ws=ws, we=we, bucket_h="B = 0"), f"{name}_roaming")},
                   "loop": {r["U"]: r for r in kql(Q_LOOP.format(ws=ws, we=we), f"{name}_looping")}}
    IPS = kql(Q_IP.format(ws=cur[0], we=cur[1]), "cur_ip")
    APPS = kql(Q_APPS.format(ws=cur[0], we=cur[1]), "cur_apps")
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}

    # ---- period flags
    def period_users(pp):
        ss, stt, la, ro, lo = pp["ss"], pp["start"], pp["launch"], pp["roam"], pp["loop"]
        U = {u: r for u, r in ss.items() if (r["Days"] or 0) >= MIN_DAYS_P and (r["N"] or 0) >= MIN_N_P}
        oth = [r for r in U.values() if r["Acct"] not in accts]
        nl = p90([r["Nd1"] / r["N"] for r in oth]); gl = p90([r["Pd1"] / r["N"] for r in oth])
        rl = p90([x["RoamHours"] / x["Hours"] for x in ro.values() if x["Acct"] not in accts and x["Hours"] >= 20])
        out = {}
        for u, r in U.items():
            s = stt.get(u, {}); l = la.get(u, {}); x = ro.get(u); lp = lo.get(u, {})
            f = {"acct": r["Acct"], "ram": ram_tier(s), "cores": s.get("Cores"),
                 "wifi": bool(s.get("Starts")) and (s.get("WifiStarts") or 0) / s["Starts"] >= 0.5,
                 "swap": r["HF500"] / r["N"] >= 0.5 or r["HF2000"] / r["N"] >= 0.25,
                 "frozen": r["Fz1"] / r["N"] >= 0.05,
                 "latency": (r["PcgN"] or 0) >= MIN_N_P and (r["PcgP50"] or 0) >= 250,
                 "launch": (l.get("Launches") or 0) >= 10 and (l.get("OverR") or 0) >= 3 and l["OverR"] / l["Launches"] >= 0.25,
                 "net": r["Nd1"] / r["N"] > nl, "gw": r["Pd1"] / r["N"] > gl,
                 "roam": bool(x) and x["Hours"] >= 20 and x["RoamHours"] / x["Hours"] > rl,
                 "loop": (lp.get("LoopWindows") or 0) > 0,
                 "low_disk": s.get("FreeMin") is not None and s["FreeMin"] < 10,
                 "free_mb": s.get("FreeRamP50"),
                 "cpu": r["Cpu90"] / r["N"] >= 0.10,
                 "pcg_p50": r["PcgP50"] if (r["PcgN"] or 0) >= MIN_N_P else None, "net_p50": r["NetP50"],
                 "net_share": r["Nd1"] / r["N"], "gw_share": r["Pd1"] / r["N"]}
            out[u] = f
        return out, {"net_line": nl, "gw_line": gl, "roam_line": rl}
    PU = {k: period_users(P[k]) for k in P}

    # ---- weekly rows
    wkrows = defaultdict(list)
    for r in SSW:
        if (r["N"] or 0) >= MIN_N_W and (r["Days"] or 0) >= MIN_DAYS_W: wkrows[r["B"]].append(r)
    wkroam = defaultdict(list)
    for r in RW:
        if (r["Hours"] or 0) >= 10: wkroam[r["B"]].append(r)

    ip_users = Counter(r["ClientIP"] for r in IPS)
    country = {r["U"]: (r["Country"] or "?") for r in IPS if ip_users[r["ClientIP"]] < SHARED_IP_USERS}

    weeks_docs, report_docs, feed = [], [], []
    MEAS = ["swap", "net", "gw", "roam", "frozen", "latency"]
    for acct in accts:
        for b in range(a.backfill - 1, -1, -1):
            wk = (wend - dt.timedelta(days=7 * (b + 1))).isoformat()
            rows = wkrows[b]; A = [r for r in rows if r["Acct"] == acct]; O = [r for r in rows if r["Acct"] not in accts]
            if not A: continue
            nl = p90([r["Nd1"] / r["N"] for r in O]); gl = p90([r["Pd1"] / r["N"] for r in O])
            fn = {"swap": lambda r: r["HF500"] / r["N"] >= 0.5 or r["HF2000"] / r["N"] >= 0.25, "net": lambda r: r["Nd1"] / r["N"] > nl,
                  "gw": lambda r: r["Pd1"] / r["N"] > gl, "frozen": lambda r: r["Fz1"] / r["N"] >= 0.05,
                  "latency": lambda r: (r["PcgN"] or 0) >= 30 and (r["PcgP50"] or 0) >= 250}
            m = {k: {"acct": rate(sum(map(f, A)), len(A)), "others": rate(sum(map(f, O)), len(O)), "users": sum(map(f, A)), "n": len(A)} for k, f in fn.items()}
            rr = wkroam[b]; RA = [x for x in rr if x["Acct"] == acct]; RO = [x for x in rr if x["Acct"] not in accts]
            rl = p90([x["RoamHours"] / x["Hours"] for x in RO]); rf = lambda x: x["RoamHours"] / x["Hours"] > rl
            m["roam"] = {"acct": rate(sum(map(rf, RA)), len(RA)), "others": rate(sum(map(rf, RO)), len(RO)), "users": sum(map(rf, RA)), "n": len(RA)}
            la = [r["PcgP50"] for r in A if (r["PcgN"] or 0) >= 30 and r["PcgP50"]]; lo = [r["PcgP50"] for r in O if (r["PcgN"] or 0) >= 30 and r["PcgP50"]]
            m["lat_ms"] = {"acct": round(st.mean(la)) if la else None, "others": round(st.mean(lo)) if lo else None,
                           "acct_med": round(st.median(la)) if la else None, "others_med": round(st.median(lo)) if lo else None, "n": len(la)}
            weeks_docs.append({"collection": "weeks", "doc_id": f"{acct}__{wk}", "data": {
                "account": acct, "week": wk, "measures": m, "bands": {"acct": band_split(la), "others": band_split(lo)},
                "run_id": run_id, "version": VERSION}})

        # ---- report doc (period detail)
        cu, cl = PU["cur"]; pu, pl = PU["prev"]
        A = {u: f for u, f in cu.items() if f["acct"] == acct}; O = [f for f in cu.values() if f["acct"] not in accts]
        Ap = {u: f for u, f in pu.items() if f["acct"] == acct}; Op = [f for f in pu.values() if f["acct"] not in accts]
        if not A: print(f"WARNING: no scored users for {acct}"); continue
        lo12 = [f for f in A.values() if f["ram"] and f["ram"] <= 12]; hi16 = [f for f in A.values() if f["ram"] and f["ram"] >= 16]
        RAMBANDS = {"8 GB or less": lambda f: bool(f["ram"]) and f["ram"] <= 8, "12 GB": lambda f: bool(f["ram"]) and 8 < f["ram"] <= 12,
                    "16 GB": lambda f: bool(f["ram"]) and 12 < f["ram"] <= 16, "20 GB+": lambda f: bool(f["ram"]) and f["ram"] > 16}
        params = {}
        for k in ("swap", "net", "gw", "roam", "frozen", "latency", "launch", "low_disk", "loop", "cpu"):
            pers = sorted(u for u, f in A.items() if f[k] and u in Ap and Ap[u][k])
            params[k] = {"cur": {"users": sum(f[k] for f in A.values()), "of": len(A), "rate": rate(sum(f[k] for f in A.values()), len(A)),
                                 "others": rate(sum(f[k] for f in O), len(O))},
                         "prev": {"rate": rate(sum(f[k] for f in Ap.values()), len(Ap)), "others": rate(sum(f[k] for f in Op), len(Op))},
                         "le12": [sum(f[k] for f in lo12), len(lo12)], "ge16": [sum(f[k] for f in hi16), len(hi16)], "persistent": len(pers),
                         "bands": {bn: [sum(f[k] for f in A.values() if bf(f)), sum(1 for f in A.values() if bf(f)),
                                        sum(f[k] for f in O if bf(f)), sum(1 for f in O if bf(f))] for bn, bf in RAMBANDS.items()}}
        # CPU cores (physical, from Container started): users per bucket and three measures, account against other customers
        COREBANDS = {"4 or fewer": lambda f: bool(f["cores"]) and f["cores"] <= 4, "6 to 8": lambda f: bool(f["cores"]) and 4 < f["cores"] <= 8,
                     "10 to 12": lambda f: bool(f["cores"]) and 8 < f["cores"] <= 12, "14 or more": lambda f: bool(f["cores"]) and f["cores"] > 12}
        cores = {bn: {"acct_n": sum(1 for f in A.values() if bf(f)), "others_n": sum(1 for f in O if bf(f)),
                      **{k: [sum(f[k] for f in A.values() if bf(f)), sum(1 for f in A.values() if bf(f)), sum(f[k] for f in O if bf(f)), sum(1 for f in O if bf(f))]
                         for k in ("swap", "cpu", "frozen")}} for bn, bf in COREBANDS.items()}
        cores_known = {"acct": sum(1 for f in A.values() if f["cores"]), "others": sum(1 for f in O if f["cores"])}
        GROUP = {"swap": "memory", "net": "connectivity", "gw": "connectivity", "frozen": "frozen", "latency": "latency", "launch": "launch"}
        named = []
        for u, f in A.items():
            pk = [k for k in GROUP if f[k] and u in Ap and Ap[u][k]]
            if pk: named.append({"user": u, "persistent": pk, "groups": sorted({GROUP[k] for k in pk}), "now": [k for k in GROUP if f[k]], "ram": f["ram"]})
        named.sort(key=lambda x: (-len(x["groups"]), -len(x["persistent"]), x["user"]))
        multi = [x for x in named if len(x["groups"]) >= 2]
        conn_only = [x for x in named if x["groups"] == ["connectivity"] and {"net", "gw"} <= set(x["persistent"])]
        # First period: no scored users in the prior 28 days, so "both months" cannot be measured. List who is flagged now instead.
        no_prior = not Ap
        now_list = sorted(({"user": u, "now": [k for k in GROUP if f[k]], "groups": sorted({GROUP[k] for k in GROUP if f[k]}), "ram": f["ram"]}
                           for u, f in A.items() if any(f[k] for k in GROUP)), key=lambda x: (-len(x["groups"]), -len(x["now"]), x["user"]))[:50]   # top 50; any_now has the full count
        med = lambda v: round(100 * st.median(v), 2) if v else None
        conn = {"cabled": {"acct_net": med([f["net_share"] for f in A.values() if not f["wifi"]]), "others_net": med([f["net_share"] for f in O if not f["wifi"]]),
                           "acct_gw": med([f["gw_share"] for f in A.values() if not f["wifi"]]), "others_gw": med([f["gw_share"] for f in O if not f["wifi"]]),
                           "acct_n": sum(1 for f in A.values() if not f["wifi"])},
                "wifi": {"acct_net": med([f["net_share"] for f in A.values() if f["wifi"]]), "others_net": med([f["net_share"] for f in O if f["wifi"]]),
                         "acct_gw": med([f["gw_share"] for f in A.values() if f["wifi"]]), "others_gw": med([f["gw_share"] for f in O if f["wifi"]]),
                         "acct_n": sum(1 for f in A.values() if f["wifi"])},
                "both_drop_measures": sum(1 for f in A.values() if f["net"] and f["gw"]), "net_users": sum(f["net"] for f in A.values()),
                "roamers_with_net_drops": sum(1 for f in A.values() if f["roam"] and f["net"]), "roamers": sum(f["roam"] for f in A.values()),
                "home_ip_share": None}
        # same-country latency baseline
        byc = defaultdict(lambda: {"a": [], "o": []})
        for u, f in cu.items():
            c = country.get(u)
            if c and f["pcg_p50"]: byc[c]["a" if f["acct"] == acct else "o"].append(f["pcg_p50"])
        ctab = []
        for c, d in sorted(byc.items(), key=lambda z: -len(z[1]["a"])):
            if len(d["a"]) < 8: continue
            base = round(st.median(d["o"])) if len(d["o"]) >= 10 else None
            ctab.append({"country": c, "acct_n": len(d["a"]), "acct_med": round(st.median(d["a"])), "others_n": len(d["o"]), "others_med": base,
                         "over50": sum(v >= base + 50 for v in d["a"]) if base else None})
        ips_a = [r for r in IPS if r["Acct"] == acct]
        conn["home_ip_share"] = [sum(1 for r in ips_a if ip_users[r["ClientIP"]] == 1), len(ips_a)]
        lat_a = [f["pcg_p50"] for f in A.values() if f["pcg_p50"]]; lat_o = [f["pcg_p50"] for f in O if f["pcg_p50"]]
        lat_ap = [f["pcg_p50"] for f in Ap.values() if f["pcg_p50"]]; lat_op = [f["pcg_p50"] for f in Op if f["pcg_p50"]]
        net_a = [f["net_p50"] for f in A.values() if f["net_p50"]]; net_o = [f["net_p50"] for f in O if f["net_p50"]]
        # free RAM at container start (user median), by memory band
        def fr(g):
            v = [f["free_mb"] for f in g if f["free_mb"] is not None]
            return {"n": len(v), "median_mb": round(st.median(v)) if v else None, "under_1gb": rate(sum(x < 1024 for x in v), len(v)),
                    "under_1gb_users": sum(x < 1024 for x in v), "under_2gb": rate(sum(x < 2048 for x in v), len(v))} if v else {"n": 0}
        bands = {"8 GB or less": lambda f: f["ram"] and f["ram"] <= 8, "12 GB": lambda f: f["ram"] and 8 < f["ram"] <= 12,
                 "16 GB": lambda f: f["ram"] and 12 < f["ram"] <= 16, "20 GB+": lambda f: f["ram"] and f["ram"] > 16,
                 # 1.2.1: two-band split at 16 GB, same cut as the le12/ge16 population counts
                 "Under 16 GB": lambda f: f["ram"] and f["ram"] <= 12, "16 GB and above": lambda f: f["ram"] and f["ram"] > 12}
        free_ram = {"all": {"acct": fr(A.values()), "others": fr(O)}}
        for bn, bf in bands.items():
            ga = [f for f in A.values() if bf(f)]; go = [f for f in O if bf(f)]
            free_ram[bn] = {"acct": fr(ga), "others": fr(go),
                            "swap_if_under_1gb": {"acct": rate(sum(f["swap"] for f in ga if (f["free_mb"] or 9e9) < 1024), sum(1 for f in ga if (f["free_mb"] or 9e9) < 1024)),
                                                  "others": rate(sum(f["swap"] for f in go if (f["free_mb"] or 9e9) < 1024), sum(1 for f in go if (f["free_mb"] or 9e9) < 1024))}}
        # apps launched inside Blue Border: share of scored users who launched each app at least once
        ua = defaultdict(set); uo = defaultdict(set); launches = Counter(); web = Counter()
        for r in APPS:
            if r["U"] in A: ua[r["App"]].add(r["U"]); launches[r["App"]] += r["Launches"]; web[r["App"]] += r["Web"]
            elif r["U"] in cu and r["Acct"] not in accts: uo[r["App"]].add(r["U"])
        apps = [{"app": k, "acct_users": len(v), "acct_pct": rate(len(v), len(A)), "others_pct": rate(len(uo.get(k, ())), len(O)),
                 "launches": launches[k], "via_browser": round(100 * web[k] / launches[k]) if launches[k] else 0}
                for k, v in sorted(ua.items(), key=lambda z: -len(z[1]))[:15]]
        report = {"account": acct, "week": week.isoformat(), "period": [d.isoformat() for d in cur], "prior": [d.isoformat() for d in prev],
                  "population": {"scored": len(A), "scored_prev": len(Ap), "others": len(O), "le12": len(lo12), "ge16": len(hi16)},
                  "params": params, "lines": {"cur": cl, "prev": pl},
                  "latency": {"bands_cur": {"acct": band_split(lat_a), "others": band_split(lat_o)},
                              "bands_prev": {"acct": band_split(lat_ap), "others": band_split(lat_op)},
                              "internet_med": {"acct": round(st.median(net_a)) if net_a else None, "others": round(st.median(net_o)) if net_o else None},
                              "country": ctab},
                  "connectivity": conn, "free_ram": free_ram, "apps": apps, "cores": cores, "cores_known": cores_known,
                  "named": {"any_now": sum(1 for f in A.values() if any(f[k] for k in GROUP)), "persistent_any": len(named),
                            "multi": multi, "connectivity_only_both": [x["user"] for x in conn_only], "persistent_list": named,
                            "first_period": no_prior, "now_list": now_list},
                  "run_id": run_id, "version": VERSION, "checks": checks}
        report_docs.append({"collection": "reports", "doc_id": f"{acct}__{week.isoformat()}", "data": report})
        # facts for the insight writer: latest 5 weekly measures + period headline numbers
        wk_docs = [d["data"] for d in weeks_docs if d["data"]["account"] == acct]
        facts = {"account": acct, "week": week.isoformat(), "weekly": [{"week": d["week"], **{k: d["measures"][k] for k in ("swap", "net", "gw", "frozen", "roam", "lat_ms")}} for d in wk_docs],
                 "period": {k: params[k] for k in ("swap", "net", "gw", "frozen", "latency", "launch", "roam")}, "population": report["population"],
                 "named": {"first_period": no_prior, "flagged_now": len(now_list),
                           "persistent_any": None if no_prior else len(named), "multi": None if no_prior else len(multi), "connectivity_only_both": None if no_prior else len(conn_only)},
                 "latency_internet_med": report["latency"]["internet_med"], "country": ctab[:6],
                 "free_ram": free_ram, "apps": apps[:10]}
        json.dump(facts, open(os.path.join(a.out, f"facts_{acct}.json"), "w", encoding="utf-8"), indent=1)
        last = wk_docs[-1]["measures"] if wk_docs else {}
        feed.append({"week": week.isoformat(), "account": acct, "scored_users": len(A),
                     "swap_pct": last.get("swap", {}).get("acct"), "swap_others": last.get("swap", {}).get("others"),
                     "net_drop_pct": last.get("net", {}).get("acct"), "gw_drop_pct": last.get("gw", {}).get("acct"),
                     "frozen_pct": last.get("frozen", {}).get("acct"), "frozen_others": last.get("frozen", {}).get("others"),
                     "latency_avg_ms": last.get("lat_ms", {}).get("acct"), "latency_avg_others": last.get("lat_ms", {}).get("others"),
                     "named_persistent": "" if no_prior else len(named), "named_multi": "" if no_prior else len(multi), "run_id": run_id})

    json.dump({"docs": weeks_docs}, open(os.path.join(a.out, "weeks.json"), "w", encoding="utf-8"))
    json.dump({"docs": report_docs}, open(os.path.join(a.out, "reports.json"), "w", encoding="utf-8"))
    # one file per document + manifest, for ArtifactData batch entries {op:"set", collection, doc_id, file_path}
    manifest = []
    for d in weeks_docs + report_docs:
        p = os.path.abspath(os.path.join(a.out, "docs", d["collection"], d["doc_id"] + ".json"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: json.dump(d["data"], f, separators=(",", ":"))
        manifest.append({"collection": d["collection"], "doc_id": d["doc_id"], "file_path": p, "bytes": os.path.getsize(p)})
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8"), indent=1)
    too_big = [m for m in manifest if m["bytes"] > 250_000]
    if too_big: print(f"WARNING: documents over 250 KB: {[m['doc_id'] for m in too_big]}", file=sys.stderr)
    if feed:
        with open(os.path.join(a.out, "feed.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(feed[0])); w.writeheader(); w.writerows(feed)
    run = {"run_id": run_id, "version": VERSION, "week": week.isoformat(), "period": [str(d) for d in cur], "prior": [str(d) for d in prev],
           "accounts": accts, "checks": checks, "check_failures": bad, "timings_s": TIMINGS, "cached": CACHED,
           "docs": {"weeks": len(weeks_docs), "reports": len(report_docs)}}
    json.dump(run, open(os.path.join(a.out, "run.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: run[k] for k in ("run_id", "week", "docs", "check_failures")}), flush=True)
    if bad: print("COMPLETENESS FAILED: row counts differ from exact scalars", file=sys.stderr); sys.exit(2)

if __name__ == "__main__":
    main()
