# Отчёт A4 configurator (ветка py/configurator)

Перенесены настройка конфига (`lib/vostok_config.sh`, `configure_vostok.sh`) и генератор (`tools/gen_electronics.py`).
База поведения: bash 1.3a (коммит `6808e7a`). `configure_vostok.sh` теперь обёртка:
`PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok configure "$@"` (без `-I`). Старые `lib/vostok_config.sh`,
`tools/gen_electronics.py`, `tools/mcu_merge.py`, `tools/pin_conflicts.py` не менялись: ими пользуется `install_vostok.sh`
(до A5) и golden-прогон `gen_matrix`.

Коммиты: `electronics.py`, `configurator.py` + обёртка + строка в `cli.py`, тесты electronics, тесты configurator, MAP + отчёт.

## Что перенесено (bash -> Python)

Полная таблица в `MAP.md` (колонки «Python» и статус заполнены). Коротко:

| bash | Python |
|---|---|
| `tools/gen_electronics.py` (глобалы `TABLE_OPTS`, `SVERIT`, `TABLE_SRC`; `main()` ~250 строк) | `vostok/electronics.py`: `Generator` (состояние прогона - поля объекта, `generate()` разбит на `_load_main_preset`, `_parse_driver_spec`, `_load_blank_template`, `_apply_presets`, `_driver_blocks`, `_fill_pins`, `_replace_other_pins`, `_render`, `_mark_empty_pins`), `GenOptions`, `GenResult`, `main()` с прежней командной строкой и протоколом `NAME/WARN/FILL/EMPTY` (`python3 -m vostok.electronics`) |
| `BOARD_NAMES`/`BOARD_FILE` h723/f446 | `electronics.board_naming(registry, main)`: плата находится через реестр (id или алиас), см. «Открытые вопросы» п. 4 |
| `detect_hardware`, `detect_main_board`, `main_candidates`, `prev_main_board`, `ask_board`, `check_main_bridge`, `main_board_from_opt`, `main_boards_hint` | `configurator.HardwareDetector` (+ `detect() -> Hardware`) |
| глобалы `MAIN_BOARD`, `MAIN`, `HEADS`, `ALPS_COUNT`, `MODE`, `HEAD_MCU` и функции `main_label/main_short/head_*/klipper_cfg_for_main/katapult_cfg_for_main/alps_side` | `configurator.Hardware` (dataclass; чип - свойство от реестра) |
| `byid_find`, `dfu_count`, `dfu_family`, `show_usb_state` (+ мост/CAN-проверки) | функции модуля `configurator` на `system.Runner` (`probe()`: stderr скрыт, работает и в dry-run) |
| `RES_*`, `collect_mcu_state`, `mcu_blocks`, `prev_keys` | `McuValues`, `Configurator.collect_mcu_state`, `mcu_blocks(hw, res)`, `Configurator.prev_keys` |
| `stage_config` (~140 строк), `pick_electronics`, `find_reference`, `gen_custom_electronics`, `print_gen_warnings`, `drivers_wizard`, `merge_mcus_into_cfg`, `sync_head_names`, `stage_modules`, `module_wanted`, `report_pin_conflicts` | методы `Configurator` (`stage_config` ~45 строк + `_config_root`, `_write_config`, `_finish_config`, `_dry_run_report`) |
| `guess_main_board`, `guess_from_printer_cfg`, `parse_args`, `usage`, `main` | `Configurator.guess_*`, `configurator.parse_args`, `USAGE`, `main` |
| глобалы `OPT_*`, `GEN_*`, `REF_*`, `EL_*`, `CFG_STATE`, `DRIVERS_SPEC` | `Options`, `Env`, поля `Configurator` (`gen: GenResult`, `ref_cfg/ref_kind`, `el_src/el_name`, `cfg_state`, `drivers_spec`) |

Правило «свой electronics-конфиг всегда основа» и `cfg_state none|blank|foreign|vostok` сохранены (`find_reference`,
`stage_config`; сама функция `cfg_state` - `cfgfile`, A1).

### Точка расширения выбора платы по умолчанию (требование оркестратора)
`configurator.rank_main_boards(reg, ids) -> list` - единственная функция порядка предпочтения главных плат; её вызывают и
`HardwareDetector.main_candidates` (кандидаты по железу), и `Configurator.guess_main_board` (догадка по printer.cfg). Сейчас:
проверенные (`VERIFIED=yes`) раньше, при равенстве чип по убыванию (H7 раньше F4), затем id. Ранжирование по `board_rank`
(1.3b) добавляется только в неё; тест `test_is_single_extension_point` проверяет, что обе точки идут через неё.

### Для A5 (переиспользование)
`Hardware`, `HardwareDetector` (`detect()`, `only_detect=` в `Options`), `Options`, `Env`, `McuValues`, `mcu_blocks`,
`rank_main_boards`, `byid_find/dfu_count/dfu_family/show_usb_state/usb_bridge_present/can_iface_exists/serial_from_path`,
`Configurator.collect_mcu_state/stage_config`. Не перенесены (нужны только install): `family_name`, `uid_addr`, `dfu_read_uid`,
`bridge_usb_serial`, `print_boards` - отмечены `todo (A5)` в MAP. Файл `hardware.py` (A2) я не создавал: общие функции лежат в
`configurator.py`; при слиянии A2/A5 могут перенести их в `hardware.py` без изменения сигнатур.

## Намеренные отличия от bash
1. **`boards/bad_args` (golden) - единственное расхождение.** Последний сценарий (`configure_vostok.sh --printer-data <нет каталога>`
   без `-y` и без терминала) в bash падал на артефакте: сообщения `lib/vostok_config.sh: line 53: /dev/tty: No such device or
   address` и `line 54: ans: unbound variable` (`read` из недоступного /dev/tty + `set -u`), после чего меню рисовалось второй раз.
   В Python это `ОШИБКА: нужен терминал: установка просит переключать платы и нажимать Enter`, код выхода тот же (1). Воспроизводить
   текст ошибки bash с путём и номером строки бессмысленно. Эталон не пересняли (по условию); прошу оркестратора пересъёмку
   только этого кейса (`run_golden.sh --update boards/bad_args`) либо принять расхождение.
2. Скачивание конфигурации: `urllib` вместо `curl` + `tar` (меньше внешних зависимостей; поддерживаются `https://`, `file://`).
   Распаковка с отбрасыванием верхнего каталога (`--strip-components=1`), небезопасные имена (`..`) и ссылки пропускаются.
   Сообщения `не удалось скачать …` / `не удалось распаковать конфигурацию` те же, но без шума `curl:`/`gzip:`/`tar:` в stderr.
3. `stock_electronics`: признак `_h723_` ищется в имени файла, а не в полном пути (раньше каталог с `_h723_` в пути «подходил»
   бы любому файлу).
4. Если задан `--main`, кандидаты по железу не вычисляются (раньше при одном устройстве в DFU зря вызывался `sudo -n dfu-util`).
5. Переменная окружения `ONLY_DETECT` в `configure` не читается (опции у этого скрипта нет; `Options.only_detect` нужен install).
6. Копирование файлов и `.bak` через `shutil`/`cfgfile.backup_file`; ошибки записи - `VostokError`, а не `cp: …` и обрыв по `set -e`.
7. Временный каталог удаляется всегда (в bash при `die` оставался `/tmp/tmp.*`).
8. Сохранена особенность bash: каталог журнала создаётся до проверки `printer_data`, поэтому `--printer-data <несуществующий>`
   создаёт каталог и работа продолжается (проверка `нет каталога … (укажите --printer-data)` практически недостижима).
   Покрыто golden и тестом `test_main_missing_printer_data_dir_is_created_for_log`.
9. `cli.py` (файл A1): добавлены импорт `configurator` и строка `"configure": configurator.main` (как разрешает CONTRACTS).

## Проверки
- `python3 -m unittest discover installer/tests`: 165 тестов, **164 OK, 1 FAIL** - `test_golden` из-за единственного
  расхождения п. 1. Новых тестов 89: `test_electronics` (15) и `test_configurator` (74), ~10 с.
- `installer/tests/run_golden.sh` (полный): 234 эталона, **расхождений 1 (`boards/bad_args`, п. 1)**. Все 38 эталонов
  `configure/*` (сценарии A-P, dry и real, дерево `pd/config` с sha256 и полным текстом `printer.cfg`/`electronics_*.cfg`),
  `help/configure_vostok` и остальные 192 - байт-в-байт.
- Матрица генератора (мои скрипты в scratchpad, не в репозитории): старый `tools/gen_electronics.py` против
  `vostok.electronics.main` - 1891 сочетание (10 главных плат x 4 варианта голов x 8 наборов драйверов x ALPS 0/2 x
  эталон: нет / сток / 4 файла user_configs; stdout, stderr, код выхода и файл - побайтно): **различий 0**.
  В репозитории та же сверка идёт в `test_electronics` (около 70 сочетаний + ошибки), она пропускается, когда A6 удалит старый файл.
- Интерактивные сценарии в pty: старый `configure_vostok.sh` из `git 6808e7a` и новый, одинаковые ответы - 38 сценариев (меню
  платы/голов/ALPS/источника/файла/драйверов, ответы да/нет на вопросы про модули и эталон чужой платы, devices.tsv и мост,
  DFU и CAN-признаки, два кандидата с `-y`, конфликт пинов модуля, закомментированный `[include]`, чужой/пустой printer.cfg,
  скачивание `file://`, все `die`-сообщения): полный вывод и файлы `pd/config` совпадают, **различия только в шуме
  `curl:`/`tar:`** (п. 2).
- Обёртка: `--help`, `-V`, неизвестная опция и ошибки проверены тестом `TestWrapper` и golden.

## Открытые вопросы
1. Пересъёмка/принятие `boards/bad_args` (п. 1 выше).
2. **Harness (файл A0, не мой):** `Sandbox.violations()` считает нарушением новые `vostok/__pycache__/*.pyc` в копии `installer/`,
   которые Python создаёт при запуске любой обёртки. Для проверки я локально (без коммита) пропускал `__pycache__` в
   `golden_lib.Sandbox._tree_snapshot` (`if "__pycache__" in dn: dn.remove("__pycache__")`); без этого падает любой кейс
   с python-обёрткой. Нужно внести один раз для всех агентов (или задавать `PYTHONDONTWRITEBYTECODE=1` в `base_env`).
3. `lib/vostok_config.sh` и `tools/gen_electronics.py`, `mcu_merge.py`, `pin_conflicts.py` остаются до A5/A6: логика
   дублируется (bash для install, Python для configure). `tools/gen_electronics.py` для A6 заменяется обёрткой
   `python3 -m vostok.electronics "$@"` (протокол и коды те же) - тогда golden `gen_matrix` останется зелёным без пересъёмки.
4. `BOARD_NAMES/BOARD_FILE`: в формате `.board` (менять нельзя) нет полей «название в шапке»/«часть имени файла», поэтому для двух
   плат со старыми именами (`octopus-pro-h723`, `octopus-pro-f446`; `CFG == CHIP`) значения лежат в `LEGACY_BOARD_NAMES`
   (`electronics.py`), а сама плата находится через реестр. Если в 1.3b добавят поля `NAME`/`FILE` в `.board`, таблицу можно удалить.
5. Устройство `hardware.py` (A2): общие USB/DFU/CAN-функции сейчас в `configurator.py` (см. «Для A5»); решение о переносе - при слиянии.
6. Сортировка `main_candidates` (`sort`) и порядок glob в bash зависят от локали; Python сортирует по кодовым точкам (в golden
   `LC_ALL=C.UTF-8`, различий нет). На хостах с `en_US.UTF-8` порядок плат с `-`/`.` в id мог бы отличаться - считаю улучшением.
