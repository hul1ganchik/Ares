"""Where users connect from, and which gateway they connect to, one account against other customers.
Location = country of each user's most-used public address that fewer than 5 users of the same account share (ClientCountryOrRegion); a user with
no such address falls back to their most-used one, and if 20+ users share it they go in a "shared address" row.
Gateway = the PublicIp on the user's PCG health probes, per hour; hours that touched two gateways are dropped.
Each user's main gateway = the one with most connected hours (probe counts run fast while a tunnel is sick, so they
over-weight a bad gateway). Latency = median Session Score pcgLatency over the hours on that gateway (probes report
latency only when they answer, which some accounts' rarely do). Users need 10+ hours with a score.
Region names come from pcg_groups in accounts/<acct>.json (the account's Admin Portal gateway list), else <acct>/gateways.json, else the gateway's /24.
Gateways the account reached that the list doesn't name are printed and written as unlisted_gateways, so the list can be checked.
Usage: python -I gateway_by_location.py <account> <ws> <we> <out.json>"""
import collections, json, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

SHARED_IP_USERS, MIN_HOURS, MIN_USERS = 20, 10, 5
KQL = r"""
let ws = datetime({ws}); let we = datetime({we});
let ev = AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId);
let ipb = ev | where isnotempty(ClientIP) and ClientIP != '0.0.0.0';
let ipusers = ipb | summarize IpUsers = dcount(U) by ClientIP;
let ipacct = ipb | summarize AcctIpUsers = dcount(U) by ClientIP, Acct;
let home = ipb | summarize E = count(), Country = take_any(ClientCountryOrRegion) by U, Acct, ClientIP
| join kind=inner ipusers on ClientIP | join kind=inner ipacct on ClientIP, Acct | extend R = iff(AcctIpUsers < 5, 1e12, 0.0) + E
| summarize arg_max(R, Country, IpUsers) by U, Acct | project U, Acct, Country, Shared = IpUsers >= {shared};
let ss = ev | where Name == 'Session Score' | extend Pcg = todouble(Measurements['Container.pcgLatency'])
| where Pcg > 0 and Pcg < 999 | summarize HP50 = percentile(Pcg, 50) by U, Acct, H = bin(TimeGenerated, 1h);
AppTraces | where TimeGenerated >= ws and TimeGenerated < we and Message has 'PCG health'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId), Gw = extract(@'PublicIp:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)', 1, Message)
| where isnotempty(Gw)
| summarize Gws = make_set(Gw, 4) by U, Acct, H = bin(TimeGenerated, 1h) | where array_length(Gws) == 1 | extend Gw = tostring(Gws[0])
| join kind=leftouter ss on U, Acct, H
| summarize Hours = count(), SsHours = countif(isnotnull(HP50)), P50 = percentile(HP50, 50) by U, Acct, Gw
| join kind=inner home on U, Acct
| project U, Acct, Country, Shared, Gw, Hours, SsHours, P50
"""

acct, ws, we, out = sys.argv[1:5]
root = os.environ.get("TH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # data folder (runs/, <account>/); build_indepth sets TH_HOME
ap_ = os.path.join(root, "accounts", f"{acct}.json"); gp = os.path.join(root, acct, "gateways.json")   # notes file first, older per-account file second
plan = ({"groups": json.load(open(ap_, encoding="utf-8")).get("pcg_groups")} if os.path.exists(ap_) else None) or None
if not (plan and plan["groups"]): plan = json.load(open(gp, encoding="utf-8")) if os.path.exists(gp) else None
if not plan: print(f"No PCG gateway list for {acct}: gateways named by IP prefix. Add pcg_groups to accounts/{acct}.json.")
# the first group is the account default; regions in other groups carry the group name, since a group limits its users to its own regions
G0 = ((plan or {}).get("groups") or [{}])[0].get("group")
ipname = {ip: (g["group"], r["region"] if g["group"] == G0 else f'{r["region"]}, {g["group"]} group') for g in (plan or {}).get("groups", []) for r in g["regions"] for ip in r["ips"]}
def gname(ip):
    if ip in ipname: return ipname[ip]
    return (None, ".".join(ip.split(".")[:3]) + ".x")

rows = q(KQL.format(ws=ws, we=we, shared=SHARED_IP_USERS))
U = {}
for r in rows:
    u = U.setdefault((r["U"], r["Acct"]), {"acct": r["Acct"], "loc": "Shared address" if r["Shared"] else (r["Country"] or "Unknown"), "gw": {}})
    u["gw"][r["Gw"]] = (r["Hours"], r["P50"] if r["SsHours"] else None)
users = []
for (name, a), u in U.items():
    tot = sum(v[0] for v in u["gw"].values())
    ip = max(u["gw"], key=lambda k: u["gw"][k][0])
    if u["gw"][ip][1] is None or tot < MIN_HOURS: continue
    grp, reg = gname(ip)
    users.append({"u": name, "acct": a, "loc": u["loc"], "gw_ip": ip, "group": grp, "region": reg, "ms": u["gw"][ip][1],
                  "main_share": u["gw"][ip][0] / tot, "regions_seen": len({gname(k)[1] for k in u["gw"]})})
A = [x for x in users if x["acct"] == acct]; O = [x for x in users if x["acct"] != acct]
# gateways this account reached that the notes' list doesn't name (every probe hour, before the 10-hour floor): the list may be stale or incomplete
unl = collections.defaultdict(lambda: [set(), 0])
for (name, a), u in U.items():
    if a != acct: continue
    for ip, (h, _) in u["gw"].items():
        if ip not in ipname: unl[ip][0].add(name); unl[ip][1] += h
unlisted = sorted(({"ip": ip, "users": len(v[0]), "hours": v[1]} for ip, v in unl.items()), key=lambda r: -r["hours"])
if plan and unlisted:
    print(f"PCG endpoints not on the {acct} gateway list: " + ", ".join(f'{r["ip"]} ({r["users"]} users, {r["hours"]} h)' for r in unlisted)
          + ". Check Admin Portal > Private Company Gateway and update pcg_groups.")
med = lambda v: round(st.median(v)) if v else None
band = lambda v: "250+" if v >= 250 else "200-249" if v >= 200 else "under 200"

others_by_loc = collections.defaultdict(list)
for x in O: others_by_loc[x["loc"]].append(x["ms"])
def mixof(g):  # users and median latency per gateway region, most users first
    m = collections.defaultdict(list)
    for x in g: m[x["region"]].append(x["ms"])
    return [{"region": k, "users": len(v), "median_ms": med(v)} for k, v in sorted(m.items(), key=lambda z: -len(z[1]))]
by_loc = collections.defaultdict(list)
for x in A: by_loc[x["loc"]].append(x)
locs = []
for loc, g in sorted(by_loc.items(), key=lambda z: (z[0] == "Shared address", -len(z[1]))):
    ob = others_by_loc.get(loc, [])
    locs.append({"location": loc, "users": len(g), "median_ms": med([x["ms"] for x in g]),
                 "watch_200": sum(200 <= x["ms"] < 250 for x in g), "over_250": sum(x["ms"] >= 250 for x in g),
                 "gateways": mixof(g), "others_users": len(ob), "others_median_ms": med(ob) if len(ob) >= 10 else None})
small = [l for l in locs if l["users"] < MIN_USERS and l["location"] != "Shared address"]
big = [l for l in locs if l not in small]
if small:
    g = [x for x in A if x["loc"] in {l["location"] for l in small}]
    big.append({"location": f"{len(small)} other countries", "countries": [l["location"] for l in small], "users": len(g),
                "median_ms": med([x["ms"] for x in g]), "watch_200": sum(200 <= x["ms"] < 250 for x in g), "over_250": sum(x["ms"] >= 250 for x in g),
                "gateways": mixof(g), "others_users": None, "others_median_ms": None})
big.sort(key=lambda l: (l["location"] == "Shared address", l["location"].endswith("other countries"), -l["users"]))

gws = []
order = list(dict.fromkeys(ipname.values()))
seen = collections.defaultdict(list)
for x in A: seen[(x["group"], x["region"])].append(x)
for key in order + [k for k in seen if k not in order]:
    g = seen.get(key, [])
    froms = collections.Counter(x["loc"] for x in g)
    gws.append({"group": key[0], "region": key[1], "users": len(g), "median_ms": med([x["ms"] for x in g]),
                "over_250": sum(x["ms"] >= 250 for x in g), "from": [{"location": k, "users": v} for k, v in froms.most_common(4)],
                "on_plan": key in order})
res = {"account": acct, "default_group": G0, "groups": [{"group": g["group"], "regions": len(g["regions"])} for g in (plan or {}).get("groups", [])], "window": [ws, we], "plan_source": (plan or {}).get("source"), "min_hours": MIN_HOURS, "shared_ip_users": SHARED_IP_USERS,
       "acct_users": len(A), "others_users": len(O), "acct_median_ms": med([x["ms"] for x in A]), "others_median_ms": med([x["ms"] for x in O]),
       "acct_bands": dict(collections.Counter(band(x["ms"]) for x in A)), "others_bands": dict(collections.Counter(band(x["ms"]) for x in O)),
       "multi_region_users": sum(x["regions_seen"] >= 2 for x in A), "unlisted_gateways": unlisted if plan else None,
       "locations": big, "gateways": gws,
       "slow_users": sorted([{"u": x["u"], "loc": x["loc"], "region": x["region"], "ms": round(x["ms"])} for x in A if x["ms"] >= 200], key=lambda r: -r["ms"])}
json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("locations", "gateways", "slow_users")}, indent=1))
for l in big: print(l["location"], l["users"], l["median_ms"], l["over_250"], [(g["region"], g["users"], g["median_ms"]) for g in l["gateways"][:3]], l["others_median_ms"])
for g in gws: print(g["group"], g["region"], g["users"], g["median_ms"], g["from"][:3])
print("slow:", res["slow_users"][:10])
