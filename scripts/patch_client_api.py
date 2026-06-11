"""Patch add_class/add_method/add_function to accept and write cst_node_id into SQL."""
import sys

path = '/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/database_client/client_api_files.py'
content = open(path).read()
before = content

# --- add_class: add cst_node_id param and include in SQL ---
content = content.replace(
    'def add_class(\n'
    '        self,\n'
    '        file_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        docstring: Optional[str],\n'
    '        bases: List[str],\n'
    '        end_line: Optional[int] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace class. Returns class id."""\n'
    '        bases_json = json.dumps(bases)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO classes (file_id, name, line, end_line, docstring, bases) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?)",\n'
    '            (file_id, name, line, end_line, docstring, bases_json),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
    'def add_class(\n'
    '        self,\n'
    '        file_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        docstring: Optional[str],\n'
    '        bases: List[str],\n'
    '        end_line: Optional[int] = None,\n'
    '        cst_node_id: Optional[str] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace class. Returns class id."""\n'
    '        bases_json = json.dumps(bases)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO classes (file_id, name, line, end_line, cst_node_id, docstring, bases) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?)",\n'
    '            (file_id, name, line, end_line, cst_node_id, docstring, bases_json),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
)

# --- add_method: add cst_node_id param and include in SQL ---
content = content.replace(
    'def add_method(\n'
    '        self,\n'
    '        class_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        args: List[str],\n'
    '        docstring: Optional[str],\n'
    '        complexity: Optional[int] = None,\n'
    '        end_line: Optional[int] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace method. Returns method id."""\n'
    '        args_json = json.dumps(args)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO methods (class_id, name, line, end_line, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?)",\n'
    '            (class_id, name, line, end_line, args_json, docstring),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
    'def add_method(\n'
    '        self,\n'
    '        class_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        args: List[str],\n'
    '        docstring: Optional[str],\n'
    '        complexity: Optional[int] = None,\n'
    '        end_line: Optional[int] = None,\n'
    '        cst_node_id: Optional[str] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace method. Returns method id."""\n'
    '        args_json = json.dumps(args)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO methods (class_id, name, line, end_line, cst_node_id, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?)",\n'
    '            (class_id, name, line, end_line, cst_node_id, args_json, docstring),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
)

# --- add_function: add cst_node_id param and include in SQL ---
content = content.replace(
    'def add_function(\n'
    '        self,\n'
    '        file_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        args: List[str],\n'
    '        docstring: Optional[str],\n'
    '        complexity: Optional[int] = None,\n'
    '        end_line: Optional[int] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace function. Returns function id."""\n'
    '        args_json = json.dumps(args)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO functions (file_id, name, line, end_line, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?)",\n'
    '            (file_id, name, line, end_line, args_json, docstring),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
    'def add_function(\n'
    '        self,\n'
    '        file_id: int,\n'
    '        name: str,\n'
    '        line: int,\n'
    '        args: List[str],\n'
    '        docstring: Optional[str],\n'
    '        complexity: Optional[int] = None,\n'
    '        end_line: Optional[int] = None,\n'
    '        cst_node_id: Optional[str] = None,\n'
    '    ) -> int:\n'
    '        """Add or replace function. Returns function id."""\n'
    '        args_json = json.dumps(args)\n'
    '        result = self.execute(\n'
    '            "INSERT OR REPLACE INTO functions (file_id, name, line, end_line, cst_node_id, args, docstring) "\n'
    '            "VALUES (?, ?, ?, ?, ?, ?, ?)",\n'
    '            (file_id, name, line, end_line, cst_node_id, args_json, docstring),\n'
    '        )\n'
    '        return result.get("lastrowid", 0) or 0\n',
)

if content == before:
    print('ERROR: nothing changed — string mismatch, check indentation/content')
    sys.exit(1)

changes = sum([
    'cst_node_id: Optional[str] = None' in content,
    'cst_node_id, docstring, bases_json' in content,
    'cst_node_id, args_json, docstring' in content,
])
print(f'Changes applied: {changes}/3 blocks patched')
if changes < 3:
    print('WARNING: not all blocks were patched')
    sys.exit(1)

open(path, 'w').write(content)
print('Saved OK')
