"""Weekly per-user health table, fleet-wide (os33 excluded), 7-day buckets ending at END (exclusive).
Session Score (swapping, frozen, gateway latency, local/gateway drops) + gateway roaming (PCG health checks).
Usage: python -I weekly.py <end_exclusive YYYY-MM-DD> <weeks> <out.json>"""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile
WS = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"
SS = r"""
let we = datetime({we}); let ws = we - {weeks}*7d;
AppEvents
| where TimeGenerated >= ws and TimeGenerated < we
| where Name == 'Session Score' and tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account))
| where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend Wk = toint((we - TimeGenerated) / 7d)
| extend HF = todouble(Measurements['Device.memoryHardFaults']), Fz = todouble(Measurements['Stability.unresponsiveApps']),
         Pcg = todouble(Measurements['Container.pcgLatency']), Net = todouble(Measurements['Device.networkLatency']),
         ND = todouble(Measurements['Device.networkDisconnects']), PD = todouble(Measurements['Container.pcgDisconnects'])
| summarize N=count(), Days=dcount(startofday(TimeGenerated)), HF500=countif(HF>=500), HF2000=countif(HF>=2000), Fz1=countif(Fz>=1),
    PcgP50=percentile(iff(Pcg>0, Pcg, real(null)),50), PcgN=countif(Pcg>0), NetP50=percentile(iff(Net>0, Net, real(null)),50),
    Nd1=countif(ND>0), Pd1=countif(PD>0) by UserAuthenticatedId, Acct, Wk
"""
RO = r"""
let we = datetime({we}); let ws = we - {weeks}*7d;
AppTraces
| where TimeGenerated >= ws and TimeGenerated < we
| where Message has 'PCG health'
| extend Acct = tolower(tostring(Properties.Account))
| where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend Peer = extract(@'PublicIp:\s*([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+', 1, Message)
| where isnotempty(Peer)
| summarize Sites = dcount(Peer) by UserAuthenticatedId, Acct, H = bin(TimeGenerated, 1h)
| extend Wk = toint((we - H) / 7d)
| summarize Hours = count(), RoamHours = countif(Sites >= 2) by UserAuthenticatedId, Acct, Wk
"""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

we, weeks, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
ss = q(SS.format(we=we, weeks=weeks)); print("session rows", len(ss))
ro = q(RO.format(we=we, weeks=weeks)); print("roaming rows", len(ro))
json.dump({"end": we, "weeks": weeks, "pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ss": ss, "roam": ro}, open(out, "w", encoding="utf-8"))
