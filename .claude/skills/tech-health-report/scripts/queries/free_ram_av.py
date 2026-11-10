"""Free RAM at container start + security-product sets, one account vs other customers (os33 excluded).
Reads runs/why8_<ws>_<we>.json (why_8gb.py) and runs/av_sets_<ws>_<we>.json (av_sets.kql), one row per user.
Scored users: 5+ days and 50+ Session Score readings. Swapping = same line as the page (>=500 hard faults on half
the readings, or >=2000 on a quarter). Writes <account>/free_ram_av.json and prints the tables.
Usage: python -I free_ram_av.py <ws> <we> [account]"""
import json, os, statistics as st, sys
from collections import Counter, defaultdict
ws, we = sys.argv[1:3]; ACCT = sys.argv[3]
root = os.environ.get("TH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # data folder (runs/, <account>/); build_indepth sets TH_HOME
D = json.load(open(os.path.join(root, "runs", f"why8_{ws}_{we}.json"), encoding="utf-8"))
AVS = {(r["U"], r["Acct"]): r for r in json.load(open(os.path.join(root, "runs", f"av_sets_{ws}_{we}.json"), encoding="utf-8"))}
S = {(r["U"], r["Acct"]): r for r in D["start"]}; SS = {(r["U"], r["Acct"]): r for r in D["ss"]}

def band(r):
    m = r.get("TotMiB")
    if not m: return None
    gb = m / 1024; tol = 2.5 if "AMD" in (r.get("Cpu") or "") else 1.0
    if gb <= 8 + 0.3: return "8 GB or less"
    if 12 - tol <= gb <= 12 + 0.3: return "12 GB"
    if gb <= 16 + 0.3: return "16 GB"
    return "20 GB+"
FAM = [("mcafee", "McAfee"), ("crowdstrike", "CrowdStrike"), ("sentinel", "SentinelOne"), ("avast", "Avast"), ("avg", "AVG"), ("norton", "Norton"),
       ("kaspersky", "Kaspersky"), ("eset", "ESET"), ("bitdefender", "Bitdefender"), ("sophos", "Sophos"), ("trend micro", "Trend Micro"), ("apex one", "Trend Micro"),
       ("webroot", "Webroot"), ("malwarebytes", "Malwarebytes"), ("cylance", "Cylance"), ("360 total", "360 Total Security"), ("avira", "Avira"),
       ("hp wolf", "HP Wolf"), ("datto", "Datto AV"), ("forticlient", "FortiClient"), ("defender", "Defender"), ("windows security", "Defender")]
def fam(p):
    s = p.lower()
    for k, n in FAM:
        if k in s: return n
    return "other: " + p
def prods(r):
    p = r["Products"] if isinstance(r["Products"], list) else json.loads(r["Products"] or "[]")
    return sorted({fam(x) for x in p})

users = []
for k, s in S.items():
    ss = SS.get(k)
    if not ss or (ss["Days"] or 0) < 5 or (ss["N"] or 0) < 50 or s.get("AvP50") is None: continue
    av = AVS.get(k); ps = prods(av) if av else []
    third = [p for p in ps if p != "Defender"]
    users.append({"u": k[0], "acct": k[1] == ACCT, "band": band(s), "free": s["AvP50"], "swap": ss["HF500"] / ss["N"] >= 0.5 or ss["HF2000"] / ss["N"] >= 0.25,
                  "prods": ps, "third": third, "n_prod": len(ps), "known": av is not None})
users = [x for x in users if x["band"]]
L = [x for x in users if x["acct"]]; O = [x for x in users if not x["acct"]]
pc = lambda a, b: round(100 * a / b, 1) if b else None
sw = lambda g: pc(sum(x["swap"] for x in g), len(g))
out = {"window": [ws, we], "account": ACCT, "n_acct": len(L), "n_other": len(O)}

# ---- A) free RAM at start by memory band
BANDS = ["8 GB or less", "12 GB", "16 GB", "20 GB+"]
def fr(g):
    if not g: return None
    lo = [x for x in g if x["free"] < 1024]; hi = [x for x in g if x["free"] >= 1024]
    return {"n": len(g), "median_mb": round(st.median(x["free"] for x in g)), "pct_under_1gb": pc(len(lo), len(g)),
            "pct_under_2gb": pc(sum(x["free"] < 2048 for x in g), len(g)), "swap_under_1gb": sw(lo), "n_under_1gb": len(lo),
            "swap_1gb_plus": sw(hi), "n_1gb_plus": len(hi)}
A = {b: {"acct": fr([x for x in L if x["band"] == b]), "other": fr([x for x in O if x["band"] == b])} for b in BANDS}
A["all"] = {"acct": fr(L), "other": fr(O)}
out["free_ram"] = A
print(f"A) FREE RAM AT CONTAINER START (user median), {ACCT} vs other customers, {ws}..{we}")
for b in BANDS + ["all"]:
    a, o = A[b]["acct"], A[b]["other"]
    if not a or not o:
        print(f"  {b:13} n {a['n'] if a else 0:4}/{o['n'] if o else 0:5}  (no users)"); continue
    print(f"  {b:13} n {a['n']:4}/{o['n']:5}  median {a['median_mb']:5}/{o['median_mb']:5} MB  <1GB {a['pct_under_1gb']:5}/{o['pct_under_1gb']:5}%  <2GB {a['pct_under_2gb']}/{o['pct_under_2gb']}%"
          f"  swap if <1GB {a['swap_under_1gb']}/{o['swap_under_1gb']}%  if 1GB+ {a['swap_1gb_plus']}/{o['swap_1gb_plus']}%")

# ---- B) security products
def prof(g):
    n = len(g); c = Counter(p for x in g for p in x["prods"]); m = Counter(len(x["prods"]) for x in g)
    combos = Counter(" + ".join(x["prods"]) for x in g if len(x["prods"]) >= 2)
    return {"n": n, "known": sum(x["known"] for x in g), "product_pct": {k: pc(v, n) for k, v in c.most_common()},
            "product_n": dict(c.most_common()), "two_plus_pct": pc(sum(len(x["prods"]) >= 2 for x in g), n),
            "three_plus_pct": pc(sum(len(x["prods"]) >= 3 for x in g), n), "two_third_party_pct": pc(sum(len(x["third"]) >= 2 for x in g), n),
            "combos": combos.most_common(15)}
print("\nB) SECURITY PRODUCTS (one row per user; Defender listed alongside a third-party product counts as a product)")
for label, flt in [("8 GB or less", lambda x: x["band"] == "8 GB or less"), ("all bands", lambda x: True)]:
    LL = [x for x in L if flt(x)]; OO = [x for x in O if flt(x)]
    sec = {}
    for grp, g in [("acct_swappers", [x for x in LL if x["swap"]]), ("acct_non", [x for x in LL if not x["swap"]]),
                   ("other_swappers", [x for x in OO if x["swap"]]), ("other_non", [x for x in OO if not x["swap"]])]:
        sec[grp] = prof(g)
    out["security_" + label] = sec
    print(f"\n  [{label}] swappers {ACCT} n={sec['acct_swappers']['n']} non={sec['acct_non']['n']}; other swappers n={sec['other_swappers']['n']} non={sec['other_non']['n']}")
    keys = sorted({k for v in sec.values() for k in v["product_n"]}, key=lambda k: -(sec["acct_swappers"]["product_n"].get(k, 0) * 50 + sec["other_swappers"]["product_n"].get(k, 0)))
    print(f"    {'product':22} {'acct swap':>10} {'acct non':>9} {'oth swap':>9} {'oth non':>8}")
    for k in keys:
        if sum(v["product_n"].get(k, 0) for v in sec.values()) < 20 and not any(sec[g]["product_n"].get(k) for g in ("acct_swappers", "acct_non")): continue
        print(f"    {k:22} " + " ".join(f"{(sec[g]['product_pct'].get(k) or 0):>8}%" for g in ("acct_swappers", "acct_non", "other_swappers", "other_non")))
    for m in ("two_plus_pct", "three_plus_pct", "two_third_party_pct"):
        print(f"    {m:22} " + " ".join(f"{'-' if sec[g][m] is None else sec[g][m]:>8}%" for g in ("acct_swappers", "acct_non", "other_swappers", "other_non")))
    print(f"    {ACCT} swappers' 2+ product combos:", sec["acct_swappers"]["combos"])
    print(f"    {ACCT} non-swappers' combos:", sec["acct_non"]["combos"])
    print("    other swappers' top combos:", sec["other_swappers"]["combos"][:8])

# ---- C) swap rate by product, same memory band and same free-RAM bin (8 GB only; others = reference)
print("\nC) 8 GB OR LESS: swapping rate by security product within the same free-RAM bin (other customers; account in brackets)")
fb = lambda v: "<1 GB" if v < 1024 else "1-2 GB" if v < 2048 else "2 GB+"
def grp(x):
    t = x["third"]
    if not x["known"]: return None
    if not t: return "Defender only"
    if len(t) >= 2: return "2+ third-party"
    return t[0] if t[0] in ("McAfee", "Avast", "Norton", "CrowdStrike", "SentinelOne", "AVG") else "other third-party"
C = defaultdict(dict)
for b in ("<1 GB", "1-2 GB", "2 GB+"):
    for gname in ("Defender only", "McAfee", "Avast", "Norton", "AVG", "CrowdStrike", "SentinelOne", "other third-party", "2+ third-party"):
        o = [x for x in O if x["band"] == "8 GB or less" and fb(x["free"]) == b and grp(x) == gname]
        a = [x for x in L if x["band"] == "8 GB or less" and fb(x["free"]) == b and grp(x) == gname]
        C[b][gname] = {"other_n": len(o), "other_swap": sw(o), "acct_n": len(a), "acct_swap": sw(a)}
    print(f"  free {b}: " + "; ".join(f"{g} {v['other_swap']}% n{v['other_n']} [{v['acct_swap']}% n{v['acct_n']}]" for g, v in C[b].items() if v["other_n"] >= 15 or v["acct_n"]))
out["swap_by_product_8gb"] = C
# share of the account's 8 GB swappers by product group
sw8 = [x for x in L if x["band"] == "8 GB or less" and x["swap"]]
out["acct_8gb_swappers_by_group"] = dict(Counter(grp(x) for x in sw8).most_common())
print(f"\n  {ACCT} 8 GB swappers by product group (n {len(sw8)}):", out["acct_8gb_swappers_by_group"])
osw8 = [x for x in O if x["band"] == "8 GB or less" and x["swap"]]
print(f"  other 8 GB swappers by product group (n {len(osw8)}):", dict(Counter(grp(x) for x in osw8).most_common()))
out["other_8gb_swappers_by_group"] = dict(Counter(grp(x) for x in osw8).most_common())
json.dump(out, open(os.path.join(root, ACCT, "free_ram_av.json"), "w", encoding="utf-8"), indent=1)
