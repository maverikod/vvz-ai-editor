"""Touch files to force reindex."""
import os, time
files = [
    '/home/vasilyvz/projects/tools/cst_mcp_sandbox_20260501/mcp_cst_workspace/test_inline_ids.py',
]
for f in files:
    t = time.time()
    os.utime(f, (t, t))
    print(f'Touched: {f}')
