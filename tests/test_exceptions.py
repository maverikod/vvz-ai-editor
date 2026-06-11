"""
Tests for exception hierarchy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from ai_editor.core.exceptions import (
    AIEditorError,
    ValidationError,
    RefactoringError,
    DatabaseError,
    DatabaseOperationError,
    AnalysisError,
    ConfigurationError,
    ProjectIdError,
    MultipleProjectIdError,
    ProjectIdMismatchError,
    ProjectNotFoundError,
    InvalidProjectIdFormatError,
    NestedProjectError,
    DuplicateProjectIdError,
    GitOperationError,
    CSTModulePatchError,
    DocstringValidationError,
    QueryParseError,
)


class TestAIEditorError:
    """Test base AIEditorError exception."""

    def test_base_exception_creation(self):
        """Test creating base exception."""
        error = AIEditorError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.code is None
        assert error.details == {}

    def test_base_exception_with_code(self):
        """Test creating base exception with code."""
        error = AIEditorError("Test error", code="TEST_ERROR")
        assert error.message == "Test error"
        assert error.code == "TEST_ERROR"

    def test_base_exception_with_details(self):
        """Test creating base exception with details."""
        details = {"key": "value", "number": 42}
        error = AIEditorError("Test error", details=details)
        assert error.details == details


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_creation(self):
        """Test creating validation error."""
        error = ValidationError("Validation failed", field="test_field")
        assert error.message == "Validation failed"
        assert error.field == "test_field"
        assert error.code == "VALIDATION_ERROR"
        assert isinstance(error, AIEditorError)


class TestRefactoringError:
    """Test RefactoringError exception."""

    def test_refactoring_error_creation(self):
        """Test creating refactoring error."""
        error = RefactoringError("Refactoring failed", operation="split_file")
        assert error.message == "Refactoring failed"
        assert error.operation == "split_file"
        assert error.code == "REFACTORING_ERROR"
        assert isinstance(error, AIEditorError)


class TestDatabaseError:
    """Test DatabaseError exception."""

    def test_database_error_creation(self):
        """Test creating database error."""
        error = DatabaseError("Database error", operation="query")
        assert error.message == "Database error"
        assert error.operation == "query"
        assert error.code == "DATABASE_ERROR"
        assert isinstance(error, AIEditorError)


class TestDatabaseOperationError:
    """Test DatabaseOperationError exception."""

    def test_database_operation_error_creation(self):
        """Test creating database operation error."""
        error = DatabaseOperationError(
            "Operation failed",
            operation="execute",
            db_path="/path/to/db",
            sql="SELECT * FROM files",
            params=("param1",),
            root_dir="/root",
            timeout=10.0,
        )
        assert error.message == "Operation failed"
        assert error.operation == "execute"
        assert error.db_path == "/path/to/db"
        assert error.sql == "SELECT * FROM files"
        assert error.params == ("param1",)
        assert error.root_dir == "/root"
        assert error.timeout == 10.0
        assert error.code == "DATABASE_OPERATION_ERROR"
        assert isinstance(error, AIEditorError)

    def test_database_operation_error_with_cause(self):
        """Test creating database operation error with cause."""
        cause = ValueError("Original error")
        error = DatabaseOperationError("Operation failed", cause=cause)
        assert error.cause is cause


class TestAnalysisError:
    """Test AnalysisError exception."""

    def test_analysis_error_creation(self):
        """Test creating analysis error."""
        error = AnalysisError("Analysis failed", analysis_type="ast")
        assert error.message == "Analysis failed"
        assert error.analysis_type == "ast"
        assert error.code == "ANALYSIS_ERROR"
        assert isinstance(error, AIEditorError)


class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_configuration_error_creation(self):
        """Test creating configuration error."""
        error = ConfigurationError("Config invalid", config_key="server_port")
        assert error.message == "Config invalid"
        assert error.config_key == "server_port"
        assert error.code == "CONFIGURATION_ERROR"
        assert isinstance(error, AIEditorError)


class TestProjectIdError:
    """Test ProjectIdError exception."""

    def test_project_id_error_creation(self):
        """Test creating project ID error."""
        error = ProjectIdError("Project ID error", project_id="test-id")
        assert error.message == "Project ID error"
        assert error.project_id == "test-id"
        assert error.code == "PROJECT_ID_ERROR"
        assert isinstance(error, AIEditorError)


class TestMultipleProjectIdError:
    """Test MultipleProjectIdError exception."""

    def test_multiple_project_id_error_creation(self):
        """Test creating multiple project ID error."""
        paths = ["/path1/projectid", "/path2/projectid"]
        error = MultipleProjectIdError(
            "Multiple projectid files found", projectid_paths=paths
        )
        assert error.message == "Multiple projectid files found"
        assert error.projectid_paths == paths
        assert error.code == "MULTIPLE_PROJECT_ID_ERROR"
        assert isinstance(error, AIEditorError)


class TestProjectIdMismatchError:
    """Test ProjectIdMismatchError exception."""

    def test_project_id_mismatch_error_creation(self):
        """Test creating project ID mismatch error."""
        error = ProjectIdMismatchError(
            "Project ID mismatch",
            file_project_id="file-id",
            db_project_id="db-id",
        )
        assert error.message == "Project ID mismatch"
        assert error.file_project_id == "file-id"
        assert error.db_project_id == "db-id"
        assert error.code == "PROJECT_ID_MISMATCH_ERROR"
        assert isinstance(error, AIEditorError)


class TestProjectNotFoundError:
    """Test ProjectNotFoundError exception."""

    def test_project_not_found_error_creation(self):
        """Test creating project not found error."""
        error = ProjectNotFoundError("Project not found", project_id="test-id")
        assert error.message == "Project not found"
        assert error.project_id == "test-id"
        assert error.code == "PROJECT_NOT_FOUND_ERROR"
        assert isinstance(error, AIEditorError)


class TestInvalidProjectIdFormatError:
    """Test InvalidProjectIdFormatError exception."""

    def test_invalid_project_id_format_error_creation(self):
        """Test creating invalid project ID format error."""
        error = InvalidProjectIdFormatError(
            "Invalid format", projectid_path="/path/projectid"
        )
        assert error.message == "Invalid format"
        assert error.projectid_path == "/path/projectid"
        assert error.code == "INVALID_PROJECT_ID_FORMAT_ERROR"
        assert isinstance(error, AIEditorError)


class TestNestedProjectError:
    """Test NestedProjectError exception."""

    def test_nested_project_error_creation(self):
        """Test creating nested project error."""
        error = NestedProjectError(
            "Nested project detected",
            child_project="/child",
            parent_project="/parent",
        )
        assert error.message == "Nested project detected"
        assert error.child_project == "/child"
        assert error.parent_project == "/parent"
        assert error.code == "NESTED_PROJECT_ERROR"
        assert isinstance(error, AIEditorError)


class TestDuplicateProjectIdError:
    """Test DuplicateProjectIdError exception."""

    def test_duplicate_project_id_error_creation(self):
        """Test creating duplicate project ID error."""
        error = DuplicateProjectIdError(
            "Duplicate project ID",
            project_id="test-id",
            existing_root="/existing",
            duplicate_root="/duplicate",
        )
        assert error.message == "Duplicate project ID"
        assert error.project_id == "test-id"
        assert error.existing_root == "/existing"
        assert error.duplicate_root == "/duplicate"
        assert error.code == "DUPLICATE_PROJECT_ID_ERROR"
        assert isinstance(error, AIEditorError)


class TestGitOperationError:
    """Test GitOperationError exception."""

    def test_git_operation_error_creation(self):
        """Test creating git operation error."""
        error = GitOperationError(
            "Git operation failed", operation="init", git_command="git init"
        )
        assert error.message == "Git operation failed"
        assert error.operation == "init"
        assert error.git_command == "git init"
        assert error.code == "GIT_OPERATION_ERROR"
        assert isinstance(error, AIEditorError)


class TestCSTModulePatchError:
    """Test CSTModulePatchError exception."""

    def test_cst_module_patch_error_creation(self):
        """Test creating CST module patch error."""
        error = CSTModulePatchError(
            "Patch failed", patch_type="docstring", file_path="/path/file.py"
        )
        assert error.message == "Patch failed"
        assert error.patch_type == "docstring"
        assert error.file_path == "/path/file.py"
        assert error.code == "CST_MODULE_PATCH_ERROR"
        assert isinstance(error, AIEditorError)


class TestDocstringValidationError:
    """Test DocstringValidationError exception."""

    def test_docstring_validation_error_creation(self):
        """Test creating docstring validation error."""
        validation_errors = ["Missing docstring", "Invalid format"]
        error = DocstringValidationError(
            "Validation failed",
            file_path="/path/file.py",
            validation_errors=validation_errors,
        )
        assert error.message == "Validation failed"
        assert error.file_path == "/path/file.py"
        assert error.validation_errors == validation_errors
        assert error.patch_type == "docstring"
        assert isinstance(error, CSTModulePatchError)
        assert isinstance(error, AIEditorError)


class TestQueryParseError:
    """Test QueryParseError exception."""

    def test_query_parse_error_creation(self):
        """Test creating query parse error."""
        error = QueryParseError(
            "Parse failed",
            query_string="Class.method",
            parse_position=10,
        )
        assert error.message == "Parse failed"
        assert error.query_string == "Class.method"
        assert error.parse_position == 10
        assert error.code == "QUERY_PARSE_ERROR"
        assert isinstance(error, AIEditorError)


class TestExceptionHierarchy:
    """Test exception hierarchy."""

    def test_all_exceptions_inherit_from_ai_editor_error(self):
        """Test that all exceptions inherit from AIEditorError."""
        exceptions = [
            ValidationError("test"),
            RefactoringError("test"),
            DatabaseError("test"),
            DatabaseOperationError("test"),
            AnalysisError("test"),
            ConfigurationError("test"),
            ProjectIdError("test"),
            MultipleProjectIdError("test"),
            ProjectIdMismatchError("test"),
            ProjectNotFoundError("test"),
            InvalidProjectIdFormatError("test"),
            NestedProjectError("test"),
            DuplicateProjectIdError("test"),
            GitOperationError("test"),
            CSTModulePatchError("test"),
            DocstringValidationError("test"),
            QueryParseError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, AIEditorError)
            assert isinstance(exc, Exception)

    def test_docstring_validation_inherits_from_cst_patch(self):
        """Test that DocstringValidationError inherits from CSTModulePatchError."""
        error = DocstringValidationError("test")
        assert isinstance(error, CSTModulePatchError)
        assert isinstance(error, AIEditorError)

    def test_exception_raising(self):
        """Test that exceptions can be raised and caught."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Test error", field="test_field")

        assert exc_info.value.message == "Test error"
        assert exc_info.value.field == "test_field"

    def test_exception_chaining(self):
        """Test exception chaining."""
        original_error = ValueError("Original")
        try:
            raise DatabaseOperationError("Database error", cause=original_error)
        except DatabaseOperationError as e:
            assert e.cause is original_error
            assert isinstance(e, AIEditorError)
