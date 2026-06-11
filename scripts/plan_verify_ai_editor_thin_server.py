#!/usr/bin/env python3
"""Verify ai-editor-thin-server plan against planning standards (strict)."""
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
    collect_steps,
    create_body,
    extract_embedded_body,
    normalize_file_text,
    task_tail,
)

PLAN_ROOT = Path(__file__).resolve().parents[1] / "docs/plans/ai-editor-thin-server"
REPO_ROOT = Path(__file__).resolve().parents[1]

FILE_PATH_RE = re.compile(
    r"\b(ai_editor|tests|client)/[a-zA-Z0-9_./-]+"
    r"|\.py\b|\.json\b"
    r"|\bOpenCommand\b|\bCloseCommand\b"
    r"|\bUniversalFile\w+Command\b"
    r"|\bhooks\.py\b|\bconfig\.json\b"
)
CROSS_STEP_RE = re.compile(
    r"\bG-\d{3}\b|\bT-\d{3}\b(?!\s*open-orchestration)"
    r"|после G-|from G-|Requires .+ T-\d"
)
CROSS_AS_PROMPT_RE = re.compile(
    r"\bG-\d{3}\b"
    r"|\bT-\d{3}\b"
    r"|\bA-\d{3}\b"
    r"|\(priority\s+\d+\)"
    r"|\bAfter\s+G-\d+"
    r"|\bfrom\s+G-\d+"
    r"|\bDo not delete .+ \(G-\d+"
)
FAKE_DELETE_RE = re.compile(
    r"delete\s+existing|Delete\s+monolithic|Delete\s+existing",
    re.IGNORECASE,
)
OPEN_DECISION_RE = re.compile(
    r"\bas appropriate\b|\bif needed\b|\bTBD\b|\badd necessary imports\b"
    r"|\bfollowing the existing pattern\b",
    re.IGNORECASE,
)
CREATE_PY_RE = re.compile(r"```(?:py|python)\n(.*?)```", re.DOTALL)
MAX_FILE_LINES = 400
def embedded_body(prompt: str) -> str | None:
    m4 = re.search(
        r"CURRENT FILE CONTENT[^\n]*:\n````(?:md|markdown)\n(.*?)````",
        prompt,
        re.DOTALL,
    )
    if m4:
        return m4.group(1)
    m3 = re.search(
        r"CURRENT FILE CONTENT[^\n]*:\n```[^\n]*\n(.*?)```",
        prompt,
        re.DOTALL,
    )
    return m3.group(1) if m3 else None


def main() -> int:
    findings: list[tuple[str, str]] = []

    def add(check: str, msg: str) -> None:
        findings.append((check, msg))

    spec = yaml.safe_load((PLAN_ROOT / "spec.yaml").read_text(encoding="utf-8"))
    concepts = {c["concept_id"]: c for c in spec["concepts"]}
    hrs = (PLAN_ROOT / "source_spec.md").read_text(encoding="utf-8").splitlines()

    covered: set[int] = set()
    for c in concepts.values():
        for sr in c.get("source_ranges", []):
            covered.update(range(sr["start"], sr["end"] + 1))

    in_nb = False
    for i, line in enumerate(hrs, 1):
        if "<!-- non-binding -->" in line:
            in_nb = True
        if "<!-- /non-binding -->" in line:
            in_nb = False
        if in_nb:
            continue
        if re.match(r"\{[a-z0-9]{4}\}", line) and i not in covered:
            add("c2", f"HRS labeled line {i} not in MRS source_ranges")

    def rk(r: dict) -> tuple:
        return (r["from_concept"], r["to_concept"], r["type"])

    mrs_rels = {rk(r) for r in spec["relations"]}
    g_concepts: dict[str, set[str]] = {}
    all_g_rels: set[tuple] = set()

    for gp in sorted(PLAN_ROOT.glob("G-*/README.yaml")):
        g = yaml.safe_load(gp.read_text(encoding="utf-8"))
        gid = g["step_id"]
        g_concepts[gid] = set(g.get("concepts", []))
        desc = g.get("description", "")
        if re.search(r"\bEditSession\b", desc):
            add("G-conceptual", f"{gid}: class name EditSession in G description")
        for r in g.get("relations", []):
            k = rk(r)
            all_g_rels.add(k)
            if k not in mrs_rels:
                add("I1b-G", f"{gid} relation {k} not in MRS")

    for cid in concepts:
        if cid not in set().union(*g_concepts.values()):
            add("I1a", f"{cid} not in any G concepts")
    for k in mrs_rels - all_g_rels:
        add("I1b-M", f"MRS relation {k} not in any G")

    for tp in sorted(PLAN_ROOT.glob("G-*/T-*/README.yaml")):
        t = yaml.safe_load(tp.read_text(encoding="utf-8"))
        tid = t["step_id"]
        parent = t["parent_global_step"]
        desc = t.get("description", "")

        for c in t.get("concepts", []):
            if c not in g_concepts.get(parent, set()):
                add("t6", f"{tid}: {c} not in {parent}")

        if FILE_PATH_RE.search(desc):
            add("t-forbidden", f"{tid}: path/class leak in description")
        if CROSS_STEP_RE.search(desc):
            add("t8", f"{tid}: cross-step ref in description")

        for section in ("inputs", "outputs"):
            for item in t.get(section, []) or []:
                d = item.get("description", "")
                if FILE_PATH_RE.search(d):
                    add("t-forbidden", f"{tid}: path in {section}.{item.get('name')}")
                if CROSS_STEP_RE.search(d):
                    add("t8", f"{tid}: cross-step ref in {section}.{item.get('name')}")

        listed = t.get("atomic_steps") or []
        as_dir = tp.parent / "atomic_steps"
        for aid in listed:
            if not [
                f
                for f in as_dir.glob("*.yaml")
                if yaml.safe_load(f.read_text(encoding="utf-8")).get("step_id") == aid
            ]:
                add("TS-sync", f"{tid}: missing AS {aid}")

        ts_c = set(t.get("concepts", []))
        for af in as_dir.glob("*.yaml"):
            ad = yaml.safe_load(af.read_text(encoding="utf-8"))
            if ad.get("step_id") not in listed:
                add("TS-sync", f"{tid}: orphan {af.name}")
            prompt = ad.get("prompt", "")
            for c in ad.get("concepts", []):
                if c not in ts_c:
                    add("a1", f"{ad['step_id']}: {c} not in TS {tid}")
            a5_text = (
                task_tail(prompt)
                if ad.get("operation") == "modify_file"
                else prompt
            )
            if CROSS_AS_PROMPT_RE.search(a5_text):
                add("a5", f"{ad['step_id']} ({af.name}): cross-step ref in prompt")
            if ad.get("operation") == "modify_file":
                if "CURRENT FILE CONTENT" not in prompt.upper():
                    add("a8", f"{ad['step_id']} ({af.name}): no file body in prompt")
                else:
                    body = embedded_body(prompt)
                    if body is not None:
                        n = len(body.splitlines())
                        if n > MAX_FILE_LINES:
                            add(
                                "a3",
                                f"{ad['step_id']} ({ad.get('target_file')}): "
                                f"embedded file {n} lines > {MAX_FILE_LINES}",
                            )
                tail = task_tail(prompt)
                if OPEN_DECISION_RE.search(clean_a5(tail)):
                    add("a4", f"{ad['step_id']} ({af.name}): open decision in modify task tail")
            elif ad.get("operation") == "create_file":
                if FAKE_DELETE_RE.search(prompt):
                    add("split-fake", f"{ad['step_id']}: delete prose in create_file")
                if OPEN_DECISION_RE.search(prompt):
                    add("a4", f"{ad['step_id']} ({af.name}): open decision in create prompt")
                blocks = CREATE_PY_RE.findall(prompt)
                if not blocks:
                    add(
                        "a4",
                        f"{ad['step_id']} ({ad.get('target_file')}): "
                        "create_file missing ```py body (a4 self-sufficiency)",
                    )
                else:
                    body = max(blocks, key=lambda b: len(b.splitlines()))
                    n = len(body.splitlines())
                    if n > MAX_FILE_LINES:
                        add(
                            "a3",
                            f"{ad['step_id']} ({ad.get('target_file')}): "
                            f"create body {n} lines > {MAX_FILE_LINES}",
                        )
                    if "def " not in body and "class " not in body:
                        add(
                            "a4",
                            f"{ad['step_id']} ({ad.get('target_file')}): "
                            "create ```py lacks def/class",
                        )
                    tf = ad.get("target_file", "")
                    if (
                        tf
                        and not tf.startswith("tests/")
                        and "import " not in body
                        and "from " not in body
                    ):
                        add(
                            "a4",
                            f"{ad['step_id']} ({tf}): create body lacks import statements",
                        )
            # a7 depends_on within TS
            as_ids_in_dir = {
                yaml.safe_load(f.read_text(encoding="utf-8")).get("step_id")
                for f in as_dir.glob("*.yaml")
            }
            for dep in ad.get("depends_on") or []:
                if dep not in as_ids_in_dir:
                    add("a7", f"{ad['step_id']}: depends_on {dep} missing in TS {tid}")
            # a9 verification field
            ver = ad.get("verification") or {}
            vtype = ver.get("type")
            if vtype not in ("pytest", "import", "static_analysis", "manual"):
                add("a9", f"{ad['step_id']}: invalid verification.type {vtype!r}")
            if not ver.get("target") or not str(ver.get("target")).strip():
                add("a9", f"{ad['step_id']}: verification.target empty")
            if not ver.get("expected") or not str(ver.get("expected")).strip():
                add("a9", f"{ad['step_id']}: verification.expected empty")

    # I2: every MRS concept referenced in at least one AS
    as_concepts: set[str] = set()
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        as_concepts.update(yaml.safe_load(af.read_text(encoding="utf-8")).get("concepts") or [])
    for cid in concepts:
        if cid not in as_concepts:
            add("I2", f"{cid} ({concepts[cid]['name']}) not referenced in any AS concepts")

    # a8-chain: cumulative post-prior state (same state machine as plan_rebuild_chains)
    states: dict[str, str] = {}
    state_origin: dict[str, str] = {}
    for it in collect_steps():
        ad = it["ad"]
        tf = ad.get("target_file", "")
        op = ad.get("operation", "")
        prompt = ad.get("prompt", "")

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
        if op != "modify_file" or not tf:
            continue

        embedded = extract_embedded_body(prompt)
        if embedded is None:
            continue
        expected = states.get(tf)
        if expected is None:
            repo = REPO_ROOT / tf
            expected = repo.read_text(encoding="utf-8") if repo.is_file() else ""
            exp_src = "repo" if repo.is_file() else "missing"
        else:
            exp_src = state_origin.get(tf, "simulated")

        if normalize_file_text(embedded) != normalize_file_text(expected):
            add(
                "a8-chain",
                f"{ad['step_id']} {tf}: embedded != post-prior "
                f"({exp_src}, {len(expected.splitlines())} vs {len(embedded.splitlines())} lines)",
            )
        else:
            tail = clean_a5(task_tail(prompt))
            states[tf] = apply_modify(embedded, tf, tail)
            state_origin[tf] = f"{ad['step_id']} modify"

    # a8-chain-dup: identical embed across modify chain on same file
    modify_chains: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        if ad.get("operation") != "modify_file":
            continue
        tf = ad.get("target_file", "")
        body = embedded_body(ad.get("prompt", ""))
        if not tf or not body:
            continue
        modify_chains[tf].append((ad["step_id"], hash(body.strip())))
    for tf, entries in modify_chains.items():
        if len(entries) >= 2 and len({h for _, h in entries}) == 1:
            add(
                "a8-chain-dup",
                f"{tf}: {len(entries)} modify AS share identical CURRENT FILE CONTENT",
            )

    print(f"Plan: {PLAN_ROOT}")
    print(f"Findings: {len(findings)}")
    by: dict[str, list[str]] = defaultdict(list)
    for c, m in findings:
        by[c].append(m)
    for c in sorted(by):
        print(f"\n[{c}] {len(by[c])}")
        for m in by[c][:8]:
            print(f"  - {m}")
        if len(by[c]) > 8:
            print(f"  ... +{len(by[c]) - 8} more")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
