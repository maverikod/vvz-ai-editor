# 04. Markdown eligibility

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)
- Следующий шаг: [../05-watcher-integration/index.md](../05-watcher-integration/index.md)
- Связанный config contract: [../02-config-contract/index.md](../02-config-contract/index.md)

## Цель

Реализовать единый predicate для определения, является ли файл допустимым Markdown-документом для docs indexing.

## Входные материалы

- Config contract: [../02-config-contract/index.md](../02-config-contract/index.md)
- Validator/generator step: [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)
- Watcher integration target: [../05-watcher-integration/index.md](../05-watcher-integration/index.md)

## Релевантные исходники

```text
code_analysis/core/config_validator/section_code_analysis.py
code_analysis/core/file_watcher*
code_analysis/core/file_watcher_pkg/**
```

## Правило допуска

Файл eligible только если:

1. `code_analysis.docs_indexing.enabled == true`.
2. Путь project-relative.
3. Суффикс файла ровно `.md`.
4. Путь находится под одним из `roots` или явно разрешён include pattern, например `README.md`.
5. Путь соответствует хотя бы одному include pattern.
6. Путь не соответствует ни одному exclude pattern.
7. Файл существует на диске и не помечен deleted.

## Задачи

- Создать/выделить функцию eligibility для docs indexing.
- Использовать один и тот же predicate в watcher, tests и diagnostics.
- Реализовать нормализацию путей к project-relative POSIX form.
- Исключение должно выигрывать у включения.
- Не расширять это правило на `.txt`, `.rst`, `.adoc`, `.json`, `.yaml`, `.py`.

## Шаблоны исключения

Default:

```text
docs/plans/**
docs/ai_reports/**
```

Optional examples for user configs:

```text
docs/archive/**
docs/tmp/**
docs/**/drafts/**
docs/**/*.bak.md
docs/**/*~.md
```

## Ожидаемые артефакты шага

```text
eligibility-rules.md
include-exclude-examples.md
eligibility-test-cases.md
```

## Передача в следующие шаги

- Predicate используется в [05-watcher-integration](../05-watcher-integration/index.md).
- Тест-кейсы используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).
- Diagnostics reasons используются в [08-search-and-diagnostics](../08-search-and-diagnostics/index.md).

## Проверка

- `docs/guide.md` passes when enabled.
- `README.md` passes when enabled and included.
- `docs/guide.txt` fails.
- `docs/plans/task.md` fails by default exclude.
- If `docs/**/*` is allowed by validator, runtime eligibility still rejects non-md files by suffix; if strict validator rejects it, the rejection must be documented and tested.