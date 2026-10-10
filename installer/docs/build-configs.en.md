# Firmware build settings

[🇷🇺 Русский](build-configs.md) | 🇬🇧 English

[← Contents](../README.en.md)

They live in `configs/` (Klipper) and `configs/katapult/` (katapult). Regenerate with `tools/gen_configs.sh --force`. Values come from the guide; for the Octopus Pro F446 (not covered by the guide: 12 MHz, 32KiB bootloader, USB PA11/PA12) and the EBB42 (STM32G0B1, 8 MHz, CAN PB0/PB1) they come from documentation and board schematics. If your board has a different crystal or bootloader offset, edit the config: `make menuconfig KCONFIG_CONFIG=…` in the Klipper directory. The installer writes the "serial number / UUID → build config" map to `devices.tsv` (the button reads it).
