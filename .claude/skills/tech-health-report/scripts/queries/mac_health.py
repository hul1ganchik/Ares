"""Mac users for one account against other customers' Mac users, one 28-day window.
Macs send no Session Score, so none of the Windows measures apply. What they do send, per user:
Container started (start time, free memory and disk, RAM, chip, macOS), Container can't start, PCG disconnected,
PCG usable after wake (time to reconnect after sleep). Lines that have no product threshold are other customers' top 10%.
Usage: python -I mac_health.py <account> <ws> <we> <out.json>"""
import json, os, re, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

PU = r"""
let ws = datetime({ws}); let we = datetime({we});
let M = AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Mac'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId);
let S = M | where Name == 'Container started'
| extend FD = todouble(Measurements['SystemDriveTotalFreeSpace']), OV = tostring(Properties.OsVersion)
| summarize LastStart=arg_max(TimeGenerated, FD, OV), Starts=count(), StartP50=percentile(todouble(Measurements['timeToStart']), 50),
    FreeRamP50=percentile(todouble(Measurements['AvailablePhysicalMemory']), 50), RamMiB=max(todouble(Measurements['TotalPhysicalMemory'])),
    Chip=take_any(tostring(Properties.CpuName)), Machines=dcount(tostring(Properties.ComputerSerialNumber)) by U, Acct;
let E = M | summarize Days=dcount(startofday(TimeGenerated)), CantStart=countif(Name == "Container can't start"),
    Drops=countif(Name == 'PCG disconnected'), Wakes=countif(Name == 'PCG usable after wake'),
    WakeP50=percentile(iff(Name == 'PCG usable after wake', todouble(Measurements['durationMs']), real(null)), 50) by U, Acct;
E | join kind=leftouter S on U, Acct
| project U, Acct, Days, CantStart, Drops, Wakes, WakeP50, Starts, StartP50, FreeRamP50, RamMiB, FreeDisk=FD, Chip, Os=OV, Machines
"""
SCALAR = r"""
let ws = datetime({ws}); let we = datetime({we});
AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Mac'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| summarize by U = tolower(UserAuthenticatedId), Acct | count
"""
MIN_DAYS, FEW = 5, 20


def chip(c):
    c = c or ""
    m = re.match(r"Apple (M\d)", c)
    if m: return m.group(1)
    if c.startswith("Apple"): return "Other Apple"
    return "Intel" if "Intel" in c else "Unknown"


def ram_band(mib):
    if not mib: return None
    gb = mib / 1024
    return "8 GB" if gb <= 8.5 else "16 GB" if gb <= 16.5 else "18 GB+"


def share(rows, f):
    return round(100 * sum(1 for r in rows if f(r)) / len(rows), 1) if rows else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs)) if xs else None


def p90(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[int(0.9 * (len(xs) - 1))] if xs else None


def main():
    acct, ws, we, out = sys.argv[1:5]
    f = dict(ws=ws, we=we)
    rows = q(PU.format(**f)); total = q(SCALAR.format(**f))[0]["Count"]
    if len(rows) != total: sys.exit(f"mac_health: {len(rows)} user rows but {total} Mac users: result truncated")
    for r in rows:
        r["drops_per_day"] = (r["Drops"] or 0) / r["Days"] if r["Days"] else 0
        r["band"] = ram_band(r.get("RamMiB")); r["chip"] = chip(r.get("Chip"))
        r["os_major"] = (r.get("Os") or "").split(".")[0] or None
    A = [r for r in rows if r["Acct"] == acct]; O = [r for r in rows if r["Acct"] != acct]
    As = [r for r in A if r["Days"] >= MIN_DAYS]; Os = [r for r in O if r["Days"] >= MIN_DAYS]
    # lines with no product threshold: other customers' scored Mac users' top 10%
    line = {"start_ms": p90([r["StartP50"] for r in Os]), "wake_ms": p90([r["WakeP50"] for r in Os if (r["Wakes"] or 0) >= 10]),
            "drops_per_day": p90([r["drops_per_day"] for r in Os])}
    def measures(g):
        wk = [r for r in g if (r["Wakes"] or 0) >= 10]; st_ = [r for r in g if r["StartP50"] is not None]
        dk = [r for r in g if r["FreeDisk"] is not None]
        return {"users": len(g),
                "start_med_ms": med([r["StartP50"] for r in st_]), "slow_start": share(st_, lambda r: r["StartP50"] > line["start_ms"]),
                "cant_start": share(g, lambda r: (r["CantStart"] or 0) > 0),
                "drops_med_per_day": round(st.median([r["drops_per_day"] for r in g]), 2) if g else None,
                "many_drops": share(g, lambda r: r["drops_per_day"] > line["drops_per_day"]),
                "wake_users": len(wk), "wake_med_ms": med([r["WakeP50"] for r in wk]), "slow_wake": share(wk, lambda r: r["WakeP50"] > line["wake_ms"]),
                "low_disk": share(dk, lambda r: r["FreeDisk"] < 10)}
    def makeup(g, key, order):
        k = [r for r in g if r[key]]
        return {v: {"n": sum(1 for r in k if r[key] == v), "pct": share(k, lambda r, v=v: r[key] == v)} for v in order}
    def free_mem(g):
        res = {}
        for b in ("8 GB", "16 GB", "18 GB+"):
            x = [r for r in g if r["band"] == b and r["FreeRamP50"] is not None]
            res[b] = {"n": len(x), "median_mb": med([r["FreeRamP50"] for r in x]), "under_1gb": share(x, lambda r: r["FreeRamP50"] < 1024)}
        return res
    chips = ["M1", "M2", "M3", "M4", "M5", "Other Apple", "Intel"]
    oss = sorted({r["os_major"] for r in rows if r["os_major"]}, key=lambda v: -int(v) if v.isdigit() else 0)
    flagged = []
    for r in As:
        fl = [k for k, ok in (("slow_start", r["StartP50"] is not None and r["StartP50"] > line["start_ms"]),
                              ("cant_start", (r["CantStart"] or 0) > 0), ("many_drops", r["drops_per_day"] > line["drops_per_day"]),
                              ("slow_wake", (r["Wakes"] or 0) >= 10 and r["WakeP50"] > line["wake_ms"]),
                              ("low_disk", r["FreeDisk"] is not None and r["FreeDisk"] < 10)) if ok]
        if fl: flagged.append({"user": r["U"], "flags": fl, "ram": r["band"], "chip": r["chip"], "os": r["os_major"], "days": r["Days"]})
    flagged.sort(key=lambda x: (-len(x["flags"]), x["user"]))
    res = {"account": acct, "window": [ws, we], "min_days": MIN_DAYS, "few": FEW, "lines": line,
           "population": {"acct_all": len(A), "acct_scored": len(As), "others_all": len(O), "others_scored": len(Os),
                          "acct_machines": sum(r.get("Machines") or 0 for r in A)},
           "measures": {"acct": measures(As), "others": measures(Os)},
           "makeup": {"chip": {"acct": makeup(A, "chip", chips), "others": makeup(O, "chip", chips)},
                      "ram": {"acct": makeup(A, "band", ["8 GB", "16 GB", "18 GB+"]), "others": makeup(O, "band", ["8 GB", "16 GB", "18 GB+"])},
                      "os": {"acct": makeup(A, "os_major", oss), "others": makeup(O, "os_major", oss)}},
           "free_mem": {"acct": free_mem(As), "others": free_mem(Os)}, "flagged": flagged}
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
    print(f"mac_health: {len(A)} {acct} Mac users ({len(As)} scored), {len(O)} at other customers ({len(Os)} scored); {len(flagged)} flagged")


if __name__ == "__main__":
    main()
