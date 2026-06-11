"""One-shot patch: add _fix_yaml_string_values to open_command.py."""
from pathlib import Path
import ast

target = Path(
    "/home/vasilyvz/projects/tools/ai_editor/"
    "ai_editor/commands/universal_file_edit/open_command.py"
)
content = target.read_text(encoding="utf-8")

FUNC = '''

def _fix_yaml_string_values(text: str) -> str:
    """Quote unquoted YAML scalar values that contain ': ' or inline comments.

    PyYAML misparses bare values containing ': ' (treats them as new mapping
    keys). This pre-write fixer wraps such values in double quotes so the file
    remains valid YAML after write.

    Skips block scalars (> |), flow collections ({} []), already-quoted values,
    booleans, null, and numeric scalars.

    Args:
        text: Raw YAML text that may contain unquoted problematic values.

    Returns:
        YAML text with problematic scalar values quoted.
    """
    import re as _re

    _YAML_SCALARS = frozenset(
        {"true", "false", "null", "~", "yes", "no", "on", "off"}
    )
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    in_block_scalar = False
    block_indent = 0

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if in_block_scalar:
            if stripped and indent <= block_indent and not stripped[0].isspace():
                in_block_scalar = False
            else:
                result.append(line)
                continue

        if stripped.startswith("#"):
            result.append(line)
            continue

        if _re.match(r"^(\s*)[\w_-]+:\s*[>|](\s*#.*)?$", line.rstrip()):
            in_block_scalar = True
            block_indent = indent
            result.append(line)
            continue

        m = _re.match(r"^(\s*)([\w_-]+):\s+(.+)$", line.rstrip())
        if not m:
            result.append(line)
            continue

        key_indent, key, value = m.group(1), m.group(2), m.group(3)

        if value.startswith(("'", '"')):
            result.append(line)
            continue
        if value.startswith("{") or value.startswith("["):
            result.append(line)
            continue
        if value.lower() in _YAML_SCALARS:
            result.append(line)
            continue
        if _re.match(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$", value):
            result.append(line)
            continue

        cm = _re.search(r"\s+#\s", value)
        if cm:
            val_part = value[: cm.start()].strip()
            comment_part = "  " + value[cm.start() :].strip()
        else:
            val_part = value
            comment_part = ""

        needs_quote = ": " in val_part or (
            comment_part and not val_part.startswith(("'", '"'))
        )
        if not needs_quote:
            result.append(line)
            continue

        escaped = val_part.replace("\\", "\\\\").replace('"', '\\"')
        new_line = f'{key_indent}{key}: "{escaped}"{comment_part}\n'
        result.append(new_line)

    return "".join(result)
'''

INSERT_BEFORE = "class UniversalFileOpenCommand(BaseMCPCommand):"
if "def _fix_yaml_string_values" not in content:
    content = content.replace(INSERT_BEFORE, FUNC + "\n" + INSERT_BEFORE)
    print("Added _fix_yaml_string_values function")
else:
    print("Function already present")

OLD_YAML_BLOCK = (
    '            elif suffix in (".yaml", ".yml"):\n'
    "                abs_path.write_text(\n"
    '                    initial_content if initial_content else "{}\\n",\n'
    '                    encoding="utf-8",\n'
    "                )"
)
NEW_YAML_BLOCK = (
    '            elif suffix in (".yaml", ".yml"):\n'
    "                abs_path.write_text(\n"
    "                    _fix_yaml_string_values(\n"
    '                        initial_content if initial_content else "{}\\n"\n'
    "                    ),\n"
    '                    encoding="utf-8",\n'
    "                )"
)

if OLD_YAML_BLOCK in content:
    content = content.replace(OLD_YAML_BLOCK, NEW_YAML_BLOCK)
    print("Replaced YAML write block")
elif NEW_YAML_BLOCK in content:
    print("YAML block already patched")
else:
    print("ERROR: YAML block not found")
    for i, line in enumerate(content.splitlines()):
        if ".yaml" in line or ".yml" in line:
            print(f"  L{i + 1}: {line}")

target.write_text(content, encoding="utf-8")
print("File written.")

try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
