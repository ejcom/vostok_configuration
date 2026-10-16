# История изменений установщика VOSTOK

🇷🇺 Русский | [🇬🇧 English](CHANGELOG.en.md)

Текущая версия записана в файле `VERSION` (`-V`/`--version` у всех скриптов). Описание: [README.md](README.md).

## 1.4 — 2026-10-16

Установщик перенесён с bash на Python 3.8+ (только стандартная библиотека). Команды, флаги, переменные окружения, тексты вывода, коды возврата и форматы файлов (`devices.tsv`, `*.board`, конфиги сборки) не изменились: `install_vostok.sh`, `configure_vostok.sh`, `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `install_fluidd_theme.sh`, `install_klipperscreen_theme.sh` остались точками входа и теперь запускают `python3 -m vostok <команда>`.

- Вся логика лежит в пакете `vostok/`; удалены `lib/vostok_config.sh` и `lib/boards.sh`. `tools/gen_configs.sh` заменён на `tools/gen_configs.py` (те же опции `--force`, `--board`, `--check`, `--build`, те же 36 конфигов); `tools/gen_electronics.py` сохранил путь и аргументы, но стал обёрткой над `vostok/`; обёртки `tools/mcu_merge.py`, `tools/pin_conflicts.py` и `tools/can_uuid.py` удалены (их логика доступна как `vostok.cfgfile` и `vostok.can_uuid`, установщик вызывает модули напрямую).
- Добавлены юнит-тесты (`python3 -m unittest discover tests`) и golden-эталоны вывода со старых скриптов (`tests/run_golden.sh`).
- Отличия от 1.3a (мелкие): Moonraker и скачивание конфигурации идут через `urllib`, `curl` для них не вызывается; без терминала и без `-y` вопрос сразу даёт `ОШИБКА: нужен терминал…` вместо служебных сообщений bash (`/dev/tty: No such device`, `ans: unbound variable`), код выхода 1 как раньше; файлы (`devices.tsv`, `moonraker.asvc`, `mcu_update.cfg`, темы) записываются атомарно; сбой внешней команды и непредвиденная ошибка дают одну строку `ОШИБКА: …` вместо обрыва скрипта или traceback; `flash_can` для моста ищет katapult в `BYID_DIR`, а не в жёстком `/dev/serial/by-id`; временный каталог конфигуратора удаляется всегда; проверка «bash 4.4+» больше не нужна.
- Требуется `python3` 3.8 или новее (на Debian 11 он есть); остальные требования прежние.

## 1.3a — 2026-10-15

- Конфигуратор: пресеты пинов главных плат `templates/boards/main/` (`octopus_pro_v1.0`, `manta_m8p_v1.0`, `manta_m8p_v1.1`, `manta_m8p_v2.0`); поле `TEMPLATE` в `.board` указывает на пресет, `tools/gen_configs.sh --check` проверяет, что файл есть. Для этих плат `gen_electronics.py --template <имя>` подставляет моторы, сокеты и SPI драйверов, стол, вентиляторы, концевики, зонд, хотэнды (без плат голов) и таблицу «оборудование → разъём» в шапку; блоки помечены СВЕРЬТЕ. Платы не проверены на железе. Для Spider v2.x / v3.0 и FLY-C8 пресета нет: надёжного источника пинов не нашлось.
- Исправлено: SPI драйверов (`PA5/PA7/PA6`) больше не подставляется на платы, кроме Octopus Pro; в пресете `--template octopus_pro` для F446 использовались пины v1.1 (стол `PB0`), у Octopus Pro v1.0 это HE2 = `PB10`: F446 и F429 теперь используют `octopus_pro_v1.0`. Для H723 вывод не изменился (сверено побайтно).
- Тексты предупреждений и сообщений установщика называют плату пресета, а не «Octopus Pro».

## 1.3 — 2026-10-15

- Реестр плат: `boards/*.board` (по файлу на плату: чип, кварц, смещение приложения, пины CAN, подсказка DFU, проверена ли на железе) и `lib/boards.sh`. Подписи, конфиги сборки, подсказки DFU и проверки в установщике берутся из реестра, а не из привязки к чипу.
- Новые главные платы: BTT Octopus Pro v1.0 F429, BTT Manta M8P v1.0 / v1.1 / v2.0, Fysetc Spider v3.0 H723 / v3.0 F446 / v2.x, Mellow FLY-C8 (алиасы `fly-c6`, `flyc6`). **Все новые платы не проверены на железе**: параметры взяты из документации производителей, установщик предупреждает об этом в плане.
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
