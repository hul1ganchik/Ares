#!/usr/bin/env python3
"""Write the in-depth Tech Health page for one run folder (made by build_indepth.py), in the in-depth report design.
Every number comes from the run's files. Also writes facts.json, the only input for story.json.
build_summary.py then inserts the last-full-week block after the story.
Usage: python -I build_indepth_page.py <run folder> <page.html>"""
import datetime as dt, html, json, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
run, page = sys.argv[1:3]
J = lambda f: json.load(open(os.path.join(run, f), encoding="utf-8")) if os.path.exists(os.path.join(run, f)) else None
R = J("score/reports.json")["docs"][0]["data"]; MAN = J("manifest.json"); FR_AV = J("free_ram_av.json"); AM = J("app_mix.json")
LC = J("latency_check.json"); BL = J("brazil_latency.json"); GL = J("gateway_by_location.json"); US = J("users_since_august.json"); SBW = J("swap_by_band_weekly.json"); AB = J("apps_by_band.json")
MH = J("mac_health.json")   # Mac users (mac_health.py); older runs have none
# flavor: "internal" keeps everything; "client" is for the customer's technical team: no rating, no build/script
# internals, and a numbers-first tour. Other customers appear only as shares and medians in both.
CLIENT = os.environ.get("TH_FLAVOR", "internal") == "client"; STORY = J("story.json"); WT = J("weekly_trend.json")
acct = R["account"]; e = html.escape
NAME = (STORY or {}).get("display_name") or (J("account.json") or {}).get("display_name") or acct
pop = R["population"]; P = R["params"]

FEW = 20  # fewer account users than this in a band (or comparison group): grey, not compared
def d(s, end=False):
    x = dt.date.fromisoformat(s[:10]) - dt.timedelta(days=1 if end else 0); return f"{x.day} {x.strftime('%b')} {x.year}"
def r0(v): return "–" if v is None else (str(int(v + 0.5)) if v >= 1 or v == 0 else "<1")   # half-up, same as build_summary.py
def pc(v): return "–" if v is None else f"{r0(v)}%"
def n(v): return "–" if v is None else f"{v:,}"
CONF = {"hi": "High", "mh": "Medium-high", "md": "Medium", "ml": "Medium-low", "lo": "Low"}
def conf(c, why=""): return f'<span class="conf {c}"' + (f' title="{e(why)}"' if why else "") + f'>{CONF[c]}</span>'   # reason on hover only
PER, PRI = R["period"], R["prior"]
M = {"swap": ("Memory swapping", "a sign the laptop is short of memory", "md", "measured reliably; goes with slower apps for the same user"),
     "net": ("Local network drops", "the laptop's own connection", "ml", "new measure; line is other customers' top 10%"),
     "gw": ("Gateway disconnects", "the Venn tunnel", "ml", "new measure; often follows a local drop"),
     "frozen": ("Apps frozen", "what users feel", "mh", "reliable and repeats; says an app hung, not why"),
     "latency": ("Slow gateway (250 ms+)", "typical latency", "hi", "checked against a second source"),
     "launch": ("Slow app launches", "against each app's own slowest 10%", "md", "lines are provisional"),
     "roam": ("Gateway roaming", "switching gateway sites", "ml", "follows the drops; watch only"),
     "cpu": ("CPU pinned at 90%+", "on 10% of readings", "ml", "supporting evidence"),
     "low_disk": ("Low disk", "under 10 GB free", "md", "measured at container start"),
     "loop": ("Reconnect loops", "5+ failures in 5 minutes", "ml", "rare; watch only")}

# ---------------- facts for the story (numbers only)
fr = R["free_ram"]; sec = (FR_AV or {}).get("security_8 GB or less", {})
facts = {"account": acct, "period": PER, "prior": PRI, "population": pop,
         "measures": {k: {"rate": P[k]["cur"]["rate"], "others": P[k]["cur"]["others"], "users": P[k]["cur"]["users"], "prev_rate": P[k]["prev"]["rate"],
                          "prev_others": P[k]["prev"]["others"], "persistent": P[k]["persistent"], "le12": P[k]["le12"], "ge16": P[k]["ge16"]} for k in M},
         "weekly": {k: [(p["wk"], p["acct"], p["others"]) for p in WT["series"][k]] for k in ("swap", "net", "gw", "frozen", "lat_ms")} if WT else {},
         "free_ram": {b: fr[b] for b in fr},
         "named": {"multi": len(R["named"]["multi"]), "persistent_any": R["named"]["persistent_any"], "any_now": R["named"]["any_now"]},
         "latency": {"internet_med": R["latency"]["internet_med"]},
         "gateway_move": (BL or {}).get("moved_to_brazil"), "gateway_stayed": (BL or {}).get("did_not_move"),
         "cores": R.get("cores"), "cores_known": R.get("cores_known"),
         "gateway_location": {k: GL[k] for k in ("acct_users", "others_users", "acct_median_ms", "others_median_ms", "acct_bands", "others_bands")} if GL else None,
         "mac": {"population": MH["population"], "lines": MH["lines"], "measures": MH["measures"], "flagged": len(MH["flagged"]),
                 "ram": MH["makeup"]["ram"], "chip": MH["makeup"]["chip"]} if MH else None}
json.dump(facts, open(os.path.join(run, "facts.json"), "w", encoding="utf-8"), indent=1)

css = open(os.path.join(HERE, "indepth_style.css"), encoding="utf-8").read() + """
.mv .before{fill:var(--muted)} .mv .after{fill:var(--accent)} .mv .ln{stroke:var(--line);stroke-width:2} .mv .worse{stroke:var(--bad-soft)}
.mv text{fill:var(--muted);font-family:var(--mono);font-size:11px} .mv text.u{fill:var(--fg);font-family:var(--sans);font-size:12px}
tr.focus td{background:var(--accent-soft)}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.step{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px;display:grid;gap:6px;align-content:start}
.step .no{font-family:var(--mono);font-size:.75rem;color:var(--accent)} .step .scr{font-family:var(--mono);font-size:.75rem;color:var(--muted)}
th.grp{text-align:center;border-left:1px solid var(--line)} .bl{border-left:1px solid var(--line)} td.o{color:var(--muted)}
details.more>summary{list-style:none} details.more>summary::-webkit-details-marker{display:none}
details.more>summary::before{content:"\\203A";display:inline-block;width:1em;font-size:1.4rem;line-height:1;color:var(--accent);transition:transform .15s ease;align-self:center}
details.more[open]>summary::before{transform:rotate(90deg)}
details.more>summary::after{content:"(expand)";font-size:.78rem;color:var(--muted);order:3}
details.more[open]>summary::after{content:"(collapse)"}
details.more>summary .small{order:4;flex-basis:100%;padding-left:calc(1em + 10px)}
"""
parts = []
# ---------------- header + story
above = sorted([k for k in M if (P[k]["cur"]["rate"] or 0) - (P[k]["cur"]["others"] or 0) >= 3], key=lambda k: -((P[k]["cur"]["rate"] or 0) - (P[k]["cur"]["others"] or 0)))
parts.append(f'''<header style="display:grid;gap:8px">
  <div class="eyebrow">{"Prepared for " + e(NAME) + " IT · names your users · Tech Health report" if CLIENT else "Internal · names users · Tech Health in-depth report"}</div>
  <h1>{e(NAME)}: technical health and trend</h1>
  <div class="meta"><span>This month: {d(PER[0])} to {d(PER[1], True)}</span><span>Last month: {d(PRI[0])} to {d(PRI[1], True)}</span>
    <span>{n(pop["scored"])} Windows users scored (5+ days)</span>{f'<span>{n(MH["population"]["acct_scored"])} Mac users scored</span>' if MH else ""}<span>Compared with other Venn customers' users on the same platform</span></div>
</header>''')
if STORY:
    chip = {"Red": "c-bad", "Amber": "c-warn", "Green": "c-good"}.get(STORY.get("tech"), "c-info")
    paras = STORY.get("paragraphs", [])
    parts.append('<section class="story">\n  <div class="eyebrow">The story</div>\n  <p class="lead">' + e(STORY["headline"]) + "</p>\n"
                 + "".join(f"  <p>{e(p)}</p>\n" for p in paras)
                 + (f'  <p class="small">Proposed rating: <span class="chip {chip}">Tech: {e(STORY["tech"])}</span> <span class="chip {chip}">Trend: {e(STORY.get("trend", ""))}</span></p>\n' if STORY.get("tech") and not CLIENT else "")
                 + "</section>")
else:
    k0 = above[0] if above else None
    parts.append('<section class="story">\n  <div class="eyebrow">The story</div>\n  <p class="lead">'
                 + (e(f"{M[k0][0]} is furthest above other customers: {pc(P[k0]['cur']['rate'])} of {NAME} users against {pc(P[k0]['cur']['others'])}.") if k0 else "Every measure is at or below other customers.")
                 + '</p>\n  <p class="small">Draft summary: write story.json from facts.json and rebuild with --render-only.</p>\n</section>')

# ---------------- what to do (story actions)
if STORY and STORY.get("actions"):
    parts.append('<section id="what-to-do"><h2>What to do</h2><ul>' + "".join(f"<li>{e(x)}</li>" for x in STORY["actions"]) + "</ul></section>")

# ---------------- by memory band (all measures)
BANDS = ["8 GB or less", "12 GB", "16 GB", "20 GB+"]
def bcell(k, b):
    a_u, a_n, o_u, o_n = P[k]["bands"][b]
    if not a_n: return '<td class="n cell-grey">no users</td>'
    ar, orr = 100 * a_u / a_n, 100 * o_u / o_n if o_n else None
    cls = "cell-grey" if a_n < FEW else "cell-warn" if orr is not None and ar - orr >= 3 else "cell-good" if orr is not None and ar <= orr else ""
    return f'<td class="n {cls}">{pc(ar)} / {pc(orr)}' + ('<br><span class="small">few users</span>' if a_n < FEW else "") + "</td>"
hdr = "".join(f'<th>{b}<br><span class="small">{n(P["swap"]["bands"][b][1])} / {n(P["swap"]["bands"][b][3])} users</span></th>' for b in BANDS)
rows = "".join(f'<tr><td><b>{e(M[k][0])}</b></td>{"".join(bcell(k, b) for b in BANDS)}</tr>' for k in ("swap", "frozen", "launch", "cpu", "net", "gw"))
parts.append(f'''<details class="more" id="by-memory">
<summary><span class="h2like">By memory band</span> <span class="small">every measure against other customers' users with the same memory, {d(PER[0])} to {d(PER[1], True)}</span></summary>
<section><div class="tw"><table><thead><tr><th>Measure</th>{hdr}</tr></thead><tbody>{rows}</tbody></table></div>
<p class="small">Each cell: {e(NAME)} / other customers with the same memory. Amber: {e(NAME)} 3+ points above; green: at or below; grey: fewer than {FEW} {e(NAME)} users.</p></section>
</details>''')

# ---------------- free memory at start
FRB = ["Under 16 GB", "16 GB and above"] if "Under 16 GB" in fr else BANDS   # two-band split at 16 GB
MIX = {k: sum((fr[b][k].get("n") or 0) for b in FRB) for k in ("acct", "others")}   # machines with a known memory size, all bands
def frb(b):
    x = fr[b]; A, O = x["acct"], x["others"]
    if not A.get("n"): return f"<tr><td><b>{b}</b></td>" + '<td class="n bl" colspan="2">no users</td>' + '<td class="n bl"></td><td></td>' * 3 + "</tr>"
    few = A["n"] < FEW; sw = x.get("swap_if_under_1gb", {})
    def c(av, ov, worse_if_lower=False):
        if few or av is None or ov is None: return " cell-grey" if few else ""
        bad = av < 0.85 * ov if worse_if_lower else av - ov >= 5
        return " cell-warn" if bad else ""
    return (f'<tr><td><b>{b}</b>{"<span class=tag>few users</span>" if few else ""}</td><td class="n bl">{pc(100 * A["n"] / MIX["acct"] if MIX["acct"] else None)}<br><span class="small">{n(A["n"])}</span></td><td class="n o">{pc(100 * (O.get("n") or 0) / MIX["others"] if MIX["others"] else None)}</td>'
            f'<td class="n bl{c(A.get("median_mb"), O.get("median_mb"), True)}">{n(A.get("median_mb"))} MB</td><td class="n o">{n(O.get("median_mb"))} MB</td>'
            f'<td class="n bl{c(A.get("under_1gb"), O.get("under_1gb"))}">{pc(A.get("under_1gb"))}</td><td class="n o">{pc(O.get("under_1gb"))}</td>'
            f'<td class="n bl{swc(A, sw)}">{pc(sw.get("acct"))}</td><td class="n o">{pc(sw.get("others"))}</td></tr>')
def swc(A, sw):  # swapping is measured only among users who start under 1 GB free, so the size test uses that group
    if sw.get("acct") is None or sw.get("others") is None: return ""
    if (A.get("under_1gb_users") or 0) < FEW: return " cell-grey"
    return " cell-warn" if sw["acct"] - sw["others"] >= 5 else ""
f8 = fr["8 GB or less"]; fa = fr["all"]
FU, FUL = (fr["Under 16 GB"], ("machines" if CLIENT else "laptops") + " under 16 GB") if "Under 16 GB" in fr else (f8, "8 GB laptops")   # boxes and tour use the under-16 GB group
parts.append(f'''<section id="free-ram">
  <h2>Free memory when Blue Border starts</h2>
  <p class="small">Each user's median free physical memory at container start, {d(PER[0])} to {d(PER[1], True)}. It is read before any work in Blue Border, so it shows what is already running on the laptop outside Blue Border.</p>
  <div class="cols">
    <div class="box"><div class="eyebrow">{FUL[0].upper() + FUL[1:]}, median free at start</div><div class="big">{n(FU["acct"].get("median_mb"))} MB</div><p class="small">Other customers' {FUL}: {n(FU["others"].get("median_mb"))} MB.</p></div>
    <div class="box"><div class="eyebrow">{FUL[0].upper() + FUL[1:]} starting under 1 GB free</div><div class="big">{pc(FU["acct"].get("under_1gb"))}</div><p class="small">{n(FU["acct"].get("under_1gb_users"))} of {n(FU["acct"].get("n"))} users. Other customers: {pc(FU["others"].get("under_1gb"))}.</p></div>
    <div class="box"><div class="eyebrow">All {e(NAME)} users starting under 1 GB free</div><div class="big">{pc(fa["acct"].get("under_1gb"))}</div><p class="small">{n(fa["acct"].get("under_1gb_users"))} of {n(fa["acct"].get("n"))} users. Other customers: {pc(fa["others"].get("under_1gb"))}.</p></div>
  </div>
  <div class="tw"><table class="pair"><thead><tr><th rowspan="2">Memory band</th><th class="grp" colspan="2">Share of machines</th><th class="grp" colspan="2">Median free at start</th><th class="grp" colspan="2">Start under 1 GB free</th><th class="grp" colspan="2">Swapping, if under 1 GB at start</th></tr>
  <tr>{('<th class="n bl">' + e(NAME) + '</th><th class="n">Other customers</th>') * 4}</tr></thead><tbody>{"".join(frb(b) for b in FRB)}</tbody></table></div>
  <p class="small">Share of machines: each band's share of the {n(MIX["acct"])} {e(NAME)} machines with a known memory size (count underneath), against the same share at other customers. Amber: {e(NAME)} worse than other customers with the same memory: median free memory below 85% of theirs, or 5 or more points higher on starting under 1 GB free or on swapping. Grey: fewer than {FEW} {e(NAME)} users to compare (for swapping, fewer than {FEW} who start under 1 GB free).</p>
</section>''')
if CLIENT:   # client tour (23 Oct): table first, then the tiles, wrapped so step 2 can highlight both and the tour keeps moving down
    fs_ = parts[-1]; i_, j_, k_ = fs_.index('  <div class="cols">'), fs_.index('  <div class="tw">'), fs_.index('</section>')
    parts[-1] = fs_[:i_] + '  <div id="free-ram-body" style="display:grid;gap:12px">\n' + fs_[j_:k_] + fs_[i_:j_] + '  </div>\n' + fs_[k_:]

# ---------------- CPU cores (machine makeup)
CO = R.get("cores")
if CO:
    ck = R.get("cores_known") or {}
    def share(a, b): return 100 * a / b if b else None
    def mcell(v):
        a_u, a_n, o_u, o_n = v
        if not a_n: return '<td class="n bl cell-grey">–</td><td class="n o">–</td>'
        ar, orr = 100 * a_u / a_n, (100 * o_u / o_n if o_n else None)
        cls = "cell-grey" if a_n < FEW else "cell-warn" if orr is not None and ar - orr >= 3 else ""
        return f'<td class="n bl {cls}">{pc(ar)}</td><td class="n o">{pc(orr)}</td>'
    crow = "".join(f'<tr><td><b>{e(b)}</b>{"<span class=tag>few users</span>" if 0 < x["acct_n"] < FEW else ""}</td>'
                   f'<td class="n bl">{pc(share(x["acct_n"], ck.get("acct")))}<br><span class="small">{n(x["acct_n"])}</span></td><td class="n o">{pc(share(x["others_n"], ck.get("others")))}</td>'
                   + mcell(x["cpu"]) + mcell(x["swap"]) + "</tr>" for b, x in CO.items())
    parts.append(f'''<section id="cpu-cores">
  <h2>Laptops by CPU cores</h2>
  <p class="small">Physical CPU cores reported when Blue Border starts, {d(PER[0])} to {d(PER[1], True)}. {n(ck.get("acct"))} of {n(pop["scored"])} {e(NAME)} users report a core count. Each pair: {e(NAME)}, then other customers' users with the same core count.</p>
  <div class="tw"><table class="pair"><thead><tr><th rowspan="2">CPU cores</th><th class="grp" colspan="2">Share of users</th><th class="grp" colspan="2">CPU pinned at 90%+</th><th class="grp" colspan="2">Memory swapping</th></tr>
  <tr>{('<th class="n bl">' + e(NAME) + '</th><th class="n">Other customers</th>') * 3}</tr></thead><tbody>{crow}</tbody></table></div>
  <p class="small">Amber: {e(NAME)} 3+ points above other customers with the same core count. Grey: fewer than {FEW} {e(NAME)} users. Core count is a description of the fleet, not a cause on its own.</p>
</section>''')

# ---------------- apps in use by memory group and swapping flag, plus an optional focus app from accounts/<key>.json
APPN = {"CompanyUrlWebApp": "Company web links", "Bloc de notas": "Bloc de notas (Notepad, Spanish Windows)"}
def appmix(BB):   # does any top app separate flagged from unflagged users under 16 GB? 10+ points = name it
    g = BB.get("Under 16 GB") or next(iter(BB.values()))
    if min(g["flagged"], g["not_flagged"]) < FEW: return "Too few flagged or unflagged users under 16 GB to compare their apps."
    r = max(g["apps"], key=lambda r: abs((r["flagged_pct"] or 0) - (r["not_flagged_pct"] or 0)))
    d_ = (r["flagged_pct"] or 0) - (r["not_flagged_pct"] or 0)
    if abs(d_) < 10: return "Flagged and unflagged users run largely the same apps. Starting memory separates them more clearly (see Free memory at start)."
    return (f"Under 16 GB, {APPN.get(r['app'], r['app'])} is the clearest difference: {pc(r['flagged_pct'])} of flagged users run it, against "
            f"{pc(r['not_flagged_pct'])} of unflagged users. This goes with swapping; it is not shown to cause it.")
if AB:
    FU_ = AB.get("focus_users") or []; FA = AB.get("focus") if FU_ else None; FL = AB.get("focus_launch") or {}; FW = AB.get("focus_within_user"); BB = AB["bands"]
    bl = list(BB)
    def acell(b, k, r):
        g = BB[b]["flagged" if k == "flagged_pct" else "not_flagged"]
        return f'<td class="n{" bl" if k == "flagged_pct" else ""}{" cell-grey" if g < FEW else ""}">{pc(r[k])}</td>'
    arows = "".join(f'<tr{" class=focus" if r["app"] == FA else ""}><td><b>{e(APPN.get(r["app"], r["app"]))}</b></td>'
                    + "".join(acell(b, k, next(x for x in BB[b]["apps"] if x["app"] == r["app"])) for b in bl for k in ("flagged_pct", "not_flagged_pct")) + "</tr>"
                    for r in BB[bl[0]]["apps"])
    hdr2 = "".join(f'<th class="n bl">Flagged<br><span class="small">{n(BB[b]["flagged"])} users</span></th><th class="n">Not flagged<br><span class="small">{n(BB[b]["not_flagged"])} users</span></th>' for b in bl)
    fb = {b: [u for u in FU_ if u["band"] == b] for b in bl}
    def frate(b):
        x = next((r for r in BB[b]["apps"] if r["app"] == FA), None); k = len(fb[b])
        if not x or not k: return f"{e(b)}: no users"
        return (f'{e(b)}: {n(sum(u["flagged"] for u in fb[b]))} of {n(k)} flagged ({pc(x["flag_with"])}), against {pc(x["flag_without"])} of the '
                f'{n(BB[b]["users"] - k)} users without it' + (' <span class="tag">few users</span>' if k < FEW else ""))
    urows = "".join(f'<tr><td>{e(u["u"])}</td><td>{e(u["band"])}</td><td class="n">{n(round(u["free_mb"]))} MB</td><td class="n">{n(u["launches"])}</td>'
                    f'<td{" class=cell-warn" if u["flagged"] else ""}>{"Flagged" if u["flagged"] else "Not flagged"}</td></tr>' for u in FU_)
    wl = (f'<li>Within the same user, on days they used it: {pc(FW["after_pct"])} of readings were above the lower threshold in the 2 hours after a launch, against '
          f'{pc(FW["rest_pct"])} the rest of those days ({n(FW["users"])} users: {n(FW["higher"])} higher after, {n(FW["lower"])} lower, '
          f'{n(FW["users"] - FW["higher"] - FW["lower"])} about the same).</li>') if FW else ""
    def fread():
        x0 = next((r for r in BB[bl[0]]["apps"] if r["app"] == FA), None); k0 = len(fb[bl[0]])
        if not x0 or k0 < FEW or x0["flag_with"] is None or x0["flag_without"] is None:
            return f"Too few {e(NAME)} users of {e(FA)} on machines under 16 GB (fewer than {FEW}) to compare them with users without it."
        g = x0["flag_with"] - x0["flag_without"]
        if abs(g) < 3: return f"Under 16 GB, users of {e(FA)} swap at about the same rate as users without it. Starting memory separates them more clearly."
        return (f"Under 16 GB, users of {e(FA)} swap {'more' if g > 0 else 'less'} often than users without it ({pc(x0['flag_with'])} against {pc(x0['flag_without'])}). "
                "This goes with the app; it is not shown to cause it.")
    fbox = "" if not FA else f"""<div class="tw" style="padding:14px 16px"><h3 style="margin:0 0 6px">{e(FA)}</h3><ul style="margin:0;padding-left:18px;display:grid;gap:4px">
    <li>Launched inside Blue Border by {n(FL.get("users"))} {e(NAME)} users on {n(FL.get("user_days"))} user-days in four weeks{(" (" + e(FL["paths"][0]) + ")") if FL.get("paths") else ""}.</li>
    <li>{pc(FL.get("within10_pct"))} of launches come within 10 minutes of Blue Border starting. Typical launch {n(FL.get("launch_ms_p50"))} ms.</li>
    <li>{frate(bl[0])}.</li><li>{frate(bl[1])}.</li>{wl}
    <li>Read: {fread()}</li></ul>
  <details class="more notes" style="margin-top:8px"><summary><span class="small">Users who launched {e(FA)} ({n(len(FU_))} scored)</span></summary>
  <table><thead><tr><th>User</th><th>Memory group</th><th class="n">Median free at start</th><th class="n">Launches</th><th>Swapping</th></tr></thead><tbody>{urows}</tbody></table></details></div>"""
    parts.append(f"""<section id="apps-by-band">
  <h2>Apps in use, by memory group</h2>
  <p class="small">Share of users in each group who launched the app inside Blue Border at least once, {d(AB["window"][0])} to {d(AB["window"][1], True)}, split by whether they were flagged for sustained swapping. The {n(len(BB[bl[0]]["apps"]))} apps most used at {e(NAME)}{"; " + e(FA) + " is highlighted" if FA else ""}. Apps run outside Blue Border are not in telemetry.</p>
  <div class="tw"><table class="pair"><thead><tr><th rowspan="2">App</th>{"".join(f'<th class="grp" colspan="2">{e(b)}</th>' for b in bl)}</tr><tr>{hdr2}</tr></thead><tbody>{arows}</tbody></table></div>
  <p class="small">{e(appmix(BB))} Grey: fewer than {FEW} users in that column.</p>
  {fbox}
</section>""")

# ---------------- security products
if sec:
    sw_, non = sec["acct_swappers"], sec["acct_non"]; osw, onon = sec["other_swappers"], sec["other_non"]
    def sp(g, k): return pc(g["product_pct"].get(k, 0))
    prods = [k for k in sw_["product_pct"] if k != "Defender"][:5]
    srows = "".join(f'<tr><td><b>{e(k)}</b></td><td class="n">{sp(sw_, k)}</td><td class="n">{sp(non, k)}</td><td class="n o">{sp(osw, k)}</td><td class="n o">{sp(onon, k)}</td></tr>' for k in prods)
    parts.append(f'''<details class="more" id="security-products">
<summary><span class="h2like">Security software and swapping</span> <span class="small">which products swapping 8 GB users run, {d(PER[0])} to {d(PER[1], True)}</span></summary>
<section><div class="tw"><table><thead><tr><th>8 GB or less</th><th class="n">{e(NAME)} swapping<br><span class="small">{n(sw_["n"])}</span></th><th class="n">{e(NAME)} not swapping<br><span class="small">{n(non["n"])}</span></th>
<th class="n">Other customers swapping</th><th class="n">Other customers not swapping</th></tr></thead><tbody>{srows}
<tr class="muted-row"><td>Two third-party products</td><td class="n">{pc(sw_["two_third_party_pct"])}</td><td class="n">{pc(non["two_third_party_pct"])}</td><td class="n">{pc(osw["two_third_party_pct"])}</td><td class="n">{pc(onon["two_third_party_pct"])}</td></tr></tbody></table></div>
<p class="small">Windows keeps Defender listed next to a third-party product, so "two products" almost always means Defender plus one; true double antivirus is the last row. Coincident, not proven per user. <span class="conf ml">Medium-low</span></p></section>
</details>''')

# ---------------- monthly detail, all ten
def mrow(k):
    c, p = P[k]["cur"], P[k]["prev"]; g = (c["rate"] or 0) - (c["others"] or 0); gp = (p["rate"] or 0) - (p["others"] or 0)
    cls = "cell-warn" if g >= 3 else "cell-good" if g <= -1 else ""
    tr = "better" if gp - g >= 2 else "worse" if g - gp >= 2 else "steady"
    return (f'<tr><td><b>{e(M[k][0])}</b><br><span class="small">{e(M[k][1])}</span></td><td class="n {cls}">{pc(c["rate"])}<br><span class="small">{n(c["users"])} users</span></td>'
            f'<td class="n o">{pc(c["others"])}</td><td class="n">{pc(p["rate"])}</td><td class="n o">{pc(p["others"])}</td><td>{tr}</td><td class="n">{n(P[k]["persistent"])}</td><td>{conf(M[k][2], M[k][3])}</td></tr>')
order = sorted(M, key=lambda k: -((P[k]["cur"]["rate"] or 0) - (P[k]["cur"]["others"] or 0)))
parts.append(f'''<section id="monthly">
  <h2>Monthly detail: every measure</h2>
  <p class="small">Share of scored users flagged on each measure, compared with other customers. This month {d(PER[0])} to {d(PER[1], True)}; last month {d(PRI[0])} to {d(PRI[1], True)}. Sorted by the gap to other customers. Trend compares the gap with last month's; 2 points or more is better or worse.</p>
  <div class="tw"><table><thead><tr><th>Measure</th><th class="n">{e(NAME)}, this month</th><th class="n">Others</th><th class="n">{e(NAME)}, last month</th><th class="n">Others</th><th>Gap trend</th><th class="n">Failed both months</th><th>Confidence</th></tr></thead>
  <tbody>{"".join(mrow(k) for k in order)}</tbody></table></div>
</section>''')

# ---------------- where users connect from
def short(r):  # "North America (US-East), US PCG group" -> "US-East (US PCG group)"
    i, j = r.find("("), r.find(")")
    if i < 0 or j < i: return r
    s_ = r[i + 1:j].split(",")[0]; rest = r[j + 1:].strip(" ,")
    return f"{s_} ({rest})" if rest else s_
if GL and GL["locations"]:
    w200 = lambda b: (b.get("200-249", 0) + b.get("250+", 0)); ab, ob = GL["acct_bands"], GL["others_bands"]
    def mixcell(g): return "<br>".join(f'{e(short(x["region"]))}: {n(x["users"])} <span class="small">· {x["median_ms"]} ms</span>' for x in g["gateways"][:3]) + (f'<br><span class="small">+{len(g["gateways"]) - 3} more</span>' if len(g["gateways"]) > 3 else "")
    lrows = "".join(f'<tr><td>{e(l["location"])}' + (f'<br><span class="small">{e(", ".join(l["countries"]))}</span>' if l.get("countries") else "") +
                    f'</td><td class="n">{n(l["users"])}</td><td class="n">{l["median_ms"]} ms</td><td class="n o">{"–" if l["others_median_ms"] is None else str(l["others_median_ms"]) + " ms"}</td>'
                    f'<td>{mixcell(l)}</td><td class="n">{n(l["watch_200"] + l["over_250"])}</td></tr>' for l in GL["locations"])
    fromcell = lambda g: ", ".join(f'{x["location"]} {x["users"]}' for x in g["from"])
    grows = "".join(f'<tr><td>{e(g["group"] or "Not on the list")}</td><td>{e(short(g["region"]))}</td><td class="n">{n(g["users"]) if g["users"] else "none"}</td>'
                    f'<td class="n">{"–" if g["median_ms"] is None else str(g["median_ms"]) + " ms"}</td><td class="small">{e(fromcell(g))}</td></tr>' for g in GL["gateways"])
    G0 = GL.get("default_group"); nd = [g for g in GL["gateways"] if g["group"] and g["group"] != G0 and g["users"]]
    slow_nd = [x for x in GL["slow_users"] if x["region"].endswith(" group")]
    grp_note = ""
    if nd:
        gu = sum(g["users"] for g in nd); names = ", ".join(f'{x["u"].split(".")[0]} ({x["loc"]}, {x["ms"]} ms)' for x in slow_nd)
        grp_note = (f'<div class="box" style="margin-top:12px"><div class="eyebrow">Users outside the {e(G0)} group</div>'
                    f'<p>{n(gu)} users connect mainly through a gateway in another group ({e(", ".join(sorted({g["group"] for g in nd})))}), typical latency {", ".join(str(g["median_ms"]) + " ms" for g in nd)}. '
                    f'A group limits its users to its own regions, so these users cannot reach the closer regions in {e(G0)}.'
                    + (f' {len(slow_nd)} of them are at 200 ms or more: {e(names)}. Check with the customer whether they need to be in that group.' if slow_nd else "") + '</p></div>')
    parts.append(f"""<section id="where-connect">
  <h2>Where users connect from, and the gateway they reach</h2>
  <p class="small">{n(GL["acct_users"])} {e(NAME)} users with 50 or more gateway checks from {d(GL["window"][0])} to {d(GL["window"][1], True)}, compared with other customers' users. Country is from each user's own public address. Each user's main gateway is the one most of their checks went to, and typical latency is their median to it. Watch from 200 ms, flag from 250 ms.</p>
  <div class="cols">
    <div class="box"><div class="eyebrow">Typical user, gateway latency</div><div class="big">{GL["acct_median_ms"]} ms</div><p class="small">Median {e(NAME)} user, against {GL["others_median_ms"]} ms for the median user at other customers.</p></div>
    <div class="box"><div class="eyebrow">Users at 200 ms or more</div><div class="big">{n(w200(ab))} of {n(GL["acct_users"])}</div><p class="small">{pc(100 * w200(ab) / GL["acct_users"])} of {e(NAME)} users, against {pc(100 * w200(ob) / GL["others_users"])} of users at other customers. {n(ab.get("250+", 0))} at 250 ms or more.</p></div>
    <div class="box"><div class="eyebrow">Gateway regions in use</div><div class="big">{sum(1 for g in GL["gateways"] if g["users"] and g["on_plan"])} of {sum(1 for g in GL["gateways"] if g["on_plan"])}</div><p class="small">Regions on {e(NAME)}'s gateway list that are some user's main gateway. {n(GL["multi_region_users"])} users reached two or more regions during the month.</p></div>
  </div>
  <h3>By country</h3>
  <div class="tw"><table><thead><tr><th>Country</th><th class="n">Users</th><th class="n">Typical latency</th><th class="n">Other customers there</th><th>Main gateway: users · typical latency</th><th class="n">200 ms+</th></tr></thead><tbody>{lrows}</tbody></table></div>
  <p class="small">Other customers there: median user at other customers in the same country, shown where they have 10 or more users. Countries with fewer than 5 {e(NAME)} users are grouped.</p>
  <h3>By gateway region</h3>
  <div class="tw"><table><thead><tr><th>Group</th><th>Region</th><th class="n">Main gateway for</th><th class="n">Typical latency</th><th>Users come from</th></tr></thead><tbody>{grows}</tbody></table></div>
  <p class="small">Regions and groups from {e(NAME)}'s Admin Portal gateway list. Latency covers only the trip to the Venn gateway.</p>
  {grp_note}
</section>""")

# ---------------- latency details
lat = R["latency"]
brows = "".join(f'<tr><td>{e(b["band"])}</td><td class="n bl">{pc(b["pct"])}<br><span class="small">{n(b["users"])}</span></td><td class="n o">{pc(o["pct"])}</td></tr>' for b, o in zip(lat["bands_cur"]["acct"], lat["bands_cur"]["others"]))
crows = "".join(f'<tr><td>{e(c["country"])}</td><td class="n">{n(c["acct_n"])}</td><td class="n">{c["acct_med"]} ms</td><td class="n o">{"too few" if c["others_med"] is None else str(c["others_med"]) + " ms"}</td><td class="n">{n(c["over50"])}</td></tr>' for c in lat["country"][:10])
acc = ""
if LC:
    pu = [u for u in LC["per_user"] if u.get("SsP50") and u.get("HP50") and (u.get("SsN") or 0) >= 50 and (u.get("HN") or 0) >= 50]
    dif = [abs(u["SsP50"] - u["HP50"]) for u in pu]; agree = sum((u["SsP50"] >= 250) == (u["HP50"] >= 250) for u in pu)
    ssa = next((x for x in LC["session_score"] if x["G"] == "acct"), {})
    acc = (f'<section><h3>How accurate the latency figures are</h3><p class="small">For {n(len(pu))} {e(NAME)} users, the scored latency and the product\'s own gateway probe differ by '
           f'{st.median(dif):.0f} ms in the typical case, and agree on the 250 ms line for {pc(100 * agree / len(pu) if pu else None)} of users. '
           f'Readings clamped at 999 ms: {n(ssa.get("Clamp"))}. Gateway latency covers only the trip to the Venn gateway; proxy, security inspection and app-server distance add delay telemetry does not measure.</p></section>') if pu else ""
parts.append(f'''<details class="more" id="latency-details">
<summary><span class="h2like">Latency details</span> <span class="small">bands, same-country comparison and accuracy check (optional reading)</span></summary>
<section><h3>Users by typical gateway latency</h3><div class="tw"><table><thead><tr><th>Band</th><th class="n bl">{e(NAME)}</th><th class="n">Other customers</th></tr></thead><tbody>{brows}</tbody></table></div></section>
<section><h3>Same country, {e(NAME)} against other customers</h3><div class="tw"><table><thead><tr><th>Country</th><th class="n">{e(NAME)} users</th><th class="n">Their median</th><th class="n">Others there</th><th class="n">50+ ms over others</th></tr></thead><tbody>{crows}</tbody></table></div>
<p class="small">Typical local network latency: {e(NAME)} {n(lat["internet_med"]["acct"])} ms, others {n(lat["internet_med"]["others"])} ms. Country is from each user's public address; addresses shared with other users are left out.</p></section>
{acc}
</details>''')

# ---------------- connectivity
pf = lambda v: "n/a" if v is None else f"{v:.1f}%"
con = R["connectivity"]; home = con.get("home_ip_share") or [0, 0]
parts.append(f'''<section id="connectivity">
  <h2>Connectivity in more detail</h2>
  <div class="cols">
    <div class="box"><div class="eyebrow">Cabled laptops, share of readings with a local drop</div><div class="big">{pf(con["cabled"]["acct_net"])}</div><p class="small">Typical (median) user. Other customers' cabled laptops: {pf(con["cabled"]["others_net"])}. {n(con["cabled"]["acct_n"])} {e(NAME)} users mostly on a cable.</p></div>
    <div class="box"><div class="eyebrow">Wi-Fi laptops, same measure</div><div class="big">{pf(con["wifi"]["acct_net"])}</div><p class="small">Typical (median) user. Other customers on Wi-Fi: {pf(con["wifi"]["others_net"])}. {n(con["wifi"]["acct_n"])} {e(NAME)} users.</p></div>
    <div class="box"><div class="eyebrow">Connect from a unique address</div><div class="big">{n(home[0])} of {n(home[1])}</div><p class="small">Users seen this month (scored or not) on a public internet address no other Venn user shares. The rest share an address with other users, for example an office, a VPN or a gateway.</p></div>
  </div>
  <p class="small">{n(con["both_drop_measures"])} of {n(con["net_users"])} users with local drops also have gateway disconnects. {n(con["roamers_with_net_drops"])} of {n(con["roamers"])} roaming users also have local drops.</p>
</section>''')

# ---------------- gateway move
if BL and BL.get("moved_to_brazil") and BL["moved_to_brazil"]["users"] >= 5:
    s, stay = BL["moved_to_brazil"], BL["did_not_move"]; mv = sorted(BL["moved_users"], key=lambda r: -r["before_ms"])
    W2, rh, P2 = 1100, 19, 150; X = lambda v: P2 + (W2 - P2 - 20) * min(v, 220) / 220
    body = ""
    for i, u in enumerate(mv):
        y = 14 + i * rh
        body += (f'<text class="u" x="0" y="{y+4}">{e(u["u"].split(".")[0])}</text><line class="ln{" worse" if u["after_ms"] > u["before_ms"] else ""}" x1="{X(u["before_ms"]):.1f}" y1="{y}" x2="{X(u["after_ms"]):.1f}" y2="{y}"/>'
                 f'<circle class="before" cx="{X(u["before_ms"]):.1f}" cy="{y}" r="5"/><circle class="after" cx="{X(u["after_ms"]):.1f}" cy="{y}" r="5"/>')
    H2 = 14 + len(mv) * rh
    ticks = "".join(f'<line class="ln" x1="{X(v):.1f}" y1="{H2}" x2="{X(v):.1f}" y2="{H2+5}"/><text x="{X(v):.1f}" y="{H2+18}" text-anchor="middle">{v} ms</text>' for v in (0, 50, 100, 150, 200))
    parts.append(f'''<section id="gateway-move">
  <h2>The Brazil gateway: {s["before_med"]} ms to {s["after_med"]} ms for the {s["users"]} users who moved</h2>
  <p class="small">Each user's typical gateway latency before (22 Aug to 21 Sep) and after (22 Sep to {d(BL["window"][1], True)}) the Brazil gateway went live on 21 Sep. {s["improved_20ms"]} of {s["users"]} improved by 20 ms or more. The {n(stay["users"])} users who stayed on their old gateway: {stay["before_med"]} ms before, {stay["after_med"]} ms after. Grey dot before, blue dot after.</p>
  <div class="tw" style="padding:14px"><svg class="mv" viewBox="0 0 {W2} {H2+24}" width="100%" role="img" aria-label="gateway latency before and after per user">{body}{ticks}</svg></div>
</section>''')

# ---------------- Mac users (mac_health.py, 27 Oct): own measures, compared only with other customers' Macs
MF = {"slow_start": "Slow container start", "cant_start": "Container could not start", "many_drops": "Many gateway drops",
      "slow_wake": "Slow reconnect after sleep", "low_disk": "Low disk"}
if MH:
    mp_, ml_, ma, mo = MH["population"], MH["lines"], MH["measures"]["acct"], MH["measures"]["others"]
    def mcls(a, o, users):
        if a is None or o is None: return ""
        return "cell-grey" if users < FEW else "cell-warn" if a - o >= 3 else "cell-good" if a <= o else ""
    def secs(ms): return "–" if ms is None else f"{ms / 1000:.1f} s"
    mrows_ = [("slow_start", f"start slower than {secs(ml_['start_ms'])} (other customers' slowest 10%)", f"Typical start {secs(ma['start_med_ms'])}, others {secs(mo['start_med_ms'])}", ma["users"]),
              ("cant_start", "at least one \"can't start\" this month", "", ma["users"]),
              ("many_drops", f"more than {ml_['drops_per_day']:.1f} gateway drops per active day (others' top 10%)", f"Typical {ma['drops_med_per_day']:.2f} a day, others {mo['drops_med_per_day']:.2f}", ma["users"]),
              ("slow_wake", f"typical reconnect after sleep over {secs(ml_['wake_ms'])} (others' slowest 10%)", f"Typical {secs(ma['wake_med_ms'])}, others {secs(mo['wake_med_ms'])}; users with 10+ wakes ({n(ma['wake_users'])})", ma["wake_users"]),
              ("low_disk", "under 10 GB free on the system disk at the latest start", "", ma["users"])]
    mtab = "".join(f'<tr><td><b>{MF[k]}</b><br><span class="small">{e(why)}</span></td><td class="n {mcls(ma[k], mo[k], u)}">{pc(ma[k])}</td><td class="n o">{pc(mo[k])}</td><td class="small">{e(typ)}</td></tr>'
                   for k, why, typ, u in mrows_)
    def mk(key, order=None):
        A_, O_ = MH["makeup"][key]["acct"], MH["makeup"][key]["others"]
        return "".join(f'<tr><td>{e(("macOS " + v) if key == "os" else v)}</td><td class="n bl">{pc(A_[v]["pct"])}<br><span class="small">{n(A_[v]["n"])}</span></td><td class="n o">{pc(O_[v]["pct"])}</td></tr>'
                       for v in (order or A_) if A_[v]["n"])
    fmrows = "".join(f'<tr><td>{b}{"<span class=tag>few users</span>" if 0 < MH["free_mem"]["acct"][b]["n"] < FEW else ""}</td><td class="n bl">{n(MH["free_mem"]["acct"][b]["median_mb"])} MB<br><span class="small">{n(MH["free_mem"]["acct"][b]["n"])} users</span></td>'
                     f'<td class="n o">{n(MH["free_mem"]["others"][b]["median_mb"])} MB</td></tr>' for b in ("8 GB", "16 GB", "18 GB+") if MH["free_mem"]["acct"][b]["n"])
    worst = max(MF, key=lambda k: (ma[k] or 0) - (mo[k] or 0))
    frows_ = "".join(f'<tr><td class="mono">{e(x["user"].split(".")[0])}</td><td>{e(", ".join(MF[k] for k in x["flags"]))}</td><td>{e(x["ram"] or "")}</td><td>{e(x["chip"])}</td><td>{e("macOS " + x["os"] if x["os"] else "")}</td></tr>'
                     for x in MH["flagged"] if len(x["flags"]) >= 2)
    n2 = sum(1 for x in MH["flagged"] if len(x["flags"]) >= 2)
    parts.append(f'''<section id="macs">
  <h2>Mac users</h2>
  <p class="small">{n(mp_["acct_all"])} {e(NAME)} users used Blue Border on a Mac from {d(MH["window"][0])} to {d(MH["window"][1], True)}; {n(mp_["acct_scored"])} on 5 or more days are scored here, against {n(mp_["others_scored"])} Mac users at other customers. Macs send no Session Score readings, so swapping, frozen apps, CPU, launch time and latency are not measured on them. Macs also send no list of security software, so the security software section covers Windows only. These are the measures Macs do send.</p>
  <div class="cols">
    <div class="box"><div class="eyebrow">Mac users scored</div><div class="big">{n(mp_["acct_scored"])}</div><p class="small">{pc(100 * mp_["acct_scored"] / (mp_["acct_scored"] + pop["scored"]))} of {e(NAME)}'s scored users (Windows and Mac).</p></div>
    <div class="box"><div class="eyebrow">Furthest above other customers' Macs</div><div class="big">{pc(ma[worst])}</div><p class="small">{MF[worst]}: {e(NAME)} Mac users, against {pc(mo[worst])} at other customers.</p></div>
    <div class="box"><div class="eyebrow">Flagged on 2 or more measures</div><div class="big">{n(n2)} of {n(mp_["acct_scored"])}</div><p class="small">{n(len(MH["flagged"]))} flagged on at least one. Listed at the end of this section.</p></div>
  </div>
  <div class="tw"><table><thead><tr><th>Measure</th><th class="n">{e(NAME)} Macs</th><th class="n">Other customers' Macs</th><th>Typical values</th></tr></thead><tbody>{mtab}</tbody></table></div>
  <p class="small">Share of scored Mac users flagged on each measure. Amber: {e(NAME)} 3+ points above other customers' Macs; green: at or below; grey: fewer than {FEW} users. Measures with no product threshold use other customers' slowest or highest 10% as the line, so other customers sit at 10% by design.</p>
  <h3>The Macs</h3>
  <div class="cols">
    <div class="tw"><table class="pair"><thead><tr><th>Chip</th><th class="n bl">{e(NAME)}</th><th class="n">Others</th></tr></thead><tbody>{mk("chip")}</tbody></table></div>
    <div class="tw"><table class="pair"><thead><tr><th>Memory</th><th class="n bl">{e(NAME)}</th><th class="n">Others</th></tr></thead><tbody>{mk("ram")}</tbody></table></div>
    <div class="tw"><table class="pair"><thead><tr><th>macOS</th><th class="n bl">{e(NAME)}</th><th class="n">Others</th></tr></thead><tbody>{mk("os")}</tbody></table></div>
  </div>
  <p class="small">Share of all {n(mp_["acct_all"])} {e(NAME)} Mac users (count underneath), from each Mac's start-up record.</p>
  <h3>Free memory when Blue Border starts</h3>
  <div class="tw"><table class="pair"><thead><tr><th>Memory</th><th class="n bl">{e(NAME)}, median free</th><th class="n">Other customers' Macs</th></tr></thead><tbody>{fmrows}</tbody></table></div>
  <p class="small">macOS counts free memory differently from Windows (it keeps recently used memory in use and frees it on demand), so compare these only with other Macs, not with the Windows figures above.</p>
  <details class="more notes" style="margin-top:8px"><summary><span class="small">Mac users flagged on 2 or more measures ({n(n2)})</span></summary>
  <table><thead><tr><th>User</th><th>Flagged on</th><th>Memory</th><th>Chip</th><th>macOS</th></tr></thead><tbody>{frows_}</tbody></table></details>
</section>''')

# ---------------- named users
nm = R["named"]; MN = {k: v[0] for k, v in M.items()}
pers = {x["user"]: x["persistent"] for x in nm.get("persistent_list", [])}; first_period = bool(nm.get("first_period"))
nl = nm.get("now_list") or nm["multi"]   # older run files only have the both-months list
nrows = "".join(f'<tr><td class="mono">{e(x["user"].split(".")[0])}</td><td>{e(", ".join(MN.get(k, k) for k in x.get("now") or x.get("persistent", [])))}</td>'
                f'<td class="n">{"" if x.get("ram") is None else str(x["ram"]) + " GB"}</td>'
                f'<td>{"" if first_period else e(", ".join(MN.get(k, k) for k in pers.get(x["user"], [])))}</td></tr>' for x in nl)
parts.append(f'''<section id="named">
  <h2>Named users impacted</h2>
  <div class="cols">
    <div class="box"><div class="eyebrow">Any measure this month</div><div class="big">{n(nm["any_now"])} of {n(pop["scored"])}</div><p class="small">Each drop line flags 10% of other customers by design, so this total runs high.</p></div>
    <div class="box"><div class="eyebrow">Also flagged last month</div><div class="big">{"Not yet" if first_period else n(nm["persistent_any"])}</div><p class="small">{"First month for this account, so there is no earlier month to compare." if first_period else "Same measure, both months: the users we are sure about."}</p></div>
    <div class="box"><div class="eyebrow">Listed below</div><div class="big">{n(len(nl))}</div><p class="small">Most measures first{", top 50 shown" if len(nl) >= 50 else ""}. Start at the top.</p></div>
  </div>
  <div class="tw"><table><thead><tr><th>User</th><th>Flagged this month on</th><th class="n">Memory</th><th>Also last month</th></tr></thead><tbody>{nrows}</tbody></table></div>
  <p class="small">User IDs end in <span class="mono">.{e(acct)}</span>.</p>
</section>''')

# ---------------- how it was built
steps = MAN.get("steps", []) if MAN else []
sh = "".join(f'<div class="step"><div class="no">{s_["n"]:02d}</div><h3>{e(s_["title"])}</h3><p class="small">{e(s_["what"])}</p>'
             f'<p class="scr">{e(", ".join(s_["scripts"]))}<br>{n(s_["queries"])} queries · {n(s_["rows"])} rows'
             + (f' · {s_["live_seconds"]:.0f} s live' if s_.get("live_seconds") else f' · {s_["seconds"]:.0f} s') + '</p></div>' for s_ in steps)
chk = next((s_.get("checks") for s_ in steps if s_.get("checks")), {}) or {}
if not CLIENT: parts.append(f'''<section id="how-built">
  <h2>How this report was built</h2>
  <p class="small">One command, <span class="mono">build_indepth.py --account {e(acct)}</span>, runs the steps below in order and writes this page. Every number is a share of users, compared with other customers over the same period. The summary at the top is written from the run's facts file only.</p>
  <div class="steps">{sh}<div class="step"><div class="no">{len(steps)+1:02d}</div><h3>Write the report</h3><p class="small">Every section from the files above; the weekly block by build_summary.py.</p><p class="scr">build_indepth_page.py, build_summary.py</p></div></div>
  <p class="small">Completeness: row counts matched exact totals for {", ".join(f"{k.replace('_', ' ')} ({v[0]:,})" for k, v in chk.items()) or "–"}. Run {e(R["run_id"])}, {e(R["version"])}.</p>
</section>''')

# ---------------- users since the August peak (users_since_august.py)
if US and US["all"]["aug"] and not CLIENT:   # internal only since 23 Oct
    ua = US["all"]
    urows = "".join(f'<tr><td><b>{e(g["group"])}</b></td><td class="n bl">{pc(100 * g["aug"] / ua["aug"])}<br><span class="small">{n(g["aug"])}</span></td>'
                    f'<td class="n bl">{n(g["left"])}</td><td class="n">{pc(g["left_pct"])}</td><td class="n o">{pc(g["others_left_pct"])}</td>'
                    f'<td class="n bl">{n(g["disabled"])}</td><td class="n">{n(g["still_enabled"])}</td></tr>' for g in US["groups"])
    gb = {g["group"]: g for g in US["groups"]}; lo, hi = gb.get("Below 16 GB"), gb.get("16 GB and above")
    parts.append(f"""<section id="users-since-aug">
  <h2>Users since the August peak</h2>
  <p class="small">{n(ua["aug"])} {e(NAME)} users used Blue Border in {e(US["baseline"])}. A user is counted as gone when they have no use from {e(US["latest"])}; signing out alone does not count as use. Disabled means the account is disabled or deleted in Venn. Memory is each laptop's latest reading; Mac users are shown separately.</p>
  <div class="cols">
    <div class="box"><div class="eyebrow">August users not seen in October</div><div class="big">{n(ua["left"])} of {n(ua["aug"])}</div><p class="small">{pc(ua["left_pct"])} of {e(NAME)}'s August users, against {pc(ua["others_left_pct"])} at other customers.</p></div>
    <div class="box"><div class="eyebrow">Of those, disabled in Venn</div><div class="big">{n(ua["disabled"])}</div><p class="small">Accounts {e(NAME)} disabled or deleted. {n(ua["still_enabled"])} are still enabled but not using Blue Border.</p></div>
    <div class="box"><div class="eyebrow">Below 16 GB against 16 GB and above</div><div class="big">{pc(lo["left_pct"]) if lo else "–"} · {pc(hi["left_pct"]) if hi else "–"}</div><p class="small">Share of each group gone. About the same in both, so the drop is not tied to laptop memory.</p></div>
  </div>
  <div class="tw"><table class="pair"><thead><tr><th rowspan="2">Group</th><th class="grp">August users</th><th class="grp" colspan="3">Not seen 1 to 22 Oct</th><th class="grp" colspan="2">Of those</th></tr>
  <tr><th class="n bl">Share (count)</th><th class="n bl">Users</th><th class="n">Share of group</th><th class="n">Other customers</th><th class="n bl">Disabled</th><th class="n">Still enabled</th></tr></thead><tbody>{urows}</tbody></table></div>
  <p class="small">{n(ua["aug"] - sum(g["aug"] for g in US["groups"]))} users with no memory reading are counted in the totals only.</p>
</section>""")

# ---------------- data and limits
# client IT flavor: no data-limits section
if not CLIENT: parts.append(f'''<section id="limits">
  <h2>Data and limits</h2>
  <ul class="small">
    <li>{"Every measure except the Mac section is for Windows users. Macs send no Session Score readings, so memory swapping, frozen apps, CPU, app launch time and gateway latency are Windows only; the Mac section uses what Macs do send." if MH else "Windows users only. Macs send no Session Score readings, so they are not scored here."}</li>
    <li>Scored users have 5+ active days and 50+ readings in the month (3+ days for a week); scored Mac users have 5+ active days. Other customers means every other Venn customer's users on the same platform.</li>
    <li>A daily data limit drops part of the afternoon (US Eastern) on many days; every rate here is a share of users, so it is less affected than counts.</li>
    <li>Measures show what happened on the device, not why. Apps and security software are associations, not proof for any one user.</li>
  </ul>
</section>''')

# section order follows the tour: story, free memory, named users, what to do, CPU cores, where users connect,
# then the reference sections; "how it was built" and the limits stay last. The last-week block is inserted after the story later.
FIRST = ["free-ram", "apps-by-band", "named", "what-to-do", "cpu-cores", "where-connect", "macs", "users-since-aug"]; LAST = ["how-built", "limits"]
def ordered(ps):
    sid = lambda p: (re.search(r'\bid="([^"]+)"', p[:200]) or [None, None])[1]
    key = lambda p: (-1, 0) if sid(p) is None else (0, FIRST.index(sid(p))) if sid(p) in FIRST else (2, LAST.index(sid(p))) if sid(p) in LAST else (1, 0)
    return sorted(ps, key=key)   # stable: header and story first, reference sections keep their order
out = (f'<title>{e(NAME)} Tech Health{" (IT)" if CLIENT else ""}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
       '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">\n'
       f'<style>{css}</style>\n\n<div class="wrap">\n' + "\n\n".join(ordered(parts)) + "\n</div>\n")
# ---------------- presenter tour (hidden until T is pressed; see tour/tour.js). Talking points come from this run's files.
def apps_step():   # same step in both tours, right after swapping
    if not AB: return []
    FA = AB.get("focus") if AB.get("focus_users") else None; FL = AB.get("focus_launch") or {}; FW = AB.get("focus_within_user"); lo = AB["bands"].get("Under 16 GB") or {}
    fx = next((r for r in lo.get("apps", []) if r["app"] == FA), None); k = sum(1 for u in (AB.get("focus_users") or []) if u["band"] == "Under 16 GB")
    pts = [appmix(AB["bands"])]
    if FA: pts.append(f"{FA}: {n(FL.get('users'))} users launched it on {n(FL.get('user_days'))} user-days in four weeks. {pc(FL.get('within10_pct'))} of launches come within 10 minutes of Blue Border starting.")
    if FA and fx and k: pts.append(f"{n(k)} of its users are on machines under 16 GB, and {pc(fx['flag_with'])} of them are flagged, against {pc(fx['flag_without'])} of other users in that group. " + ("Too few users to call it a pattern." if k < FEW else "") + "")
    if FA and FW: pts.append(f"Same user, same days: {pc(FW['after_pct'])} of readings above the lower threshold in the 2 hours after a {FA} launch, against {pc(FW['rest_pct'])} the rest of the day.")
    return [{"label": "Apps in use", "sel": "#apps-by-band", "title": "Apps in use, by memory group",
             "say": f"Apps launched inside Blue Border, split by memory group and swapping flag" + (f", with {FA} highlighted." if FA else "."), "points": pts}]
def tour_steps():
    st_ = []
    if STORY: st_.append({"label": "Story", "sel": ".story", "title": "The story and rating",
                          "say": f"Written from this run's facts only. Rated {STORY.get('tech')}, {STORY.get('trend', '').lower()}."})
    if WT:
        sw5 = WT["series"]["swap"]; last = sw5[-1]; pv_ = [x["acct"] for x in sw5[:-1] if x["acct"] is not None]; prior = sum(pv_) / len(pv_) if pv_ else None
        st_.append({"label": "Last week", "sel": ".glance", "title": "Last full week, against the 4 before",
                    "say": f"Each measure against other customers, with a five-week line. Swapping: {pc(last['acct'])} of {NAME} users last week, against {pc(last['others'])} at other customers, down from {pc(prior)}."})
    st_.append({"label": "Free memory", "sel": "#free-ram", "title": "Free memory when Blue Border starts",
                "say": f"{pc(FU['acct'].get('under_1gb'))} of {NAME}'s {FUL} start under 1 GB free, against {pc(FU['others'].get('under_1gb'))} of other customers' {FUL}. Swapping is the symptom: the laptop is short of memory."})
    st_ += apps_step()
    st_.append({"label": "Named users", "sel": "#named", "title": "Named users impacted",
                "say": f"{n(R['named']['any_now'])} users are flagged on at least one measure this month; the most affected are listed first: the CSM's do-first list."})
    if STORY and STORY.get("actions"):
        st_.append({"label": "What to do", "sel": "#what-to-do", "title": "What to do", "say": "Steps a CSM or SA can take this week, written from the facts."})
    if CO:
        c4 = CO["4 or fewer"]; ck_ = R.get("cores_known") or {}
        st_.append({"label": "CPU cores", "sel": "#cpu-cores", "title": "Laptops by CPU cores",
                    "say": f"{pc(100 * c4['acct_n'] / ck_['acct'] if ck_.get('acct') else None)} of {NAME} users are on 4 cores or fewer, against {pc(100 * c4['others_n'] / ck_['others'] if ck_.get('others') else None)} at other customers."})
    if GL and GL["locations"]:
        G0 = GL.get("default_group"); nd = sum(g["users"] for g in GL["gateways"] if g["group"] and g["group"] != G0)
        sl = [x for x in GL["slow_users"] if x["region"].endswith(" group")]
        st_.append({"label": "Where users connect", "sel": "#where-connect", "title": "Where users connect from, and the gateway they reach",
                    "say": f"Each country, the gateway its users reach and the latency. The typical {NAME} user is at {GL['acct_median_ms']} ms against {GL['others_median_ms']} ms at other customers."
                           + (f" {len(sl)} of the {nd} users outside the {G0} group are at 200 ms or more: their group cannot reach the closer regions." if sl else "")})
    st_ += mac_step()
    return st_
def mac_step():   # same step in both tours
    if not MH: return []
    a_, o_ = MH["measures"]["acct"], MH["measures"]["others"]
    up = [k for k in MF if (a_[k] or 0) - (o_[k] or 0) >= 3 and (a_["wake_users"] if k == "slow_wake" else a_["users"]) >= FEW]
    return [{"label": "Mac users", "sel": "#macs", "title": "Mac users",
             "say": f"{n(MH['population']['acct_scored'])} scored Mac users, compared only with other customers' Macs on what Macs report: start, can't-start, drops, reconnect after sleep, disk.",
             "points": [f"{MF[k]}: {pc(a_[k])}, against {pc(o_[k])} at other customers." for k in up] or ["Every Mac measure is within 3 points of other customers' Macs."]}]
def tech_steps():   # client technical tour: the numbers, not what each area is
    G = lambda b: fr.get(b) or {}; lo, hi = G("Under 16 GB"), G("16 GB and above"); st_ = []
    if lo and hi:
        st_.append({"label": "Fleet by memory", "sel": "#free-ram .tw", "title": "Your Windows machines by memory",
                    "say": f"{pc(100 * lo['acct']['n'] / MIX['acct'])} of your active Windows machines ({n(lo['acct']['n'])}) have under 16 GB; {pc(100 * hi['acct']['n'] / MIX['acct'])} ({n(hi['acct']['n'])}) have 16 GB or more.",
                    "points": [f"Other customers: {pc(100 * lo['others']['n'] / MIX['others'])} under 16 GB, {pc(100 * hi['others']['n'] / MIX['others'])} at 16 GB and above."]})
        st_.append({"label": "Free memory at start", "sel": "#free-ram-body" if CLIENT else "#free-ram", "title": "Free memory before any work in Blue Border",
                    "say": "Machines under 16 GB start short of memory, before Blue Border runs anything. Each figure is compared with comparable machines at other customers.",
                    "points": [f"Median free at start: {n(lo['acct']['median_mb'])} MB, against {n(lo['others']['median_mb'])} MB elsewhere.",
                               f"{pc(lo['acct']['under_1gb'])} start under 1 GB free ({n(lo['acct']['under_1gb_users'])} machines), against {pc(lo['others']['under_1gb'])} elsewhere.",
                               f"Of those, {pc(lo['swap_if_under_1gb']['acct'])} were flagged for sustained swapping, against {pc(lo['swap_if_under_1gb']['others'])} elsewhere. How we measure swapping is on the next step.",
                               f"16 GB and above: {pc(hi['acct']['under_1gb'])} start under 1 GB free, against {pc(hi['others']['under_1gb'])} elsewhere."]})
    if WT:
        sw = WT["series"]["swap"][-1]; bl = {b: v[-1] for b, v in (SBW or {}).items()}; lo_, hi_ = bl.get("Under 16 GB"), bl.get("16 GB and above")
        pts = ["What we measure: how often each machine reads memory back from disk, as an indicator of memory pressure. A reading is taken every 5 minutes.",
               "What we flag: users above our internal thresholds for a large share of the time they're measured: above the lower threshold in at least half of their readings, or above the higher threshold in at least a quarter."]
        if lo_ and hi_ and lo_["a"] is not None and hi_["a"] is not None:
            pts.append(f"Worth noting: the flag rate falls sharply as memory goes up. {pc(lo_['a'])} of your machines under 16 GB were flagged last week, against {pc(hi_['a'])} at 16 GB and above. Comparable machines at other customers show the same pattern ({pc(lo_['o'])} against {pc(hi_['o'])}).")
        pts.append(f"All users: {pc(sw['acct'])}, against {pc(sw['others'])} at other customers.")
        st_.append({"label": "Swapping last week", "sel": ".glance", "title": "Memory swapping, last full week",
                    "say": "Every machine swaps a little; we count it only when it's sustained.", "points": pts,
                    # the Session Score lines (CONFIG-430): Memory\Pages Input/sec, 12 samples a minute kept at the 90th percentile, every 5 minutes
                    "note": "Thresholds: 500 and 2,000 pages read from disk per second (Windows counter Memory\\Pages Input/sec), measured every 5 minutes."})
    st_ += apps_step()
    nm_ = R["named"].get("now_list") or R["named"]["multi"]
    st_.append({"label": "Users to start with", "sel": "#named", "title": "Named users to start with",
                "say": f"{n(len(nm_))} users are listed, most measures first.",
                "points": [f"{n(sum(1 for x in nm_ if x.get('ram') and x['ram'] < 16))} of them are on machines under 16 GB."]
                          + ([f"{n(lo['acct']['under_1gb_users'])} machines under 16 GB start under 1 GB free: check what starts at sign-in."] if lo else [])})
    if GL and GL["locations"]:
        G0 = GL.get("default_group"); nd = sum(g["users"] for g in GL["gateways"] if g["group"] and g["group"] != G0)
        sl = [x for x in GL["slow_users"] if x["region"].endswith(" group")]; mvd = (BL or {}).get("moved_to_brazil") or {}
        hi200 = lambda b: sum(b.get(k, 0) for k in ("200-249", "250+"))
        st_.append({"label": "Gateway latency", "sel": "#where-connect", "title": "Gateway latency and where users connect",
                    "say": f"Typical gateway latency is {GL['acct_median_ms']} ms, against {GL['others_median_ms']} ms at other customers.",
                    "points": [f"{n(hi200(GL['acct_bands']))} of {n(GL['acct_users'])} users at 200 ms or more, against {pc(100 * hi200(GL['others_bands']) / GL['others_users'])} of users at other customers."]
                              + ([f"Brazil gateway: the {n(mvd['users'])} users who moved went from {mvd['before_med']} ms to {mvd['after_med']} ms."] if mvd.get("users") else [])
                              + ([f"{len(sl)} of the {nd} users in another gateway group are at 200 ms or more; that group reaches only its own regions."] if sl else [])})
    if US and US["all"]["aug"] and not CLIENT:
        ua = US["all"]; gb = {g["group"]: g for g in US["groups"]}
        st_.append({"label": "Users since August", "sel": "#users-since-aug", "title": "Users since the August peak",
                    "say": f"{n(ua['left'])} of {n(ua['aug'])} August users have not used Blue Border in October ({pc(ua['left_pct'])}, against {pc(ua['others_left_pct'])} at other customers).",
                    "points": [f"Below 16 GB {pc(gb['Below 16 GB']['left_pct'])}, 16 GB and above {pc(gb['16 GB and above']['left_pct'])}: about the same, so not tied to memory.",
                               f"{n(ua['disabled'])} of the {n(ua['left'])} are disabled or deleted in Venn; {n(ua['still_enabled'])} are still enabled."]})
    st_ += mac_step()
    return st_
TOUR_JS = open(os.path.join(HERE, "tour", "tour.js"), encoding="utf-8").read()
out += ("<script>\n" + TOUR_JS + "\nPresenterTour.init(" + json.dumps(tech_steps() if CLIENT else tour_steps()).replace("</", "<\\/") + ", {autoSeconds: 14, rail: true, content: \".wrap\"});\n</script>\n")
open(page, "w", encoding="utf-8").write(out); print(page)
