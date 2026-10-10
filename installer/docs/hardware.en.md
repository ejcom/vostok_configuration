# Supported boards and directory contents

[🇷🇺 Русский](hardware.md) | 🇬🇧 English

[← Contents](../README.en.md)

## Supported hardware

| Part | Options |
|---|---|
| Mainboard | BTT Octopus Pro v1.1 **H723** (as in the guide) or Octopus Pro **F446** |
| Toolhead boards (CAN) | Fysetc **H36** v1.3 / v2 or BTT **EBB42**; or none |
| ALPS sensors (USB) | 0, 1 or 2 |

- **With toolhead boards** the Octopus is flashed as a **USB→CAN bridge**, as in the guide, and the toolhead boards run over CAN (`can0`, 1 Mbit). They can be flashed in two ways:
  - **"on the bench"** (the default): katapult and Klipper together over DFU via USB, without 24 V or CAN; `canbus_uuid` is computed from the chip UID and verified after assembly with `install_vostok.sh --check-can`;
  - **in an assembled printer**: katapult over DFU, Klipper over CAN (24 V and CAN cables required).
- **Without CAN toolhead boards** (with a passive Fly miniAB toolhead board wired directly to the Octopus) the Octopus works over plain USB.
- ALPS (STM32F072) are flashed over USB: katapult via DFU, then Klipper.

## Contents of `installer/`

| Path | What it is |
|---|---|
| `install_vostok.sh` | first-time installation (all stages) |
| `configure_vostok.sh` | printer config setup separate from the installation, see [CONFIGURATOR.en.md](../CONFIGURATOR.en.md) |
| `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `mcu-update.service.in` | Klipper and firmware update, the Fluidd button |
| `install_fluidd_theme.sh`, `fluidd-theme/` | K3D VOSTOK theme for Fluidd: logo, `custom.css`, preset |
| `lib/vostok_config.sh` | shared config-setup library (sourced by `install_vostok.sh` and `configure_vostok.sh`) |
| `templates/` | blank electronics config without boards and drivers (`electronics_blank.cfg`), board presets (`boards/`) and driver presets (`drivers/`) |
| `tools/` | `gen_electronics.py` (electronics config generator), `mcu_merge.py` (adds `[mcu]` sections, `--set` for `canbus_uuid`), `can_uuid.py` (canbus_uuid from the chip UID), `pin_conflicts.py` (finds duplicated pins), `gen_configs.sh` (firmware build configs) |
| `configs/` | Klipper and katapult build configs |
| `docs/` | this documentation split by topic |
| `VERSION`, `CHANGELOG.en.md` | installer version (`-V`/`--version` in every script) and the [changelog](../CHANGELOG.en.md) |
