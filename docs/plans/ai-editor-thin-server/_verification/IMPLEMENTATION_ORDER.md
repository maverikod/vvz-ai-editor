# Global Implementation Execution Order

Plan: `docs/plans/ai-editor-thin-server/`  
Global steps: G-001 … G-010  
Source: `depends_on` fields in each `G-*/README.yaml`  
Parallel cap: **≤ 4 global steps per batch** within a wave (CR-016 / orchestrator policy)

---

## Dependency table

| G-step | Title | depends_on | Produces (one line) |
|--------|-------|------------|---------------------|
| G-001 | Workspace root и модель каталога сессии | — | Fix on disk the Workspace Root, Editor Session Directory, File Subtree, Origin Snapshot, and Edit Subdirectory hierarchy: one session directory per CA Session, one subtree per open file, immutable origin snapshot, isolated edit subdirectory; session artifacts stay outside the CA project tree. |
| G-002 | Upstream-клиент к Code Analysis Server | — | Extend Upstream Client with internal CA API Contract wrappers for session validation, open/close/write stages, preview-path, and create-path open; resolve `file_path`→`file_id`; centralize connection config; Upstream Client is the sole path for locks and content changes on CA. |
| G-003 | Оркестрация Open и Close | G-001, G-002, G-007 | Implement Open Stage and Close Stage in File Workflow using CA Session as the sole `session_id`, Session Guard validation, upstream lock/unlock, origin snapshot and edit subdirectory on open, and file subtree/session cleanup on close. |
| G-004 | Адаптация edit и preview к workspace | G-003, G-007 | Keep Internal Edit Engine semantics unchanged while moving Edit Stage to work only inside Edit Subdirectory within File Subtree, with workspace-relative paths and CA Session context, without altering Origin Snapshot. |
| G-005 | Write compare-and-upload | G-003, G-004, G-007 | Implement Write Stage with byte-wise compare of canonical edit export vs Origin Snapshot: preview yields local diff only; commit no-ops on equality or uploads via Upstream Client and refreshes Origin Snapshot on CA success. |
| G-006 | Сужение MCP-поверхности | G-003 | Remove duplicate/legacy command families from public MCP so only target file workflow and health remain, with CA access only inside workflow via Upstream Client, verified against Product Acceptance Criteria. |
| G-007 | Broken session policy | G-002 | Implement internal Session Guard for session validation and Broken Session Policy (normal vs terminating ops), plus Workspace Session Cleanup when CA session is confirmed absent. |
| G-008 | Единый клиентский фасад | G-006 | Converge the client library to one public File Workflow facade over MCP Workflow Surface with mandatory CA Session context, deprecating parallel/duplicate client facades per Legacy Removal Scope. |
| G-009 | Удаление legacy-кода | G-006, G-008 | Remove the full Legacy Removal Scope inventory from the editor codebase (local project DB, workers, search/analysis MCP, legacy session/file commands, duplicate client contracts) while preserving Editor Responsibility Boundaries. |
| G-010 | Приёмка и тесты | G-005, G-006, G-007, G-008 | Domain-verify Product Acceptance Criteria C-022 full checklist for thin AI Editor Server readiness, yielding confirmed passage of the complete C-022 checklist. |

---

## Wave-ordered execution plan

Steps in the same wave are mutually independent (all `depends_on` satisfied by prior waves) and **may run in parallel**, subject to the **≤ 4 parallel** batching rule.

### Wave 1 — Foundation (no upstream G-step deps)

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 1a | G-001, G-002 | 2 (≤ 4) |

### Wave 2 — Session guard (upstream client)

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 2a | G-007 | 1 |

### Wave 3 — Open/Close orchestration

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 3a | G-003 | 1 |

> **Note:** G-003 lists G-007 in `depends_on` for implementation order (Session Guard must exist before Open/Close orchestration), not as a semantic overlap with G-007’s scope.

### Wave 4 — Edit adaptation + MCP surface narrowing

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 4a | G-004, G-006 | 2 (≤ 4) |

### Wave 5 — Write stage + client facade

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 5a | G-005, G-008 | 2 (≤ 4) |

### Wave 6 — Legacy removal

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 6a | G-009 | 1 |

### Wave 7 — Acceptance

| Batch | G-steps | Parallel count |
|-------|---------|----------------|
| 7a | G-010 | 1 |

---

## Summary sequence

```
Wave 1:  G-001, G-002          (parallel)
Wave 2:  G-007
Wave 3:  G-003
Wave 4:  G-004, G-006          (parallel)
Wave 5:  G-005, G-008          (parallel)
Wave 6:  G-009
Wave 7:  G-010
```

No wave exceeds 4 steps; **no sub-batch splitting required**.

---

## Cycles and dangling dependencies

| Check | Result |
|-------|--------|
| Dependency cycles | **None** |
| Dangling `depends_on` (references outside G-001…G-010) | **None** |
| Missing G-step README.yaml | **None** (all 10 present) |

---

## Supplementary metadata

| Artifact | Status |
|----------|--------|
| `parallel_waves.yaml` | **Not found** anywhere under `docs/plans/ai-editor-thin-server/` |

Execution order derived solely from per-step `depends_on` fields and topological wave sort.
