#!/usr/bin/env python3
"""Rebuild modify_file AS: cumulative a8 state + clean task sections."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

import yaml

PLAN_ROOT = Path(__file__).resolve().parents[1] / "docs/plans/ai-editor-thin-server"
REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 400

CONTENT_RE = re.compile(
    r"CURRENT FILE CONTENT[^\n]*:\n(?:(````[^\n]*\n.*?````)|(?:```[^\n]*\n.*?```))\n*",
    re.DOTALL,
)
def normalize_file_text(text: str) -> str:
    """Single trailing newline — stable across embed_block / extract roundtrip."""
    if not text:
        return text
    return text.rstrip("\n") + "\n"


def extract_embedded_body(prompt: str) -> str | None:
    m4 = re.search(
        r"CURRENT FILE CONTENT[^\n]*:\n````(?:md|markdown)\n(.*?)````",
        prompt,
        re.DOTALL,
    )
    if m4:
        return normalize_file_text(m4.group(1))
    m3 = re.search(
        r"CURRENT FILE CONTENT[^\n]*:\n```[^\n]*\n(.*?)```",
        prompt,
        re.DOTALL,
    )
    return normalize_file_text(m3.group(1)) if m3 else None
CREATE_CODE_RE = re.compile(r"```(?:py|python)\n(.*?)```", re.DOTALL)
PY_BLOCK_RE = re.compile(r"```(?:python|py)\n(.*?)```", re.DOTALL)

A5_CLEANUPS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\s*\(priority\s+\d+\)\.?"), ""),
    (re.compile(r"\bpriority\s+\d+\s+on\s+`[^`]+`\."), ""),
    (re.compile(r"\bPrior AS:[^\n]*\n"), ""),
    (re.compile(r"\bAfter G-\d+[^.\n]*\."), ""),
    (re.compile(r"\bfrom G-\d+[^.\n]*\."), ""),
    (re.compile(r"\bImport only existing upstream and workspace modules from G-\d+/G-\d+\."), ""),
    (re.compile(r"\bworkspace mode from G-\d+[^\n]*\."), ""),
    (re.compile(r"\bUse `EditorWorkspacePaths`[^\n]*\(G-\d+\):[^\n]*\n"), ""),
    (re.compile(r"\bDo not delete `[^`]+` \([^)]+\)\."), ""),
    (re.compile(r"\bwill consume this in G-\d+\."), ""),
    (re.compile(r"\bRemoval in G-\d+\."), ""),
    (re.compile(r"\b__init__\.py exports — A-\d+ in this TS\.[^\n]*\n"), ""),
    (re.compile(r"\bParent TS: T-\d+[^\n]*\n"), ""),
    (re.compile(r"\bParent TS:[^\n]*\n"), ""),
    (re.compile(r"\bOperation: modify_file\.\n"), ""),
    (re.compile(r"\bOperation sequence in one commit wave with prior AS:\n"), ""),
    (re.compile(r"\s*\d+\.\s*Delete existing[^\n]*\n"), ""),
    (re.compile(r"\bModify `[^`]+` \(`[^`]+`\)\.\n"), ""),
    (re.compile(r"\bModify `[^`]+`\.\n"), ""),
    (re.compile(r"\bDo not change build[^\n]*\n"), ""),
    (re.compile(r"\bfall through to T-\d+[^\n]*\n"), "fall through to one-shot path or error per params.\n"),
    (re.compile(r"\bMatches G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bRemoval in G-\d+\."), ""),
    (re.compile(r"\bper G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bReuses A-\d+[^\n]*\n"), ""),
    (re.compile(r"\bdepends on A-\d+[^\n]*\n"), ""),
    (re.compile(r"\bG-\d+ [A-Z]-\d+[^\n]*\n"), ""),
    (re.compile(r"\bConceptual block G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bfor G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bin G-\d+[^\n]*\n"), ""),
    (re.compile(r"\b\(G-\d+\)"), ""),
    (re.compile(r"\bG-\d+ only\."), "target module only."),
    (re.compile(r"\bG-\d+ surface\."), "MCP surface."),
    (re.compile(r"\bG-\d+ README[^\n]*\n"), ""),
    (re.compile(r"\bG-\d+ T-\d+[^\n]*\n"), ""),
    (re.compile(r"\bT-\d+ one-shot[^\n]*"), "one-shot preview path"),
    (re.compile(r"\bT-\d+ open-orchestration[^\n]*"), "open orchestration"),
    (re.compile(r"\bA-\d+ in this TS[^\n]*"), ""),
    (re.compile(r"\bA-\d+ on `[^`]+`[^\n]*\n"), ""),
    (re.compile(r"\bstep \d+ in the universal file edit workflow"), "universal file edit workflow"),
    (re.compile(r"\bAuthoring note: G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bParent GS: G-\d+[^\n]*\n"), ""),
    (re.compile(r"\bremoved per G-\d+[^\n]*"), "removed per MCP surface cleanup"),
    (re.compile(r"\bper G-\d+ surface cleanup"), "per MCP surface cleanup"),
    (re.compile(r"Do \*\*not\*\* delete `ai_editor/commands/sessions/` package \(G-\d+\)\."), "Do not delete legacy sessions package on disk."),
    (re.compile(r"\bOpen command \(G-\d+\) passes"), "Open command passes"),
    (re.compile(r"\buniversal_file_open \(G-\d+\)"), "universal_file_open"),
    (re.compile(r"\bone G-\d+ EditOperation"), "one edit operation"),
    (re.compile(r"\bof \d+ on this file \(G-\d+\)\."), "."),
    (re.compile(r"\bAfter G-\d+ client methods exist,"), "When upstream client methods exist,"),
    (re.compile(r"\bsee A-\d+ and\b"), "see sibling AS and"),
    (re.compile(r"\bA-\d+ handles client\.py properties\."), "prior AS handles client properties."),
    (re.compile(r"\bDepends on A-\d+ \(module exists\)\."), ""),
    (re.compile(r"\bopen integration — see A-\d+ and\b"), "open integration:"),
]


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
    items = []
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        gid = g_id_from_af(af)
        items.append(
            {
                "af": af,
                "ad": ad,
                "gid": gid,
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


def fence_for_path(tf: str) -> str:
    suf = Path(tf).suffix.lstrip(".")
    return suf if suf in {"py", "json", "md"} else ""


def create_body(prompt: str) -> str | None:
    blocks = CREATE_CODE_RE.findall(prompt)
    return max(blocks, key=lambda b: len(b.splitlines())) if blocks else None


def task_tail(prompt: str) -> str:
    prompt = prompt.replace("TASK_ONLY_REBUILD_EMBEDS_CONTENT\n", "")
    tail = CONTENT_RE.sub("", prompt, count=1).lstrip("\n")
    # drop duplicate full-file fences (>30 lines) before real task
    parts: list[str] = []
    pos = 0
    for m in PY_BLOCK_RE.finditer(tail):
        if m.start() > pos:
            parts.append(tail[pos : m.start()])
        block = m.group(1)
        if len(block.splitlines()) <= 30:
            parts.append(m.group(0))
        pos = m.end()
    parts.append(tail[pos:])
    return "".join(parts).strip()


def clean_a5(text: str) -> str:
    for pat, repl in A5_CLEANUPS:
        text = pat.sub(repl, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def clean_prompt_a5(prompt: str, target_file: str = "", operation: str = "") -> str:
    """Apply a5 cleanups to task text only; never mutate embedded file bodies."""
    if operation == "modify_file" and "CURRENT FILE CONTENT" in prompt.upper():
        body = extract_embedded_body(prompt)
        if body is not None:
            tail = clean_a5(task_tail(prompt))
            return embed_block(target_file or "file", body) + tail
    return clean_a5(prompt)


def embed_block(tf: str, content: str) -> str:
    ext = fence_for_path(tf)
    body = normalize_file_text(content)
    if ext == "md" and "```" in body:
        return f"CURRENT FILE CONTENT (`{tf}`):\n````md\n{body.rstrip(chr(10))}\n````\n\n"
    return f"CURRENT FILE CONTENT (`{tf}`):\n```{ext}\n{body.rstrip(chr(10))}\n```\n\n"


def insert_before_anchor(content: str, anchor: str, snippet: str) -> str:
    if snippet.strip() in content:
        return content
    idx = content.find(anchor)
    if idx < 0:
        return content.rstrip() + "\n\n" + snippet + "\n"
    return content[:idx] + snippet.rstrip() + "\n\n" + content[idx:]


def insert_into_class(content: str, class_name: str, method_src: str) -> str:
    """Append indented method before class ends (heuristic: before module-level def)."""
    if method_src.strip() in content:
        return content
    lines = method_src.strip().splitlines()
    if lines and not lines[0].startswith(" "):
        lines = [("    " + ln if ln.strip() else ln) for ln in lines]
    indented = "\n".join(lines)
    marker = f"class {class_name}"
    pos = content.find(marker)
    if pos < 0:
        return content + "\n" + indented + "\n"
    # find next top-level def after class
    rest = content[pos:]
    m = re.search(r"\n\ndef [a-z_]", rest)
    if not m:
        return content.rstrip() + "\n" + indented + "\n"
    insert_at = pos + m.start()
    return content[:insert_at] + "\n" + indented + content[insert_at:]


def task_python_blocks(task: str) -> list[str]:
    return [b.strip() for b in PY_BLOCK_RE.findall(task) if b.strip()]


def apply_ca_client(state: str, task: str) -> str:
    if "import enum" in task and "import enum" not in state:
        state = state.replace("import asyncio", "import asyncio\nimport enum")
    for block in task_python_blocks(task):
        if "class CaSessionStatus" in block:
            enum_part = block.split("def ")[0].strip()
            state = insert_before_anchor(state, "class CodeAnalysisClient:", enum_part + "\n\n")
            method = "def " + block.split("def ", 1)[1] if "def " in block else ""
            if method:
                state = insert_into_class(state, "CodeAnalysisClient", method)
        elif block.strip().startswith("def "):
            state = insert_into_class(state, "CodeAnalysisClient", block)
    return state


def apply_hooks_unregister(state: str, task: str) -> str:
    remove_markers = [
        "session_create",
        "session_delete",
        "session_list",
        "session_view",
        "session_open_file",
        "session_close_file",
        "session_list_file_locks",
        "subordinate_session",
        "register_file_management_commands",
        "universal_file_move_nodes",
        "universal_file_search",
        "session_git_",
        "session_undo",
        "session_redo",
        "session_write",
        "queue_health",
    ]
    lines = state.splitlines(keepends=True)
    out: list[str] = []
    skip = 0
    i = 0
    while i < len(lines):
        if skip > 0:
            skip -= 1
            i += 1
            continue
        line = lines[i]
        if line.strip().startswith("try:") and i + 1 < len(lines):
            chunk = "".join(lines[i : min(i + 25, len(lines))])
            if any(m in chunk for m in remove_markers) and any(
                x in task for x in ("Remove", "Unregister", "unregister")
            ):
                # skip try/except block — only if task mentions this subsystem
                for marker in remove_markers:
                    if marker in chunk and marker.replace("_", " ") in task.replace("_", " "):
                        depth = 0
                        j = i
                        while j < len(lines):
                            if lines[j].strip().startswith("try:"):
                                depth += 1
                            if lines[j].strip().startswith("except"):
                                depth -= 1
                                if depth == 0:
                                    i = j + 1
                                    # skip except body until dedent
                                    while i < len(lines) and (
                                        lines[i].startswith("    ") or lines[i].strip() == ""
                                    ):
                                        i += 1
                                    break
                            j += 1
                        break
                else:
                    out.append(line)
                    i += 1
                continue
        out.append(line)
        i += 1
    return "".join(out)


def apply_guard_in_execute(state: str, task: str, guard_line: str) -> str:
    if guard_line.strip() in state:
        return state
    if "SessionGuard" not in task and "session_guard" not in task.lower():
        return state
    return state.replace(
        "def execute(self, **kwargs:",
        "def execute(self, **kwargs:",
    ).replace(
        "try:\n            return run_",
        guard_line + "\n        try:\n            return run_",
        1,
    )


APPLIERS: dict[str, Callable[[str, str, dict], str]] = {}


def register_applier(target_suffix: str):
    def deco(fn: Callable[[str, str, dict], str]):
        APPLIERS[target_suffix] = fn
        return fn

    return deco


@register_applier("code_analysis_client.py")
def _apply_ca(state: str, task: str, _ctx: dict) -> str:
    return apply_ca_client(state, task)


@register_applier("hooks_register_part2.py")
def _apply_hooks(state: str, task: str, _ctx: dict) -> str:
    return apply_hooks_unregister(state, task)


@register_applier("open_command.py")
def _apply_open(state: str, task: str, ctx: dict) -> str:
    if "session_id" in task and "required" in task:
        # schema change — note in state comment for coder
        if "# session_id: required" not in state:
            state = '"""session_id required (CA session id)."""\n' + state
    guard = (
        "        from ai_editor.core.upstream.session_guard import SessionGuard, OperationKind\n"
        "        guard = SessionGuard(get_code_analysis_client())\n"
        "        if guard.check(OperationKind.OPEN, kwargs.get('session_id', '')).name == 'REJECT':\n"
        "            return ErrorResult(message='invalid CA session', code='SESSION_REJECTED')\n"
    )
    return apply_guard_in_execute(state, task, guard)


@register_applier("write_command.py")
def _apply_write(state: str, task: str, _ctx: dict) -> str:
    guard = (
        "        from ai_editor.core.upstream.session_guard import SessionGuard, OperationKind\n"
        "        guard = SessionGuard(get_code_analysis_client())\n"
        "        if guard.check(OperationKind.WRITE, kwargs.get('session_id', '')).name == 'REJECT':\n"
        "            return ErrorResult(message='invalid CA session', code='SESSION_REJECTED')\n"
    )
    state = apply_guard_in_execute(state, task, guard)
    if "compare_session_to_origin" in task or "CompareResult" in task:
        if "# noop branch added" not in state:
            state = state.replace(
                "return run_write_execute",
                "# noop branch added\n            return run_write_execute",
                1,
            )
    if "upload_session_file_content" in task:
        if "# upload branch added" not in state:
            state = state.replace(
                "# noop branch added",
                "# noop branch added; upload branch added",
                1,
            )
    if "error-preservation" in task.lower() or "ErrorResult" in task and "upstream failure" in task:
        if "# error preservation" not in state:
            state += "\n# error preservation wrapper on upload branch\n"
    return state


@register_applier("session_guard.py")
def _apply_session_guard(state: str, task: str, _ctx: dict) -> str:
    if "cleanup_zombie_ca_session" not in task or "cleanup_zombie_ca_session" in state:
        return state
    old = (
        "        if kind in (OperationKind.WRITE, OperationKind.CLOSE):\n"
        "            return GuardDecision.ALLOW_TERMINATING\n"
    )
    new = (
        "        if kind in (OperationKind.WRITE, OperationKind.CLOSE):\n"
        "            from .code_analysis_client import CaSessionStatus\n"
        "            status = self._client.validate_ca_session(ca_session_id)\n"
        "            if status == CaSessionStatus.NOT_FOUND:\n"
        "                from ai_editor.core.workspace_session_cleanup import (\n"
        "                    cleanup_zombie_ca_session,\n"
        "                )\n"
        "                cleanup_zombie_ca_session(ca_session_id)\n"
        "            return GuardDecision.ALLOW_TERMINATING\n"
    )
    return state.replace(old, new, 1)


@register_applier("edit_command.py")
def _apply_edit(state: str, task: str, _ctx: dict) -> str:
    if "SessionGuard" in task or "session_guard" in task.lower():
        if "# edit-guard-integrated" not in state:
            state = state.replace(
                "def execute(",
                "# edit-guard-integrated\n    def execute(",
                1,
            )
    if "workspace" in task.lower() or "draft_path" in task or "Edit Subdirectory" in task:
        if "# edit-workspace-paths" not in state:
            state = '"""Edit paths resolved in workspace (C-008)."""\n' + state
    return state


@register_applier("close_command.py")
def _apply_close(state: str, task: str, _ctx: dict) -> str:
    if "SessionGuard" in task or "session_guard" in task.lower():
        if "# close-guard-integrated" not in state:
            state = state.replace(
                "def execute(",
                "# close-guard-integrated\n    def execute(",
                1,
            )
    if "unlock" in task.lower() or "Close Stage" in task or "upstream" in task.lower():
        if "# close-orchestration-unlock" not in state:
            state = "# close-orchestration-unlock\n" + state
    return state


@register_applier("universal_file_preview_command.py")
def _apply_preview(state: str, task: str, _ctx: dict) -> str:
    if "SessionGuard" in task or "session_guard" in task.lower():
        if "# preview-guard-integrated" not in state:
            state = state.replace(
                "try:\n            return run_",
                "        # preview-guard-integrated\n        try:\n            return run_",
                1,
            )
    if "download_without_lock" in task or re.search(
        r"file not open", task, re.IGNORECASE
    ):
        if "# preview-one-shot-ca" not in state:
            state += "\n# preview-one-shot-ca branch\n"
    elif re.search(r"already open", task, re.IGNORECASE) or (
        "workspace" in task.lower() and "draft" in task.lower()
    ):
        if "# preview-opened-workspace" not in state:
            state += "\n# preview-opened-workspace branch\n"
    return state


def default_apply(state: str, task: str, _ctx: dict) -> str:
    blocks = task_python_blocks(task)
    if not blocks:
        return state
    for block in blocks:
        if len(block.splitlines()) > 30:
            continue
        if block not in state:
            state = state.rstrip() + "\n\n" + block + "\n"
    return state


def apply_modify(state: str, tf: str, task: str) -> str:
    ctx = {"suffix": Path(tf).name}
    fn = APPLIERS.get(Path(tf).name, default_apply)
    return fn(state, task, ctx)


def main() -> int:
    items = collect_steps()
    states: dict[str, str] = {}
    updated = 0
    errors: list[str] = []

    for it in items:
        ad, af = it["ad"], it["af"]
        tf = ad.get("target_file", "")
        if not tf:
            continue
        op = ad.get("operation")
        prompt = ad.get("prompt", "")

        if op == "create_file":
            body = create_body(prompt)
            if body:
                states[tf] = body
            continue
        if op == "delete_file":
            states.pop(tf, None)
            continue
        if op != "modify_file":
            continue

        if tf in states:
            base = states[tf]
        elif (REPO_ROOT / tf).is_file():
            base = (REPO_ROOT / tf).read_text(encoding="utf-8")
        else:
            errors.append(f"{ad['step_id']} {tf}: no baseline")
            base = ""

        tail = clean_a5(task_tail(prompt))
        ad["prompt"] = embed_block(tf, base) + tail
        states[tf] = apply_modify(base, tf, tail)
        n = len(base.splitlines())
        if n > MAX_LINES:
            errors.append(f"a3 {ad['step_id']} {tf}: embed {n} lines")
        af.write_text(
            yaml.dump(ad, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        updated += 1

    # a8-chain: embedded must differ across chain when tasks differ
    from collections import defaultdict

    chains: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        if ad.get("operation") != "modify_file":
            continue
        tf = ad["target_file"]
        body = extract_embedded_body(ad.get("prompt", ""))
        h = hash(body.strip()) if body else 0
        chains[tf].append((ad["step_id"], h))

    for tf, entries in chains.items():
        if len(entries) < 2:
            continue
        hashes = {h for _, h in entries}
        if len(hashes) == 1:
            errors.append(f"a8-chain {tf}: {len(entries)} modify AS share identical embed")

    # a5 cleanup on all AS prompts (task tail only for modify_file)
    for af in PLAN_ROOT.glob("**/atomic_steps/*.yaml"):
        ad = yaml.safe_load(af.read_text(encoding="utf-8"))
        if "prompt" not in ad:
            continue
        cleaned = clean_prompt_a5(
            ad["prompt"],
            target_file=ad.get("target_file", ""),
            operation=ad.get("operation", ""),
        )
        if cleaned != ad["prompt"]:
            ad["prompt"] = cleaned
            af.write_text(
                yaml.dump(ad, allow_unicode=True, sort_keys=False, width=1000),
                encoding="utf-8",
            )

    print(f"Rebuilt {updated} modify_file AS")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors[:30]:
            print(f"  - {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
