# Installation: launch, stages, options

[🇷🇺 Русский](install.md) | 🇬🇧 English

[← Contents](../README.en.md)

## Launch and check modes

You need a Debian-like system (Armbian, Raspberry Pi OS, BTT Pi, etc.), a regular user with `sudo`, internet access and the boards connected over USB. 24 V power is not needed for USB flashing: toolhead boards are flashed "on the bench" over DFU by default. A 24 V supply and CAN cables are needed only for the "Klipper over CAN" option and for verifying `canbus_uuid` after the electronics are installed in the printer.

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
3. Detects the boards (`/dev/serial/by-id`, DFU mode, USB-CAN bridge), asks about what cannot be detected (mainboard, toolhead boards, number of ALPS) and shows the plan. If several registry boards share the detected chip (for example H723 on the Octopus Pro, Manta M8P v2.0 and Spider v3), it asks which one you have; the default is the board from the previous `devices.tsv`, otherwise the one verified on hardware; with `-y` and no `devices.tsv` entry the installer stops here and requires `--main <id>`. For boards without a USB-CAN bridge combined with CAN toolhead boards the installer refuses before flashing (use `--heads none`); for boards not verified on hardware the plan carries a warning.
4. With toolhead boards, configures `can0` (`/etc/network/interfaces.d/can0`, 1 Mbit, `txqueuelen 128`).
5. Flashes the boards one by one and tells you what to do by hand at each step:
   - **ALPS**: BOOT + RESET → DFU → katapult → Klipper;
   - **toolhead boards** — method of your choice (`--heads-flash`):
     - **`dfu` — "on the bench" (the default, also with `-y`)**: one board at a time, connected over USB only, BOOT0/BOOT + RESET → DFU → katapult and Klipper in a single session. No 24 V and no CAN needed, so every board can be flashed before it goes into the printer. The `canbus_uuid` cannot be queried without a bus, so the installer reads the chip UID over DFU and computes `canbus_uuid` with the same algorithm as the firmware; the bridge UUID is computed from the Octopus USB serial. These values go to `printer.cfg` and `devices.tsv` but are **not verified on the bus**: after installing the electronics in the printer, apply 24 V and run `./install_vostok.sh --check-can` (see below). If the UID could not be read, `printer.cfg` keeps `ЗАПОЛНИТЕ`;
     - **`can` — for an assembled printer**: BOOT0/BOOT + RESET → DFU → katapult, then Klipper over CAN, verified with `canbus_query.py`. **A 24 V supply and CAN connections of the toolhead boards and the Octopus are required** — the installer warns about this before flashing starts;
   - **mainboard** (the Octopus as an example): BOOT0 jumper + RESET → DFU; some boards enter DFU with buttons or a different jumper — the installer prints the hint for the selected board, see the [table](hardware.en.md#mainboards). Method of your choice: **katapult and Klipper together over DFU in one session (recommended, the default)** or katapult over DFU and then Klipper through katapult (then remove the jumper). Klipper is for USB or the USB→CAN bridge.

   If flashing a board fails, a menu offers: retry, flash katapult and Klipper together over DFU, flash again via DFU (katapult) and Klipper through katapult, flash only Klipper directly over DFU, skip the board or abort. It works for every board.

   If a board already has katapult or Klipper, answer `s` + Enter at the DFU prompt and double-press RESET quickly.
6. Printer configuration. Asks where to take the electronics config from:
   - **standard** (repository root, maintained by the author) or **user** (`user_configs/`; check the wiring diagram at the top of the file first — a wrong wiring can damage the electronics);
   - **generate your own**: a blank template without boards and drivers + presets of the detected boards + a driver wizard; pins and parameters are taken from your current config, or from the stock main on a clean H723 installation;
   - **skip editing** (only if `printer.cfg` already exists, the default): only the missing `[mcu …]` sections are added.

   Then it asks about optional modules (for example `chamber_heater.cfg`) and checks for pin conflicts. Details and all rules: [CONFIGURATOR.en.md](../CONFIGURATOR.en.md). Files are copied to `~/printer_data/config`, previous ones are saved as `*.bak-<date>`.
7. Starts Klipper, checks the firmware versions and installs the update button and the Fluidd theme.

Do by hand afterwards: check `electronics_*.cfg` against your wiring (for a generated file: fill in the pins marked `ЗАПОЛНИТЕ` and review the blocks marked `СВЕРЬТЕ`), check the toolhead thermistors (hold a thermistor with your fingers — the temperature should rise on the right head, otherwise swap the `T0…`/`T1…` sections), and for ALPS add `[load_cell_probe]` and run `LOAD_CELL_CALIBRATE`.

## `install_vostok.sh` options

| Option | Purpose |
|---|---|
| `--main <id\|alias>` | mainboard: an id from the `boards/` registry or an alias (`h723`, `f446` — Octopus Pro, as before; the others are in the [table](hardware.en.md#mainboards)); otherwise detected/asked |
| `--list-boards` | print the registry boards (id, chip, USB-CAN bridge, verified on hardware) and exit |
| `--heads none\|v1.3\|v2\|ebb42` | toolhead boards (`--h36` is the old name); the id and aliases of registry toolhead boards (`ROLE=head`) are also accepted, but heads without an electronics template (`ebb36-v1.0`, `ebb-gen2`, `sht36-v2`) are rejected with an error, see [hardware.en.md](hardware.en.md#toolhead-boards) |
| `--heads-flash dfu\|can` | how to flash toolhead boards: `dfu` — "on the bench", katapult and Klipper over USB without 24 V or CAN (the default, also with `-y`); `can` — katapult over DFU, Klipper over CAN (24 V and CAN cables required) |
| `--check-can` | after installing the electronics in the printer: read `canbus_uuid` from the CAN bus (24 V required), compare with the computed values, fix `devices.tsv` and `printer.cfg`, restart Klipper; flashes nothing |
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
| `-V`, `--version` | print the installer version (current: 1.3, file `VERSION`) |
| `-y` | no questions where a default exists (hardware steps still wait for Enter) |

Log: `~/printer_data/logs/vostok_install.log`. The installation is repeatable: finished stages are skipped.
