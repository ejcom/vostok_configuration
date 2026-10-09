# VOSTOK Installer

[🇷🇺 Русский](README.md) | 🇬🇧 English

Scripts that set up a VOSTOK on a clean system following the [💾 Electronics firmware](https://k3d.tech/vostok/manual/electronics/firmware/) guide (in Russian), and later update Klipper and all board firmwares with one button in Fluidd.

- `install_vostok.sh` — first-time setup: packages, KIAUH, the [Klipper fork](https://github.com/dmbutyugin/klipper/tree/generic-cartesian), Moonraker, Fluidd, katapult, flashing of all boards, printer configuration, update button.
- `update_klipper_mcu.sh` — updates Klipper and re-flashes all boards (the button runs it too).
- `install_fluidd_button.sh` — installs the `mcu-update` button in Fluidd (power menu ⏻ → `mcu-update` → Start).

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
   - **Octopus**: BOOT0 jumper + RESET → DFU → katapult (then remove the jumper) → Klipper (USB or USB→CAN bridge).

   If a board already has katapult or Klipper, answer `s` + Enter at the DFU prompt and double-press RESET quickly.
6. Printer configuration. Asks where to take the electronics config from: **standard** (repository root, maintained by the author) or **user** (`user_configs/`, configurations by users; check the wiring diagram at the top of the file first — a wrong wiring can damage the electronics). Copies `printer.cfg`, `printer_base.cfg`, `chamber_heater.cfg`, the chosen `electronics_*.cfg` and `postprocessing/` to `~/printer_data/config` and fills in the detected `[mcu]`, `[mcu T0CB]`/`[mcu T1CB]` (`T0_EBB`/`T1_EBB` for EBB42; the names come from the chosen file) and `[mcu alps]`. **An existing `printer.cfg` is never touched**; the script only prints the `[mcu …]` block to paste.
7. Starts Klipper, checks the firmware versions and installs the update button.

Do by hand afterwards: adapt `electronics_*.cfg` to your wiring, check the toolhead thermistors (hold a thermistor with your fingers — the temperature should rise on the right head, otherwise swap the `T0…`/`T1…` sections), and for ALPS add `[load_cell_probe]` and run `LOAD_CELL_CALIBRATE`.

## `install_vostok.sh` options

| Option | Purpose |
|---|---|
| `--main h723\|f446` | mainboard (otherwise detected/asked) |
| `--heads none\|v1.3\|v2\|ebb42` | toolhead boards (`--h36` is the old name) |
| `--alps 0\|1\|2` | number of ALPS |
| `--config-source standard\|user` | config source: repository root or `user_configs/` |
| `--electronics FILE` | a specific `electronics_*.cfg` |
| `--only-detect` | only detect boards and show the plan |
| `--dry-run` | show steps and commands, change nothing |
| `--skip-software` / `--skip-flash` / `--skip-config` / `--skip-button` | skip a stage |
| `--skip-board BOARD` | do not flash an already flashed board: `alps`, `alps0`, `alps1`, `main` or `heads` (repeatable) |
| `--reflash` | do not offer to skip, flash every board again |
| `--upgrade` | `apt upgrade` before installing |
| `-y` | no questions where a default exists (hardware steps still wait for Enter) |

Log: `~/printer_data/logs/vostok_install.log`. The installation is repeatable: finished stages are skipped.

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

A flashing error on one board does not stop the installation: a menu offers to retry (from the step that failed), reflash via DFU, skip the board or abort. Without a terminal or with `-y` the board is skipped. Skipped boards are listed in the summary, and `printer.cfg` gets `ЗАПОЛНИТЕ` (fill in) instead of their serial/`canbus_uuid`.

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

Tested on a real printer: board detection, build and flashing of the USB variants (Octopus Pro H723 over USB, ALPS on STM32F072), the Fluidd button, building all configs, `printer.cfg` generation. **Not tested on hardware**: a clean KIAUH CLI installation, the USB→CAN bridge, H36 and EBB42 toolhead boards, the Octopus Pro F446, and chip detection in DFU by Option Bytes. If something does not match your board or you found a bug, open an issue with the log (`~/printer_data/logs/vostok_install.log`) or ask in the Telegram channel [K_3_D](http://t.me/K_3_D), mentioning Dmitry Kostenko.

## Removal

`./install_fluidd_button.sh --uninstall` removes the service, the Moonraker drop-in and the sudoers rule.
