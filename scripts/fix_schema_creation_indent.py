"""
One-off script to fix indentation in schema_creation.py.
Lines at 4 spaces that are not block starters get +4 spaces (become 8).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import re

PATH = "ai_editor/core/database/schema_creation.py"

# Block starters at 4 spaces: do not add indent
BLOCK_STARTER = re.compile(r"^\s{4}(try:|except\s|if\s|for\s|else:|elif\s|finally:)\s*")


def main() -> None:
    with open(PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out = []
    for line in lines:
        if line.startswith("    ") and not line.startswith("        "):
            stripped = line[4:].lstrip()
            if stripped and not BLOCK_STARTER.match(line):
                line = "    " + line
        out.append(line)

    with open(PATH, "w", encoding="utf-8") as f:
        f.writelines(out)
    print("Done.")


if __name__ == "__main__":
    main()
