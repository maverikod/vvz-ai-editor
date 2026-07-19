import uuid

import pytest

from ai_editor.core.tree_temp.ini_source_parser import (
    ConfigContainer,
    ConfigKey,
    parse_ini_source,
)


def test_ini_parser_builds_root_and_section_key_nodes_with_trivia_and_anchors() -> None:
    source = """# root comment
name = editor ; keep this comment

[server] ; section
host: localhost
; port follows
port = 8080
"""

    roots = parse_ini_source(source)

    assert len(roots) == 1
    root = roots[0]
    assert isinstance(root, ConfigContainer)
    assert root.type == "object"
    assert root.insert_before_line == 1
    assert root.insert_after_line == 8

    root_key, section = root.children
    assert isinstance(root_key, ConfigKey)
    assert root_key.key == "name"
    assert root_key.value == "editor"
    assert root_key.comment_before == "# root comment"
    assert root_key.comment_inline == "; keep this comment"
    assert root_key.source_line == 2
    assert root_key.insert_before_line == 2
    assert root_key.insert_after_line == 3

    assert isinstance(section, ConfigContainer)
    assert section.key == "server"
    assert section.comment_before == ""
    assert section.source_line == 4
    assert section.insert_before_line == 4
    assert section.insert_after_line == 8
    host, port = section.children
    assert isinstance(host, ConfigKey)
    assert host.key == "host"
    assert host.value == "localhost"
    assert host.separator == ":"
    assert isinstance(port, ConfigKey)
    assert port.comment_before == "; port follows"
    assert port.source_line == 7


def test_ini_parser_assigns_parser_owned_uuid4_ids_and_section_trailing_trivia() -> None:
    source = """top = 1

[server]
host = localhost
# tail comment

"""

    root = parse_ini_source(source)[0]
    assert isinstance(root, ConfigContainer)
    section = root.children[1]
    assert isinstance(section, ConfigContainer)
    key = section.children[0]
    assert isinstance(key, ConfigKey)

    for node in (root, section, key):
        parsed_id = uuid.UUID(node.stable_id)
        assert parsed_id.version == 4
        assert str(parsed_id) == node.stable_id

    assert root.trailing_trivia == ""
    assert section.trailing_trivia == "# tail comment\n"
    assert section.end_line == 6
    assert section.insert_after_line == 7
    assert root.end_line == 6
    assert root.insert_after_line == 7


def test_ini_parser_rejects_non_key_non_section_content() -> None:
    with pytest.raises(ValueError, match="unsupported content on line 1"):
        parse_ini_source("not a key\n")
