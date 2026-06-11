# 05. Watcher integration

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)
- Следующий шаг: [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- Наблюдения watcher: [../01-current-state-inventory/watcher-observations.md](../01-current-state-inventory/watcher-observations.md)

## Цель

Подключить Markdown docs indexing к существующему file watcher без изменения поведения по умолчанию.

## Входные материалы

- Eligibility predicate: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)
- Config contract: [../02-config-contract/index.md](../02-config-contract/index.md)
- Current-state observations: [../01-current-state-inventory/index.md](../01-current-state-inventory/index.md)

## Релевантные исходники

```text
code_analysis/core/file_watcher*
code_analysis/core/file_watcher_pkg/**
code_analysis/core/config.py
code_analysis/core/config_server.py
code_analysis/main_config.py
```

## Главное правило

Если `code_analysis.docs_indexing.enabled=false`, watcher должен работать как раньше.

## Задачи

- Найти точку, где watcher получает active server config.
- Добавить чтение `code_analysis.docs_indexing`.
- Встроить eligibility predicate из [04-markdown-eligibility](../04-markdown-eligibility/index.md).
- Для enabled config учитывать только `.md` candidates.
- Применять roots/include/exclude.
- Не индексировать `.txt`, `.rst`, `.adoc`, `.json`, `.yaml`, `.py` через docs path.
- Сохранять существующие ignore rules для `.venv`, caches, hidden dirs, deleted files.
- Логировать skipped docs с причиной: disabled, non-md, excluded, outside_roots.

## Ожидаемые артефакты шага

```text
watcher-change-notes.md
watcher-skip-reasons.md
watcher-test-cases.md
```

## Передача в следующие шаги

- Eligible `.md` files передаются в [06-indexing-chunker-integration](../06-indexing-chunker-integration/index.md).
- Skip reasons используются в [08-search-and-diagnostics](../08-search-and-diagnostics/index.md).
- Watcher test cases используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).

## Выход шага

- Watcher обнаруживает eligible Markdown docs только при enabled config.
- Watcher не меняет code indexing behavior.
- Watcher создаёт/обновляет обычные `files` records через существующий механизм.

## Проверка

- `enabled=false`: `.md` docs не попадают в docs indexing path.
- `enabled=true`: `docs/guide.md` попадает.
- `enabled=true`: `docs/plans/task.md` исключён.
- `enabled=true`: `docs/guide.txt` игнорируется.
- Проверка выполняется на dedicated test project only.
