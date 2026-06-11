#!/usr/bin/env python3
"""Embed CURRENT FILE CONTENT into modify_file atomic steps (a8 compliance)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PLAN_ROOT = Path(__file__).resolve().parents[1] / "docs/plans/ai-editor-thin-server"
REPO_ROOT = Path(__file__).resolve().parents[1]

CONTENT_MARKER = "CURRENT FILE CONTENT"
CONTENT_RE = re.compile(
    r"CURRENT FILE CONTENT[^\n]*:\n```[^\n]*\n.*?```\n*",
    re.DOTALL,
)
CREATE_CODE_RE = re.compile(r"```(?:py|python)\n(.*?)```", re.DOTALL)


def g_sort_key(gdir: Path) -> int:
    m = re.search(r"G-(\d+)", gdir.name)
    return int(m.group(1)) if m else 999


def t_sort_key(tdir: Path) -> int:
    m = re.search(r"T-(\d+)", tdir.name)
    return int(m.group(1)) if m else 999


def topo_g_order() -> dict[str, int]:
    g_data: dict[str, dict] = {}
    for gp in PLAN_ROOT.glob("G-*/README.yaml"):
        g = yaml.safe_load(gp.read_text(encoding="utf-8"))
        g_data[g["step_id"]] = g

    deps: dict[str, set[str]] = {
        gid: set(g.get("depends_on") or []) for gid, g in g_data.items()
    }
    order: dict[str, int] = {}
    visited: set[str] = set()

    def visit(gid: str) -> int:
        if gid in order:
            return order[gid]
        if gid in visited:
            return g_sort_key_from_id(gid)
        visited.add(gid)
        if not deps.get(gid):
            rank = 0
        else:
            rank = max(visit(d) for d in deps[gid]) + 1
        order[gid] = rank
        return rank

    def g_sort_key_from_id(gid: str) -> int:
        for gp in PLAN_ROOT.glob("G-*/README.yaml"):
            g = yaml.safe_load(gp.read_text(encoding="utf-8"))
            if g["step_id"] == gid:
                return g_sort_key(gp.parent)
        return 999

    for gid in sorted(g_data):
        visit(gid)
    return order


def g_id_from_path(af: Path) -> str:
    gdir = af.parent.parent.parent
    return yaml.safe_load((gdir / "README.yaml").read_text(encoding="utf-8"))["step_id"]


def collect_all_steps() -> list[dict]:
    g_order = topo_g_order()
    items = []
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        gid = g_id_from_path(af)
        items.append(
            {
                "af": af,
                "ad": ad,
                "tf": ad.get("target_file", ""),
                "sort": (
                    g_order.get(gid, 999),
                    g_sort_key(af.parent.parent.parent),
                    t_sort_key(af.parent.parent),
                    ad.get("priority", 0),
                    ad.get("step_id", ""),
                ),
            }
        )
    items.sort(key=lambda x: x["sort"])
    return items


def create_body_from_prompt(prompt: str) -> str | None:
    blocks = CREATE_CODE_RE.findall(prompt)
    if not blocks:
        return None
    return max(blocks, key=lambda b: len(b.splitlines()))


def fence_for_path(tf: Path) -> str:
    if tf.suffix in {".py", ".json"}:
        return tf.suffix.lstrip(".")
    if tf.suffix == ".md":
        return "markdown"
    return ""


def embed_content(prompt: str, tf: str, content: str) -> str:
    prompt = CONTENT_RE.sub("", prompt).lstrip("\n")
    ext = fence_for_path(Path(tf))
    block = f"{CONTENT_MARKER} (`{tf}`):\n```{ext}\n{content}\n```\n\n"
    return block + prompt


def resolve_content(tf: str, states: dict[str, str]) -> str | None:
    if tf in states:
        return states[tf]
    repo_path = REPO_ROOT / tf
    if repo_path.is_file():
        return repo_path.read_text(encoding="utf-8")
    return None


def main() -> int:
    items = collect_all_steps()
    states: dict[str, str] = {}
    updated = 0
    missing = []
    over_400 = []

    for it in items:
        ad, af = it["ad"], it["af"]
        tf = it["tf"]
        if not tf:
            continue
        op = ad.get("operation")
        prompt = ad.get("prompt", "")

        if op == "create_file":
            body = create_body_from_prompt(prompt)
            if body is not None:
                states[tf] = body
            continue
        if op == "delete_file":
            states.pop(tf, None)
            continue
        if op != "modify_file":
            continue

        cumulative = resolve_content(tf, states)
        if cumulative is None:
            missing.append((ad["step_id"], tf))
            cumulative = ""

        line_count = len(cumulative.splitlines()) if cumulative else 0
        if line_count > 400:
            over_400.append((ad["step_id"], tf, line_count))

        ad["prompt"] = embed_content(prompt, tf, cumulative)
        af.write_text(
            yaml.dump(ad, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        updated += 1

    print(f"Updated {updated} modify_file AS")
    if missing:
        print(f"Missing baseline ({len(missing)}):")
        for aid, tf in missing:
            print(f"  {aid} {tf}")
    if over_400:
        print(f"a3 warnings embedded >400 lines ({len(over_400)}):")
        for aid, tf, n in over_400:
            print(f"  {aid} {tf}: {n} lines")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
