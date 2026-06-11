# Client Sessions Subsystem — Source Specification

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## 1. Purpose

The code_analysis server is used by AI models and external editors. Each
working session (model invocation, editor window, script run) needs a stable,
cross-project, DB-persisted identity so that:

- file locks are attributed to a session, not to an OS process;
- stale sessions can be identified and cleaned up by time of last activity;
- in the future, dialogues, tasks, and other stateful objects can be attached
  to the same identity.

A client session is a UUID4 identifier that is THE SAME entity as the
universal_file_open edit session. Currently edit sessions live only in memory
and are keyed by an in-process UUID. This subsystem extends them by persisting
the same UUID in a database row with a comment and a last_active_at timestamp.

## 2. Session identity and lifecycle

The client calls session_create with a human-readable comment.
The server generates a UUID4, inserts a row, and returns the session_id.
The client passes this session_id to all subsequent commands.

Every command that accepts session_id updates last_active_at to now before
executing its main logic. If session_id is not found, the command returns
SESSION_NOT_FOUND without executing. There is no anonymous mode: all
operations require a valid session_id, with one strictly defined exception
described in section 9.

The client calls session_delete to end the session.
- If the session has open file locks and force is false: error SESSION_HAS_LOCKS.
- If force is true: all file locks for that session are released, then the
  session record is deleted.

Sessions whose last_active_at is older than a configurable threshold are
considered stale and can be listed or deleted by an operator.

## 3. Session storage

Table client_sessions (global, not project-scoped):
  session_id      — UUID4, primary key, server-generated, immutable
  comment         — human-readable label from client, not null, default empty
  created_at      — timestamp of insert
  last_active_at  — updated on every session-touching command

## 4. File lock storage

A file lock records that a specific file is open in a specific session.

Table session_file_locks:
  session_id  — references client_sessions; cascade delete on session removal
  project_id  — references the registered project
  file_id     — references the file record in the files table
  locked_at   — timestamp of lock acquisition
  Primary key: (session_id, project_id, file_id)

Lock semantics:
- Acquiring a lock is idempotent: if the record already exists, no error.
- Releasing a lock is idempotent: if the record does not exist, no error.
- Only one lock record per (session, project, file) triple.

## 5. Replacement of the PID-based lock mechanism

The existing advisory lock system uses the OS process PID as the session
identifier (runtime_lock_sessions table, keyed by pid). This is replaced by
the client session UUID4:

- runtime_lock_sessions identifies a server process, not a client session.
  Client sessions are independent of the server process that handles them.
- The new session_file_locks table uses session_id (UUID4) as the owner,
  not pid.
- Unlocking a file no longer requires knowing the PID. The caller supplies
  session_id and the server releases the lock for that session.
- A caller with a valid session_id can release any lock owned by that session,
  regardless of which server process originally acquired it.
- Force-delete of a session (force=true) releases all file locks for that
  session regardless of which process holds them.

## 6. Session service

A pure service layer (no MCP coupling) handles all DB operations for sessions
and file locks. It provides:

- Session existence check without side effects
- Session creation returning the new session record
- Session touch: update last_active_at, raise if not found
- Session deletion with optional force (releasing locks first)
- Session listing with optional stale-threshold filter and show_session_ids flag
- File lock acquisition (idempotent)
- File lock release (idempotent)
- File lock listing for one session
- File lock count for one session
- Global locked-files listing across all sessions, without exposing session_id

## 7. MCP commands

session_create: accepts comment; returns session_id and timestamps.
No session_id required (session does not exist yet).

session_delete: accepts session_id and force flag. Touch NOT applied
(session is being deleted). Returns count of locks released when force=true.
Error SESSION_HAS_LOCKS if locks exist and force=false.
Error SESSION_NOT_FOUND if session missing.

session_list: accepts optional stale_threshold_seconds and optional session_id.
This is the only command where session_id is optional.
Behavior depends on config flag show_session_ids (see section 10):
- show_session_ids=false: session_id may be omitted; session_id is never
  included in output regardless of whether session_id was supplied.
- show_session_ids=true: session_id is required (SESSION_ID_REQUIRED if
  missing); touch is applied; session_id is included in each output row.

session_open_file: accepts session_id, project_id, file_id.
Touches session first. Acquires file lock. Returns acquisition status.

session_close_file: accepts session_id, project_id, file_id.
Touches session first. Releases file lock. Returns release status.

session_list_file_locks: accepts session_id.
Touches session first. Returns locks for that session.

## 8. CLI extensions

Two new subcommands are added to the existing server management CLI (casmgr):

casmgr sessions [--config PATH]: lists all client sessions.
Columns: session_id, comment, created_at, last_active_at, open_lock_count.
Session identifiers are always shown in CLI output (operator tool, not API).
Reads the DB directly via config path, no running server required.

casmgr locks [--config PATH]: lists all locked files across all sessions.
Columns: project_id, file_id, locked_at. Does NOT output session_id.
Reads the DB directly via config path, no running server required.

## 9. Anonymous exception: session_list without session_id

The only permitted anonymous call (no session_id) is:
  session_list with show_session_ids=false in config.

Rationale: an operator or monitoring tool needs to discover existing sessions
before obtaining a session_id of its own. This call is read-only and
non-mutating. When show_session_ids=true, the caller must authenticate with a
valid session_id so that touch is applied and the output is access-controlled.

All other commands: session_id is always required. No exceptions.

## 10. Configuration: show_session_ids

The server configuration contains a boolean flag under the sessions section:

  sessions:
    show_session_ids: false

Behavior:
- false (default):
    session_list without session_id: permitted; session_id omitted from output.
    session_list with session_id: permitted; touch applied; session_id still
    omitted from output.
- true:
    session_list without session_id: rejected with SESSION_ID_REQUIRED.
    session_list with session_id: permitted; touch applied; session_id
    included in each row of the output.

Config validator: must verify show_session_ids is a boolean; reject if missing
or wrong type.
Config generator: must emit show_session_ids: false as the default value.

<!-- non-binding -->
Future extensions: attach dialogues, tasks, heartbeat, TTL auto-expiry.
<!-- /non-binding -->

## 11. Roles and permissions

A role is a named entity with a unique identifier. Table roles:
  role_id  — UUID4, primary key, server-generated
  name     — TEXT, unique, not null

A role permission grants a role access to a specific command on a specific
registered proxy server. Table role_permissions:
  role_id      — references roles, cascade delete
  command_name — TEXT, MCP command name
  server_uuid  — UUID4, proxy server identifier from the proxy registry
  Primary key: (role_id, command_name, server_uuid)

Roles are assigned to a session at creation time via role_ids list in
session_create. A session accumulates all permissions of all its assigned
roles. A session with no roles has no permissions under allowlist policy.
## 12. Resource policy for authorized principals

Authentication and transport-level authorization are outside this subsystem.
They are handled by mcp_proxy_adapter via API keys, bearer tokens, mTLS,
certificates, roles, and proxy-side permission middleware.

ClientSession is not an authentication token and must not be treated as one.
It is a resource ownership context for an already authenticated user, service,
editor, script, or AI agent.

The server configuration may contain a resource policy mode under the security
section:

  security:
    policy: disabled

Three modes:
- disabled: no additional session-level resource-action restrictions are
  applied after proxy authentication; all valid sessions may execute all
  resource actions.
- allowlist: only explicitly permitted resource-action triples are allowed.
  A session with no assigned roles cannot execute restricted resource actions.
- denylist: all resource actions are permitted except those explicitly denied.
  A session with no assigned roles can execute all non-denied resource actions.

The policy applies after the incoming request has already been authenticated by
mcp_proxy_adapter. It restricts what the already authenticated principal may do
through this ClientSession: open or close files, acquire workspace write access,
run terminals, claim or release plans, force-clean resources, and perform other
resource-affecting actions.

The config validator must verify that policy is one of the three allowed
values. The config generator must emit policy: disabled as the default.

## 13. CLI as operator interface

The casmgr CLI subcommands (sessions, locks) are an operator interface that
reads the database directly without going through MCP or session validation.
They are not subject to ResourcePolicy or SessionTouchRule. They always
display session_id regardless of show_session_ids config.
They are not subject to ResourcePolicy or SessionTouchRule. They always
display session_id regardless of show_session_ids config.
reads the database directly without going through MCP or session validation.
They are not subject to SecurityPolicy or SessionTouchRule. They always
display session_id regardless of show_session_ids config.
