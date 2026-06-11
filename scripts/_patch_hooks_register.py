"""One-shot patch: add lifecycle search commands to hooks_register_part1.py."""
from pathlib import Path

f = Path('ai_editor/hooks_register_part1.py')
content = f.read_text()

old = '        reg.register(SearchStartCommand, "custom")'
new = (
    '        reg.register(SearchStartCommand, "custom")\n'
    '        from .commands.search_get_page_command import SearchGetPageCommand\n'
    '        from .commands.search_get_status_command import SearchGetStatusCommand\n'
    '        from .commands.search_cancel_command import SearchCancelCommand\n'
    '        from .commands.search_close_command import SearchCloseCommand\n'
    '        reg.register(SearchGetPageCommand, "custom")\n'
    '        reg.register(SearchGetStatusCommand, "custom")\n'
    '        reg.register(SearchCancelCommand, "custom")\n'
    '        reg.register(SearchCloseCommand, "custom")'
)

if old not in content:
    print('MARKER NOT FOUND')
    exit(1)

patched = content.replace(old, new, 1)
f.write_text(patched)
print('OK')
