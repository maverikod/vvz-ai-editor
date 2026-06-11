# Шаги: CST save safety

**Правило:** один файл этого каталога `steps/*.md` = один шаг = **ровно один** целевой файл исходного кода в репозитории (кроме шага 07 — только тесты).

**Для исполнителя (Qwen 2.5 Coder и аналоги):** читать шаги **строго по номеру**; в каждом шаге есть ссылки на код, план и соседние шаги — дополнительный контекст искать только по этим ссылкам.

| Шаг | Целевой файл | Спецификация шага |
|-----|----------------|-------------------|
| 01 | [`code_analysis/core/cst_tree/models.py`](../../../../code_analysis/core/cst_tree/models.py) | [01-code_analysis-core-cst_tree-models.md](./01-code_analysis-core-cst_tree-models.md) |
| 02 | [`code_analysis/core/cst_tree/tree_builder.py`](../../../../code_analysis/core/cst_tree/tree_builder.py) | [02-code_analysis-core-cst_tree-tree_builder.md](./02-code_analysis-core-cst_tree-tree_builder.md) |
| 03 | **`code_analysis/core/cst_tree/tree_save_verification.py`** (создать) | [03-code_analysis-core-cst_tree-tree_save_verification.md](./03-code_analysis-core-cst_tree-tree_save_verification.md) |
| 04 | [`code_analysis/core/cst_tree/tree_saver.py`](../../../../code_analysis/core/cst_tree/tree_saver.py) | [04-code_analysis-core-cst_tree-tree_saver.md](./04-code_analysis-core-cst_tree-tree_saver.md) |
| 05 | [`code_analysis/commands/cst_modify_tree_command.py`](../../../../code_analysis/commands/cst_modify_tree_command.py) | [05-code_analysis-commands-cst_modify_tree_command.md](./05-code_analysis-commands-cst_modify_tree_command.md) |
| 06 | [`code_analysis/commands/cst_save_tree_command.py`](../../../../code_analysis/commands/cst_save_tree_command.py) | [06-code_analysis-commands-cst_save_tree_command.md](./06-code_analysis-commands-cst_save_tree_command.md) |
| 07 | **`tests/test_cst_save_verification.py`** (создать) | [07-tests-test_cst_save_verification.md](./07-tests-test_cst_save_verification.md) |

**Тезисы и цели плана:** [../README.md](../README.md).

**Параллелизация шагов:** [../PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md).

**Стандарты репозитория после правок кода:** [docs/PROJECT_RULES.md](../../../PROJECT_RULES.md) (venv, black, flake8, mypy на затронутых путях).
