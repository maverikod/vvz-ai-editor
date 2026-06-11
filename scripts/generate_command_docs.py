"""
Generate per-command documentation from command classes.

Reads get_schema() and metadata() from each MCP command and writes
docs/commands/<block>/<command_name>.md with: purpose, arguments,
return format, examples (correct and incorrect).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import importlib
import json
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
DOCS_COMMANDS = ROOT / "docs" / "commands"

# Command name -> (module path, class name, block)
COMMAND_MAP = [
    ("get_ast", "ai_editor.commands.ast.get_ast", "GetASTMCPCommand", "ast"),
    (
        "search_ast_nodes",
        "ai_editor.commands.ast.search_nodes",
        "SearchASTNodesMCPCommand",
        "ast",
    ),
    (
        "ast_statistics",
        "ai_editor.commands.ast.statistics",
        "ASTStatisticsMCPCommand",
        "ast",
    ),
    (
        "list_project_files",
        "ai_editor.commands.ast.list_files",
        "ListProjectFilesMCPCommand",
        "ast",
    ),
    (
        "get_code_entity_info",
        "ai_editor.commands.ast.entity_info",
        "GetCodeEntityInfoMCPCommand",
        "ast",
    ),
    (
        "list_code_entities",
        "ai_editor.commands.ast.list_entities",
        "ListCodeEntitiesMCPCommand",
        "ast",
    ),
    (
        "get_imports",
        "ai_editor.commands.ast.imports",
        "GetImportsMCPCommand",
        "ast",
    ),
    (
        "find_dependencies",
        "ai_editor.commands.ast.dependencies",
        "FindDependenciesMCPCommand",
        "ast",
    ),
    (
        "get_class_hierarchy",
        "ai_editor.commands.ast.hierarchy",
        "GetClassHierarchyMCPCommand",
        "ast",
    ),
    ("find_usages", "ai_editor.commands.ast.usages", "FindUsagesMCPCommand", "ast"),
    (
        "export_graph",
        "ai_editor.commands.ast.graph",
        "ExportGraphMCPCommand",
        "ast",
    ),
    (
        "list_backup_files",
        "ai_editor.commands.backup_mcp_commands",
        "ListBackupFilesMCPCommand",
        "backup",
    ),
    (
        "list_backup_versions",
        "ai_editor.commands.backup_mcp_commands",
        "ListBackupVersionsMCPCommand",
        "backup",
    ),
    (
        "restore_backup_file",
        "ai_editor.commands.backup_mcp_commands",
        "RestoreBackupFileMCPCommand",
        "backup",
    ),
    (
        "delete_backup",
        "ai_editor.commands.backup_mcp_commands",
        "DeleteBackupMCPCommand",
        "backup",
    ),
    (
        "clear_all_backups",
        "ai_editor.commands.backup_mcp_commands",
        "ClearAllBackupsMCPCommand",
        "backup",
    ),
    (
        "update_indexes",
        "ai_editor.commands.code_mapper_mcp_command",
        "UpdateIndexesMCPCommand",
        "code_mapper",
    ),
    (
        "list_long_files",
        "ai_editor.commands.code_mapper_mcp_commands",
        "ListLongFilesMCPCommand",
        "code_mapper",
    ),
    (
        "list_errors_by_category",
        "ai_editor.commands.code_mapper_mcp_commands",
        "ListErrorsByCategoryMCPCommand",
        "code_mapper",
    ),
    (
        "format_code",
        "ai_editor.commands.code_quality_commands",
        "FormatCodeCommand",
        "code_quality",
    ),
    (
        "lint_code",
        "ai_editor.commands.code_quality_commands",
        "LintCodeCommand",
        "code_quality",
    ),
    (
        "type_check_code",
        "ai_editor.commands.code_quality_commands",
        "TypeCheckCodeCommand",
        "code_quality",
    ),
    (
        "check_vectors",
        "ai_editor.commands.check_vectors_command",
        "CheckVectorsCommand",
        "misc",
    ),
    (
        "get_worker_status",
        "ai_editor.commands.worker_status_mcp_commands",
        "GetWorkerStatusMCPCommand",
        "worker_status",
    ),
    (
        "get_database_status",
        "ai_editor.commands.worker_status_mcp_commands",
        "GetDatabaseStatusMCPCommand",
        "worker_status",
    ),
    (
        "start_worker",
        "ai_editor.commands.worker_management_mcp_commands",
        "StartWorkerMCPCommand",
        "worker_management",
    ),
    (
        "stop_worker",
        "ai_editor.commands.worker_management_mcp_commands",
        "StopWorkerMCPCommand",
        "worker_management",
    ),
    (
        "view_worker_logs",
        "ai_editor.commands.log_viewer_mcp_commands",
        "ViewWorkerLogsMCPCommand",
        "log_viewer",
    ),
    (
        "list_worker_logs",
        "ai_editor.commands.log_viewer_mcp_commands",
        "ListWorkerLogsMCPCommand",
        "log_viewer",
    ),
    (
        "rotate_worker_logs",
        "ai_editor.commands.log_viewer_mcp_commands",
        "RotateWorkerLogsMCPCommand",
        "log_viewer",
    ),
    (
        "analyze_timing_bottlenecks",
        "ai_editor.commands.log_viewer_mcp_commands",
        "AnalyzeTimingBottlenecksMCPCommand",
        "log_viewer",
    ),
    (
        "get_database_corruption_status",
        "ai_editor.commands.database_integrity_mcp_commands",
        "GetDatabaseCorruptionStatusMCPCommand",
        "database_integrity",
    ),
    (
        "backup_database",
        "ai_editor.commands.database_integrity_mcp_commands",
        "BackupDatabaseMCPCommand",
        "database_integrity",
    ),
    (
        "repair_sqlite_database",
        "ai_editor.commands.database_integrity_mcp_commands",
        "RepairSQLiteDatabaseMCPCommand",
        "database_integrity",
    ),
    (
        "restore_database",
        "ai_editor.commands.database_restore_mcp_commands",
        "RestoreDatabaseFromConfigMCPCommand",
        "database_restore",
    ),
    (
        "cleanup_deleted_files",
        "ai_editor.commands.file_management_mcp_commands",
        "CleanupDeletedFilesMCPCommand",
        "file_management",
    ),
    (
        "unmark_deleted_file",
        "ai_editor.commands.file_management_mcp_commands",
        "UnmarkDeletedFileMCPCommand",
        "file_management",
    ),
    (
        "collapse_versions",
        "ai_editor.commands.file_management_mcp_commands",
        "CollapseVersionsMCPCommand",
        "file_management",
    ),
    (
        "repair_database",
        "ai_editor.commands.file_management_mcp_commands",
        "RepairDatabaseMCPCommand",
        "file_management",
    ),
    (
        "change_project_id",
        "ai_editor.commands.project_management_mcp_commands",
        "ChangeProjectIdMCPCommand",
        "project_management",
    ),
    (
        "create_project",
        "ai_editor.commands.project_management_mcp_commands",
        "CreateProjectMCPCommand",
        "project_management",
    ),
    (
        "project_set_mark_del",
        "ai_editor.commands.project_management_mcp_commands",
        "DeleteProjectMCPCommand",
        "project_management",
    ),
    (
        "delete_unwatched_projects",
        "ai_editor.commands.project_management_mcp_commands",
        "DeleteUnwatchedProjectsMCPCommand",
        "project_management",
    ),
    (
        "list_projects",
        "ai_editor.commands.project_management_mcp_commands",
        "ListProjectsMCPCommand",
        "project_management",
    ),
    (
        "run_project_script",
        "ai_editor.commands.run_project_script_command",
        "RunProjectScriptCommand",
        "project_management",
    ),
    (
        "run_project_module",
        "ai_editor.commands.run_project_module_command",
        "RunProjectModuleCommand",
        "project_management",
    ),
    (
        "start_repair_worker",
        "ai_editor.commands.repair_worker_mcp_commands",
        "StartRepairWorkerMCPCommand",
        "repair_worker",
    ),
    (
        "stop_repair_worker",
        "ai_editor.commands.repair_worker_mcp_commands",
        "StopRepairWorkerMCPCommand",
        "repair_worker",
    ),
    (
        "repair_worker_status",
        "ai_editor.commands.repair_worker_mcp_commands",
        "RepairWorkerStatusMCPCommand",
        "repair_worker",
    ),
    (
        "fulltext_search",
        "ai_editor.commands.search_mcp_commands",
        "FulltextSearchMCPCommand",
        "search",
    ),
    (
        "list_class_methods",
        "ai_editor.commands.search_mcp_commands",
        "ListClassMethodsMCPCommand",
        "search",
    ),
    (
        "find_classes",
        "ai_editor.commands.search_mcp_commands",
        "FindClassesMCPCommand",
        "search",
    ),
    (
        "rebuild_faiss",
        "ai_editor.commands.vector_commands.rebuild_faiss",
        "RebuildFaissCommand",
        "vector",
    ),
    (
        "revectorize",
        "ai_editor.commands.vector_commands.revectorize",
        "RevectorizeCommand",
        "vector",
    ),
    (
        "split_class",
        "ai_editor.commands.refactor_mcp_commands",
        "SplitClassMCPCommand",
        "refactor",
    ),
    (
        "extract_superclass",
        "ai_editor.commands.refactor_mcp_commands",
        "ExtractSuperclassMCPCommand",
        "refactor",
    ),
    (
        "split_file_to_package",
        "ai_editor.commands.refactor_mcp_commands",
        "SplitFileToPackageMCPCommand",
        "refactor",
    ),
    (
        "analyze_complexity",
        "ai_editor.commands.analyze_complexity_mcp",
        "AnalyzeComplexityMCPCommand",
        "analysis",
    ),
    (
        "find_duplicates",
        "ai_editor.commands.find_duplicates_mcp",
        "FindDuplicatesMCPCommand",
        "analysis",
    ),
    (
        "comprehensive_analysis",
        "ai_editor.commands.comprehensive_analysis_mcp",
        "ComprehensiveAnalysisMCPCommand",
        "analysis",
    ),
    (
        "semantic_search",
        "ai_editor.commands.semantic_search_mcp",
        "SemanticSearchMCPCommand",
        "analysis",
    ),
    # CST
    (
        "cst_load_file",
        "ai_editor.commands.cst_load_file_command",
        "CSTLoadFileCommand",
        "cst",
    ),
    (
        "cst_save_tree",
        "ai_editor.commands.cst_save_tree_command",
        "CSTSaveTreeCommand",
        "cst",
    ),
    (
        "cst_reload_tree",
        "ai_editor.commands.cst_reload_tree_command",
        "CSTReloadTreeCommand",
        "cst",
    ),
    (
        "cst_find_node",
        "ai_editor.commands.cst_find_node_command",
        "CSTFindNodeCommand",
        "cst",
    ),
    (
        "cst_get_node_info",
        "ai_editor.commands.cst_get_node_info_command",
        "CSTGetNodeInfoCommand",
        "cst",
    ),
    (
        "cst_get_node_by_range",
        "ai_editor.commands.cst_get_node_by_range_command",
        "CSTGetNodeByRangeCommand",
        "cst",
    ),
    (
        "cst_modify_tree",
        "ai_editor.commands.cst_modify_tree_command",
        "CSTModifyTreeCommand",
        "cst",
    ),
    (
        "cst_create_file",
        "ai_editor.commands.cst_create_file_command",
        "CSTCreateFileCommand",
        "cst",
    ),
    (
        "cst_convert_and_save",
        "ai_editor.commands.cst_convert_and_save_command",
        "CSTConvertAndSaveCommand",
        "cst",
    ),
    (
        "list_cst_blocks",
        "ai_editor.commands.list_cst_blocks_command",
        "ListCSTBlocksCommand",
        "cst",
    ),
    ("query_cst", "ai_editor.commands.query_cst_command", "QueryCSTCommand", "cst"),
]


def _safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default) if obj else default


def _schema_props_table(schema):
    props = _safe_get(schema, "properties") or {}
    required = set(_safe_get(schema, "required") or [])
    rows = []
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        typ = spec.get("type", "")
        desc = spec.get("description", "")
        req = "**Yes**" if name in required else "No"
        default = spec.get("default")
        if default is not None:
            desc = desc + f" Default: `{json.dumps(default)}`."
        rows.append((name, typ, req, desc))
    return rows


def _render_md(name, cls_name, block, schema, meta, source_hint):
    lines = [
        f"# {name}",
        "",
        f"**Command name:** `{name}`  ",
        f"**Class:** `{cls_name}`  ",
        f"**Source:** `{source_hint}`  ",
        f"**Category:** {block}",
        "",
        "Author: Vasiliy Zdanovskiy  ",
        "email: vasilyvz@gmail.com",
        "",
        "---",
        "",
        "## Purpose (Предназначение)",
        "",
    ]
    desc = (
        _safe_get(meta, "detailed_description") or _safe_get(meta, "description") or ""
    )
    if desc:
        lines.append(desc.strip().replace("\n\n", "\n\n").replace("\n", "\n"))
    else:
        lines.append(_safe_get(schema, "description", "No description in schema."))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Arguments (Аргументы)")
    lines.append("")
    lines.append("| Parameter | Type | Required | Description |")
    lines.append("|-----------|------|----------|-------------|")
    for name, typ, req, desc in _schema_props_table(schema):
        desc_esc = desc.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{name}` | {typ} | {req} | {desc_esc[:200]} |")
    lines.append("")
    add_props = _safe_get(schema, "additionalProperties")
    if add_props is False:
        lines.append(
            "**Schema:** `additionalProperties: false` — only the parameters above are accepted."
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Returned data (Возвращаемые данные)")
    lines.append("")
    lines.append(
        "All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`)."
    )
    lines.append("")
    rv = _safe_get(meta, "return_value") or {}
    success_info = _safe_get(rv, "success") or {}
    if isinstance(success_info, dict):
        data_desc = (
            success_info.get("data")
            or success_info.get("example")
            or "See execute() implementation."
        )
        lines.append("### Success")
        lines.append("")
        lines.append("- **Shape:** `SuccessResult` with `data` object.")
        if isinstance(data_desc, dict):
            for k, v in data_desc.items():
                if isinstance(v, str):
                    lines.append(f"- `{k}`: {v}")
                else:
                    lines.append(f"- `{k}`: (see example)")
        lines.append("")
    err_info = _safe_get(rv, "error") or {}
    if isinstance(err_info, dict):
        lines.append("### Error")
        lines.append("")
        lines.append("- **Shape:** `ErrorResult` with `code` and `message`.")
        err_cases = _safe_get(meta, "error_cases") or {}
        if err_cases:
            lines.append(
                "- **Possible codes:** "
                + ", ".join(err_cases.keys())
                + " (and others)."
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Examples")
    lines.append("")
    lines.append("### Correct usage")
    lines.append("")
    examples = _safe_get(meta, "usage_examples") or []
    for i, ex in enumerate(examples[:5] if isinstance(examples, list) else []):
        if not isinstance(ex, dict):
            continue
        desc = ex.get("description") or ex.get("title") or f"Example {i+1}"
        cmd = ex.get("command") or ex.get("params")
        if cmd is None:
            continue
        lines.append(f"**{desc}**")
        lines.append("```json")
        lines.append(json.dumps(cmd, indent=2))
        lines.append("```")
        expl = ex.get("explanation") or ""
        if expl:
            lines.append("")
            lines.append(expl)
        lines.append("")
    if not any(isinstance(ex, dict) and ex.get("command") for ex in (examples or [])):
        lines.append("Use required parameters from the Arguments table above.")
        lines.append("")
    lines.append("### Incorrect usage")
    lines.append("")
    err_cases = _safe_get(meta, "error_cases") or {}
    for code, info in err_cases.items():
        if isinstance(info, dict):
            example = info.get("example") or info.get("description")
            solution = info.get("solution") or info.get("resolution")
            lines.append(f"- **{code}**: {example or code}. {solution or ''}")
            lines.append("")
    required = set(_safe_get(schema, "required") or [])
    if required and not err_cases:
        lines.append(
            "- Missing required parameters → schema validation error or command-specific error (e.g. PROJECT_NOT_FOUND)."
        )
        lines.append("")
    if err_cases:
        lines.append("## Error codes summary")
        lines.append("")
        lines.append("| Code | Description | Action |")
        lines.append("|------|-------------|--------|")
        for code, info in err_cases.items():
            if isinstance(info, dict):
                desc = (info.get("description") or info.get("example") or code)[:60]
                sol = (info.get("solution") or info.get("resolution") or "")[:50]
                lines.append(f"| `{code}` | {desc} | {sol} |")
        lines.append("")
    best = _safe_get(meta, "best_practices")
    if isinstance(best, list) and best:
        lines.append("## Best practices")
        lines.append("")
        for b in best[:8]:
            if isinstance(b, str):
                lines.append(f"- {b}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main():
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    created = 0
    failed = []
    for name, mod_path, cls_name, block in COMMAND_MAP:
        out_dir = DOCS_COMMANDS / block
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{name}.md"
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            schema = cls.get_schema() if hasattr(cls, "get_schema") else {}
            meta = cls.metadata() if hasattr(cls, "metadata") else {}
            source_hint = (
                mod_path.replace(
                    "ai_editor.commands.", "ai_editor/commands/"
                ).replace(".", "/")
                + ".py"
            )
            if "backup_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/backup_mcp_commands.py"
            if "project_management_mcp_commands" in mod_path:
                source_hint = (
                    "ai_editor/commands/project_management_mcp_commands.py"
                )
            if "worker_status_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/worker_status_mcp_commands.py"
            if "file_management_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/file_management_mcp_commands.py"
            if "code_mapper_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/code_mapper_mcp_commands.py"
            if "database_integrity_mcp_commands" in mod_path:
                source_hint = (
                    "ai_editor/commands/database_integrity_mcp_commands.py"
                )
            if "log_viewer_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/log_viewer_mcp_commands.py"
            if "worker_management_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/worker_management_mcp_commands.py"
            if "search_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/search_mcp_commands.py"
            if "refactor_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/refactor_mcp_commands.py"
            if "repair_worker_mcp_commands" in mod_path:
                source_hint = "ai_editor/commands/repair_worker_mcp_commands.py"
            content = _render_md(name, cls_name, block, schema, meta, source_hint)
            out_file.write_text(content, encoding="utf-8")
            created += 1
        except Exception as e:
            failed.append((name, str(e)))
    if failed:
        for name, err in failed:
            print(f"FAILED {name}: {err}", file=sys.stderr)
    print(f"Created {created} command docs. Failed: {len(failed)}.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
