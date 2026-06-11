# Step 13: Tests + comprehensive_analysis

Status: TODO  
Depends on: Steps 09–12  
Test files:
- `tests/test_universal_file_read_command.py`
- `tests/test_universal_file_save_command.py`
- `tests/test_universal_file_replace_command.py`
- `tests/test_universal_file_delete_command.py`
- `tests/mcp/test_universal_file_mcp_regression.py`

## Прочитайте перед написанием

```text
read_project_text_file tests/test_universal_file_save_command.py start_line=1 end_line=60
read_project_text_file tests/test_universal_file_replace_command.py start_line=1 end_line=60
read_project_text_file tests/test_universal_file_delete_command.py start_line=1 end_line=60
read_project_text_file tests/mcp/test_universal_file_mcp_regression.py start_line=1 end_line=80
```

Также прочитайте тесты из `old_code/` (если есть более полная версия).

## Тесты под каждый Step

### Step 03 (base.py)

```python
from code_analysis.core.file_handlers.base import STANDARD_HANDLER_ERROR_CODES

def test_backup_required_in_standard_codes():
    assert "BACKUP_REQUIRED" in STANDARD_HANDLER_ERROR_CODES

def test_update_file_data_error_in_standard_codes():
    assert "UPDATE_FILE_DATA_ERROR" in STANDARD_HANDLER_ERROR_CODES
```

### Step 04 (registry.py)

```python
from code_analysis.core.file_handlers.registry import resolve_handler, RegistryError

def test_log_resolves_to_text():
    assert resolve_handler("file.log", "read") == "text"

def test_toml_raises():
    with pytest.raises(RegistryError) as exc:
        resolve_handler("config.toml", "read")
    assert exc.value.code == "UNSUPPORTED_FILE_EXTENSION"
    assert "handler_id" in exc.value.details

def test_unknown_suffix_raises():
    with pytest.raises(RegistryError) as exc:
        resolve_handler("file.xyz", "save")
    assert "handler_id" in exc.value.details
```

### Step 05 (text_handler.py)

```python
from code_analysis.core.file_handlers.text_handler import TEXT_SUFFIXES

def test_log_in_text_suffixes():
    assert ".log" in TEXT_SUFFIXES
```

### Steps 06–08 (backup+rollback)

Тестировать через существующие файлы или дополнить:

```python
# test_universal_file_save_command.py — добавить
def test_save_response_includes_backup_uuid(tmp_path, monkeypatch):
    """SuccessResult.data must include backup_uuid when backup was created."""
    # setup: создать тестовый .md-файл и project
    ...
    result = await cmd.execute(project_id=..., file_path="readme.md",
                               content="new content")
    assert isinstance(result, SuccessResult)
    assert "backup_uuid" in result.data
    assert result.data["backup_uuid"] is not None

def test_save_backup_required_abort(tmp_path, monkeypatch):
    """If BackupManager.create_backup() fails, save must abort with BACKUP_REQUIRED."""
    monkeypatch.setattr(BackupManager, "create_backup", lambda *a, **kw: None)
    result = await cmd.execute(...)
    assert isinstance(result, ErrorResult)
    assert result.code == "BACKUP_REQUIRED"

# test_universal_file_replace_command.py — аналогично
def test_replace_response_includes_backup_uuid(...):
    ...

def test_replace_backup_required_abort(...):
    ...

# test_universal_file_delete_command.py — аналогично
def test_delete_file_mode_no_persist(tmp_path, ...):
    """delete_mode=file must not call persist_plain_text_file_metadata."""
    ...

def test_delete_range_mode_updates_metadata(tmp_path, ...):
    """delete_mode=range must persist metadata after write."""
    ...
```

### Steps 09–12 (schema/description)

```python
# Проверить schema additionalProperties=False
def test_read_schema_additional_properties_false():
    schema = UniversalFileReadCommand.get_schema()
    assert schema["additionalProperties"] is False

def test_save_schema_additional_properties_false():
    schema = UniversalFileSaveCommand.get_schema()
    assert schema["additionalProperties"] is False

def test_replace_schema_additional_properties_false():
    schema = UniversalFileReplaceCommand.get_schema()
    assert schema["additionalProperties"] is False

def test_delete_schema_additional_properties_false():
    schema = UniversalFileDeleteCommand.get_schema()
    assert schema["additionalProperties"] is False

# Проверить что .log упомянут в read-schema
def test_read_schema_mentions_log():
    schema = UniversalFileReadCommand.get_schema()
    desc = schema["properties"]["file_path"]["description"]
    assert ".log" in desc
```

## Прогон тестов

```python
# Через run_project_module (MCP)
run_project_module(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    module="pytest",
    args=["tests/test_universal_file_save_command.py",
          "tests/test_universal_file_replace_command.py",
          "tests/test_universal_file_delete_command.py",
          "tests/test_universal_file_read_command.py",
          "-v", "--tb=short"]
)
```

## comprehensive_analysis

```python
comprehensive_analysis(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    # file_path=None — весь проект
    check_placeholders=True,
    check_stubs=True,
    check_empty_methods=True,
    check_imports=True,
    check_long_files=True,
    check_duplicates=True,
    check_flake8=True,
    check_mypy=True,
    use_queue=True
)
# Затем queue_get_job_status до completed
```

Проверить что `summary.total_flake8_errors == 0` и `summary.total_mypy_errors == 0`
по изменённым файлам.

## Проверка выполнения

- [ ] Тесты Step 03: `BACKUP_REQUIRED`, `UPDATE_FILE_DATA_ERROR` проходят
- [ ] Тесты Step 04: `.log` резолвит, `.toml` бросает с handler_id в details
- [ ] Тесты Step 05: `.log` в `TEXT_SUFFIXES`
- [ ] Тесты Steps 06–08: backup_uuid в data, BACKUP_REQUIRED abort
- [ ] Тесты Steps 09–12: additionalProperties=False во всех схемах
- [ ] comprehensive_analysis: flake8=0 mypy=0 по изменённым файлам
- [ ] INDEX.md: все шаги отмечены ✅ DONE