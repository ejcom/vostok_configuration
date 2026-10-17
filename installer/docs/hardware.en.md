# Supported boards and directory contents

[🇷🇺 Русский](hardware.md) | 🇬🇧 English

[← Contents](../README.en.md)

## Supported hardware

| Part | Options |
|---|---|
| Mainboard | BTT Octopus Pro v1.1 **H723** (as in the guide) or Octopus Pro **F446**; also the boards from the `boards/` registry (table below) |
| Toolhead boards (CAN) | Fysetc **H36** v1.3 / v2 or BTT **EBB42/EBB36** v1.1/v1.2; other registry heads are build-only for now (see "Toolhead boards" below); or none |
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
| `fly-c8` (`flyc8`) | STM32F407 | 8 MHz | 0x08008000 | yes (PB8/PB9) | `sudo fly-flash -d c8 -u` or BOOT + RESET | Mellow-3D/klipper-docs, `docs/board/fly_C8` | no |
| `octopus-f446` (`octopus-v1.1-f446`, `octopus-v1.0-f446`) | STM32F446 | 12 MHz | 0x08008000 | yes (PD0/PD1, bridge not confirmed) | BOOT0 jumper (J75) + RESET | Klipper `generic-bigtreetech-octopus-v1.1.cfg`, BTT repository | no |
| `octopus-f429` (`octopus-v1.1-f429`, `octopus-v1.0-f429`) | STM32F429 | 8 MHz | 0x08008000 | yes (PD0/PD1, bridge not confirmed) | BOOT0 jumper (J75) + RESET | same | no |
| `octopus-max-ez` (`max-ez`, `octopus-maxez`) | STM32H723 | 25 MHz | 0x08020000 | yes (PD0/PD1, bridge not confirmed) | BOOT + RESET | Klipper `generic-bigtreetech-octopus-max-ez.cfg`, BTT repository | no |
| `kraken` (`kraken-v1.0`, `kraken-v1.1`, `btt-kraken`) | STM32H723 | 25 MHz | 0x08020000 | **no** (CAN PD0/PD1 is on the schematic, BTT does not describe a bridge; disabled in the registry) | BOOT + RESET | BTT BIGTREETECH-Kraken repository | no |
| `ldo-leviathan-v1.2` (`leviathan`, `leviathan-v1.2`, `ldo-leviathan`) | STM32F446 | 12 MHz | 0x08008000 | yes (PB5/PB6) | SW2 (BOOT) + SW1 (RESET) | LDO, Dr. Klipper, Klipper `generic-ldo-leviathan-v1.2.cfg` | no |
| `fly-super8-pro-h723` (`super8pro`, `super8-pro`, `flysuper8pro`) | STM32H723 | 25 MHz | 0x08020000 | yes (PB8/PB9) | BOOT0 jumper | Mellow documentation | no |
| `fly-super8` (`super8`, `flysuper8`) | STM32F407 | 8 MHz | 0x08008000 | yes (PB8/PB9) | BOOT0 jumper + RESET (per the schematic) | Mellow documentation | no |
| `mks-monster8-v2` (`monster8`, `monster8-v2`) | STM32F407 | 8 MHz | 0x08008000 | yes (PB8/PB9) | BOOT0 (S2) + RESET (S1) | MKS repository, community reports | no |

Katapult is always written over DFU at 0x08000000 on every board. USB is PA11/PA12 on all boards.

> ⚠️ **Verified on hardware:** Octopus Pro v1.1 H723, Manta M8P v2.0 (CB1 and CB2), toolhead boards Fysetc H36 v1.3 / v2 and BTT EBB36/EBB42, ALPS; the USB→CAN bridge, flashing the toolheads "on the bench" and over CAN, `--check-can`. **The other boards** (Octopus Pro F446 and F429, Manta M8P v1.0 / v1.1, Spider v3.0 H723 / F446, Spider v2.x, FLY-C8, and since 1.7 also the non-Pro Octopus F446 / F429, Octopus Max EZ, Kraken, LDO Leviathan v1.2, FLY Super8 / Super8 Pro, MKS Monster8 V2 and the EBB36/42 v1.0, EBB Gen2 and SHT36 v2 toolhead boards) are set up from the manufacturers' documentation and have not been tried on hardware: check the board, crystal and DFU procedure, do the first flash with no heaters or motors connected, and report problems to the developer. Details: [tested.en.md](tested.en.md).
- **M8P v1.0 and Spider v2.x have no USB-CAN bridge**: CAN toolhead boards are not supported with them and the installer refuses (use `--heads none`).
- **Octopus Pro F429** is v1.0 only; v1.1 has a different pinout and chip (H723), use `octopus-pro-h723` for it.
- **FLY-C8**: DIP switches 1 and 2 route the internal USB to the ARM part of the board, 3 and 4 route it to the Type-C connector; flashing is done over DFU via USB.
- **Manta M8P**: the MCU sits on the same board as the CB1/CM4, USB to it is internal.
- **Octopus (non-Pro) F446/F429** use the same pins as the Octopus Pro v1.0 (the `octopus_pro_v1.0` preset); the USB-CAN bridge on PD0/PD1 comes from the schematic and has not been tried on hardware. When the board is chosen automatically by chip, F446/F429 still default to the Octopus Pro; select the non-Pro with `--main octopus-f446|octopus-f429`.
- **FLY Super8 Pro H723:** Mellow's documentation says STM32H723 with a 25 MHz crystal, but the schematic in the Mellow-3D repository shows an **STM32H743ZIT6 and an 8 MHz crystal**. Check the chip marking and crystal on your board: on an H743/8 MHz board this build **will not start** (it needs `MACH_STM32H743` and 8M, which the registry does not have); do not flash until you have checked.
- **BTT Kraken:** 8 **built-in** TMC2160 (SPI, 24-60 V); the driver cannot be replaced, so the TMC2240/5160 from the VOSTOK guide do not apply, and the current is limited by external MOSFETs/Rsense (v1.0 and v1.1 differ). BTT does not describe a USB-CAN bridge mode (menuconfig offers USB or CAN), so `CAN` is empty in the registry and the installer does not accept CAN toolhead boards with the Kraken (use `--heads none`). No pin preset.
- **LDO Leviathan v1.2:** fewer than 7 drivers (the exact number is not confirmed): without toolhead boards there may not be enough for the motors and two extruders, plan for toolhead boards (EBB). The board ships without a bootloader; while the bridge is running, Klipper can only be updated over USB, not CAN.
- **MKS Monster8 V2:** katapult with a 32KiB bootloader comes from a community report (the bridge worked with 32KiB and did not bring up `can0` with 48KiB); MKS has no documentation for it: if the offset does not match, `can0` will not come up; the stock MKS bootloader (48KiB) is replaced, to roll back flash the stock firmware from the SD card. Jumper J2 must be set to CAN; check the chip marking (F446 or F407).
- **Super8 (F407), Max EZ, Octopus F446/F429:** DFU entry and the USB-CAN bridge come from documentation and schematics, not tried on hardware.
- **Rejected for the registry:** MKS SKIPR (built-in RK3328 host, the MCU is wired to it over UART, USB firmware is not standard, bridge not confirmed, no more than 6 drivers) and Fysetc Spider King407 (too little data, no second source).
- **Pins and the configurator.** There is no stock `electronics_*.cfg` for the new boards: the configurator generates a template without pins (`--config-source generate`) or takes your file from `user_configs/` (`--config-source user`); pin presets exist for the Octopus Pro (H723 per the guide; F446/F429 use `octopus_pro_v1.0`) and Manta M8P v1.0 / v1.1 / v2.0 (`templates/boards/main/`, not verified on hardware); Spider v2.x / v3.0, FLY-C8 and the 1.7 boards (except Octopus F446/F429) have no preset (see [CONFIGURATOR.en.md](../CONFIGURATOR.en.md)).

How to add your own board: [build-configs.en.md](build-configs.en.md#how-to-add-a-board).

## Toolhead boards

Toolhead boards are in the registry too (`ROLE=head`), and `--heads` accepts `none` and the id or alias of any of them (list: `./install_vostok.sh --list-boards`). The values that existed before (`v1.3`, `v2`, `ebb42`; `--h36` is the same) work as before and produce the same output. Only a toolhead board that has an electronics template `templates/boards/<TEMPLATE>.cfg` (the board's `TEMPLATE` field) can be selected: the configurator takes the extruder, thermistor and endstop pins from it and **does not invent them**. For the others the installer refuses: `--heads <board>: ... нет шаблона электроники` (no electronics template).

| id (aliases) | Chip | Crystal | CAN | `--heads` | Verified on hardware |
|---|---|---|---|---|---|
| `h36-v1.3` (`v1.3`) | STM32G0B1 | 12 MHz | PB0/PB1 | **yes**, `v1.3` | **yes** |
| `h36-v2` (`v2`) | STM32G431 | 12 MHz | PB0/PB1 | **yes**, `v2` | **yes** |
| `ebb42` (`ebb36`) | STM32G0B1 | 8 MHz | PB0/PB1 | **yes**, `ebb42` (`ebb36` selects the same) | **yes** (EBB36) |
| `ebb36-v1.0` (`ebb42-v1.0`) | STM32F072 | 8 MHz | PB8/PB9 | no: no electronics template (v1.0 pins differ from v1.1/v1.2) | no |
| `ebb-gen2` (`ebb36-gen2`, `ebb42-gen2`) | STM32G0B1 | 8 MHz | PB12/PB13 | no: no electronics template (Gen2 pins not confirmed) | no |
| `sht36-v2` (`sht42`, `sht36v2`) | STM32F072 | 8 MHz | PB8/PB9 | no: no electronics template | no |

For boards without a template the registry provides build configs (`tools/gen_configs.py --board <id>`), but not yet the selection in the installer. To enable such a board: add `templates/boards/<name>.cfg` with `@@T0@@`/`@@T1@@` blocks (extruder, thermistor, endstop and probe pins from the board documentation, checked against its schematic) and put the name in the `TEMPLATE` field of its `.board`; no code changes are needed.

> ⚠️ **Toolhead warnings.**
> - **`ebb36` is an ambiguous alias:** it points to `ebb42` (EBB36/EBB42 **v1.1 and v1.2**, G0B1). EBB36/EBB42 **v1.0** (F072) is `ebb36-v1.0` and **Gen2** is `ebb-gen2`: they have a different chip or CAN pins, the firmware is not interchangeable.
> - **FLY SHT36 v2** comes with three MCU variants: STM32F072, APM32F072 (after 2022-10-28) and GD32F103 (earlier). The config targets F072/APM32F072; if the board was bought before 2022-10-28 (GD32F103), do not use this build. The APM32F072 shows up in DFU as `314b:0106` while the installer looks for `0483:df11`, so it cannot be flashed over DFU through the installer, only over CAN into the factory Katapult.
> - **Not supported: FLY SHT36 v3 / SHT36 Max v3 and MKS THR36 / THR42**: they are RP2040. This needs separate code work: an `rp2040` family in `vostok/boards.py` and `tools/gen_configs.py` (Kconfig `MACH_RP2040`, `RPXXXX_CANBUS`, `RPXXXX_CANBUS_GPIO_RX/TX`, 16 KiB offset), BOOTSEL detection (`2e8a:0003`) instead of DFU `0483:df11` in `vostok/hardware.py`, UF2 flashing (the `RPI-RP2` drive or `picotool`) instead of `dfu-util` in `vostok/flashing.py`, and another way to get the UID for `canbus_uuid` (the RP2040 has no DFU UID address like the STM32). Per-board details (16 KiB offset, CAN GPIO 1/0 on the SHT36 v3) are in the branch commit history.

## Pinouts

Board pinout images live in [`pinouts/`](../pinouts/README.en.md) (a board-to-files table; sources and licences are in `pinouts/SOURCES.tsv`). The installer prints the path and web link of your board's image in the install plan (for an unverified board), at DFU entry, in the configurator warnings (empty ЗАПОЛНИТЕ pins, pin conflicts) and in the final summary. The images are set by the `PINOUT` field in `boards/<id>.board`; if it is empty (ALPS and Spider v3.0 H723), `DOC` is shown. FLY Super8 Pro and SHT36 v2 / SHT42 have schematics instead of a pinout (Mellow has no pinout sheet). The address can be overridden with `VOSTOK_PINOUT_URL`.

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
| `pinouts/` | board pinout images with sources (`SOURCES.tsv`) |
| `boards/` | board registry: one `<id>.board` file per board (build parameters, labels, DFU hints, whether verified on hardware) |
| `tests/` | unit tests (`python3 -m unittest discover tests`) and golden output references (`tests/run_golden.sh`) |
| `configs/` | Klipper and katapult build configs |
| `docs/` | this documentation split by topic |
| `VERSION`, `CHANGELOG.en.md` | installer version (`-V`/`--version` in every script) and the [changelog](../CHANGELOG.en.md) |
