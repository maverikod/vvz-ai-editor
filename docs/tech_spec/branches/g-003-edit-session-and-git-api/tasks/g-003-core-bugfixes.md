# G-003 Remediation: Core EditSession and SessionRepo Bugfixes

## Purpose

Close blocking correctness gaps in the on-disk C-012/C-013 implementation so per-mutation commits, re-validation, and revert match the G-003 plan (`{d003}`, `{h009}`, `{e005}`).

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- Machine spec: `docs/plans/marked_tree_unification/spec.yaml` (C-012, C-013, C-025)
- Tactical steps: T-001, T-002 under same G-003 directory

## Scope

**Included:**
- Fix `_try_revalidate()` in core `EditSession` to rebuild tree inside the session directory using MAP from the session tree file (`prior_map` from session path), never writing the external co-located tree during session edit.
- After `_post_mutation_full()`, update CHECKSUMS section in the in-session tree file with fresh SHA-256 for tree content and exported source per `{d003}`.
- After successful re-validation (state returns VALID), record checksums and create a SessionRepo commit capturing restored artefacts.
- Fix `SessionRepo.revert()`: after restoring tree blob at target revision, re-export in-session source via unmark before `commit_full()` so tree and source stay paired.

**Excluded:**
- MCP command registration (separate task `g-003-mcp-command-registration.md`)
- Universal-file integration wiring (separate task `g-003-universal-file-integration.md`)
- New tests (separate task `g-003-test-coverage.md`)

## Boundaries

- Do not modify HRS/MRS/plan YAML.
- Do not change legacy `commands/universal_file_edit/session.py` in this task.
- Do not register MCP commands here.

## Dependencies

- none (runs first among remediation tasks touching `edit_session.py`)

## Parallelization note

Can run in parallel with `g-003-mcp-command-registration.md`. Must complete before `g-003-universal-file-integration.md` if integration relies on corrected revalidation/checksum behavior.

## Expected outcome

- `EditSession.apply_plaintext_mutation()` path that triggers re-validation updates session-local tree only, preserves MAP UUID4 and `next_free`, updates CHECKSUMS, and commits via SessionRepo.
- Valid-mode mutations leave CHECKSUMS consistent with on-disk tree and exported source.
- `SessionRepo.revert(rev)` produces a new FULL commit with matching tree and unmark-exported source.

## Correction items

Researcher audit (2026-05-31) identified:
1. `_try_revalidate()` uses `TreeBuilder.build()` targeting external sidecar — wrong.
2. Post-mutation CHECKSUMS preserved stale `source_sha256`.
3. `SessionRepo.revert()` calls `commit_full()` without re-unmarking source.

## Questions/escalation rule

Escalate to global orchestrator if fixing re-validation requires changing `{h009}` semantics or TreeBuilder public contract across global steps.

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/core/edit_session/edit_session.py` | Fix `_try_revalidate`, CHECKSUMS update in `_post_mutation_full` |
| modify | `code_analysis/core/edit_session/session_repo.py` | Fix `revert()` source re-sync |

## Class/function inventory

### `code_analysis.core.edit_session.edit_session.EditSession`

- `_post_mutation_full(self) -> None` — after tree write and source export, recompute and write CHECKSUMS into session tree file, then `SessionRepo.commit_full()`.
- `_try_revalidate(self) -> None` — parse MAP from `self.session_tree_path`; build tree in session dir only; use `NodeIdMap.build(..., prior_map=session_map)`; on success set `tree_validity=VALID`, update checksums, commit FULL.

### `code_analysis.core.edit_session.session_repo.SessionRepo`

- `revert(self, rev: str) -> str` — restore tree at `rev`, unmark-export source to session source path, then `commit_full()` with message indicating revert.

## Error handling map

| condition | exception | caller action |
|-----------|-----------|---------------|
| Re-validation still unparseable | no state change; remain INVALID | continue degraded edits |
| Dulwich revert target missing | propagate `KeyError`/`ValueError` from dulwich | MCP command maps to `REVISION_NOT_FOUND` |

## Test plan

Verified by `tester_auto` after `g-003-test-coverage` tests land:
- `tests/unit/test_edit_session_revalidation.py` — MAP UUID4 preserved
- `tests/unit/test_session_repo.py` — revert pairs tree+source

## Concrete examples

1. **CHECKSUMS after valid mutation:** source changes → `_post_mutation_full` writes new `source_sha256` and `tree_sha256` into CHECKSUMS section of session `.tree` file.
2. **Revert:** session at commit C2, `revert("C1")` → new commit C3 where tree matches C1 tree and source equals unmark(tree at C1).

## Algorithm: `_try_revalidate`

1. Read plaintext from `session_source_path`.
2. Attempt handler parse; on failure return without change.
3. Load `prior_map` from MAP section of `session_tree_path` (not external tree).
4. Build marked tree in memory; write only to `session_tree_path`.
5. Export source via unmark to `session_source_path`.
6. Update CHECKSUMS in session tree file.
7. Set `tree_validity = VALID`; `SessionRepo.commit_full()`.

## Forbidden approaches

- Do not call `TreeBuilder.build()` with external `source_abs` as write target during session revalidation.
- Do not skip CHECKSUMS update to "preserve" old checksums after content changed.
- Do not use destructive git reset in revert.
