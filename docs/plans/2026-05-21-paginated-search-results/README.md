# Paginated Search Results

Status: ready_for_review — AS layer green pass in progress; implementation not required for plan freeze.

**Machine plan:** `source_spec.md`, `spec.yaml`, `G-*/T-*/A-*/README.yaml` (GS/T layers `ready_for_review`; G-008 green pass 2026-05-23 — canonical contract `job_id` + `block_position` + `index_url`; T-006 test AS assert block model; wave 2 resolved G-007/T-006 vs G-008/T-005 `search_cancel_command.py` conflict — G-008/T-005 owns MCP lifecycle commands, G-007/T-006 owns queue-cancel hook only).

**Test coverage map:** [tests_required_coverage.yaml](./tests_required_coverage.yaml) — maps each of 12 unit + 6 MCP `tests_required` entries to covering AS (`0/18` covered by existing AS; **8 new AS** under G-008/T-006-test-wiring).

**Карта параллелизации:** [parallelization_map.yaml](./parallelization_map.yaml) — волны G/T/AS, serial chains, critical path, runtime notes. **Без лимита на число субагентов** — только one-file rule и depends_on.

## G-008 contract decision (canonical)

G-008 implementation uses **job_id + block_position + index_url**, not the README opaque `cursor` model below.

| README draft field | G-008 canonical field | Role |
| --- | --- | --- |
| `search_id` in `search_start` / lifecycle params | `job_id` | Client-visible SearchSession id (`SearchSession.search_id`) |
| `page.items` + `next_cursor` | `block_position` (1-based) + block JSON `items` | Each published `SearchResultBlock` is fetched by position from the job index |
| (not named in draft lifecycle) | `index_url` | HTTP index template, e.g. `/search/jobs/{job_id}/index` |
| `cursor` / `next_cursor` | **Not used** in G-008 MCP lifecycle | Opaque cursor remains a draft idea only; continuation is `job_id` + next `block_position` |

**Mapping rules:**

- `search_start` with `paginated=true` returns `job_id`, `index_url`, and `first_block_position` (or `null` when no block yet).
- `search_get_page` requires `job_id`; optional `block_position` defaults to `1`; response includes `items` from `blocks/block_{n}.json`, not cursor slices.
- `search_get_status`, `search_cancel`, and `search_close` all use `job_id` (not `search_id`).
- HTTP block reads use the same `job_id` and block position as MCP; `index_url` points at the directory index listing published positions.
- Plan AS, tests (`G-008/T-006`), and `existing_behavior_inventory.yaml` follow this mapping. README YAML blocks below retain draft cursor wording for historical context only.

This plan captures the initial task/specification for adding paginated and resumable search results to `code-analysis-server` search commands.

```yaml
spec_id: paginated-search-results
language: en
project: code-analysis-server
package: code_analysis
priority: high
status: ready_for_review

title: >
  Add paginated and resumable search results for fulltext, semantic, fs_grep,
  project_cross_search, and future tree-query/xpath search.

problem:
  current: >
    Search commands return one bounded result set. Long searches either block,
    auto-queue, or return only the final payload. The model cannot inspect early
    results while the algorithm is still running, cannot request the next page,
    and cannot adjust the viewing window without re-running the whole search.
  desired: >
    Search commands must support paginated, resumable result retrieval. A long
    search should create a search session/job, accumulate results incrementally,
    and allow clients to fetch result pages while the search is still running.

goals:
  - Support pagination for fs_grep.
  - Support pagination for fulltext_search.
  - Support pagination for semantic_search.
  - Support pagination for project_cross_search merged results.
  - Support the same model for future tree_query / xpath_search.
  - Allow clients to preview early results before the full search completes.
  - Allow clients to control page size/window.
  - Avoid returning huge payloads.
  - Preserve queue/hard-timeout behavior.
  - Keep search result identity stable across pages.

non_goals:
  - Do not require streaming transport.
  - Do not replace queue_get_job_status.
  - Do not remove existing non-paginated command compatibility immediately.
  - Do not make grep scan indexed unchanged files again.
  - Do not expose line-only grep as cross-search evidence when structural grep is required.

core_concept:
  name: SearchSession
  description: >
    A server-side persisted or semi-persisted result buffer for one search
    execution. It stores normalized result rows, search metadata, progress,
    warnings, errors, and cursor/page state.

new_commands:
  search_start:
    description: Start a search using a selected backend or orchestration mode.
    params:
      project_id: {type: string, required: true}
      search_type: {type: string, enum: [fulltext, semantic, grep, cross, tree_query], required: true}
      query: {type: string, required: false}
      grep_patterns: {type: array, items: {type: string}, required: false}
      xpath: {type: string, required: false}
      file_pattern: {type: string, required: false}
      page_size: {type: integer, default: 20, minimum: 1, maximum: 200}
      auto_queue_on_inline_timeout: {type: boolean, default: true}
      inline_timeout_seconds: {type: number, default: 3.0}
      hard_timeout_seconds: {type: number, default: 120.0}
      include_preview: {type: boolean, default: false}
      require_structural_grep: {type: boolean, default: true}
      scan_all: {type: boolean, default: false}
    returns:
      inline_completed:
        success: true
        search_id: string
        status: completed
        page: {items: list, next_cursor: string|null, page_size: integer}
        summary: object
      running:
        success: true
        search_id: string
        status: running|queued|pending
        job_id: string|null
        page: {items: list, next_cursor: string|null, page_size: integer}
        message: Search started. First page may contain partial results.

  search_get_page:
    description: Fetch a page from an existing SearchSession.
    params:
      search_id: {type: string, required: true}
      cursor: {type: string, required: false}
      page_size: {type: integer, default: 20, minimum: 1, maximum: 200}
      wait_for_new_results: {type: boolean, default: false}
      wait_timeout_seconds: {type: number, default: 0, minimum: 0, maximum: 30}
    returns:
      success: true
      search_id: string
      status: running|completed|failed|cancelled|timed_out
      page: {items: list, cursor: string|null, next_cursor: string|null, has_more: boolean, page_size: integer}
      progress:
        scanned_files: integer|null
        candidate_files: integer|null
        produced_results: integer
        consumed_results: integer
      warnings: list
      errors: list

  search_get_status:
    description: Return status/progress without returning result rows.
    params:
      search_id: {type: string, required: true}
    returns:
      success: true
      search_id: string
      status: string
      progress: object
      summary: object
      warnings: list
      errors: list

  search_cancel:
    description: Cancel a running search session and stop underlying queued work when possible.
    params:
      search_id: {type: string, required: true}
    returns: {success: true, cancelled: boolean}

  search_close:
    description: Release stored result buffers for a search session.
    params:
      search_id: {type: string, required: true}
    returns: {success: true, closed: boolean}

result_model:
  SearchResultItem:
    fields:
      result_id: {type: string, description: Stable id for this result within search_id.}
      rank: {type: number}
      source: {enum: [fulltext, semantic, grep_unindexed, grep_changed, grep_draft, tree_query, cross]}
      file_path: {type: string}
      line_number: {type: integer|null}
      start_line: {type: integer|null}
      end_line: {type: integer|null}
      node_ref: {type: string|null}
      selector: {type: string|null}
      preview: {type: object|null}
      text: {type: string|null}
      score: {type: number|null}
      confidence: {enum: [low, medium, high, null]}
      evidence: {type: object|null}
      diagnostics: {type: object|null}

cursor_model:
  type: opaque_string
  requirements:
    - Cursor must be opaque to clients.
    - Cursor must be stable for a given search_id.
    - Cursor must not expose DB offsets directly if that creates unsafe coupling.
    - Cursor may encode result index and generation number.
    - Cursor must remain valid until search session expires or is closed.

pagination_policy:
  default_page_size: 20
  max_page_size: 200
  result_buffer_limit:
    default: 10000
    behavior: If more results are produced, keep best ranked items and/or spill to disk/DB.
  ordering:
    fulltext: bm25 desc
    semantic: score desc
    grep: file_path asc, line_number asc unless rank override exists
    cross: confidence desc, evidence_score desc, score desc
    tree_query: file_path asc, start_line asc
  stable_order_requirement: >
    Once a result is visible on a page, it must not move to a previous page.
    Later higher-ranked results may appear in later pages unless the search is
    completed and final_sort=true is requested.

fs_grep_changes:
  requirement: fs_grep must be able to produce results incrementally into SearchSession.
  behavior:
    - Text mode may page line matches.
    - Structural mode must page only enriched matches when required.
    - Grep must continue respecting scan_all=false, include_logs=false, index-gap filtering, hard timeout, and inline timeout.
    - Grep should flush page-ready batches periodically after N matches, M files scanned, or T seconds.

fulltext_search_changes:
  requirement: fulltext_search must support offset/cursor pagination.
  implementation_options:
    - SQL LIMIT/OFFSET for simple first version.
    - Keyset pagination for production version.
  required_fields: [bm25_score, entity_type, entity_name, file_path, content snippet]

semantic_search_changes:
  requirement: semantic_search must support pagination even if backend returns top_k.
  behavior:
    - First version may request top_k = cursor_offset + page_size and slice.
    - Production version should support backend-native paging if available.
    - Results must be JSON-safe scalars.

project_cross_search_changes:
  requirement: project_cross_search must support paginated merged evidence.
  behavior:
    - semantic/fulltext/grep sources may complete at different times.
    - SearchSession stores normalized evidence by file_path.
    - Partial pages may be returned while sources are still running.
    - If grep times out, already merged grep evidence is dropped unless fully structural.
    - line-only grep must not count as evidence when require_structural_grep=true.
    - source_counts must include semantic, fulltext, grep_raw, grep_structural, grep_line_only_ignored, tree_query.

future_tree_query_changes:
  requirement: XPath-like/tree-query search must use the same SearchSession pagination.
  search_type: tree_query
  behavior:
    - Scan only known tree formats by default.
    - Query structural blocks/nodes, not raw text.
    - Return preview-compatible node_ref or selector.
    - Support disk and draft_session sources.
    - Return pages as soon as per-file tree query results are available.

storage:
  option_v1: {type: in_memory, ttl_seconds: 1800, max_sessions: 100}
  option_v2: {type: database, description: Store search_sessions and search_results tables for restart resilience.}
  recommendation: {start_with: in_memory, migrate_to: database_if_needed}

timeouts:
  inline_timeout: {constant: SEARCH_INLINE_TIMEOUT_SECONDS, default: 3.0}
  hard_timeout: {constant: SEARCH_HARD_TIMEOUT_SECONDS, default: 120.0}
  page_wait_timeout: {default: 0, max: 30}

compatibility:
  existing_commands:
    fs_grep:
      behavior: Existing direct fs_grep may continue returning one result payload. Add optional paginated=true to use SearchSession.
    fulltext_search:
      behavior: Add page_size/cursor, but keep old limit behavior.
    semantic_search:
      behavior: Add page_size/cursor, but keep old limit behavior.
    project_cross_search:
      behavior: Add paginated=true. Existing non-paginated call may internally use SearchSession and return first page plus search_id.

schema_additions_common:
  paginated: {type: boolean, default: false}
  page_size: {type: integer, default: 20, minimum: 1, maximum: 200}
  cursor: {type: string, required: false}
  include_search_id: {type: boolean, default: true}

tests_required:
  unit:
    - search_session_create_and_page
    - search_session_cursor_stability
    - search_session_page_size_override
    - fs_grep_paginated_first_page_before_completion
    - fulltext_pagination_preserves_order
    - semantic_pagination_json_safe
    - cross_search_pages_structural_grep_only
    - cross_search_grep_timeout_drops_grep_evidence
    - search_cancel_stops_running_grep
    - search_close_releases_buffer
    - cursor_invalid_after_close
    - queued_search_does_not_autoqueue_recursively
  mcp:
    - start_cross_search_returns_search_id
    - get_first_page_while_running
    - preview_result_from_first_page
    - request_next_page
    - cancel_long_grep_search
    - server_responsive_during_running_search

definition_of_done:
  - Long search can return search_id before completion.
  - Client can fetch first page while search is still running.
  - Client can fetch next pages with cursor.
  - Page size can be adjusted per request.
  - fs_grep, fulltext, semantic, project_cross_search support pagination.
  - Timed-out grep does not count as evidence.
  - Structural grep evidence remains preview-compatible.
  - Search buffers have TTL/close cleanup.
  - Server remains responsive during long searches.
```

Key architectural idea:

```text
search command must not be only "return everything".
It must become "create a search session, return the first page, then the client paginates".
```

Expected model workflow:

```text
1. start search
2. inspect first page
3. preview interesting files
4. request next page
5. refine query or stop
```

For XPath/tree-query this is especially important: structural search over files can be expensive, but the first matched nodes can already be inspected before the whole project traversal finishes.
