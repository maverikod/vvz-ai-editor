# Parallelization map

## Scope

This map defines safe parallel execution for the Markdown docs indexing and optional vectorization plan.

Main rule: parallel work is allowed only where interfaces are stable and no two performers modify the same pipeline boundary at the same time.

Pipeline order:

```text
config
  -> eligibility
  -> watcher
  -> files rows
  -> chunker file API
  -> code_chunks persistence
  -> fulltext/BM25
  -> optional FAISS/vectorization
  -> search verification
```

## Global decisions

- Only `.md` files are in scope.
- `docs_indexing.enabled=false` by default.
- `docs_indexing.vectorize=false` by default.
- Chunker accepts Markdown as ordinary text input.
- Chunker returns chunks, vectors, token data, BM25 data, and source text fragments.
- Markdown chunks use `ChunkType.DOC_BLOCK` / `"DocBlock"`.
- With `vectorize=false`, chunks must still be persisted and fulltext/BM25 search must work.
- With `vectorize=false`, FAISS/semantic visibility must be disabled.
- No dedicated diagnostics command is required for this task.
- Verification must be done by tests plus existing MCP commands.

## Dependency groups

### Group A — Preflight / inventory

Steps:

- `01-current-state-inventory`

Must run first.

Outputs required before implementation:

- actual DB behavior for `files` and `code_chunks`;
- actual vector/FAISS mapping behavior;
- actual watcher behavior;
- actual indexing worker behavior;
- actual chunker file API behavior;
- actual `semantic_search` and `fulltext_search` behavior.

Parallelism: limited.

Safe parallel subtasks:

- DB/schema inventory;
- watcher inventory;
- indexing worker inventory;
- vectorization/search inventory.

Do not start implementation before inventory conclusions are recorded.

### Group B — Config contract

Steps:

- `02-config-contract`
- `03-config-validator-generator`

Can run after Group A starts, but final implementation must align with Group A findings.

Safe parallelism:

- one performer writes/updates config contract docs;
- one performer implements validator changes;
- one performer implements generator/CLI changes.

Shared boundary:

```text
code_analysis.docs_indexing
```

Required synchronization point:

- field names;
- defaults;
- validator strictness;
- CLI option names.

Do not let validator and generator diverge.

### Group C — Markdown eligibility

Steps:

- `04-markdown-eligibility`

Can run in parallel with Group B after config shape is stable.

Responsibilities:

- implement single eligibility helper;
- enforce `.md` suffix;
- enforce project-relative paths;
- enforce roots/include/exclude;
- ensure exclude wins over include.

This group should not edit watcher/indexer internals except through planned integration points.

Required output:

```text
is_docs_markdown_eligible(...)
```

or equivalent single reusable helper.

### Group D — Watcher integration

Steps:

- `05-watcher-integration`

Depends on:

- Group B config contract;
- Group C eligibility helper;
- Group A watcher inventory.

Do not run in parallel with indexing-persistence changes unless interfaces are frozen.

Responsibilities:

- load `code_analysis.docs_indexing`;
- keep current behavior unchanged when disabled;
- pass only eligible `.md` files into indexing path;
- preserve existing ignore behavior for `.venv`, caches, hidden dirs, and deleted paths.

Risk level: medium.

Reason: watcher is a live pipeline entry point.

### Group E — Indexing and chunk persistence

Steps:

- `06-indexing-chunker-integration`

Depends on:

- Group A DB/indexer/chunker inventory;
- Group C eligibility helper;
- Group D watcher route or an agreed direct indexing entry point.

Responsibilities:

- route eligible `.md` files to existing chunker file API;
- persist Markdown chunks into existing `code_chunks`;
- use `ChunkType.DOC_BLOCK` / `"DocBlock"`;
- preserve token/BM25/source fragment data when available;
- avoid new `docs_chunks` or `docs_vectors`.

Risk level: high.

Reason: this is the core data pipeline boundary.

Do not run concurrently with Group F unless chunk persistence contract is frozen.

### Group F — Vectorization gate

Steps:

- `07-vectorization-gating`

Depends on:

- Group E chunk persistence;
- Group A vectorization inventory.

Responsibilities:

- with `vectorize=false`, prevent FAISS writes and semantic visibility;
- with `vectorize=false`, do not suppress chunk persistence or fulltext/BM25;
- with `vectorize=true`, reuse existing vectorization worker;
- do not create a separate docs vectorizer.

Risk level: high.

Reason: the difference between fulltext and semantic behavior must be exact.

### Group G — Search behavior

Steps:

- `08-search-and-diagnostics`

Depends on:

- Group E chunk persistence;
- Group F vectorization gate.

Responsibilities:

- verify `fulltext_search` returns Markdown when `vectorize=false`;
- verify `semantic_search` does not return Markdown when `vectorize=false`;
- verify `semantic_search` can return Markdown when `vectorize=true`;
- avoid adding a new diagnostics command unless an unavoidable gap appears.

Can run partly in parallel with Group F only for read-only inspection and test design.

Do not finalize before Group F behavior is implemented.

### Group H — Tests and MCP verification

Steps:

- `09-tests-and-mcp-verification`

Depends on all implementation groups.

Can prepare test skeletons earlier.

Must verify:

- config defaults;
- validator errors;
- include/exclude behavior;
- Markdown indexing disabled behavior;
- Markdown indexing enabled behavior;
- `code_chunks` persistence;
- fulltext/BM25 with `vectorize=false`;
- no FAISS/semantic result with `vectorize=false`;
- FAISS/semantic result with `vectorize=true`;
- queue nested success, not only completed/progress.

This group is final gate before docs rollout.

### Group I — Docs and rollout

Steps:

- `10-docs-and-rollout`

Depends on:

- Group H verification results;
- known limitations;
- final behavior.

Can prepare draft docs earlier, but must not finalize before MCP verification.

## Recommended execution waves

### Wave 0 — Single coordination pass

Owner: lead performer.

Tasks:

- read all index files;
- confirm final decisions;
- record inventory requirements;
- freeze config field names;
- freeze chunk type decision;
- freeze `vectorize=false` search contract.

Output:

```text
implementation-decisions.md
```

or equivalent section in the plan.

### Wave 1 — Parallel preparation

Can run in parallel:

- Performer 1: DB/schema/vector/search inventory.
- Performer 2: watcher/indexing/chunker inventory.
- Performer 3: config contract, validator, generator plan.
- Performer 4: eligibility helper design and tests.

Do not edit shared pipeline code yet except isolated validator/generator/eligibility files.

### Wave 2 — Independent implementation

Can run in parallel with coordination:

- Config validator/generator implementation.
- Eligibility helper implementation.
- Unit tests for config and eligibility.

Synchronization required before moving forward:

- generated config matches validator;
- eligibility helper accepts the same config shape;
- `.md` strictness is tested.

### Wave 3 — Pipeline integration

Mostly sequential:

1. Watcher integration.
2. Indexing/chunker integration.
3. `code_chunks` persistence verification.
4. Vectorization gate.

Parallel work allowed only for tests and docs drafts.

### Wave 4 — Search verification

Sequential after pipeline integration:

1. Verify `vectorize=false` chunk persistence.
2. Verify `fulltext_search` returns Markdown.
3. Verify `semantic_search` does not return Markdown.
4. Enable vectorization in test config.
5. Verify FAISS/vector entries.
6. Verify `semantic_search` returns Markdown.

### Wave 5 — Finalization

Can run in parallel after Wave 4:

- final docs;
- rollout notes;
- known limitations;
- MCP verification report.

Final merge only after all MCP checks pass.

## Unsafe parallelism

Do not parallelize these without explicit interface freeze:

- watcher integration and indexing route changes;
- indexing persistence and vectorization gate changes;
- chunk type changes and search consumers;
- config field changes and validator/generator/eligibility implementation;
- FAISS mapping changes and `semantic_search` changes.

## Suggested performer split

### Performer A — Config and eligibility

Owns:

- `02-config-contract`
- `03-config-validator-generator`
- `04-markdown-eligibility`

May edit:

- config validator source;
- config generator source;
- CLI config source;
- eligibility helper;
- related unit tests.

Must not edit:

- watcher internals beyond agreed integration point;
- vectorization worker internals;
- `.venv`;
- `site-packages`.

### Performer B — Watcher and indexing

Owns:

- `05-watcher-integration`
- `06-indexing-chunker-integration`

May edit:

- watcher integration;
- indexing worker route;
- chunker file API integration;
- `code_chunks` persistence path;
- integration tests.

Must not edit:

- config field names after freeze;
- vectorization semantics without Performer C coordination;
- `.venv`;
- `site-packages`.

### Performer C — Vectorization and search

Owns:

- `07-vectorization-gating`
- `08-search-and-diagnostics`

May edit:

- vectorization gating;
- FAISS eligibility selection;
- search tests;
- verification scripts/docs.

Must preserve:

- fulltext/BM25 works with `vectorize=false`;
- semantic/FAISS visibility is disabled with `vectorize=false`;
- semantic/FAISS visibility works with `vectorize=true`.

### Performer D — Verification and rollout

Owns:

- `09-tests-and-mcp-verification`
- `10-docs-and-rollout`

May prepare early drafts, but final docs depend on MCP verification.

Must record:

- command;
- expected;
- actual;
- error;
- root cause;
- fix;
- post-fix verification;
- status.

## Completion gate

The work is complete only when:

- config defaults are safe;
- validator rejects invalid Markdown patterns;
- eligibility is tested;
- watcher behavior is unchanged when disabled;
- eligible `.md` files create/update `files` rows;
- Markdown chunks are persisted in `code_chunks`;
- fulltext/BM25 returns Markdown with `vectorize=false`;
- FAISS/semantic search does not return Markdown with `vectorize=false`;
- FAISS/semantic search returns Markdown with `vectorize=true`;
- behavior is verified through MCP commands and separate read/search commands;
- observations are recorded.
