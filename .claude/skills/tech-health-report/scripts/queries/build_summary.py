"""Build the weekly summary block (rounded numbers, confidence, swapping split by memory band, collapsed band matrix)
and insert it after the story in the local draft page.
Usage: python build_summary.py <weekly_trend.json> <draft.html> [swap_by_band_weekly.json]"""
import datetime as dt, json, math, re, sys
hr = lambda v: int(math.floor(v + 0.5)) if v >= 0 else -int(math.floor(-v + 0.5))   # half-up rounding
src, page = sys.argv[1:3]
bands_src = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
NAME = sys.argv[4] if len(sys.argv) > 4 else "This account"
T = json.load(open(src, encoding="utf-8")); S = T["series"]; weeks = T["weeks"]
SB = json.load(open(bands_src, encoding="utf-8")) if bands_src else {}
ROWS = [("swap", "Memory swapping", "all memory sizes"), ("net", "Local network drops", "the laptop's own connection, cabled too"),
        ("gw", "Gateway disconnects", "Venn tunnel"), ("frozen", "Apps frozen", "what users feel"),
        ("lat_ms", "Gateway latency", "average per user, ms; lower is better *")]
UNIT = {"lat_ms": " ms"}
CONF = {"hi": "High", "mh": "Medium-high", "md": "Medium", "ml": "Medium-low", "lo": "Low"}
WHY = {"swap": ("md", "measured reliably; heavy swapping goes with about 3x more frozen-app time for the same user, not proven per user"),
       "net": ("ml", "new measure, no agreed line yet; drops coincide with frozen apps but cause is not proven"),
       "gw": ("ml", "new measure, no agreed line yet; often follows a local drop"),
       "frozen": ("mh", "reliable and repeats month to month; says an app hung, not why"),
       "lat_ms": ("hi", "checked against the product's own gateway probe; see Latency details")}
FEW = 20
import os
_bl = os.path.join(os.path.dirname(src), "brazil_latency.json")
_mv = (json.load(open(_bl, encoding="utf-8")).get("moved_to_brazil") or {}) if os.path.exists(_bl) else {}
BRAZIL = None   # a gateway go-live marker is account-specific; not drawn on the trend lines
BRAZIL_LEGEND = "."

def rp(v):  # rounded percent text
    return "<1" if 0 < v < 1 else str(hr(v))
def conf(k, why): return f'<span class="conf {k}" title="{why}">{CONF[k]}</span>'   # reason on hover only (no subtext in the column)

def spark(pts, ka="acct", ko="others"):
    w, h, pad = 120, 34, 4
    vals = [p[ka] for p in pts] + [p[ko] for p in pts]
    top = max(vals) * 1.15 or 1
    x = lambda i: pad + i * (w - 2 * pad) / (len(pts) - 1)
    y = lambda v: h - pad - v / top * (h - 2 * pad)
    line = lambda k: " ".join(f"{x(i):.1f},{y(p[k]):.1f}" for i, p in enumerate(pts))
    mk = f'<line class="mk" x1="{x(weeks.index(BRAZIL)):.1f}" y1="2" x2="{x(weeks.index(BRAZIL)):.1f}" y2="{h-2}"/>' if BRAZIL in weeks else ""
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="weekly trend">' + mk +
            f'<polyline class="oth" points="{line(ko)}"/><polyline class="acc" points="{line(ka)}"/>'
            f'<circle class="dot" cx="{x(len(pts)-1):.1f}" cy="{y(pts[-1][ka]):.1f}" r="2.6"/></svg>')

def verdict(pts, step, ka="acct", ko="others"):
    gap = [p[ka] - p[ko] for p in pts if p[ka] is not None and p[ko] is not None]
    if len(gap) < 2: return ("Not enough weeks", "c-grey")
    early, late = sum(gap[:-1]) / len(gap[:-1]), gap[-1]
    if late <= 0 and early <= 0: return ("Below others", "c-good")
    d = late - early
    if d <= -step: return ("Improving, still above", "c-warn") if late > 0 else ("Improving", "c-good")
    if d >= step: return ("Worsening", "c-bad")
    return ("Steady, above", "c-warn") if late > 0 else ("Below others", "c-good")

def row(name, sub, pts, unit, cf, cls="", sub_a="", sub_o="", ka="acct", ko="others", step=2, few=False):
    if pts[-1][ka] is None or pts[-1][ko] is None or sum(p[ka] is not None for p in pts[:-1]) == 0:
        return (f'<tr class="{cls}"><td><b>{name}</b>' + (f'<br><span class="small">{sub}</span>' if sub else "") + '</td>'
                f'<td class="n" colspan="6">Not enough users this week to measure</td><td>{cf}</td></tr>')
    pts = [p for p in pts if p[ka] is not None and p[ko] is not None]
    last = pts[-1]; prior = sum(p[ka] for p in pts[:-1]) / len(pts[:-1]); d = hr(last[ka] - prior)
    v, c = verdict(pts, step, ka, ko)
    if few: v, c = v + ", few users", "c-grey"
    fmt = (lambda x: str(hr(x))) if unit == " ms" else rp
    return (f'<tr class="{cls}"><td><b>{name}</b>' + (f'<br><span class="small">{sub}</span>' if sub else "") + '</td>'
            f'<td class="n big2">{fmt(last[ka])}{unit}' + (f'<br><span class="small">{sub_a}</span>' if sub_a else "") + '</td>'
            f'<td class="n">{fmt(last[ko])}{unit}{sub_o}</td><td class="n">{fmt(prior)}{unit}</td><td class="n">{d:+d}</td>'
            f'<td>{spark(pts, ka, ko)}</td><td><span class="chip {c}">{v}</span></td><td>{cf}</td></tr>')

rows, FACT = [], {}
for k, name, sub in ROWS:
    pts = S[k]; last = pts[-1]; u = UNIT.get(k, "%")
    sub_a = f'median {last["acct_med"]} ms' if k in UNIT else f'{last["users"]} user' + ("" if last["users"] == 1 else "s")
    sub_o = f'<br><span class="small">median {last["others_med"]} ms</span>' if k in UNIT else ""
    rows.append(row(name, sub, pts, u, conf(*WHY[k]), "parent" if k == "swap" and SB else "", sub_a, sub_o, step=10 if k in UNIT else 2))
    pv = [p["acct"] for p in pts[:-1] if p["acct"] is not None]
    FACT[k] = (last["acct"], last["others"], sum(pv) / len(pv) if pv else None)
    if k == "swap" and SB:
        for b in SB:   # bands as swap_by_band_weekly.py writes them (two bands split at 16 GB since 23 Oct)
            bp = [{"acct": p["a"], "others": p["o"]} for p in SB[b]]; n, us = SB[b][-1]["n"], SB[b][-1]["u"]; few = n < FEW
            cf = conf("lo", f"fewer than {FEW} users in this band; a few people move it") if few else conf("md", "same basis as the line above")
            rows.append(row(b, "", bp, "%", cf, "sub", f"{us} of {n} users", sub_o="", few=few))

wk0 = dt.date.fromisoformat(weeks[0]); wL = dt.date.fromisoformat(weeks[-1]); wkN = wL + dt.timedelta(days=6); wP = dt.date.fromisoformat(weeks[-2]) + dt.timedelta(days=6)
f = {k: tuple(rp(x) if k != "lat_ms" else str(hr(x)) for x in v) for k, v in FACT.items()}
_bands = [(b, SB[b][-1]) for b in SB if SB[b][-1]["a"] is not None and SB[b][-1]["o"] is not None] if SB else []
band_line = (" Split by memory: " + "; ".join(f'{b[0].lower() + b[1:]} {rp(x["a"])}% against {rp(x["o"])}% at other customers' for b, x in _bands) + ".") if _bands else ""
def rel(k, step=None):
    a, o, _ = FACT[k]; st_ = step or (10 if k == "lat_ms" else 2)
    return "above other customers" if a - o >= st_ else "below other customers" if o - a >= st_ else "level with other customers"
def mv(k):
    a, _, pr = FACT[k]
    return "are easing" if pr - a >= 2 else "are rising" if a - pr >= 2 else "are steady"
block = f'''<section class="glance">
  <div class="eyebrow">Last full week · {wL:%a %d %b} to {wkN:%a %d %b} 2026, against the 4 weeks before ({wk0:%d %b} to {wP:%d %b})</div>
  <div class="tw"><table class="gl">
    <thead><tr><th>Measure</th><th>{NAME}, last week</th><th>Other customers, last week</th><th>{NAME}, prior 4 weeks</th><th>Change (pts)</th><th>5 weeks</th><th>Direction</th><th>Confidence</th></tr></thead>
    <tbody>
    {"".join(rows)}
    </tbody>
  </table></div>
  <details class="more notes"><summary><span class="small">How to read this table, and what it says</span></summary>
  <p class="small legend"><span class="sw acc"></span> {NAME} <span class="sw oth"></span> other customers{BRAZIL_LEGEND} Each value is the share of users past the line that week (users with 3+ days and 50+ readings); memory band lines compare with other customers' users in the same band. The drop lines are other customers' top 10%, so their rate sits at about 10% by design. Direction compares last week's gap to other customers with the average gap over the 4 weeks before; a change of 2 points (10 ms for latency) or more is improving or worsening. Numbers are rounded; direction is worked out on unrounded values.</p>
  <ul class="sum">
    <li><b>Memory swapping</b>: {f["swap"][0]}% of users last week against {f["swap"][1]}% elsewhere ({f["swap"][2]}% over the prior 4 weeks).{band_line}</li>
    <li><b>Connection drops {mv("net")}</b>: local network drops {f["net"][0]}% last week against {f["net"][2]}% over the prior 4 weeks, gateway disconnects {f["gw"][0]}% against {f["gw"][2]}%. Against other customers: local drops {rel("net")}, gateway disconnects {rel("gw")}.</li>
    <li><b>Frozen apps</b> ({f["frozen"][0]}% against {f["frozen"][1]}%) are {rel("frozen")}. <b>Gateway latency</b> averaged {f["lat_ms"][0]} ms per {NAME} user last week against {f["lat_ms"][1]} ms at other customers ({f["lat_ms"][2]} ms over the prior 4 weeks); the median user {S["lat_ms"][-1]["acct_med"]} ms against {S["lat_ms"][-1]["others_med"]} ms.</li>
  </ul>
  <p class="small">* Latency is each user's median gateway latency that week, averaged over users, with the median user underneath. It covers only the trip to the Venn gateway; proxy, security inspection and app-server distance add delay that telemetry does not measure. Same-country comparison and bands are in "Latency details".</p>
  <p class="small">Confidence: <span class="conf hi">High</span> cross-checked against a second source. <span class="conf mh">Medium-high</span> reliable and repeats, cause not attributed. <span class="conf md">Medium</span> measured reliably, user impact shown only partly. <span class="conf ml">Medium-low</span> new, or no agreed line yet. <span class="conf lo">Low</span> too few users to read on its own.</p>
  <p class="small">Also tracked, outside the five: gateway roaming (watch: it follows the drops; {rp(S["roam"][-1]["acct"])}% last week against {rp(S["roam"][-1]["others"])}%) and slow app launches (see the monthly detail).</p>
  </details>
</section>
'''
css = '''.glance{display:grid;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:18px}
.glance .tw{border:0;background:transparent}
table.gl td{vertical-align:middle}
.spark{display:block;max-width:100%;height:auto}
.spark .acc{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark .oth{fill:none;stroke:var(--muted);stroke-width:1.4;stroke-dasharray:3 3}
.spark .mk{stroke:var(--warn);stroke-width:1;stroke-dasharray:2 2;opacity:.7}
.spark .dot{fill:var(--accent)}
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}
.sw{display:inline-block;width:18px;height:0;border-top:2px solid var(--accent);vertical-align:middle}
.big2{font-size:1.05rem;font-weight:600}
.sw.oth{border-top:1.5px dashed var(--muted)} .sw.mk{border-top:1.5px dashed var(--warn)}
ul.sum{margin:0}
'''
css2 = '''/* v2 summary additions */
.conf{display:inline-block;font-size:.72rem;font-weight:500;padding:1px 7px;border-radius:4px;border:1px solid var(--line);white-space:nowrap}
.conf.hi{border-color:var(--good);color:var(--good)} .conf.mh{border-color:var(--good);color:var(--good);border-style:dashed}
.conf.md{border-color:var(--warn);color:var(--warn)} .conf.ml{border-color:var(--warn);color:var(--warn);border-style:dashed} .conf.lo{border-color:var(--muted);color:var(--muted);border-style:dotted}
.why{display:block;font-size:.72rem;color:var(--muted);margin-top:2px;max-width:30ch}
.c-grey{background:var(--line);color:var(--muted)}
tr.sub td:first-child{padding-left:26px} tr.sub td{border-bottom:1px dashed var(--line)} tr.parent td{border-bottom:0}
td.cell-warn{background:var(--warn-soft)} td.cell-good{background:var(--good-soft)} td.cell-grey{background:var(--line);color:var(--muted)}
.muted-row td{color:var(--muted)} .tag{font-size:.7rem;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:6px}
'''
h = open(page, encoding="utf-8").read()
h = re.sub(r'<section class="glance">.*?</section>\n', "", h, flags=re.S)
h = re.sub(r'<details class="more" id="by-memory">.*?</details>\n', "", h, flags=re.S)
if ".glance{" not in h: h = h.replace("</style>", css + "</style>", 1)
if "/* v2 summary additions */" not in h: h = h.replace("</style>", css2 + "</style>", 1)
# client IT flavor (23 Oct): the block goes after the free-memory section, so the tour reads top to bottom
anchor = '<section id="free-ram">' if os.environ.get("TH_FLAVOR") == "client" and '<section id="free-ram">' in h else '<section class="story">'
i = h.index(anchor); j = h.index('</section>', i) + len('</section>')
h = h[:j] + "\n\n" + block + h[j:]  # the by-memory matrix is generated by build_indepth_page.py from the run
if os.environ.get("TH_FLAVOR") == "client":   # telemetry can't tell a laptop from a desktop: say "machine" on the client page
    for a, b in (("Laptops", "Machines"), ("laptops", "machines"), ("Laptop", "Machine"), ("laptop", "machine")): h = h.replace(a, b)
open(page, "w", encoding="utf-8").write(h)
print("inserted;", [(k, verdict(S[k], 10 if k in UNIT else 2)[0]) for k, *_ in ROWS])
