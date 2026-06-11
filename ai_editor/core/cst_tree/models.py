"""
Data models for CST tree management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import libcst as cst


class TreeOperationType(str, Enum):
    """Type of tree operation.

    Attributes:
        REPLACE: Replace a node with new code.
        REPLACE_RANGE: Replace a range of sibling nodes with new code.
        INSERT: Insert new code relative to a node.
        DELETE: Delete a node.
        MOVE: Move a node to a new location.
    """

    REPLACE = "replace"
    REPLACE_RANGE = "replace_range"
    INSERT = "insert"
    DELETE = "delete"
    MOVE = "move"


@dataclass
class DocstringMeta:
    """Structured docstring stored in node metadata and migrated with the node.

    Analogous to stable_id: survives tree rebuilds via _build_tree_index and
    is applied to the LibCST node automatically during cst_save_tree, so
    new_code in cst_modify_tree never needs a hand-written docstring.

    For methods/functions: set summary, args, returns.
    For classes: set summary, attributes.
    For legacy unstructured docstrings: set docstring_body only.

    Attributes:
        summary: One-line description (first line of docstring).
        args: Mapping of parameter name to its description.
        returns: Return value description.
        attributes: Mapping of attribute name to its description.
        docstring_body: Raw body text for legacy unstructured docstrings.
    """

    summary: str = ""
    args: Dict[str, str] = field(default_factory=dict)
    returns: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    docstring_body: str = ""

    def is_empty(self) -> bool:
        """Return True when no docstring content is set.

        Returns:
            True when all fields are empty or default.
        """
        return not any(
            [
                self.summary,
                self.args,
                self.returns,
                self.attributes,
                self.docstring_body,
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for sidecar storage.

        Returns:
            Dict containing only non-empty fields.
        """
        result: Dict[str, Any] = {}
        if self.summary:
            result["summary"] = self.summary
        if self.args:
            result["args"] = dict(self.args)
        if self.returns:
            result["returns"] = self.returns
        if self.attributes:
            result["attributes"] = dict(self.attributes)
        if self.docstring_body:
            result["docstring_body"] = self.docstring_body
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocstringMeta":
        """Deserialize from sidecar dict.

        Args:
            data: Dict produced by :meth:`to_dict`.

        Returns:
            DocstringMeta instance with fields populated from data.
        """
        return cls(
            summary=str(data.get("summary", "")),
            args=dict(data.get("args") or {}),
            returns=str(data.get("returns", "")),
            attributes=dict(data.get("attributes") or {}),
            docstring_body=str(data.get("docstring_body", "")),
        )

    @classmethod
    def from_raw(cls, raw: str) -> "DocstringMeta":
        """Parse a raw docstring string into structured form where possible.

        Recognises Google-style sections (Args:, Returns:, Attributes:).
        Falls back to docstring_body when no sections are found.

        Args:
            raw: Raw docstring text without triple quotes.

        Returns:
            DocstringMeta with parsed fields, or docstring_body as fallback.
        """
        lines = raw.strip().splitlines()
        if not lines:
            return cls()
        summary = lines[0].strip()
        args: Dict[str, str] = {}
        returns = ""
        attributes: Dict[str, str] = {}
        current_section: Optional[str] = None
        current_param: Optional[str] = None
        for line in lines[1:]:
            stripped = line.strip()
            if stripped in ("Args:", "Arguments:"):
                current_section = "args"
                current_param = None
            elif stripped == "Returns:":
                current_section = "returns"
                current_param = None
            elif stripped == "Attributes:":
                current_section = "attributes"
                current_param = None
            elif current_section == "args" and ":" in stripped:
                name, _, desc = stripped.partition(":")
                current_param = name.strip()
                args[current_param] = desc.strip()
            elif current_section == "args" and current_param and stripped:
                args[current_param] += " " + stripped
            elif current_section == "returns" and stripped:
                returns = (returns + " " + stripped).strip()
            elif current_section == "attributes" and ":" in stripped:
                name, _, desc = stripped.partition(":")
                current_param = name.strip()
                attributes[current_param] = desc.strip()
            elif current_section == "attributes" and current_param and stripped:
                attributes[current_param] += " " + stripped
        if args or returns or attributes:
            return cls(
                summary=summary, args=args, returns=returns, attributes=attributes
            )
        return cls(summary=summary, docstring_body=raw.strip())


@dataclass(frozen=True)
class TreeNodeMetadata:
    """Metadata for a CST node.

    Lightweight representation sent to clients without the full CST tree.
    stable_id is assigned once at node creation and never changes across rebuilds.
    node_id may be reassigned after index rebuild; stable_id always points back
    to the original UUID so callers can use it as a durable handle.
    docstring migrates with the node the same way stable_id does.

    Attributes:
        node_id: Internal node identifier; may change after index rebuild.
        stable_id: UUID assigned at creation; never changes on rebuild.
        type: LibCST node type (e.g., FunctionDef, ClassDef).
        kind: Node kind (e.g., function, class, method, stmt, smallstmt).
        name: Simple name of the node if applicable.
        qualname: Qualified name including class context.
        start_line: 1-based start line in source file.
        start_col: 0-based start column.
        end_line: 1-based end line.
        end_col: 0-based end column.
        children_count: Number of direct children.
        children_ids: Ordered list of child node_ids.
        parent_id: Parent node_id, or None for root.
        code: Optional source code snippet for this node.
        docstring: Structured docstring metadata; migrates with stable_id.
    """

    node_id: str
    stable_id: str
    type: str
    kind: str
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: int = 1
    start_col: int = 0
    end_line: int = 1
    end_col: int = 0
    children_count: int = 0
    children_ids: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    code: Optional[str] = None
    docstring: Optional["DocstringMeta"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dict with node fields including node_id and stable_id.
        """
        result: Dict[str, Any] = {
            "node_id": self.node_id,
            "stable_id": self.stable_id,
            "type": self.type,
            "kind": self.kind,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "children_count": self.children_count,
        }
        if self.name is not None:
            result["name"] = self.name
        if self.qualname is not None:
            result["qualname"] = self.qualname
        if self.children_ids:
            result["children_ids"] = self.children_ids
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.code is not None:
            result["code"] = self.code
        if self.docstring is not None and not self.docstring.is_empty():
            result["docstring"] = self.docstring.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TreeNodeMetadata":
        """Build metadata from :meth:`to_dict` / sidecar JSON.

        Args:
            data: Dictionary produced by :meth:`to_dict` or read from sidecar.

        Returns:
            TreeNodeMetadata instance reconstructed from the dictionary.
        """
        children_ids = data.get("children_ids")
        if children_ids is not None and not isinstance(children_ids, list):
            children_ids = []
        docstring_data = data.get("docstring")
        docstring = DocstringMeta.from_dict(docstring_data) if docstring_data else None
        return cls(
            node_id=str(data.get("node_id") or data.get("stable_id", "")),
            stable_id=str(data.get("stable_id") or data.get("node_id", "")),
            type=str(data["type"]),
            kind=str(data["kind"]),
            name=data.get("name"),
            qualname=data.get("qualname"),
            start_line=int(data.get("start_line", 1)),
            start_col=int(data.get("start_col", 0)),
            end_line=int(data.get("end_line", 1)),
            end_col=int(data.get("end_col", 0)),
            children_count=int(data.get("children_count", 0)),
            children_ids=[str(x) for x in (children_ids or [])],
            parent_id=(
                str(data["parent_id"]) if data.get("parent_id") is not None else None
            ),
            code=data.get("code"),
            docstring=docstring,
        )


@dataclass
class TreeOperation:
    """Operation to modify a CST tree."""

    action: TreeOperationType
    node_id: str = (
        ""  # Node ID for replace/delete operations (empty for insert with target_node_id)
    )
    code: Optional[str] = None
    code_lines: Optional[List[str]] = None
    position: Optional[str] = None
    position_after_index: Optional[int] = None
    parent_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None
    replace_all_child_nodes: bool = False


# Reserved node_id: denotes the Module (root) node of the tree.
ROOT_NODE_ID_SENTINEL = "__root__"


@dataclass
class CSTTree:
    """CST tree with metadata.

    The full CST tree is stored in memory on the server.
    Clients receive only metadata about nodes.

    Attributes:
        tree_id: Unique identifier for this tree session.
        file_path: Absolute path to the source file.
        module: Parsed LibCST module object.
        node_map: Mapping from node_id to LibCST node object.
        metadata_map: Mapping from node_id to TreeNodeMetadata.
        parent_map: Mapping from node_id to parent node_id.
        node_id_aliases: Mapping old_node_id to current_node_id after mutations.
        root_node_id: Node ID of the module root node.
        loaded_at: Monotonic timestamp when the tree was loaded.
        last_accessed_at: Monotonic timestamp of last access for TTL tracking.
        disk_source_sha256_hex: SHA-256 hex of UTF-8 file bytes at last disk sync.
        disk_source_length: Byte length of file at last disk sync.
        module_source_sha256_hex: SHA-256 hex of module.code at last sync.
    """

    tree_id: str
    file_path: str
    module: cst.Module
    node_map: Dict[str, cst.CSTNode] = field(default_factory=dict)
    metadata_map: Dict[str, TreeNodeMetadata] = field(default_factory=dict)
    parent_map: Dict[str, Optional[str]] = field(default_factory=dict)
    node_id_aliases: Dict[str, str] = field(default_factory=dict)
    # node_id_aliases: old_node_id -> current_node_id (transitive closure).
    # Populated after each _build_tree_index call so that stale UUIDs from
    # previous cst_modify_tree calls are automatically resolved to current ones.
    # Cleared on reload_tree_from_file (full UUID reset from disk).
    root_node_id: Optional[str] = None
    loaded_at: float = field(default_factory=time.monotonic)
    last_accessed_at: float = field(default_factory=time.monotonic)
    disk_source_sha256_hex: Optional[str] = None
    disk_source_length: int = 0
    module_source_sha256_hex: Optional[str] = None

    @classmethod
    def create(cls, file_path: str, module: cst.Module) -> "CSTTree":
        """Create a new CSTTree with generated tree_id.

        Args:
            file_path: Absolute path to the source file.
            module: Parsed LibCST module object.

        Returns:
            New CSTTree instance with a freshly generated tree_id.
        """
        tree_id = str(uuid.uuid4())
        return cls(
            tree_id=tree_id,
            file_path=file_path,
            module=module,
        )

    def find_by_stable_id(self, stable_id: str) -> Optional[TreeNodeMetadata]:
        """Find node metadata by stable_id.

        stable_id is assigned once at node creation and never changes,
        even after tree rebuilds caused by insert/delete operations.

        When duplicate rows share a stable_id (e.g. legacy blank-line markers),
        prefer editable statement/class/function nodes over whitespace leaves.

        Args:
            stable_id: The stable user-facing node identifier.

        Returns:
            TreeNodeMetadata if found, None otherwise.
        """
        preferred_types = (
            "FunctionDef",
            "AsyncFunctionDef",
            "ClassDef",
            "SimpleStatementLine",
            "Decorator",
        )
        candidates = [
            meta for meta in self.metadata_map.values() if meta.stable_id == stable_id
        ]
        if not candidates:
            return None
        for node_type in preferred_types:
            for meta in candidates:
                if meta.type == node_type:
                    return meta
        return candidates[0]

    def set_docstring(self, stable_id: str, docstring: "DocstringMeta") -> bool:
        """Set docstring metadata for a node by stable_id without reloading the tree.

        The docstring is stored in metadata_map and applied to the LibCST node
        automatically during cst_save_tree.

        Args:
            stable_id: The stable node identifier.
            docstring: Structured docstring to assign to the node.

        Returns:
            True if the node was found and updated, False otherwise.
        """
        for node_id, meta in self.metadata_map.items():
            if meta.stable_id == stable_id:
                self.metadata_map[node_id] = TreeNodeMetadata(
                    node_id=meta.node_id,
                    stable_id=meta.stable_id,
                    type=meta.type,
                    kind=meta.kind,
                    name=meta.name,
                    qualname=meta.qualname,
                    start_line=meta.start_line,
                    start_col=meta.start_col,
                    end_line=meta.end_line,
                    end_col=meta.end_col,
                    children_count=meta.children_count,
                    children_ids=meta.children_ids,
                    parent_id=meta.parent_id,
                    code=meta.code,
                    docstring=docstring,
                )
                return True
        return False

    def set_docstrings(self, docstrings: Dict[str, "DocstringMeta"]) -> Dict[str, bool]:
        """Set docstrings for multiple nodes in one call.

        Args:
            docstrings: Mapping of stable_id to DocstringMeta.

        Returns:
            Mapping of stable_id to True if node found and updated, False otherwise.
        """
        return {sid: self.set_docstring(sid, doc) for sid, doc in docstrings.items()}
