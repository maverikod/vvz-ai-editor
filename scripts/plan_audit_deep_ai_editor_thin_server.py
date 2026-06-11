#!/usr/bin/env python3
"""Deep audit beyond plan_verify — catches shallow-green gaps."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_rebuild_chains import (  # noqa: E402
    apply_modify,
    clean_a5,
    create_body,
    extract_embedded_body,
    normalize_file_text,
    task_tail,
)

PLAN_ROOT = Path(__file__).resolve().parents[1] / "docs/plans/ai-editor-thin-server"
REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 400

CREATE_CODE_RE = re.compile(r"```(?:py|python)\n(.*?)```", re.DOTALL)

# Broader than plan_verify a5
CROSS_REF_RE = re.compile(
    r"\bG-\d{3}\b"
    r"|\bT-\d{3}\b"
    r"|\bA-\d{3}\b"
    r"|\(priority\s+\d+\)"
    r"|\bpriority\s+\d+\s+on\b"
    r"|\bAfter\s+G-\d+"
    r"|\bfrom\s+G-\d+"
    r"|\bDo not change\b.*\bT-\d"
    r"|\bRequires\b.*\bG-\d"
    r"|\bв\s+G-\d"
    r"|\bпосле\s+G-"
    r"|\bG-001\b|\bG-002\b|\bG-003\b|\bG-004\b|\bG-005\b|\bG-006\b|\bG-007\b",
    re.IGNORECASE,
)

OTHER_FILE_RE = re.compile(
    r"`([a-zA-Z0-9_./-]+\.(?:py|json|md|yaml))`"
    r"|(?:modify|create|delete|touch|update)\s+[`']?([a-zA-Z0-9_./-]+\.py)"
    r"|(?:and|or)\s+`([a-zA-Z0-9_./-]+\.py)`",
    re.IGNORECASE,
)

FAKE_DELETE_RE = re.compile(
    r"delete\s+existing|Delete\s+existing|удалить\s+существующ",
    re.IGNORECASE,
)


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
    deps = {gid: set(g.get("depends_on") or []) for gid, g in g_data.items()}
    order: dict[str, int] = {}
    visited: set[str] = set()

    def visit(gid: str) -> int:
        if gid in order:
            return order[gid]
        if gid in visited:
            return 0
        visited.add(gid)
        rank = 0 if not deps.get(gid) else max(visit(d) for d in deps[gid]) + 1
        order[gid] = rank
        return rank

    for gid in sorted(g_data):
        visit(gid)
    return order


def g_id_from_af(af: Path) -> str:
    return yaml.safe_load(
        (af.parent.parent.parent / "README.yaml").read_text(encoding="utf-8")
    )["step_id"]


def collect_steps() -> list[dict]:
    g_order = topo_g_order()
    out = []
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        gid = g_id_from_af(af)
        out.append(
            {
                "af": af,
                "ad": ad,
                "gid": gid,
                "tid": ad.get("parent_tactical_step"),
                "sort": (
                    g_order.get(gid, 999),
                    g_sort_key(af.parent.parent.parent),
                    t_sort_key(af.parent.parent),
                    ad.get("priority", 0),
                    ad.get("step_id", ""),
                ),
            }
        )
    out.sort(key=lambda x: x["sort"])
    return out


def main() -> int:
    findings: list[tuple[str, str]] = []

    def add(cat: str, msg: str) -> None:
        findings.append((cat, msg))

    steps = collect_steps()
    g_order = topo_g_order()

    # --- G README: listed TS exist ---
    for gp in PLAN_ROOT.glob("G-*/README.yaml"):
        g = yaml.safe_load(gp.read_text(encoding="utf-8"))
        gid = g["step_id"]
        gdir = gp.parent
        for tid in g.get("tactical_steps") or []:
            matches = list(gdir.glob(f"T-*{tid.split('-')[1]}*/README.yaml")) + list(
                gdir.glob(f"*/T-{tid.split('-')[1]}-*/README.yaml")
            )
            # simpler: any T dir with step_id in README
            found = False
            for tp in gdir.glob("T-*/README.yaml"):
                t = yaml.safe_load(tp.read_text(encoding="utf-8"))
                if t.get("step_id") == tid:
                    found = True
                    break
            if not found:
                add("G-TS-sync", f"{gid} lists {tid} but no T README")

    # --- per-TS AS sync, a6 priority within (file, TS) ---
    for tp in PLAN_ROOT.glob("G-*/T-*/README.yaml"):
        t = yaml.safe_load(tp.read_text(encoding="utf-8"))
        tid = t["step_id"]
        listed = set(t.get("atomic_steps") or [])
        as_dir = tp.parent / "atomic_steps"
        pri_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
        as_ids_in_dir: set[str] = set()

        for af in as_dir.glob("*.yaml"):
            ad = yaml.safe_load(af.read_text(encoding="utf-8"))
            aid = ad.get("step_id", "")
            as_ids_in_dir.add(aid)
            if aid not in listed:
                add("TS-sync", f"{tid}: orphan file {af.name} ({aid})")
            tf = ad.get("target_file", "")
            if tf and ad.get("priority") is not None:
                pri_by_file[tf].append((ad["priority"], aid))

        for aid in listed:
            if aid not in as_ids_in_dir:
                add("TS-sync", f"{tid}: listed {aid} but no yaml")

        for tf, pris in pri_by_file.items():
            seen: dict[int, str] = {}
            for p, aid in pris:
                if p in seen:
                    add("a6", f"{tid} {tf}: priority {p} on {aid} and {seen[p]}")
                seen[p] = aid

    # --- global priority per file (cross-TS within plan order) ---
    global_pri: dict[str, list[tuple]] = defaultdict(list)
    for it in steps:
        ad = it["ad"]
        tf = ad.get("target_file")
        if tf and ad.get("priority") is not None:
            global_pri[tf].append((it["sort"], ad["priority"], it["gid"], it["tid"], ad["step_id"]))

    # --- simulate file state + a8 cross-chain ---
    states: dict[str, str] = {}
    state_origin: dict[str, str] = {}

    for it in steps:
        ad, af = it["ad"], it["af"]
        tf = ad.get("target_file", "")
        op = ad.get("operation", "")
        prompt = ad.get("prompt", "")

        # a5 broad — task tail only for modify_file (not embedded repo bodies)
        a5_text = task_tail(prompt) if op == "modify_file" else prompt
        if CROSS_REF_RE.search(a5_text):
            m = CROSS_REF_RE.search(a5_text)
            add("a5-deep", f"{ad['step_id']} ({af.name}): cross-ref '{m.group(0) if m else '?'}'")

        # a2 one-file: other paths in prompt
        if tf:
            for m in OTHER_FILE_RE.finditer(prompt):
                other = next(g for g in m.groups() if g)
                if other and other != tf and not other.endswith("schema.py"):
                    # metadata/schema siblings often referenced
                    if "metadata" in other or "schema" in other:
                        continue
                    if other.startswith("tests/"):
                        add("a2", f"{ad['step_id']}: mentions other file `{other}` (target {tf})")

        # fake delete without delete_file op
        if op == "create_file" and FAKE_DELETE_RE.search(prompt):
            add("split-fake", f"{ad['step_id']}: prose 'delete existing' but operation is create_file only")

        if op == "create_file" and tf:
            body = create_body(prompt)
            if body:
                states[tf] = body
                state_origin[tf] = f"{ad['step_id']} create"
            continue
        if op == "delete_file" and tf:
            states.pop(tf, None)
            state_origin.pop(tf, None)
            continue

        if op == "modify_file" and tf:
            embedded = extract_embedded_body(prompt)
            if embedded is None:
                add("a8", f"{ad['step_id']}: no CURRENT FILE CONTENT")
                continue
            en = len(embedded.splitlines())
            if en > MAX_LINES:
                add("a3", f"{ad['step_id']} {tf}: embedded {en} lines")

            expected = states.get(tf)
            if expected is None:
                repo = REPO_ROOT / tf
                if repo.is_file():
                    expected = repo.read_text(encoding="utf-8")
                    exp_src = "repo"
                else:
                    exp_src = "missing"
                    expected = ""
            else:
                exp_src = state_origin.get(tf, "simulated")

            if normalize_file_text(embedded) != normalize_file_text(expected or ""):
                add(
                    "a8-chain",
                    f"{ad['step_id']} {tf}: embedded body != post-prior state "
                    f"(expected from {exp_src}, {len(expected.splitlines())} lines, "
                    f"embedded {en} lines)",
                )
            else:
                tail = clean_a5(task_tail(prompt))
                states[tf] = apply_modify(embedded, tf, tail)
                state_origin[tf] = f"{ad['step_id']} modify"

    # --- depends_on dangling ---
    as_by_id: dict[tuple[str, str], dict] = {}
    for it in steps:
        key = (it["tid"], it["ad"]["step_id"])
        as_by_id[key] = it["ad"]

    for it in steps:
        ad = it["ad"]
        for dep in ad.get("depends_on") or []:
            if (it["tid"], dep) not in as_by_id:
                add("a7", f"{ad['step_id']}: depends_on {dep} missing in TS {it['tid']}")

    # --- create imports non-existent modules (heuristic) ---
    for it in steps:
        ad = it["ad"]
        if ad.get("operation") != "create_file":
            continue
        body = create_body(ad.get("prompt", ""))
        if not body:
            continue
        tf = ad.get("target_file", "")
        for imp in re.findall(r"from \.(\w+) import|from \.(\w+\.\w+) import", body):
            mod = next(x for x in imp if x)
            # check if planned create exists
            sibling = str(Path(tf).parent / f"{mod.split('.')[-1]}.py")
            planned = {s["ad"].get("target_file") for s in steps if s["ad"].get("operation") == "create_file"}
            repo_exists = (REPO_ROOT / sibling).is_file()
            if sibling not in planned and not repo_exists and "schema" in mod:
                add("a4-import", f"{ad['step_id']}: imports .{mod} but {sibling} not in plan/repo")

    # --- modify count vs reported ---
    modify_count = sum(1 for s in steps if s["ad"].get("operation") == "modify_file")

    print(f"Deep audit: {PLAN_ROOT}")
    print(f"AS total: {len(steps)}, modify_file: {modify_count}")
    print(f"Findings: {len(findings)}")
    by: dict[str, list[str]] = defaultdict(list)
    for c, m in findings:
        by[c].append(m)
    for c in sorted(by):
        print(f"\n[{c}] {len(by[c])}")
        for m in by[c][:12]:
            print(f"  - {m}")
        if len(by[c]) > 12:
            print(f"  ... +{len(by[c]) - 12} more")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
