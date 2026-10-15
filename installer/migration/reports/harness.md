# Отчёт A0 harness (ветка py/harness)

## Что сделано
Страховочная сетка из 234 golden-эталонов, снятых со СТАРЫХ bash-скриптов (старые файлы не правились). Запуск: `installer/tests/run_golden.sh`.

## Как запускать
- `installer/tests/run_golden.sh` — сравнить всё (около 2 мин, 4 потока; код 0 — совпало, 1 — расхождения, 2 — хост не подходит).
- `--list` — имена; `--filter ШАБЛОН` (fnmatch, можно повторять) — подмножество; `-v` — печатать ok.
- `--show ИМЯ` (или `группа/`) — diff «эталон → сейчас» (`--full` — весь текущий вывод). Работает и для сжатых групп: эталоны хранятся полным текстом.
- `--update [ШАБЛОН]` — пересъём эталонов, ТОЛЬКО по этому флагу. Не пишет, если скрипты вышли за песочницу, вызвали sudo или упал harness.
- `--keep` — оставить песочницу для отладки.
- `python3 -m unittest discover installer/tests` — `test_golden.py` запускает run_golden.sh (код 2 -> skip).

## Устройство
- `tests/golden_runner.py` (CLI, хранилище), `golden_lib.py` (песочница, заглушки, мок Moonraker, нормализация), `golden_cases.py` (перечень эталонов), `fixtures/`, `golden/`.
- Скрипты запускаются из КОПИИ `installer/` (без tests, migration, build, firmware) + снимок корня репозитория `fixtures/repo_root` (printer.cfg, стоковый electronics, chamber_heater.cfg, user_configs/, заглушки printer_base.cfg и postprocessing) во временном каталоге; дрейф корневых конфигов main эталоны не ломает. Копия installer/ в конце сверяется по хэшам (скрипты не должны в неё писать).
- Каждый запуск: новая сессия (нет tty), stdin=/dev/null, HOME/PRINTER_DATA/LOG_FILE/DEVICES_FILE/BUILD_DIR/FIRMWARE_DIR/BYID_DIR/KERNEL_CONFIG/MIN_FREE_MB/MIN_MEM_MB — в каталоге эталона; `LC_ALL=C.UTF-8`, `TZ=UTC`.
- Заглушки в PATH: `sudo` (запрещён: вызов пишется в эталон строкой «ВЫЗВАН sudo» и блокирует `--update`), `git` (`ls-remote` без сети, остальное настоящий git), `lsusb`, `ip` (`GOLDEN_CAN_UP=1` — can0 UP), `dpkg`, `apt-get`, `systemctl`, `ss`, `dfu-util`, `arm-none-eabi-gcc`, `make`, `df`, `uname`.
- Мок Moonraker: `http.server` в потоке, сценарий выбирается первым сегментом пути `MOONRAKER_URL=http://127.0.0.1:порт/<сценарий>`.
- Фикстурный git-репозиторий Klipper (детерминированные sha, upstream через bare-клон), katapult/flashtool.py, klippy-env/bin/pip.
- Сторож: до/после сравниваются `~/printer_data/config`, `~/printer_data/logs/vostok_*`, `klipper_mcu_update*`, `~/klipper_mcu` (живые логи klipper/moonraker не сторожатся).

## Покрытие
| группа | эталонов | что |
|---|---|---|
| help | 6 | `--help`, `-V`, неизвестная опция для всех 6 скриптов |
| boards | 2 | `--list-boards`; ошибки аргументов install/configure |
| install_matrix | 80 | `--only-detect` и `--dry-run` × 10 главных плат из `boards/` (ROLE=main) × heads none/v1.3/v2/ebb42 (режим usb/bridge однозначно задаётся heads; плата без моста с головами — отказ, тоже эталон) |
| install | 13 | автоопределение по byid, `--heads-flash can`, `--main-flash katapult`, `--skip-*`, `--skip-board/--reflash`, generate+drivers, `--upgrade`, ядро без CAN, `VOSTOK_CFG_LOCAL=0`, `--check-can --dry-run`, без tty и без `-y` |
| gen_matrix | 81 | `tools/gen_electronics.py`: 10 плат × 4 heads × 2 набора (драйверы стока / `all=5160plus` + alps=2), аргументы как у `gen_custom_electronics`, полный текст результата; плюс ошибки аргументов |
| configure | 38 | сценарии A–H и дополнительные, каждый `_dry` и `_real` (запись в копию pd: дерево/хэши, полный текст printer.cfg и electronics_*.cfg) |
| tools | 3 | mcu_merge (`--list`, OK/ADD/DIFF/TODO, `--dry`, повтор, `--set` SET/SAME/DIFF/NOSECTION/`--force`), pin_conflicts, can_uuid |
| update | 8 | `update_klipper_mcu.sh --list` на фикстуре + мок Moonraker: USB, CAN, ALPS, не в printer.cfg, katapult, нет конфига; CAN down; нет Moonraker (+`--ignore-moonraker`); печать/пауза; flashed.tsv/пустой by-id; неоднозначный чип; ошибки preflight; «всё актуально» |
| integrations | 3 | кнопка Fluidd (dry-run, `--with-macro`, `--flash-args`, `--uninstall`), тема Fluidd и тема KlipperScreen (dry, install, `--logo-copy`, `--no-activate`, `--uninstall`) |

### Сценарии конфигуратора A–H
В `CONFIGURATOR.md` сценарии не пронумерованы (5 «типовых»), нумерация harness (также в шапке `golden_cases.py`): A чистая установка generate без голов all=5160; B существующий конфиг, драйверы 2209; C существующий, головы EBB42; D skip + `--alps 2`; E skip + chamber_heater; F standard, головы v1.3; G user, EBB42; H generate на Spider v3 H723 / Manta M8P v2.0 (heads v2) / Octopus F446 / FLY-C8. Дополнительно: I чужой (KIAUH) и пустой printer.cfg, J skip с DIFF/TODO, K `--reference none` + `--modules all`, L без tty и без `-y`, M все модули, N `VOSTOK_CFG_LOCAL=0`, O отсутствующий `--electronics`, P `PRINTER_DATA` против `--printer-data`.

## Недетерминированное и его нормализация
- Пути: каталог эталона -> `<CASE>`, копия installer -> `<INSTALL>`, репозиторий -> `<REPO>`, фикстуры -> `<SHARED>`, tmp -> `<TMP>`.
- Порт мока -> `<PORT>`; `.bak-ГГГГММДД-ЧЧММСС` -> `.bak-<ДАТА>`; sha в `git describe` -> `-g<SHA>`; `ОС: …`, версия python3, объём памяти -> заглушки.
- Резервные копии с меткой секунд при совпадении секунды перезаписывают друг друга (в configure их две за запуск): в деревьях они идут как множество имён без размера/хэша; в сценариях с несколькими запусками подряд (темы, mcu_merge) между запусками пауза 1,1 с.
- `show_usb_state` (lib/vostok_config.sh) читает `/dev/serial/by-id` хоста в обход `BYID_DIR`: список между «Устройства в /dev/serial/by-id:» и «Устройств в режиме DFU» заменяется заглушкой.
- Логи в деревьях — только факт наличия; кэш fontconfig и `.fonts/.uuid` исключены.
- В dry-run на «чистой машине» есть `fatal: cannot change to '<CASE>/home/klipper'` (git describe в несуществующем KLIPPER_DIR) и `stm32h723xx-.bin` в команде dfu-util — особенность старого кода, зафиксирована в эталоне; если Python-версия её исправит, это осознанное отличие, эталон переснять.

## Проверка требований
- `--dry-run` и `--only-detect` install_vostok.sh sudo-пароль НЕ требуют (`start_sudo` возвращается до `sudo -v`, все `sudo ...` в dry-run только печатаются). Заглушка sudo: ни одного вызова за все 234 эталона.
- Вне временных каталогов ничего не пишется (сторож + хэши копии installer): нарушений нет. Достаточно env: `PRINTER_DATA`, `LOG_FILE` (по умолчанию внутри PRINTER_DATA), `DEVICES_FILE`, `BUILD_DIR`, `FIRMWARE_DIR`, `HOME`, `BYID_DIR`; скрипты править не пришлось.
- Сеть: preflight делает `git ls-remote` (без доступа к github.com скрипт падает даже в dry-run) — в harness заглушка.

## Результаты
- `tests/run_golden.sh`: 234 эталона, расхождений 0 — три прогона подряд после финальной съёмки (стабильно). Около 2 мин.
- `python3 -m unittest discover installer/tests`: 1 тест, OK (133 с).
- Размер `tests/golden` около 310 КБ (группы >150 КБ — `.txt.gz`, mtime=0, детерминированно), фикстуры около 150 КБ.

## Чего эталоны не покрывают
- Реальную прошивку, DFU/katapult-потоки, интерактивные меню (`retry/dfu/dfuall/dfuk/skip/abort`) — без tty не вызвать; зона A5 с поддельным `ui`.
- Не-dry-run `install_vostok.sh`, `--check-can` с реальной шиной, ветки `update_klipper_mcu.sh` кроме `--list` (KIAUH, `--git-update`, прошивка CAN), polkit/sudoers кнопки, активацию тем через живой Moonraker (POST).
- Загрузчик без python3 (нужен контейнер); `tools/gen_configs.sh --check/--build`.
- Эталоны привязаны к текущим путям `tools/*.py`: если A1/A4 заменят их обёртками или удалят, нужно поправить вызов в `golden_cases.py`, не меняя ожидаемый текст.
- Реестр `boards/` и `templates/` берутся из реального `installer/`: их законное изменение меняет эталоны.

## Открытые вопросы
1. Сценарии A–H в `CONFIGURATOR.md` не определены; принята нумерация harness. Если у оркестратора другой смысл — перенумеровать.
2. В реестре 10 главных плат, не 14 (14 — всего с головами и ALPS); матрица охватывает все 10 главных.
3. Хост: нужны systemd (`/run/systemd/system`), модули python `serial`, `venv`, `ensurepip`, Debian-подобная ОС, bash 4.4+, не root; иначе run_golden.sh выходит с кодом 2 (skip).
4. Полный прогон около 2 мин; `-j` можно увеличить.
5. Особенности старого кода (не исправлялись): `show_usb_state` игнорирует `BYID_DIR`; traceback `mcu_merge.py` без аргументов (в эталон не включён); дубль резервных копий в одну секунду.
