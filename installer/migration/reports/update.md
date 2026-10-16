# Отчёт A2 update (ветка py/update от py-migration)

Перенесён `update_klipper_mcu.sh` (база поведения - bash 1.3a) на `vostok/update.py` + `firmware.py` + `hardware.py`. Обёртка `update_klipper_mcu.sh` вызывает `PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok update "$@"` (INSTALL_DIR через `readlink -f`, без `-I`). `--help`/`-V`/ошибки идентичны (golden `help/update_klipper_mcu` без расхождений). Ничего не запушено, реальная прошивка и `~/printer_data` не использовались.

## Что перенесено (bash -> Python)

Полная таблица с колонкой «Python» заполнена в `migration/MAP.md`. Кратко:

| bash | Python |
|---|---|
| аргументы, `usage`, `-V` | `update.parse_args`, `update.USAGE`, `update.read_version` |
| `mr_get`, `json_get(eval)`, `cfg_mcus`, `cfg_mcu_versions`, проверки Moonraker | `update.Moonraker` (urllib, таймаут 5 с, HTTP>=400 = ошибка как `curl -f`; JSON разбирается без `eval`) |
| 9 параллельных массивов `MCU_*` | `update.Mcu` (dataclass: name, path, chip, serial, cfg, version, order, uuid, is_bridge) |
| `preflight`, `check_*` | `Updater.preflight/check_moonraker/check_not_printing` |
| `add_mcu`, `add_can_mcu`, `discover_mcus`, `print_mcus` | `Updater.*` (таблица выравнивается по БАЙТАМ UTF-8, как `printf %-Ns` в bash) |
| `by_id_chip/serial`, `can_iface_up`, `wait_for_device`, поиск `usb-katapult_*` | `hardware.*` |
| `host_version`, `norm_version`, `build_firmware`, вызовы `flashtool.py` | `firmware.*` |
| `pending_commits`, `update_host(_git)`, `post_update_checks`, `services`, `flash_can`, `flash_all`, `wait_for_klipper`, `verify_versions`, `main` | методы `Updater`, `update.main` |
| `devices_lookup`, `state_get/set`, `sctl`, `can_manage_services`, `confirm` | уже в `state`, `system`, `ui` (A1) |

Регистрация: `cli.COMMANDS["update"] = update.main` (строка + импорт в `vostok/cli.py`).

## Сохранено 1:1
Флаги `--list/--no-update/--no-flash/--force-flash/--git-update/--ignore-moonraker/-y/-V/-h`; автоматический `--git-update` без tty (stdin не терминал); без tty и без прав на службы - та же ошибка в preflight (`system.can_manage_services(True)`: polkit, затем `sudo -n`); порядок прошивки 1 (MCU вне printer.cfg) -> 2 (дополнительные) -> 3 (главный `[mcu]` / мост USB-CAN), мост последним; тексты ошибок и справок при неудачной прошивке; коды возврата (0 / 1 / код ошибки через VostokError = 1); формат `flashed.tsv`/`devices.tsv`; запись в журнал `LOG_FILE`.

## Намеренные отличия
1. **Исправлено**: `flash_can` для моста искал `usb-katapult_*` в жёстком `/dev/serial/by-id`; теперь берётся `BYID_DIR` (`hardware.wait_for_katapult`, тест `test_bridge_uses_byid_dir_from_config`).
2. Убрана проверка наличия `curl` (больше не нужен: Moonraker через urllib). Остальные проверки `preflight` и их тексты прежние.
3. Строка журнала «=== запуск ... ===»: в bash из-за `shift` в `$*` всегда был пустой список аргументов; сохранено (два пробела перед `===`).
4. Системные вызовы через `Runner` дописывают в журнал строки `$ <команда>` (в bash их не было) - вывод на экран не меняется.
5. Некоторые сбои `git rev-parse/describe` в bash молча завершали скрипт (`set -e` в подстановке); теперь это `VostokError` с сообщением.
6. Проверка `bash >= 4.4` не нужна (убрана).

## Временное решение для install_vostok.sh (важно для A5/A6)
`install_vostok.sh` (пока bash) делает `source update_klipper_mcu.sh` ради функций (`info`, `discover_mcus`, `build_firmware`, `flash_can`...). Чтобы не сломать его и 190 golden-кейсов install, прежний bash-скрипт сохранён как `lib/update_legacy.sh` (только `SCRIPT_DIR` поправлен на родителя `lib/`), а обёртка при `source` (BASH_SOURCE != $0) подключает его и делает `return`. Сам `update_klipper_mcu.sh` при запуске работает на Python. **`lib/update_legacy.sh` удалить вместе с переносом install на Python (A5/A6)**; это единственный потребитель.

## Правка вне зоны владения
`tests/golden_lib.py`: в `base_env` добавлено `"PYTHONDONTWRITEBYTECODE": "1"`. Без неё первый же Python-запуск из обёртки создаёт `vostok/__pycache__` в копии installer/ и golden сообщает «нарушение изоляции» (так же упадут обёртки A3/A4/A5). Отдельный коммит, строка идентична для всех агентов; эталоны не переснимались.

## Результаты
- `python3 -m unittest discover installer/tests`: 121 тест, OK (в т.ч. 45 новых в `tests/test_update.py`: разбор аргументов, Moonraker на настоящем HTTP-сервере, поиск MCU/CAN/мост, порядок 1->2->3, режимы git/KIAUH/no-flash/no-update/force/list, отказ от подтверждения и отсутствие tty, сбои прошивки, сборка с поддельным `make`, `update_host_git` на настоящих git-репозиториях (ff, переписанная история, локальные коммиты), восстановление gcode_shell_command, проверка итогов, обёртка и symlink).
- golden: `tests/run_golden.sh` - 234 эталона, расхождений 0 (с тем же `PYTHONDONTWRITEBYTECODE`; эталоны не пересъёмались).

## Открытые вопросы
1. `Runner.run` не умеет глушить stderr и перенаправлять вывод в файл. Поэтому `hardware.run_quiet` (subprocess с `stderr=DEVNULL`: git/ip/systemctl/`import serial`) и `firmware._make` (вывод make в `make.log`) вызывают subprocess напрямую. Предложение: добавить в `Runner.run` параметры `quiet`/`stdout_file` и перевести эти места (контракт A1).
2. Версия установщика читается локально (`update.read_version`); у остальных скриптов будет то же - вынести в общий модуль (A6/A1).
3. Для A5: `hardware.py`/`firmware.py` содержат только то, что нужно update; поиск by-id по `usb-Klipper_*`/`usb-katapult_*`, ожидание CAN и обёртки `flashtool.py` готовы к повторному использованию (`firmware.flashtool/flash_usb/flash_can_node/request_bootloader_can`, `hardware.wait_for_katapult/wait_for_can_iface`). lsusb/dfu-util/`canbus_query` не переносились.
4. Реальная проверка на железе не выполнялась (по условиям): `flash_can` для моста, `ifup`, KIAUH-режим покрыты только заглушками.
