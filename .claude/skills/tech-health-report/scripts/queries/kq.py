"""Run one KQL file against venn-apps and print or save rows. Usage: python -I kq.py <file.kql> [out.json]
Optional third/fourth args: key=value pairs substituted into {key} placeholders in the file (e.g. ws=2026-09-21 we=2026-10-19)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thq import q  # shared transport + cache
kql = open(sys.argv[1], encoding="utf-8").read()
out = sys.argv[2] if len(sys.argv) > 2 and "=" not in sys.argv[2] else None
for kv in [a for a in sys.argv[2:] if "=" in a]:
    k, v = kv.split("=", 1); kql = kql.replace("{" + k + "}", v)
rows = q(kql)
if out: json.dump(rows, open(out, "w", encoding="utf-8")); print(len(rows), "rows ->", out)
else:
    for r in rows: print(r)
