# Отчёт A6 cleanup-docs (ветка py/cleanup-docs от py-migration 413b922)

## Что сделано (коммиты)
1. `tools/gen_configs.sh` -> `tools/gen_configs.py` (stdlib; использует `vostok.boards.Registry`). Все функции из MAP.md перенесены (`gen`, `clock_hz`, `hex_addr`, `can_lines`, `gen_klipper_cfg`, `gen_katapult_cfg`, `gen_all`, `sig`, ветки `--check`/`--build`). `.sh` удалён.
2. `lib/boards.sh` удалён (каталог `lib/` исчез). `tools/mcu_merge.py`, `pin_conflicts.py`, `can_uuid.py` не удалены, а стали тонкими обёртками (как `gen_electronics.py` в A5); в `vostok/cfgfile.py` добавлены `mcu_merge_main` и `pin_conflicts_main` (CLI прежних скриптов, `.bak` не создаётся). Причина: golden-эталоны `tools/mcu_merge`, `tools/pin_conflicts`, `tools/can_uuid` вызывают эти файлы по пути, а эталоны переснимать нельзя; доки и пользователи тоже ссылаются на эти команды.
3. Тесты: из `test_boards.py` убраны два парных теста с bash (`lib/boards.sh` больше нет), из `test_can_uuid.py` - сверка со старым скриптом (он стал обёрткой). В `test_install.py` проверка `-V` читает `VERSION`, а не литерал `1.3a`.
4. Документация: `docs/hardware*.md` (состав каталога: `vostok/`, `tests/` вместо `lib/*.sh`), `docs/build-configs*.md`, `docs/tested*.md`, `CONFIGURATOR*.md` (раздел «Устройство» и «Как расширять» указывают на `vostok/configurator.py`, `electronics.py`, `cfgfile.py`), `../AGENTS.md`, комментарии в `boards/*.board` и `vostok/boards.py`/`firmware.py` (текст ошибки «создайте: tools/gen_configs.py»). Публичные команды в документации не менялись. CHANGELOG ru/en: новая секция 1.4 (перенос на Python без изменения поведения + мелкие отличия из reports/*.md); старые записи (1.3a и ранее) оставлены как история. `VERSION` = 1.4.
5. `migration/MAP.md`, `migration/STATUS.md`, этот отчёт. Каталог `migration/` не удалялся (только по команде оркестратора).

## Намеренные отличия
- `gen_configs.py --help` печатает `tools/gen_configs.py` и `vostok/boards.py` вместо `.sh`/`lib/boards.sh` (иначе текст идентичен). Заголовок таблицы `--build` выровнен по байтам, как это делал bash-`printf` (проверено побайтово на `--build --board h36-v1.3`).
- Если у платы-головы `CAN_KIND` не `mmenu|direct`, сообщение в stderr и продолжение без CAN-строк сохранены как в bash (процесс-подстановка не прерывала скрипт).
- Диагностика `--check` использует системный `diff` (как bash), порядок сортировки строк - по кодам символов (bash `sort` зависит от локали, на значимые ключи это не влияет).
- Harness: песочница golden записывает в свою копию `VERSION` значение `1.3a` (`GOLDEN_VERSION` в `tests/golden_lib.py`), иначе `VERSION=1.4` меняет 44 эталона (строка «VOSTOK installer 1.3a» в `-V`/справке/журналах). Сами эталоны не тронуты.
- Сообщение `нет конфига katapult: … (создайте: tools/gen_configs.sh)` теперь указывает на `.py` (скрипта `.sh` нет); в golden этот текст не встречается.

## Проверки
- `python3 -m unittest discover installer/tests`: 399 тестов, OK (4 skipped); было 402 у A5, минус 3 удалённых парных теста.
- `installer/tests/run_golden.sh`: 234 эталона, расхождений 0 (после удаления `lib/`, `gen_configs.sh` и при `VERSION=1.4`). Эталоны не переснимались.
- `tools/gen_configs.py --check`: «проверено: 41, расхождений: 0» (36 конфигов + 5 пресетов пинов), вывод побайтово равен `gen_configs.sh --check`. `--force` в копии каталога: все 36 конфигов побайтово совпадают с результатом `gen_configs.sh --force` (вывод скриптов тоже). Коды выхода 2 для `--board nosuch`, `--bad`, `--board` без аргумента совпадают. `--build --board h36-v1.3` равен по выводу bash-версии.
- Расхождение конфигов каталога с генерацией только в `CONFIG_KATAPULT_VERSION` (строка версии, не значимый ключ) - это и в bash.
- Потребители перед удалением (grep): `lib/boards.sh` - только `tests/test_boards.py` и комментарии; `tools/gen_configs.sh` - docs, AGENTS, `vostok/firmware.py` (текст ошибки), комментарии `*.board`; `lib/vostok_config.sh` уже удалён A5, остались лишь упоминания в комментариях/историях (CHANGELOG, `legacy_*` фикстуры, docstring'и «бывшие …») - они намеренно оставлены.

## Открытые вопросы
1. `tools/mcu_merge.py|pin_conflicts.py|can_uuid.py` оставлены как обёртки ради golden; их можно удалить вместе с тремя эталонами `tools/*` и парными тестами в `test_cfgfile.py` только решением оркестратора (потребуется пересъёмка).
2. `gen_configs.py --build` не прогонялся целиком (долгая сборка всех 36 конфигов), только на одной плате.
3. Для S6 (1.3b): `board_rank`, `ebb42`+алиас `ebb36` и т. п. переносятся в `vostok/boards.py`/`configurator.py`; `gen_configs.py` работает через `Registry`, ничего отдельно менять не должен. После S6 обновить в `CHANGELOG` 1.4/1.3b и `GOLDEN_VERSION` не потребуется.
4. `migration/` удалить последним коммитом по команде оркестратора; в `STATUS.md`/`MAP.md` тогда ссылки уйдут вместе с каталогом.
