# План: thin AI Editor Server

## Статус

| Слой | Статус |
|------|--------|
| HRS | актуален (post-audit) |
| MRS | 25 концептов (C-001…C-025) |
| GS / TS / AS | ready_for_review |
| Верификация | [GREEN](consistency_verification_report.md) |

## Ключевые артефакты

- [source_spec.md](source_spec.md)
- [spec.yaml](spec.yaml)
- [ca_api_contract.md](ca_api_contract.md)
- [consistency_verification_report.md](consistency_verification_report.md)

## Порядок реализации

```
G-001 ║ G-002
         ↓
       G-007   ← Session Guard (до open orchestration)
         ↓
       G-003 → G-004 → G-005 ─┐
         ├→ G-006 → G-008 ────┼→ G-010
         └──────────────── G-009
```

## G-steps

| ID | Имя | depends_on |
|----|-----|------------|
| G-001 | Workspace | — |
| G-002 | Upstream C-023 | — |
| G-007 | Session Guard C-024 | G-002 |
| G-003 | Open/Close | G-001, G-002, **G-007** |
| G-004 | Edit/Preview | G-003, G-007 |
| G-005 | Write | G-003, G-004 |
| G-006 | MCP cleanup | G-003 |
| G-008 | Client facade | G-006 |
| G-009 | Legacy removal | G-006, G-008 |
| G-010 | Acceptance | G-005, **G-006**, G-007, G-008 |

## Новое после аудита

- **G-001 T-006** — sidecar + tree-temp в workspace
- **G-002 T-006/T-007** — download без lock, create=true upload
- **G-005 T-005** — write_mode preview/commit
- **G-006 T-005** — снять queue_health
- **C-024/C-025** — Session Guard + zombie cleanup
