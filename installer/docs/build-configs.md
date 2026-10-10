# Параметры сборки прошивок

🇷🇺 Русский | [🇬🇧 English](build-configs.en.md)

[← К оглавлению](../README.md)

Лежат в `configs/` (Klipper) и `configs/katapult/` (katapult). Воспроизвести: `tools/gen_configs.sh --force`. Значения взяты из гайда; для Octopus Pro F446 (гайд её не описывает: 12 МГц, загрузчик 32KiB, USB PA11/PA12) и EBB42 (STM32G0B1, 8 МГц, CAN PB0/PB1) — по документации и схемам плат. Если у вашей платы другой кварц или смещение загрузчика, поправьте конфиг: `make menuconfig KCONFIG_CONFIG=…` в каталоге Klipper. Соответствие «серийный номер / UUID → конфиг сборки» установщик пишет в `devices.tsv` (его читает кнопка).
