"""
One-shot migration: set root_path = name for all projects
where root_path is currently an absolute path.

Dry-run by default. Pass --apply to commit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
import os, json, sys
from pathlib import Path

DRY_RUN = '--apply' not in sys.argv

env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('\'"'))

import psycopg
from psycopg.rows import dict_row

cfg = json.loads(Path('config.json').read_text())

def find_driver(o):
    if isinstance(o, dict):
        if o.get('type') == 'postgres' and 'config' in o:
            return o['config']
        for v in o.values():
            r = find_driver(v)
            if r:
                return r
    return None

dc = find_driver(cfg)
pw = os.environ.get(dc.get('password_env', ''))

conn = psycopg.connect(
    host=dc['host'], port=dc['port'],
    dbname=dc['dbname'], user=dc['user'],
    password=pw, connect_timeout=15,
    row_factory=dict_row,
)
conn.autocommit = False
cur = conn.cursor()

# Show what will be changed
cur.execute("""
    SELECT id, name, root_path
    FROM projects
    WHERE root_path LIKE '/%' AND deleted = FALSE
    ORDER BY name
""")
rows = cur.fetchall()

print(f"Projects to update ({len(rows)}):")
for r in rows:
    print(f"  {r['name']:35} | '{r['root_path']}' -> '{r['name']}'")

if DRY_RUN:
    print()
    print('DRY RUN — no changes made. Pass --apply to commit.')
    conn.rollback()
    conn.close()
    sys.exit(0)

# Apply
cur.execute("""
    UPDATE projects
    SET root_path = name
    WHERE root_path LIKE '/%' AND deleted = FALSE
""")
print(f'\nUpdated {cur.rowcount} rows.')
conn.commit()
print('COMMITTED.')

# Verify
cur.execute("""
    SELECT COUNT(*) AS still_absolute
    FROM projects
    WHERE root_path LIKE '/%' AND deleted = FALSE
""")
res = cur.fetchone()
print(f'Remaining absolute root_paths: {res["still_absolute"]}')

conn.close()
