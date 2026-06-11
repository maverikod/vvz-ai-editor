"""
Fixtures for query_cst command tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def project_root(tmp_path):
    """Project root as tmp_path."""
    return tmp_path


@pytest.fixture
def mock_db(project_root):
    """Mock database for query_cst (resolve project, index_file after replace)."""
    db = MagicMock()
    db.get_project.return_value = {
        "id": "test-proj",
        "root_path": str(project_root),
    }
    db.index_file.return_value = {"success": True}
    db.disconnect.return_value = None
    return db
