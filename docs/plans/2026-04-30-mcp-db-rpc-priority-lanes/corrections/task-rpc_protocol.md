# Task: rpc_protocol.py — audit and fix

**File:** `code_analysis/core/database_client/protocol/rpc_protocol.py`
**Lines:** 133 (within limit)
**Plan steps:** 1 (priority field)

---

## Issues found

### 1. Step 1 is DONE correctly ✅

- `priority: int = 0` added to `RPCRequest` dataclass (line 65), after `params`,
  before `request_id` — matches plan field order requirement.
- `to_dict()`: serializes only when non-zero (`if self.priority != 0`) — matches plan.
- `from_dict()`: reads `priority = int(data.get("priority", 0))` — matches plan.
- Default `0` preserves backward compatibility for in-process and socket transports.

### 2. Tests exist and pass ✅

`tests/test_rpc_protocol.py` has 6 priority-specific tests:
- `test_request_priority_round_trip_nonzero`
- `test_request_from_dict_priority_key_absent`
- `test_request_to_dict_omits_priority_when_zero`
- `test_request_round_trip_priority_explicit_zero`
- `test_request_from_dict_priority_non_numeric_raises`
- `test_request_to_dict_negative_priority_serialized`

### 3. No issues — step 1 is complete

No code changes needed. Mark step 1 as DONE in plan status.

---

## Validation

No changes required. File passes all checks.
