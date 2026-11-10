#!/usr/bin/env python3
"""Build the in-depth Tech Health report for one account, start to finish, narrating each step.
Runs the analysis scripts in order, then writes the page. Account-specific notes (display name, focus app,
context) come from accounts/<key>.json when it exists; the build works without one.

Usage
  python -I build_indepth.py --account <key> [--week 2026-10-12] [--render-only] [--no-cache]

  --week         Monday of the last full week to report (default: last full week). The month is the 28 days ending that Sunday.
  --render-only  skip the data steps and rebuild the page from the last run (after writing or editing story.json)
  --no-cache     run every query live (default: reuse a query's saved result when its exact text ran before)

Code and data are kept apart: the scripts can sit in a read-only folder (the published skill), and runs/, cache/,
accounts/ and <account>/ go to the data folder: TH_HOME if set, else this folder when it already has runs/ (the
working copy), else TechHealth in the user's home folder. Notes shipped beside the scripts (../accounts) are copied into the data
folder's accounts/ the first time, never over an existing file.

Output: runs/indepth_<account>_<week>/ with every step's output, manifest.json (what ran, rows, seconds) and
tech-health-indepth-<account>.html. The story at the top is story.json in the same folder, written from facts.json only.
"""
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); Q = os.path.join(HERE, "queries")
HOME = os.environ.get("TH_HOME") or (HERE if os.path.isdir(os.path.join(HERE, "runs")) else os.path.join(os.path.expanduser("~"), "TechHealth"))
PY = [sys.executable, "-I"]
CACHE_KEEP_DAYS = 35   # cached results older than this are deleted at the start of a build (a month plus margin)

def last_monday():
    t = dt.datetime.now(dt.timezone.utc).date(); return t - dt.timedelta(days=t.weekday() + 7)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--account", required=True); ap.add_argument("--week")
    ap.add_argument("--render-only", action="store_true"); ap.add_argument("--flavor", choices=["internal", "client"], default="internal"); ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(); acct = a.account.strip().lower()
    week = dt.date.fromisoformat(a.week) if a.week else last_monday()
    wend = week + dt.timedelta(days=7); ws = wend - dt.timedelta(days=28)
    out = os.path.join(HOME, "runs", f"indepth_{acct}_{week}"); os.makedirs(out, exist_ok=True); os.makedirs(os.path.join(HOME, acct), exist_ok=True)
    seed, notes = os.path.join(os.path.dirname(HERE), "accounts"), os.path.join(HOME, "accounts"); os.makedirs(notes, exist_ok=True)
    if os.path.isdir(seed) and os.path.abspath(seed) != os.path.abspath(notes):
        for f in os.listdir(seed):
            if not os.path.exists(os.path.join(notes, f)): shutil.copy(os.path.join(seed, f), os.path.join(notes, f))
    ap_ = os.path.join(notes, f"{acct}.json"); ACC = json.load(open(ap_, encoding="utf-8")) if os.path.exists(ap_) else {}
    if ACC: shutil.copy(ap_, os.path.join(out, "account.json"))
    env = dict(os.environ, TH_LOG=os.path.join(out, "queries.log"), TH_HOME=HOME)
    if not a.no_cache: env["TH_CACHE_DIR"] = os.path.join(HOME, "cache", "q")
    old = time.time() - CACHE_KEEP_DAYS * 86400; pruned = 0
    for dp, _, fs in os.walk(os.path.join(HOME, "cache")):
        for f in fs:
            if f.endswith(".json") and os.path.getmtime(os.path.join(dp, f)) < old: os.remove(os.path.join(dp, f)); pruned += 1
    mp = os.path.join(out, "manifest.json")
    man = json.load(open(mp, encoding="utf-8")) if (a.render_only and os.path.exists(mp)) else {
        "account": acct, "week": str(week), "period": [str(ws), str(wend)], "steps": [], "started_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"In-depth Tech Health report: {acct}. Last full week {week}; month {ws} to {wend - dt.timedelta(days=1)}.", flush=True)
    if pruned: print(f"Removed {pruned} cached results older than {CACHE_KEEP_DAYS} days.", flush=True)

    def step(n, title, what, cmds, outputs):
        print(f"\n[{n}] {title}\n    {what}", flush=True)
        lp = env["TH_LOG"]; before = sum(1 for _ in open(lp, encoding="utf-8")) if os.path.exists(lp) else 0
        t0 = time.time(); stdout_all = []
        for c in cmds:
            p = subprocess.run(c, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=HERE)
            if p.returncode:
                print(p.stdout[-1200:]); print(p.stderr[-1200:], file=sys.stderr); sys.exit(f"step {n} failed: {' '.join(c[2:4])}")
            stdout_all += p.stdout.splitlines()
            for l_ in p.stdout.splitlines():
                if l_.startswith(("No PCG gateway list", "PCG endpoints not on")): print("    " + l_, flush=True)
        qs = [json.loads(l) for l in open(lp, encoding="utf-8").read().splitlines()[before:]] if os.path.exists(lp) else []
        for line in stdout_all:  # tech_health_weekly prints "  label: N rows, ..." per query
            m = re.match(r"\s+(\w+): (\d+) rows, (cached|[\d.]+ s)", line)
            if m: qs.append({"rows": int(m.group(2)), "how": "cached" if m.group(3) == "cached" else "live"})
        rows = sum(x["rows"] for x in qs); live = sum(1 for x in qs if x["how"] == "live")
        scripts = [os.path.basename(c[2]) for c in cmds]
        print(f"    {', '.join(scripts)}: {len(qs)} queries ({live} live), {rows:,} rows, {time.time() - t0:.0f} s", flush=True)
        secs = round(time.time() - t0, 1)
        man["steps"].append({"n": n, "title": title, "what": what, "scripts": scripts, "queries": len(qs), "live": live, "rows": rows,
                             # live_seconds is the time of a fully live step; a partly cached step keeps the last full live time
                             "seconds": secs, "live_seconds": secs if qs and live == len(qs) else prev_live.get(n) or (secs if live else None), "outputs": outputs})

    prev_live = {}
    if os.path.exists(mp):
        for s_ in json.load(open(mp, encoding="utf-8")).get("steps", []):
            if s_.get("live_seconds"): prev_live[s_["n"]] = s_["live_seconds"]
    if not a.render_only:
        man["steps"] = []
        score = os.path.join(out, "score")
        step(1, "Compare every user with other customers",
             f"Every Windows user at every customer, two 28-day periods: memory, frozen apps, launches, CPU, disk, drops, roaming, latency.",
             [PY + [os.path.join(HERE, "tech_health_weekly.py"), "--accounts", acct, "--week", str(week), "--out", score, "--backfill", "5",
                    ] + ([] if a.no_cache else ["--cache-dir", os.path.join(HOME, "cache")])], ["score/reports.json", "score/facts_" + acct + ".json"])
        # tech_health_weekly has its own transport; log its query count from run.json
        run = json.load(open(os.path.join(score, "run.json"), encoding="utf-8"))
        man["steps"][-1]["checks"] = run["checks"]
        print(f"    completeness: " + ", ".join(f"{k} {v[0]:,} = {v[1]:,}" for k, v in run["checks"].items()), flush=True)
        wk = os.path.join(out, "weekly.json")
        step(2, "Five-week trend", "One row per user per week, so each measure gets a weekly line against other customers.",
             [PY + [os.path.join(Q, "weekly.py"), str(wend), "5", wk], PY + [os.path.join(Q, "weekly_trend.py"), acct, wk, os.path.join(out, "weekly_trend.json")]],
             ["weekly_trend.json"])
        w8 = os.path.join(HOME, "runs", f"why8_{ws}_{wend}.json"); av = os.path.join(HOME, "runs", f"av_sets_{ws}_{wend}.json")
        step(3, "Memory at start", "Free memory when Blue Border starts and installed memory for every user, plus security software.",
             [PY + [os.path.join(Q, "why_8gb.py"), str(ws), str(wend)], PY + [os.path.join(Q, "kq.py"), os.path.join(Q, "av_sets.kql"), av, f"ws={ws}", f"we={wend}"],
              PY + [os.path.join(Q, "swap_by_band_weekly.py"), acct, wk, w8, os.path.join(out, "swap_by_band_weekly.json")],
              PY + [os.path.join(Q, "apps_by_band.py"), acct, str(ws), str(wend), w8, os.path.join(out, "apps_by_band.json")] + ([ACC["focus_app"]] if ACC.get("focus_app") else []),
              PY + [os.path.join(Q, "free_ram_av.py"), str(ws), str(wend), acct]],
             ["swap_by_band_weekly.json", "apps_by_band.json", f"{acct}/free_ram_av.json"])
        # the Brazil before/after step is one account's gateway move; it runs only when the notes ask for it ("brazil_gateway_step": true)
        brazil = bool(ACC.get("brazil_gateway_step"))
        step(4, "Gateway and latency", "Latency checked against a second source, and where each user connects from and the gateway they reach"
             + (", plus each user's gateway before and after the Brazil gateway went live." if brazil else "."),
             [PY + [os.path.join(Q, "latency_check.py"), acct, str(ws), str(wend), os.path.join(out, "latency_check.json")],
              PY + [os.path.join(Q, "gateway_by_location.py"), acct, str(ws), str(wend), os.path.join(out, "gateway_by_location.json")]]
             + ([PY + [os.path.join(Q, "brazil_latency.py"), str(wend), acct]] if brazil else []),
             ["latency_check.json", "gateway_by_location.json"] + ([f"{acct}/brazil_latency.json"] if brazil else []))
        step(5, "Mac users", "Macs send no Session Score, so they are compared on what they do send: start time, can't-start, gateway drops, reconnect after sleep, free disk and memory at start.",
             [PY + [os.path.join(Q, "mac_health.py"), acct, str(ws), str(wend), os.path.join(out, "mac_health.json")]], ["mac_health.json"])
        for f in ("free_ram_av.json",) + (("brazil_latency.json",) if brazil else ()):
            shutil.copy(os.path.join(HOME, acct, f), os.path.join(out, f))
        if not brazil and os.path.exists(os.path.join(out, "brazil_latency.json")): os.remove(os.path.join(out, "brazil_latency.json"))
        man["finished_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump(man, open(mp, "w", encoding="utf-8"), indent=1)

    print(f"\n[6] Write the report\n    Every section from the files above. The summary at the top comes from story.json, written from facts only.", flush=True)
    page = os.path.join(out, f"tech-health-indepth-{acct}" + ("-client" if a.flavor == "client" else "") + ".html")
    sp = os.path.join(out, "story.json")
    name = (json.load(open(sp, encoding="utf-8")).get("display_name") if os.path.exists(sp) else None) or ACC.get("display_name") or acct
    for c in ([PY + [os.path.join(HERE, "build_indepth_page.py"), out, page]],
              [PY + [os.path.join(Q, "build_summary.py"), os.path.join(out, "weekly_trend.json"), page, os.path.join(out, "swap_by_band_weekly.json"), name]]):
        p = subprocess.run(c[0], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE, env={**os.environ, "TH_FLAVOR": a.flavor})
        if p.returncode: print(p.stdout[-1500:]); print(p.stderr[-1500:], file=sys.stderr); sys.exit("page build failed")
    tot = sum(s["seconds"] for s in man["steps"])
    print(f"\nDone. {sum(s['queries'] for s in man['steps'])} queries, {sum(s['rows'] for s in man['steps']):,} rows, {tot:.0f} s of data steps.\nReport: {page}")
    if not os.path.exists(os.path.join(out, "story.json")):
        print("No story.json yet: the page has a placeholder summary. Write story.json from facts.json, then run with --render-only.")

if __name__ == "__main__":
    main()
