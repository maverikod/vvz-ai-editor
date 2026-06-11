"""Temporary script to list plans directory."""

import os

base = "/home/vasilyvz/projects/tools/ai_editor/docs/plans"
for name in [
    "2026-04-30-mcp-db-rpc-priority-lanes",
    "2026-04-30-workers-fresh-files-first",
]:
    p = os.path.join(base, name)
    if os.path.isdir(p):
        files = sorted(os.listdir(p))
        print(f"=== {name} ===")
        for f in files:
            fp = os.path.join(p, f)
            print(f"--- {f} ---")
            print(open(fp).read())
    elif os.path.isfile(p):
        print(f"=== {name} ===")
        print(open(p).read())
    else:
        print(f"{name}: NOT FOUND")
import os

p = "/home/vasilyvz/projects/tools/ai_editor/docs/plans"
if os.path.isdir(p):
    for f in sorted(os.listdir(p)):
        print(f)
else:
    print("NOT FOUND")
