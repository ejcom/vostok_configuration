# Отчёт A3 integrations

Ветка `py/integrations` (от `py-migration`), не запушена. Файлы: `vostok/integrations.py`, три обёртки `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh`, `tests/test_integrations.py`; плюс строки реестра в `vostok/cli.py` и колонка «Python» в `migration/MAP.md`.

## Что перенесено (bash -> Python)

| bash | Python |
|---|---|
| `install_fluidd_button.sh` (весь) | `integrations.main_button`, класс `FluiddButton` (`checks`, `step_rights`, `step_unit`, `step_asvc_and_dropins`, `step_macro`, `uninstall`) |
| `usage` (3 шт.) | `USAGE_BUTTON`, `USAGE_THEME`, `USAGE_KS` (текст побайтно прежний) |
| `render_unit` | `FluiddButton.render_unit` (подстановка `@USER@ @HOME@ @PRINTER_DATA@ @SCRIPT@ @FLASH_ARGS@`) |
| `restart_moonraker` | `FluiddButton.restart_moonraker` (`Runner.systemctl`: polkit, затем sudo) |
| `can_manage_services` | `system.can_manage_services(allow_sudo=False)` |
| `install_fluidd_theme.sh` | `main_theme`, класс `FluiddTheme` |
| `db_get_theme`, `db_theme_logo`, `is_ours` | `FluiddTheme.db_get_theme/db_theme_logo/is_ours` (urllib вместо curl: `http_request`) |
| `edit_fluidd_cfg`, `preset_json` | `FluiddTheme.edit_fluidd_cfg` (бэкап `.bak-<дата>` + атомарная запись через `cfgfile.atomic_write`), `FluiddTheme.preset` |
| `install_klipperscreen_theme.sh` | `main_ks_theme`, класс `KlipperScreenTheme` |
| `edit_ks_conf`, `current_theme` | `integrations.edit_ks_conf`, `integrations.current_ks_theme` (код перенесён дословно, включая особенности разбора) |

Сохранено: `--uninstall`, `--dry-run`, `--force`, `--no-activate`, `--logo-copy`, `--with-macro`, `--flash-args`, `--printer-data/--fluidd-dir/--ks-dir`, `-y`, `-V`, `-h`; порядок разбора аргументов и тексты ошибок; маркер `VOSTOK-THEME`; бэкапы; sudoers через `visudo -cf`; запись в `moonraker.asvc` (в т.ч. файл без завершающего `\n`); drop-in `After=mcu-update.service`; макрос `mcu_update.cfg`; env `PRINTER_DATA KLIPPER_DIR KATAPULT_DIR MOONRAKER_URL FLUIDD_DIR KS_DIR FONT_DIR`. sudo/systemctl/apt только через `Runner`, чтение (`--list`, `list-unit-files`) через отдельный не-dry `Runner`.

Обёртки: `PYTHONPATH="$INSTALL_DIR" PYTHONDONTWRITEBYTECODE=1 VOSTOK_PROG="$0" exec python3 -m vostok <button|theme|ks-theme> "$@"` (без `-I`).

## Намеренные отличия

1. Обёртки передают `VOSTOK_PROG="$0"`: нужно для строки «Удалить: $0 --uninstall» (в bash это `$0`). Без переменной берётся путь `INSTALL_DIR/<скрипт>`.
2. В обёртках добавлен `PYTHONDONTWRITEBYTECODE=1`: golden-harness считает появление `vostok/__pycache__` в копии installer «нарушением изоляции» и env детям не пробрасывает. Решение оркестратору: оставить так или починить harness (тогда переменную из обёрток убрать).
3. curl не нужен (проверка «нет curl» удалена), Moonraker опрашивается через urllib (`-sf`: код >= 400 = ошибка; таймауты 5/10 с как в curl).
4. Файловые записи, которые в bash были `cat >`/`>>` (`moonraker.asvc`, `mcu_update.cfg`) и `install` (темы), теперь атомарные (tmp + rename); права существующего файла сохраняются.
5. Сбой промежуточной sudo-команды при установке/удалении (`rm`, `daemon-reload`, `install`) даёт `ОШИБКА: команда завершилась с кодом N` и код 1 (в bash `set -e` завершал бы скрипт с кодом самой команды).
6. Ошибка разбора `config.json` при `--uninstall` теперь предупреждение и продолжение удаления (в bash был бы traceback с пустым выводом и продолжением); при установке JSON проверяется заранее, как раньше.
7. `fc-cache`: stderr не подавляется (Runner не умеет), только stdout; результат так же определяет `warn`.
8. `uiSettings.theme == null` в базе Moonraker считается «темы нет» (в bash падал бы разбор).
9. Без доступного `/dev/tty` и без `-y` вопрос о чужой теме Fluidd даёт `ОШИБКА: нужен терминал…` (bash падал с `answer: unbound variable`); код возврата тот же (1).

## Вопросы оркестратору (расхождение с формулировкой задачи)

- В задаче: «поведение -y с чужой темой (не заменять без --force)». В базе bash 1.3a это верно только для KlipperScreen (`-y` + чужая тема = не менять, предупреждение). В Fluidd `confirm()` при `-y` отвечает «да», и чужая тема **заменяется** (подтверждено сравнением старого и нового скрипта на заглушке Moonraker). Перенесено 1:1 с bash (golden/база 1.3a); если нужно как в KlipperScreen, это одна строка в `FluiddTheme.step_activate` (и новое поведение, а не перенос).
- Особенности, перенесённые как есть: при `--uninstall` KlipperScreen `Tektur-OFL.txt` в каталоге шрифтов остаётся; `edit_ks_conf` не видит значение при записи `theme: x` (двоеточие) и считает текущей базовую тему (в сообщении «была тема: material-dark»).
- `vostok/cli.py` не в списке моих файлов: добавлены только 3 строки `COMMANDS[...]` и импорт `integrations` (при слиянии с A2/A4 возможен тривиальный конфликт в этом блоке).
- Полный golden-прогон (`tests/run_golden.sh`) дал 1 «нарушение изоляции» не по моим эталонам: изменён реальный `/home/klipper/printer_data/logs/klipper_mcu_update.log` (последняя запись 08:00:45, во время прогона; скорее всего параллельный агент/процесс, мои тесты и `integrations/*` его не трогают: `--filter 'integrations/*'` чист). Стоит перепроверить при слиянии.

## Проверки

- `python3 -m unittest discover tests`: 112 тестов, OK (из них 36 новых в `test_integrations.py`: разбор аргументов, обе темы на копиях в tmp, правка `KlipperScreen.conf` во всех ветках, кнопка со stub-Runner: polkit/sudoers/visudo-ошибка/dry-run/asvc/drop-in/макрос/uninstall).
- Golden `tests/run_golden.sh --filter 'integrations/*'`: 3 эталона, 0 расхождений (эталоны не переснимались).
- Дополнительное сравнение старых и новых скриптов на 47 сценариях в песочнице с мок-Moonraker (чужой css/тема/каталог, --force, -y, --logo-copy, --uninstall, --dry-run, битый JSON, saved-блок `#~#`, нет Moonraker и т.д.): вывод, коды, деревья файлов и состояние базы совпадают; единственное расхождение — п. 9 выше.
- Не проверялось на реальной системе: реальный sudo/systemctl/visudo/apt кнопки (по условию не запускались), только через stub Runner и golden dry-run.
