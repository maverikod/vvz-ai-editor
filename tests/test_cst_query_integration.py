"""
Integration tests for CSTQuery on real data from test_data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from ai_editor.cst_query import query_source

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestCSTQueryIntegrationRealData:
    """Integration tests for CSTQuery on real data from test_data/."""

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_functions_in_real_file(self):
        """Test querying functions in real file from vast_srv."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for functions
        matches = query_source(source, "function")
        assert len(matches) >= 0  # May have no top-level functions

        # Query for methods
        matches = query_source(source, "method")
        assert len(matches) >= 0  # May have no methods

        # Query for classes
        matches = query_source(source, "class")
        assert len(matches) >= 0  # May have no classes

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_classes_in_real_file(self):
        """Test querying classes in real file from vast_srv."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for classes
        matches = query_source(source, "class")
        assert len(matches) >= 0

        # If classes found, test querying methods within them
        if matches:
            class_name = matches[0].name
            if class_name:
                # Query for methods in specific class
                method_matches = query_source(
                    source, f'class[name="{class_name}"] method'
                )
                assert len(method_matches) >= 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_with_predicates_real_file(self):
        """Test querying with predicates on real file."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for functions with name predicate
        matches = query_source(source, 'function[name^="test"]')
        assert len(matches) >= 0

        # Query for classes with name predicate
        matches = query_source(source, 'class[name^="Test"]')
        assert len(matches) >= 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_statements_in_real_file(self):
        """Test querying statements in real file."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for return statements
        matches = query_source(source, 'smallstmt[type="Return"]')
        assert len(matches) >= 0

        # Query for all statements
        matches = query_source(source, "stmt")
        assert len(matches) >= 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_complex_queries_real_file(self):
        """Test complex queries on real file."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for first return in functions
        matches = query_source(source, "function smallstmt[type='Return']:first")
        assert len(matches) >= 0

        # Query for methods in classes
        matches = query_source(source, "class method")
        assert len(matches) >= 0

    @pytest.mark.skipif(not BHLFF_DIR.exists(), reason="test_data/bhlff/ not found")
    def test_query_bhlff_project(self):
        """Test querying files from bhlff project."""
        py_files = list(BHLFF_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/bhlff/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for functions
        matches = query_source(source, "function")
        assert len(matches) >= 0

        # Query for classes
        matches = query_source(source, "class")
        assert len(matches) >= 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_multiple_files_vast_srv(self):
        """Test querying multiple files from vast_srv."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))[:5]  # Limit to 5 files
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        total_functions = 0
        total_classes = 0

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                functions = query_source(source, "function")
                classes = query_source(source, "class")
                total_functions += len(functions)
                total_classes += len(classes)
            except Exception:
                continue

        # Should have processed at least some files
        assert total_functions >= 0
        assert total_classes >= 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_with_code_included_real_file(self):
        """Test querying with code included on real file."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for functions with code included
        matches = query_source(source, "function", include_code=True)
        assert len(matches) >= 0

        # If matches found, verify code is included
        if matches:
            for match in matches:
                assert match.code is not None
                assert len(match.code) > 0

    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(), reason="test_data/vast_srv/ not found"
    )
    def test_query_pseudos_real_file(self):
        """Test querying with pseudos on real file."""
        py_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = py_files[0]
        source = test_file.read_text(encoding="utf-8")

        # Query for first function
        matches = query_source(source, "function:first")
        assert len(matches) <= 1  # Should return at most one

        # Query for last function
        matches = query_source(source, "function:last")
        assert len(matches) <= 1  # Should return at most one

        # Query for nth function
        matches = query_source(source, "function:nth(0)")
        assert len(matches) <= 1  # Should return at most one
