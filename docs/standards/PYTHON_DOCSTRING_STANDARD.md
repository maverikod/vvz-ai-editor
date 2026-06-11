<!--
Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
-->

# Python docstring and type-hint standard

Machine-enforced rules for Python modules edited through CST save paths (`cst_save_tree`, `cst_apply_buffer`, `compose_cst_module`, and related validation). Implementation: `code_analysis/core/cst_module/docstring_validator.py` (`validate_module_docstrings`).

Related: [PROJECT_RULES.md](../PROJECT_RULES.md) (**CR-009**, **CR-012**), [AI_TOOL_USAGE_RULES.md](../AI_TOOL_USAGE_RULES.md) §8, [AGENT_CONTEXT_RULES.md](AGENT_CONTEXT_RULES.md) §2.11.

---

## 1. Scope

| Applies to | Does not replace |
|------------|------------------|
| Python `.py` files validated on CST write | `black` / `flake8` / `mypy` (**CR-007**) |
| Module, class, and function/method docstrings | Sphinx/reST build pipelines |
| Parameter and return documentation in docstrings | Google-style optional sections not listed below |

After changing `docstring_validator.py`, **restart the code-analysis daemon** so running workers load the new module.

---

## 2. File (module) docstring

**Required** as the first statement in the file (AST module docstring).

Must be non-empty. Recommended shape:

```python
"""
Short module purpose.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

**CR-012:** production files in this repo use `HEADER_AUTHOR` / `HEADER_EMAIL` from [PROJECT_RULES.md](../PROJECT_RULES.md).

---

## 3. Class docstring

**Required** for every `class` definition.

### 3.1 What counts as a “class attribute” for validation

The validator collects names from the class body:

| Source | Example |
|--------|---------|
| Class-level assignment | `DEFAULT = 1` |
| Annotated class attribute | `limit: int = 10` |
| `@property` method name | `label` from `def label(self) -> str:` |
| `__init__` instance assignment (top-level statements only) | `self.width = width`, `self.color: str = "red"` |

Names assigned only inside other methods (not `__init__`) are **not** required in the class docstring.

Regular methods (non-property) are **not** listed under Attributes; they have their own method docstrings (§4).

### 3.2 Documenting attributes

When at least one attribute name is collected, the class docstring must mention **each** name using one of these patterns (case-insensitive, `re.DOTALL` for section forms):

| Pattern | Example |
|---------|---------|
| `:attr name` / `:attribute name` | `:attr width` |
| `Attributes:` … `name` | See template below |
| `Properties:` … `name` | For `@property` names |
| Word boundary + name + `:` | `width: Outer width in px.` |
| Word boundary + name + `(` | Rare; `name(` |

**Recommended** (matches [AI_TOOL_USAGE_RULES.md](../AI_TOOL_USAGE_RULES.md) and passes all patterns reliably):

```python
class Box:
    """Axis-aligned box.

    Attributes:
        width: Outer width.
        height: Outer height.
        label: Human-readable label (@property).
    """

    width: float
    height: float

    def __init__(self, width: float, height: float) -> None:
        """Create a box."""
        self.width = width
        self.height = height

    @property
    def label(self) -> str:
        """Display label."""
        return f"{self.width}x{self.height}"
```

Use the **same identifier** as in code (`label`, not “Label text” only). A line `label: Description` under `Attributes:` is enough for `\blabel\s*:`.

Properties may be documented in `Attributes:` or `Properties:`; both section headers are accepted.

---

## 4. Method and function docstring

**Required** for:

- Every method on a class (including `__init__`, `@property`, staticmethods)
- Every module-level function

Also validated on the same nodes when encountered via `ast.walk` (duplicate messages for nested functions can appear in error lists; fix the underlying docstring once).

### 4.1 Type hints (signature)

| Rule | Exception |
|------|-----------|
| Every parameter except `self` / `cls` has an annotation | — |
| Return annotation present | `__init__` still needs `-> None` if the validator runs on it |

### 4.2 Parameter documentation

For each parameter (except `self` / `cls`), the docstring must match one of:

| Pattern | Example |
|---------|---------|
| `:param name` / `:parameter name` | `:param width` |
| `Args:` … `name` | Google-style block |
| `Parameters:` … `name` | |
| `\bname\s*:` | `width: Outer width.` |
| `\bname\s*\(` | |

### 4.3 Return documentation

Required for any function/method that has a **return annotation**, except **`__init__`** (return section not checked).

Accepted patterns: `:return`, `:returns`, `Returns:`, `Return:` (case-insensitive).

```python
def area(self) -> float:
    """Compute area.

    Returns:
        Area in square units.
    """
    return self.width * self.height
```

---

## 5. Enforcement and failures

Validation runs from `code_analysis/core/cst_module/validation.py` when CST writes request docstring checks.

Typical error prefixes:

- `File-level docstring is missing or empty`
- `Class 'Name' (line N) is missing docstring`
- `Class 'Name' (line N) docstring is missing attribute descriptions: attr1, attr2`
- `Method Context.name (line N) is missing docstring`
- `Method … is missing type hints for parameters: …`
- `Method … is missing return type hint`
- `Method … docstring is missing parameter descriptions: …`
- `Method … docstring is missing return value description`

Fix the docstring or signature, then retry the save.

---

## 6. Checklist before `cst_save_tree`

- [ ] Module docstring at top of file
- [ ] Every class has a docstring; `Attributes:` lists all class attrs, `__init__` `self.*`, and `@property` names
- [ ] Every method/function has a docstring, full parameter annotations, return annotation, documented parameters, and `Returns:` when not `__init__`
- [ ] **black**, **flake8**, **mypy** clean on touched paths (**CR-007**)

---

## 7. Tests

Regression tests: `tests/test_docstring_validator.py`.
