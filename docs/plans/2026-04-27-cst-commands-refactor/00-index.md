# CST commands refactor plan

## Purpose
Step-by-step plan for fixing and extending CST-command infrastructure.
Based on problems documented in `docs/csterr.md` and architectural analysis
of `libcst 1.8.6` performed on 2026-04-27.

Each step is written for Haiku: exact files, exact line numbers, exact questions,
no open architectural decisions. Every step is isolated and independently executable.

## Source of problems

```text
docs/csterr.md -- 9 documented problems from live editing session
```

## Coverage map: csterr.md problems -> plan steps

```text
Problem 1: insert fails in IndentedBlock           -> steps 01, 02
Problem 2: replace fails in IndentedBlock          -> steps 03, 04  (mutable layer investigation)
Problem 3: preview damages class structure         -> step 05
Problem 4: query_cst replaced=1 with empty diff   -> steps 06, 07
Problem 5: preview/apply semantics unreliable      -> steps 09, 10
Problem 6: compose blocked by pre-existing errors  -> steps 11, 12
Problem 7: large payload blocked by safety filter  -> step 13
Problem 8: no cst_replace_range                   -> out of scope (wrong abstraction level)
Problem 9: result fields inconsistent             -> steps 09, 10
```

## Confirmed root causes (from Opus analysis 2026-04-27)

```text
Problem 1+2: insert_node_at_position whitelist = {Module, FunctionDef, ClassDef} only.
  File: code_analysis/core/cst_tree/tree_modifier_ops_insert.py lines 53-62
  File: code_analysis/core/cst_tree/tree_modifier_ops_find.py lines 222-224
  Fix direction: structural check hasattr(node, body)+isinstance(node.body, IndentedBlock)
  Edge cases: SimpleStatementSuite, Match (no body field), on_leave without super().

Problem 2: replace in IndentedBlock -- NodeReplacer looks correct in isolation.
  Suspected cause: mutable layer (edits.py) or stale metadata in batch path.
  File: code_analysis/core/mutable_cst/edits.py
  Needs investigation before fix.

Problem 3: compose_cst_module preview damages class structure.
  Likely cause: whole-method CST replacement corrupts surrounding module/class nodes.
  Needs investigation in compose_cst_module preview path.

Problem 4: query_cst returns replaced=1 with empty diff.
  File: TBD -- needs investigation in step 06.

Problem 5+9: CST edit commands missing file_written/preview_only/backup_uuid fields.
  Files: all cst_*_command.py result construction.

Problem 6: compose_cst_module blocks local patch due to whole-file mypy/docstring check.
  File: TBD -- needs investigation in step 11.

Problem 7: large CST payloads blocked by external safety filter.
  Fix: buffer-based upload workflow.
```

## Key libcst constraints (must not violate)

```text
- body field type is BaseSuite, not IndentedBlock directly.
  BaseSuite has two subclasses:
    IndentedBlock(body: Sequence[BaseStatement])  -- multi-line blocks
    SimpleStatementSuite(body: Sequence[BaseSmallStatement])  -- one-liners
  Inserting BaseStatement into SimpleStatementSuite is a type error.

- Match node has no body field. It has cases: Sequence[MatchCase].
  MatchCase.body is BaseSuite -- insert INTO MatchCase works via structural check.

- with_changes() returns a NEW frozen object (dataclasses.replace).
  Use updated_node.body.with_changes(body=new_body),
  NOT cst.IndentedBlock(body=new_body) -- the latter loses indent/header/footer.

- on_leave without super().on_leave() disables leave_* dispatch.
  Either use only leave_* methods, or call super() first.

- PositionProvider metadata exists only on original_node, not updated_node.
  Always use original_node for position lookups inside leave_* methods.

- Try has 4 body points: body, handlers[i].body, orelse.body, finalbody.body.
  Each is a separate node (ExceptHandler, Else, Finally) with its own IndentedBlock.
  leave_IndentedBlock covers all 4 automatically.
```

## Step order

```text
--- INSERT FIX ---
01-insert-whitelist-inventory.md        -- read 3 files, answer 5 questions, no writes
02-insert-whitelist-fix.md              -- patch insert_node_at_position and find.py

--- REPLACE INVESTIGATION ---
03-replace-indentedblock-investigation.md -- find why replace fails in IndentedBlock
04-replace-indentedblock-fix.md           -- fix replace in mutable/batch path if needed

--- PREVIEW SAFETY ---
05-preview-damage-investigation.md      -- find why compose preview damages class structure

--- QUERY_CST DIFF ---
06-query-cst-diff-investigation.md     -- find where diff is produced, why empty
07-query-cst-diff-fix.md               -- fix empty diff bug

--- ON_LEAVE HIDDEN BUG ---
08-on-leave-dispatch-check.md          -- verify RelativeNodeInserter on_leave dispatch

--- RESULT FIELDS ---
09-result-fields-inventory.md          -- inventory all CST edit commands result fields
10-result-fields-fix.md                -- add file_written/preview_only/backup_uuid

--- COMPOSE VALIDATION ---
11-compose-validation-investigation.md  -- find whole-file validation gate
12-compose-validation-fix.md           -- add validate_syntax_only mode

--- LARGE PAYLOAD ---
13-buffer-upload-design.md             -- design buffer-based replacement workflow

--- EDGE CASE GUARDS ---
14-edge-case-guards.md                 -- SimpleStatementSuite and Match guards

--- TESTS ---
15-insert-tests.md                     -- test insert in all compound statement bodies
16-replace-tests.md                    -- test replace in IndentedBlock contexts
17-regression-tests.md                 -- verify all existing CST operations still work
```

## Global rules

```text
- Do not touch insert_node_relative -- already works correctly.
- Do not touch NodeReplacer in tree_modifier_ops_replace.py -- already works correctly.
- Do not use on_leave without super().on_leave().
- Use updated_node.body.with_changes(body=new_body) not cst.IndentedBlock(body=new_body).
- Every step: read -> propose -> confirm -> write.
- No step writes more than one file without explicit approval.
- Investigation steps (01, 03, 05, 06, 08, 09, 11): read only, no writes.
```

## Definition of done

```text
- insert_node_at_position works for If/For/While/Try/With/ExceptHandler/Else/Finally/MatchCase.
- insert_node_at_position gives clear error for SimpleStatementSuite and Match directly.
- replace works correctly in IndentedBlock via mutable and CST paths.
- compose_cst_module preview does not damage surrounding class/module structure.
- query_cst diff is non-empty when modified_source differs from file.
- compose_cst_module supports validate_syntax_only=true.
- All CST edit commands return file_written and preview_only consistently.
- RelativeNodeInserter on_leave dispatch is verified correct or fixed.
- Buffer-based replacement workflow designed for large payloads.
- All existing CST tests pass.
```
