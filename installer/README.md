# Установщик VOSTOK

🇷🇺 Русский | [🇬🇧 English](README.en.md)

Скрипты, которые разворачивают VOSTOK на чистой системе по гайду [💾 Прошивка электроники](https://k3d.tech/vostok/manual/electronics/firmware/) и потом обновляют Klipper и прошивки плат одной кнопкой в Fluidd.

- `install_vostok.sh` — первоначальная установка: пакеты, KIAUH, [форк Klipper](https://github.com/dmbutyugin/klipper/tree/generic-cartesian), Moonraker, Fluidd, katapult, прошивка всех плат, конфигурация принтера, кнопка обновления.
- `update_klipper_mcu.sh` — обновление Klipper и перепрошивка всех плат (его же запускает кнопка).
- `install_fluidd_button.sh` — ставит в Fluidd кнопку `mcu-update` (меню питания ⏻ → `mcu-update` → Start).

> ⚠️ Установщик прошивает платы и просит вручную переключать джамперы и кабели. Читайте подсказки на каждом шаге. Без `--dry-run` он меняет систему: ставит пакеты, службы и прошивки.

## Что поддерживается

| Узел | Варианты |
|---|---|
| Главная плата | BTT Octopus Pro v1.1 **H723** (по гайду) или Octopus Pro **F446** |
| Платы голов (CAN) | Fysetc **H36** v1.3 / v2 или BTT **EBB42**; можно без них |
| Датчики ALPS (USB) | 0, 1 или 2 |

- **С платами голов** Octopus прошивается как **мост USB→CAN**, как в гайде, а платы голов — по CAN (`can0`, 1 Мбит).
- **Без плат голов** Octopus работает по обычному USB.
- ALPS (STM32F072) прошиваются по USB: katapult через DFU, затем Klipper.

## Требования и проверки

Перед установкой скрипт сам проверяет окружение и останавливается с понятным сообщением, если что-то не так (`--only-detect` и `--dry-run` только показывают результат):

- **система**: `sudo`, `apt-get`, `dpkg`, `systemctl`, запущенный systemd, базовые утилиты; свободно не менее 2 ГБ в домашнем каталоге; ОЗУ + swap не менее 1 ГБ (иначе предупреждение); `python3` 3.8 или новее;
- **доступ**: запуск не от root, терминал для диалога (если будут шаги с железом), членство в группе `dialout` (иначе `sudo usermod -aG dialout $USER` и перелогиниться), доступ к github.com;
- **инструменты** (недостающие ставятся из пакетов автоматически, при `--skip-software` скрипт только сообщает, что поставить): `python3` (+ `venv`, `pyserial`), `git`, `curl`, `tar`, `make`, `arm-none-eabi-gcc`, `dfu-util`, `lsusb`, `ip`;
- **для схемы с платами голов (мост USB→CAN)**: ядро с `CONFIG_CAN`, `CONFIG_CAN_RAW`, `CONFIG_CAN_GS_USB`. Если ядро собрано без CAN (так у части образов Orange Pi), скрипт остановится до прошивки, чтобы не оставить Octopus в режиме моста без рабочего `can0`.

## Быстрый старт

Нужна Debian-подобная система (Armbian, Raspberry Pi OS, BTT Pi и т. п.), обычный пользователь с `sudo`, интернет и подключённые по USB платы. Питание 24 В для прошивки по USB не нужно, для прошивки плат голов по CAN — нужно.

```bash
git clone https://github.com/dmitry-sorkin/vostok_configuration.git
cd vostok_configuration/installer

./install_vostok.sh --only-detect   # что видит скрипт, ничего не меняет
./install_vostok.sh --dry-run       # все шаги и команды без изменений
./install_vostok.sh                 # установка
```

Каталог клона должен остаться на месте: кнопка обновления запускает скрипты из него. Если установщик запущен из клона, конфигурацию принтера он берёт оттуда же (удобно проверять форки и PR); иначе скачивает `main`. Переменная `VOSTOK_CFG_LOCAL=0` заставляет всегда скачивать, `VOSTOK_CFG_LOCAL=/путь` — взять свой каталог.

## Что делает установщик

1. Проверки и пакеты (`apt`: git, dfu-util, gcc-arm-none-eabi, python3-serial и др.).
2. KIAUH → Klipper (форк `dmbutyugin/klipper`, ветка `generic-cartesian`), Moonraker, Fluidd; расширение `gcode_shell_command`; katapult. Если `~/klipper` уже есть, но не форк, предложит переключить.
3. Определяет платы (`/dev/serial/by-id`, режим DFU, мост USB-CAN), спрашивает о том, что определить нельзя (главная плата, платы голов, число ALPS), показывает план.
4. Если есть платы голов — настраивает `can0` (`/etc/network/interfaces.d/can0`, 1 Мбит, `txqueuelen 128`).
5. Прошивает платы по очереди и на каждом шаге говорит, что сделать руками:
   - **ALPS**: BOOT + RESET → DFU → katapult → Klipper;
   - **платы голов**: BOOT0/BOOT + RESET → DFU → katapult; позже Klipper по CAN с проверкой через `canbus_query.py`;
   - **Octopus**: джампер BOOT0 + RESET → DFU → katapult (потом снять джампер) → Klipper (USB или мост USB→CAN).

   Если на плате уже есть katapult или Klipper, на запросе DFU введите `s` + Enter и дважды быстро нажмите RESET.
6. Конфигурация принтера. Спрашивает, откуда взять конфиг электроники: **стандартный** (корень репозитория, поддерживается автором) или **пользовательский** (`user_configs/`, конфиги пользователей; перед выбором сверьте схему подключения в начале файла — неверная схема может вывести электронику из строя). Копирует `printer.cfg`, `printer_base.cfg`, `chamber_heater.cfg`, выбранный `electronics_*.cfg`, `postprocessing/` в `~/printer_data/config` и вписывает найденные `[mcu]`, `[mcu T0CB]`/`[mcu T1CB]` (для EBB42 — `T0_EBB`/`T1_EBB`, имена берутся из выбранного файла) и `[mcu alps]`. **Существующий `printer.cfg` не трогается**, скрипт только печатает готовый блок `[mcu …]`.
7. Запускает Klipper, сверяет версии прошивок, ставит кнопку обновления.

После установки вручную: адаптировать `electronics_*.cfg` под свою проводку, проверить термисторы голов (возьмите термистор пальцами — температура должна расти у нужной головы, иначе поменяйте местами секции `T0…`/`T1…`), для ALPS добавить `[load_cell_probe]` и выполнить `LOAD_CELL_CALIBRATE`.

## Опции `install_vostok.sh`

| Опция | Назначение |
|---|---|
| `--main h723\|f446` | главная плата (иначе определит/спросит) |
| `--heads none\|v1.3\|v2\|ebb42` | платы голов (`--h36` — прежнее имя) |
| `--alps 0\|1\|2` | число ALPS |
| `--config-source standard\|user` | источник конфига: корень репозитория или `user_configs/` |
| `--electronics ФАЙЛ` | конкретный `electronics_*.cfg` |
| `--only-detect` | только определить платы и показать план |
| `--dry-run` | показать шаги и команды, ничего не менять |
| `--skip-software` / `--skip-flash` / `--skip-config` / `--skip-button` | пропустить этап |
| `--upgrade` | `apt upgrade` перед установкой |
| `-y` | не задавать вопросов, где есть ответ по умолчанию (шаги с железом всё равно ждут Enter) |

Лог: `~/printer_data/logs/vostok_install.log`. Установка повторяема: уже сделанное пропускается.

## Кнопка обновления

В Fluidd: ⏻ (вверху справа) → `mcu-update` → Start. Скрипт обновит ветку Klipper (`git fast-forward`, без KIAUH и sudo-пароля), соберёт прошивки, прошьёт все платы через katapult (USB и CAN; Octopus-мост последним) и проверит, что версии прошивок совпадают с хостом. Если обновлений нет, напишет «всё актуально». Лог: `~/printer_data/logs/klipper_mcu_update.log`.

Из терминала:

```bash
./update_klipper_mcu.sh --list                    # что найдено, ничего не меняет
./update_klipper_mcu.sh                           # обновить хост (KIAUH), собрать и прошить
./update_klipper_mcu.sh --no-update --force-flash # перепрошить текущей версией
```

**Не нажимайте Stop** на `mcu-update` во время прошивки. Кнопку можно поставить и отдельно, без установщика: `./install_fluidd_button.sh` (`--dry-run`, `--uninstall`). Форк Klipper нельзя обновить штатной кнопкой Update Manager, поэтому и нужна эта: после обновления хоста прошивки плат обязательно обновить, иначе Klipper не запустится (`MCU Protocol error`).

## Если прошивка не удалась

Katapult остаётся в плате, прошивку можно повторить; Klipper на это время остановлен.
1. `ls /dev/serial/by-id/` — плата может быть `usb-katapult_…`. Нет — дважды быстро нажмите RESET.
2. `python3 ~/katapult/scripts/flashtool.py -d /dev/serial/by-id/usb-katapult_… -f installer/firmware/<файл>.bin`
3. CAN: `ip -s -d link show can0` (`state UP`, `bitrate 1000000`, ошибок нет). На шине должно быть около 60 Ом (два терминатора по 120 Ом), состояние BUS-OFF лечится перезапуском интерфейса: `sudo ip link set can0 down type can && sudo ip link set can0 up type can bitrate 1000000`.
4. `sudo systemctl start klipper`.

Скрипты сами печатают эти подсказки при ошибках.

## Параметры сборки прошивок

Лежат в `configs/` (Klipper) и `configs/katapult/` (katapult). Воспроизвести: `tools/gen_configs.sh --force`. Значения взяты из гайда; для Octopus Pro F446 (гайд её не описывает: 12 МГц, загрузчик 32KiB, USB PA11/PA12) и EBB42 (STM32G0B1, 8 МГц, CAN PB0/PB1) — по документации и схемам плат. Если у вашей платы другой кварц или смещение загрузчика, поправьте конфиг: `make menuconfig KCONFIG_CONFIG=…` в каталоге Klipper. Соответствие «серийный номер / UUID → конфиг сборки» установщик пишет в `devices.tsv` (его читает кнопка).

## Что проверено

На реальном принтере проверены: определение плат, сборка и прошивка USB-вариантов (Octopus Pro H723 по USB, ALPS на STM32F072), кнопка в Fluidd, сборка всех конфигов, генерация `printer.cfg`. **Не проверено на железе**: чистая установка KIAUH через CLI, мост USB→CAN, платы голов H36 и EBB42, Octopus Pro F446 и определение чипа в DFU по Option Bytes. Если что-то не сходится с вашей платой — пишите в issue с логом.

## Удаление

`./install_fluidd_button.sh --uninstall` убирает сервис, drop-in Moonraker и sudoers-правило.
