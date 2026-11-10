"""Why do one account's 8 GB users swap more than other customers' 8 GB users?
Per user, fleet-wide (os33 excluded), one window: free RAM at container start, hardware/security context,
apps launched (set + counts), commit charge level, and the swapping measure. Writes runs/why8_<ws>_<we>.json.
Usage: python -I why_8gb.py <ws> <we>"""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile
WS = "32fa3f43-8bb5-40a6-9163-88e71f54b7f8"
BASE = """let ws = datetime({ws}); let we = datetime({we});
let base = AppEvents | where TimeGenerated >= ws and TimeGenerated < we
| where tostring(Properties.CategoryName) == 'LocalZone Container Windows'
| extend Acct = tolower(tostring(Properties.Account)) | where Acct != 'os33' and isnotempty(UserAuthenticatedId)
| extend U = tolower(UserAuthenticatedId);
"""
Q = {
 "start": BASE + """base | where Name == 'Container started'
| extend Tot = todouble(Measurements['TotalPhysicalMemory']), Av = todouble(Measurements['AvailablePhysicalMemory'])
| summarize Starts=count(), TotMiB=max(Tot), AvP50=percentile(Av,50), AvP10=percentile(Av,10), Cpu=take_any(tostring(Properties.CpuName)),
  Cores=max(toint(Properties.CpuNumberOfCores)), Logical=max(toint(Properties.CpuNumberOfLogicalProcessors)), Model=take_any(tostring(Properties.ComputerVersion)),
  Mfr=take_any(tostring(Properties.ComputerManufacturer)), AV=take_any(tostring(Properties.AntivirusDisplayName)), AVn=max(toint(Properties.AntivirusCount)),
  Os=take_any(tostring(Properties.OsCaption)), Ext=max(strlen(tostring(Properties.BrowsersExtensions))), Rmm=take_any(tostring(Properties.RmmTools)),
  Office=take_any(tostring(Properties.MicrosoftOfficeVersions)) by U, Acct""",
 "ss": BASE + """base | where Name == 'Session Score'
| extend HF = todouble(Measurements['Device.memoryHardFaults']), Mem = todouble(Measurements['Device.memoryUsage']), Cpu = todouble(Measurements['Device.cpuLoad'])
| summarize N=count(), Days=dcount(startofday(TimeGenerated)), HF500=countif(HF>=500), HF2000=countif(HF>=2000), MemP50=percentile(Mem,50), Mem95=countif(Mem>=95),
  CpuP50=percentile(Cpu,50), Hours=dcount(bin(TimeGenerated,1h)) by U, Acct""",
 "apps": BASE + """base | where Name == 'App launched'
| extend App = tostring(Properties.appName) | where isnotempty(App) and App !startswith 'Workplace' and App !in~ ('File Explorer','explorer.exe')
| summarize L=count() by U, Acct, App
| summarize Apps=make_bag(bag_pack(App, L)), Distinct=count(), Launches=sum(L) by U, Acct""",
}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache

ws, we = sys.argv[1:3]
out = {k: q(v.format(ws=ws, we=we)) for k, v in Q.items()}
for k, v in out.items(): print(k, len(v))
root = os.environ.get("TH_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # data folder (runs/, <account>/); build_indepth sets TH_HOME
json.dump(out, open(os.path.join(root, "runs", f"why8_{ws}_{we}.json"), "w", encoding="utf-8"))
