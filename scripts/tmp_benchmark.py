"""Token cost estimate for CST vs string approach."""

# Rough token estimate: ~1 token per 4 chars (GPT standard)
def tokens(s): return len(s) // 4

print('=== TOKEN COST PER OPERATION ===')
print()

# ---- STRING approach ----
str_op = '''
{
  "action": "replace_lines",
  "start": 1,
  "end": 3,
  "content": "def add(a, b):\\n    return a + b"
}
'''
print(f'STRING op payload:       {tokens(str_op):>5} tokens  ({len(str_op)} chars)')

# ---- CST approach: cst_find_node ----
cst_find = '''
cst_find_node({"query": "FunctionDef[name='add']", "tree_id": "550e8400-..."}) ->
{"matches": [{"node_id": "abc123-...", "start_line": 1, "end_line": 3, ...}]}
'''
print(f'CST find_node round-trip: {tokens(cst_find):>5} tokens  (query + response)')

# ---- CST approach: cst_modify_tree ----
cst_modify = '''
cst_modify_tree({
  "tree_id": "550e8400-e29b-41d4-a716-446655440000",
  "operations": [{
    "action": "replace",
    "node_id": "abc123-def456-789...",
    "code_lines": [
      "def add(a, b):",
      "    # optimized",
      "    return a + b"
    ]
  }]
}) -> {"success": true, "file_written": true, "operations_applied": 1}
'''
print(f'CST modify_tree payload:  {tokens(cst_modify):>5} tokens  ({len(cst_modify)} chars)')

cst_total = tokens(cst_find) + tokens(cst_modify)
print(f'CST TOTAL (find+modify):  {cst_total:>5} tokens')
print(f'STRING TOTAL:             {tokens(str_op):>5} tokens')
print(f'CST overhead:             {cst_total/max(tokens(str_op),1):.1f}x more tokens')

print()
print('=== REAL CONVERSATION OVERHEAD (this session) ===')
print()

# What we actually spend tokens on in a CST session:
cst_session_overhead = """
Per single function replace:
  1. cst_load_file call + large response (all nodes)  -> stored to file, ~0 ctx tokens used
  2. bash_tool to extract node_id from response       -> ~50 tokens
  3. cst_get_node_info to read current code           -> ~150 tokens (read + response)
  4. cst_modify_tree with new code                    -> ~100 tokens (call + response)
  TOTAL: ~300 tokens for a single targeted replace

For string approach:
  1. get_file_lines (start/end)                       -> ~20 tokens
  2. replace_file_lines with new content              -> ~50 tokens
  TOTAL: ~70 tokens
"""
print(cst_session_overhead)

print('CST vs string token ratio: ~4x per operation')
print()
print('=== BUT: what does CST buy you? ===')
benefits = [
  ('Structural correctness',  'CST always produces valid Python (parse-validated)'),
  ('Indentation handling',    'CST never breaks indentation inside classes/functions'),
  ('Semantic targeting',      'Replace by name/type, not by line number (fragile)'),
  ('Refactoring safety',      'Rename, extract, restructure without regex failures'),
  ('Multi-op atomicity',      'replace_many applies N replacements atomically'),
  ('No line drift',           'After edits, line numbers shift; CST UUIDs do not'),
  ('Cross-file consistency',  'DB index stays in sync (ast_trees, cst_trees, entities)'),
]
for name, desc in benefits:
    print(f'  + {name:<28} {desc}')

print()
print('=== BREAK-EVEN ANALYSIS ===')
print()
print('String editing breaks silently when:')
breakeven = [
  'Regex mismatches due to whitespace/comment variation',
  'Line numbers shift after previous edits in same session',
  'Function spans multiple lines with complex decorators',
  'Editing inside a class (indentation level varies)',
  'Two edits conflict (overlapping ranges)',
  'File encoding or CRLF issues',
]
for b in breakeven:
    print(f'  - {b}')
print()
print('CST breaks when:')
cst_breaks = [
  'File has syntax errors (cannot parse)',
  'Very large files (>5000 lines): parse is slower',
  'RPC server is unavailable',
]
for b in cst_breaks:
    print(f'  - {b}')

print()
print('VERDICT:')
print('  Time:   CST is ~700x slower (libcst) to ~7000x (full RPC)')
print('  Tokens: CST costs ~4x more per operation')
print('  Value:  CST is worth it for structural edits (rename, refactor,')
print('          multi-op, class-level). Not worth it for simple line patches.')
print('  Sweet spot: CST for "edit logic", string for "edit text" (comments, strings).')
