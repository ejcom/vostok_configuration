# Что проверено

🇷🇺 Русский | [🇬🇧 English](tested.en.md)

[← К оглавлению](../README.md)

На реальном принтере (Orange Pi, Debian 11, Octopus Pro H723 и два ALPS, без плат голов) проверены: чистая установка ПО через KIAUH CLI (Klipper-форк, Moonraker, Fluidd, katapult), определение плат, определение чипа в DFU по Option Bytes (STM32F0 и STM32H7), сборка и прошивка USB-вариантов (Octopus Pro H723 по USB, ALPS на STM32F072) через katapult, прошивка Klipper на Octopus Pro H723 по DFU без katapult, кнопка в Fluidd, сборка всех конфигов, запись `printer.cfg`, генерация конфига электроники для H723 без плат голов, подключение модуля нагревателя камеры и поиск пересечений пинов.

Проверено только в `--dry-run` и на копиях каталога конфигурации: генерация конфига электроники для остальных сочетаний плат голов и драйверов (разбор результата как конфига Klipper) и дописывание `[mcu]`.

**Не проверено на железе**: прошивка плат голов «на столе» (katapult и Klipper одним сеансом DFU без 24 В и CAN), чтение UID чипа по DFU и вычисление `canbus_uuid` (алгоритм сверен с кодом прошивки на случайных UID, но не с реальной шиной), `install_vostok.sh --check-can` на живой шине, прошивка katapult и Klipper одним сеансом DFU, мост USB→CAN, платы голов H36 и EBB42, Octopus Pro F446, определение этих плат (F4, STM32G0/G4) в DFU, а также пины из таблицы разъёмов Octopus Pro для голов без плат голов на H723 (взята из конфигов F446): конфиг по ней генерируется, но с реальной проводкой пины не сверены. Если что-то не сходится с вашей платой или нашли баг — создайте issue с логом (`~/printer_data/logs/vostok_install.log`) или спросите в Telegram-канале [K_3_D](http://t.me/K_3_D), упомянув Dmitry Kostenko.

**Платы, не проверенные на железе:** главные — Octopus Pro F446, Octopus Pro v1.0 F429, Manta M8P v1.0 / v1.1 / v2.0, Spider v3.0 H723, Spider v3.0 F446, Spider v2.x, FLY-C8; платы голов — Fysetc H36 v1.3 и v2, BTT EBB42. Проверены только Octopus Pro v1.1 H723 и ALPS.

**Новые платы реестра** (Octopus Pro F429, Manta M8P v1.0/v1.1/v2.0, Spider v3.0 H723/F446, Spider v2.x, FLY-C8) на железе не проверялись вовсе. Проверено только на хосте: сборка их конфигов Klipper и katapult (`tools/gen_configs.sh --check --build`), `--dry-run` и подбор параметров по документации производителей. Не проверено на железе:

- вход в DFU (кнопки BOOT/BT0, перемычка у Spider v2.x, `fly-flash` и DIP-переключатели FLY-C8) и вся прошивка katapult и Klipper;
- определение семейства по Option Bytes для F4 и G0/G4 и неразличимость плат на одном чипе (H723: Octopus, Manta v2.0, Spider v3.0);
- пины CAN моста (Manta M8P v1.1 PD12/PD13, FLY-C8 PB8/PB9; у Spider v3.0 F446 PD0/PD1 документацией не подтверждены);
- смещения приложения katapult, двойной RESET; `mass-erase` стирает штатный загрузчик производителя;
- чтение UID и `canbus_uuid` на этих платах;
- допущение, что «Fly C6» — это FLY-C8.

Подробности и таблица плат: [hardware.md](hardware.md#главные-платы).
