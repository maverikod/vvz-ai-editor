"""
Read-only diagnostic: show all projects root_path format
and files.relative_path coverage per group.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
import os, json, sys
from pathlib import Path

# Load .env
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
conn.autocommit = True
cur = conn.cursor()

print('=== projects: id | name | root_path | format ===')
cur.execute("""
    SELECT id, name, root_path,
        CASE
            WHEN root_path LIKE '/%' THEN 'ABSOLUTE'
            WHEN root_path = name    THEN 'NAME_ONLY_OK'
            ELSE                          'OTHER'
        END AS fmt
    FROM projects
    WHERE deleted = FALSE
    ORDER BY fmt, name
""")
for r in cur.fetchall():
    print(f"  {r['fmt']:15} | {r['name']:35} | {r['root_path']}")

print()
print('=== files.relative_path coverage by root_path format ===')
cur.execute("""
    SELECT
        CASE
            WHEN p.root_path LIKE '/%' THEN 'ABSOLUTE'
            WHEN p.root_path = p.name  THEN 'NAME_ONLY_OK'
            ELSE                            'OTHER'
        END AS fmt,
        COUNT(f.id)                                                               AS total_files,
        COUNT(f.relative_path) FILTER (WHERE f.relative_path IS NOT NULL
                                         AND f.relative_path != '')               AS with_rel,
        COUNT(f.id)            FILTER (WHERE f.relative_path IS NULL
                                          OR f.relative_path = '')                AS without_rel
    FROM projects p
    LEFT JOIN files f
           ON f.project_id = p.id
          AND (f.deleted = FALSE OR f.deleted IS NULL)
    WHERE p.deleted = FALSE
    GROUP BY 1
    ORDER BY 1
""")
for r in cur.fetchall():
    print(f"  {r['fmt']:15} | total={r['total_files']:6} | with_rel={r['with_rel']:6} | without_rel={r['without_rel']:6}")

conn.close()
