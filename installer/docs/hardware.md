# Платы и состав каталога

🇷🇺 Русский | [🇬🇧 English](hardware.en.md)

[← К оглавлению](../README.md)

## Что поддерживается

| Узел | Варианты |
|---|---|
| Главная плата | BTT Octopus Pro v1.1 **H723** (по гайду) или Octopus Pro **F446**; также платы из реестра `boards/` (таблица ниже) |
| Платы голов (CAN) | Fysetc **H36** v1.3 / v2 или BTT **EBB42**; можно без них |
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
| `manta-m8p-v2.0` (`m8p-v2.0`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1) | BOOT + RESET | BTT, `generic-bigtreetech-manta-m8p-V2_0.cfg` | нет |
| `spider-v3-h723` (`spider-h723`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1) | кнопки BT0 + RST | docs.fysetc.com | нет |
| `spider-v3-f446` (`spider-f446`) | STM32F446 | 12 МГц | 0x08008000 | есть (PD0/PD1, документацией не подтверждены) | кнопки BT0 + RST | docs.fysetc.com | нет |
| `spider-v2-f446` (`spider-v2`, `spider-v2.x`) | STM32F446 | 12 МГц | 0x08008000 | **нет** | перемычка BT0–3.3V + RESET | `generic-fysetc-spider.cfg` из Klipper, Voron docs | нет |
| `fly-c8` (`flyc8`, `fly-c6`, `flyc6`) | STM32F407 | 8 МГц | 0x08008000 | есть (PB8/PB9) | `sudo fly-flash -d c8 -u` или BOOT + RESET | Mellow-3D/klipper-docs, `docs/board/fly_C8` | нет |

Katapult у всех плат пишется по DFU с 0x08000000. USB у всех плат — PA11/PA12.

> ⚠️ **Платы, кроме Octopus Pro H723, на железе не проверены (Octopus Pro F446 и платы голов H36/EBB42 тоже).** Их параметры взяты из документации производителей и исходников Klipper/katapult, конфиги прошивок собираются, но ни одна новая плата установщиком не прошивалась. Перед первой прошивкой сверьте плату, кварц и способ входа в DFU с документацией производителя.
>
> **Проверено на железе:** Octopus Pro v1.1 H723 и ALPS (F072). Больше ничего.
>
> **Не проверены на железе (платы):**
> - главные: Octopus Pro F446, Octopus Pro v1.0 F429, Manta M8P v1.0 / v1.1 / v2.0, Spider v3.0 H723, Spider v3.0 F446, Spider v2.x, FLY-C8;
> - платы голов: Fysetc H36 v1.3, Fysetc H36 v2, BTT EBB42.
>
> **Что не проверено на железе:**
> - **Прошивка целиком** (katapult и Klipper за один сеанс DFU, затем запуск) на Octopus Pro F446 и F429, Manta M8P v1.0/v1.1/v2.0, Spider v3.0 H723/F446, Spider v2.x и FLY-C8.
> - **Вход в DFU:** кнопки BOOT/RESET у Manta M8P, BT0/RST у Spider v3, перемычка BT0–3.3V у Spider v2.x, `fly-flash -d c8 -u` и положение DIP-переключателей у FLY-C8.
> - **Определение платы по DFU:** семейство чипа читается по адресу Option Bytes; на железе это проверено только для F0 и H7, для F4 (F407/F429/F446) и G0/G4 — только по документации ST. Платы на одном чипе (H723: Octopus, Manta v2.0, Spider v3.0) по DFU неразличимы, их различает только ваш выбор.
> - **Пины CAN моста:** Manta M8P v1.1 (PD12/PD13) и FLY-C8 (PB8/PB9) по документации; для Spider v3.0 F446 (PD0/PD1) документация пины не подтверждает.
> - **Katapult на новых платах:** смещения приложения (128/32/8 КиБ), двойной RESET, светодиод не задан. Запись katapult по DFU с `mass-erase` стирает весь флеш, включая штатный загрузчик производителя; вернуть его можно только его `.bin` через ROM-загрузчик STM32 (DFU остаётся доступным всегда).
> - **canbus_uuid:** чтение UID чипа по DFU и вычисление `canbus_uuid` на железе не проверялись ни на одной плате (в том числе на новых).
> - **Допущение про «Fly C6»:** в документации Mellow такой платы нет, под ней понимается FLY-C8.
>
> Первую прошивку новой платы делайте под наблюдением, без подключённых нагревателей и моторов, а о проблемах сообщайте разработчику.
- **M8P v1.0 и Spider v2.x без USB-CAN моста**: платы голов по CAN с ними не поддерживаются, установщик отказывает (нужен `--heads none`).
- **Octopus Pro F429** — только версия v1.0; у v1.1 другая распиновка и чип (H723), для неё используйте `octopus-pro-h723`.
- **FLY-C8**: DIP-переключатели 1 и 2 направляют внутренний USB к ARM-части платы, 3 и 4 — на разъём Type-C; прошивка идёт через DFU по USB. В документации Mellow платы «Fly C6» нет, под этим названием понимается FLY-C8 (алиасы `fly-c6`, `flyc6`).
- **Manta M8P**: MCU стоит на одной плате с CB1/CM4, USB к нему внутренний.
- **Пины и конфигуратор.** Стокового `electronics_*.cfg` для новых плат нет: конфигуратор генерирует шаблон без пинов (`--config-source generate`) или берёт ваш файл из `user_configs/` (`--config-source user`); пресеты пинов есть у Octopus Pro (H723 — по гайду; F446/F429 — `octopus_pro_v1.0`) и Manta M8P v1.0 / v1.1 / v2.0 (`templates/boards/main/`, не проверены на железе); у Spider v2.x / v3.0 и FLY-C8 пресета нет (см. [CONFIGURATOR.md](../CONFIGURATOR.md)).

Как добавить свою плату: [build-configs.md](build-configs.md#как-добавить-плату).

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
| `tools/` | `gen_electronics.py` (генерация конфига электроники), `mcu_merge.py` (дописывание `[mcu]`, `--set` для `canbus_uuid`), `can_uuid.py` (canbus_uuid по UID чипа), `pin_conflicts.py` (поиск повторяющихся пинов); `mcu_merge.py`, `pin_conflicts.py`, `can_uuid.py`, `gen_electronics.py` - обёртки над модулями `vostok/`, `gen_configs.py` (конфиги сборки прошивок по реестру `boards/`) |
| `boards/` | реестр плат: по файлу `<id>.board` на плату (параметры сборки, подписи, подсказки DFU, проверена ли на железе) |
| `tests/` | юнит-тесты (`python3 -m unittest discover tests`) и golden-эталоны вывода (`tests/run_golden.sh`) |
| `configs/` | конфиги сборки Klipper и katapult |
| `docs/` | эта документация по разделам |
| `VERSION`, `CHANGELOG.md` | версия установщика (`-V`/`--version` у всех скриптов) и [история изменений](../CHANGELOG.md) |
