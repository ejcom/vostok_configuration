# Платы и состав каталога

🇷🇺 Русский | [🇬🇧 English](hardware.en.md)

[← К оглавлению](../README.md)

## Что поддерживается

| Узел | Варианты |
|---|---|
| Главная плата | BTT Octopus Pro v1.1 **H723** (по гайду) или Octopus Pro **F446**; также платы из реестра `boards/` (таблица ниже) |
| Платы голов (CAN) | Fysetc **H36** v1.3 / v2 или BTT **EBB42/EBB36** v1.1/v1.2; другие головы реестра пока только собираются (см. «Платы голов» ниже); можно без них |
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
| `fly-c8` (`flyc8`) | STM32F407 | 8 МГц | 0x08008000 | есть (PB8/PB9) | `sudo fly-flash -d c8 -u` или BOOT + RESET | Mellow-3D/klipper-docs, `docs/board/fly_C8` | нет |
| `octopus-f446` (`octopus-v1.1-f446`, `octopus-v1.0-f446`) | STM32F446 | 12 МГц | 0x08008000 | есть (PD0/PD1, мост не подтверждён) | джампер BOOT0 (J75) + RESET | `generic-bigtreetech-octopus-v1.1.cfg` из Klipper, репозиторий BTT | нет |
| `octopus-f429` (`octopus-v1.1-f429`, `octopus-v1.0-f429`) | STM32F429 | 8 МГц | 0x08008000 | есть (PD0/PD1, мост не подтверждён) | джампер BOOT0 (J75) + RESET | то же | нет |
| `octopus-max-ez` (`max-ez`, `octopus-maxez`) | STM32H723 | 25 МГц | 0x08020000 | есть (PD0/PD1, мост не подтверждён) | BOOT + RESET | `generic-bigtreetech-octopus-max-ez.cfg` из Klipper, репозиторий BTT | нет |
| `kraken` (`kraken-v1.0`, `kraken-v1.1`, `btt-kraken`) | STM32H723 | 25 МГц | 0x08020000 | **нет** (CAN PD0/PD1 есть на схеме, мост BTT не описывает; отключён в реестре) | BOOT + RESET | репозиторий BTT BIGTREETECH-Kraken | нет |
| `ldo-leviathan-v1.2` (`leviathan`, `leviathan-v1.2`, `ldo-leviathan`) | STM32F446 | 12 МГц | 0x08008000 | есть (PB5/PB6) | SW2 (BOOT) + SW1 (RESET) | LDO, Dr. Klipper, `generic-ldo-leviathan-v1.2.cfg` из Klipper | нет |
| `fly-super8-pro-h723` (`super8pro`, `super8-pro`, `flysuper8pro`) | STM32H723 | 25 МГц | 0x08020000 | есть (PB8/PB9) | джампер BOOT0 | документация Mellow | нет |
| `fly-super8` (`super8`, `flysuper8`) | STM32F407 | 8 МГц | 0x08008000 | есть (PB8/PB9) | джампер BOOT0 + RESET (по схеме) | документация Mellow | нет |
| `mks-monster8-v2` (`monster8`, `monster8-v2`) | STM32F407 | 8 МГц | 0x08008000 | есть (PB8/PB9) | BOOT0 (S2) + RESET (S1) | репозиторий MKS, отчёты сообщества | нет |

Katapult у всех плат пишется по DFU с 0x08000000. USB у всех плат — PA11/PA12.

> ⚠️ **Проверены на железе:** Octopus Pro v1.1 H723, Manta M8P v2.0 (CB1 и CB2), платы голов Fysetc H36 v1.3 / v2 и BTT EBB36/EBB42, ALPS; мост USB→CAN, прошивка голов «на столе» и по CAN, `--check-can`. **Остальные платы** (Octopus Pro F446 и F429, Manta M8P v1.0 / v1.1, Spider v3.0 H723 / F446, Spider v2.x, FLY-C8, а с версии 1.7 ещё Octopus F446 / F429 (не Pro), Octopus Max EZ, Kraken, LDO Leviathan v1.2, FLY Super8 / Super8 Pro, MKS Monster8 V2 и головы EBB36/42 v1.0, EBB Gen2, SHT36 v2) настроены по документации производителей и на железе не проверялись: сверьте плату, кварц и вход в DFU, первую прошивку делайте без нагревателей и моторов, о проблемах сообщайте разработчику. Подробности: [tested.md](tested.md).
- **M8P v1.0 и Spider v2.x без USB-CAN моста**: платы голов по CAN с ними не поддерживаются, установщик отказывает (нужен `--heads none`).
- **Octopus Pro F429** — только версия v1.0; у v1.1 другая распиновка и чип (H723), для неё используйте `octopus-pro-h723`.
- **FLY-C8**: DIP-переключатели 1 и 2 направляют внутренний USB к ARM-части платы, 3 и 4 — на разъём Type-C; прошивка идёт через DFU по USB.
- **Manta M8P**: MCU стоит на одной плате с CB1/CM4, USB к нему внутренний.
- **Octopus (не Pro) F446/F429** — те же пины, что у Octopus Pro v1.0 (используется пресет `octopus_pro_v1.0`); мост USB-CAN на PD0/PD1 по схеме, на железе не проверен. При автоматическом выборе по чипу F446/F429 остаётся Octopus Pro; Octopus без Pro выбирайте через `--main octopus-f446|octopus-f429`.
- **FLY Super8 Pro H723:** документация Mellow называет STM32H723 с кварцем 25 МГц, но в схеме репозитория Mellow-3D указан **STM32H743ZIT6 и кварц 8 МГц**. Сверьте маркировку чипа и кварц на своей плате: на H743/8 МГц эта сборка **не запустится** (нужны `MACH_STM32H743` и 8M, их в реестре нет), не прошивайте, пока не проверили.
- **BTT Kraken:** 8 **встроенных** TMC2160 (SPI, 24–60 В), драйвер заменить нельзя; TMC2240/5160 из гайда VOSTOK к ней неприменимы, ток ограничен внешними MOSFET/Rsense (v1.0 и v1.1 различаются). Режим моста USB-CAN BTT не описывает (в menuconfig USB или CAN), поэтому `CAN` в реестре пуст и платы голов по CAN с Kraken установщик не принимает (нужен `--heads none`). Пресета пинов нет.
- **LDO Leviathan v1.2:** драйверов меньше 7 (точное число не подтверждено): без плат голов моторов и двух экструдеров VOSTOK может не хватить, рассчитывайте на головы с платами (EBB). Плата поставляется без загрузчика; Klipper при работе моста обновляется только по USB, не по CAN.
- **MKS Monster8 V2:** katapult с загрузчиком 32KiB взят по отчёту сообщества (мост работал с 32KiB и не поднимал `can0` с 48KiB), документации MKS на это нет: при несовпадении смещения `can0` не поднимется; стоковый загрузчик MKS (48KiB) заменяется, откат — прошивкой стока с SD-карты. Перемычка J2 должна стоять на CAN; проверьте маркировку чипа (F446 или F407).
- **Super8 (F407), Max EZ, Octopus F446/F429:** вход в DFU и мост USB-CAN взяты из документации и схем, на железе не проверены.
- **Отказано в реестре:** MKS SKIPR (встроенный хост RK3328, MCU связан с ним по UART, USB-прошивка не штатна, мост не подтверждён, драйверов не больше 6) и Fysetc Spider King407 (данных мало, второго источника нет).
- **Пины и конфигуратор.** Стокового `electronics_*.cfg` для новых плат нет: конфигуратор генерирует шаблон без пинов (`--config-source generate`) или берёт ваш файл из `user_configs/` (`--config-source user`); пресеты пинов есть у Octopus Pro (H723 — по гайду; F446/F429 — `octopus_pro_v1.0`) и Manta M8P v1.0 / v1.1 / v2.0 (`templates/boards/main/`, не проверены на железе); у Spider v2.x / v3.0, FLY-C8 и плат версии 1.7 (кроме Octopus F446/F429) пресета нет (см. [CONFIGURATOR.md](../CONFIGURATOR.md)).

Как добавить свою плату: [build-configs.md](build-configs.md#как-добавить-плату).

## Платы голов

Платы голов тоже лежат в реестре (`ROLE=head`), `--heads` принимает `none` и id или алиас любой из них (список: `./install_vostok.sh --list-boards`). Значения, которые были раньше (`v1.3`, `v2`, `ebb42`; `--h36` — то же), работают как прежде и выводят то же самое. Выбрать можно только голову, для которой есть шаблон электроники `templates/boards/<TEMPLATE>.cfg` (поле `TEMPLATE` платы): пины экструдера, термистора и концевиков конфигуратор берёт оттуда и **не выдумывает**. Для остальных голов установщик отказывает: `--heads <плата>: для платы … нет шаблона электроники`.

| id (алиасы) | Чип | Кварц | CAN | `--heads` | Проверено на железе |
|---|---|---|---|---|---|
| `h36-v1.3` (`v1.3`) | STM32G0B1 | 12 МГц | PB0/PB1 | **да**, `v1.3` | **да** |
| `h36-v2` (`v2`) | STM32G431 | 12 МГц | PB0/PB1 | **да**, `v2` | **да** |
| `ebb42` (`ebb36`) | STM32G0B1 | 8 МГц | PB0/PB1 | **да**, `ebb42` (`ebb36` — тот же выбор) | **да** (EBB36) |
| `ebb36-v1.0` (`ebb42-v1.0`) | STM32F072 | 8 МГц | PB8/PB9 | нет: нет шаблона электроники (пины v1.0 другие, чем у v1.1/v1.2) | нет |
| `ebb-gen2` (`ebb36-gen2`, `ebb42-gen2`) | STM32G0B1 | 8 МГц | PB12/PB13 | нет: нет шаблона электроники (пины Gen2 не подтверждены) | нет |
| `sht36-v2` (`sht42`, `sht36v2`) | STM32F072 | 8 МГц | PB8/PB9 | нет: нет шаблона электроники | нет |

Для голов без шаблона реестр даёт конфиги сборки (`tools/gen_configs.py --board <id>`), но пока не сам выбор в установщике. Чтобы включить такую голову: добавить `templates/boards/<имя>.cfg` с блоками `@@T0@@`/`@@T1@@` (пины экструдеров, термисторов, концевиков и зонда по документации платы, сверенные со схемой) и вписать имя в поле `TEMPLATE` её `.board`; код менять не нужно.

> ⚠️ **Предупреждения по головам.**
> - **`ebb36` — неоднозначный алиас:** он указывает на `ebb42` (EBB36/EBB42 **v1.1 и v1.2**, G0B1). Плата EBB36/EBB42 **v1.0** (F072) — это `ebb36-v1.0`, **Gen2** — `ebb-gen2`: у них другой чип или пины CAN, прошивки не взаимозаменяемы.
> - **FLY SHT36 v2:** бывает три варианта МК — STM32F072, APM32F072 (после 2022-10-28) и GD32F103 (раньше). Конфиг сделан под F072/APM32F072; если плата куплена до 2022-10-28 (GD32F103), сборку не используйте. APM32F072 в DFU виден как `314b:0106`, а установщик ищет `0483:df11`, поэтому по DFU через установщик она не прошьётся, только по CAN в заводской Katapult.
> - **Не поддержаны: FLY SHT36 v3 / SHT36 Max v3 и MKS THR36 / THR42** — это RP2040. Нужна отдельная доработка кода: семейство `rp2040` в `vostok/boards.py` и `tools/gen_configs.py` (Kconfig `MACH_RP2040`, `RPXXXX_CANBUS`, `RPXXXX_CANBUS_GPIO_RX/TX`, смещение 16 KiB), обнаружение режима BOOTSEL (`2e8a:0003`) вместо DFU `0483:df11` в `vostok/hardware.py`, прошивка UF2 (диск `RPI-RP2` или `picotool`) вместо `dfu-util` в `vostok/flashing.py`, другой способ получить UID для `canbus_uuid` (у RP2040 нет адреса UID в DFU, как у STM32). Подробности по платам (смещение 16 KiB, CAN GPIO 1/0 у SHT36 v3) в истории коммитов ветки.

## Распиновка

Картинки распиновки плат лежат в [`pinouts/`](../pinouts/README.md) (таблица «плата -> файлы», источники и лицензии — в `pinouts/SOURCES.tsv`). Установщик печатает путь и веб-ссылку на картинку вашей платы в плане установки (для непроверенной платы), при входе в DFU, в предупреждениях конфигуратора (пустые пины ЗАПОЛНИТЕ, пересечения пинов) и в итоге. Картинки задаёт поле `PINOUT` в `boards/<id>.board`; если оно пусто (ALPS и Spider v3.0 H723), показывается `DOC`. У FLY Super8 Pro и SHT36 v2 / SHT42 вместо pinout лежат принципиальные схемы (листа pinout у Mellow нет). Адрес можно заменить переменной `VOSTOK_PINOUT_URL`.

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
