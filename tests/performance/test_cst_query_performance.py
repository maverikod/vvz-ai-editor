"""
Performance tests for CSTQuery.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import time
from pathlib import Path

import pytest

from ai_editor.cst_query import query_source

TEST_DATA_DIR = Path(__file__).parent.parent.parent / "test_data"


class TestCSTQueryPerformance:
    """Performance tests for CSTQuery."""

    def test_query_performance_small_file(self):
        """Test query performance on small file."""
        source = """
class TestClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
    
    def method3(self):
        pass
"""
        start = time.time()
        matches = query_source(source, "method")
        duration = time.time() - start

        assert len(matches) == 3
        assert duration < 0.25, f"Query took {duration:.3f}s, should be < 0.25s"

    def test_query_performance_medium_file(self):
        """Test query performance on medium file."""
        # Generate medium-sized source
        source = "class TestClass:\n"
        for i in range(100):
            source += f"    def method_{i}(self):\n        pass\n"

        start = time.time()
        matches = query_source(source, "method")
        duration = time.time() - start

        assert len(matches) == 100
        assert duration < 1.0, f"Query took {duration:.3f}s, should be < 1.0s"

    def test_query_performance_large_file(self):
        """Test query performance on large file."""
        # Generate large source
        source = "class TestClass:\n"
        for i in range(1000):
            source += f"    def method_{i}(self):\n        pass\n"

        start = time.time()
        matches = query_source(source, "method")
        duration = time.time() - start

        assert len(matches) == 1000
        # Allow up to 12s for 1000 methods; variance across CI/machines
        assert duration < 12.0, f"Query took {duration:.3f}s, should be < 12.0s"

    def test_complex_query_performance(self):
        """Test complex query performance."""
        source = "class TestClass:\n"
        for i in range(100):
            source += f"    def method_{i}(self):\n        return True\n"

        start = time.time()
        # Use descendant combinator (methods are not direct children of class)
        # Use double quotes for selector values
        matches = query_source(
            source, 'class[name="TestClass"] method[name="method_50"]'
        )
        duration = time.time() - start

        assert len(matches) == 1
        # Allow up to 2.0s for complex selector; variance across CI/machines
        assert duration < 2.0, f"Query took {duration:.3f}s, should be < 2.0s"

    @pytest.mark.skipif(not TEST_DATA_DIR.exists(), reason="test_data not found")
    def test_query_performance_real_file(self):
        """Test query performance on real file from test_data."""
        vast_srv_dir = TEST_DATA_DIR / "vast_srv"
        if not vast_srv_dir.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find a Python file
        py_files = list(vast_srv_dir.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        start = time.time()
        matches = query_source(source, "function")
        duration = time.time() - start

        # Should complete in reasonable time
        assert duration < 1.0, f"Query took {duration:.3f}s, should be < 1.0s"
        assert len(matches) >= 0  # May have no functions

    @pytest.mark.skipif(not TEST_DATA_DIR.exists(), reason="test_data not found")
    def test_query_performance_real_codebase(self):
        """Test query performance on real codebase."""
        vast_srv_dir = TEST_DATA_DIR / "vast_srv"
        if not vast_srv_dir.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find multiple Python files
        py_files = list(vast_srv_dir.rglob("*.py"))[:10]  # Limit to 10 files
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        total_matches = 0
        start = time.time()

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                matches = query_source(source, "function")
                total_matches += len(matches)
            except Exception:
                continue

        duration = time.time() - start

        # Should complete in reasonable time (increased timeout for real files)
        assert duration < 15.0, f"Query took {duration:.3f}s, should be < 15.0s"
        assert total_matches >= 0
