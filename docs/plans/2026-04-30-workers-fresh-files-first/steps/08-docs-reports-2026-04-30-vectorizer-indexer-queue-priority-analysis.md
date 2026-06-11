# Шаг 8: `docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md`

**Один файл = один шаг** (документ в `docs/reports/`, не пакет `code_analysis/`).

## Статус

По [README.md](../README.md): шаг **к выполнению** — синхронизировать отчёт с уже внедрённой семантикой; убрать описание старого ASC/FIFO как **«текущего»** для горячих путей воркеров.

## Цель

- Формулировки «текущее поведение», цитаты SQL и сводная таблица **§5** соответствуют коду **`processing.py`**, **`processing_cycle.py`**, **`processing_cycle_projects.py`**, **`batch_processor.py`**, **`file_batch_packing.py`**.
- Таблица **§5**: **четыре** колонки — **Место / Было / Стало / Статус** (см. приложение в README).
- Заключение **§8**: политика DESC для горячих путей и сохранение канона **ASC** для FAISS rebuild / `base_chunks`.

## Объём правок (чеклист плана)

**16 согласованных замен** по разделам (§2.2–2.3, §3.2–3.5, §5, §6, §8, пересверка всех fenced **`start:end:path`**). Детальная карта абзацев — в [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md), раздел «Шаг 8».

## Инструменты записи (сервер)

1. Предпочтительно **`universal_file_replace`** с массивом **`replacements`**: **`dry_run: true`** → preview, затем **`dry_run: false`**.
2. Fallback: **`universal_file_save`** с полным текстом и тем же preview.
3. Legacy по строкам — **`write_project_text_lines`** только при отсутствии альтернатив; при множественных диапазонах — **с конца файла к началу**, чтобы не сдвигать номера строк.

Перед каждой заменой сверять фактический текст через **`read_project_text_file`** (или полное чтение отчёта).

## Критерий готовности

- Отчёт без устаревшего ASC для горячих путей воркеров как актуального состояния; цитаты SQL и **§5** согласованы с репозиторием после диффов.

## См. также

- [README.md](../README.md) — шаг 8 и приложение «исправления» (universal replace, 16 замен, пересверка citations).
- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — таблица разделов и подзадачи §1–§8.
