# Issues Found in Refactoring Plan

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Analysis date: 2026-05-03 (updated)

---

## CRITICAL ERRORS (план в прежней версии был неверен)

### Issue 1: Step 07 — rpc_handlers_file_trash.py — проблема сложнее чем просто заменить SQL

**Реальность:**
Trash-методы (`mark_file_deleted`, `unmark_file_deleted`, `hard_delete_file`) — это
**не чистый SQL**, они перемещают файлы физически. Исходник —
`core/database/files/trash.py` (438 строк).

**Правильный план для step 07:**
Step-07 предлагает два варианта (A: вынос логики в trash_standalone.py,
B: документировать `_get_code_db` как архитектурное исключение).
`from_existing_driver` безопасен — не открывает новое соединение и не вызывает sync_schema.

---

### Issue 2: Step 08 — rpc_handlers_index_file.py — Option B была неверна

**Правильный план:** Использовать `update_file_data_via_driver(self.driver)` (step 09).
`DatabaseClient.index_file()` здесь нельзя — рекурсивный RPC. Уже зафиксировано в step-08.

---

### Issue 3: Steps 04 и 05 — driver.sync_schema() требует аргументы (RESOLVED)

**Решение уже внесено в step-04 и step-05.**

Использовать `get_schema_definition()` + `backup_dir`.
`SQLiteDriver.sync_schema()` — строка **476** (не 493). `backup_dir` — optional (default None).
`PostgreSQLDriver.sync_schema()` — строка **532** (было 509 — устарело; обновлено 2026-05-03).

---

### Issue 4: Step 06 — DatabaseClient.connect() не принимает {"path": ...} (RESOLVED, OUTDATED)

Степ-06 уже обновлён — в текущей версии вместо `DatabaseClient` используется
`InProcessRpcClient → DatabaseClient(rpc_client=ipc)`. Проблема с `connect({«path»: ...})` — устарела.

---

### Issue 5: Step 08 не упомянул DatabaseClient.index_file() (RESOLVED)

`DatabaseClient.index_file()` есть на строке **509** (`_ClientAPIFilesMixin`). Рекурсивный RPC.
Зафиксировано в step-08.

---

### Issue 6: Step 06 — vectorize_file_immediately отсутствует в DatabaseClient (OPEN)

`vectorize_file_immediately` есть только в CodeDatabase mixins (`update_vectorize.py:16`).
В DatabaseClient нет. Решается в step 10 (создание `_vectorize_via_client` в `update_standalone.py`).

До завершения step 10, `_vectorize_file_immediately` в `vectorize_after_index.py`
вызовет `AttributeError` на `DatabaseClient`. Step 06 помечен это как MEDIUM RISK.

---

## НЕТОЧНОСТИ

### Issue 7: Step 02 — номер строки database._commit() (RESOLVED)

В README плана было написано "line 120".
Реально `database._commit()` на строке **119** (verified).
Step-02 уже содержит node_id `adad552c` (commit guard lines 175-179).

---

### Issue 8: Step 03 — Union в faiss_manager.py (RESOLVED)

В `faiss_manager.py` `Union` импортируется в отдельной строке (line 24: `from typing import Union`).
**Других использований Union (не `Union[CodeDatabase, DatabaseClient]`) в файле нет.**
Импорт Union можно безопасно удалить целиком. Step-03 обновлён.

---

### Issue 9: Steps 01-03 — не указан XPath-запросы (RESOLVED)

Step-файлы обновлены: добавлены node_id и явные CST-команды с `code_lines`.

---

### Issue 10: Step 07 — источник SQL trash-методов (RESOLVED)

Где лежат trash-методы теперь указано: `core/database/files/trash.py`.
Локации: `mark_file_deleted:17`, `unmark_file_deleted:236`, `get_deleted_files:366`, `hard_delete_file:394`.
Step-07 обновлён.

---

## НЕОДНОЗНАЧНОСТИ

### Issue 11: Steps 08/09 — архитектурный выбор (RESOLVED)

Решение зафиксировано: `InProcessRpcClient(RPCHandlers(driver)) → DatabaseClient(rpc_client=ipc)`.
`analyze_file()` принимает DatabaseClient, не BaseDatabaseDriver. Step-09 обновлён.

---

### Issue 12: Step 06 — как получить RPC-адрес из конфига (RESOLVED)

Step-06 использует `InProcessRpcClient` (не требует сетевого RPC-адреса). Обновлён.

---

## СЛОЖНЫЕ ДЛЯ HAIKU ШАГИ

### Красная зона (STOP перед началом)

| Шаг | Проблема |
|------|-----------|
| Step 07 | Архитектурное решение (Approach A или B) нужно выбрать. Filesystem-логика в trash.py |
| Step 09 | 401 строка + InProcessRpcClient. Читать источники перед началом |
| Step 10 | Зависит от 09 + чтение `vectorize_file_immediately` в полном объёме |

### Жёлтая зона (требует осторожности)

| Шаг | Проблема |
|------|-----------|
| Step 06 | `_vectorize_file_immediately` будет бить AttributeError до завершения step 10 |
| Step 08 | Зависит от 09 |

### Зелёная зона (безопасно для Haiku)

| Шаг | Почему безопасно |
|------|-------------------|
| Step 01 | 101 строка, 1 isinstance-ветка, точные node_id, node `e094384e` |
| Step 02 | Точные node_id. Учтен баг сохранения embedding |
| Step 03 | Только type signatures, уточнен Union |
| Step 04 | Точный код замены cmd_schema, get_schema_definition |
| Step 05 | Точный код замены, PG-ветка |

---

## НОВЫЕ ISSUES (найдены анализом 2026-05-03)

---

### Issue 13: Step 10 — `await analyze_file()` — TypeError (FIXED IN STEP FILE)

**Проблема:** в шаблоне `update_and_vectorize_via_driver` шага 10 стояло
`update_result = await analyze_file(...)`. `analyze_file` в `update_indexes_analyzer.py:34`
определена как обычная `def`, не `async def`. `await` на синхронной функции → `TypeError`.
Step 09 правильно вызывает `analyze_file()` без `await`.

**Исправлено:** строка исправлена в step-10-update-vectorize.md,
добавлено предупреждение «analyze_file is sync — do NOT await».

---

### Issue 14: Step 11 — удаление db_driver/ невозможно без переделки CodeDatabase (FIXED IN STEP FILE)

**Проблема:** `CodeDatabase.__init__` в `database/base.py:137` вызывает `create_driver()`
из legacy `db_driver`. Удаление каталога без переделки `__init__` даёт `NameError`.
Кроме того, legacy `create_driver` и новый `database_driver_pkg.driver_factory.create_driver`
**не взаимозаменяемы** — разные поддерживаемые типы и разные интерфейсы драйверов.

**Исправлено:** в step-11-delete-db-driver.md добавлена секция
«CRITICAL: CodeDatabase.__init__ must be rewritten» с Approach A и Approach B.
Risk повышен с LOW до MEDIUM. Executor обязан остановиться и согласовать с пользователем.

**Неучтённая мотивация в README:** legacy db_driver НЕ поддерживает PostgreSQL вообще.
Это техническая необходимость, а не только архитектурная чистота.

---

### Issue 15: Step 06 — `_in_process_driver` — логический дубль (FIXED IN STEP FILE)

**Проблема:** прежний шаблон `_create_database` сохранял `client._in_process_driver = driver`
и прежний `_close_driver` вызывал его явно. Но `InProcessRpcClient.disconnect()`
(строка 54, `in_process_rpc_client.py`) уже вызывает `self.handlers.driver.disconnect()`
внутри → двойной disconnect.

**Исправлено:** атрибут `_in_process_driver` убран, `_close_driver` упрощён до
одного `rpc_client.disconnect()`. Добавлено пояснение.

---

### Issue 16: Step 08 — logger.debug НЕ внутри try-block (FIXED IN STEP FILE)

**Проблема:** план ошибочно писал «logger.debug удалится автоматически при замене try-block».
Реально logger.debug стоит на строках 105-107, **до** `try:` на строке 108,
и при замене try-block остаётся в коде со стаж-сообщением о `from_existing_driver`.

**Исправлено:** в step-08 добавлена отдельная `delete`-операция для logger.debug
с примером `cst_get_node_by_range(start_line=105, end_line=107)`.

---

### Issue 17: Step 02 — bug fix не отражён в validation (OPEN)

**Проблема:** step-02 исправляет баг: embeddings НЕ сохранялись в БД при DatabaseClient-пути.
Validation sequence содержит только lint/format/typecheck, но не проверяет
что `code_chunks.embedding_vector IS NOT NULL` после реального прогона.

**Рекомендация:** после деплоя step-02 дополнительно проверить:
trigger vectorization → убедиться, что `embedding_vector` заполняется в `code_chunks`.

---

### Issue 18: Step 09/10 — boilerplate InProcessRpcClient повторяется дважды (OPEN, LOW)

Оба шага содержат идентичный блок:
```python
handlers = RPCHandlers(driver)
ipc = InProcessRpcClient(handlers)
ipc.connect()
client = DatabaseClient(rpc_client=ipc)
```
При реализации рекомендуется вынести в `_make_in_process_client(driver)` в `update_standalone.py`
чтобы не дублировать код сопровождения.

---

### Issue 19: core/database/__init__.py re-export CodeDatabase — осознанно оставляется (DOCUMENTED)

`core/database/__init__.py:12` делает `from .base import CodeDatabase`. После steps 01-10
этот re-export остаётся — он нужен тестам (30+ fixtures импортируют `CodeDatabase` через короткий путь).
Удалять его не нужно. Это осознанное решение: тесты продолжают использовать
CodeDatabase как fixture-helper через SQLite in-memory.
