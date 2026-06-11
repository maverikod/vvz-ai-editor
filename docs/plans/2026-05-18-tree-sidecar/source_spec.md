# Tree Sidecar for Structured Formats

## Problem

JSON and YAML files currently have no persistent node identity. When a file is
opened for editing, node UUIDs are generated in memory and lost on session close
or server restart. This makes stable references to nodes impossible across
sessions, prevents drill-down navigation in `universal_file_preview`, and creates
an inconsistent experience compared to Python files which have a persistent `.cst`
sidecar.

## Solution

Introduce a sidecar file for every tree-structured non-Python format (JSON, YAML).
The sidecar lives in `.trees/` next to the project root and stores the full node
tree with stable UUIDs, type information, values, and comments. The source data
file and the sidecar are kept in sync via SHA-256 of the source file.

Python files and their `.cst/` sidecars are not affected.

## Sidecar Location and Naming

Sidecars are stored in `.trees/` at the project root:

```
project/
  data.json              <- source data file
  config.yaml            <- source data file
  .trees/
    data.json.tree       <- sidecar for data.json
    config.yaml.tree     <- sidecar for config.yaml
  .cst/                  <- Python sidecars, unchanged
    module.py.tree
```

## Sidecar Format

The sidecar is a valid JSON file with the following top-level structure:

```json
{
  "source_sha256": "<hex SHA-256 of source file at last sync>",
  "root": [ <tree nodes> ]
}
```

`root` is always an array. For a JSON/YAML object at the top level, `root`
contains one node of type `object`. For a JSON array at the top level, `root`
contains the array element nodes directly.

## Node Structure

Every node carries:

- `stable_id` — UUID v4, assigned once, never changes for the lifetime of the node
- `type` — one of: `object`, `array`, `string`, `number`, `boolean`, `null`
- `key` — present on nodes that are object members; the string key name
- `value` — present on scalar nodes (`string`, `number`, `boolean`, `null`)
- `children` — present on `object` and `array` nodes; ordered list of child nodes
- `comment_before` — comment text on the line(s) above this node
- `comment_inline` — comment text to the right of this node on the same line

Comments are stored as plain strings. For JSON files, `//` line comments and
`/* */` block comments are supported. For YAML files, `#` line comments are
supported. Comments are preserved through round-trip edit -> write cycles.

Example — source JSON with comments:

```
{
  "a": 1  // inline comment
}
// above comment
```

Corresponding sidecar:

```json
{
  "source_sha256": "abc123...",
  "root": [
    {
      "stable_id": "11111111-...",
      "type": "object",
      "comment_before": "// above comment",
      "children": [
        {
          "stable_id": "22222222-...",
          "key": "a",
          "type": "number",
          "value": 1,
          "comment_inline": "// inline comment"
        }
      ]
    }
  ]
}
```

## Comment Ownership Rules

1. A comment on the same line as a value (inline) -> belongs to that value's node
   as `comment_inline`.
2. A comment on its own line above a value -> stored as `comment_before` on the
   child node immediately following the comment.
3. A top-level comment above the first root node -> stored as `comment_before` on
   the first root node.

The same rules apply identically to JSON and YAML.

## SHA Synchronisation and Priority

Every sidecar records `source_sha256`: the SHA-256 of the source file at the time
the sidecar was last written. On `universal_file_open`:

1. No sidecar exists -> build tree from source, assign new UUIDs, write sidecar.
2. Sidecar exists, SHA matches -> load sidecar as-is.
3. Sidecar exists, SHA mismatch, no active session -> source has priority;
   rebuild tree from source, assign new UUIDs, overwrite sidecar.
4. Sidecar exists, SHA mismatch, active session holds the file -> sidecar has
   priority (mismatch is the result of a write through the session); do not rebuild.

## Edit Session Integration

The universal file edit workflow (open -> edit -> write -> close) is extended:

- `universal_file_open`: invoke SHASyncPolicy to obtain the TreeNode tree,
  register an EditSession, return session_id and format_group.
- `universal_file_edit`: mutate the in-memory tree. Surviving node UUIDs are
  preserved. New nodes get new UUIDs.
- `universal_file_write`: serialise the tree to the source format, write the
  source file, update the sidecar with the new source_sha256.
- `universal_file_close` without prior write: discard in-memory changes;
  on-disk sidecar is unchanged.

## Parsers and Serializers

For each supported format, two components work together:

- A **SourceParser** reads the source file bytes and produces a TreeNode tree,
  applying CommentOwnershipRule during parsing.
- A **SourceSerializer** consumes a TreeNode tree and produces source file bytes,
  restoring comments at the positions recorded in the tree.

Neither component touches the Sidecar or the EditSession directly.

## Preview Navigation

For **tree-temp** sources (JSON and YAML), the same navigation rules apply to both
formats.

`universal_file_preview` accepts an optional `node_ref` equal to a TreeNode
`stable_id` from the Sidecar-backed tree. Because Sidecar UUIDs are persistent
across sessions and server restarts, `node_ref` values obtained in one session
remain valid in subsequent sessions on the same file.

When no `node_ref` is provided, the command returns the root-level blocks
(**root_view**).

**Container focus.** When `node_ref` identifies a **container** node (`type` is
`object` or `array`), behaviour is unchanged: the command returns that node's
**ordered children** as the block list—the same semantics as
`container_drill_down` in PreviewNavigation (C-009).

**Scalar focus (tree-temp / sidecar).** When `node_ref` identifies a **scalar**
node (`type` is `string`, `number`, `boolean`, or `null`):

1. Resolve the node in the Sidecar-backed tree.
2. Walk **up the parent chain** to the **nearest ancestor** whose `type` is
   **`object` or `array`**.
3. Use **that container** as the **effective focus** for preview: return its
   **ordered children** as the block list (same block-list contract as
   `container_drill_down`).
4. If **no** `object` or `array` ancestor exists—for example, the document root
   is a scalar—treat **`node_ref` as absent** and return **root_view** (same as
   omitting the parameter).

**Errors.** An unknown or unresolvable `stable_id` remains an input or resolution
error; the scalar-focus rule does not apply to failed resolution.

**Relation to generic preview.** The frozen plan `2026-05-12-universal-file-preview`
defines a generic preview **NavigationProcedure** in which focus on a **scalar**
node yields an **empty** block set. This tree-temp Sidecar integration
**specialises** that procedure for persistent drill-down: a scalar `node_ref` is
remapped to the nearest enclosing container, or to **root_view** when no such
ancestor exists. This plan does **not** claim to change the frozen
`2026-05-12-universal-file-preview` specification.

## Formats in Scope

- JSON (`.json`) — with `//` and `/* */` comment support via a tolerant parser
- YAML (`.yaml`, `.yml`) — with `#` comment support via ruamel.yaml round-trip

Python (`.py`) and its `.cst/` sidecar are out of scope and remain unchanged.

<!-- non-binding -->
Future candidates: Markdown, HTML. Not in this plan.
<!-- /non-binding -->
