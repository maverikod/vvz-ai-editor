# ТЗ: Markdown docs indexing through existing chunk/vector pipeline

## Status

Draft specification for implementation.

## Goal

Add optional indexing of project documentation from Markdown files into the existing `code_analysis` database and chunk pipeline.

Documentation indexing must reuse the same file/chunk/vector lifecycle that is already used for indexed project code. It must not introduce a parallel documentation-only storage model.

## Key requirements

1. Only Markdown files are in scope.
2. Documentation indexing is disabled by default.
3. Documentation vectorization is disabled by default, even when documentation indexing is enabled.
4. Settings must be stored in the main server config, not in `projectid`.
5. The implementation must use the existing chunker file ingestion command/API where possible.
6. Indexed documentation chunks must be stored in the existing `files` / `code_chunks` / vector pipeline structures so existing search commands can reuse them.
7. No changes are allowed in `.venv`, `site-packages`, or installed dependency copies.

## Explicit non-goals

Do not implement a separate documentation storage stack:

```text
docs_chunks
docs_vectors
documentation_vectors
separate markdown vectorizer
separate semantic search path for docs
```

Using a distinct `chunk_type` value (such as `ChunkType.DOC_BLOCK`) within the existing `code_chunks` table is not a separate storage stack and is explicitly allowed.

Do not index non-Markdown files through this feature:

```text
.txt
.rst
.adoc
.json
.yaml
.yml
.toml
.py
.pyi
.pyw
.log
.tmp
```

## Configuration design

Add a new section under `code_analysis`:

```json
{
  "code_analysis": {
    "docs_indexing": {
      "enabled": false,
      "vectorize": false,
      "roots": ["docs"],
      "include": ["docs/**/*.md", "README.md"],
      "exclude": ["docs/plans/**", "docs/ai_reports/**"]
    }
  }
}
```

### Defaults

The defaults above apply when the `docs_indexing` section is omitted entirely from config.

Important: `vectorize=false` is the default even when `enabled=true` is set manually.

### Field semantics

`enabled`:

- Type: boolean.
- Default: false.
- If false, the file watcher and indexing workers must ignore this feature completely.

`vectorize`:

- Type: boolean.
- Default: false.
- If false, Markdown docs may be indexed/chunked, but their chunks must not be added to embeddings/FAISS.
- If true, Markdown docs chunks are eligible for the existing vectorization pipeline.

`roots`:

- Type: array of strings.
- Default: `["docs"]`.
- Informational hint listing the top-level directories that `include` patterns are expected to cover. Does not act as an independent filter: a file is eligible if and only if it matches an `include` pattern. Files outside `roots` but matched by an `include` pattern (e.g. `README.md`) are eligible.
- Must not allow absolute paths.
- Must not allow path traversal.

`include`:

- Type: array of strings.
- Default: `["docs/**/*.md", "README.md"]`.
- Project-relative glob/fnmatch-style patterns.
- Must only allow Markdown patterns.

`exclude`:

- Type: array of strings.
- Default: `["docs/plans/**", "docs/ai_reports/**"]`.
- Project-relative exclusion patterns.
- Exclusion wins over inclusion.

## Markdown-only rule

The feature is strictly Markdown-only.

A candidate file is eligible only if all of the following are true:

1. The project-level config section `code_analysis.docs_indexing.enabled` is true.
2. The path is project-relative.
3. The path has suffix `.md`.
4. The path matches at least one `include` pattern. Files not matched by any include pattern are skipped regardless of `roots`.
5. The path does not match any `exclude` pattern. Exclude has absolute priority over include: a file matched by both is always excluded.
6. The file is not deleted and exists on disk.

The validator must reject non-Markdown include patterns. Examples of invalid include patterns:

```text
docs/**/*.txt
docs/**/*.rst
docs/**/*
**/*
*.json
*.py
```

Allowed include examples:

```text
docs/**/*.md
README.md
*.md
```
*.md
```

## Config validator work

Study and extend these files:

```text
code_analysis/core/config_validator/validator.py
code_analysis/core/config_validator/section_code_analysis.py
code_analysis/core/config_validator/field_types.py
code_analysis/core/config_validator/field_types_code_analysis.py
code_analysis/core/config_validator/field_values.py
code_analysis/core/config_validator/result.py
```

Required validation rules:

1. `docs_indexing` is optional.
2. If present, `docs_indexing` must be an object.
3. `enabled` must be boolean.
4. `vectorize` must be boolean.
5. `roots` must be an array of project-relative strings.
6. `roots` entries must not be absolute paths.
7. `roots` entries must not contain `..` path traversal.
8. `include` must be an array of strings.
9. `exclude` must be an array of strings.
10. `include` patterns must be Markdown-only.
11. `exclude` patterns may be broader, but must remain project-relative and must not escape project root.
12. Invalid fields should produce structured `ValidationResult` errors with section/key context.

## Config generator work

Study and extend these files:

```text
code_analysis/core/config_generator.py
code_analysis/cli/config_cli_generate.py
code_analysis/cli/config_cli_parser.py
code_analysis/cli/config_cli_commands.py
```

Required generator changes:

1. Add generator arguments for docs indexing:

```text
code_analysis_docs_indexing_enabled
code_analysis_docs_indexing_vectorize
code_analysis_docs_indexing_roots
code_analysis_docs_indexing_include
code_analysis_docs_indexing_exclude
```

2. Generated config must include the `code_analysis.docs_indexing` section or consistently apply defaults when omitted.
3. CLI help must clearly state that only `.md` files are supported.
4. CLI help must clearly state that vectorization is disabled by default.
5. The generated sample config must not enable docs indexing by default.

## Database schema study

Before implementation, inspect the actual database schema and driver abstractions for these areas:

```text
files
code_chunks
vector ids / vector chunks
FAISS mapping
project_id linkage
deleted flags
file path identity
chunk_uuid
chunk_type
chunk_text
line
token_count
bm25_score
```

Relevant implementation areas to inspect:

```text
code_analysis/core/database/schema*
code_analysis/core/database/files/*
code_analysis/core/database/code_chunk*
code_analysis/core/database_client/objects/vector_chunk.py
code_analysis/core/faiss_manager.py
```

The implementation must document the actual schema behavior before changing it.

## Existing semantic search contract

The current `semantic_search` command performs vector lookup through FAISS and then maps FAISS `vector_id` values back to database rows equivalent to:

```sql
SELECT
    c.id AS chunk_id,
    c.file_id,
    c.vector_id,
    c.chunk_uuid,
    c.chunk_type,
    c.chunk_text,
    c.line,
    f.path AS file_path,
    c.bm25_score,
    c.token_count
FROM code_chunks c
JOIN files f ON f.id = c.file_id
WHERE c.project_id = ?
  AND c.vector_id IN (...)
```

Therefore, Markdown docs must be represented in the same `files` and `code_chunks` structures if they should ever appear in `semantic_search` results.

When `vectorize=false`, docs chunks must not appear in `semantic_search`, because they should not have embeddings/FAISS entries.

When `vectorize=true`, docs chunks may appear in `semantic_search` if they pass through the same vectorization pipeline and receive valid `vector_id` entries.

## File watcher study

Study the file watcher before implementation:

```text
code_analysis/core/file_watcher*
code_analysis/core/file_watcher_pkg/*
```

Expected behavior to document:

1. How project roots are discovered.
2. How `projectid` is read today.
3. How ignored files and directories are filtered.
4. How deleted/changed/new files are detected.
5. How `files` DB rows are created or updated.
6. How work is handed to indexing/vectorization workers.

Required watcher changes:

1. Load `code_analysis.docs_indexing` from active server config.
2. If disabled, keep current behavior unchanged.
3. If enabled, consider Markdown candidates under configured roots/includes.
4. Apply exclude patterns after include patterns.
5. Only pass `.md` files into the docs indexing path.
6. Do not treat `docs_indexing` as permission to index all text files.
7. Preserve existing project ignore behavior for `.venv`, caches, hidden dirs, and deleted paths.

## Indexing worker study

Study these areas before implementation:

```text
code_analysis/core/indexing_worker_pkg/*
code_analysis/core/vectorization_worker_pkg/chunking.py
code_analysis/core/vectorization_worker_pkg/batch_processor.py
code_analysis/core/vectorization_worker_pkg/file_batch_packing.py
code_analysis/core/vectorization_worker_pkg/processing.py
code_analysis/core/vectorization_worker_pkg/processing_cycle.py
code_analysis/core/indexing_worker_pkg/vectorize_after_index.py
```

Expected behavior to document:

1. How files become chunks today.
2. How the chunker service is invoked.
3. How file-based chunking is represented.
4. How chunk rows are inserted into DB.
5. How `vectorize_after_index` is triggered.
6. How chunks become embeddings and FAISS entries.
7. How skipped/failed files are marked.

## Chunker integration requirement

The chunker already has a command/API for receiving a file. Markdown docs must use that existing file-based chunker entrypoint.

Do not implement a new Markdown splitter unless the existing chunker file command cannot process `.md`; if it cannot, document the exact limitation and create a separate follow-up task for the chunker service owner.

Expected flow:

```text
eligible .md file
  -> existing file DB row
  -> existing chunker file command/API
  -> chunk results
  -> existing code_chunks insert/update path
  -> optional vectorization depending on docs_indexing.vectorize
```


If the chunker service is unavailable, the `files` row is written without chunks. The file is left in a state that the indexing worker will detect as unprocessed in the next cycle and retry. This is the existing worker retry mechanism — no special handling is required for Markdown docs.

## Chunk representation requirements

Markdown documentation chunks must be compatible with existing `semantic_search` output fields.

At minimum, each persisted chunk must have:

```text
project_id
file_id
chunk_uuid
chunk_type
chunk_text
line
token_count — populated only when vectorize=true (chunker provides it); NULL when vectorize=false
bm25_score — populated only when vectorize=true (chunker provides it); NULL when vectorize=false
vector_id — populated only when vectorize=true; NULL otherwise
```

Markdown documentation chunks must use the existing `SemanticChunk.type` contract from `chunk_metadata_adapter`:

```text
ChunkType.DOC_BLOCK / "DocBlock"
```

Do not introduce `documentation_markdown` or any other new chunk type unless `chunk_metadata_adapter.ChunkType` is extended first and all consumers of `chunk_type` are checked.

## Vectorization behavior

Default behavior:

```text
docs_indexing.enabled = false
docs_indexing.vectorize = false
```

When `enabled=false`:

- Markdown docs are ignored by this feature.
- Existing code indexing behavior remains unchanged.

When `enabled=true` and `vectorize=false`:

- Eligible Markdown docs are indexed and chunked if the indexing design supports non-vector chunks.
- No embeddings are requested for those chunks.
- No FAISS entries are created for those chunks.
- `semantic_search` should not return those docs.
- `bm25_score` and `token_count` are NULL (chunker is not called when vectorize=false). Fulltext/BM25 search does not return these docs.

When `enabled=true` and `vectorize=true`:

- Eligible Markdown docs are indexed and chunked.
- Existing embedding flow is used.
- Existing FAISS index update flow is used.
- `semantic_search` may return Markdown docs through the current `code_chunks JOIN files` path.

## Exclusion templates

Default exclusions:

```text
docs/plans/**
docs/ai_reports/**
```

Recommended optional exclusions for local configs:

```text
docs/archive/**
docs/tmp/**
docs/**/drafts/**
docs/**/*.bak.md
docs/**/*~.md
```

Non-Markdown extensions are rejected by the Markdown-only rule even when not excluded.

## Required implementation steps

1. Record current database schema behavior for `files`, `code_chunks`, vector ids, and FAISS mapping.
2. Record current file watcher behavior for file discovery, ignored paths, project rows, and update scheduling.
3. Record current indexing worker behavior for file-to-chunk processing.
4. Record current vectorization worker behavior for chunk-to-embedding-to-FAISS processing.
5. Record the existing chunker file command/API contract.
6. Add config model/defaults for `code_analysis.docs_indexing`.
7. Extend config generator with docs indexing options and safe defaults.
8. Extend config validator with strict Markdown-only checks.
9. Add watcher eligibility filtering for Markdown docs using roots/include/exclude.
10. Route eligible Markdown files through the existing file indexing path.
11. Route Markdown files to the existing chunker file command/API.
12. Persist Markdown chunks into existing `code_chunks` structures.
13. Ensure `docs_indexing.vectorize=false` prevents FAISS writes and semantic-search visibility for Markdown docs, but does not suppress chunk persistence or fulltext/BM25 data.
14. Ensure `docs_indexing.vectorize=true` reuses existing vectorization worker behavior.
15. Add tests for defaults, validator errors, include/exclude behavior, indexing without vectorization, fulltext/BM25 with vectorization disabled, and indexing with vectorization enabled.
16. Verify behavior through MCP commands and separate read/search commands.

## Required tests

### Config validator tests

1. Missing `docs_indexing` is valid.
2. `enabled=false`, `vectorize=false` is valid.
3. `enabled=true`, `vectorize=false` is valid.
4. `enabled=true`, `vectorize=true` is valid.
5. Non-boolean `enabled` fails.
6. Non-boolean `vectorize` fails.
7. Absolute roots fail.
8. Roots with `..` fail.
9. Include pattern `docs/**/*.txt` fails.
10. Include pattern `docs/**/*` fails.
11. Include pattern `**/*` fails.
12. Include pattern `docs/**/*.md` passes.
13. Include pattern `README.md` passes.

### Config generator tests

1. Generated default config has docs indexing disabled.
2. Generated default config has docs vectorization disabled.
3. Generated custom config preserves Markdown-only include patterns.
4. CLI help documents `.md` only.

### Watcher/indexing tests

Use a dedicated test project only.

1. With `enabled=false`, docs Markdown files are ignored by docs indexing.
2. With `enabled=true`, `docs/guide.md` is eligible.
3. With `enabled=true`, `docs/guide.txt` does not pass the watcher eligibility check and is not handed to the docs indexing path (distinct from the eligibility helper unit test: this verifies the watcher integration boundary, not just the filter logic).
4. With `enabled=true`, `docs/plans/task.md` is excluded by default.
5. With `enabled=true`, eligible Markdown files create/update existing `files` rows.
6. Eligible Markdown files are passed to the existing chunker file API.
7. Markdown chunks are persisted in existing `code_chunks` structures.

### Vectorization and search tests

1. With `enabled=true` and `vectorize=false`, Markdown chunks are persisted in `code_chunks`.
2. With `enabled=true` and `vectorize=false`, Markdown chunks keep chunker-returned token and BM25 data when available.
3. With `enabled=true` and `vectorize=false`, Markdown docs are returned by fulltext/BM25 search when the query matches.
2. With `enabled=true` and `vectorize=false`, `token_count` and `bm25_score` are NULL in persisted chunks (chunker is not called).
3. With `enabled=true` and `vectorize=false`, Markdown docs are not returned by `fulltext_search` (no bm25_score).
6. With `enabled=true` and `vectorize=true`, FAISS contains vector entries for Markdown chunks.
7. With `enabled=true` and `vectorize=true`, `semantic_search` can return Markdown docs via the existing `code_chunks JOIN files` path.

## MCP verification checklist

After implementation, verify with MCP-level behavior, not only unit tests:

1. Config generation command creates config with docs indexing disabled by default.
2. Config validation accepts default config.
3. Config validation rejects non-Markdown include patterns.
4. `list_project_files` can see Markdown files normally.
5. Indexing run with docs disabled does not index docs.
6. Indexing run with docs enabled indexes only eligible `.md` files.
7. Separate DB/read command verifies created `files` and `code_chunks` rows.
8. With vectorization disabled, `fulltext_search` returns matching Markdown docs.
9. With vectorization disabled, `semantic_search` does not return docs.
10. With vectorization enabled, `semantic_search` returns docs when query matches.
8. With vectorization disabled, `fulltext_search` does not return Markdown docs (bm25_score is NULL).
9. With vectorization disabled, `semantic_search` does not return docs.
10. With vectorization enabled, `fulltext_search` and `semantic_search` return docs when query matches.
12. Queue job status must be inspected through nested result success, not only `status=completed`.

## Documentation updates

Update or add docs after implementation:

```text
docs/COMMAND_METADATA_STANDARD.md
docs/COMMANDS_GUIDE.md
docs/PROJECT_RULES.md
```

Add a short user-facing section explaining:

- docs indexing is Markdown-only;
- docs indexing is disabled by default;
- docs vectorization is disabled by default;
- settings live in main config under `code_analysis.docs_indexing`;
- docs use the same chunks/vector search pipeline as code.

## Safety notes

Do not test destructive file/project operations on real projects.

For destructive lifecycle tests, use only dedicated test projects or temporary project copies.

## Resolved implementation decisions

1. Markdown documentation chunks must use the existing `ChunkType.DOC_BLOCK` / `"DocBlock"` contract. Do not introduce a new documentation-specific chunk type unless `chunk_metadata_adapter.ChunkType` is extended first and all consumers are checked.
2. The existing chunker file API supports Markdown input directly because it chunks plain file text. The input may be text, HTML, or Markdown; eligibility for this feature is restricted to `.md` by the watcher filter — other formats that the chunker accepts technically are rejected before reaching the chunker.
3. The chunker is called only when `vectorize=true`. It returns chunk texts, token information, BM25 data, and vector embeddings. When `vectorize=false`, the chunker is not called and these fields are NULL.
4. When `docs_indexing.enabled=true` and `docs_indexing.vectorize=false`, Markdown files get a `files` row but no chunks, no embeddings, and no FAISS entries. The indexing worker marks the file as processed without vectorization.
5. When `vectorize=false`, `fulltext_search` and `semantic_search` do not return Markdown docs. These docs become visible in search only when `vectorize=true` and the full chunker/embedding pipeline has run.
6. Do not add a dedicated diagnostics command for docs indexing in this task. Verify behavior with tests plus existing MCP commands: `list_project_files`, read/DB inspection commands, `fulltext_search`, `semantic_search`, `check_vectors`, and queue status checks where applicable.