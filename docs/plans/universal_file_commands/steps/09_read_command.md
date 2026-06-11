# Step 09: universal_file_read_command.py — документирование Python-маршрута

Status: TODO  
Depends on: Step 05  
File: `code_analysis/commands/universal_file_read_command.py` (304 строки)

## Текущее состояние (factual)

### Схема (строки 93—133)

```python
"required": ["project_id", "file_path"],
"additionalProperties": False,
```

Параметры: `project_id`, `file_path`, `start_line` (optional), `end_line` (optional).

### Маршрутизация

| handler_id | Куда маршрутизируется |
|------------|-------------------|
| `text` | `read_lines_range_ok(absolute_path, sl, el)` |
| `json` | `JsonFileHandler().read(req)` |
| `yaml` | `YamlFileHandler().read(req)` |
| `python` | `GetFileLinesCommand().execute(...)` |

### Проблема

В `descr` и schema description нет явного упоминания что:
- Python-файлы рутируются через `GetFileLinesCommand` (не `TextFileHandler`)
- `start_line`/`end_line` игнорируются для JSON/YAML
- возвращаемые поля различаются по handler_id

## Что сделать

### Изменение 1: Дополнить description в schema

Найти `"description"` внутри `"properties": {"file_path": {...}}` (строка ~115) и добавить:

```python
"description": (
    "Single path relative to project root (literal; no ``*?[]`` globs — "
    "use ``list_project_files`` with ``file_pattern`` to discover paths). "
    "Handler routing by extension: "
    ".md/.txt/.rst/.adoc/.log → text (lines); "
    ".json → JSON tree; .yaml/.yml → YAML tree; "
    ".py/.pyi/.pyw → get_file_lines (line view, CST-safe). "
    "start_line/end_line are ignored for JSON and YAML handlers."
),
```

### Изменение 2: Добавить описание полей ответа в schema

Добавить в description квалификацию полей ответа:

```text
text/python: {handler_id, operation, file_path, project_id, start_line, end_line, lines, total_lines}
json:        {handler_id, operation, file_path, project_id, data (parsed object), size}
yaml:        {handler_id, operation, file_path, project_id, data (parsed object), size}
```

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/commands/universal_file_read_command.py start_line=85 end_line=140
```

## Инструменты MCP

```python
# 1. Загрузить
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_read_command.py"
)

# 2. Найти get_schema
cst_find_node(tree_id=..., search_type="xpath",
              query="function[name='get_schema']")

# 3. Найти description file_path property (внутри get_schema)
# и обновить через cst_modify_tree

# 4. Сохранить
cst_save_tree(tree_id=..., project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
              file_path="code_analysis/commands/universal_file_read_command.py")
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/commands/universal_file_read_command.py")
```

## Проверка выполнения

- [ ] `file_path` description упоминает все четыре handler_id
- [ ] description говорит что start_line/end_line игнорируются для JSON/YAML
- [ ] поля ответа описаны для каждого handler
- [ ] `lint_code` вернул 0 ошибок