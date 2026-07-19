import uuid

from ai_editor.core.tree_temp.toml_source_parser import (
    TomlConfigContainer,
    parse_toml_source,
)
from ai_editor.core.tree_temp.toml_source_serializer import serialize_toml_source
from ai_editor.core.tree_temp.tree_node import TreeNode


def _inserted(key: str, value: object, type_: str = "string") -> TreeNode:
    return TreeNode(stable_id=str(uuid.uuid4()), type=type_, key=key, value=value)


def test_toml_serializer_preserves_order_comments_and_table_header_comment() -> None:
    source = """# root
first = 1
last = 3 # inline

[server] # table comment
# host comment
host = \"localhost\"
port = 80
"""
    root = parse_toml_source(source)[0]
    assert isinstance(root, TomlConfigContainer)
    table = root.children[2]
    assert isinstance(table, TomlConfigContainer)
    root.children.insert(1, _inserted("middle", 2, "number"))
    table.children.insert(1, _inserted("enabled", True, "boolean"))
    table.children[0].value = "example.test"
    del root.children[2]
    del table.children[2]

    assert serialize_toml_source([root]) == """# root
first = 1
middle = 2
[server] # table comment
# host comment
host = \"example.test\"
enabled = true
"""


def test_toml_serializer_preserves_raw_value_format_until_replace() -> None:
    source = 'title = "demo#value" # keep\nitems = [1,  2]\n'
    root = parse_toml_source(source)[0]
    assert serialize_toml_source([root]) == source
    root.children[0].value = "changed"
    assert serialize_toml_source([root]) == 'title = "changed" # keep\nitems = [1,  2]\n'
