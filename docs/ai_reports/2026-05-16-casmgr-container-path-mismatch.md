# Bug Report: casmgr status fails inside mcp-terminal container (pid_namespace=host)

**Date:** 2026-05-16
**Reporter:** Claude
**Severity:** Medium — casmgr unusable from container when server runs on host
**File:** `code_analysis/cli/server_manager_cli.py`

## Summary

`casmgr status` reports `stopped (pidfile pid=N alive but no daemon for this
config; pidfile likely stale)` when called from inside a Docker container
(mcp-terminal with `pid_namespace=host`) while the server runs on the host.
The server is actually running; the bug is in path comparison inside
`_find_daemon_pids`.

## Environment

- Server runs on host: `pid=245341`, cwd=`/home/vasilyvz/projects/tools/code_analysis`
- casmgr called from container: `/workspace` is a bind-mount of the same directory
- Container has `pid_namespace=host` so `/proc/<pid>/cwd` is accessible

## Root cause

`_find_daemon_pids` compares resolved config paths:

```python
cfg_resolved = str(Path(config_path).resolve())
# config_path inside container: /workspace/config.json
# cfg_resolved: /workspace/config.json

# Then for each matching process in ps:
resolved = _resolved_config_path_for_daemon_pid(pid, cfg_val)
# cfg_val from ps: "config.json" (relative, as stored by _spawn_daemon)
# /proc/<pid>/cwd resolves to: /home/vasilyvz/projects/tools/code_analysis
# resolved = /home/vasilyvz/projects/tools/code_analysis/config.json

if resolved == cfg_resolved:  # FAILS: different mount paths, same file
    pids.append(pid)
```

The comparison fails because `/workspace/config.json` and
`/home/vasilyvz/projects/tools/code_analysis/config.json` are the same
file (same inode, same bind-mount) but have different string paths.

## Trace

```
_cmd_status("/workspace/config.json")
  _find_daemon_pids("/workspace/config.json")  # returns []
    cfg_resolved = "/workspace/config.json"
    ps output: pid=245341 ... -m code_analysis.main --config config.json --daemon
    cfg_val = "config.json"
    _resolved_config_path_for_daemon_pid(245341, "config.json")
      /proc/245341/cwd -> /home/vasilyvz/projects/tools/code_analysis
      returns "/home/vasilyvz/projects/tools/code_analysis/config.json"
    "/home/vasilyvz/.../config.json" == "/workspace/config.json"  # False
  # pids = [] -> no daemon found
  pf_pid = 245341  # alive
  -> "stopped (pidfile pid=245341 alive but no daemon for this config)"
```

## Proposed fix

In `_resolved_config_path_for_daemon_pid` or in `_find_daemon_pids`,
after path string comparison fails, add an inode comparison:

```python
# After string comparison fails:
if resolved is not None and resolved != cfg_resolved:
    try:
        if os.path.samefile(resolved, cfg_resolved):
            pids.append(pid)
            continue
    except OSError:
        pass
```

`os.path.samefile` compares inodes and device numbers — works correctly
for bind-mounts regardless of the path prefix used to reach the file.

## Affected function

`_find_daemon_pids` in `code_analysis/cli/server_manager_cli.py` — the
section after `resolved = _resolved_config_path_for_daemon_pid(pid, cfg_val)`.

## Test case

A test should mock `_resolved_config_path_for_daemon_pid` to return a
different path that points to the same inode as `config_path`, and verify
that `_find_daemon_pids` still returns the PID.
