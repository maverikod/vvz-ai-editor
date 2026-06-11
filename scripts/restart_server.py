import subprocess
import sys

result = subprocess.run(
    [sys.executable, '-m', 'ai_editor.server', 'restart'],
    capture_output=True, text=True, timeout=10,
)
print(result.stdout)
print(result.stderr)
