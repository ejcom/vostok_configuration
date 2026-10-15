# STATUS переноса установщика на Python

Ветка интеграции: `py-migration` (от `add-installer`). Агенты: ветки `py/<имя>`, worktree. Источник истины по плану: `PLAN.md`. Обновляет оркестратор после каждого агента.

## Агенты

| агент | ветка | статус | последний коммит | открытые вопросы | дата |
|---|---|---|---|---|---|
| A0 harness | py/harness | review | см. git log py/harness | 5 вопросов в reports/harness.md (нумерация A–H, 10 главных плат, требования к хосту) | 2026-10-15 |
| A1 core | py/core | todo | | | |
| A2 update | py/update | todo | | | |
| A3 integrations | py/integrations | todo | | | |
| A4 configurator | py/configurator | todo | | | |
| A5 install-flow | py/install-flow | todo | | | |
| A6 cleanup-docs | py/cleanup-docs | todo | | | |

Статусы: todo | in-progress | review | merged. Ревью (R) после волн 0–1, 2, 3, 4: отчёты в `reports/review-*.md`.

## Сессии

| сессия | содержание | статус |
|---|---|---|
| S1 | подготовка (каталог migration/) + A0 harness + R | подготовка выполнена 2026-10-15, A0 не начат |
| S2 | A1 core + R | todo |
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
