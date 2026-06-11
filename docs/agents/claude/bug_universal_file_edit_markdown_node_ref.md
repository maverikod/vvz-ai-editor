# BUG: universal_file_edit UNKNOWN_NODE_REF — root cause identified

**Date:** 2026-05-23  
**Status:** Root cause identified, not a server bug.

## Summary

During editing of `source_spec.md`, `universal_file_edit` repeatedly returned
`UNKNOWN_NODE_REF`. After investigation, this is not a server defect.

## Root cause

The edit session (`session_id` from `universal_file_open`) is lost on server
restart. `node_ref` values obtained from `universal_file_preview` **without**
`session_id` are stable UUIDs from the on-disk tree, but they are not registered
in any active session. Passing them to `universal_file_edit` always fails with
`UNKNOWN_NODE_REF` because the server looks up the node in the session draft,
not on disk.

The correct workflow requires that `universal_file_preview` is called **with the
same `session_id`** that was returned by `universal_file_open`, and that the
session has not expired (server restart invalidates all sessions).

## Correct workflow

1. `universal_file_open` → `session_id`
2. `universal_file_preview(session_id=...)` → `node_ref` UUIDs from the draft
3. `universal_file_edit(session_id=..., operations=[{node_ref: ..., ...}])` → OK
4. `universal_file_write(write_mode="preview")` → diff
5. `universal_file_write(write_mode="commit")` → write to disk
6. `universal_file_close` → release session

## Key rule

Never reuse `node_ref` across sessions or after a server restart.
Always call `universal_file_preview` with `session_id` immediately before `universal_file_edit`.
