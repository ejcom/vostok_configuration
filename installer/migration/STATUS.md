# STATUS переноса установщика на Python

Ветка интеграции: `py-migration` (от `add-installer`). Агенты: ветки `py/<имя>`, worktree. Источник истины по плану: `PLAN.md`. Обновляет оркестратор после каждого агента.

## Агенты

| агент | ветка | статус | последний коммит | открытые вопросы | дата |
|---|---|---|---|---|---|
| A0 harness | py/harness | merged | b89f806 (слияние в py-migration; golden 234/0 расхождений) | 5 вопросов в reports/harness.md (нумерация A–H, 10 главных плат, требования к хосту) | 2026-10-15 |
| A1 core | py/core | merged | см. git log py-migration (слияние py/core; 75 тестов, golden 234/0) | 4 вопроса в reports/core.md | 2026-10-15 |
| A2 update | py/update | merged | слияние py/update (121 тест; golden 234/0) | см. reports/update.md | 2026-10-16 |
| A3 integrations | py/integrations | merged | слияние py/integrations | см. reports/integrations.md | 2026-10-16 |
| A4 configurator | py/configurator | merged | слияние py/configurator | см. reports/configurator.md | 2026-10-16 |
| A5 install-flow | py/install-flow | review | см. git log py/install-flow (402 теста, golden 232 из 234) | 2 эталона не пересняты (install/dry_no_tty_no_y, boards/bad_args), см. reports/install-flow.md | 2026-10-16 |
| A6 cleanup-docs | py/cleanup-docs | review | см. git log py/cleanup-docs (399 тестов, golden 234/0, gen_configs --check 41/0) | tools/mcu_merge, pin_conflicts, can_uuid оставлены обёртками ради golden; см. reports/cleanup-docs.md | 2026-10-16 |

Статусы: todo | in-progress | review | merged. Ревью (R) после волн 0–1, 2, 3, 4: отчёты в `reports/review-*.md`.

## Сессии

| сессия | содержание | статус |
|---|---|---|
| S1 | подготовка (каталог migration/) + A0 harness + R | подготовка и A0 выполнены 2026-10-15, ревью R по волне 0 не запущено |
| S2 | A1 core + R | A1 выполнен и влит 2026-10-15; ревью R по волнам 0–1 не запускалось |
| S3 | A2 ‖ A3 ‖ A4 + слияние + R | todo |
| S4 | A5 install-flow | todo |
| S5 | A6 cleanup-docs + итоговый R | todo |

## Как продолжить (протокол начала сессии)
1. Прочитать этот файл и `MAP.md`; `git log --oneline py-migration`.
2. Найти первую незавершённую волну; запустить агентов по `prompts/<A…>.md` (Agent, general-purpose, `isolation: worktree`).
3. После каждого агента: слить ветку в `py-migration` (`--no-ff`), прогнать `python3 -m unittest discover installer/tests` и `tests/run_golden.sh`, обновить таблицы здесь и в `MAP.md`, закоммитить.

## Решения / продолжить с
- 2026-10-15: план утверждён пользователем; публичные команды и флаги не меняются, `python3 -m vostok` — внутренняя деталь обёрток. Слияние `py-migration` → `add-installer` только после S5 и по явному одобрению; push/PR делает пользователь.
- 2026-10-15: на старте ветка `add-installer` содержит незакоммиченных изменений: нет (проверено `git status`).
- 2026-10-15 (A0): dry-run/--only-detect install_vostok.sh sudo-пароль не требуют и вне tmp не пишут при env PRINTER_DATA/LOG_FILE/DEVICES_FILE/BUILD_DIR/FIRMWARE_DIR/HOME/BYID_DIR; но preflight делает git ls-remote (нужна сеть; в harness заглушка), а show_usb_state читает /dev/serial/by-id хоста в обход BYID_DIR (нормализуется). Подробности: reports/harness.md.
- 2026-10-15 (A1): уточнения контрактов (предложение оркестратору, подробно в reports/core.md): VostokError/FlashError/UserAbort живут в `vostok/__init__.py` (ui реэкспортирует UserAbort); настройки ui — `ui.opts` (не `options`: конфликт с параметром `ask_choice`); `Runner.systemctl/sudo_keepalive` — методы, `can_manage_services(allow_sudo)` — функция модуля; `cfgfile.sections()` возвращает `Section`, результаты утилит — `Result.line()`; `can_uuid` — отдельный модуль `vostok/can_uuid.py`; `python3 -I -m vostok` не работает (-I отключает cwd/PYTHONPATH), обёртки должны вызывать `PYTHONPATH=<installer> python3 -m vostok`. Старые tools/*.py и lib/*.sh не менялись.
- 2026-10-15 (оркестратор): принято уточнение контрактов A1 (CONTRACTS.md): обёртки вызывают `PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok <cmd>`, без `-I`; состояние ui — `ui.opts`; Runner.systemctl/sudo_keepalive — методы. Открытые вопросы A1: строгая UTF-8 при чтении include (оставить `replace`), `re.escape` в module_state (оставить, осознанное исправление), путь .bak из merge_mcus (A4 решает), `test_boards` ~10 с (приемлемо).
- 2026-10-15 (конец дня): влиты A0 и A1 в `py-migration`. Следующий шаг на завтра: (1) по желанию R по волнам 0–1 (`prompts/R-reviewer.md`, отчёт `reports/review-wave1.md`), (2) волна 2: A2 ‖ A3 ‖ A4 параллельно по `prompts/A2-…A4-….md` (в промпт добавить: worktree может стоять на main, сразу `git checkout -b py/<имя> py-migration`; обёртки вызывают `PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok <cmd>`; golden после замены своей обёртки переснимать нельзя без согласования). Старые worktree агентов в `.claude/worktrees/` можно удалить (`git worktree remove`), ветки `py/harness`, `py/core` влиты. Не запушено.

- 2026-10-16 (решение пользователя): ветки `add-installer` и `docs-verified-boards` не трогаем, работаем только в `py-migration` (база 1.3a). Изменения 1.3b (`168b26f`: `board_rank`, `VERIFIED=yes` у h36-v1.3/v2, ebb42 «EBB42/EBB36» + алиас `ebb36`, manta-m8p-v2.0, docs/CHANGELOG) переносятся в Python-архитектуру отдельным шагом S6 после S5. Golden-эталоны остаются на 1.3a. В A4 выбор платы по умолчанию оформить одной функцией — точкой расширения под `board_rank`.
- 2026-10-16 (оркестратор): влиты A3, A2, A4 (157+ тестов, golden 234/0). Намеренно переснят один эталон `boards/bad_args`: без tty bash печатал мусор (`/dev/tty: No such device`, `ans: unbound variable`), теперь `ОШИБКА: нужен терминал…`, код выхода тот же. `PYTHONDONTWRITEBYTECODE=1` оставлен (обёртки + golden_lib). Fluidd-тема с `-y` и чужой темой по-прежнему заменяется (1:1 с 1.3a). Временный `lib/update_legacy.sh` удалить в A5/A6. A5: добавить в `Runner.run` параметры `quiet`/`stdout_file`; USB/DFU/CAN-функции из `configurator.py` (byid_find, dfu_*, show_usb_state…) решить, переносить ли в `hardware.py`; `LEGACY_BOARD_NAMES` в `electronics.py` удалить, когда в `.board` появятся поля (S6/1.3b). Дальше: R по волне 2 (по желанию), затем A5.
- 2026-10-16 (A5): `install_vostok.sh` перенесён на Python (`install.py`, `host.py`, `flashing.py`), загрузчик - 60 строк; замечания ревью H1/M1/M2/M4/L1 закрыты первым коммитом, M3 - вторым (отдельно, можно откатить). Удалены `lib/update_legacy.sh`, `lib/vostok_config.sh`; `tools/gen_electronics.py` - обёртка (нужна golden gen_matrix). Golden: 232/234, не пересняты `install/dry_no_tty_no_y` (bash печатал `/dev/tty: No such device`, как в уже согласованном `boards/bad_args`) и `boards/bad_args` (из-за M3). Продолжить с: решение оркестратора по пересъёмке (`tests/run_golden.sh --update boards/bad_args install/dry_no_tty_no_y`), слияние `py/install-flow` -> `py-migration`, затем A6 (docs, `tools/gen_configs.py`, `lib/boards.sh`, `tools/mcu_merge.py|pin_conflicts.py|can_uuid.py`, `VERSION`, ссылки на удалённые файлы в docs/CONFIGURATOR/CHANGELOG/AGENTS).
- 2026-10-16 (оркестратор): влит A5 (py/install-flow). Переснято 2 эталона (boards/bad_args — M3, install/dry_no_tty_no_y — M4; без tty вместо мусора bash одна строка «ОШИБКА: нужен терминал…», код 1). Дальше: A6 cleanup-docs (docs/CONFIGURATOR/CHANGELOG/AGENTS.md ссылаются на удалённые lib/*.sh, lib/boards.sh, tools/gen_configs.sh→.py, VERSION 1.4), итоговый R, затем S6 (перенос 1.3b). Юнит-тесты после слияния A5 мной не прогонялись (у A5: 402, 4 skip).
- 2026-10-16 (A6): `tools/gen_configs.sh` -> `.py`, удалены `lib/` и `gen_configs.sh`, доки/AGENTS/CHANGELOG обновлены, VERSION 1.4. Чтобы golden остался 234/0, песочница harness подставляет `VERSION=1.3a` (`GOLDEN_VERSION` в tests/golden_lib.py). Старые `tools/{mcu_merge,pin_conflicts,can_uuid}.py` - тонкие обёртки (нужны golden). Продолжить с: слияние `py/cleanup-docs` -> `py-migration`, итоговый R, S6 (перенос 1.3b), затем удаление `migration/` отдельным коммитом по команде оркестратора.
