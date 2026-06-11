"""
CST module tools (package).

This package contains the implementation previously located in `cst_module_tools.py`.
The legacy module remains as a compatibility shim.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ..exceptions import CSTModulePatchError, DocstringValidationError
from .models import BlockInfo, ReplaceOp, InsertOp, CreateOp, Selector
from .blocks import list_cst_blocks, list_file_structure
from .patcher import apply_replace_ops
from .patcher_insert import apply_insert_ops
from .patcher_create import apply_create_ops
from .docstring_validator import validate_module_docstrings
from .utils import (
    compile_module,
    move_module_imports_to_top,
    unified_diff,
    write_with_backup,
)

__all__ = [
    "CSTModulePatchError",
    "DocstringValidationError",
    "Selector",
    "ReplaceOp",
    "InsertOp",
    "CreateOp",
    "BlockInfo",
    "list_cst_blocks",
    "list_file_structure",
    "apply_replace_ops",
    "apply_insert_ops",
    "apply_create_ops",
    "validate_module_docstrings",
    "move_module_imports_to_top",
    "compile_module",
    "unified_diff",
    "write_with_backup",
]
