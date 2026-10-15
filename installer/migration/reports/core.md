# Отчёт A1 core (ветка py/core)

Фундамент пакета `installer/vostok/`: `__init__` (исключения), `ui`, `system`, `boards`, `state`, `cfgfile`, `can_uuid`, `cli`, `__main__`. Этап аддитивный: старые `*.sh` и `tools/*.py` не менялись и не заменялись обёртками.

Коммиты: `f5c9ff1` (сигнатуры с докстрингами, заглушки), `de7ad66` (реализация), `5d29ef9` (тесты); затем MAP/STATUS/отчёт.

## Что перенесено (по MAP.md)
| bash / python-утилита | Python |
|---|---|
| `info/ok/warn/die/step/log_to_file` (все 4 скрипта) | `ui.info/ok/warn/die/step/log` (+ `ui.error` для печати `ОШИБКА:` из `cli.main`) |
| `have_tty/need_tty/ask_yn/ask_choice` | `ui.have_tty/need_tty/ask_yn/ask_choice` |
| `confirm` (update, button, обе темы) | `ui.confirm(q, need=True)`; темы без терминала возвращали «нет» -> `need=False` |
| `pause_hw` (install) | `ui.pause_hw` (ответ возвращается строкой, TMP_ANS не нужен) |
| `run` (install, button), dry-run | `system.Runner.run` (единственный subprocess) |
| `start_sudo` | `Runner.sudo_keepalive()` (контекстный менеджер, фоновый поток `sudo -n true` каждые 50 с) |
| `sctl` | `Runner.systemctl(action, unit)` |
| `can_manage_services` (update: pkcheck или `sudo -n`; button: только pkcheck) | `system.can_manage_services(allow_sudo=True)` |
| `lib/boards.sh` целиком | `boards.Board`, `Registry.get/ids/list/resolve/for_chip/for_family/has_bridge/cfg_path/by_cfg`, `registry()` (env `BOARDS_DIR`, `CONFIGS_DIR`, `KATAPULT_CONFIGS`) |
| `devices_lookup`, чтение/запись `devices.tsv` | `state.DevicesFile.load/save/lookup` |
| `state_get/state_set` (`flashed.tsv`) | `state.FlashedLog.get/set` (атомарно, tmp+rename) |
| `tools/mcu_merge.py` (`--list`, merge, `--set`) | `cfgfile.list_mcus`, `merge_mcus`, `set_canbus_uuid` |
| `tools/pin_conflicts.py` | `cfgfile.pin_conflicts` |
| heredoc `stage_config` | `cfgfile.rewrite_printer_text/rewrite_printer_cfg` |
| `cfg_state`, `module_state`, `module_add_include` | `cfgfile.cfg_state/module_state/module_add_include` |
| `.bak-<дата>` (`cp -p`) | `cfgfile.backup_file`, `atomic_write(path, text, backup=True)` |
| `tools/can_uuid.py`, `can_uuid_from_serial` | `can_uuid.fasthash64/can_uuid/main` (`can_uuid(bytes.fromhex(serial))`) |

Единый разбор: `read_with_includes` один, `sections()` один (хранит и упорядоченные `items` с дубликатами для pin_conflicts, и `opts` для mcu_merge). Строки результатов утилит — `Result(kind, name, args).line()` (TAB-формат прежний: OK/ADD/DIFF/TODO, SET/SAME/DIFF/NOSECTION, CONFLICT).

## Намеренные отличия
- `module_state`: имя файла в регулярном выражении экранируется (в bash `chamber_heater.cfg` с «.» совпадало бы с `chamber_heaterXcfg`). Тест `test_state_dot_is_literal` фиксирует.
- Ошибки Python-версии: нечитаемый/нестрого-UTF-8 printer.cfg в `merge_mcus/set_canbus_uuid` -> `VostokError("не удалось прочитать …")` вместо traceback старого `mcu_merge.py`.
- Запись файлов атомарная (tmp+`os.replace`, права сохраняются, симлинк правится по цели); раньше `open(...,"w")`. Резервная копия: `merge_mcus(backup=True)` делает `.bak-<дата>` сама и только если есть `ADD` (в bash это делал вызывающий через `cp -p`); `set_canbus_uuid` и `rewrite_printer_cfg` по умолчанию `backup=False` (как раньше: `--set` без копии, а `stage_config` делает общую метку времени для printer.cfg и electronics сам, через `cfgfile.backup_file(path, stamp)`).
- `ui.die` бросает `VostokError`; печать `ОШИБКА:` и код 1 — в `cli.main`. EOF на `/dev/tty` -> `UserAbort` (в bash `read` падал под `set -e`).
- `Runner.run(capture=True)` собирает stdout (stderr остаётся на экране, как у `$(...)`); `tee=True` выводит stdout+stderr и пишет строки в журнал. Нет команды -> код 127 (при `check=True` `CommandError`).
- `boards_preload` не нужен (ленивый кэш в `Registry`), `registry()` принимает те же env.

## Результаты проверок
- `python3 -m unittest discover installer/tests -k test_boards -k test_state -k test_cfgfile -k test_can_uuid -k test_ui -k test_system`: 71 тест OK (около 15 с; основное время — bash-сверка реестра, bash 1 раз разбирает все платы).
- Парные проверки «новое == старое»: `mcu_merge.py` (list, dry, запись, повтор, `--set` во всех ветках SET/SAME/DIFF/NOSECTION/`--force`, 4 варианта printer.cfg, сравнение вывода и байтов файла); `pin_conflicts.py` (сток, конфликты с include/probe/spi_software/дубли ключей, все user_configs и chamber_heater из фикстур); heredoc правки printer.cfg (текст heredoc берётся из `lib/vostok_config.sh` в момент теста, 7 вариантов × 2 формы blocks, байты равны); `module_state/module_add_include` (функции извлекаются из `lib/vostok_config.sh` и исполняются в bash, 8 вариантов + сток); `cfg_state` (grep-логика bash); `lib/boards.sh` (все поля, cfg, by_cfg, for_chip/family, resolve, тексты 9 ошибок формата); `awk` для devices/flashed.
- `can_uuid`: 8 векторов, посчитанных настоящим C-кодом `klipper/lib/fast-hash/fasthash.c` (gcc), 3 вектора из golden, 200 случайных UID == старому `tools/can_uuid.py`, другие длины fasthash64, CLI-ошибки и usage.
- `installer/tests/run_golden.sh` (полный): 234 эталона, расхождений 0 (старые скрипты не менялись; фильтры tools/boards/help входят в этот прогон).
- `python3 -I -c "import sys; sys.path.insert(0,'installer'); import vostok…"` работает (тест `test_isolated_import`).

## Предложения по уточнению контрактов (CONTRACTS.md меняет оркестратор)
1. Исключения: `VostokError`, `FlashError`, `UserAbort` определены в `vostok/__init__.py` (чтобы `boards`/`system` не зависели от `ui`); `from vostok import VostokError`, `ui.UserAbort` тоже доступен. Добавлено `boards.BoardError(VostokError)`, `system.CommandError(VostokError)` (атрибуты `returncode`, `stdout`).
2. `ui`: добавлены `log(msg)`, `error(msg)`, `die(msg)` (бросает `VostokError`), `need_tty()`, `confirm(q, need=True)`. Состояние — `ui.opts` (`yes/dry_run/log_file`); `ask_choice(q, default, options)` сохраняет имя параметра `options`, поэтому модульный объект назван `opts`.
3. `system`: `Runner(dry_run=None)` (None = брать `ui.opts.dry_run`), `run(cmd, *, sudo, check, capture, tee, env, cwd, timeout)`, `sudo(cmd, **kw)`, `capture(cmd) -> str`, `systemctl(action, unit) -> bool`, `sudo_keepalive(enabled=True)` — менеджер контекста; `can_manage_services(allow_sudo=True)` — функция модуля (не метод).
4. `boards`: `Registry(boards_dir, configs_dir=None, katapult_dir=None)`, `ids()` (все файлы, включая битые), `list(role)` (битые плат с ролью не попадают — как bash), `cfg_path` возвращает `None`, если конфига нет (в bash код 1), `resolve` -> `None`, `by_cfg` -> `(id, kind)` или `None`; `registry()` читает env. `Board.field(KEY)`, `Board.alias_list`; поля — строки как в файле (`verified` = "yes"/"no").
5. `state`: `DevicesFile.load/save/lookup`, `FlashedLog.get/set` как в контракте; `lookup` возвращает `Device` или `None`.
6. `cfgfile`: `sections(text) -> list[Section(name, items, opts)]`; `list_mcus(cfg)`; `merge_mcus(cfg, blocks_text, dry=False, backup=True) -> list[Result]`; `set_canbus_uuid(cfg, name, uuid, force=False, backup=False) -> Result`; `pin_conflicts(cfg) -> list[Result]`; `rewrite_printer_text` (чистая) и `rewrite_printer_cfg(path, electronics, blocks_text, backup=False)`; `module_state(cfg, file)`, `module_add_include(cfg, file, backup=False)`; `backup_file(path, stamp=None)`, `atomic_write(path, text, backup=True) -> Path|None`.
7. `can_uuid` — отдельный модуль `vostok/can_uuid.py` (в плане он значился внутри `electronics.py`/`hardware.py`). A4/A2/A5 импортируют `from vostok.can_uuid import can_uuid`.
8. Запуск обёрток: `python3 -I -m vostok` НЕ работает (`-I` отключает cwd и PYTHONPATH). Обёртки должны вызывать `PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok <команда> "$@"` (или `cd "$INSTALL_DIR"`). Импорт вида `python3 -I -c "import sys; sys.path.insert(0,'installer'); import vostok"` работает.
9. `cli.main(argv)`: команда не указана/неизвестна -> код 2 и сообщение в stderr; `COMMANDS` пока пуст (владельцы своих этапов добавляют строки). Служебных подкоманд `can-uuid`/`mcu-merge` не регистрировал (новых команд в плане нет); при необходимости строки `COMMANDS["can-uuid"] = lambda a: can_uuid.main(["can_uuid"] + a)` добавляются тривиально.

## Открытые вопросы
1. Нужна ли строгая UTF-8-проверка в `read_with_includes`? Сохранено прежнее поведение (`errors="replace"` для чтения include, строгий UTF-8 для правимого файла).
2. `module_state` теперь строже (экранированная точка); если нужно побайтовое повторение bash — убрать `re.escape` (одна строка).
3. Для A4: `merge_mcus_into_cfg` печатал ADD/OK/DIFF/TODO через `ok/info/warn` и «Резервная копия: …*» — это остаётся в вызывающем коде (у `merge_mcus` есть `Result` и путь копии можно получить через `backup_file`; `atomic_write` возвращает путь, но `merge_mcus` его наружу не отдаёт — при необходимости вернуть кортеж скажите оркестратору).
4. `python3 -m unittest` в `test_boards` ~10 с из-за bash-сверки; если мешает, можно пометить медленной или кэшировать.
