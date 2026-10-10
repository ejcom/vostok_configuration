# Update button

[🇷🇺 Русский](update-button.md) | 🇬🇧 English

[← Contents](../README.en.md)

In Fluidd: ⏻ (top right) → `mcu-update` → Start. The script updates the Klipper branch (`git fast-forward`, no KIAUH and no sudo password), builds the firmware, flashes all boards through katapult (USB and CAN; the Octopus bridge last) and checks that the firmware versions match the host. If there is nothing to update it says so. Log: `~/printer_data/logs/klipper_mcu_update.log`.

From a terminal:

```bash
./update_klipper_mcu.sh --list                    # what was found, changes nothing
./update_klipper_mcu.sh                           # update host (KIAUH), build and flash
./update_klipper_mcu.sh --no-update --force-flash # re-flash with the current version
```

**Do not press Stop** on `mcu-update` while flashing. The button can be installed on its own, without the installer: `./install_fluidd_button.sh` (`--dry-run`, `--uninstall`). The Klipper fork cannot be updated by the stock Update Manager button, which is why this one exists: after the host is updated the boards must be re-flashed, otherwise Klipper does not start (`MCU Protocol error`).
