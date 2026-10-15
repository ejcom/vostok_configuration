# Параметры сборки прошивок

🇷🇺 Русский | [🇬🇧 English](build-configs.en.md)

[← К оглавлению](../README.md)

Лежат в `configs/` (Klipper) и `configs/katapult/` (katapult). Воспроизвести: `tools/gen_configs.sh --force` (строится по реестру плат `boards/*.board`). Значения взяты из гайда; для Octopus Pro F446 (гайд её не описывает: 12 МГц, загрузчик 32KiB, USB PA11/PA12) и EBB42 (STM32G0B1, 8 МГц, CAN PB0/PB1) — по документации и схемам плат. Если у вашей платы другой кварц или смещение загрузчика, поправьте конфиг: `make menuconfig KCONFIG_CONFIG=…` в каталоге Klipper. Соответствие «серийный номер / UUID → конфиг сборки» установщик пишет в `devices.tsv` (его читает кнопка).

Имена файлов задаёт поле `CFG` платы: Klipper USB — `configs/<CFG>.config`, мост USB→CAN — `configs/<CFG>-canbridge.config`, голова по CAN — `configs/<CFG>-can.config`, katapult — `configs/katapult/<CFG>.config` (у голов `<CFG>-can.config`). У прежних плат старые имена, где `CFG` — чип (`stm32h723xx`, `stm32f446xx`, `stm32g0b1xx`, `stm32g431xx`, `stm32g0b1xx-ebb42`, `stm32f072xb`), чтобы не ломать уже записанные `devices.tsv`; у новых плат `CFG` равен id (`configs/fly-c8.config`, `configs/katapult/spider-v3-h723.config` и т. д.). `devices.tsv` хранит имя конфига сборки, `update_klipper_mcu.sh` ищет конфиг USB-MCU сначала в `devices.tsv` (по серийному номеру), затем `configs/<serial>.config`, затем `configs/<чип>.config`.

## Как добавить плату

1. Создайте `boards/<id>.board` (проще всего скопировать похожую плату). Формат: строки `KEY="значение"` без кода, комментарии `#`. Поля:

   | Поле | Значение |
   |---|---|
   | `LABEL` | название для вывода |
   | `ROLE` | `main`, `head` или `alps` |
   | `CHIP` | чип в Klipper, например `stm32h723xx` |
   | `FAMILY` | `f0`, `f4`, `h7` или `g` |
   | `MACH` | название чипа в Kconfig, например `STM32H723` |
   | `CLOCK` | кварц: `8M`, `12M` или `25M` |
   | `APP_OFFSET` | начало Klipper после загрузчика: `2000`, `8000` или `20000` |
   | `USB` | `PA11_PA12` или пусто |
   | `CAN` | пины CAN (например `PD0_PD1`) или пусто, если моста/CAN нет |
   | `CAN_KIND` | `cmenu` (мост на главной плате), `mmenu` или `direct` (головы); обязателен, если задан `CAN` |
   | `INITIAL_PINS`, `BRIDGE_INITIAL_PINS`, `KATAPULT_INITIAL_PINS` | пины, которые держать выключенными при старте (Klipper USB, мост, katapult) |
   | `KATAPULT_LED`, `KATAPULT_DOUBLE_RESET` | светодиод katapult; `y` — запуск двойным RESET |
   | `CFG` | основа имён файлов (для новых плат равна id) |
   | `ALIASES` | алиасы для `--main` через пробел |
   | `DFU_HINT`, `DFU_HOW` | текст подсказки о входе в DFU; `jumper` (джампер) или `button` (кнопки) |
   | `ELEC_PATTERN` | часть имени `electronics_*.cfg`, по которой файл относится к плате (пусто — стокового конфига нет) |
   | `TEMPLATE` | `octopus_pro` (пресеты пинов Octopus) или пусто |
   | `HEAD_NAMES` | имена секций голов (для `ROLE=head`) |
   | `VERIFIED` | `yes` — проверена на железе, `no` — только по документации |
   | `DOC`, `NOTE` | источник данных и примечание |

   Плата без моста USB→CAN (пустой `CAN`) не годится для плат голов по CAN: установщик откажет.
2. Создайте конфиги сборки: `tools/gen_configs.sh --board <id>` (добавьте `--force`, чтобы перезаписать существующие). Скрипт строит Kconfig-строки из полей и проверяет, что каждая сохранилась после `olddefconfig`.
3. Проверьте: `tools/gen_configs.sh --check` — сгенерировать во временный каталог и сравнить с `configs/` по значимым ключам (код 1 при расхождении).
4. Соберите: `tools/gen_configs.sh --build` — собрать каждый конфиг во временном каталоге; для katapult проверяется, что `katapult.bin` меньше смещения приложения.
5. Проверьте плату: `./install_vostok.sh --list-boards`, `./install_vostok.sh --dry-run --main <id>`. Пока плата не прошита на железе, оставьте `VERIFIED="no"`.

Список плат реестра и их параметры: [hardware.md](hardware.md#главные-платы).
