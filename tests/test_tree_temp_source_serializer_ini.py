import uuid

from ai_editor.core.tree_temp.ini_source_parser import ConfigContainer, parse_ini_source
from ai_editor.core.tree_temp.ini_source_serializer import serialize_ini_source
from ai_editor.core.tree_temp.tree_node import TreeNode


def _inserted(key: str, value: str) -> TreeNode:
    return TreeNode(stable_id=str(uuid.uuid4()), type="string", key=key, value=value)


def test_ini_serializer_inserts_root_and_section_keys_in_list_order() -> None:
    source = """# root
first = 1
last = 3 ; inline
[server] ; section
# host comment
host: localhost
tail: yes
"""
    root = parse_ini_source(source)[0]
    assert isinstance(root, ConfigContainer)
    section = root.children[2]
    assert isinstance(section, ConfigContainer)
    root.children.insert(1, _inserted("middle", "2"))
    section.children.insert(1, _inserted("port", "8080"))
    assert serialize_ini_source([root]) == """# root
first = 1
middle = 2
last = 3 ; inline
[server] ; section
# host comment
host: localhost
port: 8080
tail: yes
"""


def test_ini_serializer_replace_and_delete_preserve_comments_order_and_style() -> None:
    source = """; preamble
name = old ; keep
remove = gone

[server]
# keep before host
host: old
delete_me: gone
port: 80 ; port comment
# section tail
"""
    root = parse_ini_source(source)[0]
    assert isinstance(root, ConfigContainer)
    name, _remove, section = root.children
    assert isinstance(section, ConfigContainer)
    name.value = "new"
    section.children[0].value = "example.test"
    del root.children[1]
    del section.children[1]
    assert serialize_ini_source([root]) == """; preamble
name = new ; keep
[server]
# keep before host
host: example.test
port: 80 ; port comment
# section tail
"""
