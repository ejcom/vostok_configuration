# Отчёт A5 install-flow

Ветка `py/install-flow` (от `py-migration` fb57ad9), не запушена. Работа выполнена целиком (делить на A5a/A5b не пришлось).

## Что сделано (по коммитам)

1. `d50a664` - замечания ревью `review-wave2.md`:
   - **H1**: `Runner.run` получил `quiet` (stderr в /dev/null), `stdout_file`/`append` (`>файл 2>&1`), `readonly` (выполнять и в dry-run).
     `firmware._make`, `hardware.run_quiet` и `hardware.ifup` переведены на Runner, лишний `import subprocess` в `update.py` убран.
     `firmware.build_firmware` в dry-run только печатает (не трогает `build/` и `configs/*.config`).
     В `vostok/` `subprocess` теперь только в `system.py`.
   - **M4**: `ui.need_tty` и `ui.confirm` используют `have_tty()` (реальный `open('/dev/tty')`).
   - **M2**: `DevicesFile.save` атомарна (tmp + `os.replace`, права прежнего файла сохраняются); общий `_atomic_write` в `state.py`.
   - **M1**: `cli.main` ловит непредвиденные исключения (`ОШИБКА: <тип>: <текст>`, traceback в журнал, код 1); `Updater.run` печатает подсказку про остановленный Klipper при любой ошибке.
   - **L1**: `sudo_keepalive` проверяет наличие sudo и в dry-run (порядок как в bash: проверка всегда, пароль только вне dry-run/only-detect).
2. `6822ea7` - **M3** отдельным коммитом (меняет эталон, см. ниже): `configure --printer-data <нет каталога>` не создаёт каталог.
3. `2ab2e44` - перенос `install_vostok.sh`: `vostok/install.py`, `host.py`, `flashing.py`; USB/DFU/CAN-функции из `configurator.py` переехали в `hardware.py`; `install_vostok.sh` - загрузчик.
4. `f89b8a8` - тесты (`test_install`, `test_flashing`, `test_host`, `test_hardware`, `fakes.py`).
5. `4849b13` - удалены `lib/update_legacy.sh`, `lib/vostok_config.sh`; `tools/gen_electronics.py` - обёртка над `vostok.electronics`.
6. Последний коммит: `cli` тихо обрабатывает `BrokenPipeError` (`... | head`, код 141), `MAP.md`, `STATUS.md`, этот отчёт.

L2-L4 не трогал (не просили).

## Соответствие bash -> Python

Полная таблица в `MAP.md` (все строки `install_vostok.sh` и «todo»-строки `lib/vostok_config.sh` закрыты). Кратко:

| bash | Python |
|---|---|
| ~45 глобалов | `install.InstallContext` (`opts: host.Options`, `env: host.Env`, `hw: configurator.Hardware`, `res: host.Results`, `updater`, `flasher`) |
| `RES_*` | `Results.mcu` (`configurator.McuValues`, его же использует `Configurator.stage_config`) |
| `FLASH_FAILED/SKIPPED`, `HEADS_SKIP`, `HEADS_WAY`, `HEAD_UUID_SRC`, `HEAD_DFU_DONE`, `PREV_DEVICES` | поля `host.Results` |
| `TMP_ANS`, `NEW_KATAPULT_DEV`, `FLASHED_SERIAL`, `FLASHED_UUID`, `DFU_UID_UUID` | возвращаемые значения (`Outcome`, строки) |
| коды возврата прошивки | `FlashError` (текст предупреждения, если он ещё не напечатан) |
| `flash_board` + `flash_menu` + `BOARD_PHASE` + `BOARD_DEV` | `flashing.flash_with_retry` + `flash_menu` + `FlashJob.retry_phase/dev` |
| `try_alps/try_main/try_head_*` | задания `make_alps_job/make_main_job/make_head_katapult_job/make_head_dfu_job/make_head_klipper_job` |
| способы прошивки | стратегии `DfuAll`, `KatapultThenKlipper`, `DfuKlipperOnly`, `CanKlipper` (+ `HeadKatapult` для варианта «katapult плат голов по DFU, Klipper по CAN») |
| `die` посреди кода | `VostokError`/`UserAbort`, печать и подсказка про остановленный Klipper в `install.main` |
| `start_sudo`/`trap cleanup` | `Runner.sudo_keepalive` в `ExitStack` + `install._klipper_hint` |
| `source update_klipper_mcu.sh` (services, wait_for_klipper, verify_versions, mr_get) | `update.Updater` (его методы вызывает install) |
| `source lib/vostok_config.sh` (detect_hardware, stage_config) | `configurator.HardwareDetector`, `Configurator.stage_config` (тот же код, что у `configure`) |

Загрузчик `install_vostok.sh` (60 строк): `PYTHONPATH="$INSTALL_DIR" PYTHONDONTWRITEBYTECODE=1 exec python3 -m vostok install "$@"`; при отсутствии python3 ставит `python3 python3-venv` через `sudo apt-get` (кроме режимов `--dry-run/--only-detect/--help/--list-boards/-V`: там ничего не меняется, печатается ошибка), проверяет версию >= 3.8.

## Намеренные отличия от bash 1.3a

- Без терминала и без `-y` вопрос (`ask_yn/ask_choice/pause_hw`) сразу даёт `ОШИБКА: нужен терминал…`, а не мусор bash (`/dev/tty: No such device`, `ans: unbound variable`) и не печатает меню перед ошибкой.
- `sudo tee` для `/etc/network/interfaces.d/can0` и `systemd/network/80-can0.*` заменён на `sudo install -m 644 <tmp> <файл>` (в dry-run строка `[dry-run] sudo tee …` напечатана как раньше). Результат тот же (root:root 0644).
- `devices.tsv` пишется атомарно (M2).
- `ctrl+C`/непредвиденные ошибки: `ОШИБКА: <тип>: …` вместо traceback (M1).
- `check_bootstrap` берёт память из `/proc/meminfo`, остальное (`df`, `uname`, `id`, `ss`, `lsusb`, `ip`, `dfu-util`) - внешние программы через Runner, как в bash (иначе golden с заглушками не совпал бы).
- `family_name`/`uid_addr`/`dfu_read_uid`/`bridge_usb_serial` в `hardware.py`; `can_uuid_from_serial` и `tools/can_uuid.py` не вызываются (используется `vostok.can_uuid`).

## Результаты проверок

- `python3 -m unittest discover installer/tests`: 402 теста (было 246), 4 пропущено (сверка со старым `gen_electronics.py`), **1 падение - `test_golden`** из-за двух расхождений эталонов ниже; всё остальное зелёное.
- `installer/tests/run_golden.sh`: 234 эталона, **расхождений 2**, остальные 232 совпадают, в том числе вся матрица `install_matrix` (детект и dry-run для всех плат и режимов), `gen_matrix` (через обёртку `tools/gen_electronics.py`), `help`, `integrations`, `update`, `configure`.

### Расхождения эталонов (не пересняты, нужно решение оркестратора)

Оба вызваны тем, что в песочнице нет управляющего терминала (`start_new_session`), а bash при этом печатал мусор. Предлагаю пересъёмку по аналогии с уже согласованным `boards/bad_args`: `tests/run_golden.sh --update boards/bad_args install/dry_no_tty_no_y`.

1. `install/dry_no_tty_no_y` (`install_vostok.sh --dry-run --main h723 --heads none --alps 0` без tty и без `-y`) - вызвано M4:
```
 == Octopus Pro v1.1 H723 ==
-Как прошить Octopus Pro v1.1 H723?
-  1) katapult и Klipper сразу по DFU (рекомендуется)
-  2) katapult по DFU, затем Klipper через katapult
-<INSTALL>/lib/vostok_config.sh: line 53: /dev/tty: No such device or address
-<INSTALL>/lib/vostok_config.sh: line 54: ans: unbound variable
+ОШИБКА: нужен терминал: установка просит переключать платы и нажимать Enter
```
   Код выхода тот же (1). Любая реализация без bash-мусора даст другой текст.
2. `boards/bad_args` (`configure_vostok.sh --printer-data <нет каталога>`) - вызвано M3 (отдельный коммит `6822ea7`, откатывается `git revert`, если M3 не нужен):
```
 $ configure_vostok.sh --printer-data <CASE>/no-such-dir
 # rc=1
-
-== Настройка конфига VOSTOK (версия 1.3a) ==
-… (определение MCU, меню «Главная плата», затем ОШИБКА: нужен терминал…)
+ОШИБКА: нет каталога <CASE>/no-such-dir (укажите --printer-data)
```
   Каталог `<printer-data>/logs` больше не создаётся при опечатке в пути.

## Тесты

Новые файлы: `tests/test_install.py` (разбор опций, `--list-boards/-h/-V` по порядку, выбор способа прошивки голов, план, автопропуск ALPS/голов/главной платы по версии и `--skip-board/--reflash`, `--main-flash`, порядок этапов для dfu/can, `--check-can` (все ветки сопоставления UUID), итоги, кнопка/тема, порядок вывода при ошибке и остановленном Klipper, сценарии с настоящим Runner и заглушками в PATH для DFU-сеанса, katapult+Klipper, ошибок dfu-util/make; загрузчик: без python3 в PATH, dry-run режимы, установка через заглушки sudo/apt-get, старый python3, symlink), `tests/test_flashing.py` (wait_dfu, DFU-прошивка katapult/Klipper в режимах make/guide, мост, CAN-плата, меню retry/dfu/dfuall/dfuk/skip/abort, повтор с фазы klipper без повторного DFU, `CanKlipper`), `tests/test_host.py` (проверки окружения и инструментов, пакеты, KIAUH/форк, правка `kiauh.cfg` сверена 1:1 со старым heredoc, CAN-конфиг, Moonraker), `tests/test_hardware.py` (перенесённые USB/DFU-тесты + UID, мост, шина CAN, ядро), общие заглушки `tests/fakes.py`.
Эталоны старого кода вынесены в `tests/fixtures/legacy_rewrite_printer_cfg.py` и `legacy_modules.sh` (вместо удалённого `lib/vostok_config.sh`; на них сверяются тесты `cfgfile`). Сверка с `tools/gen_electronics.py` в `test_electronics` теперь пропускается (файл стал обёрткой); побайтовую эквивалентность гарантирует golden `gen_matrix`.

## Открытые вопросы / замечания

1. Решение по двум эталонам (см. выше).
2. `docs/*`, `CONFIGURATOR*.md`, `CHANGELOG*`, `AGENTS.md` ещё ссылаются на `lib/vostok_config.sh` и `tools/gen_electronics.py` как на логику (это A6). `lib/boards.sh` и `tools/gen_configs.sh` не тронуты (A6).
3. Реальная прошивка, sudo и `~/printer_data` не использовались; настоящий non-dry путь проверен только заглушками (`FakeRunner` и PATH-заглушки). Живой прогон на железе - за пользователем.
4. Python 3.8 фактически не проверялся (на хосте 3.9.2): `ast.parse(feature_version=(3,8))` проходит, `match`/`:=`/`removeprefix`/`list[...]` не используются.
5. `LEGACY_BOARD_NAMES` в `electronics.py` по-прежнему ждёт полей `.board` (S6/1.3b), не трогал.
6. `host.EnvChecks.check_bootstrap` сохраняет прежний список обязательных утилит (`awk sed grep …`), хотя Python-установщику они не нужны; можно сократить на A6 без риска для golden (важен только текст «базовые утилиты…»).
