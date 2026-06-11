# Compatibility notes — `docs_indexing`

**Родительский шаг:** [index.md](index.md).  
**Расширенная версия:** [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md).

## Конфигурация

- Отсутствие `code_analysis.docs_indexing` — **валидно**; семантика как до фичи.
- Поля только boolean и массивы строк по контракту ТЗ; абсолютные пути и `..` в `roots` — отвергаются валидатором.
- Настройки **не** читаются из `projectid`.

## Поведение пайплайна

- При `enabled=false` файл watcher и связанная логика **полностью игнорируют** docs indexing (шаг 05).
- Индексация исходного кода (`.py` и пр.) не должна меняться при выключенной фиче.
- Markdown-доки используют те же `files` / `code_chunks`, что и код; отдельных `docs_chunks` / `docs_vectors` нет.
- `vectorize=false`: чанки могут существовать без `vector_id`/FAISS; `semantic_search` не обязан возвращать доки.
- `vectorize=true`: используется существующий worker векторизации; форма ответа `semantic_search` та же, что для кодовых чанков.

## Поиск и драйвер БД

- Различие **fulltext** (FTS/`code_content`) и **semantic** (FAISS + `code_chunks`) должно оставаться строгим: отключение векторизации отключает только семантический путь для доков, не обязательно полнотекст (см. ТЗ и шаг 08).
- Backend-specific: SQLite FTS/`rowid` vs UUID в универсальной схеме — не смешивать предположения между драйверами (см. [rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md)).

## Команды и MCP

- Новый отдельный diagnostics-командный контур для этой задачи не требуется ТЗ; проверка — существующими командами и тестами.
