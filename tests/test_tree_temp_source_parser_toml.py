from ai_editor.core.tree_temp.toml_source_parser import (
    TomlConfigContainer,
    TomlConfigKey,
    parse_toml_source,
)


def test_toml_parser_preserves_root_and_table_structure() -> None:
    source = "# document\ntitle = \"demo#value\" # inline\n\n[server.http]\n# host comment\nhost = \"localhost\"\nport = 8080\n"

    root = parse_toml_source(source)[0]
    assert isinstance(root, TomlConfigContainer)
    assert root.insert_before_line == 1
    assert root.end_line == 7

    title = root.children[0]
    assert isinstance(title, TomlConfigKey)
    assert title.key == "title"
    assert title.value == "demo#value"
    assert title.comment_before == "# document"
    assert title.comment_inline == "# inline"
    assert title.source_line == 2
    assert title.insert_before_line == 2
    assert title.insert_after_line == 3
    assert title.value_raw == '\"demo#value\"'
    assert title.line_ending == "\n"

    table = root.children[1]
    assert isinstance(table, TomlConfigContainer)
    assert table.table_name == "server.http"
    assert table.dotted_path == ("server", "http")
    assert table.comment_before == ""
    assert table.source_line == 4
    assert table.insert_before_line == 4
    assert table.insert_after_line == 8

    host = table.children[0]
    port = table.children[1]
    assert isinstance(host, TomlConfigKey)
    assert host.comment_before == "# host comment"
    assert host.value == "localhost"
    assert port.key == "port"
    assert port.value == 8080
    assert table.trailing_trivia == ""


def test_toml_parser_supports_arrays_inline_tables_and_eof_trivia() -> None:
    root = parse_toml_source(
        "items = [1, 2]\nmetadata = { enabled = true }\n# eof\n"
    )[0]

    items, metadata = root.children[:2]
    assert isinstance(items, TomlConfigKey)
    assert items.type == "array"
    assert [item.value for item in items.children] == [1, 2]
    assert isinstance(metadata, TomlConfigKey)
    assert metadata.type == "object"
    assert metadata.children[0].key == "enabled"
    assert metadata.children[0].value is True
    assert root.trailing_trivia == "# eof"


def test_toml_parser_preserves_inline_table_header_comment() -> None:
    root = parse_toml_source('[server] # table comment\nhost = "localhost"\n')[0]

    table = root.children[0]
    assert isinstance(table, TomlConfigContainer)
    assert table.table_name == "server"
    assert table.raw_header == "[server] # table comment"
    assert table.comment_inline == "# table comment"
    assert table.source_line == 1
    assert table.end_line == 2
    assert table.insert_before_line == 1
    assert table.insert_after_line == 3
    assert table.children[0].key == "host"


def test_toml_parser_rejects_invalid_toml() -> None:
    try:
        parse_toml_source("[broken\n")
    except ValueError as exc:
        assert str(exc).startswith("Invalid TOML:")
    else:
        raise AssertionError("invalid TOML was accepted")
