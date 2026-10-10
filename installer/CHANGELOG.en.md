# VOSTOK Installer Changelog

[🇷🇺 Русский](CHANGELOG.md) | 🇬🇧 English

The current version is stored in the `VERSION` file (`-V`/`--version` in every script). Description: [README.en.md](README.en.md).

## 1.2c — 2026-10-10

- Toolhead boards are now flashed "on the bench" by default: katapult and Klipper in one DFU session over USB, without 24 V or CAN. The method is chosen in the dialog or with `--heads-flash dfu|can`; "Klipper over CAN" is kept for an assembled printer (the installer warns about 24 V and CAN cables beforehand).
- The toolhead boards' `canbus_uuid` is computed from the chip UID read over DFU (`tools/can_uuid.py`), the Octopus bridge UUID from its USB serial. The values are written to `printer.cfg` and `devices.tsv` with a warning that they are not verified on the bus.
- New `--check-can` option: after installing the electronics in the printer it reads `canbus_uuid` from the bus, compares them and fixes `devices.tsv` and `printer.cfg` (`tools/mcu_merge.py --set`).
- Plan, flashing steps, summary and error menu hints were rewritten for both methods.

## 1.2b — 2026-10-10

- K3D VOSTOK Fluidd theme: `install_fluidd_theme.sh` and `fluidd-theme/` (teal `#009B98`, K3D logo, Tektur font, a preset in the Moonraker database).
- The installer applies the theme as a separate step, skip it with `--skip-theme`.
- Theme options: `--force`, `--logo-copy`, `--no-activate`, `--dry-run`, `--uninstall`.

## 1.2a — 2026-10-09

- Standalone `configure_vostok.sh` and the shared library `lib/vostok_config.sh`: config setup separately from the installation.
- Generation of `electronics_*.cfg` for your boards and drivers (`templates/`, `tools/gen_electronics.py`), adding `[mcu]` sections (`tools/mcu_merge.py`), pin-conflict check (`tools/pin_conflicts.py`), extra modules (`chamber_heater.cfg`).
- A clean installation takes everything from main, while an existing VOSTOK config is preserved: only `electronics_*.cfg`, `[mcu]` and the include are replaced, and `printer_base.cfg`, `chamber_heater.cfg` and `SAVE_CONFIG` stay.
- Fixed: replacing `[mcu]` used to eat the `SAVE_CONFIG` block.
- The toolhead board menu got the entry "none (passive board, e.g. fly miniAB)".

## 1.0a — 2026-10-09

The first numbered version. It includes everything done before versioning was introduced (since 2026-10-08).

- `install_vostok.sh`: packages, KIAUH, Klipper fork, Moonraker, Fluidd, katapult, flashing of ALPS, toolhead boards (H36 v1.3/v2, EBB42) and Octopus Pro (H723/F446) over USB or through the USB-CAN bridge, writing `printer.cfg`.
- `update_klipper_mcu.sh` and the `mcu-update` button in the Fluidd power menu: Klipper update and re-flashing of the boards.
- Environment checks before installation and flashing (sudo, disk space, tools, CAN support in the kernel).
- Flashing no longer stops on a single board failure: a menu "retry / via DFU / Klipper directly over DFU / skip / abort".
- Options `--skip-board` and `--reflash`, automatic skipping of boards that already have the current Klipper.
- Boards that were not flashed get an `ЗАПОЛНИТЕ` placeholder in `printer.cfg`, and the list of problem boards is printed at the end.
- Versioning: the `VERSION` file and the `-V`/`--version` option.
