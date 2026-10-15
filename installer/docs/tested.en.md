# What has been tested

[🇷🇺 Русский](tested.md) | 🇬🇧 English

[← Contents](../README.en.md)

Tested on a real printer (Orange Pi, Debian 11, Octopus Pro H723 and two ALPS, no toolhead boards): a clean software installation through the KIAUH CLI (Klipper fork, Moonraker, Fluidd, katapult), board detection, chip detection in DFU by Option Bytes (STM32F0 and STM32H7), build and flashing of the USB variants (Octopus Pro H723 over USB, ALPS on STM32F072) through katapult, flashing Klipper to the Octopus Pro H723 over DFU without katapult, the Fluidd button, building all configs, writing `printer.cfg`, generating the electronics config for the H723 without toolhead boards, enabling the chamber heater module and the pin-conflict check.

Tested only in `--dry-run` and on copies of the config directory: generating the electronics config for the other combinations of toolhead boards and drivers (parsing the result as a Klipper config) and adding `[mcu]` sections.

**Not tested on hardware**: flashing toolhead boards "on the bench" (katapult and Klipper in one DFU session without 24 V or CAN), reading the chip UID over DFU and computing `canbus_uuid` (the algorithm was checked against the firmware code on random UIDs, but not against a real bus), `install_vostok.sh --check-can` on a live bus, flashing katapult and Klipper together in one DFU session, the USB→CAN bridge, H36 and EBB42 toolhead boards, the Octopus Pro F446, detecting these boards (F4, STM32G0/G4) in DFU, and the pins from the Octopus Pro socket table for heads without toolhead boards on the H723 (taken from F446 configs): the config is generated from it, but the pins have not been checked against real wiring. If something does not match your board or you found a bug, open an issue with the log (`~/printer_data/logs/vostok_install.log`) or ask in the Telegram channel [K_3_D](http://t.me/K_3_D), mentioning Dmitry Kostenko.

**Boards not verified on hardware:** mainboards: Octopus Pro F446, Octopus Pro v1.0 F429, Manta M8P v1.0 / v1.1 / v2.0, Spider v3.0 H723, Spider v3.0 F446, Spider v2.x, FLY-C8; toolhead boards: Fysetc H36 v1.3 and v2, BTT EBB42. Only the Octopus Pro v1.1 H723 and ALPS are verified.

**The new registry boards** (Octopus Pro F429, Manta M8P v1.0/v1.1/v2.0, Spider v3.0 H723/F446, Spider v2.x, FLY-C8) have not been tested on hardware at all. Only host-side checks were done: building their Klipper and katapult configs (`tools/gen_configs.sh --check --build`), `--dry-run`, and choosing parameters from the manufacturers' documentation. Not tested on hardware:

- entering DFU (BOOT/BT0 buttons, the Spider v2.x jumper, `fly-flash` and the FLY-C8 DIP switches) and the whole katapult and Klipper flashing;
- Option Bytes family detection for F4 and G0/G4, and telling apart boards that share a chip (H723: Octopus, Manta v2.0, Spider v3.0);
- the bridge CAN pins (Manta M8P v1.1 PD12/PD13, FLY-C8 PB8/PB9; for the Spider v3.0 F446 PD0/PD1 the documentation does not confirm them);
- katapult application offsets, double reset; `mass-erase` wipes the manufacturer's bootloader;
- reading the UID and `canbus_uuid` on these boards;
- the assumption that "Fly C6" means the FLY-C8.

Details and the board table: [hardware.en.md](hardware.en.md#mainboards).
