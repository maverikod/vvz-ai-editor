Стек ошибок / проблем на текущий момент

1. CST compose range replacement
Status: fixed / verified earlier
Symptom:
- compose_cst_module при range replacement терял blank lines / trivia.
Root cause:
- пустые строки в LibCST сидят в leading_lines, replacement их не переносил.
Fix:
- поправлен CST patching/preservation.
Verification:
- MCP-поведение compose_cst_module подтвердило исправление.
Current risk:
- низкий, но нужен regression test на trivia/blank lines.

2. query_cst / command execute contract
Status: open
Symptom:
- часть команд живёт в старом стиле execute(explicit_args) -> SuccessResult.
- adapter/base contract ожидает execute(**kwargs) -> CommandResult.
Root cause:
- разъехался контракт command layer ↔ mcp-proxy-adapter.
Fix direction:
- приводить команды code-analysis-server к execute(self, **kwargs: Any) -> CommandResult.
- начать с query_cst_command.py.
Current risk:
- typing/runtime несовместимости при новых версиях adapter.

3. ErrorResult.code typing mismatch
Status: adapter-side issue / open
Symptom:
- фактический API использует строковые error codes типа "CST_QUERY_ERROR".
- typing adapter ожидает int.
Root cause:
- контракт Result/ErrorResult в mcp-proxy-adapter не соответствует фактическому API code-analysis-server.
Fix direction:
- не переводить строки в int внутри code-analysis-server.
- поставить задачу mcp-proxy-adapter: ErrorResult.code должен поддерживать string codes или иметь отдельное поле.
Current risk:
- mypy/typing конфликт, ложные фиксы в прикладном коде.

4. Watcher broad .venv traversal
Status: fixed / verified
Symptom:
- file_watcher сканировал .venv/site-packages, CPU доходил до ~100%.
- list_project_files(show_venv=false) показывал .venv paths.
Root cause:
- should_skip_dir не отсекал .venv/venv достаточно рано.
- ignore_exceptions разворачивали огромные glob’ы внутри site-packages.
Fix:
- shared project_ignore_policy.
- ранний skip .venv/venv/.git/cache dirs.
- allowlisted venv files добавляются ограниченно, без полного обхода .venv.
- list_project_files/status aggregates фильтруют ignored paths.
Verification:
- watcher logs показывали skip descending into .venv.
- list_project_files total упал, .venv/site-packages исчезли из default listing.
Current risk:
- allowlist должен сохраняться; нельзя «лечить» глобальным запретом .venv.

5. allowlisted .venv dependency identity collision
Status: hotfix applied / needs continued monitoring
Symptom:
- indexing_worker писал:
  Data inconsistency detected: file .../.venv/... exists in project X but is being added to project Y.
- старый project file помечался deleted, related data очищалась.
Root cause:
- files.crud.add_file искал cross-project conflict по:
  (relative_path = ? OR path = ?) AND project_id != ?
- relative_path уникален только внутри project root, но ошибочно использовался как глобальный идентификатор.
Fix:
- межпроектный конфликт ограничен same absolute path:
  path = ? AND project_id != ?
- same-project lookup по relative_path OR path оставлен.
Verification:
- код crud.py проверен через read_project_text_file.
- тесты описаны/добавлены исполнителем.
Current risk:
- другие path-only/global lookups ещё надо найти, особенно execute_single.py.

6. Path-only lookup in comprehensive_analysis execute_single.py
Status: open / planned
Symptom:
- найден global query:
  SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1
Root cause:
- потенциальное использование path как глобального business identifier без явного scope.
Fix direction:
- если это normal analysis — добавить project_id.
- если это diagnostic/repair — явно документировать и покрыть тестом.
Current risk:
- возможная новая cross-project путаница при nested roots / same absolute path.

7. index_file false success due to mtime skip
Status: fixed / verified
Symptom:
- indexing logs показывали [index_file] Completed success=True.
- get_database_status показывал files_indexed=0, chunked=0.
Root cause:
- watcher записывал last_modified.
- update_file_data видел disk mtime == files.last_modified и делал skipped=True.
- при первом индексировании AST ещё не существовал, но analyze_file не запускался.
Fix:
- mtime fast path разрешён только если уже есть ast_trees row.
- get_database_status считает indexed AST-aware.
Verification:
- после рестарта files_indexed начал расти и дошёл почти до 100%.
Current state:
- indexed: 2052 / 2053 = 99.95%.
Current risk:
- статус needing_indexing теперь противоречивый, см. пункт 13.

8. PostgreSQL HAVING alias bug in vectorization Step 0
Status: fixed / verified
Symptom:
- vectorization Step 0 падал:
  column "cnt" does not exist
- Step 1 chunking не запускался.
- code_chunks оставался пустым.
Root cause:
- SQL использовал HAVING cnt > 0.
- SQLite принимает alias в HAVING, PostgreSQL нет.
Fix:
- заменено на HAVING COUNT(cc.id) > 0.
Verification:
- после рестарта chunking пошёл.
Current risk:
- нужны dialect regression tests.

9. code_chunks INSERT OR REPLACE not portable to PostgreSQL
Status: fixed / verified
Symptom:
- после исправления HAVING следующим блокером должен был стать INSERT OR REPLACE INTO code_chunks.
Root cause:
- PostgreSQL не поддерживает INSERT OR REPLACE.
- адаптер раньше не мапил code_chunks на ON CONFLICT.
Fix:
- введён shared code_analysis/core/database/code_chunk_sql.py.
- DocstringChunker больше не владеет SQL строкой upsert.
- PostgreSQL adapter переводит code_chunks upsert в ON CONFLICT (chunk_uuid) DO UPDATE.
Verification:
- chunk_count начал расти.
Current state:
- chunks total: 1141
- vectorized chunks: 1136 / 1141 = 99.56%.
Current risk:
- не дублировать SQL обратно в chunker/worker.

10. Chunking/vectorization pipeline disconnected
Status: fixed / verified
Symptom:
- files_indexed рос, но chunk_count = 0.
- vectorization worker idle, FAISS rebuild 0 vectors.
Root cause:
- комбинация пунктов 8 и 9:
  Step 0 падал на PostgreSQL HAVING alias, Step 1 не доходил до DocstringChunker;
  затем code_chunks upsert был PostgreSQL-incompatible.
Fix:
- HAVING COUNT(cc.id) > 0.
- portable code_chunks upsert abstraction.
Verification:
- chunk_count и vectorized_chunks начали расти по всем трём проектам.
Current state:
- code_analysis: 206 chunks, 206 vectorized.
- mcp_proxy_adapter: 628 chunks, 626 vectorized.
- vast_srv: 307 chunks, 304 vectorized.

11. get_database_status project_id semantics
Status: known design issue / open
Symptom:
- get_database_status(project_id=...) фактически возвращает общий статус по всем проектам.
Root cause:
- command schema/implementation не фильтрует по project_id, хотя параметр передаётся через MCP.
Fix direction:
- либо убрать/не принимать project_id;
- либо реализовать явный фильтр project_id;
- в документации команды указать фактическое поведение.
Current risk:
- вводит в заблуждение при проверке одного проекта.

12. get_database_status ignored/stale rows
Status: partially fixed / monitor
Symptom:
- раньше samples включали .venv/site-packages rows.
Root cause:
- status aggregates не использовали общий ignore policy.
Fix:
- добавлен SQL/helper для default status aggregates.
Verification:
- нормальные samples больше не доминируются .venv.
Current risk:
- allowlisted venv rows должны учитываться осознанно, non-allowlisted ignored rows — нет.

13. get_database_status counter inconsistency
Status: new/open
Symptom:
- сейчас:
  active files: 2053
  indexed: 2052 / 2053 = 99.95%
  needing_indexing: 15
- арифметически это не сходится.
Root cause hypothesis:
- indexed и needing_indexing считаются по разным условиям.
- indexed уже AST-aware, а needing_indexing использует старый или другой критерий.
Fix direction:
- привести агрегаты к единой модели состояний:
  active = indexed + needing_indexing + failed/ignored/other_explicit_state
- добавить отдельные счетчики для ambiguous/failed/skipped, если сумма не обязана сходиться.
Likely file:
- code_analysis/commands/worker_status_mcp_commands/get_database_status_build.py
Current risk:
- статус вводит в заблуждение, хотя worker logs чистые.

14. Schema identity model gap
Status: design/open
Symptom:
- desired model: watch_dirs -> projects -> files -> chunks with UUID identities.
- current schema:
  watch_dirs.id TEXT UUID-like
  projects.id TEXT UUID-like
  files.id INTEGER autoincrement
  code_chunks.id INTEGER autoincrement
  code_chunks.chunk_uuid UNIQUE
Root cause:
- legacy integer surrogate keys for files/chunks/entities.
Fix direction:
- не мигрировать сразу int -> UUID.
- сначала добавить UUID business columns, например files.file_uuid.
- сохранить integer FK internals до отдельной миграции.
Current risk:
- прямая миграция int->UUID затронет AST/CST/entities/chunks/vector_index/MCP API.

15. code_chunks.project_id denormalization consistency
Status: open diagnostic
Symptom:
- code_chunks имеет и file_id, и project_id.
- schema не гарантирует code_chunks.project_id == files.project_id.
Root cause:
- project_id денормализован для скорости, но нет CHECK/FK composite guarantee.
Fix direction:
- добавить diagnostic query:
  SELECT chunks where cc.project_id != files.project_id.
- позже рассмотреть trigger/composite FK или application invariant tests.
Current risk:
- возможная рассинхронизация ownership chunks/files.

16. SQLite-specific cleanup SQL risk
Status: known/open
Symptom:
- clear_file_data содержит DELETE FROM code_content_fts WHERE rowid IN (...)
- ранее были правила не использовать SQLite-only SQL в PostgreSQL mode.
Root cause:
- часть cleanup кода всё ещё ориентирована на SQLite FTS.
Fix direction:
- проверить, адаптируется ли это в PostgreSQL driver или пропускается.
- сделать backend-aware cleanup для FTS/rowid.
Current risk:
- cleanup/delete paths могут падать в PostgreSQL при фактическом вызове.

17. Worker/status observability gaps
Status: open
Symptom:
- раньше worker мог быть idle/running без ясного bottleneck.
- queue completed/progress=100 не означает success.
Root cause:
- статусы показывают процесс, но не всегда stage/result semantics.
Fix direction:
- stage-specific logs:
  indexing_started/indexing_done
  chunking_started/chunking_done
  vectorization_started/vectorization_done.
- queue status must expose command.result.success.
Current risk:
- completed job может маскировать failed command.

18. Adapter / queuemgr boundary
Status: open / separate projects
Symptom:
- adapter и queuemgr имеют собственные контракты и не должны патчиться внутри code-analysis-server.
Root cause:
- часть проблем обнаружена через code-analysis-server, но принадлежит adapter layer.
Fix direction:
- писать отдельные задания разработчикам:
  mcp-proxy-adapter: Result typing, ErrorResult.code, execute contract mapping.
  queuemgr: truthful job status / lifecycle semantics if needed.
Current risk:
- фиксы не в том пакете создадут костыли.

19. Docs/plans refactor plan
Status: created
Location:
- docs/plans/2026-04-27-identity-db-pipeline-refactor/
Created files:
- 00-index.md
- 01-code_analysis_core_database_files_crud.md
- 02-code_analysis_commands_comprehensive_analysis_mcp_execute_single.md
- 03-code_analysis_core_file_identity.md
- 04-code_analysis_core_project_ignore_policy.md
- 05-code_analysis_core_database_schema_identity.md
- 06-code_analysis_core_database_code_chunk_sql.md
- 07-code_analysis_core_file_watcher_pkg_scanner.md
- 08-code_analysis_core_database_driver_pkg_drivers_postgres_run.md
- 09-code_analysis_core_docstring_chunker_pkg_docstring_chunker.md
- 10-code_analysis_core_vectorization_worker_pkg_batch_processor.md
- 11-code_analysis_core_vectorization_worker_pkg_processing_cycle_projects.md
- 12-uuid_business_identity_transition.md
- 13-parallelization-map.md
Current risk:
- need one extra step file for get_database_status counter consistency.

Current runtime summary:
- indexing worker errors in last check: 0
- vectorization worker errors in last check: 0
- indexed: 2052 / 2053 = 99.95%
- chunks total: 1141
- vectorized chunks: 1136 / 1141 = 99.56%
- active new problem: get_database_status counters inconsistent


21. healthy_parse_blocks_line_ops applies CST gate to all file types
Status: fixed
Symptom:
- write_project_text_lines and get_file_lines for non-Python files (.md, .txt, .json etc.)
  returned USE_CST_COMMANDS instead of working normally.
- Writing to docs/ERRORS.md was blocked with:
  'This file parses successfully. Use CST commands instead...'
Root cause:
- healthy_parse_blocks_line_ops() in line_command_cst_gate.py called cst.parse_module()
  for ANY file regardless of extension.
- Markdown files occasionally passed LibCST parse as valid Python,
  so the gate refused writes even for non-code files.
Fix:
- Added file_path: str = '' parameter to healthy_parse_blocks_line_ops().
- Before CST parse: check extension against FORBIDDEN_PYTHON_SOURCE_SUFFIXES.
  Non-Python extension -> return False immediately (skip gate).
- FORBIDDEN_PYTHON_SOURCE_SUFFIXES imported from project_text_file_guard (no duplication).
- pathlib.Path imported in line_command_cst_gate.py.
- Callers updated: get_file_lines_command.py, replace_file_lines_command.py +file_path=file_path.
Files changed:
- code_analysis/commands/line_command_cst_gate.py
- code_analysis/commands/get_file_lines_command.py
- code_analysis/commands/replace_file_lines_command.py
Verification:
- write_project_text_lines on docs/ERRORS.md passed without USE_CST_COMMANDS.
- CST gate logic for .py/.pyi/.pyw/.pyx/.pxd/.pxi files unchanged.
Current risk:
- Existing tests in test_project_text_file_commands.py call function without file_path.
  Need new test: non-Python file with valid Python content must not be blocked by gate.

22. # ERRORS.md — Найденные проблемы MCP / CST API

Дата: 2026-04-27  
Контекст: правка файлов `multi_project_worker_scan.py`, `multi_project_worker_cycle.py` через `code-analysis-server` (MCP-Proxy).

---

## 1. Валидатор блокирует запись из-за ошибок в docstring, не связанных с текущей правкой
НЕУДОБНО
**Команда:** `compose_cst_module`  
**Симптом:**
```
VALIDATION_ERROR: Docstring validation failed:
  - Method scan_watch_dir (line 39) docstring is missing parameter descriptions: _ignore_patterns
```
Параметр в сигнатуре — `_ignore_patterns`, в docstring был написан `ignore_patterns` — несовпадение имён.  
**Проблема:** Валидатор не разрешает применять **никакие** изменения в файл, пока в нём есть предсуществующая ошибка docstring — даже если текущая правка docstring не касается.  
**Последствие:** Пришлось сначала исправить docstring, и только потом применять целевое изменение. Хирургический патч превратился в два.

---

## 2. `compose_cst_module` блокирует запись с сообщением «Found 0 mypy errors»

**Команда:** `compose_cst_module`  
**Симптом:**
```
VALIDATION_ERROR: type_checker: Found 0 mypy errors
```
Ноль ошибок — это успех mypy, но сервер трактует это как `success: false` и блокирует запись.  
**Предположение:** Баг в логике проверки результата mypy: поле `errors` пустое, но `success` выставляется в `false` если mypy вернул что-либо в stderr или нестандартный exit code. Либо конфигурация сервера требует mypy молчать полностью, а он печатает summary строку.  
**Последствие:** `compose_cst_module` стал недоступен для редактирования строки 454 в `multi_project_worker_scan.py`. Пришлось переключиться на `query_cst` с `replace_with` + `start_line`/`end_line`, который валидацию не запускает.

---

## 3. `compose_cst_module` с selector `kind: function` обрезает тело функции

**Команда:** `compose_cst_module`, selector `{kind: "function", name: "scan_watch_dir"}`  
**Симптом:**
```
type_checker: Found 1 mypy errors
error: Missing return statement  [empty-body]
```
**Проблема:** При использовании `selector.kind = "function"` команда заменяет только сигнатуру и docstring, тело функции отбрасывается. В результате mypy видит функцию без тела.  
**Ожидаемое поведение:** Замена только docstring/сигнатуры с сохранением тела, либо явная документация что `kind: function` заменяет функцию целиком и требует передавать полный код.  
**Обходной путь:** Замена docstring через `cst_modify_tree` по `node_id` узла-выражения (Expr с SimpleString).

---

## 4. `cst_get_node_by_range` возвращает ближайший родительский узел вместо точного диапазона
Проверить. Точный диапазон и невозможен
**Команда:** `cst_get_node_by_range`, `start_line=457, end_line=461`  
**Симптом:** Вернул узел `Try` (строки 96–467) вместо блока из 5 строк `stats[...] += ...`.  
**Проблема:** Когда запрошенный диапазон не совпадает точно с границами ни одного CST-узла, команда возвращает наименьший **содержащий** узел. Для блоков из нескольких statement-ов, которые не являются отдельным CST-узлом, это всегда будет весь блок `try/for/if`.  
**Последствие:** Нельзя надёжно адресовать произвольный диапазон строк через `cst_get_node_by_range` — нужно идти через `cst_get_node_at_line` построчно и собирать node_id вручную.

---

## 5. `cst_modify_tree` не поддерживает операцию `insert_after`
НЕУДОБНО
**Команда:** `cst_modify_tree`, `action: "insert_after"`  
**Симптом:**
```
INVALID_ACTION: Invalid action: insert_after
```
**Проблема:** Отсутствует операция вставки строки после заданного узла. Доступны только `replace`. Для вставки новой строки после существующей приходится использовать обходные пути: заменять строку на две через `query_cst`/`compose_cst_module`.  
**Желаемый функционал:** `insert_before`, `insert_after` по `node_id`.

---

## 6. `query_cst` с одновременным `selector` + `start_line` не выполняет замену

**Команда:** `query_cst`, параметры `selector="FunctionDef[name='scan_watch_dir']", start_line=457, replace_with=...`  
**Симптом:** `replaced: 1`, но diff пустой, файл не изменился.  
**Проблема:** При комбинации `selector` + `start_line` + `replace_with` команда сообщает об успехе (`replaced: 1`), но реально замену не производит. Поведение вводит в заблуждение — нет ни ошибки, ни предупреждения.  
**Обходной путь:** Использовать `query_cst` только с `start_line`/`end_line` без `selector`, либо только с `selector` без `start_line`.

---

## 7. `cst_modify_tree` инвалидирует node_id после сохранения дерева

**Команда:** `cst_modify_tree`  
**Симптом:**
```
INVALID_OPERATION: Node not found for replacement: c4d25ccd-...
```
**Проблема:** После любой записи (`save_applied: true`) все node_id из предыдущей загрузки дерева становятся невалидными. Необходимо каждый раз заново вызывать `cst_load_file`, чтобы получить актуальные id.  
**Неудобство:** Это не задокументировано явно. Команда `cst_reload_tree` существует, но возвращает ответ слишком большого размера (tool result too large), что делает её практически непригодной для получения новых node_id.

---

## 8. `cst_reload_tree` возвращает ответ, превышающий лимит контекста
должны быть только узлы первого уровня - сигнатуры методов, названия классов, переменные и докстринги модуля (обсудить)
**Команда:** `cst_reload_tree`  
**Симптом:**
```
Tool result too large for context, stored at /mnt/user-data/tool_results/...
```
**Проблема:** После успешного применения правки попытка перезагрузить дерево через `cst_reload_tree` возвращает объём данных, который не помещается в контекст. Получить актуальные node_id без отдельного вызова `cst_load_file` невозможно.  
**Желаемый функционал:** Параметр `return_format: "declarative"` или `outline_only: true` для `cst_reload_tree`, аналогичный тому, что есть в `cst_load_file`.

---

## 9. `read_only_batch` не включает в whitelist базовые read-команды
Разобраться почему
**Команда:** `read_only_batch` с `get_file_lines`, `file_structure`  
**Симптом:**
```
BATCH_COMMAND_NOT_WHITELISTED: Command is not in the read-only batch whitelist.
`Разобраться почему``
**Проблема:** Команды `get_file_lines` и `file_structure` не входят в whitelist `read_only_batch`, хотя являются явно read-only операциями. Батчевое чтение нескольких файлов одним вызовом недоступно.  
**Последствие:** Каждый файл и каждый диапазон строк нужно читать отдельным вызовом, что увеличивает round-trip время.

---

## 10. `get_file_lines` недоступен для валидных Python-файлов без специального флага конфигурации
И не должен быть доступен. для этого есть CST
**Команда:** `get_file_lines`  
**Симптом:**
```
USE_CST_COMMANDS: This file parses successfully. Use CST commands instead.
Set code_analysis.allow_line_commands_on_healthy_files=true to allow get_file_lines/replace_file_lines on healthy files.
```
**Проблема:** Для любого корректно парсящегося `.py`-файла прямой доступ к строкам через `get_file_lines` заблокирован. Это форсирует использование CST-команд даже там, где достаточно прочитать 10 строк.  
**Неудобство:** CST-команды значительно тяжелее по объёму ответа и требуют дополнительных round-trip для получения node_id нужного фрагмента.


