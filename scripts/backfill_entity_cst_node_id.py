"""
One-off backfill script: fill nullable cst_node_id for existing entity rows.

Fills cst_node_id (UUID4) for classes, functions, and methods where it is NULL.
Resolves entity -> CST node by file path and line range where possible; otherwise
generates a new UUID4 (documented policy: entity is not resolvable to a tree node
until re-indexed).

Policy when mapping is impossible (file missing, parse error, or no matching node):
assign a new UUID4 so that no row remains NULL. Do not leave NULL after completion.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_editor.core.database import CodeDatabase
from ai_editor.core.database.base import create_driver_config_for_worker
from ai_editor.core.cst_tree.tree_builder import load_file_to_tree
from ai_editor.core.cst_tree.tree_range_finder import find_node_by_range

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _missing_cst_node_id_columns(database: CodeDatabase) -> List[str]:
    """Return list of table names (classes, functions, methods) that lack cst_node_id."""
    missing = []
    for table in ("classes", "functions", "methods"):
        try:
            info = database._get_table_info(table)
        except Exception:
            missing.append(table)
            continue
        names = {col.get("name") for col in (info or [])}
        if "cst_node_id" not in names:
            missing.append(table)
    return missing


def _is_valid_uuid4(value: str) -> bool:
    """Return True if value is a valid UUID4 string."""
    if not value or len(value) != 36:
        return False
    try:
        u = uuid.UUID(value)
        return u.version == 4
    except (ValueError, AttributeError):
        return False


def _resolve_file_abs_path(
    database: CodeDatabase, file_id: int
) -> Optional[Tuple[str, str]]:
    """
    Resolve file_id to (absolute_path, project_id).

    Returns None if file or project not found.
    """
    row = database._fetchone(
        "SELECT f.path, f.project_id FROM files f WHERE f.id = ?", (file_id,)
    )
    if not row:
        return None
    path = row["path"]
    project_id = row["project_id"]
    proj = database._fetchone(
        "SELECT root_path FROM projects WHERE id = ?", (project_id,)
    )
    if not proj:
        return None
    root = Path(proj["root_path"]).resolve()
    if Path(path).is_absolute():
        abs_path = str(Path(path).resolve())
    else:
        abs_path = str((root / path).resolve())
    return (abs_path, project_id)


def _resolve_node_id_from_tree(
    tree_id: str,
    entity_line: int,
    entity_end_line: Optional[int],
    entity_name: str,
    entity_kind: str,
) -> Optional[str]:
    """
    Resolve entity to node_id using an already-loaded tree.

    entity_kind: "class" | "function" | "method"
    Returns node_id if a matching node is found, else None.
    """
    end_line = entity_end_line if entity_end_line is not None else entity_line
    try:
        meta = find_node_by_range(tree_id, entity_line, end_line, prefer_exact=False)
    except Exception:
        return None
    if not meta:
        return None
    if entity_kind == "class":
        if meta.type != "ClassDef" or (meta.name or "") != entity_name:
            return None
    elif entity_kind == "function":
        if meta.type != "FunctionDef" or meta.kind != "function":
            return None
        if (meta.name or "") != entity_name:
            return None
    elif entity_kind == "method":
        if meta.type != "FunctionDef" or meta.kind != "method":
            return None
        if (meta.name or "") != entity_name:
            return None
    else:
        return None
    if not _is_valid_uuid4(meta.node_id):
        return None
    return meta.node_id


def _backfill_table(
    database: CodeDatabase,
    table: str,
    id_column: str,
    file_id_column: str,
    line_column: str,
    end_line_column: str,
    name_column: str,
    entity_kind: str,
    dry_run: bool,
    stats: Dict[str, int],
) -> None:
    """
    Backfill cst_node_id for one entity table.

    Loads each file at most once (group by file_id) then resolves or generates
    node_id for all entities in that file.
    """
    if table == "methods":
        rows = database._fetchall(
            """
            SELECT m.id, m.name, m.line, m.end_line, c.file_id
            FROM methods m
            JOIN classes c ON m.class_id = c.id
            WHERE m.cst_node_id IS NULL OR trim(m.cst_node_id) = ''
            """
        )
    else:
        rows = database._fetchall(
            f"""
            SELECT id, name, line, end_line, {file_id_column} AS file_id
            FROM {table}
            WHERE cst_node_id IS NULL OR trim(cst_node_id) = ''
            """
        )

    by_file: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        file_id = row["file_id"]
        by_file.setdefault(file_id, []).append(row)

    for file_id, file_rows in by_file.items():
        tree_id: Optional[str] = None
        resolved = _resolve_file_abs_path(database, file_id)
        if resolved:
            abs_path, _ = resolved
            if Path(abs_path).exists() and Path(abs_path).is_file():
                try:
                    tree = load_file_to_tree(abs_path)
                    tree_id = tree.tree_id
                except Exception:
                    pass
        for row in file_rows:
            eid = row["id"]
            name = row["name"] or ""
            line = row["line"]
            end_line = row.get("end_line")
            stats["processed"] += 1
            if tree_id:
                node_id = _resolve_node_id_from_tree(
                    tree_id, line, end_line, name, entity_kind
                )
            else:
                node_id = None
            if node_id:
                stats["mapped"] += 1
            else:
                node_id = str(uuid.uuid4())
                stats["generated"] += 1
            if not dry_run:
                try:
                    database._execute(
                        f"UPDATE {table} SET cst_node_id = ? WHERE id = ?",
                        (node_id, eid),
                    )
                except Exception as e:
                    logger.warning("Update failed for %s id=%s: %s", table, eid, e)
                    stats["failed"] += 1
    if not dry_run and rows:
        database._commit()


def _post_check(database: CodeDatabase) -> Dict[str, int]:
    """Return counts of rows with NULL or empty cst_node_id per table."""
    result = {}
    for table in ("classes", "functions", "methods"):
        row = database._fetchone(
            f"""
            SELECT COUNT(*) AS c FROM {table}
            WHERE cst_node_id IS NULL OR trim(cst_node_id) = ''
            """
        )
        result[table] = row["c"] if row else 0
    return result


def run_backfill(
    database: CodeDatabase,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Run backfill for classes, functions, and methods.

    Returns dict with keys: processed, mapped, generated, failed, post_check.
    """
    stats: Dict[str, int] = {
        "processed": 0,
        "mapped": 0,
        "generated": 0,
        "failed": 0,
    }
    _backfill_table(
        database,
        table="classes",
        id_column="id",
        file_id_column="file_id",
        line_column="line",
        end_line_column="end_line",
        name_column="name",
        entity_kind="class",
        dry_run=dry_run,
        stats=stats,
    )
    _backfill_table(
        database,
        table="functions",
        id_column="id",
        file_id_column="file_id",
        line_column="line",
        end_line_column="end_line",
        name_column="name",
        entity_kind="function",
        dry_run=dry_run,
        stats=stats,
    )
    _backfill_table(
        database,
        table="methods",
        id_column="id",
        file_id_column="file_id",
        line_column="line",
        end_line_column="end_line",
        name_column="name",
        entity_kind="method",
        dry_run=dry_run,
        stats=stats,
    )
    post_check = _post_check(database)
    return {"stats": stats, "post_check": post_check}


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill cst_node_id (UUID4) for classes, functions, methods."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to config.json",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override database path (else from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Only report counters, do not write (default: True)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to database (disables dry-run)",
    )
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    db_path: Optional[Path] = args.db_path
    if db_path is None:
        if not args.config.exists():
            logger.error("Config file not found: %s", args.config)
            return 1
        import json

        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
        ai_editor_config = config.get("ai_editor", {})
        db_path = Path(ai_editor_config.get("db_path", "data/ai_editor.db"))

    if db_path is None or not db_path.exists():
        logger.error("Database file not found: %s", db_path)
        return 1

    logger.info("Using database: %s", db_path)
    logger.info("Mode: %s", "dry-run (no writes)" if args.dry_run else "APPLY")

    driver_config = create_driver_config_for_worker(db_path, "sqlite_proxy")
    database = CodeDatabase(driver_config)

    # Precondition: step 01 must have added nullable cst_node_id columns
    missing = _missing_cst_node_id_columns(database)
    if missing:
        logger.error(
            "Missing cst_node_id column in: %s. Apply step 01 (schema nullable) first.",
            ", ".join(missing),
        )
        return 1

    result = run_backfill(database, dry_run=args.dry_run)

    stats = result["stats"]
    post_check = result["post_check"]

    logger.info(
        "Backfill summary: processed=%d mapped=%d generated=%d failed=%d",
        stats["processed"],
        stats["mapped"],
        stats["generated"],
        stats["failed"],
    )
    logger.info(
        "Post-check (NULL/empty cst_node_id): classes=%d functions=%d methods=%d",
        post_check["classes"],
        post_check["functions"],
        post_check["methods"],
    )

    if post_check["classes"] + post_check["functions"] + post_check["methods"] > 0:
        if args.dry_run:
            logger.info(
                "Run with --apply to fill NULLs; then re-run to confirm post-check."
            )
        else:
            logger.warning("Some rows still have NULL/empty cst_node_id after run.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
