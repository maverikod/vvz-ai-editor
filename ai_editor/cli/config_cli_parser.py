"""
Argument parser builder for config CLI.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
from typing import Any, Callable

from ai_editor.core.config_placeholders import PH_CODE_ANALYSIS_HOST


def build_parser(
    cmd_generate: Callable[[argparse.Namespace], int],
    cmd_validate: Callable[[argparse.Namespace], int],
    cmd_schema: Callable[[argparse.Namespace], int],
) -> argparse.ArgumentParser:
    """Build and return the config CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Configuration generator and validator for ai-editor-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.required = True

    gen_parser = subparsers.add_parser(
        "generate", help="Generate configuration file", aliases=["gen"]
    )
    gen_parser.add_argument(
        "--protocol",
        type=str,
        choices=["http", "https", "mtls"],
        required=True,
        help="Server/proxy protocol",
    )
    gen_parser.add_argument(
        "--out",
        type=str,
        default="config.json",
        help="Output config path (default: config.json)",
    )
    gen_parser.add_argument(
        "--with-proxy",
        action="store_true",
        help="Enable proxy registration",
    )
    gen_parser.add_argument(
        "--server-host", type=str, help="Server host (default: 0.0.0.0)"
    )
    gen_parser.add_argument(
        "--server-port", type=int, help="Server port (default: 8080)"
    )
    gen_parser.add_argument(
        "--server-cert-file", type=str, help="Server certificate file path"
    )
    gen_parser.add_argument("--server-key-file", type=str, help="Server key file path")
    gen_parser.add_argument(
        "--server-ca-cert-file",
        type=str,
        help="Server CA certificate file path (required for mTLS protocol)",
    )
    gen_parser.add_argument("--server-crl-file", type=str, help="Server CRL file path")
    gen_parser.add_argument(
        "--server-debug", action="store_true", help="Enable debug mode (default: False)"
    )
    gen_parser.add_argument(
        "--server-log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (default: INFO)",
    )
    gen_parser.add_argument(
        "--server-log-dir",
        type=str,
        help="Log directory path (default: ./logs)",
    )
    gen_parser.add_argument(
        "--registration-host",
        type=str,
        help="Registration proxy host (default: localhost)",
    )
    gen_parser.add_argument(
        "--registration-port",
        type=int,
        help="Registration proxy port (default: 3005)",
    )
    gen_parser.add_argument(
        "--registration-protocol",
        type=str,
        choices=["http", "https", "mtls"],
        help="Registration protocol",
    )
    gen_parser.add_argument(
        "--registration-cert-file",
        type=str,
        help="Registration certificate file path",
    )
    gen_parser.add_argument(
        "--registration-key-file",
        type=str,
        help="Registration key file path",
    )
    gen_parser.add_argument(
        "--registration-ca-cert-file",
        type=str,
        help="Registration CA certificate file path",
    )
    gen_parser.add_argument(
        "--registration-crl-file",
        type=str,
        help="Registration CRL file path",
    )
    gen_parser.add_argument(
        "--registration-server-id",
        type=str,
        help="Server ID for registration",
    )
    gen_parser.add_argument(
        "--registration-server-name",
        type=str,
        help="Server name for registration",
    )
    gen_parser.add_argument(
        "--instance-uuid",
        type=str,
        help="Server instance UUID (UUID4 format, auto-generated if not provided)",
    )
    gen_parser.add_argument(
        "--server-advertised-host",
        type=str,
        help="Host/IP advertised in registration metadata (server.advertised_host)",
    )
    gen_parser.add_argument(
        "--enable-qa-mcp-hooks",
        action="store_true",
        help="Set enable_qa_mcp_hooks=true in generated config (default: false)",
    )
    gen_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip post-generation validation",
    )
    gen_parser.add_argument(
        "--code-analysis-host",
        type=str,
        default=PH_CODE_ANALYSIS_HOST,
        help=(
            "Code Analysis Server host/IP or placeholder "
            f"(default: {PH_CODE_ANALYSIS_HOST})"
        ),
    )
    gen_parser.add_argument(
        "--code-analysis-port",
        type=int,
        default=15010,
        help="Code Analysis Server port (default: 15010)",
    )
    gen_parser.add_argument(
        "--code-analysis-protocol",
        type=str,
        choices=["http", "https"],
        default="https",
        help="Code Analysis Server protocol (default: https)",
    )
    gen_parser.add_argument(
        "--code-analysis-timeout",
        type=float,
        default=60.0,
        help="Code Analysis Server request timeout in seconds (default: 60)",
    )
    gen_parser.add_argument(
        "--code-analysis-server-id",
        type=str,
        default="code-analysis-server",
        help="Registered MCP server_id for Code Analysis (default: code-analysis-server)",
    )
    gen_parser.add_argument(
        "--code-analysis-cert-file",
        type=str,
        help="Client certificate for mTLS to Code Analysis Server",
    )
    gen_parser.add_argument(
        "--code-analysis-key-file",
        type=str,
        help="Client key for mTLS to Code Analysis Server",
    )
    gen_parser.add_argument(
        "--code-analysis-ca-cert-file",
        type=str,
        help="CA certificate for Code Analysis Server mTLS",
    )
    gen_parser.add_argument(
        "--code-analysis-crl-file",
        type=str,
        help="CRL file for Code Analysis Server mTLS",
    )
    gen_parser.add_argument(
        "--code-analysis-check-hostname",
        action="store_true",
        help="Enable TLS hostname check for Code Analysis upstream",
    )
    gen_parser.add_argument(
        "--ai-editor-workspace-root",
        type=str,
        default="data/editor_workspaces",
        help="ai_editor.storage.workspace_root (default: data/editor_workspaces)",
    )
    gen_parser.add_argument(
        "--ai-editor-no-git-commit-on-write",
        action="store_true",
        help="Set ai_editor.git_commit_on_write=false (default: true)",
    )
    gen_parser.add_argument(
        "--queue-enabled",
        action="store_true",
        help="Enable queue manager (default: True)",
    )
    gen_parser.add_argument(
        "--queue-disabled",
        action="store_true",
        help="Disable queue manager",
    )
    gen_parser.add_argument(
        "--queue-in-memory",
        action="store_true",
        help="Use in-memory queue (default: True)",
    )
    gen_parser.add_argument(
        "--queue-persistent",
        action="store_true",
        help="Use persistent queue (not in-memory)",
    )
    gen_parser.add_argument(
        "--queue-max-concurrent",
        type=int,
        help="Maximum concurrent jobs (default: 10)",
    )
    gen_parser.add_argument(
        "--queue-retention-seconds",
        type=int,
        help="Completed job retention in seconds (default: 21600)",
    )
    gen_parser.add_argument(
        "--ai-editor-db-path",
        type=str,
        help="Database path for ai_editor section (default: data/ai_editor.db)",
    )
    gen_parser.add_argument(
        "--ai-editor-driver-type",
        type=str,
        choices=["sqlite", "sqlite_proxy", "postgres", "mysql"],
        help="Database driver type (default: sqlite_proxy)",
    )
    gen_parser.add_argument(
        "--ai-editor-driver-path",
        type=str,
        help="Database path for driver config (default: same as --ai-editor-db-path)",
    )
    gen_parser.add_argument(
        "--ai-editor-pg-host",
        type=str,
        help="PostgreSQL host (with --ai-editor-driver-type postgres)",
    )
    gen_parser.add_argument(
        "--ai-editor-pg-port",
        type=int,
        help="PostgreSQL port (default: 5432)",
    )
    gen_parser.add_argument(
        "--ai-editor-pg-dbname",
        type=str,
        help="PostgreSQL database name (default: ai_editor)",
    )
    gen_parser.add_argument(
        "--ai-editor-pg-user",
        type=str,
        help="PostgreSQL user name",
    )
    gen_parser.add_argument(
        "--ai-editor-pg-password-env",
        type=str,
        help="Environment variable for DB password, read from .env (default: AI_EDITOR_POSTGRES_PASSWORD)",
    )
    gen_parser.add_argument(
        "--ai-editor-log",
        type=str,
        help="Code analysis log file path (default: logs/ai_editor.log)",
    )
    gen_parser.add_argument(
        "--ai-editor-faiss-index-path",
        type=str,
        help="FAISS index file path (default: data/faiss_index.bin)",
    )
    gen_parser.add_argument(
        "--ai-editor-vector-dim",
        type=int,
        help="Vector dimension for embeddings (default: 384)",
    )
    gen_parser.add_argument(
        "--ai-editor-min-chunk-length",
        type=int,
        help="Minimum chunk length (default: 30)",
    )
    gen_parser.add_argument(
        "--ai-editor-retry-attempts",
        type=int,
        help="Vectorization retry attempts (default: 3)",
    )
    gen_parser.add_argument(
        "--ai-editor-retry-delay",
        type=float,
        help="Vectorization retry delay in seconds (default: 1.0)",
    )
    gen_parser.add_argument(
        "--allow-line-commands-on-healthy-files",
        action="store_true",
        help="Allow get_file_lines/replace_file_lines on parseable .py files (default: False)",
    )
    gen_parser.add_argument(
        "--indexing-worker-enabled",
        action="store_true",
        help="Enable indexing worker (default: True)",
    )
    gen_parser.add_argument(
        "--indexing-worker-disabled",
        action="store_true",
        help="Disable indexing worker",
    )
    gen_parser.add_argument(
        "--indexing-worker-poll-interval",
        type=int,
        help="Indexing worker poll interval in seconds (default: 30)",
    )
    gen_parser.add_argument(
        "--indexing-worker-batch-size",
        type=int,
        help="Indexing worker batch size (default: 5)",
    )
    gen_parser.add_argument(
        "--indexing-worker-log-path",
        type=str,
        help="Indexing worker log path (default: logs/indexing_worker.log)",
    )
    gen_parser.add_argument(
        "--file-watcher-enabled",
        action="store_true",
        help="Enable file watcher (default: True)",
    )
    gen_parser.add_argument(
        "--file-watcher-disabled",
        action="store_true",
        help="Disable file watcher",
    )
    gen_parser.add_argument(
        "--file-watcher-scan-interval",
        type=int,
        help="File watcher scan interval in seconds (default: 60)",
    )
    gen_parser.add_argument(
        "--file-watcher-log-path",
        type=str,
        help="File watcher log path (default: logs/file_watcher.log)",
    )
    gen_parser.add_argument(
        "--file-watcher-version-dir",
        type=str,
        help="File watcher version directory (default: data/versions)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-enabled",
        action="store_true",
        help="Set ai_editor.docs_indexing.enabled true (docs: .md/.json/.yaml/.yml; default off)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-disabled",
        action="store_true",
        help="Set ai_editor.docs_indexing.enabled false (default)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-vectorize",
        action="store_true",
        help="Set ai_editor.docs_indexing.vectorize true (default off; eligibility ignores)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-no-vectorize",
        action="store_true",
        help="Set ai_editor.docs_indexing.vectorize false (default)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-roots",
        type=str,
        help="Comma-separated docs_indexing.roots (default: docs)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-include",
        type=str,
        help="Comma-separated docs_indexing.include globs (each must reference .md/.json/.yaml/.yml)",
    )
    gen_parser.add_argument(
        "--ai-editor-docs-indexing-exclude",
        type=str,
        help="Comma-separated docs_indexing.exclude globs",
    )
    gen_parser.set_defaults(func=cmd_generate)

    val_parser = subparsers.add_parser(
        "validate", help="Validate configuration file", aliases=["val"]
    )
    val_parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to configuration file",
    )
    val_parser.set_defaults(func=cmd_validate)

    schema_parser = subparsers.add_parser(
        "schema",
        help="Apply database schema (create tables and indexes). Run once for new DB or after schema changes.",
    )
    schema_parser.add_argument(
        "--file",
        type=str,
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    schema_parser.add_argument(
        "--no-stop",
        action="store_true",
        help="Do not stop server/workers when DB is in use (migration may fail with 'database is locked')",
    )
    schema_parser.set_defaults(func=cmd_schema)

    return parser
