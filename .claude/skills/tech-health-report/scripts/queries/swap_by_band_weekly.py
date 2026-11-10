"""Weekly swapping by memory band, account vs other customers' users in the same band (for build_summary.py).
Reads the weekly json (weekly.py) and the why_8gb start table (installed RAM per user).
Usage: python -I swap_by_band_weekly.py <account> <weekly json> <why8 json> <out json>"""
import json, sys
from collections import defaultdict
acct, wsrc, rsrc, out = sys.argv[1:5]
W = json.load(open(wsrc, encoding="utf-8")); R = json.load(open(rsrc, encoding="utf-8"))
ram = {}
for r in R["start"]:
    m = r.get("TotMiB")
    if not m: continue
    gb = m / 1024; tol = 2.5 if "AMD" in (r.get("Cpu") or "") else 1.0
    ram[r["U"].lower()] = "Under 16 GB" if gb <= 12.3 else "16 GB and above"   # two bands split at 16 GB
g = defaultdict(lambda: defaultdict(list))
for r in W["ss"]:
    if (r["N"] or 0) < 50 or (r["Days"] or 0) < 3: continue
    b = ram.get(r["UserAuthenticatedId"].lower())
    if b: g[b][r["Wk"]].append(r)
sw = lambda r: r["HF500"] / r["N"] >= 0.5 or r["HF2000"] / r["N"] >= 0.25
res = {}
for b in ("Under 16 GB", "16 GB and above"):
    res[b] = []
    for wk in range(W["weeks"] - 1, -1, -1):
        a = [r for r in g[b][wk] if r["Acct"] == acct]; o = [r for r in g[b][wk] if r["Acct"] != acct]
        res[b].append({"wk": wk, "a": round(100 * sum(map(sw, a)) / len(a), 1) if a else None, "o": round(100 * sum(map(sw, o)) / len(o), 1) if o else None,
                       "n": len(a), "u": sum(map(sw, a))})
json.dump(res, open(out, "w", encoding="utf-8"), indent=1); print({b: v[-1] for b, v in res.items()})
