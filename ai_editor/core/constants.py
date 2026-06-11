"""
Project-wide constants.

This module contains all constants used across the codebase to avoid hardcoded values.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Set

from .project_ignore_policy import DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES

# ============================================================================
# File Extensions
# ============================================================================

# File extensions to scan and add to DB for indexing.
# Only .py is indexed (AST/CST); other extensions were causing index errors.
# Config files can be tracked elsewhere via CONFIG_FILE_EXTENSIONS if needed.
CODE_FILE_EXTENSIONS: Set[str] = {
    ".py",
}

# Configuration file extensions
CONFIG_FILE_EXTENSIONS: Set[str] = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}


# ============================================================================
# Ignore Patterns
# ============================================================================

# Default patterns to ignore (always applied). Unioned with shared traversal dir names.
DEFAULT_IGNORE_PATTERNS: Set[str] = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".tox",
    ".nox",
    "node_modules",
    "dist",
    "build",
    "data/versions",  # Version directory for deleted files
    "data/versions/**",  # All subdirectories in versions
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.lock",
    ".coverage",
} | set(DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES)

# Git ignore patterns (additional patterns for .gitignore)
GIT_IGNORE_PATTERNS: Set[str] = {
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    "*.so",
    ".Python",
    "build/",
    "develop-eggs/",
    "dist/",
    "downloads/",
    "eggs/",
    ".eggs/",
    "lib/",
    "lib64/",
    "parts/",
    "sdist/",
    "var/",
    "wheels/",
    "*.egg-info/",
    ".installed.cfg",
    "*.egg",
    ".venv/",
    "venv/",
    "ENV/",
    "env/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".coverage",
    "htmlcov/",
    ".tox/",
    ".cache",
    "*.log",
    "data/",
    "logs/",
}


# ============================================================================
# File and Directory Names
# ============================================================================

# Project identification file name
PROJECTID_FILENAME: str = "projectid"

# Git directory name
GIT_DIR_NAME: str = ".git"

# Git ignore file name
GITIGNORE_FILENAME: str = ".gitignore"

# Version directory name (relative to project root)
VERSIONS_DIR_NAME: str = "data/versions"

# Locks directory name (relative to config directory)
LOCKS_DIR_NAME: str = "data/locks"

# Logs directory name (relative to project root)
LOGS_DIR_NAME: str = "logs"

# Data directory name (relative to project root)
DATA_DIR_NAME: str = "data"


# ============================================================================
# Sizes and Limits
# ============================================================================

# Maximum lines in a file before splitting is recommended
DEFAULT_MAX_FILE_LINES: int = 400

# Minimum text length for chunking
DEFAULT_MIN_CHUNK_LENGTH: int = 30

# Maximum log file size in bytes (10 MB)
DEFAULT_LOG_MAX_BYTES: int = 10485760

# Number of backup log files to keep
DEFAULT_LOG_BACKUP_COUNT: int = 5

# Default vector dimension for embeddings
DEFAULT_VECTOR_DIM: int = 384

# File modification time tolerance in seconds (for comparison)
FILE_MODIFICATION_TOLERANCE: float = 0.1

# Epsilon for updating last_modified timestamp
LAST_MODIFIED_EPSILON: float = 0.001

# Default request queue maximum size
DEFAULT_QUEUE_MAX_SIZE: int = 1000

# Maximum RPC request size in bytes (10 MB)
RPC_MAX_REQUEST_SIZE: int = 10485760

# Max .json file size (bytes on disk) for read_project_text_file to use structured JSON load
# (same session shape as json_load_file). Above this, the command returns plain text lines.
DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES: int = 1048576


# ============================================================================
# Timeouts and Intervals
# ============================================================================

# Default poll interval in seconds
DEFAULT_POLL_INTERVAL: int = 30

# Default scan interval in seconds
DEFAULT_SCAN_INTERVAL: int = 60

# Default retry attempts count
DEFAULT_RETRY_ATTEMPTS: int = 3

# Default retry delay in seconds
DEFAULT_RETRY_DELAY: float = 10.0

# Default command timeout in seconds
DEFAULT_COMMAND_TIMEOUT: float = 60.0

# Default git command timeout in seconds
DEFAULT_GIT_TIMEOUT: float = 10.0

# Proxy driver poll interval in seconds
PROXY_DRIVER_POLL_INTERVAL: float = 1.0

# Maximum retries for database connection
DB_CONNECTION_MAX_RETRIES: int = 5

# Delay between database connection retries in seconds
DB_CONNECTION_RETRY_DELAY: float = 2.0

# Maximum scan duration in seconds
DEFAULT_MAX_SCAN_DURATION: int = 300

# Default worker stop timeout in seconds
DEFAULT_WORKER_STOP_TIMEOUT: float = 10.0

# Default worker monitoring interval in seconds
DEFAULT_WORKER_MONITOR_INTERVAL: float = 30.0

# Driver startup delay in seconds (wait for socket creation; bind can lag under load)
DRIVER_STARTUP_DELAY: float = 2.0

# RPC server socket timeout in seconds
RPC_SERVER_SOCKET_TIMEOUT: float = 1.0

# RPC processing loop interval in seconds
RPC_PROCESSING_LOOP_INTERVAL: float = 0.1

# Driver main loop interval in seconds
DRIVER_MAIN_LOOP_INTERVAL: float = 0.1

# Default request timeout in seconds
DEFAULT_REQUEST_TIMEOUT: float = 300.0

# Default RPC server worker pool size for generic (non-SQLite) RPC path only.
# Must never be used for SQLite: SQLite uses isolated process with
# SQLITE_RPC_SINGLE_CONSUMER_POOL_SIZE and single-consumer queue semantics.
DEFAULT_RPC_WORKER_POOL_SIZE: int = 10

# Default shutdown grace timeout in seconds
DEFAULT_SHUTDOWN_GRACE_TIMEOUT: float = 30.0


# ============================================================================
# SQLite serialized execution (isolated process)
# ============================================================================
#
# SQLite DB file operations are executed by exactly one DB executor thread
# (TZ/architecture constraint). The isolated process uses a single-consumer
# queue; DEFAULT_RPC_WORKER_POOL_SIZE must not be used for SQLite SQL
# execution.

# RPC worker pool size for SQLite isolated process: exactly one executor
# for all DB file operations (no multi-threaded SQL execution for SQLite).
SQLITE_RPC_SINGLE_CONSUMER_POOL_SIZE: int = 1

# Mode identifier for serialized/single-consumer queue semantics in the
# SQLite isolated process (consumed by runner and RPC server in later steps).
SQLITE_SERIALIZED_EXECUTION_MODE: str = "serialized"


# ============================================================================
# Analysis Patterns
# ============================================================================

# Placeholder patterns for code analysis
PLACEHOLDER_PATTERNS: list[str] = [
    "TODO",
    "FIXME",
    "XXX",
    "HACK",
    "NOTE",
    "BUG",
    "OPTIMIZE",
    "PLACEHOLDER",
    "STUB",
    "NOT IMPLEMENTED",
]

# Stub patterns (functions/methods with pass, ellipsis, NotImplementedError)
STUB_PATTERNS: list[str] = [
    "pass",
    "...",
    "NotImplementedError",
    "raise NotImplementedError",
]


# ============================================================================
# Ports and Hosts
# ============================================================================

# Default server host
DEFAULT_SERVER_HOST: str = "0.0.0.0"

# Default server port
DEFAULT_SERVER_PORT: int = 15000

# Default chunker service port
DEFAULT_CHUNKER_PORT: int = 8009

# Default embedding service port
DEFAULT_EMBEDDING_PORT: int = 8001

# Default localhost
DEFAULT_LOCALHOST: str = "localhost"


# ============================================================================
# Circuit Breaker
# ============================================================================

# Default failure threshold for circuit breaker
DEFAULT_FAILURE_THRESHOLD: int = 5

# Default recovery timeout in seconds
DEFAULT_RECOVERY_TIMEOUT: float = 60.0

# Default success threshold for circuit breaker
DEFAULT_SUCCESS_THRESHOLD: int = 2

# Default initial backoff in seconds
DEFAULT_INITIAL_BACKOFF: float = 5.0

# Default maximum backoff in seconds
DEFAULT_MAX_BACKOFF: float = 300.0

# Default backoff multiplier
DEFAULT_BACKOFF_MULTIPLIER: float = 2.0


# ============================================================================
# Batch Processor
# ============================================================================

# Default batch size
DEFAULT_BATCH_SIZE: int = 10

# Default maximum empty iterations
DEFAULT_MAX_EMPTY_ITERATIONS: int = 3

# Default empty delay in seconds
DEFAULT_EMPTY_DELAY: float = 5.0


# ============================================================================
# File Paths (relative to project root or config directory)
# ============================================================================

# Default database path (relative to config directory)
DEFAULT_DB_PATH: str = "data/ai_editor.db"

# Default FAISS directory (relative to config directory)
DEFAULT_FAISS_DIR: str = "data/faiss"

# Default vectorization worker log path (relative to project root)
DEFAULT_VECTORIZATION_WORKER_LOG: str = "logs/vectorization_worker.log"

# Default file watcher log path (relative to project root)
DEFAULT_FILE_WATCHER_LOG: str = "logs/file_watcher.log"

# Default database driver log filename
DEFAULT_DATABASE_DRIVER_LOG_FILENAME: str = "database_driver.log"


# ============================================================================
# Database Driver
# ============================================================================

# Default database driver type
DEFAULT_DB_DRIVER_TYPE: str = "sqlite_proxy"

# Default database driver socket directory
DEFAULT_DB_DRIVER_SOCKET_DIR: str = "/tmp/ai_editor_db_drivers"

# Default config file name
DEFAULT_CONFIG_FILENAME: str = "config.json"


# ============================================================================
# File Watcher Ignore Patterns (for config)
# ============================================================================

# Default ignore patterns for file watcher (glob patterns)
FILE_WATCHER_IGNORE_PATTERNS: list[str] = [
    "**/__pycache__/**",
    "**/.git/**",
    "**/node_modules/**",
]


# ============================================================================
# Read-only batch command output
# ============================================================================

# Maximum inline response size in bytes; above this, output is written to file.
# Must be a finite value (no hidden default that bypasses overflow-to-file).
DEFAULT_BATCH_MAX_RESPONSE_BYTES: int = 1_048_576  # 1 MiB

# Default directory for oversized batch output files (relative or absolute).
# Resolved at config load; must comply with project writable path policy.
DEFAULT_BATCH_OUTPUT_DIR: str = "data/batch_output"

# Retention time in seconds for batch output files; 0 means no automatic cleanup.
DEFAULT_BATCH_OUTPUT_RETENTION_SECONDS: int = 86_400  # 24 hours
