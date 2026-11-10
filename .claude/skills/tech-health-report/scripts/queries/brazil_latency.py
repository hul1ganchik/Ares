"""Gateway latency before vs after the Brazil gateway pair (added 2026-09-21 15:45 UTC), one account.
Source: PCG health probes (AppTraces 'PCG health': 'Latency: N' and the gateway 'PublicIp'), so latency and the gateway
it was measured to come from the same line. Site = /24 of the gateway IP, named from the account notes' pcg_groups (accounts/<account>.json in the data folder).
Before = 2026-08-22 .. 2026-09-21 15:00 UTC; after = 2026-09-22 12:00 UTC .. <we> (transition excluded).
Also weekly per-user medians (account vs other customers) for a trend line.
Writes <account>/brazil_latency.json. Usage: python -I brazil_latency.py <we> <account>"""
import json, os, shutil, statistics as st, subprocess, sys, tempfile
WS = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"
WE, ACCT = sys.argv[1], sys.argv[2]
_root = os.environ.get("TH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _sites():  # /24 of each gateway IP -> short region name ("South America (Brazil)" -> "Brazil"); non-default groups get ", <group> group"
    notes = json.load(open(os.path.join(_root, "accounts", ACCT + ".json"), encoding="utf-8")); s = {}
    for i, g in enumerate(notes.get("pcg_groups") or []):
        for r in g["regions"]:
            name = r["region"][r["region"].find("(") + 1:].rstrip(")") if "(" in r["region"] else r["region"]
            for ip in r["ips"]: s.setdefault(ip.rsplit(".", 1)[0], name if i == 0 else f"{name}, {g['group']} group")
    if not s: sys.exit("brazil_latency: no pcg_groups in the account notes")
    return s
SITES = _sites()
PER_USER = r"""
AppTraces
| where TimeGenerated >= datetime(2026-08-22) and TimeGenerated < datetime({we}) and Message has 'PCG health'
| where tolower(tostring(Properties.Account)) == '{acct}'
| where not(TimeGenerated between (datetime(2026-09-21 15:00) .. datetime(2026-09-22 12:00)))
| extend P = iff(TimeGenerated < datetime(2026-09-21 15:00), 'before', 'after')
| extend L = todouble(extract(@'Latency:\s*([0-9]+)', 1, Message)), Site = extract(@'PublicIp:\s*([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+', 1, Message)
| where L > 0 and L < 999
| summarize N=count(), P50=percentile(L, 50) by U=tolower(UserAuthenticatedId), P, Site
"""
WEEKLY = r"""
AppTraces
| where TimeGenerated >= datetime(2026-08-17) and TimeGenerated < datetime({we}) and Message has 'PCG health'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33'
| extend L = todouble(extract(@'Latency:\s*([0-9]+)', 1, Message)) | where L > 0 and L < 999
| summarize N=count(), P50=percentile(L, 50) by U=tolower(UserAuthenticatedId), G=iff(Acct == '{acct}', 'acct', 'others'), Wk=startofweek(TimeGenerated, 1)
| where N >= 20
| summarize Users=count(), Avg=avg(P50), Med=percentile(P50, 50) by G, Wk
| order by Wk asc
"""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

rows = q(PER_USER.format(we=WE, acct=ACCT)); weekly = q(WEEKLY.format(we=WE, acct=ACCT))
U = {}
for r in rows:
    u = U.setdefault(r["U"], {"before": {}, "after": {}}); u[r["P"]][SITES.get(r["Site"], r["Site"] or "unknown")] = (r["N"], r["P50"])
def main(d):  # dominant site + weighted median approximation (median of the dominant site's probes)
    if not d: return None
    s = max(d, key=lambda k: d[k][0]); n = sum(v[0] for v in d.values())
    return s, d[s][1], d[s][0] / n, n
both = {u: (main(v["before"]), main(v["after"])) for u, v in U.items() if main(v["before"]) and main(v["after"])
        and main(v["before"])[3] >= 50 and main(v["after"])[3] >= 50}
moved = {u: ba for u, ba in both.items() if ba[1][0] == "Brazil" and ba[0][0] != "Brazil"}
stay = {u: ba for u, ba in both.items() if ba[1][0] != "Brazil"}
def summ(g):
    if not g: return None
    b = [ba[0][1] for ba in g.values()]; a = [ba[1][1] for ba in g.values()]; d = [ba[1][1] - ba[0][1] for ba in g.values()]
    return {"users": len(g), "before_med": round(st.median(b)), "after_med": round(st.median(a)), "before_avg": round(st.mean(b)), "after_avg": round(st.mean(a)),
            "change_med": round(st.median(d)), "improved_20ms": sum(x <= -20 for x in d), "worse_20ms": sum(x >= 20 for x in d),
            "from_sites": dict(sorted({s: sum(1 for ba in g.values() if ba[0][0] == s) for s in {ba[0][0] for ba in g.values()}}.items(), key=lambda z: -z[1]))}
out = {"window": ["2026-08-22", WE], "brazil_live_utc": "2026-09-21T15:45", "account": ACCT,
       "moved_to_brazil": summ(moved), "did_not_move": summ(stay), "all_users": summ(both),
       "after_site_mix": {}, "weekly": weekly,
       "moved_users": sorted([{"u": u, "before_site": ba[0][0], "before_ms": round(ba[0][1]), "after_ms": round(ba[1][1])} for u, ba in moved.items()], key=lambda r: r["after_ms"] - r["before_ms"])}
for ba in both.values(): out["after_site_mix"][ba[1][0]] = out["after_site_mix"].get(ba[1][0], 0) + 1
root = os.environ.get("TH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # data folder (runs/, <account>/); build_indepth sets TH_HOME
json.dump(out, open(os.path.join(root, ACCT, "brazil_latency.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k not in ("moved_users", "weekly")}, indent=1))
for w in weekly: print(w)
print("biggest gains:", out["moved_users"][:5]); print("worst:", out["moved_users"][-3:])
