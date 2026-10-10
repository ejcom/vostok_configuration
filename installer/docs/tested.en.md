# What has been tested

[🇷🇺 Русский](tested.md) | 🇬🇧 English

[← Contents](../README.en.md)

Tested on a real printer (Orange Pi, Debian 11, Octopus Pro H723 and two ALPS, no toolhead boards): a clean software installation through the KIAUH CLI (Klipper fork, Moonraker, Fluidd, katapult), board detection, chip detection in DFU by Option Bytes (STM32F0 and STM32H7), build and flashing of the USB variants (Octopus Pro H723 over USB, ALPS on STM32F072) through katapult, flashing Klipper to the Octopus Pro H723 over DFU without katapult, the Fluidd button, building all configs, writing `printer.cfg`, generating the electronics config for the H723 without toolhead boards, enabling the chamber heater module and the pin-conflict check.

Tested only in `--dry-run` and on copies of the config directory: generating the electronics config for the other combinations of toolhead boards and drivers (parsing the result as a Klipper config) and adding `[mcu]` sections.

**Not tested on hardware**: flashing katapult and Klipper together in one DFU session, the USB→CAN bridge, H36 and EBB42 toolhead boards, the Octopus Pro F446, detecting these boards (F4, STM32G0/G4) in DFU, and the pins from the Octopus Pro socket table for heads without toolhead boards on the H723 (taken from F446 configs): the config is generated from it, but the pins have not been checked against real wiring. If something does not match your board or you found a bug, open an issue with the log (`~/printer_data/logs/vostok_install.log`) or ask in the Telegram channel [K_3_D](http://t.me/K_3_D), mentioning Dmitry Kostenko.
