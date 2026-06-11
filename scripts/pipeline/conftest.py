"""
Pytest fixtures for test pipeline.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path

from scripts.pipeline.config import PipelineConfig


@pytest.fixture
def pipeline_config():
    """Create pipeline configuration fixture."""
    return PipelineConfig()


@pytest.fixture
def test_data_dir():
    """Get test data directory."""
    return Path(__file__).parent.parent.parent / "test_data"


@pytest.fixture
def test_projects(test_data_dir):
    """Get list of test project directories."""
    projects = []
    if test_data_dir.exists():
        for item in test_data_dir.iterdir():
            if item.is_dir() and (item / "projectid").exists():
                projects.append(item)
    return projects
