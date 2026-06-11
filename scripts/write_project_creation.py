"""Helper: overwrite project_creation.py with new bootstrapped version."""

import base64

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent

SRC_TXT = ROOT / "scripts" / "_bootstrap_pm.txt"

TARGET = ROOT / "scripts" / "bootstrap_existing.py"


b64 = SRC_TXT.read_text(encoding="utf-8").strip()

raw = base64.b64decode(b64)

TARGET.write_bytes(raw)

print(f"OK: wrote {TARGET} ({len(raw)} bytes)")
