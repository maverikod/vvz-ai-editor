# 09. Tests and MCP verification

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)
- Следующий шаг: [../10-docs-and-rollout/index.md](../10-docs-and-rollout/index.md)
- Итоговый rollout: [../10-docs-and-rollout/index.md](../10-docs-and-rollout/index.md)

## Цель

Покрыть реализацию unit/integration/MCP-level проверками. Поведение считается готовым только после фактического выполнения MCP-команд и отдельной проверки результата read/search-командами.

## Входные материалы

- Config contract: [../02-config-contract/index.md](../02-config-contract/index.md)
- Validator/generator step: [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)
- Eligibility step: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)
- Watcher step: [../05-watcher-integration/index.md](../05-watcher-integration/index.md)
- Indexing/chunker step: [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- Vectorization gate: [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)
- Search diagnostics: [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)

## Релевантные исходники и тесты

```text
tests/test_*config*.py
tests/test_*vector*.py
tests/test_*worker*.py
code_analysis/commands/semantic_search_mcp.py
code_analysis/commands/check_vectors_command.py
code_analysis/core/config_validator/**
code_analysis/core/vectorization_worker_pkg/**
```

## Unit tests

Config validator:
- Missing `docs_indexing` is valid.
- Defaults are valid.
- `enabled` must be boolean.
- `vectorize` must be boolean.
- Absolute roots fail.
- Roots with `..` fail.
- `docs/**/*.md` passes after matcher semantics are documented.
- `README.md` passes.
- `docs/**/*.txt` is rejected by strict validator or accepted only if runtime eligibility still rejects `.txt`; chosen behavior is documented.
- Broad patterns such as `docs/**/*` and `**/*` are either rejected by strict validator or explicitly allowed only with runtime `.md` suffix enforcement; chosen behavior is tested and documented.

Eligibility:

- `docs/guide.md` passes when enabled.
- `README.md` passes when included.
- `docs/guide.txt` fails.
- `docs/plans/task.md` fails by default exclude.
- Exclude wins over include.

## Integration tests

Use dedicated test project only.

- With `enabled=false`, docs are ignored.
- With `enabled=true`, eligible `.md` creates/updates `files` row.
- Eligible `.md` is sent to existing chunker file API.
- Eligible `.md` creates `code_chunks` rows.
- Non-md files do not enter docs indexing path.
- Default excluded paths do not enter docs indexing path.

- `enabled=true`, `vectorize=false`: chunks exist and are persisted in `code_chunks`.
- `enabled=true`, `vectorize=false`: chunker-returned token/BM25 data is preserved when available.
- `enabled=true`, `vectorize=false`: `fulltext_search` returns matching Markdown docs.
- `enabled=true`, `vectorize=false`: no FAISS entries are created and `semantic_search` does not return docs.
- `enabled=true`, `vectorize=true`: embeddings/FAISS entries exist.
- `enabled=true`, `vectorize=true`: `semantic_search` can return docs.

## MCP verification

Run after implementation:

```text
list_projects
list_project_files
get_database_status
get_worker_status
fulltext_search
semantic_search
check_vectors
queue_get_job_status
```

For queued work, do not trust only:

```text
status=completed
progress=100
```

Always inspect nested command success:

```text
result.command.result.success
```

## Required observation files

Record outcomes in this step directory:

```text
unit-test-results.md
integration-test-results.md
mcp-verification-results.md
known-limitations.md
```

## Передача в следующий шаг

- `mcp-verification-results.md` используется в [../10-docs-and-rollout/index.md](../10-docs-and-rollout/index.md).
- `known-limitations.md` должен быть отражён в final docs/rollout notes.

## Выход шага

- Automated tests added.
- MCP verification recorded.
- Search/vector behavior verified separately.
- Failures documented with command, expected, actual, root cause, fix, post-fix verification, status.