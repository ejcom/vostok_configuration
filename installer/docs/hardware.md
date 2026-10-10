# Платы и состав каталога

🇷🇺 Русский | [🇬🇧 English](hardware.en.md)

[← К оглавлению](../README.md)

## Что поддерживается

| Узел | Варианты |
|---|---|
| Главная плата | BTT Octopus Pro v1.1 **H723** (по гайду) или Octopus Pro **F446** |
| Платы голов (CAN) | Fysetc **H36** v1.3 / v2 или BTT **EBB42**; можно без них |
| Датчики ALPS (USB) | 0, 1 или 2 |

- **С платами голов** Octopus прошивается как **мост USB→CAN**, как в гайде, а платы голов работают по CAN (`can0`, 1 Мбит). Прошить их можно двумя способами:
  - **«на столе»** (по умолчанию): katapult и Klipper сразу по DFU через USB, без 24 В и CAN; `canbus_uuid` вычисляется по UID чипа и после сборки проверяется командой `install_vostok.sh --check-can`;
  - **в собранном принтере**: katapult по DFU, Klipper по CAN (нужны 24 В и CAN-кабели).
- **Без плат голов по CAN** (с пассивной платой головы Fly miniAB, подключённой напрямую к Octopus) Octopus работает по обычному USB.
- ALPS (STM32F072) прошиваются по USB: katapult через DFU, затем Klipper.

## Состав каталога `installer/`

| Путь | Что это |
|---|---|
| `install_vostok.sh` | первоначальная установка (все этапы) |
| `configure_vostok.sh` | настройка конфига отдельно от установки, см. [CONFIGURATOR.md](../CONFIGURATOR.md) |
| `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `mcu-update.service.in` | обновление Klipper и прошивок, кнопка в Fluidd |
| `install_fluidd_theme.sh`, `fluidd-theme/` | тема K3D VOSTOK для Fluidd: логотип, `custom.css`, пресет |
| `lib/vostok_config.sh` | общая библиотека настройки конфига (её подключают `install_vostok.sh` и `configure_vostok.sh`) |
| `templates/` | шаблон конфига электроники без плат и драйверов (`electronics_blank.cfg`), пресеты плат (`boards/`) и драйверов (`drivers/`) |
| `tools/` | `gen_electronics.py` (генерация конфига электроники), `mcu_merge.py` (дописывание `[mcu]`, `--set` для `canbus_uuid`), `can_uuid.py` (canbus_uuid по UID чипа), `pin_conflicts.py` (поиск повторяющихся пинов), `gen_configs.sh` (конфиги сборки прошивок) |
| `configs/` | конфиги сборки Klipper и katapult |
| `docs/` | эта документация по разделам |
| `VERSION`, `CHANGELOG.md` | версия установщика (`-V`/`--version` у всех скриптов) и [история изменений](../CHANGELOG.md) |
