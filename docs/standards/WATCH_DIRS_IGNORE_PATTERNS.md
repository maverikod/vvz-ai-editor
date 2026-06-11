# Watch directories and per-dir ignore patterns

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

Each watched directory in `code_analysis.worker.watch_dirs` can define its own **ignore patterns**. Files and directories matching these patterns are not indexed (not added to the database by the file watcher). Patterns are glob-style (e.g. `**/.venv/**`). Per-dir patterns are merged with the global `code_analysis.file_watcher.ignore_patterns` when scanning that directory.

This allows excluding virtualenvs (e.g. `.venv`, `venv`) and other paths per watch dir so they are never indexed.

## Config format

```json
"code_analysis": {
  "worker": {
    "watch_dirs": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "path": "/absolute/path/to/watch",
        "ignore_patterns": ["**/.venv/**", "**/venv/**", "**/__pycache__/**"]
      }
    ]
  },
  "file_watcher": {
    "ignore_patterns": ["**/.git/**", "**/node_modules/**"]
  }
}
```

- **id** (required): UUID4 for the watch directory.
- **path** (required): Absolute path to the directory to scan for projects.
- **ignore_patterns** (optional): List of glob patterns. Paths matching any of these under this watch dir are not indexed. Merged with `file_watcher.ignore_patterns` and with built-in defaults (e.g. `.venv`, `venv` in scanner defaults).

## Recommended Python service dirs

To avoid indexing Python virtualenvs, caches, and build artifacts, include at least:

- Virtualenvs: `**/.venv/**`, `**/venv/**`, `**/ENV/**`, `**/env/**`
- Caches: `**/__pycache__/**`, `**/.pytest_cache/**`, `**/.mypy_cache/**`, `**/.cache/**`
- Eggs and build: `**/.eggs/**`, `**/eggs/**`, `**/*.egg-info/**`, `**/*.egg`, `**/develop-eggs/**`, `**/dist/**`, `**/build/**`, `**/wheels/**` (do not add `**/lib/**` so as not to hide project library dirs)
- Tools: `**/.tox/**`, `**/htmlcov/**`, `**/.coverage`, `**/node_modules/**`

## Examples

- Exclude virtualenvs in all projects under this watch dir:  
  `["**/.venv/**", "**/venv/**"]`
- Full set of Python service dirs (see recommended list above).

After changing `watch_dirs` or `ignore_patterns`, restart the server (or restart the file watcher) for changes to take effect.
