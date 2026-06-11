"""Trigger server reload."""

import subprocess
import sys

result = subprocess.run(
    [
        sys.executable,
        "-c",
        'import importlib; import ai_editor.core.cst_tree.tree_builder; importlib.reload(ai_editor.core.cst_tree.tree_builder); print("reloaded")',
    ],
    capture_output=True,
    text=True,
)
print(result.stdout)
print(result.stderr)
