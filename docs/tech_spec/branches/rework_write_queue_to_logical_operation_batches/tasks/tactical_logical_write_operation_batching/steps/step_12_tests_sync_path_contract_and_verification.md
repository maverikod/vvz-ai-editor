# Atomic step 12: Contract test + repo verification (`rg`) for sync path

## Executor role

`coder_auto`

## Execution directive

1. **Create** new file `tests/test_logical_write_sync_path_contract.py` with tests that enforce the **sync path contract** after step 07:
   - **`test_sync_file_to_db_atomic_source_no_transaction_helpers`:** Read the file `code_analysis/core/database/file_tree_sync.py` as text from the repository (use `pathlib.Path(__file__).resolve().parents[...]` to locate repo root → `code_analysis/core/database/file_tree_sync.py`). Assert the **substrings** `begin_transaction`, `commit_transaction`, `rollback_transaction`, and `execute_batch` **do not** appear in the file body **except** allowed contexts:
     - **Allowed:** comments or docstrings that **mention** old behavior — **forbid** even docstring mentions if possible; **fixed rule:** assert **none** of these four substrings appear in the file at all after step 07. If step 07 left them only in docstrings, relax assertion to: **no line** outside docstrings — **simplest fixed rule:** assert **`begin_transaction(`** and **`execute_batch(`** and **`commit_transaction(`** and **`rollback_transaction(`** do not appear (function call forms) — this allows docstring prose without parentheses.
   - **`test_update_file_data_atomic_batch_uses_logical_write_only`:** Same pattern for `code_analysis/core/database_client/file_data_batch.py`: assert **`begin_transaction(`** not in file, **`execute_batch(`** not in file (except possibly in **comments** describing old behavior — prefer zero occurrences of `execute_batch(`).

2. **Document** in the test module docstring that these are **guardrails** against reintroducing multi-RPC transaction sequences.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_logical_write_sync_path_contract.py`
- **action:** `create`

## Dependency contract

- **Depends on:** steps 06–07.

## Read first

- `tests/conftest.py` (if path helpers exist — optional)

## Forbidden alternatives

- Do **not** shell out to `rg` from tests — use Python string checks for portability.

## Mandatory validation (shell — human / CI)

After implementing, run from repo root:

```bash
. .venv/bin/activate
rg -n "begin_transaction\(|execute_batch\(|commit_transaction\(|rollback_transaction\(" code_analysis/core/database/file_tree_sync.py || true
rg -n "begin_transaction\(|execute_batch\(" code_analysis/core/database_client/file_data_batch.py || true
pytest tests/test_logical_write_sync_path_contract.py -v
pytest -q
```

**Expected:** `rg` shows **no** matches for `file_tree_sync.py`. For `file_data_batch.py`, **no** `begin_transaction(` or **`execute_batch(`** — if `execute_batch` string appears in a comment, remove comment or adjust test to allow only comment lines (coder must choose: **prefer** removing misleading comments).

**Completion:** full `pytest -q` passes; `rg` lines **empty** for `file_tree_sync.py` call-pattern search.

## Blackstops

- If `file_data_batch.py` must retain the **identifier** `execute_batch` in a string for logging, **rename log message** to avoid false test failure — **do not** weaken contract test without orchestrator approval.

---

## LLAMA-readiness appendix

### Module docstring (exact)

```text
"""
Contract tests: logical write sync path must not reintroduce multi-RPC transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

### Imports

```text
from __future__ import annotations

from pathlib import Path
```

### Functions

```python
def _repo_root() -> Path:
    ...

def test_sync_file_to_db_atomic_source_no_transaction_helpers() -> None:
    ...

def test_update_file_data_atomic_batch_uses_logical_write_only() -> None:
    ...
```

### `_repo_root` algorithm

1. Start from `Path(__file__).resolve()`.
2. Walk **parents** until a directory contains **both** `code_analysis` subdirectory and `pyproject.toml` or `setup.py` or `.git` — use the **first** condition that matches this repo’s layout; **fixed:** walk until `path.joinpath("code_analysis", "core").is_dir()`.

### Assertion details

- Read text as UTF-8.
- Forbidden **call** substrings exactly: `begin_transaction(`, `execute_batch(`, `commit_transaction(`, `rollback_transaction(` for `file_tree_sync.py`.
- For `file_data_batch.py`: forbid `begin_transaction(` and `execute_batch(`.

### Error handling

- If file not found, `pytest.fail` with message.

### Edge cases

- Windows paths: not required (Linux CI).
