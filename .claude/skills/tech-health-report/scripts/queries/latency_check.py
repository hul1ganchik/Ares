"""Latency accuracy check for one account: three independent gateway-latency sources per user, plus clamp/sentinel shares.
1 Session Score Container.pcgLatency (what the report scores), 2 PCG health probe 'Latency: N' (AppTraces, frequent),
3 PCG connected 'latency' (per connection). Also Device.networkLatency (internet) for the placement gap.
Usage: python -I latency_check.py <account> <ws> <we> <out.json>"""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile
WS = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"
A = r"""
let ws = datetime({ws}); let we = datetime({we});
AppEvents
| where TimeGenerated >= ws and TimeGenerated < we and Name == 'Session Score'
| where tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33'
| extend G = iff(Acct == '{acct}', 'acct', 'others'), Pcg = todouble(Measurements['Container.pcgLatency']), Net = todouble(Measurements['Device.networkLatency'])
| summarize N=count(), Neg=countif(Pcg<=0), Clamp=countif(Pcg>=999), P50=percentile(iff(Pcg>0,Pcg,real(null)),50), P90=percentile(iff(Pcg>0,Pcg,real(null)),90),
    NetP50=percentile(iff(Net>0,Net,real(null)),50) by G
"""
B = r"""
let ws = datetime({ws}); let we = datetime({we});
AppTraces
| where TimeGenerated >= ws and TimeGenerated < we and Message has 'PCG health'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33'
| extend G = iff(Acct == '{acct}', 'acct', 'others'), L = todouble(extract(@'Latency:\s*([0-9]+)', 1, Message)),
    Resp = Message has 'Probing      : Responsive', Roam = Message has 'Need to roam : True'
| summarize N=count(), WithLat=countif(isnotnull(L)), NotResp=countif(not(Resp)), NeedRoam=countif(Roam), Clamp=countif(L>=999),
    P50=percentile(L,50), P90=percentile(L,90) by G
"""
PU = r"""
let ws = datetime({ws}); let we = datetime({we});
let s = AppEvents
| where TimeGenerated >= ws and TimeGenerated < we and Name == 'Session Score' and tolower(tostring(Properties.Account)) == '{acct}'
| extend Pcg = todouble(Measurements['Container.pcgLatency']), Net = todouble(Measurements['Device.networkLatency'])
| summarize SsN=countif(Pcg>0), SsP50=percentile(iff(Pcg>0,Pcg,real(null)),50), NetP50=percentile(iff(Net>0,Net,real(null)),50) by U=tolower(UserAuthenticatedId);
let h = AppTraces
| where TimeGenerated >= ws and TimeGenerated < we and Message has 'PCG health' and tolower(tostring(Properties.Account)) == '{acct}'
| extend L = todouble(extract(@'Latency:\s*([0-9]+)', 1, Message))
| summarize HN=countif(isnotnull(L)), HP50=percentile(L,50), NeedRoam=countif(Message has 'Need to roam : True') by U=tolower(UserAuthenticatedId);
let c = AppEvents
| where TimeGenerated >= ws and TimeGenerated < we and Name == 'PCG connected' and tolower(tostring(Properties.Account)) == '{acct}'
| extend L = todouble(Measurements['latency'])
| summarize CN=countif(L>0), CP50=percentile(iff(L>0,L,real(null)),50) by U=tolower(UserAuthenticatedId);
s | join kind=fullouter h on U | join kind=fullouter c on U
| project U=coalesce(U, U1, U2), SsN, SsP50, NetP50, HN, HP50, NeedRoam, CN, CP50
"""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

acct, ws, we, out = sys.argv[1:5]
f = dict(acct=acct, ws=ws, we=we)
res = {"session_score": q(A.format(**f)), "pcg_health": q(B.format(**f)), "per_user": q(PU.format(**f))}
json.dump(res, open(out, "w", encoding="utf-8"))
print(json.dumps({k: v for k, v in res.items() if k != "per_user"}, indent=1)); print("per-user rows", len(res["per_user"]))
