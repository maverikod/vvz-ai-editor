# Git commit on write (code_analysis.git_commit_on_write)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Config option

In `config.json`, under `code_analysis`:

- **`git_commit_on_write`** (boolean, default: false)

When **true**, the server will create a git commit after every write command completes, and for refactor commands also **before** the command runs (snapshot of state before refactor).

When **false**, no automatic commit is made; backup/version is used instead (backup is created before overwrite by the relevant commands).

## Behaviour

- **All write commands** (cst_save_tree, compose_cst_module, cst_convert_and_save, cst_create_file): after a successful write, if `git_commit_on_write` is true, the server runs `git add` and `git commit` for the written path(s). Commit message is the one passed by the user (e.g. `commit_message` param) or a default like `cst_save_tree: filename.py`.
- **Refactor commands** (split_class, extract_superclass, split_file_to_package):  
  - **Before** the refactor: if `git_commit_on_write` is true, a commit is created (e.g. "Before split_class: path/to/file.py").  
  - **After** a successful refactor: if `git_commit_on_write` is true, a commit is created for the modified/created files.  
  - Backup (old_code) is always created before refactor regardless of this option.

## Requirements

- Project root must be a git repository (`.git` present).
- `git` must be available on the server.
- If git is not available or the path is not a repo, the commit is skipped and a warning is logged; the write still succeeds.

## If not using git

When `git_commit_on_write` is false (or not set), no commit is made. Commands that overwrite files still create a **backup/version** (e.g. via BackupManager in `old_code`) before writing, so you can restore with `restore_backup_file` if needed.

## Example

```json
{
  "code_analysis": {
    "git_commit_on_write": true,
    ...
  }
}
```
