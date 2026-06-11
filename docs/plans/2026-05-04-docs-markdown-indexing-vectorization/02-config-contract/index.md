# 02. Config contract

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../01-current-state-inventory/index.md](../01-current-state-inventory/index.md)
- Следующий шаг: [../03-config-validator-generator/index.md](../03-config-validator-generator/index.md)
- Связанный шаг eligibility: [../04-markdown-eligibility/index.md](../04-markdown-eligibility/index.md)

## Цель

Закрепить контракт новой секции `code_analysis.docs_indexing` в основном серверном config.

## Входные материалы

- ТЗ: [../01-task-spec.md](../01-task-spec.md)
- Наблюдения по config validator/generator должны быть добавлены в [../01-current-state-inventory](../01-current-state-inventory/index.md), если потребуется.

## Исходные файлы

```text
code_analysis/core/config_generator.py
code_analysis/core/config_validator/validator.py
code_analysis/core/config_validator/section_code_analysis.py
code_analysis/core/config_models.py
code_analysis/cli/config_cli_generate.py
code_analysis/cli/config_cli_parser.py
```

## Решение

Настройки docs indexing относятся к серверному поведению `code_analysis`, а не к файлу `projectid` отдельного проекта. Поэтому все настройки должны жить в main config.

## Целевая секция

```json
{
  "code_analysis": {
    "docs_indexing": {
      "enabled": false,
      "vectorize": false,
      "roots": ["docs"],
      "include": ["docs/**/*.md", "README.md"],
      "exclude": ["docs/plans/**", "docs/ai_reports/**"]
    }
  }
}
```

## Правила defaults

- `enabled=false` по умолчанию.
- `vectorize=false` по умолчанию.
- `roots=["docs"]` по умолчанию.
- `include=["docs/**/*.md", "README.md"]` по умолчанию.
- `exclude=["docs/plans/**", "docs/ai_reports/**"]` по умолчанию.

## Markdown-only контракт

Допустимы только `.md` файлы. Validator не должен полагаться только на внешний вид glob-pattern: runtime eligibility обязана всё равно отсекать non-md пути по suffix check.

Перед закреплением default include patterns нужно явно проверить фактическую semantics используемого matcher (`fnmatch`, `pathlib`, custom matcher и т.п.). В частности, подтвердить, покрывает ли `docs/**/*.md` файлы вида `docs/guide.md` или только вложенные подкаталоги.

Broad patterns допустимы только если validator или eligibility гарантированно ограничивает результат Markdown suffix. Если выбран строгий validator, он должен отклонять неоднозначные patterns с понятной ошибкой, например:

```text
**/*
docs/**/*
docs/**/*.txt
*.json
*.py
```

## Ожидаемые артефакты шага

```text
config-contract.md
config-defaults.md
backward-compatibility-notes.md
```

## Передача в следующие шаги

- Контракт используется в [03-config-validator-generator](../03-config-validator-generator/index.md).
- Markdown-only часть используется в [04-markdown-eligibility](../04-markdown-eligibility/index.md).
- Defaults используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).

## Проверка

- Старый config без `docs_indexing` остаётся валидным.
- Новый config с defaults валиден.
- Никакая настройка не переносится в `projectid`.