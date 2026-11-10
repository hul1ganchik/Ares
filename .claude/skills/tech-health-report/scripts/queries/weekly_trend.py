"""Weekly trend per measure: account rate vs other customers, from runs/weekly_8w_<end>.json.
Usage: python weekly_trend.py <account> <weekly json> <out json>"""
import datetime as dt, json, sys
from collections import defaultdict
acct, src, out = sys.argv[1:4]
D = json.load(open(src, encoding="utf-8")); end = dt.date.fromisoformat(D["end"]); W = D["weeks"]
MIN_N, MIN_DAYS, MIN_HOURS = 50, 3, 10

def p90(v): v = sorted(v); return v[int(0.9 * (len(v) - 1))] if v else None
ss = defaultdict(list); ro = defaultdict(list)
for r in D["ss"]:
    if (r["N"] or 0) >= MIN_N and (r["Days"] or 0) >= MIN_DAYS: ss[r["Wk"]].append(r)
for r in D["roam"]:
    if (r["Hours"] or 0) >= MIN_HOURS: ro[r["Wk"]].append(r)

MEAS = ["swap", "net", "gw", "roam", "frozen", "latency", "lat_ms"]
res = {m: [] for m in MEAS}; weeks = []
for wk in range(W - 1, -1, -1):
    start = end - dt.timedelta(days=7 * (wk + 1)); weeks.append(start.isoformat())
    rows = ss[wk]; oth = [r for r in rows if r["Acct"] != acct]
    nl = p90([r["Nd1"] / r["N"] for r in oth]); gl = p90([r["Pd1"] / r["N"] for r in oth])
    f = {"swap": lambda r: r["HF500"] / r["N"] >= 0.5 or r["HF2000"] / r["N"] >= 0.25,
         "net": lambda r: r["Nd1"] / r["N"] > nl, "gw": lambda r: r["Pd1"] / r["N"] > gl,
         "frozen": lambda r: r["Fz1"] / r["N"] >= 0.05,
         "latency": lambda r: (r["PcgN"] or 0) >= 30 and (r["PcgP50"] or 0) >= 250}
    for m, fn in f.items():
        a = [r for r in rows if r["Acct"] == acct]; b = oth
        res[m].append({"wk": start.isoformat(), "n": len(a), "acct": round(100 * sum(map(fn, a)) / len(a), 1) if a else None,
                       "others": round(100 * sum(map(fn, b)) / len(b), 1), "users": sum(map(fn, a))})
    import statistics as st
    la = [r["PcgP50"] for r in rows if r["Acct"] == acct and (r["PcgN"] or 0) >= 30 and r["PcgP50"]]
    lo = [r["PcgP50"] for r in oth if (r["PcgN"] or 0) >= 30 and r["PcgP50"]]
    res["lat_ms"].append({"wk": start.isoformat(), "n": len(la), "acct": round(st.mean(la)) if la else None, "others": round(st.mean(lo)),
                          "acct_med": round(st.median(la)) if la else None, "others_med": round(st.median(lo)), "users": len(la)})
    rr = ro[wk]; rl = p90([r["RoamHours"] / r["Hours"] for r in rr if r["Acct"] != acct])
    a = [r for r in rr if r["Acct"] == acct]; b = [r for r in rr if r["Acct"] != acct]
    fn = lambda r: r["RoamHours"] / r["Hours"] > rl
    res["roam"].append({"wk": start.isoformat(), "n": len(a), "acct": round(100 * sum(map(fn, a)) / len(a), 1) if a else None,
                        "others": round(100 * sum(map(fn, b)) / len(b), 1), "users": sum(map(fn, a))})
json.dump({"account": acct, "end": D["end"], "weeks": weeks, "series": res}, open(out, "w", encoding="utf-8"), indent=1)
for m in MEAS:
    print(f"{m:8}", "  ".join(f"{'-' if p['acct'] is None else p['acct']:>5}/{p['others']:<5}" for p in res[m]))
print("weeks start:", weeks); print("n per week:", [p["n"] for p in res["swap"]])
