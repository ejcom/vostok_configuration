# What has been tested

[🇷🇺 Русский](tested.md) | 🇬🇧 English

[← Contents](../README.en.md)

Tested on a real printer (Orange Pi, Debian 11, Octopus Pro H723 and two ALPS, no toolhead boards): a clean software installation through the KIAUH CLI (Klipper fork, Moonraker, Fluidd, katapult), board detection, chip detection in DFU by Option Bytes (STM32F0 and STM32H7), build and flashing of the USB variants (Octopus Pro H723 over USB, ALPS on STM32F072) through katapult, flashing Klipper to the Octopus Pro H723 over DFU without katapult, the Fluidd button, building all configs, writing `printer.cfg`, generating the electronics config for the H723 without toolhead boards, enabling the chamber heater module and the pin-conflict check.

Users have verified on hardware the **Manta M8P v2.0** (with CB1 and CB2), **Fysetc H36 v1.3 and v2** and **BTT EBB36** (same firmware as the EBB42, the `ebb42` registry entry): the USB→CAN bridge on the M8P v2.0, flashing toolhead boards "on the bench" (katapult and Klipper in one DFU session) and over CAN, computing `canbus_uuid` from the chip UID, and `install_vostok.sh --check-can` on a live bus.

Tested only in `--dry-run` and on copies of the config directory: generating the electronics config for the other combinations of toolhead boards and drivers (parsing the result as a Klipper config) and adding `[mcu]` sections.

## Not tested on hardware

Registry boards: Octopus Pro F446 and F429, Manta M8P v1.0 / v1.1, Spider v3.0 H723 / F446, Spider v2.x, FLY-C8, and those added in 1.7: the non-Pro Octopus F446 / F429, Octopus Max EZ, Kraken, LDO Leviathan v1.2, FLY Super8 / Super8 Pro H723, MKS Monster8 V2 and the toolhead boards BTT EBB36/42 v1.0, BTT EBB Gen2, FLY SHT36 v2 / SHT42 (these heads cannot be selected with `--heads` yet, they have no electronics template). For them only the build of the Klipper and katapult configs (`tools/gen_configs.py --check --build`) and `--dry-run` were checked; the parameters come from the manufacturers' documentation. Specifically not verified:

- entering DFU (BOOT/BT0 buttons, the Spider v2.x jumper, `fly-flash` and the FLY-C8 DIP switches) and the whole katapult and Klipper flashing;
- Option Bytes family detection for F4; boards that share a chip (H723: Octopus, Manta v2.0, Spider v3.0) cannot be told apart over DFU, only your choice distinguishes them;
- the bridge CAN pins: Manta M8P v1.1 PD12/PD13, FLY-C8 PB8/PB9; for the Spider v3.0 F446 PD0/PD1 the documentation does not confirm them;
- katapult application offsets and double reset; writing katapult over DFU with `mass-erase` wipes the whole flash, including the manufacturer's bootloader (it can only be restored from its `.bin` through the STM32 ROM bootloader; DFU is always available);
- the assumption that "Fly C6" means the FLY-C8;
- 1.7 boards: the Super8 Pro chip and crystal (H743 and 8 MHz on the schematic, H723 and 25 MHz in the documentation), the 32KiB bootloader offset of the Monster8 V2 (from a community report), the Kraken having no bridge, the Leviathan driver count, the SHT36 v2 chip variant (F072, APM32F072 or GD32F103), and the DFU procedure and USB-CAN bridge of the Octopus F446/F429 and Max EZ;
- the configurator's pin presets for the Manta M8P and Octopus Pro F446/F429, and the Octopus Pro connector table pins for heads without toolhead boards on the H723 (taken from the F446 configs): the config is generated from them, but the pins have not been checked against real wiring.

If something does not match your board or you found a bug, open an issue with the log (`~/printer_data/logs/vostok_install.log`) or ask in the Telegram channel [K_3_D](http://t.me/K_3_D), mentioning Dmitry Kostenko.

Board table: [hardware.en.md](hardware.en.md#mainboards).
