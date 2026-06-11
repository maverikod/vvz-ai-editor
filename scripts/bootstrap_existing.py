"""Bootstrap plan_manager: scaffold dirs, extract template, create venv."""
import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path('/home/vasilyvz/projects/tools/ai_editor')
sys.path.insert(0, str(ROOT))

from ai_editor.commands.project_creation import CreateProjectCommand  # noqa: E402

PROJECT_PATH = pathlib.Path('/home/vasilyvz/projects/tools/plan_manager')
TEMPLATE_ZIP = str(ROOT / 'rules_template.zip')
SLUG = 'plan_manager'


class _FakeDB:
    """Stub database."""

    def execute(self, *args, **kwargs):
        """No-op."""


async def _main():
    """Run bootstrap phases on plan_manager."""
    cmd = CreateProjectCommand(
        database=_FakeDB(),
        watch_dir_id='unused',
        project_name=SLUG,
        description='MCP server for managing project plans as a structured tree.',
        scaffold=True,
        create_venv=True,
        template_zip=TEMPLATE_ZIP,
    )
    report = await cmd._run_bootstrap(PROJECT_PATH, SLUG)
    print(json.dumps(report, indent=2))


asyncio.run(_main())
