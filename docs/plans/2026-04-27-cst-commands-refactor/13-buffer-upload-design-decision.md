# Step 13 -- Buffer-based replacement workflow: design decision

Date: 2026-04-28
Status: DESIGN COMPLETE -- decision: Option A (use existing mechanism as-is)

---

## Investigation answers

### Q1: What does transfer_upload_begin return? Does transfer_id persist on disk?

transfer_upload_begin calls TransferServerStore.create_upload_session().
Returns TransferReceipt with transfer_id (format: "tr_<uuid>").
The session is persisted on disk immediately as a JSON file in:
  <storage_dir>/sessions/<transfer_id>.json
The uploaded file bytes land in:
  <storage_dir>/files/<transfer_id>  (identity compression)
The session survives server restarts -- disk-backed, not in-memory only.

### Q2: After transfer_upload_complete -- where is the content? How to get the path?

After complete_upload_session() the session.status = "uploaded".
Two methods exist for downstream use:

  store.get_committed_upload_path(transfer_id) -> str
    Returns session.storage_path -- the absolute path on the server disk.
    Raises if not upload or not complete.

  store.get_completed_transfer(transfer_id) -> dict
    Returns: transfer_id, local_path (= storage_path), filename,
             compression, checksum_algorithm, checksum_value,
             size_bytes, chunk_size, offset, status, expires_at.

So after transfer_upload_complete the server already has the code
as a local file at session.storage_path. No additional download needed.

### Q3: Is there an existing command that reads a server-side path and uses it as CST replacement?

No. fulltext_search for replace_block_from_file, cst_apply_buffer,
transfer_id, local_path in code_analysis commands returns 0 results.
The transfer mechanism in code_analysis today is used only for
transfer_download_begin (sending files TO the client).
There is no command that reads a completed upload buffer and applies it as CST.

---

## Decision: Option A -- use existing transfer mechanism, no new command

Rationale: the adapter already stores the uploaded file at a known local_path
on the server disk after transfer_upload_complete. A new command cst_apply_buffer
can simply accept transfer_id, call get_committed_upload_path() internally
to get the path, read the file, and pipe the content into the existing
compose_cst_module ops flow. No new HTTP routes, no new storage layer.

The only new thing is cst_apply_buffer as a thin MCP command in code_analysis
that bridges transfer_id -> local file read -> CST replace.

---

## New command design: cst_apply_buffer

File: code_analysis/commands/cst_apply_buffer_command.py

Inputs (MCP schema):
  project_id: str           -- required
  file_path: str            -- target .py file (relative to project root)
  transfer_id: str          -- from transfer_upload_complete
  selector: dict            -- same selector format as compose_cst_module ops
                               (kind: function/method/class/range/node_id/...)
  apply: bool = True        -- False = preview only
  validate_syntax_only: bool = False
  create_backup: bool = True
  return_diff: bool = False
  commit_message: str = None

Behavior:
  1. Validate transfer_id via store.get_committed_upload_path(transfer_id).
     Fail fast with TRANSFER_NOT_FOUND or TRANSFER_NOT_COMPLETE.
  2. Read replacement code from local_path (identity: read as text;
     gzip: decompress first -- check session.compression).
  3. Build a single-op ops list:
     [{"selector": selector, "new_code": code_from_buffer}]
  4. Call run_ops_mode() with the ops list -- reuse existing validate/backup/write pipeline.
  5. Return same result fields as compose_cst_module:
     file_written, preview_only, backup_uuid, diff, stats.

Why this avoids the safety filter:
  The large code payload is uploaded in advance via transfer API (chunked PUT).
  The cst_apply_buffer MCP call only passes transfer_id (short string) + selector.
  No large code payload in the JSON-RPC request body.

---

## Access to TransferServerStore from code_analysis command

The command needs to call store.get_committed_upload_path(transfer_id).
Options:
  A. Import TransferServerStore directly and instantiate with config.
     Adapter exposes it as mcp_proxy_adapter.transfer.server_store.TransferServerStore.
     The storage_dir is in config (code_analysis reads config.json).
     This is the cleanest approach -- no new RPC, no extra hop.

  B. Call transfer_upload_status command internally.
     More round-trips, not necessary.

Choice: Option A -- direct import. The adapter is already a dependency
(code_analysis already imports from mcp_proxy_adapter). The storage_dir
for uploads is configured in the adapter config (config.json section
"transfer" -> "storage_dir"). ServerConfig should expose this or
read it from the same config.json.

---

## Implementation plan (separate step after this one)

1. Read transfer storage_dir from ServerConfig (add field if missing).
2. Create cst_apply_buffer_command.py:
   - class CSTApplyBufferCommand(BaseMCPCommand)
   - get_schema() with inputs above
   - execute(): validate transfer, read file, call run_ops_mode()
3. Register command in commands/__init__.py.
4. lint_code + smoke test:
   - upload a small .py snippet via transfer_upload_begin -> PUT -> complete
   - call cst_apply_buffer with transfer_id and selector
   - verify file_written=true, diff shows replacement

---

## Risk: session expiry

Transfer sessions have a TTL (session_ttl_seconds in config).
If the MCP call to cst_apply_buffer arrives after session expiry,
get_committed_upload_path() will raise TransferError.
Mitigation: document that cst_apply_buffer must be called promptly
after transfer_upload_complete. TTL is typically 3600s -- sufficient
for interactive use.
