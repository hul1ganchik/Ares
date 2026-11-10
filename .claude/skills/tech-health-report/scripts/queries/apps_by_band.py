"""Apps in use by memory group and by swapping flag, one account vs other customers, plus a closer look at one app.
Reads runs/why8_<ws>_<we>.json (apps = launched inside Blue Border; what runs outside is not in telemetry).
Scored users: 5+ days, 50+ Session Score readings. Bands split at 16 GB, the same rule as swap_by_band_weekly.py.
For the focus app (optional, from accounts/<key>.json) also: who runs it, when it starts against container start,
and, within each user, readings above 500 hard faults/s in the 2 hours after a launch against the rest of the same days.
Usage: python -I apps_by_band.py <account> <ws> <we> <why8.json> <out.json> [focus app]"""
import json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q
acct, ws, we, w8, out = sys.argv[1:6]; FOCUS = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else None
D = json.load(open(w8, encoding="utf-8"))
S = {(r["U"], r["Acct"]): r for r in D["start"]}
A = {(r["U"], r["Acct"]): (r["Apps"] if isinstance(r["Apps"], dict) else json.loads(r["Apps"])) for r in D["apps"]}
BANDS = ["Under 16 GB", "16 GB and above"]
U = []
for r in D["ss"]:
    k = (r["U"], r["Acct"]); s = S.get(k)
    if not s or not s.get("TotMiB") or (r["N"] or 0) < 50 or (r["Days"] or 0) < 5: continue
    gb = s["TotMiB"] / 1024
    U.append({"u": k[0], "acct": k[1] == acct, "band": BANDS[0] if gb <= 12.3 else BANDS[1], "gb": round(gb, 1), "free_mb": s.get("AvP50"),
              "swap": r["HF500"] / r["N"] >= 0.5 or r["HF2000"] / r["N"] >= 0.25, "days": r["Days"], "apps": A.get(k, {})})
rate = lambda g: 100 * sum(x["swap"] for x in g) / len(g) if g else None
res = {"window": [ws, we], "focus": FOCUS, "bands": {}}
L = [x for x in U if x["acct"]]
top = [a for a, _ in Counter(a for x in L for a in x["apps"]).most_common(12)]   # same app list for both groups
if any(FOCUS in x["apps"] for x in L) and FOCUS not in top: top.append(FOCUS)
for b in BANDS:
    g = [x for x in L if x["band"] == b]; og = [x for x in U if not x["acct"] and x["band"] == b]
    fl = [x for x in g if x["swap"]]; nf = [x for x in g if not x["swap"]]
    share = lambda grp, a: 100 * sum(a in x["apps"] for x in grp) / len(grp) if grp else None
    rows = [{"app": a, "users": sum(a in x["apps"] for x in g), "flagged_pct": share(fl, a), "not_flagged_pct": share(nf, a),
             "flag_with": rate([x for x in g if a in x["apps"]]), "flag_without": rate([x for x in g if a not in x["apps"]]), "others_pct": share(og, a)} for a in top]
    res["bands"][b] = {"users": len(g), "flagged": len(fl), "not_flagged": len(nf), "flag_rate": rate(g), "others_flag_rate": rate(og), "apps": rows}
if not FOCUS:
    res["focus_users"] = []; json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
    print(f"apps_by_band: {sum(v['users'] for v in res['bands'].values())} users; no focus app -> {out}"); sys.exit(0)
# focus app: who, timing, within-user
F = [x for x in U if x["acct"] and FOCUS in x["apps"]]
res["focus_users"] = sorted(({"u": x["u"], "band": x["band"], "gb": x["gb"], "free_mb": x["free_mb"], "flagged": x["swap"], "launches": x["apps"][FOCUS]}
                             for x in F), key=lambda r: (not r["flagged"], r["band"] != BANDS[0], -r["launches"]))
BASE = f"""let ws = datetime({ws}); let we = datetime({we});
let base = AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct == '{acct}' | extend U = tolower(UserAuthenticatedId);
let d = base | where Name == 'App launched' and tostring(Properties.appName) == '{FOCUS}';
"""
t = q(BASE + """let st = base | where Name == 'Container started' | project ST = TimeGenerated, SessionId;
d | join kind=leftouter st on SessionId | extend Min = datetime_diff('minute', TimeGenerated, ST)
| summarize Launches=count(), Users=dcount(U), UserDays=dcount(strcat(U, format_datetime(TimeGenerated,'yyyy-MM-dd'))), Within10=countif(Min between (0 .. 10)),
  T50=percentile(todouble(Measurements.timeToLaunchApp),50), Paths=make_set(tostring(Properties.appPath), 3)""")[0]
res["focus_launch"] = {"launches": t["Launches"], "users": t["Users"], "user_days": t["UserDays"], "within10_pct": 100 * t["Within10"] / t["Launches"] if t["Launches"] else None,
                       "launch_ms_p50": t["T50"], "paths": json.loads(t["Paths"]) if isinstance(t["Paths"], str) else t["Paths"]}
W = q(BASE + """let dd = d | project U, DT = TimeGenerated, Day = startofday(TimeGenerated);
base | where Name == 'Session Score' and U in ((dd | distinct U)) | extend HF = todouble(Measurements['Device.memoryHardFaults'])
| project U, T = TimeGenerated, Day = startofday(TimeGenerated), HF
| join kind=inner (dd | distinct U, Day) on U, Day | join kind=leftouter (dd | project U, DT) on U
| summarize After = max(toint(T >= DT and T < DT + 2h)) by U, T, HF
| summarize N=count(), HF500=countif(HF>=500) by U, After""")
per = {}
for r in W: per.setdefault(r["U"], {})[r["After"]] = r
pairs = [(v[1], v[0]) for v in per.values() if 1 in v and 0 in v and v[1]["N"] >= 6 and v[0]["N"] >= 6]
if pairs:
    sh = lambda p: p["HF500"] / p["N"]
    res["focus_within_user"] = {"users": len(pairs), "after_pct": 100 * sum(a["HF500"] for a, _ in pairs) / sum(a["N"] for a, _ in pairs),
                                "rest_pct": 100 * sum(b["HF500"] for _, b in pairs) / sum(b["N"] for _, b in pairs),
                                "higher": sum(sh(a) > sh(b) + .05 for a, b in pairs), "lower": sum(sh(a) < sh(b) - .05 for a, b in pairs)}
json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
print(f"apps_by_band: {sum(v['users'] for v in res['bands'].values())} users; {FOCUS}: {len(F)} users -> {out}")
