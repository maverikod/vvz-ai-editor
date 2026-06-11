#!/usr/bin/env python3
"""
Build fixed file content for cst_convert_and_save (from get_file_lines data).
Writes to data/ for reading and passing to server. One-off for fixing indexing errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def build_update_test_fixed() -> str:
    """Fixed update_test_files.py: line 20 no comma after re.sub("""
    lines = [
        "#!/usr/bin/env python3",
        '"""',
        "Script to update all test files to use BaseTester.",
        "",
        "Author: Vasiliy Zdanovskiy",
        "email: vasilyvz@gmail.com",
        '"""',
        "",
        "import os",
        "import re",
        "",
        "def update_test_file(filename):",
        '    """Update a test file to use BaseTester."""',
        "    if not os.path.exists(filename):",
        "        return",
        "    ",
        "    with open(filename, 'r') as f:",
        "        content = f.read()",
        "    ",
        "    # Update imports",
        "    content = re.sub(",  # fixed: was "re.sub(","
        "        r'import asyncio\\nimport aiohttp\\nfrom typing import List, Dict, Any\\nfrom rich\\.console import Console',",
        "        'import asyncio\\nfrom typing import List, Dict, Any\\nfrom test_base import BaseTester',",
        "        content",
        "    )",
        "    ",
        "    # Update class definition",
        "    class_name = filename.replace('test_', '').replace('.py', '').title() + 'Tests'",
        '    pattern = rf\'class {class_name}:\\s*\\n\\s*"""([^"]*)"""\\s*\\n\\s*def __init__\\(self, base_url: str, headers: Dict\\[str, str\\] = None\\):\\s*\\n\\s*self\\.base_url = base_url\\s*\\n\\s*self\\.headers = headers or \\{\\}\\s*\\n\\s*self\\.console = Console\\(\\)\'',
        '    repl = rf\'class {class_name}(BaseTester):\\n    """\\\\1"""\'',
        "    content = re.sub(pattern, repl, content)",
        "    ",
        "    # Update test methods to use _make_request",
        "    # This is a simplified version - would need more complex regex for full automation",
        "    ",
        "    with open(filename, 'w') as f:",
        "        f.write(content)",
        "    ",
        '    print(f"Updated {filename}")',
        "",
        "def main():",
        '    """Update all test files."""',
        "    test_files = [",
        "        'test_ftp.py',",
        "        'test_vast.py', ",
        "        'test_k8s.py',",
        "        'test_ollama.py',",
        "        'test_github.py',",
        "        'test_queue.py',",
        "        'test_system.py'",
        "    ]",
        "    ",
        "    for filename in test_files:",
        "        update_test_file(filename)",
        "",
        'if __name__ == "__main__":',
        "    main()",
    ]
    return "\n".join(lines)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "_temp_update_test_fixed.py"
    out.write_text(build_update_test_fixed(), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
