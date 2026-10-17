# История изменений установщика VOSTOK

🇷🇺 Русский | [🇬🇧 English](CHANGELOG.en.md)

Текущая версия записана в файле `VERSION` (`-V`/`--version` у всех скриптов). Описание: [README.md](README.md).

## 1.7 — 2026-10-17

Новые платы в реестре (все `VERIFIED="no"`, только по документации) и выбор плат голов в `--heads` из реестра.

- Главные платы: BTT Octopus F446 / F429 (не Pro; `octopus-f446`, `octopus-f429`), BTT Octopus Max EZ (`octopus-max-ez`), BTT Kraken (`kraken`), LDO Leviathan v1.2 (`ldo-leviathan-v1.2`), Mellow FLY Super8 Pro H723 (`fly-super8-pro-h723`) и FLY Super8 F407 (`fly-super8`), MKS Monster8 V2 (`mks-monster8-v2`); у `spider-v3-h723` добавлены алиасы `spider-h7`, `spider-v3-h7`. Для каждой платы — `boards/<id>.board`, конфиги сборки Klipper (USB, мост) и katapult (`configs/`), все получены `tools/gen_configs.py`.
- Платы голов: BTT EBB36/EBB42 v1.0 (F072, `ebb36-v1.0`), BTT EBB36/EBB42 Gen2 (`ebb-gen2`), Mellow FLY SHT36 v2 / SHT42 (`sht36-v2`) — только запись в реестре и конфиги сборки (`*-can.config`). **В `--heads` эти головы выбрать нельзя**: для них нет шаблона электроники (пины не подтверждены и не выдумываются), установщик отвечает `--heads <плата>: для платы … нет шаблона электроники`. Чтобы включить такую голову, достаточно добавить `templates/boards/<имя>.cfg` и поле `TEMPLATE` (см. [docs/hardware.md](docs/hardware.md#платы-голов)).
- `--heads` (`install_vostok.sh`, `configure_vostok.sh`, `gen_electronics.py`) теперь берёт допустимые значения из реестра: `none` и id или алиасы плат с `ROLE=head` (`Registry.head_value`, `head_choices`, `head_ids`). Старые значения `v1.3`, `v2`, `ebb42` и `--h36` работают как раньше, вывод и имена файлов не изменились; добавлены `ebb36` (алиас `ebb42`) и id голов. Меню «Платы голов» строится по реестру (те же три пункта). У плат голов поле `TEMPLATE` теперь указывает на `templates/boards/<имя>.cfg` (`h36_v1.3`, `h36_v2`, `ebb42`); `tools/gen_configs.py --check` проверяет, что файл есть.
- Выбор по умолчанию не изменился: на H723 — Octopus Pro, на F446 и F429 — Octopus Pro (`octopus-pro-f446`, `octopus-pro-f429`), а не Octopus без Pro или LDO Leviathan с тем же чипом (`rank_main_boards` ставит платы Octopus Pro, `Registry.guide_ids`, первыми внутри чипа). Меню выбора платы по семейству f4 (DFU без by-id) стало длиннее. `update_klipper_mcu.sh`: если серийного номера нет в `devices.tsv`, берётся конфиг чипа (`stm32f446xx.config`, Octopus Pro) с предупреждением «бывают разные платы», как у H723.
- Картинки распиновки новых плат в `pinouts/` (источники, коммиты и sha256 в `SOURCES.tsv`): листы BTT (Octopus не Pro, Octopus Max EZ, Kraken, EBB36/42 v1.0 и Gen2), MKS Monster8 V2, LDO Leviathan, Mellow FLY Super8; для FLY Super8 Pro и SHT36 v2 / SHT42 у Mellow листа pinout нет, лежат принципиальные схемы. У `fly-super8-pro-h723` в `PINOUT_NOTE` предупреждение про расхождение чипа (H743 и 8 МГц на схеме, H723 и 25 МГц в документации).
- Не добавлено: MKS SKIPR (встроенный хост RK3328, мост не подтверждён, драйверов не хватает), Fysetc Spider King407 (данных мало); головы на RP2040 (FLY SHT36 v3 / Max v3, MKS THR36 / THR42) — нужна отдельная доработка кода (семейство `rp2040`, BOOTSEL/UF2), описана в [docs/hardware.md](docs/hardware.md#платы-голов).
- Предупреждения в `NOTE` и документации: Super8 Pro (в схеме H743 и 8 МГц, в документации H723 и 25 МГц), Kraken (встроенные TMC2160, моста нет в реестре), SHT36 v2 (GD32F103 до 2022-10-28, APM32F072 в DFU `314b:0106`), Monster8 V2 (загрузчик 32KiB по отчёту сообщества), Leviathan (драйверов меньше 7), неоднозначный алиас `ebb36`.
- Тесты: `NO_PINOUT` в `test_pinouts` (лицензия на картинки не указана), `test_boards` (выбор по умолчанию на F446/F429, `--heads` из реестра), `test_install` (`--heads`), `test_update` (F446 при известном и неизвестном серийном номере), обновлены ожидаемые списки в `test_configurator`. Golden-эталоны переснятые: `boards/list_boards` (новые платы), `boards/bad_args` и `gen_matrix/err_bad_args` (новый текст ошибки `--heads`, usage `gen_electronics.py` без перечня значений), `help/*` (строка про `--heads`), `install/detect_auto_h723_2alps` и `configure/P_printer_data_env` (на H723 теперь шесть кандидатов вместо трёх); добавлены кейсы `gen_matrix/*` и `install_matrix/*` для новых плат.

## 1.6 — 2026-10-16

Каталог `pinouts/` с картинками распиновки плат и вывод пути и веб-ссылки на них в установщике.

- Новый каталог `installer/pinouts/<Производитель>/<Плата>/<ревизия>/`: официальные листы BTT (Octopus Pro v1.0 и v1.1, Manta M8P v1.0 / v1.1 / v2.0, EBB42 и EBB36), Fysetc (Spider v2.2 / v2.3 / v3.0, H36 v2.0 и принципиальная схема H36 v1.3), Mellow (FLY-C8). Источник, коммит, лицензия (у производителей не указана), размер и sha256 каждого файла — в `pinouts/SOURCES.tsv`; таблица «плата -> файлы» и пометки (лёгкий лист Octopus v1.0, схема вместо pinout у H36 v1.3, нет pinout у ALPS и Spider v3.0 H723) — в `pinouts/README.md`.
- Octopus Pro v1.1: рядом с картинкой и ссылкой печатается предупреждение, что часть пинов (HE0, HE2, Motor3-EN, RGB) отличается от v1.0 (поле `.board` `PINOUT_NOTE`, список изменений - в репозитории BTT).
- Формат `.board`: необязательное поле `PINOUT` (пути от `pinouts/` через пробел), заполнено во всех платах, кроме `alps` и `spider-v3-h723`. `Registry.pinout_paths`, `pinout_url` (адрес из `VOSTOK_PINOUT_URL`, по умолчанию страница каталога на GitHub), `Board.pinout_list`; переменная `PINOUTS_DIR` подменяет каталог. У `ebb42` уточнено поле `DOC`.
- Установщик печатает «Распиновка <плата>: <путь>» и «онлайн: <ссылка>» (если картинок нет - `DOC`): в плане установки у непроверенной платы, в подсказках входа в DFU главной платы и плат голов (один раз), в предупреждениях конфигуратора (пины по разъёмам, ЗАПОЛНИТЕ), при пересечениях пинов, в итоге `configure_vostok.sh` и в итоге `install_vostok.sh` (блок «Распиновка ваших плат»: главная плата, плата головы, ALPS).
- Веб-ссылка заработает только после слияния в upstream main (до этого работает локальный путь; адрес можно переопределить через `VOSTOK_PINOUT_URL`).
- Тесты: `tests/test_pinouts.py` (файлы, sha256, `SOURCES.tsv`, `PINOUT`, README), проверки в `test_boards`, `test_install`, `test_configurator`. Golden-эталоны переснятые: изменились только добавленные строки с распиновкой (`install/*`, `install_matrix/*`, `configure/*`).

## 1.5 — 2026-10-16

Установщик перенесён с bash на Python 3.8+ (только стандартная библиотека). Команды, флаги, переменные окружения, тексты вывода, коды возврата и форматы файлов (`devices.tsv`, `*.board`, конфиги сборки) не изменились: `install_vostok.sh`, `configure_vostok.sh`, `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh` остались точками входа и теперь запускают `python3 -m vostok <команда>`.

- Вся логика лежит в пакете `vostok/`; удалены `lib/vostok_config.sh` и `lib/boards.sh`. `tools/gen_configs.sh` заменён на `tools/gen_configs.py` (те же опции `--force`, `--board`, `--check`, `--build`, те же 36 конфигов); `tools/gen_electronics.py` сохранил путь и аргументы, но стал обёрткой над `vostok/`; обёртки `tools/mcu_merge.py`, `tools/pin_conflicts.py` и `tools/can_uuid.py` удалены (их логика доступна как `vostok.cfgfile` и `vostok.can_uuid`, установщик вызывает модули напрямую).
- Добавлены юнит-тесты (`python3 -m unittest discover tests`) и golden-эталоны вывода со старых скриптов (`tests/run_golden.sh`).
- Отличия от 1.3a (мелкие): Moonraker и скачивание конфигурации идут через `urllib`, `curl` для них не вызывается; без терминала и без `-y` вопрос сразу даёт `ОШИБКА: нужен терминал…` вместо служебных сообщений bash (`/dev/tty: No such device`, `ans: unbound variable`), код выхода 1 как раньше; файлы (`devices.tsv`, `moonraker.asvc`, `mcu_update.cfg`, темы) записываются атомарно; сбой внешней команды и непредвиденная ошибка дают одну строку `ОШИБКА: …` вместо обрыва скрипта или traceback; `flash_can` для моста ищет katapult в `BYID_DIR`, а не в жёстком `/dev/serial/by-id`; временный каталог конфигуратора удаляется всегда; проверка «bash 4.4+» больше не нужна.
- Требуется `python3` 3.8 или новее (на Debian 11 он есть); остальные требования прежние.
- `configure_vostok.sh --printer-data <нет каталога>` теперь останавливается с `ОШИБКА: нет каталога … (укажите --printer-data)`; раньше (1.3) каталог молча создавался и конфиг писался в него (проверка существовала в коде, но не срабатывала). Версия 1.4 не выпускалась: 1.5 — первый релиз на Python.
- В 1.5 вошли изменения ветки 1.3b (перенесены из bash в `vostok/`): отмечены проверенными на железе (по отчётам пользователей) Manta M8P v2.0 (с CB1 и CB2), Fysetc H36 v1.3 и v2, BTT EBB36 (запись `ebb42`, подпись «BTT EBB42/EBB36», алиас `ebb36`); подтверждены мост USB→CAN на M8P v2.0, прошивка голов «на столе» и по CAN, `--check-can`. `VERIFIED="yes"` в `boards/*.board`; предупреждение в плане установки для этих плат больше не выводится.
- Выбор главной платы по умолчанию: на H723 первой предлагается плата гайда (Octopus Pro), затем проверенные, затем остальные (`Registry.rank` в `vostok/boards.py`, порядок — `rank_main_boards` в `vostok/configurator.py`), чтобы Manta M8P v2.0 не вытеснила Octopus Pro после отметки проверенной.
- Документация: предупреждение в `docs/hardware.md` сокращено до одного абзаца, подробности собраны в `docs/tested.md` (проверено / только dry-run / не проверено).

## 1.3a — 2026-10-15

- Конфигуратор: пресеты пинов главных плат `templates/boards/main/` (`octopus_pro_v1.0`, `manta_m8p_v1.0`, `manta_m8p_v1.1`, `manta_m8p_v2.0`); поле `TEMPLATE` в `.board` указывает на пресет, `tools/gen_configs.sh --check` проверяет, что файл есть. Для этих плат `gen_electronics.py --template <имя>` подставляет моторы, сокеты и SPI драйверов, стол, вентиляторы, концевики, зонд, хотэнды (без плат голов) и таблицу «оборудование → разъём» в шапку; блоки помечены СВЕРЬТЕ. Платы не проверены на железе. Для Spider v2.x / v3.0 и FLY-C8 пресета нет: надёжного источника пинов не нашлось.
- Исправлено: SPI драйверов (`PA5/PA7/PA6`) больше не подставляется на платы, кроме Octopus Pro; в пресете `--template octopus_pro` для F446 использовались пины v1.1 (стол `PB0`), у Octopus Pro v1.0 это HE2 = `PB10`: F446 и F429 теперь используют `octopus_pro_v1.0`. Для H723 вывод не изменился (сверено побайтно).
- Тексты предупреждений и сообщений установщика называют плату пресета, а не «Octopus Pro».

## 1.3 — 2026-10-15

- Реестр плат: `boards/*.board` (по файлу на плату: чип, кварц, смещение приложения, пины CAN, подсказка DFU, проверена ли на железе) и `lib/boards.sh`. Подписи, конфиги сборки, подсказки DFU и проверки в установщике берутся из реестра, а не из привязки к чипу.
- Новые главные платы: BTT Octopus Pro v1.0 F429, BTT Manta M8P v1.0 / v1.1 / v2.0, Fysetc Spider v3.0 H723 / v3.0 F446 / v2.x, Mellow FLY-C8. **Все новые платы не проверены на железе**: параметры взяты из документации производителей, установщик предупреждает об этом в плане.
- `--main` принимает id и алиасы (`h723`, `f446` работают как раньше); `--list-boards` печатает реестр. Если на чипе несколько плат, установщик спрашивает (по умолчанию — плата из прошлого `devices.tsv`, иначе проверенная). Без вопросов (`-y`) при нескольких возможных платах и без записи в `devices.tsv` установщик останавливается и просит `--main <id>`: молча прошить плату другим конфигом нельзя.
- Отказ до прошивки для плат без USB-CAN моста (M8P v1.0, Spider v2.x) при платах голов по CAN.
- `tools/gen_configs.sh` строится по реестру; опции `--board ID`, `--check` (сравнение с `configs/`), `--build` (сборка всех конфигов). Конфиги новых плат: `configs/<id>.config`, `configs/<id>-canbridge.config`, `configs/katapult/<id>.config`; имена конфигов прежних плат не менялись.
- `update_klipper_mcu.sh` берёт конфиг USB-MCU из `devices.tsv` (по серийному номеру) и показывает название платы в `--list`.
- `tools/gen_electronics.py`: `--board-name`, `--board-file`, `--template octopus_pro|none`. Для плат без стокового конфига конфигуратор по умолчанию предлагает `generate` (шаблон без пинов); чужую распиновку (Octopus) по умолчанию не подставляет. `update_klipper_mcu.sh` игнорирует запись `devices.tsv`, если её конфиг собран под другой чип, и предупреждает, когда плата на чипе с несколькими вариантами не найдена в `devices.tsv`.
- Предупреждение о непроверенных платах со списком в `docs/hardware.md` и `docs/tested.md`. Octopus Pro F446 и платы голов H36 v1.3/v2, EBB42 помечены как не проверенные на железе (раньше F446 и H36 значились проверенными); проверены только Octopus Pro H723 и ALPS.
- Документация: таблица плат в `docs/hardware.md`, раздел «Как добавить плату» в `docs/build-configs.md`.

## 1.2d — 2026-10-12

- Тема K3D VOSTOK для KlipperScreen: `install_klipperscreen_theme.sh` и `klipperscreen-theme/` (палитра k3d.tech/vostok, знак K3D на заставке, шрифт Tektur из каталога `fonts/`, лицензия OFL). Каталог `styles/vostok` собирается из иконок `material-dark`, шрифт ставится в `~/.local/share/fonts`, тема включается в `KlipperScreen.conf`.
- Установщик ставит её вместе с темой Fluidd, если `~/KlipperScreen` есть; пропуск: `--skip-theme`.
- Опции: `--ks-dir`, `--printer-data`, `--no-activate`, `--force`, `--uninstall`, `--dry-run`.

## 1.2c — 2026-10-10

- Платы голов по умолчанию прошиваются «на столе»: katapult и Klipper за один сеанс DFU по USB, без 24 В и CAN. Способ выбирается в диалоге или `--heads-flash dfu|can`; вариант «Klipper по CAN» оставлен для собранного принтера (установщик заранее предупреждает про 24 В и CAN-кабели).
- `canbus_uuid` плат голов вычисляется по UID чипа, прочитанному в DFU (`tools/can_uuid.py`), UUID моста Octopus — по его USB-serial. Значения пишутся в `printer.cfg` и `devices.tsv` с предупреждением, что на шине они не проверены.
- Новая опция `--check-can`: после установки электроники в принтер читает `canbus_uuid` с шины, сверяет их и исправляет `devices.tsv` и `printer.cfg` (`tools/mcu_merge.py --set`).
- Подсказки в плане, шагах прошивки, итогах и меню ошибок переписаны под два способа.

## 1.2b — 2026-10-10

- Тема Fluidd K3D VOSTOK: `install_fluidd_theme.sh` и `fluidd-theme/` (бирюзовый `#009B98`, логотип K3D, шрифт Tektur, пресет в базе Moonraker).
- Установщик ставит тему отдельным этапом, пропуск: `--skip-theme`.
- Опции темы: `--force`, `--logo-copy`, `--no-activate`, `--dry-run`, `--uninstall`.

## 1.2a — 2026-10-09

- Автономный `configure_vostok.sh` и общая библиотека `lib/vostok_config.sh`: настройка конфига отдельно от установки.
- Генерация `electronics_*.cfg` под ваши платы и драйверы (`templates/`, `tools/gen_electronics.py`), дописывание `[mcu]` (`tools/mcu_merge.py`), поиск пересечений пинов (`tools/pin_conflicts.py`), дополнительные модули (`chamber_heater.cfg`).
- Чистая установка берёт всё из main, а существующий конфиг VOSTOK сохраняется: заменяются только `electronics_*.cfg`, `[mcu]` и include, а `printer_base.cfg`, `chamber_heater.cfg` и `SAVE_CONFIG` остаются.
- Исправлено: замена `[mcu]` съедала блок `SAVE_CONFIG`.
- В меню плат голов добавлен пункт «нет (пассивная плата, например fly miniAB)».

## 1.0a — 2026-10-09

Первая версия с номером. В неё вошло всё, что было сделано до введения версий (с 2026-10-08).

- `install_vostok.sh`: пакеты, KIAUH, форк Klipper, Moonraker, Fluidd, katapult, прошивка ALPS, плат голов (H36 v1.3/v2, EBB42) и Octopus Pro (H723/F446) по USB или через мост USB-CAN, запись `printer.cfg`.
- `update_klipper_mcu.sh` и кнопка `mcu-update` в меню питания Fluidd: обновление Klipper и перепрошивка плат.
- Проверки окружения перед установкой и прошивкой (sudo, место, инструменты, поддержка CAN в ядре).
- Прошивка не прерывается на ошибке одной платы: меню «повторить / через DFU / Klipper напрямую по DFU / пропустить / прервать».
- Опции `--skip-board` и `--reflash`, автопропуск плат с актуальным Klipper.
- Непрошитые платы получают в `printer.cfg` заглушку `ЗАПОЛНИТЕ`, в конце выводится список проблемных плат.
- Версионирование: файл `VERSION` и опция `-V`/`--version`.
