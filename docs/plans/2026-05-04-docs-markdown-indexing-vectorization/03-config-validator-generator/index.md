# 03. Config validator and generator

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../02-config-contract/index.md](../02-config-contract/index.md)
- Следующий шаг: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)
- Проверки: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Цель

Добавить поддержку `code_analysis.docs_indexing` в config validator, config generator и CLI генерации config.

## Входные материалы

- Config contract: [../02-config-contract/index.md](../02-config-contract/index.md)
- Markdown-only eligibility rules: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)

## Исходные файлы

```text
code_analysis/core/config_generator.py
code_analysis/core/config_validator/validator.py
code_analysis/core/config_validator/section_code_analysis.py
code_analysis/core/config_validator/field_types.py
code_analysis/core/config_validator/field_types_code_analysis.py
code_analysis/core/config_validator/field_values.py
code_analysis/cli/config_cli_generate.py
code_analysis/cli/config_cli_parser.py
code_analysis/cli/config_cli_commands.py
```

## Задачи validator

- Разрешить отсутствие `docs_indexing`.
- Проверить, что при наличии `docs_indexing` является object.
- Проверить boolean поля `enabled` и `vectorize`.
- Проверить массивы строк `roots`, `include`, `exclude`.
- Validate `include` patterns against documented matcher semantics; either reject non-Markdown-resolving patterns or allow broad patterns only when runtime eligibility still enforces `.md` suffix.
- Запретить absolute paths и `..` traversal.
- Возвращать структурированные `ValidationResult` с section/key.

## Задачи generator

- Добавить generator arguments для docs indexing.
- Сгенерировать безопасные defaults.
- Не включать indexing/vectorization по умолчанию.
- CLI help должен явно писать: Markdown-only и vectorize disabled by default.

## Ожидаемые артефакты шага

```text
validator-change-notes.md
generator-change-notes.md
cli-change-notes.md
validator-test-cases.md
```

## Передача в следующие шаги

- Validator Markdown-only правила используются в [04-markdown-eligibility](../04-markdown-eligibility/index.md).
- Defaults используются в [05-watcher-integration](../05-watcher-integration/index.md) и [07-vectorization-gating](../07-vectorization-gating/index.md).
- Тест-кейсы используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).

## Проверка

- Default config valid.
- Old config without `docs_indexing` valid.
- `docs/**/*.md` valid after matcher semantics are documented.
- `README.md` valid.
- `docs/**/*.txt` invalid or harmless because runtime eligibility rejects non-md suffixes; chosen validator behavior must be documented.
- Broad patterns such as `docs/**/*` and `**/*` are either rejected by strict validator or explicitly allowed only with runtime `.md` suffix enforcement; chosen behavior must be tested and documented.