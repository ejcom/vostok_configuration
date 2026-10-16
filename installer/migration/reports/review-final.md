# Итоговое ревью миграции (A0-A6)

Ревьюер R, 2026-10-16. Ветка `py-migration`, HEAD `9b6bcbc`. Только чтение (кроме этого файла). Сверка с bash 1.3a: `git show e31499e:installer/install_vostok.sh` (1809 строк) и `lib/vostok_config.sh`, `update_klipper_mcu.sh`.

## Что проверено

- `python3 -m unittest discover installer/tests`: 399 тестов, OK (4 skipped), 79 с.
- `installer/tests/run_golden.sh`: 234 эталона, расхождений 0.
- Построчная сверка install_vostok.sh 1.3a с `install.py`, `flashing.py`, `host.py`, `hardware.py`, `firmware.py`, загрузчиком `install_vostok.sh`: функции, порядок этапов, ветви, тексты, коды выхода, `devices.tsv`/`flashed.tsv`.
- Автоматическая сверка русских строк bash с `vostok/*.py`: не найдено строк, потерянных по существу (остались только комментарии, шаблоны с `$1` и сознательно изменённое `tools/gen_configs.sh` -> `.py`).
- Прогон в песочной копии `installer/` (HOME, PRINTER_DATA, BYID_DIR во временном каталоге): `--dry-run -y --heads v2 --main h723 --alps 1`, `--check-can --dry-run -y`, `--skip-board heads --skip-board main --heads-flash can --main-flash katapult`, `--only-detect`, ошибки аргументов (`--bogus`, `--heads x`, `--skip-board foo`, `--main` без значения): коды 0/1 и тексты ожидаемые. Побочный эффект dry-run найден (N1).
- Python 3.8: `ast.parse(feature_version=(3,8))` проходит для `vostok/*.py`, `tools/*.py`; запрещённых вызовов (`removeprefix`, `is_relative_to`, `list[...]` вне аннотаций и т. п.) нет; везде `from __future__ import annotations`; только stdlib. Реально на 3.8 не запускалось (на хосте 3.9.2).
- `eval`, `shell=True`, `os.system`, `os.popen`: нет.

## Потерянные ветви (пункт 1)

Все ветви на месте, потерь не найдено; тесты есть на каждую:

| ветвь bash | Python | тесты |
|---|---|---|
| `--skip-board alps\|alps0\|alps1\|main\|heads` (повтор опции, валидация) | `install.py:107-165` (разбор), `alps_try_skip`/`heads_try_skip`/`main_try_skip` | `test_forced_*`, `test_usb_forced`, `test_forced_without_device_warns` |
| `--reflash` (отключает автопропуск, но не `--skip-board`) | те же функции, `if not forced and o.reflash` | `test_reflash_disables_auto_skip_but_not_forced` |
| автопропуск по версии (`flashed.tsv` + вопрос y) | `version_ok` + `ask_yn` | `test_auto_skip_needs_version_and_confirmation`, `test_auto_can_way_needs_bus` |
| `-y` без tty: меню неудачи даёт skip, `pause_hw` требует tty, `choose_heads_flash` берёт dfu | `flash_menu`, `ui.pause_hw`, `choose_heads_flash` | `test_no_tty_or_yes_skips_after_failure`, `test_dfu_failure_with_yes_skips_board_and_continues`, `test_auto_dfu_way` |
| `--check-can` (root-проверка, чтение devices.tsv, имена голов из printer.cfg, останов Klipper, сопоставление плат) | `check_can_main`, `check_can_uuids`, `write_uuid_to_cfg` | `test_all_found`, `test_one_wrong_uuid_is_replaced_by_the_free_one`, `test_all_unknown_walks_user_through_it`, `test_check_can_main_*`, `test_check_can_flow_and_root` |
| `--heads-flash dfu\|can`, `--main-flash dfu\|katapult` | `choose_heads_flash`, `stage_flash_main`, `stage_flash_heads_*` | `test_heads_katapult_and_dfu_stages`, `test_flash_main_way_selection`, `test_main_dfu_all_session`, `test_main_katapult_then_klipper` |
| меню retry/dfu/dfuall/dfuk/skip/abort и вариант headsdfu | `flash_menu`, `flash_with_retry` | `test_menu_mapping_and_no_tty`, `test_menu_dfu_dfuall_dfuk_set_phase`, `test_abort`, `test_skip_records_failure_and_continues` |
| ответ `s`/`ы` на запросе DFU (katapult уже на плате) | `enter_katapult`, `HeadKatapult` | `test_enter_skip_*` |
| `--list-boards`, `-V`, `-h`, неизвестная опция (справка в stderr, код 1) | `parse_args` | `test_help_version_list_are_immediate`, golden `help.txt`, `boards.txt` |
| `--upgrade`, `--skip-software/-flash/-config/-button/-theme`, `--only-detect`, `--dry-run` | `run`, `stage_packages` | `test_skip_flags`, `test_only_detect_stops_after_plan`, `test_dry_run_does_not_ask`, `test_packages_*` |

Побайтово сверены: `USAGE` (golden `help.txt`), план, итоги, тексты меню и подсказок DFU, формат строк devices.tsv (`ключ\tконфиг\tроль`, без заголовка), flashed.tsv (`ключ\tверсия`), порядок этапов (`dfu`: ALPS -> головы -> главная -> проверка UUID; `can`: ALPS -> katapult голов -> главная -> Klipper голов), `FINISH_RC` (1 при `res.failed`, нет Moonraker, ошибке кнопки/темы, `verify_versions`), `rc` при `die` (1) и Ctrl+C (130).

## Закрытие замечаний review-wave2.md

| № | статус | где проверено |
|---|---|---|
| H1 subprocess вне Runner | закрыто | `grep subprocess vostok/*.py` даёт только `system.py`; `Runner.run` получил `quiet`, `stdout_file`, `append`, `readonly`; `_make`, `run_quiet`, `ifup`, `can_uuids`, `dfu_read_uid` идут через него; `build_firmware`/`build_katapult` в dry-run не создают каталоги и не трогают конфиги (`firmware.py:101`, `:186`). Остаток: N6 |
| M1 исключения оставляют Klipper остановленным | закрыто | `cli.py:43` (общий `except Exception` -> `ОШИБКА` + traceback в журнал), `update.py:759-763` (подсказка про остановленный Klipper), `install.py:_klipper_hint` |
| M2 `DevicesFile.save` не атомарна | закрыто | `state.py:19-35,64-66` (tmp + `os.replace`, права сохраняются) |
| M3 `configure --printer-data` создаёт каталог | закрыто | `configurator.py:1262` (проверка до `mkdir` журнала) |
| M4 `need_tty`/`confirm` | закрыто | `ui.py:96-120` (`have_tty` открывает `/dev/tty`), `confirm` проверяет `have_tty` |
| M5 двойная реализация | закрыто | `lib/` нет; `test_loader_is_thin_and_has_no_legacy_sources`; упоминания `lib/*.sh` остались только в CHANGELOG (история) и docstring'ах |
| L1 sudo в dry-run | закрыто | `system.py:147`: наличие sudo проверяется всегда, пароль и поток только вне dry-run/only-detect |
| L2 `http_request` и `HTTPException` | НЕ закрыто | `integrations.py:149`; смягчено общим `except Exception` в `cli.py`, но вместо «Moonraker недоступен» будет `ОШИБКА: BadStatusLine: ...` и код 1 |
| L3 `_fetch_tarball` отбрасывает ссылки | НЕ закрыто | `configurator.py:461`, без предупреждения |
| L4 `_pad` по байтам; обёртки без проверки python3; `FlashedLog` | НЕ закрыто, сознательно | `update.py:223` без изменений; `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh` без `command -v python3` |

## Замечания

### N1. Средняя: `--dry-run` пишет в `firmware/flashed.tsv`

- `flashing.py:733` (`make_head_dfu_job.commit`) вызывает `fl.state_set(o.uuid)` без проверки dry-run; в dry-run `dfu_read_uid` возвращает `000000000000` (`hardware.py` `dfu_read_uid`), и `Flasher.state_set` (`flashing.py:133-135`) через `FlashedLog.set` перезаписывает `installer/firmware/flashed.tsv`.
- Сценарий: `./install_vostok.sh --dry-run -y --heads v2 --main h723` (путь по умолчанию, `--heads-flash dfu`). Проверено в копии: файл `flashed.tsv` изменился, в него добавилась строка `000000000000\t<версия хоста>`. Это перенос поведения bash (`state_set` там тоже не защищён), но противоречит «dry-run ничего не меняет». В рабочем каталоге `installer/firmware/flashed.tsv` уже есть такая строка (`000000000000	v0.7.0-4757-g02fa9fed`): мусор от прежних dry-run. Вреда сейчас нет (реальный UUID не бывает нулевым), но записи накапливаются, а `update` показывает их как «известные» ключи.
- Почему не поймали: `golden_lib.py:178` исключает `firmware`, `build`, `devices.tsv` из снимка `installer/`, поэтому проверка «не пишем вне временных каталогов» их не видит.
- Предложение: `if self.dry: return` в начале `Flasher.state_set`; тест «dry-run с `--heads-flash dfu` не меняет flashed.tsv»; в harness снимать `firmware/` и `devices.tsv` (создавать пустыми в песочнице, а не исключать); строку `000000000000` из живого `flashed.tsv` убрать вручную (данные пользователя, ревьюер не трогал).

### N2. Низкая: `--check-can` меняет `printer.cfg` без `.bak` и молча глотает ошибки записи

- `install.py:695-705` (`write_uuid_to_cfg`) вызывает `cfgfile.set_canbus_uuid(..., backup=False)` (`cfgfile.py:177`), хотя комментарий bash-версии обещал «бэкап перед записью» (в bash его фактически не было: parity, но правило «запись cfg атомарна с .bak» не выполнено). Атомарность есть (`atomic_write`).
- `except (VostokError, OSError): return` (`install.py:702`, `:715`): при сбое записи (диск, права) дальше печатается `canbus_uuid подтверждены на шине` (`install.py:806`), код 0.
- Сценарий: `printer.cfg` недоступен на запись, пользователь видит «подтверждены», а UUID в конфиге старый/`ЗАПОЛНИТЕ`.
- Предложение: `backup=True` для `--check-can`; при `OSError` печатать `ui.warn("не удалось записать printer.cfg: ...")` и возвращать флаг неудачи (`finish_rc = 1`).

### N3. Низкая: L2 и L3 из прошлого ревью остались открытыми

- `integrations.py:149`: заменить `except (URLError, OSError, ValueError)` на `except Exception` (или добавить `http.client.HTTPException`).
- `configurator.py:461`: символические и жёсткие ссылки из архива молча пропускаются; предупредить через `ui.warn`/`ui.log` либо поддержать безопасные относительные ссылки.

### N4. Низкая: обёртки без проверки python3 и с разным `PYTHONDONTWRITEBYTECODE`

- `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh` (строка `exec`) не проверяют `command -v python3` (в `update_klipper_mcu.sh` и `configure_vostok.sh` проверка есть). Без python3: `python3: command not found`, код 127.
- `update_klipper_mcu.sh` и `configure_vostok.sh` не ставят `PYTHONDONTWRITEBYTECODE=1`, остальные ставят. Сервис mcu-update работает от пользователя и создаёт `installer/vostok/__pycache__` (в `.gitignore`, вреда нет, но поведение разное).
- `install_vostok.sh:60`: `PYTHONPATH="$INSTALL_DIR"` затирает PYTHONPATH пользователя; для stdlib-кода безвредно.
- Предложение: единый шаблон обёртки (проверка python3, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH="$INSTALL_DIR${PYTHONPATH:+:$PYTHONPATH}"`).

### N5. Низкая: лишняя ступень абстракции в `flashing.py`

- `flashing.py:560-570` (`class Strategy` с `NotImplementedError`), четыре подкласса (`DfuAll`, `DfuKlipperOnly`, `KatapultThenKlipper`, `HeadKatapult`, `CanKlipper`), `FlashJob` с замыканиями `select`/`commit` и `_by_phase` (`:679`). Поведение верное и покрыто тестами (50 тестов), но замыкания `lambda phase: HeadKatapult()` и словарь фаз сложнее, чем `if phase == ...` внутри четырёх функций. Не блокирует; упростить можно в S6 или не трогать (риск регресса выше выгоды). Мелких модулей по 20 строк нет (`cli.py` 48, `state.py` 96).

### N6. Низкая: subprocess и запись вне Runner/атомарности в инструментах

- `tools/gen_configs.py:25,88,198,258-261`: `subprocess.call/run` напрямую (`make`, `diff`). Это инструмент разработчика, не установщика, dry-run ему не нужен; допустимо, но противоречит формулировке «единственное место с subprocess» из CONTRACTS.md. Предложение: пометить исключение в CONTRACTS.md.
- `firmware.py:128-129`: `shutil.copyfile(work/.config, cfg)` перезаписывает отслеживаемый git файл `configs/*.config` после каждой сборки неатомарно (в bash так же: `cp`, строка 511 старого скрипта). Обрыв на записи оставит усечённый конфиг в рабочем дереве, которое пользователь обновляет через `git pull`. Предложение: `cfgfile.atomic_write(backup=False)` или запись только при отличии содержимого.

### N7. Информационно: журнал в dry-run

- `--dry-run` создаёт `$PRINTER_DATA/logs/vostok_install.log` (и каталог `logs`), как и bash. Допустимо; в документации «dry-run ничего не меняет» стоит добавить «кроме журнала».

## Ссылки в docs и AGENTS.md на несуществующие файлы

- Проверены все пути в обратных кавычках в `AGENTS.md`, `installer/README*.md`, `CONFIGURATOR*.md`, `docs/*.md`: на удалённые `lib/*.sh`, `tools/gen_configs.sh`, `update_legacy.sh` ссылок нет (остались только в CHANGELOG как история 1.3a и в docstring'ах «бывший …»). Несуществующими выглядят лишь шаблоны (`*.board`, `tmcNNNN.cfg`), внешние имена Klipper (`flashtool.py`, `canbus_query.py`, `generic-*.cfg`) и файлы, которые лежат в `postprocessing/` (`fast_tool_swaps.py`, `fix_toolchange.py`); к миграции они не относятся.
- `CHANGELOG.md:18` (запись 1.3a): `tools/gen_configs.sh --check`: исторически верно, правка не нужна.

## Тонкие обёртки `tools/{mcu_merge,pin_conflicts,can_uuid}.py` (и `gen_electronics.py`)

Кто вызывает (grep по репо без `migration/`, `.cfg`, `.service.in`, `.sh`, шаблонам, темам, макросам кнопки Fluidd, `~/klipper_mcu`):

- Из кода установщика, unit-файлов, скриптов `*.sh`, кнопки Fluidd, `printer_base.cfg`/`printer.cfg` не вызывает никто: `install.py` и `configurator.py` используют `vostok.cfgfile`/`vostok.can_uuid` напрямую.
- Остались только: документация как пользовательские команды (`docs/hardware*.md:77`, `CONFIGURATOR*.md:90,243,332`, `AGENTS.md:35`, CHANGELOG), golden-случаи `tools/mcu_merge`, `tools/pin_conflicts`, `tools/can_uuid` (`tests/golden_cases.py:265,289,309`, эталон `golden/tools.txt`), `gen_electronics.py` в `gen_matrix`/`electronics` golden (`golden_cases.py:235-256`) и два теста (`test_cfgfile.py`, `test_can_uuid.py`).
- Рекомендация: оставить как есть на S6 и финальные тесты (19 строк каждая, поведение закреплено эталонами и описано в документации как ручные утилиты, внешние пользователи могли вызывать по пути). Удалять только вместе с эталонами и правкой документации, отдельным решением; на корректность Python-установщика они не влияют.

## Соответствие критериям промпта

1. Потерянные ветви: нет (таблица выше).
2. Флаги, env, коды возврата, форматы, `--help`: совпадают (golden `help.txt` 234/0, тесты парсера). `-V` теперь печатает `1.4` (сознательно, harness подставляет `1.3a`).
3. subprocess вне Runner: нет (кроме N6); eval/shell=True: нет; запись вне ожидаемых путей: нет (`/etc/network/interfaces.d/can0` или `/etc/systemd/network/80-can0.*` через `sudo install`, `printer_data/config`, `klipper/klippy/extras` (gcode_shell_command), `kiauh.cfg`, `configs/`, `firmware/`, `build/`, `devices.tsv`, журнал); атомарность: `atomic_write`/`_atomic_write` везде, кроме N6 (копирование `configs/*.config`) и `kiauh.cfg` (атомарно, без .bak, осознанно); dry-run меняет файл: N1.
4. Python 3.8, stdlib: да (синтаксис проверен `ast`).
5. Декомпозиция: терпимо (N5).
6. Тесты: покрывают отказ подтверждения, обрыв прошивки, таймауты katapult, несколько katapult-плат, неверное семейство DFU, fallback без mass-erase, выход платы из DFU, мост без can0, меню, abort, skip, `-y` без tty, загрузчик без python3. Пробелы: dry-run не проверяется на запись в `firmware/` (N1), нет теста «`--check-can` при сбое записи printer.cfg» (N2), нет теста `HTTPException` (N3).

## Вердикт

Блокирующих дефектов нет. Миграция A0-A6 полна по ветвям и контрактам, юнит-тесты (399) и golden (234/0) зелёные, замечания H1, M1-M5, L1 прошлого ревью закрыты реально, а не формально.

**К S6 (перенос 1.3b): готово.** Условия на старте S6: закрыть N1 (одна строка `if self.dry: return` + тест + расширить снимок harness на `firmware/` и `devices.tsv`), иначе перенос 1.3b будет сверяться с harness, который не видит запись в `firmware/`.

**К финальным тестам на железе: готово после N1.** N2 и N3 желательно закрыть до первого запуска `--check-can` на собранном принтере (сбой записи `printer.cfg` не должен выглядеть как успех). N4-N7 не блокируют. Реальная проверка на Python 3.8 и прошивки/CAN на железе по-прежнему невозможны в этом окружении (хост 3.9.2, прошивка и sudo запрещены).
