# Supported boards and directory contents

[🇷🇺 Русский](hardware.md) | 🇬🇧 English

[← Contents](../README.en.md)

## Supported hardware

| Part | Options |
|---|---|
| Mainboard | BTT Octopus Pro v1.1 **H723** (as in the guide) or Octopus Pro **F446**; also the boards from the `boards/` registry (table below) |
| Toolhead boards (CAN) | Fysetc **H36** v1.3 / v2 or BTT **EBB42/EBB36**; or none |
| ALPS sensors (USB) | 0, 1 or 2 |

- **With toolhead boards** the Octopus is flashed as a **USB→CAN bridge**, as in the guide, and the toolhead boards run over CAN (`can0`, 1 Mbit). They can be flashed in two ways:
  - **"on the bench"** (the default): katapult and Klipper together over DFU via USB, without 24 V or CAN; `canbus_uuid` is computed from the chip UID and verified after assembly with `install_vostok.sh --check-can`;
  - **in an assembled printer**: katapult over DFU, Klipper over CAN (24 V and CAN cables required).
- **Without CAN toolhead boards** (with a passive Fly miniAB toolhead board wired directly to the Octopus) the Octopus works over plain USB.
- ALPS (STM32F072) are flashed over USB: katapult via DFU, then Klipper.

## Mainboards

Board parameters live in the `boards/*.board` registry (`./install_vostok.sh --list-boards` prints it). The board is selected with `--main <id|alias>` or detected from the connected hardware; if several boards share the detected chip, the installer asks.

| id (aliases) | Chip | Crystal | Klipper starts at | USB-CAN bridge (CAN pins) | Entering DFU | Data source | Verified on hardware |
|---|---|---|---|---|---|---|---|
| `octopus-pro-h723` (`h723`) | STM32H723 | 25 MHz | 0x08020000 | yes (PD0/PD1) | BOOT0 jumper + RESET | k3d guide | **yes** |
| `octopus-pro-f446` (`f446`) | STM32F446 | 12 MHz | 0x08008000 | yes (PD0/PD1) | BOOT0 jumper + RESET | board schematic | no |
| `octopus-pro-f429` (`f429`) | STM32F429 | 8 MHz | 0x08008000 | yes (PD0/PD1) | BOOT0 jumper + RESET | Klipper `generic-bigtreetech-octopus-pro-v1.0.cfg` | no |
| `manta-m8p-v1.0` (`m8p-v1.0`) | STM32G0B1 | 8 MHz | 0x08002000 | **no** | BOOT + RESET | BTT, Manta-M8P repository | no |
| `manta-m8p-v1.1` (`m8p-v1.1`) | STM32G0B1 | 8 MHz | 0x08002000 | yes (PD12/PD13) | BOOT + RESET | BTT, Manta-M8P repository; `generic-bigtreetech-manta-m8p-v1.1.cfg` | no |
| `manta-m8p-v2.0` (`m8p-v2.0`) | STM32H723 | 25 MHz | 0x08020000 | yes (PD0/PD1) | BOOT + RESET | BTT, `generic-bigtreetech-manta-m8p-V2_0.cfg` | **yes** |
| `spider-v3-h723` (`spider-h723`) | STM32H723 | 25 MHz | 0x08020000 | yes (PD0/PD1) | BT0 + RST buttons | docs.fysetc.com | no |
| `spider-v3-f446` (`spider-f446`) | STM32F446 | 12 MHz | 0x08008000 | yes (PD0/PD1, not confirmed by the documentation) | BT0 + RST buttons | docs.fysetc.com | no |
| `spider-v2-f446` (`spider-v2`, `spider-v2.x`) | STM32F446 | 12 MHz | 0x08008000 | **no** | BT0-3.3V jumper + RESET | Klipper `generic-fysetc-spider.cfg`, Voron docs | no |
| `fly-c8` (`flyc8`, `fly-c6`, `flyc6`) | STM32F407 | 8 MHz | 0x08008000 | yes (PB8/PB9) | `sudo fly-flash -d c8 -u` or BOOT + RESET | Mellow-3D/klipper-docs, `docs/board/fly_C8` | no |

Katapult is always written over DFU at 0x08000000 on every board. USB is PA11/PA12 on all boards.

> ⚠️ **Verified on hardware:** Octopus Pro v1.1 H723, Manta M8P v2.0 (CB1 and CB2), toolhead boards Fysetc H36 v1.3 / v2 and BTT EBB36/EBB42, ALPS; the USB→CAN bridge, flashing the toolheads "on the bench" and over CAN, `--check-can`. **The other boards** (Octopus Pro F446 and F429, Manta M8P v1.0 / v1.1, Spider v3.0 H723 / F446, Spider v2.x, FLY-C8) are set up from the manufacturers' documentation and have not been tried on hardware: check the board, crystal and DFU procedure, do the first flash with no heaters or motors connected, and report problems to the developer. Details: [tested.en.md](tested.en.md).
- **M8P v1.0 and Spider v2.x have no USB-CAN bridge**: CAN toolhead boards are not supported with them and the installer refuses (use `--heads none`).
- **Octopus Pro F429** is v1.0 only; v1.1 has a different pinout and chip (H723), use `octopus-pro-h723` for it.
- **FLY-C8**: DIP switches 1 and 2 route the internal USB to the ARM part of the board, 3 and 4 route it to the Type-C connector; flashing is done over DFU via USB. Mellow's documentation has no "Fly C6" board, that name is taken to mean the FLY-C8 (aliases `fly-c6`, `flyc6`).
- **Manta M8P**: the MCU sits on the same board as the CB1/CM4, USB to it is internal.
- **Pins and the configurator.** There is no stock `electronics_*.cfg` for the new boards: the configurator generates a template without pins (`--config-source generate`) or takes your file from `user_configs/` (`--config-source user`); pin presets exist for the Octopus Pro (H723 per the guide; F446/F429 use `octopus_pro_v1.0`) and Manta M8P v1.0 / v1.1 / v2.0 (`templates/boards/main/`, not verified on hardware); Spider v2.x / v3.0 and FLY-C8 have no preset (see [CONFIGURATOR.en.md](../CONFIGURATOR.en.md)).

How to add your own board: [build-configs.en.md](build-configs.en.md#how-to-add-a-board).

## Contents of `installer/`

| Path | What it is |
|---|---|
| `install_vostok.sh` | first-time installation (all stages) |
| `configure_vostok.sh` | printer config setup separate from the installation, see [CONFIGURATOR.en.md](../CONFIGURATOR.en.md) |
| `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `mcu-update.service.in` | Klipper and firmware update, the Fluidd button |
| `install_fluidd_theme.sh`, `fluidd-theme/` | K3D VOSTOK theme for Fluidd: logo, `custom.css`, preset |
| `install_klipperscreen_theme.sh`, `klipperscreen-theme/` | K3D VOSTOK theme for KlipperScreen: `style.css`, `style.conf`, K3D mark, Tektur font |
| `vostok/` | the Python package with all installer logic (stdlib only, Python 3.8+); the `*.sh` files in the root are thin wrappers over `python3 -m vostok <command>` |
| `templates/` | blank electronics config without boards and drivers (`electronics_blank.cfg`), board presets (`boards/`) and driver presets (`drivers/`) |
| `tools/` | `gen_electronics.py` (electronics config generator; a wrapper over `vostok/electronics.py`), `gen_configs.py` (firmware build configs from the `boards/` registry) |
| `boards/` | board registry: one `<id>.board` file per board (build parameters, labels, DFU hints, whether verified on hardware) |
| `tests/` | unit tests (`python3 -m unittest discover tests`) and golden output references (`tests/run_golden.sh`) |
| `configs/` | Klipper and katapult build configs |
| `docs/` | this documentation split by topic |
| `VERSION`, `CHANGELOG.en.md` | installer version (`-V`/`--version` in every script) and the [changelog](../CHANGELOG.en.md) |
