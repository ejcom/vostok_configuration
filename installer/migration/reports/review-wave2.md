# Ревью волн 0-2 (harness, core, update, integrations, configurator)

Ревьюер R, 2026-10-16. Ветка `py-migration`, HEAD `919d0d8`. Только чтение (кроме этого файла).

## Что проверено

- `python3 -m unittest discover installer/tests`: 246 тестов, OK (148 с).
- `installer/tests/run_golden.sh`: 234 эталона, расхождений 0.
- Сверка MAP.md с кодом для волн 0-2: все строки со статусом `done` имеют существующий Python-эквивалент; `todo` оставлены только для A5/A6 (install_vostok.sh, `family_name`/`uid_addr`/`dfu_read_uid`/`bridge_usb_serial`/`print_boards`, `tools/gen_configs.sh`). Потерянных ветвей update/button/themes/configure не найдено.
- Построчная сверка `update_klipper_mcu.sh` (до 396579c) с `update.py`: `--list`, `--no-update`, `--no-flash`, `--force-flash`, `--git-update` (в том числе автовключение без tty), `--ignore-moonraker`, `-y`, `-V`, `-h`, коды возврата, тексты, порядок прошивки USB/extra/main, ветка моста USB-CAN, журнал flashed.tsv - совпадают. `install_fluidd_button.sh` (установка, `--uninstall`, `--with-macro`, `--dry-run`, polkit через `can_manage_services(False)`) совпадает. Темы Fluidd и KlipperScreen совпадают по ветвям (в т.ч. `-y` не заменяет чужую тему KlipperScreen).
- Python 3.8: запрещённых конструкций (`removeprefix`, `list[str]` вне аннотаций, `|` для типов, `:=` и т.п.) не найдено, только stdlib. Фактически проверить на 3.8 нельзя: на хосте только 3.9.2.
- eval/`shell=True`/`os.system`: нет. Запись cfg - через `cfgfile.atomic_write` (tmp + rename, права сохраняются), `.bak` в `merge_mcus`, `edit_fluidd_cfg`, `edit_ks_conf`, `_write_config`.

Вердикт по критичности: блокирующих дефектов нет; есть одно замечание, которое надо закрыть в начале A5 (H1).

## Замечания

### H1. Высокая (закрыть в начале A5): subprocess вне `system.Runner`, мимо dry-run

- `installer/vostok/firmware.py:236-243` (`_make`): `subprocess.call(["make", ...])` напрямую, без Runner. Dry-run его не замечает.
- `installer/vostok/hardware.py:331-338` (`run_quiet`) и `hardware.py:379-381` (`ifup`: `sudo -n ifup`): прямой `subprocess.run`; `ifup` меняет состояние и игнорирует `--dry-run`. `run_quiet` используется в `update.py:302` (`_git`), `:357` (проверка pyserial), `:623` (`systemctl list-unit-files`) и в `hardware.can_iface_up/exists`.
- `update.py:15`: `import subprocess` не используется.
- Сценарий сбоя: A5 вызовет `firmware.build_firmware` и `hardware.ifup` из `install --dry-run` (или в тестах). Установщик реально соберёт прошивку (минуты, пишет в `build/`, затирает `configs/*.config` через `shutil.copyfile(work/.config, cfg)` на `firmware.py:281`) и выполнит `sudo -n ifup`. В bash 1.3a эти действия шли через `run` и в dry-run только печатались. Контракт CONTRACTS.md ("единственное место с subprocess") нарушен, перехват в тестах разнородный.
- Предложение: расширить `Runner.run` параметрами `quiet` (stderr в DEVNULL), `stdout_file`/`append` и `readonly` (выполнять и в dry-run, для запросов вроде `git rev-parse`, `ip link show`). Перевести на них `_make`, `run_quiet`, `ifup`. Тогда `ifup` и `make` в dry-run только печатаются, а чтение работает. Это уже записано в STATUS.md как пункт для A5; здесь подтверждаю его обязательность.

### M1. Средняя: необработанные исключения оставляют Klipper остановленным без подсказки

- `installer/vostok/cli.py:303-310` ловит только `VostokError` и `KeyboardInterrupt`; `Updater.run` (`update.py:758-850`) не имеет `try/finally`. В bash 1.3a ловушки в update тоже не было (parity), но в Python добавились новые пути исключений: `shutil.copyfile` в `post_update_checks` (`update.py:537-538`, в bash `cp -n` ошибку молча глотал), `int(...)` в `pending_commits` (`:526`), копирование в `build_firmware` (`firmware.py:259-262, 280-281`), `p.get` на не-словаре в `integrations.edit_fluidd_cfg` (`integrations.py:~362`: `[p for p in lst if p.get("name") ...]`).
- Сценарий: кнопка Fluidd, Klipper остановлен (`klipper_stopped=True`), `OSError` (диск полон при сборке) -> traceback в журнал systemd, код 1, Klipper не запущен, пользователь в Fluidd не видит причины. Для install_vostok.sh (`cleanup`, строки 224-232) подсказка про остановленный Klipper есть, для update - нет.
- Предложение: в `cli.main` добавить `except OSError as e` и общий `except Exception` -> `ui.error(...)` + `ui.log(traceback)`, код 1. В `Updater.run` обернуть этап после остановки в `try/finally`: при ошибке и `klipper_stopped` напечатать "Klipper остановлен ... sudo systemctl start klipper" (а лучше попытаться `services("start")` при сбое сборки до начала прошивки; после начала прошивки не запускать автоматически - как сейчас в bash).

### M2. Средняя: `DevicesFile.save` не атомарна

- `installer/vostok/state.py:230-235` пишет `devices.tsv` через `open(path, "w")`. `FlashedLog.set` (`:260-275`) атомарна, `DevicesFile.save` - нет. A5 будет вызывать `save` из `save_devices` во время установки; файл читают update, кнопка Fluidd и сервис mcu-update (обрыв записи даёт пустой или усечённый файл -> `add_mcu` берёт `<чип>.config` вместо конфига платы, т.е. прошивка не той платы для чипов с несколькими платами).
- Предложение: тот же приём tmp + `os.replace`, что в `FlashedLog.set` (вынести общий `_atomic_write_text` в `state.py` или использовать `cfgfile.atomic_write(backup=False)`).

### M3. Средняя: `configure --printer-data <нет каталога>` создаёт каталог и мёртвая проверка

- `installer/vostok/configurator.py:1325-1326`: `env.effective_log_file.parent.mkdir(parents=True)` выполняется до `if not env.printer_data.is_dir()` (строка 1328). Комментарий признаёт: проверка "почти не срабатывает". Это перенос поведения bash, но дефект тот же.
- Сценарий: опечатка `--printer-data ~/printer_dta` создаёт `~/printer_dta/logs/` и конфигуратор идёт дальше, спрашивает железо и пишет `~/printer_dta/config/...`.
- В `919d0d8` эталон `boards/bad_args` переснят из-за смены вывода без tty; саму эту ветку "нет каталога" эталон не защищает.
- Предложение: проверять `is_dir()` до `mkdir` журнала (журнал в этом случае писать не нужно); добавить тест на "нет каталога" с кодом 1.

### M4. Средняя: `need_tty`/`confirm` считают терминал доступным, когда его нет

- `installer/vostok/ui.py:105-108` и `:165` используют `os.access("/dev/tty", os.R_OK)`. Узел `/dev/tty` существует и читаем и без управляющего терминала, поэтому проверка проходит, затем `_read_tty` (`:111-119`) падает на `open`. В эталоне `boards.txt` это видно: `Номер [по умолчанию: ...]: ОШИБКА: нужен терминал...` в одной строке (подсказка выведена до ошибки). В bash та же слабость (`[[ -r /dev/tty ]]`), т.е. parity, но для `confirm` текст ошибки теперь другой, чем в bash ("нет терминала для подтверждения, используйте -y" ожидается; при отсутствии ctty будет "нужен терминал: установка просит переключать платы...").
- Сценарий: `systemd`/кнопка/cron без `-y`, дойдя до `ui.confirm`: пользователь видит сообщение про платы вместо подсказки "используйте -y".
- Предложение: использовать `have_tty()` (реальный `open`) в `need_tty` и `confirm`; в `_read_tty` при `OSError` бросать исключение с текстом, соответствующим вызвавшей функции. Править до A5: install использует `ask_yn`/`pause_hw` в десятках мест, и golden для `-y` без tty должен остаться.

### M5. Средняя (процесс): двойная реализация до конца A5

- `installer/lib/update_legacy.sh` (788 строк) и `installer/lib/vostok_config.sh` (stage_config, heredoc правки printer.cfg, `merge_mcus_into_cfg`, `module_add_include`) остаются и используются `install_vostok.sh` через `source`. Исправления в Python (M2-M4) в install не попадут, а расхождения между двумя копиями уже есть (например, bash-ветка использует heredoc вместо `cfgfile.rewrite_printer_text`).
- Предложение: A5 не должен оставлять install на старых функциях ни для одного этапа; в Definition of Done A6 проверить, что `grep -r "update_legacy\|vostok_config.sh" installer` пуст. Тест "install_vostok.sh больше не source-ит lib/*.sh" добавить в A5.

### L1. Низкая: `sudo_keepalive` в dry-run пропускает проверку наличия sudo

- `installer/vostok/system.py:127-131`: при `dry_run` сразу `yield`; в bash `start_sudo` (install_vostok.sh:215-222) сначала `command -v sudo || die "нет sudo"`, и только затем пропускает пароль в dry-run/only-detect. Сценарий: хост без sudo, `--dry-run`: bash умирает, Python печатает план. Для A5 сохранить порядок bash (проверка sudo всегда, пароль и поток - только вне dry-run/only-detect); проверку вынести из ветки `dry_run`.

### L2. Низкая: `http_request` не ловит `http.client.HTTPException`

- `installer/vostok/integrations.py:146-150`: `except (URLError, OSError, ValueError)`. `http.client.BadStatusLine`/`IncompleteRead` (Moonraker перезапускается посреди ответа) - не `OSError`; кнопка завершится tracebackом вместо "Moonraker недоступен". `update.Moonraker.fetch` ловит `Exception` и не затронут. Заменить на `except Exception`.

### L3. Низкая: `_fetch_tarball` молча отбрасывает симлинки и хардлинки

- `installer/vostok/configurator.py:524`: `not (m.isfile() or m.isdir())` -> `continue`. `tar --strip-components=1` в bash распаковывал и ссылки. Если в репозитории конфигов появится симлинк (как `fluidd.cfg` в printer_data), он пропадёт без предупреждения. Либо предупреждать о пропуске, либо поддержать безопасные относительные симлинки.

### L4. Низкая: мелкие расхождения tsv и вывода

- `state.py:263`: `FlashedLog.set` выбрасывает пустые строки файла (awk `$1 != s` их сохраняет); `FlashedLog.get` (`:256`) не даёт пустой версии "перекрыть" предыдущую (awk перезаписывает `v` даже пустым `$2`). На рабочих файлах не проявляется (установщик пустых версий не пишет).
- `update.py:224-226` `_pad` дополняет по байтам UTF-8; в bash `printf '%-20s'` ведёт себя так в локали C (под systemd), но в UTF-8-локали терминала bash 5.1 может считать символы. Эталон снят в одной локали; не проверено в `ru_RU.UTF-8`. Влияет только на выравнивание таблицы `--list`.
- Обёртки `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh` не проверяют `command -v python3` (в `configure_vostok.sh` и `update_klipper_mcu.sh` проверка есть). Без python3 сообщение будет "python3: command not found". Для A5 (загрузчик) учесть: bootstrap ставит python3 до вызова этих обёрток.

## Соответствие критериям промпта

1. Потерянные ветви (--skip-board, --reflash, -y без tty, --check-can, --heads-flash, --main-flash, --git-update, --uninstall): в волнах 0-2 относятся к install (A5, статус `todo`) кроме `--git-update` (update.py:252, автовключение :267, ветка :801/:815, тесты `test_git_update_without_tty`, `test_flash_order_bridge_last_git_mode`) и `--uninstall` (button/theme/ks-theme, тесты есть). `-y` без tty: `ui.confirm/ask_yn/ask_choice` совпадают с bash, кроме M4. Потерь нет.
2. Флаги, env, коды возврата, форматы: совпадают (`USAGE` update/configure/button/theme/ks-theme побайтно сверены golden `--help`; форматы devices.tsv/flashed.tsv/.board не менялись; тест парсера `.board` повторяет ошибки bash).
3. subprocess вне Runner: H1. eval/shell=True: нет. Запись вне ожидаемых путей: нет (только `printer_data/config`, `firmware/`, `build/`, `configs/*.config`, журнал, `/etc/systemd/system` через sudo install). Атомарность: `atomic_write` везде, кроме `DevicesFile.save` (M2) и копирования файлов в `_write_config` через `shutil.copy` (`configurator.py:1110-1125`: оборвётся - останется `.bak`, но не атомарно; низкий риск, `printer.cfg` затем всё равно переписывается атомарно).
4. Python 3.8 и stdlib: без замечаний (не проверено на 3.8 фактически).
5. Избыточная декомпозиция: нет. Мелкие модули (`cli.py` 35 строк, `can_uuid.py` 72, `hardware.py` 102, `firmware.py` 151) оправданы как места расширения A5. `configurator.py` 1348 строк и `integrations.py` 1060 строк - крупные, но связные.
6. Тесты: покрывают не только счастливый путь (отказ подтверждения, обрыв прошивки, мост без katapult, перезаписанный upstream, локальные коммиты, грязное дерево, чужие темы, `-y` без tty). Пробелы: нет тестов на "нет каталога" в configure (M3), на необработанные исключения в `Updater.run` (M1), на `DevicesFile.save` при сбое записи (M2), на `http_request` с `HTTPException` (L2).

## Вердикт

**A5 можно начинать** после закрытия H1 (расширить `Runner` и перевести `_make`/`run_quiet`/`ifup`) и желательно M4 (`have_tty`) и M2 (атомарный `DevicesFile.save`): это три небольших правки в `system.py`, `ui.py`, `state.py`, `hardware.py`, `firmware.py` и их можно сделать первым коммитом A5 перед переносом `install`. M1, M3, L1-L4 не блокируют и могут пойти параллельно или в A6; L1 учесть при переносе `start_sudo`. Тесты (246) и golden (234/0) зелёные.
