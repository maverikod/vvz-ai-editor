"""
Base exception hierarchy for code analysis operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class AIEditorError(Exception):
    """Base exception for code analysis operations."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize exception.

        Args:
            message: Human-readable error message
            code: Optional error code for programmatic handling
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ValidationError(AIEditorError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Optional field name that failed validation
            details: Optional additional details
        """
        super().__init__(message, code="VALIDATION_ERROR", details=details)
        self.field = field


class RefactoringError(AIEditorError):
    """Raised when refactoring operations fail."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize refactoring error.

        Args:
            message: Error message
            operation: Optional refactoring operation name
            details: Optional additional details
        """
        super().__init__(message, code="REFACTORING_ERROR", details=details)
        self.operation = operation


class DatabaseError(AIEditorError):
    """Raised when database operations fail."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize database error.

        Args:
            message: Error message
            operation: Optional database operation name
            details: Optional additional details
        """
        super().__init__(message, code="DATABASE_ERROR", details=details)
        self.operation = operation


class DatabaseOperationError(AIEditorError):
    """Raised when specific database operations fail with detailed context."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        db_path: Optional[str] = None,
        sql: Optional[str] = None,
        params: Optional[Tuple[Any, ...]] = None,
        root_dir: Optional[str] = None,
        timeout: Optional[float] = None,
        cause: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize database operation error.

        Args:
            message: Human-readable error message
            operation: Database operation name (e.g., 'execute', 'fetchone')
            db_path: Path to database file
            sql: SQL statement that failed (may be truncated in logs)
            params: Query parameters tuple
            root_dir: Project root directory (if applicable)
            timeout: Operation timeout in seconds (if applicable)
            cause: Original exception that caused this error
            details: Optional additional error details
        """
        super().__init__(message, code="DATABASE_OPERATION_ERROR", details=details)
        self.operation = operation
        self.db_path = db_path
        self.sql = sql
        self.params = params
        self.root_dir = root_dir
        self.timeout = timeout
        self.cause = cause


class AnalysisError(AIEditorError):
    """Raised when analysis operations fail."""

    def __init__(
        self,
        message: str,
        analysis_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize analysis error.

        Args:
            message: Error message
            analysis_type: Optional analysis type (e.g., 'ast', 'semantic')
            details: Optional additional details
        """
        super().__init__(message, code="ANALYSIS_ERROR", details=details)
        self.analysis_type = analysis_type


class ChunkerResponseError(AIEditorError):
    """Raised when chunker response is invalid (e.g. embedding without model name)."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize chunker response error.

        Args:
            message: Error message
            file_path: Optional file path where the error occurred
            details: Optional additional details
        """
        super().__init__(message, code="CHUNKER_RESPONSE_ERROR", details=details)
        self.file_path = file_path


class ConfigurationError(AIEditorError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize configuration error.

        Args:
            message: Error message
            config_key: Optional configuration key that is invalid
            details: Optional additional details
        """
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)
        self.config_key = config_key


# Project-related exceptions


class ProjectIdError(AIEditorError):
    """Raised when project_id cannot be loaded or validated."""

    def __init__(
        self,
        message: str,
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize project ID error.

        Args:
            message: Error message
            project_id: Optional project ID that caused the error
            details: Optional additional details
        """
        super().__init__(message, code="PROJECT_ID_ERROR", details=details)
        self.project_id = project_id


class MultipleProjectIdError(AIEditorError):
    """Raised when multiple projectid files are found in the path."""

    def __init__(
        self,
        message: str,
        projectid_paths: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize multiple project ID error.

        Args:
            message: Error message
            projectid_paths: Optional list of paths to projectid files
            details: Optional additional details
        """
        super().__init__(message, code="MULTIPLE_PROJECT_ID_ERROR", details=details)
        self.projectid_paths = projectid_paths or []


class ProjectIdMismatchError(AIEditorError):
    """Raised when project_id from file does not match project_id from database."""

    def __init__(
        self,
        message: str,
        file_project_id: Optional[str] = None,
        db_project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize project ID mismatch error.

        Args:
            message: Error message
            file_project_id: Optional project ID from file
            db_project_id: Optional project ID from database
            details: Optional additional details
        """
        super().__init__(message, code="PROJECT_ID_MISMATCH_ERROR", details=details)
        self.file_project_id = file_project_id
        self.db_project_id = db_project_id


class ProjectNotFoundError(AIEditorError):
    """Raised when project is not found."""

    def __init__(
        self,
        message: str,
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize project not found error.

        Args:
            message: Error message
            project_id: Optional project ID that was not found
            details: Optional additional details
        """
        super().__init__(message, code="PROJECT_NOT_FOUND_ERROR", details=details)
        self.project_id = project_id


class InvalidProjectIdFormatError(AIEditorError):
    """Raised when projectid file has invalid format."""

    def __init__(
        self,
        message: str,
        projectid_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize invalid project ID format error.

        Args:
            message: Error message
            projectid_path: Optional path to projectid file
            details: Optional additional details
        """
        super().__init__(
            message, code="INVALID_PROJECT_ID_FORMAT_ERROR", details=details
        )
        self.projectid_path = projectid_path


class NestedProjectError(AIEditorError):
    """Raised when nested projects are detected."""

    def __init__(
        self,
        message: str,
        child_project: Optional[str] = None,
        parent_project: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize nested project error.

        Args:
            message: Error message
            child_project: Optional path to child project root
            parent_project: Optional path to parent project root
            details: Optional additional details
        """
        super().__init__(message, code="NESTED_PROJECT_ERROR", details=details)
        self.child_project = child_project
        self.parent_project = parent_project


class DuplicateProjectIdError(AIEditorError):
    """Raised when duplicate project_id is detected in different directories."""

    def __init__(
        self,
        message: str,
        project_id: Optional[str] = None,
        existing_root: Optional[str] = None,
        duplicate_root: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize duplicate project ID error.

        Args:
            message: Error message
            project_id: Optional project ID that is duplicated
            existing_root: Optional path to existing project root
            duplicate_root: Optional path to duplicate project root
            details: Optional additional details
        """
        super().__init__(message, code="DUPLICATE_PROJECT_ID_ERROR", details=details)
        self.project_id = project_id
        self.existing_root = existing_root
        self.duplicate_root = duplicate_root


# Git-related exceptions


class GitOperationError(AIEditorError):
    """Raised when git operations fail."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        git_command: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize git operation error.

        Args:
            message: Error message
            operation: Optional git operation name
            git_command: Optional git command that failed
            details: Optional additional details
        """
        super().__init__(message, code="GIT_OPERATION_ERROR", details=details)
        self.operation = operation
        self.git_command = git_command


# CST-related exceptions


class CSTModulePatchError(AIEditorError):
    """Raised when a CST patch cannot be applied safely."""

    def __init__(
        self,
        message: str,
        patch_type: Optional[str] = None,
        file_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize CST module patch error.

        Args:
            message: Error message
            patch_type: Optional type of patch that failed
            file_path: Optional path to file being patched
            details: Optional additional details
        """
        super().__init__(message, code="CST_MODULE_PATCH_ERROR", details=details)
        self.patch_type = patch_type
        self.file_path = file_path


class DocstringValidationError(CSTModulePatchError):
    """Raised when docstring validation fails."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        validation_errors: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize docstring validation error.

        Args:
            message: Error message
            file_path: Optional path to file with validation errors
            validation_errors: Optional list of validation error messages
            details: Optional additional details
        """
        super().__init__(
            message, patch_type="docstring", file_path=file_path, details=details
        )
        self.validation_errors = validation_errors or []


# Query-related exceptions


class QueryParseError(AIEditorError):
    """Raised when CSTQuery selector parsing fails."""

    def __init__(
        self,
        message: str,
        query_string: Optional[str] = None,
        parse_position: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize query parse error.

        Args:
            message: Error message
            query_string: Optional query string that failed to parse
            parse_position: Optional position in query string where error occurred
            details: Optional additional details
        """
        super().__init__(message, code="QUERY_PARSE_ERROR", details=details)
        self.query_string = query_string
        self.parse_position = parse_position
