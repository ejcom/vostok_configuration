# VOSTOK Installer

[🇷🇺 Русский](README.md) | 🇬🇧 English

Scripts that set up a VOSTOK on a clean system following the [💾 Electronics firmware](https://k3d.tech/vostok/manual/electronics/firmware/) guide (in Russian), and later update Klipper and all board firmwares with one button in Fluidd.

- `install_vostok.sh` — first-time setup: packages, KIAUH, the [Klipper fork](https://github.com/dmbutyugin/klipper/tree/generic-cartesian), Moonraker, Fluidd, katapult, flashing of all boards, printer configuration, update button.
- `configure_vostok.sh` — set up the printer config separately from the installation: choose or generate `electronics_*.cfg`, motor drivers, missing `[mcu]` sections, optional modules. Details: [CONFIGURATOR.en.md](CONFIGURATOR.en.md).
- `update_klipper_mcu.sh` — updates Klipper and re-flashes all boards (the button runs it too).
- `install_fluidd_button.sh` — installs the `mcu-update` button in Fluidd (power menu ⏻ → `mcu-update` → Start).
- `install_fluidd_theme.sh` — installs the K3D VOSTOK theme in Fluidd (colour, logo, Tektur font).

> ⚠️ The installer flashes boards and asks you to move jumpers and cables by hand. Read the prompts at every step. Without `--dry-run` it changes the system: installs packages, services and firmware.

## Supported hardware

| Part | Options |
|---|---|
| Mainboard | BTT Octopus Pro v1.1 **H723** (as in the guide) or Octopus Pro **F446** |
| Toolhead boards (CAN) | Fysetc **H36** v1.3 / v2 or BTT **EBB42**; or none |
| ALPS sensors (USB) | 0, 1 or 2 |

- **With toolhead boards** the Octopus is flashed as a **USB→CAN bridge**, as in the guide, and the toolhead boards are flashed over CAN (`can0`, 1 Mbit).
- **Without CAN toolhead boards** (with a passive Fly miniAB toolhead board wired directly to the Octopus) the Octopus works over plain USB.
- ALPS (STM32F072) are flashed over USB: katapult via DFU, then Klipper.

## Contents of `installer/`

| Path | What it is |
|---|---|
| `install_vostok.sh` | first-time installation (all stages) |
| `configure_vostok.sh` | printer config setup separate from the installation, see [CONFIGURATOR.en.md](CONFIGURATOR.en.md) |
| `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `mcu-update.service.in` | Klipper and firmware update, the Fluidd button |
| `install_fluidd_theme.sh`, `fluidd-theme/` | K3D VOSTOK theme for Fluidd: logo, `custom.css`, preset |
| `lib/vostok_config.sh` | shared config-setup library (sourced by `install_vostok.sh` and `configure_vostok.sh`) |
| `templates/` | blank electronics config without boards and drivers (`electronics_blank.cfg`), board presets (`boards/`) and driver presets (`drivers/`) |
| `tools/` | `gen_electronics.py` (electronics config generator), `mcu_merge.py` (adds `[mcu]` sections), `pin_conflicts.py` (finds duplicated pins), `gen_configs.sh` (firmware build configs) |
| `configs/` | Klipper and katapult build configs |
| `VERSION` | installer version (`-V`/`--version` in every script) |

## Requirements and checks

Before installing, the script checks the environment itself and stops with a clear message if something is wrong (`--only-detect` and `--dry-run` only report the result):

- **system**: `sudo`, `apt-get`, `dpkg`, `systemctl`, a running systemd, basic utilities; at least 2 GB free in the home directory; RAM + swap of at least 1 GB (otherwise a warning); `python3` 3.8 or newer;
- **access**: not run as root, a terminal for the dialog (when hardware steps are planned), membership in the `dialout` group (otherwise `sudo usermod -aG dialout $USER` and log in again), access to github.com;
- **tools** (missing ones are installed from packages automatically; with `--skip-software` the script only tells you what to install): `python3` (+ `venv`, `pyserial`), `git`, `curl`, `tar`, `make`, `arm-none-eabi-gcc`, `dfu-util`, `lsusb`, `ip`;
- **for the toolhead-board scheme (USB→CAN bridge)**: a kernel with `CONFIG_CAN`, `CONFIG_CAN_RAW`, `CONFIG_CAN_GS_USB`. If the kernel is built without CAN (as in some Orange Pi images), the script stops before flashing so that the Octopus is not left in bridge mode without a working `can0`.

## Quick start

You need a Debian-like system (Armbian, Raspberry Pi OS, BTT Pi, etc.), a regular user with `sudo`, internet access and the boards connected over USB. 24 V power is not needed for USB flashing, but is needed to flash toolhead boards over CAN.

```bash
git clone https://github.com/dmitry-sorkin/vostok_configuration.git
cd vostok_configuration/installer

./install_vostok.sh --only-detect   # what the script sees, changes nothing
./install_vostok.sh --dry-run       # all steps and commands, no changes
./install_vostok.sh                 # install

./configure_vostok.sh --dry-run     # config setup only, no installation or flashing
```

Keep the clone where it is: the update button runs the scripts from it. When the installer is started from a clone, it takes the printer configuration from that clone (handy for testing forks and PRs); otherwise it downloads `main`. `VOSTOK_CFG_LOCAL=0` forces the download, `VOSTOK_CFG_LOCAL=/path` uses your own directory.

## What the installer does

1. Checks and packages (`apt`: git, dfu-util, gcc-arm-none-eabi, python3-serial, etc.).
2. KIAUH → Klipper (`dmbutyugin/klipper` fork, `generic-cartesian` branch), Moonraker, Fluidd; the `gcode_shell_command` extension; katapult. If `~/klipper` exists but is not the fork, it offers to switch it.
3. Detects the boards (`/dev/serial/by-id`, DFU mode, USB-CAN bridge), asks about what cannot be detected (mainboard, toolhead boards, number of ALPS) and shows the plan.
4. With toolhead boards, configures `can0` (`/etc/network/interfaces.d/can0`, 1 Mbit, `txqueuelen 128`).
5. Flashes the boards one by one and tells you what to do by hand at each step:
   - **ALPS**: BOOT + RESET → DFU → katapult → Klipper;
   - **toolhead boards**: BOOT0/BOOT + RESET → DFU → katapult; Klipper later over CAN, verified with `canbus_query.py`;
   - **Octopus**: BOOT0 jumper + RESET → DFU. Method of your choice: **katapult and Klipper together over DFU in one session (recommended, the default)** or katapult over DFU and then Klipper through katapult (then remove the jumper). Klipper is for USB or the USB→CAN bridge.

   If flashing a board fails, a menu offers: retry, flash katapult and Klipper together over DFU, flash again via DFU (katapult) and Klipper through katapult, flash only Klipper directly over DFU, skip the board or abort. It works for every board.

   If a board already has katapult or Klipper, answer `s` + Enter at the DFU prompt and double-press RESET quickly.
6. Printer configuration. Asks where to take the electronics config from:
   - **standard** (repository root, maintained by the author) or **user** (`user_configs/`; check the wiring diagram at the top of the file first — a wrong wiring can damage the electronics);
   - **generate your own**: a blank template without boards and drivers + presets of the detected boards + a driver wizard; pins and parameters are taken from your current config, or from the stock main on a clean H723 installation;
   - **skip editing** (only if `printer.cfg` already exists, the default): only the missing `[mcu …]` sections are added.

   Then it asks about optional modules (for example `chamber_heater.cfg`) and checks for pin conflicts. Details and all rules: [CONFIGURATOR.en.md](CONFIGURATOR.en.md). Files are copied to `~/printer_data/config`, previous ones are saved as `*.bak-<date>`.
7. Starts Klipper, checks the firmware versions and installs the update button and the Fluidd theme.

Do by hand afterwards: check `electronics_*.cfg` against your wiring (for a generated file: fill in the pins marked `ЗАПОЛНИТЕ` and review the blocks marked `СВЕРЬТЕ`), check the toolhead thermistors (hold a thermistor with your fingers — the temperature should rise on the right head, otherwise swap the `T0…`/`T1…` sections), and for ALPS add `[load_cell_probe]` and run `LOAD_CELL_CALIBRATE`.

## `install_vostok.sh` options

| Option | Purpose |
|---|---|
| `--main h723\|f446` | mainboard (otherwise detected/asked) |
| `--heads none\|v1.3\|v2\|ebb42` | toolhead boards (`--h36` is the old name) |
| `--alps 0\|1\|2` | number of ALPS |
| `--config-source standard\|user\|generate\|skip` | config source: repository root, `user_configs/`, generate your own (blank template + presets of the detected boards + driver wizard) or skip editing (only add missing `[mcu …]` sections to an existing `printer.cfg`) |
| `--drivers SPEC` | drivers for `generate`: `all=2130\|2208\|2209\|2240\|5160\|5160plus` or `x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209` (no option: dialog, with `-y`: as in the stock config) |
| `--reference FILE\|none` | reference for pins and parameters of the generated config: your current electronics file by default, the stock main on a clean install (H723) |
| `--modules NAMES` | add optional modules without asking: `chamber_heater`, `all` or `none` |
| `--main-flash dfu\|katapult` | how to flash the mainboard: katapult and Klipper together over DFU (recommended) or katapult over DFU + Klipper through katapult |
| `--electronics FILE` | a specific `electronics_*.cfg` |
| `--only-detect` | only detect boards and show the plan |
| `--dry-run` | show steps and commands, change nothing |
| `--skip-software` / `--skip-flash` / `--skip-config` / `--skip-button` / `--skip-theme` | skip a stage |
| `--skip-board BOARD` | do not flash an already flashed board: `alps`, `alps0`, `alps1`, `main` or `heads` (repeatable) |
| `--reflash` | do not offer to skip, flash every board again |
| `--upgrade` | `apt upgrade` before installing |
| `-V`, `--version` | print the installer version (current: 1.2a, file `VERSION`) |
| `-y` | no questions where a default exists (hardware steps still wait for Enter) |

Log: `~/printer_data/logs/vostok_install.log`. The installation is repeatable: finished stages are skipped.

## Config setup separately from the installation

`./configure_vostok.sh` runs only the configuration stage and does not touch flashing or software. It is handy after the installation: change drivers, regenerate the config for different wiring, add a new board, enable a module.

```bash
./configure_vostok.sh --dry-run            # what would be done, changes nothing
./configure_vostok.sh                      # dialog: config source, drivers, modules
./configure_vostok.sh --config-source generate --drivers all=2209 --modules chamber_heater
```

The main rule: if you already have your own `electronics_*.cfg`, it is always the base (pins and parameters are taken from it); the stock main is used only on a clean installation. The full description, preset tables, file names, modules, backups and the option reference: **[CONFIGURATOR.en.md](CONFIGURATOR.en.md)**. Log: `~/printer_data/logs/vostok_configure.log`.

## Fluidd theme

`install_fluidd_theme.sh` (called by the installer, skip with `--skip-theme`) styles Fluidd like k3d.tech/vostok: teal `#009B98`, the K3D mark instead of the Fluidd logo, Tektur font in headings, background and cards in the site palette.

- The logo and `custom.css` go to `~/printer_data/config/.fluidd-theme/` (Fluidd picks them up itself and Fluidd updates leave the directory alone).
- The "K3D VOSTOK" preset is added to `~/fluidd/config.json` (it is in the Update Manager `persistent_files`) and activated through the Moonraker database. If another theme is already selected the script asks (`--force` replaces it without asking).
- A foreign `custom.css` is not overwritten without `--force` (the old one is kept as `.bak-<date>`). The font loads from Google Fonts; offline the default font stays.
- If the logo does not show (Moonraker requires authorization), run with `--logo-copy`; repeat after a Fluidd update.
- Reload the browser tab afterwards (Ctrl+F5). Options: `--no-activate`, `--dry-run`, `--uninstall`.

## Update button

In Fluidd: ⏻ (top right) → `mcu-update` → Start. The script updates the Klipper branch (`git fast-forward`, no KIAUH and no sudo password), builds the firmware, flashes all boards through katapult (USB and CAN; the Octopus bridge last) and checks that the firmware versions match the host. If there is nothing to update it says so. Log: `~/printer_data/logs/klipper_mcu_update.log`.

From a terminal:

```bash
./update_klipper_mcu.sh --list                    # what was found, changes nothing
./update_klipper_mcu.sh                           # update host (KIAUH), build and flash
./update_klipper_mcu.sh --no-update --force-flash # re-flash with the current version
```

**Do not press Stop** on `mcu-update` while flashing. The button can be installed on its own, without the installer: `./install_fluidd_button.sh` (`--dry-run`, `--uninstall`). The Klipper fork cannot be updated by the stock Update Manager button, which is why this one exists: after the host is updated the boards must be re-flashed, otherwise Klipper does not start (`MCU Protocol error`).

## If flashing failed

A flashing error on one board does not stop the installation: a menu offers to retry (from the step that failed), flash katapult and Klipper together over DFU, flash again via DFU (katapult) and Klipper through katapult, flash only Klipper directly over DFU, skip the board or abort. Without a terminal or with `-y` the board is skipped. Skipped boards are listed in the summary, and `printer.cfg` gets `ЗАПОЛНИТЕ` (fill in) instead of their serial/`canbus_uuid`.

If `flashtool.py` cannot write Klipper through katapult, choose "Flash Klipper directly over DFU" in the menu: the board is put in DFU, Klipper is written at the application offset and katapult is left untouched.

**RESET after DFU.** After flashing katapult over DFU, a single RESET may start the old firmware instead of katapult. Press RESET **twice in a row, quickly** (katapult blinks its LED slowly). If katapult is already on the board (for example after a previous attempt), answer `s` at the DFU prompt.

**Re-running.** The installer detects boards that already run the current Klipper version (`firmware/flashed.tsv` and `devices.tsv`) and offers to skip them, so flashed ALPS, head boards and Octopus are not flashed again. Explicitly: `--skip-board alps --skip-board heads`; to flash everything again: `--reflash`.

Manual retry: katapult stays in the board, Klipper stays stopped meanwhile.
1. `ls /dev/serial/by-id/` — the board may be `usb-katapult_…`. If not, double-press RESET quickly.
2. `python3 ~/katapult/scripts/flashtool.py -d /dev/serial/by-id/usb-katapult_… -f installer/firmware/<file>.bin`
3. CAN: `ip -s -d link show can0` (`state UP`, `bitrate 1000000`, no errors). The bus should measure about 60 Ω (two 120 Ω terminators); BUS-OFF is cured by restarting the interface: `sudo ip link set can0 down type can && sudo ip link set can0 up type can bitrate 1000000`.
4. `sudo systemctl start klipper`.

The scripts print these hints themselves on errors.

## Firmware build settings

They live in `configs/` (Klipper) and `configs/katapult/` (katapult). Regenerate with `tools/gen_configs.sh --force`. Values come from the guide; for the Octopus Pro F446 (not covered by the guide: 12 MHz, 32KiB bootloader, USB PA11/PA12) and the EBB42 (STM32G0B1, 8 MHz, CAN PB0/PB1) they come from documentation and board schematics. If your board has a different crystal or bootloader offset, edit the config: `make menuconfig KCONFIG_CONFIG=…` in the Klipper directory. The installer writes the "serial number / UUID → build config" map to `devices.tsv` (the button reads it).

## What has been tested

Tested on a real printer (Orange Pi, Debian 11, Octopus Pro H723 and two ALPS, no toolhead boards): a clean software installation through the KIAUH CLI (Klipper fork, Moonraker, Fluidd, katapult), board detection, chip detection in DFU by Option Bytes (STM32F0 and STM32H7), build and flashing of the USB variants (Octopus Pro H723 over USB, ALPS on STM32F072) through katapult, flashing Klipper to the Octopus Pro H723 over DFU without katapult, the Fluidd button, building all configs, writing `printer.cfg`, generating the electronics config for the H723 without toolhead boards, enabling the chamber heater module and the pin-conflict check.

Tested only in `--dry-run` and on copies of the config directory: generating the electronics config for the other combinations of toolhead boards and drivers (parsing the result as a Klipper config) and adding `[mcu]` sections.

**Not tested on hardware**: flashing katapult and Klipper together in one DFU session, the USB→CAN bridge, H36 and EBB42 toolhead boards, the Octopus Pro F446, detecting these boards (F4, STM32G0/G4) in DFU, and the pins from the Octopus Pro socket table for heads without toolhead boards on the H723 (taken from F446 configs): the config is generated from it, but the pins have not been checked against real wiring. If something does not match your board or you found a bug, open an issue with the log (`~/printer_data/logs/vostok_install.log`) or ask in the Telegram channel [K_3_D](http://t.me/K_3_D), mentioning Dmitry Kostenko.

## Removal

`./install_fluidd_button.sh --uninstall` removes the service, the Moonraker drop-in and the sudoers rule.

`./install_fluidd_theme.sh --uninstall` removes the preset and theme files and restores the default Fluidd theme.
