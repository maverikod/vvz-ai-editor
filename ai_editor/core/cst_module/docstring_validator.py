"""
Docstring validator for CST modules.

Validates docstrings for files, classes, and methods according to project standards.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import re
from typing import List, Optional, Tuple


def validate_module_docstrings(source: str) -> Tuple[bool, Optional[str], List[str]]:
    """
    Validate docstrings in a Python module.

    Checks:
    1. File-level docstring exists
    2. All classes have docstrings with attribute descriptions
    3. All methods have docstrings with parameter descriptions
    4. Method signatures have type hints for parameters and return type

    Args:
        source: Python source code

    Returns:
        Tuple of (is_valid, error_message, list_of_errors)
    """
    errors: List[str] = []

    try:
        tree = ast.parse(source, filename="<module>")
    except SyntaxError as e:
        return (
            False,
            f"Syntax error in module: {str(e)}",
            [f"Syntax error: {str(e)}"],
        )

    # 1. Check file-level docstring
    file_docstring = ast.get_docstring(tree)
    if not file_docstring or not file_docstring.strip():
        errors.append("File-level docstring is missing or empty")

    # 2. Check classes (methods validated inside each class; ast.walk would
    #    revisit nested FunctionDef nodes and duplicate method validation)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        class_docstring = ast.get_docstring(node)
        if not class_docstring or not class_docstring.strip():
            errors.append(
                f"Class '{node.name}' (line {node.lineno}) is missing docstring"
            )
        else:
            class_attr_errors = _validate_class_docstring(node)
            errors.extend(class_attr_errors)

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_errors = _validate_method_docstring(
                        item, node.name, node.lineno
                    )
                    errors.extend(method_errors)

    # 3. Top-level functions only (not class methods)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_errors = _validate_method_docstring(node, None, node.lineno)
            errors.extend(method_errors)

    if errors:
        error_msg = "Docstring validation failed:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        return (False, error_msg, errors)

    return (True, None, [])


def _validate_method_docstring(
    method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: Optional[str],
    class_line: Optional[int],
) -> List[str]:
    """
    Validate method docstring.

    Checks:
    1. Docstring exists
    2. All parameters are documented in docstring
    3. Return value is documented (if method has return type hint)
    4. Method signature has type hints for all parameters
    5. Method signature has return type hint

    Args:
        method_node: AST node of method/function
        class_name: Name of parent class (None for top-level functions)
        class_line: Line number of parent class

    Returns:
        List of error messages
    """
    errors: List[str] = []

    method_name = method_node.name
    method_line = method_node.lineno
    context = f"{class_name}.{method_name}" if class_name else method_name
    location = f"{context} (line {method_line})"

    # 1. Check docstring exists
    docstring = ast.get_docstring(method_node)
    if not docstring or not docstring.strip():
        errors.append(f"Method {location} is missing docstring")
        return errors  # Can't check further without docstring

    # 2. Extract method parameters (excluding self/cls always)
    args = method_node.args
    param_names = []
    for arg in args.args:
        param_name = arg.arg
        if param_name in ("self", "cls"):
            continue
        param_names.append(param_name)

    # 3. Check type hints for parameters (skip self/cls always)
    missing_type_hints = []
    for arg in args.args:
        param_name = arg.arg
        if param_name in ("self", "cls"):
            continue
        if not arg.annotation:
            missing_type_hints.append(param_name)

    if missing_type_hints:
        errors.append(
            f"Method {location} is missing type hints for parameters: {', '.join(missing_type_hints)}"
        )

    # 4. Check return type hint
    if not method_node.returns:
        errors.append(f"Method {location} is missing return type hint")

    # 5. Check that all parameters are documented in docstring
    missing_params = []
    for param_name in param_names:
        # Check if parameter name appears in docstring
        # Look for patterns like: param_name, :param param_name, Args: ... param_name
        param_patterns = [
            rf":param\s+{re.escape(param_name)}",
            rf":parameter\s+{re.escape(param_name)}",
            rf"Args:.*?{re.escape(param_name)}",
            rf"Parameters:.*?{re.escape(param_name)}",
            rf"\b{re.escape(param_name)}\s*:",
            rf"\b{re.escape(param_name)}\s*\(",
        ]
        found = any(
            re.search(pattern, docstring, re.IGNORECASE | re.DOTALL)
            for pattern in param_patterns
        )
        if not found:
            missing_params.append(param_name)

    if missing_params:
        errors.append(
            f"Method {location} docstring is missing parameter descriptions: {', '.join(missing_params)}"
        )

    # 6. Check return value documentation (if method has return type hint)
    # Skip __init__ methods as they always return None
    if method_node.returns and method_node.name != "__init__":
        return_patterns = [
            r":return",
            r":returns",
            r"Returns:",
            r"Return:",
        ]
        found_return = any(
            re.search(pattern, docstring, re.IGNORECASE) for pattern in return_patterns
        )
        if not found_return:
            errors.append(
                f"Method {location} docstring is missing return value description"
            )

    return errors


def _collect_init_instance_attributes(
    init_node: ast.FunctionDef | ast.AsyncFunctionDef,
    attributes: set[str],
) -> None:
    """Add ``self.attr`` names assigned at top level in ``__init__``."""
    for stmt in init_node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    attributes.add(target.attr)
        elif isinstance(stmt, ast.AnnAssign):
            if (
                isinstance(stmt.target, ast.Attribute)
                and isinstance(stmt.target.value, ast.Name)
                and stmt.target.value.id == "self"
            ):
                attributes.add(stmt.target.attr)


def _extract_class_attributes(class_node: ast.ClassDef) -> List[str]:
    """
    Extract all class attributes from AST node.

    Includes:
    - Class variables (assignments at class level)
    - Annotated class attributes (with type hints)
    - Properties (methods with @property decorator)
    - Instance variables declared in __init__ (self.attr = value)

    Args:
        class_node: AST node of class

    Returns:
        List of attribute names
    """
    attributes: set[str] = set()

    for item in class_node.body:
        # 1. Class variables: assignments at class level
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    attributes.add(target.id)
                elif isinstance(target, ast.Attribute):
                    # Handle cases like ClassName.attr = value
                    if isinstance(target.value, ast.Name):
                        attributes.add(target.attr)

        # 2. Annotated class attributes: attr: Type = value or attr: Type
        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name):
                attributes.add(item.target.id)

        # 3. Methods: __init__ instance attrs and @property names
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name == "__init__":
                _collect_init_instance_attributes(item, attributes)
            for decorator in item.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "property":
                    attributes.add(item.name)

    return sorted(list(attributes))


def _validate_class_docstring(class_node: ast.ClassDef) -> List[str]:
    """
    Validate class docstring contains descriptions of all attributes.

    Checks:
    1. Class docstring exists (already checked in main function)
    2. All class attributes are documented in docstring

    Args:
        class_node: AST node of class

    Returns:
        List of error messages
    """
    errors: List[str] = []

    class_name = class_node.name
    class_line = class_node.lineno
    location = f"Class '{class_name}' (line {class_line})"

    # Get class docstring
    docstring = ast.get_docstring(class_node)
    if not docstring or not docstring.strip():
        # Already reported in main function
        return errors

    # Extract all class attributes
    attributes = _extract_class_attributes(class_node)

    # Skip if no attributes found
    if not attributes:
        return errors

    # Check that all attributes are documented in docstring
    missing_attrs = []
    for attr_name in attributes:
        # Check if attribute name appears in docstring
        # Look for patterns like: attr_name, :attr attr_name, Attributes: ... attr_name
        attr_patterns = [
            rf":attr\s+{re.escape(attr_name)}",
            rf":attribute\s+{re.escape(attr_name)}",
            rf"Attributes:.*?{re.escape(attr_name)}",
            rf"Properties:.*?{re.escape(attr_name)}",
            rf"\b{re.escape(attr_name)}\s*:",
            rf"\b{re.escape(attr_name)}\s*\(",
        ]
        found = any(
            re.search(pattern, docstring, re.IGNORECASE | re.DOTALL)
            for pattern in attr_patterns
        )
        if not found:
            missing_attrs.append(attr_name)

    if missing_attrs:
        errors.append(
            f"{location} docstring is missing attribute descriptions: {', '.join(missing_attrs)}"
        )

    return errors
