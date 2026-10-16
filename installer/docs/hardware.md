# Платы и состав каталога

🇷🇺 Русский | [🇬🇧 English](hardware.en.md)

[← К оглавлению](../README.md)

## Что поддерживается

| Узел | Варианты |
|---|---|
| Главная плата | BTT Octopus Pro v1.1 **H723** (по гайду) или Octopus Pro **F446**; также платы из реестра `boards/` (таблица ниже) |
| Платы голов (CAN) | Fysetc **H36** v1.3 / v2 или BTT **EBB42/EBB36**; можно без них |
| Датчики ALPS (USB) | 0, 1 или 2 |

- **С платами голов** Octopus прошивается как **мост USB→CAN**, как в гайде, а платы голов работают по CAN (`can0`, 1 Мбит). Прошить их можно двумя способами:
  - **«на столе»** (по умолчанию): katapult и Klipper сразу по DFU через USB, без 24 В и CAN; `canbus_uuid` вычисляется по UID чипа и после сборки проверяется командой `install_vostok.sh --check-can`;
  - **в собранном принтере**: katapult по DFU, Klipper по CAN (нужны 24 В и CAN-кабели).
- **Без плат голов по CAN** (с пассивной платой головы Fly miniAB, подключённой напрямую к Octopus) Octopus работает по обычному USB.
- ALPS (STM32F072) прошиваются по USB: katapult через DFU, затем Klipper.

## Главные платы

Параметры плат лежат в реестре `boards/*.board` (`./install_vostok.sh --list-boards` печатает его). Плата выбирается опцией `--main <id|алиас>` или определяется по подключённому железу; если на найденном чипе несколько плат, установщик спрашивает.

| id (алиасы) | Чип | Кварц | Klipper начинается с | USB-CAN мост (пины CAN) | Вход в DFU | Источник данных | Проверено на железе |
|---|---|---|---|---|---|---|---|
| `octopus-pro-h723` (`h723`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1) | джампер BOOT0 + RESET | гайд k3d | **да** |
| `octopus-pro-f446` (`f446`) | STM32F446 | 12 МГц | 0x08008000 | есть (PD0/PD1) | джампер BOOT0 + RESET | схема платы | нет |
| `octopus-pro-f429` (`f429`) | STM32F429 | 8 МГц | 0x08008000 | есть (PD0/PD1) | джампер BOOT0 + RESET | `generic-bigtreetech-octopus-pro-v1.0.cfg` из Klipper | нет |
| `manta-m8p-v1.0` (`m8p-v1.0`) | STM32G0B1 | 8 МГц | 0x08002000 | **нет** | BOOT + RESET | BTT, репозиторий Manta-M8P | нет |
| `manta-m8p-v1.1` (`m8p-v1.1`) | STM32G0B1 | 8 МГц | 0x08002000 | есть (PD12/PD13) | BOOT + RESET | BTT, репозиторий Manta-M8P; `generic-bigtreetech-manta-m8p-v1.1.cfg` | нет |
| `manta-m8p-v2.0` (`m8p-v2.0`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1) | BOOT + RESET | BTT, `generic-bigtreetech-manta-m8p-V2_0.cfg` | **да** |
| `spider-v3-h723` (`spider-h723`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1) | кнопки BT0 + RST | docs.fysetc.com | нет |
| `spider-v3-f446` (`spider-f446`) | STM32F446 | 12 МГц | 0x08008000 | есть (PD0/PD1, документацией не подтверждены) | кнопки BT0 + RST | docs.fysetc.com | нет |
| `spider-v2-f446` (`spider-v2`, `spider-v2.x`) | STM32F446 | 12 МГц | 0x08008000 | **нет** | перемычка BT0–3.3V + RESET | `generic-fysetc-spider.cfg` из Klipper, Voron docs | нет |
| `fly-c8` (`flyc8`, `fly-c6`, `flyc6`) | STM32F407 | 8 МГц | 0x08008000 | есть (PB8/PB9) | `sudo fly-flash -d c8 -u` или BOOT + RESET | Mellow-3D/klipper-docs, `docs/board/fly_C8` | нет |

Katapult у всех плат пишется по DFU с 0x08000000. USB у всех плат — PA11/PA12.

> ⚠️ **Проверены на железе:** Octopus Pro v1.1 H723, Manta M8P v2.0 (CB1 и CB2), платы голов Fysetc H36 v1.3 / v2 и BTT EBB36/EBB42, ALPS; мост USB→CAN, прошивка голов «на столе» и по CAN, `--check-can`. **Остальные платы** (Octopus Pro F446 и F429, Manta M8P v1.0 / v1.1, Spider v3.0 H723 / F446, Spider v2.x, FLY-C8) настроены по документации производителей и на железе не проверялись: сверьте плату, кварц и вход в DFU, первую прошивку делайте без нагревателей и моторов, о проблемах сообщайте разработчику. Подробности: [tested.md](tested.md).
- **M8P v1.0 и Spider v2.x без USB-CAN моста**: платы голов по CAN с ними не поддерживаются, установщик отказывает (нужен `--heads none`).
- **Octopus Pro F429** — только версия v1.0; у v1.1 другая распиновка и чип (H723), для неё используйте `octopus-pro-h723`.
- **FLY-C8**: DIP-переключатели 1 и 2 направляют внутренний USB к ARM-части платы, 3 и 4 — на разъём Type-C; прошивка идёт через DFU по USB. В документации Mellow платы «Fly C6» нет, под этим названием понимается FLY-C8 (алиасы `fly-c6`, `flyc6`).
- **Manta M8P**: MCU стоит на одной плате с CB1/CM4, USB к нему внутренний.
- **Пины и конфигуратор.** Стокового `electronics_*.cfg` для новых плат нет: конфигуратор генерирует шаблон без пинов (`--config-source generate`) или берёт ваш файл из `user_configs/` (`--config-source user`); пресеты пинов есть у Octopus Pro (H723 — по гайду; F446/F429 — `octopus_pro_v1.0`) и Manta M8P v1.0 / v1.1 / v2.0 (`templates/boards/main/`, не проверены на железе); у Spider v2.x / v3.0 и FLY-C8 пресета нет (см. [CONFIGURATOR.md](../CONFIGURATOR.md)).

Как добавить свою плату: [build-configs.md](build-configs.md#как-добавить-плату).

## Распиновка

Картинки распиновки плат лежат в [`pinouts/`](../pinouts/README.md) (таблица «плата -> файлы», источники и лицензии — в `pinouts/SOURCES.tsv`). Установщик печатает путь и веб-ссылку на картинку вашей платы в плане установки (для непроверенной платы), при входе в DFU, в предупреждениях конфигуратора (пустые пины ЗАПОЛНИТЕ, пересечения пинов) и в итоге. Картинки задаёт поле `PINOUT` в `boards/<id>.board`; если оно пусто (ALPS, Spider v3.0 H723), показывается `DOC`. Адрес можно заменить переменной `VOSTOK_PINOUT_URL`.

## Состав каталога `installer/`

| Путь | Что это |
|---|---|
| `install_vostok.sh` | первоначальная установка (все этапы) |
| `configure_vostok.sh` | настройка конфига отдельно от установки, см. [CONFIGURATOR.md](../CONFIGURATOR.md) |
| `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `mcu-update.service.in` | обновление Klipper и прошивок, кнопка в Fluidd |
| `install_fluidd_theme.sh`, `fluidd-theme/` | тема K3D VOSTOK для Fluidd: логотип, `custom.css`, пресет |
| `install_klipperscreen_theme.sh`, `klipperscreen-theme/` | тема K3D VOSTOK для KlipperScreen: `style.css`, `style.conf`, знак K3D, шрифт Tektur |
| `vostok/` | Python-пакет, в котором работает вся логика установщика (stdlib, Python 3.8+); `*.sh` в корне - тонкие обёртки над `python3 -m vostok <команда>` |
| `templates/` | шаблон конфига электроники без плат и драйверов (`electronics_blank.cfg`), пресеты плат (`boards/`) и драйверов (`drivers/`) |
| `tools/` | `gen_electronics.py` (генерация конфига электроники; обёртка над `vostok/electronics.py`), `gen_configs.py` (конфиги сборки прошивок по реестру `boards/`) |
| `pinouts/` | картинки распиновки плат с источниками (`SOURCES.tsv`) |
| `boards/` | реестр плат: по файлу `<id>.board` на плату (параметры сборки, подписи, подсказки DFU, проверена ли на железе) |
| `tests/` | юнит-тесты (`python3 -m unittest discover tests`) и golden-эталоны вывода (`tests/run_golden.sh`) |
| `configs/` | конфиги сборки Klipper и katapult |
| `docs/` | эта документация по разделам |
| `VERSION`, `CHANGELOG.md` | версия установщика (`-V`/`--version` у всех скриптов) и [история изменений](../CHANGELOG.md) |
