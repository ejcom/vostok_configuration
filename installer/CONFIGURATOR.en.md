# VOSTOK configurator (`configure_vostok.sh`)

[🇷🇺 Русский](CONFIGURATOR.md) | 🇬🇧 English

The configurator sets up the printer configuration separately from the installation: it chooses or generates `electronics_*.cfg`, selects the motor drivers, adds the missing `[mcu …]` sections to `printer.cfg`, enables optional modules and checks that no pin is used twice. It does **not** touch board flashing or software installation: those are done by [`install_vostok.sh`](README.en.md). The same code runs at the configuration stage of the installer, so everything below applies to both scripts.

- [What it is for](#what-it-is-for)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Hardware detection](#hardware-detection)
- [Config sources](#config-sources)
- [“Skip” mode](#skip-mode)
- [Reference: your config is the base](#reference-your-config-is-the-base)
- [Driver wizard](#driver-wizard)
- [Driver presets](#driver-presets)
- [Board presets](#board-presets)
- [Heads without toolhead boards](#heads-without-toolhead-boards)
- [Name of the generated file](#name-of-the-generated-file)
- [Structure of the generated file](#structure-of-the-generated-file)
- [Optional modules and pin conflicts](#optional-modules-and-pin-conflicts)
- [Backups and safety](#backups-and-safety)
- [Option reference](#option-reference)
- [Typical scenarios](#typical-scenarios)
- [Limitations](#limitations)
- [Internals (for developers)](#internals-for-developers)

## What it is for

Run the configurator when:

- you installed your own drivers instead of the stock ones (TMC2209, TMC5160, etc.) and need a config for them;
- your wiring differs from the stock one (other sockets, heads wired directly to the Octopus, EBB42 boards instead of H36);
- you connected a new board (a second ALPS, toolhead boards) and its `[mcu …]` is missing in `printer.cfg`;
- you want to enable an optional module such as the chamber heater `chamber_heater.cfg`;
- you install the system from scratch: the installer calls the same code at its configuration stage.

## Quick start

```bash
cd ~/vostok_configuration/installer

./configure_vostok.sh --dry-run          # show what would be done, change nothing
./configure_vostok.sh                    # dialog: config source, drivers, modules
./configure_vostok.sh -y --config-source generate --drivers all=2209 --modules chamber_heater   # no questions
```

You need `python3` and the `~/printer_data` directory (another one: `--printer-data`). After the config is written, restart Klipper (`RESTART` in Fluidd or `sudo systemctl restart klipper`). Log: `~/printer_data/logs/vostok_configure.log`.

## How it works

1. **Hardware detection.** Mainboard, toolhead boards, number of ALPS: from options, from the current `printer.cfg`, from `/dev/serial/by-id`, otherwise by asking.
2. **Collecting `[mcu]` values.** Serial numbers and UUIDs come from `printer.cfg`, `devices.tsv` and `/dev/serial/by-id`.
3. **Config source menu.** Standard, user, generate, skip.
4. **For “generate”:** driver selection (wizard or `--drivers`), reference lookup, generation of `electronics_<…>.cfg` in a temporary directory.
5. **Writing.** The state of `printer.cfg` selects the mode. **Clean install** (no file, an empty file, or not a VOSTOK config, i.e. no `[include printer_base.cfg]`, such as the KIAUH example): `printer.cfg`, `printer_base.cfg`, `chamber_heater.cfg`, `postprocessing/` and the chosen `electronics_*.cfg` are copied from main, the previous file is saved as `*.bak-<date>`. **Existing VOSTOK config**: only the new `electronics_*.cfg` is written, and in `printer.cfg` only the set of `[mcu …]` sections and the `[include electronics_….cfg]` line change; `printer_base.cfg`, `chamber_heater.cfg` and `postprocessing/` are left alone (copied only if missing), the `SAVE_CONFIG` block and all other settings stay. Before writing, `printer.cfg` and the electronics file of the same name are saved as `*.bak-<date>`.
6. **Optional modules.** A question per module, pin-conflict check, adding `[include …]`.
7. **Pin-conflict check** of the whole config and the final warnings.

With `--dry-run` steps 1–4 and 6–7 run without writing anything and everything that would be written is printed.

## Hardware detection

Order of sources:

1. the options `--main`, `--heads`, `--alps`;
2. the existing `printer.cfg` and the files it includes:
   - mainboard: `stm32h723xx` / `stm32f446xx` in the `serial` of the `[mcu]` section, or `_h723_` / `_f446_` in the name of the included electronics file;
   - toolhead boards: a `[mcu T0_EBB]` section → EBB42; `[mcu T0CB]` → H36 (v2 if the electronics file name contains `H36v2`, otherwise v1.3); with only a USB `[mcu]` there are no toolhead boards;
   - ALPS: the number of `[mcu alps…]` sections (at most two);
3. `/dev/serial/by-id` (`usb-Klipper_stm32h723xx_…`, `usb-Klipper_stm32f072xb_…`) and DFU mode;
4. questions in the dialog (with `-y` the default is used).

Values for the `[mcu …]` blocks (serial and `canbus_uuid`) come in this order: the current `printer.cfg` → `devices.tsv` (written by the installer) → `/dev/serial/by-id`. If there is no value, the block contains `ЗАПОЛНИТЕ` (“fill in”); such a block is not added to an existing `printer.cfg` (only a warning is printed), and in a new one it is written as a placeholder on which Klipper reports an error until it is replaced.

## Config sources

| Menu item | What it does |
|---|---|
| **Standard (main root)** | copies `electronics_*.cfg` from the repository root (maintained by the author) |
| **User (user_configs)** | copies one of the `user_configs/` files; check the wiring diagram at the top of the file before use: a wrong wiring can damage the electronics |
| **Generate your own config** | builds a file from the blank template without boards and drivers and the presets of the detected boards, see below |
| **Skip editing the config** | available if `printer.cfg` already exists and selected **by default**; adds only the missing `[mcu …]` sections, see the next section |

For the first three items `printer.cfg`, `printer_base.cfg`, `chamber_heater.cfg`, the chosen `electronics_*.cfg` and `postprocessing/` are copied; `printer.cfg` gets the detected `[mcu]`, `[mcu T0CB]`/`[mcu T1CB]` (`T0_EBB`/`T1_EBB` for EBB42) and `[mcu alps]`/`[mcu alps_t1]`. The file can be given directly: `--electronics NAME.cfg`, the source with `--config-source standard|user|generate|skip`.

Without a terminal and without `--config-source`, an existing `printer.cfg` leads to “Skip” (the config is not replaced).

## “Skip” mode

Use it when you are happy with the config and only need to add a flashed board. `tools/mcu_merge.py` works; for every board in the list of found boards it prints one of these results:

| Result | Meaning |
|---|---|
| `OK` | the section already exists (the `serial`/`canbus_uuid` value is compared even if the section is named differently), nothing is done |
| `ADD` | no such section, it is added after the last `[mcu …]` of `printer.cfg` itself |
| `DIFF` | a section with that name exists but the value differs: the file is **not changed**, you see both values and decide yourself |
| `TODO` | the board is not flashed (`ЗАПОЛНИТЕ`), the section is not added |

Everything else in `printer.cfg` stays as is. A copy `printer.cfg.bak-<date>` is made before writing, and only if something is actually added. The module steps follow.

## Reference: your config is the base

**The rule:** if you already have your own `electronics_*.cfg`, it is always the base, with no questions. The stock main (for the H723) is used only on the first clean installation, when you have no config yet.

The reference is chosen automatically:

1. the active `[include electronics_*.cfg]` in `~/printer_data/config/printer.cfg`, if the file exists: this is your config;
2. otherwise, if the mainboard is the H723, the stock main from the repository root;
3. otherwise (F446 without its own config) there is no reference: pins stay empty, parameters take their defaults.

`--reference FILE` sets another reference, `--reference none` turns the reference off completely. The configurator tells which file it took at the start of generation.

What is taken from the reference (only mainboard pins, i.e. without another MCU prefix like `T0CB:`; toolhead-board pins are not carried over):

| What | From where and how |
|---|---|
| `step_pin`, `dir_pin`, `enable_pin` of the X, W, YL, YR, Z motors (and of the extruders if they are on the mainboard) | from the `[stepper motor_*]`, `[extruder]`, `[extruder1]` sections of the reference, with the `!` signs |
| the driver socket pin | `cs_pin` or `uart_pin` of the driver section of the reference. The driver type may differ: the pin is carried over between SPI and UART (on the Octopus the UART line is the CS pin) |
| SPI pins of the drivers | `spi_software_sclk/mosi/miso_pin` of the reference; if absent, the stock PA5 / PA7 / PA6 |
| `run_current`, `stealthchop_threshold`, `interpolate` | from the `[tmc… ]` sections of the reference per motor; if absent, from the stock main, then built-in values (X/W/YL/YR 1.6 A, Z 1.2 A, extruders 0.9 and 0.7 A) |
| other mainboard pins: bed and head heaters and thermistors, fans, endstops, LED, probe | if the same section and option exist in the generated file, the value of the reference replaces the preset |

## Driver wizard

Needed only for “Generate”. In the dialog:

1. “Which drivers are on the board?” — **All drivers the same** → pick a type from the list; or **Different drivers** → a type for every motor in turn: extruder T0, extruder T1 (only without toolhead boards), then X, W, Y left, Y right, Z.
2. With toolhead boards, the extruder drivers are **not asked**: the TMC2209 is soldered on the toolhead board and comes from its preset.

Without the dialog the drivers are given by `--drivers`:

```text
--drivers all=2209                                               # one type for all
--drivers x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209   # per motor (e0/e1 are not needed with toolhead boards)
```

Allowed types: `2130`, `2208`, `2209`, `2240`, `5160`, `5160plus` (also `tmc2209`, `5160pro`, `5160tplus`). With `-y` and no `--drivers` the stock drivers are used: `x, w, yl, yr, z = 2240`, `e0, e1 = 2209`.

## Driver presets

The `sense_resistor` values come from the BTT documentation (pages TMC2130, TMC2208, TMC2209, TMC2240, TMC5160, TMC5160T Plus, TMC5160T Pro V1.0). Pins in the presets are empty: they come from the reference or stay `ЗАПОЛНИТЕ`.

| Type | Interface | Pins in the section | `sense_resistor` | Note |
|---|---|---|---|---|
| TMC2130 | SPI | `cs_pin`, `spi_software_sclk/mosi/miso_pin` | 0.110 | |
| TMC2208 | UART | `uart_pin` | 0.110 | |
| TMC2209 | UART | `uart_pin` | 0.110 | |
| TMC2240 | SPI | `cs_pin`, `spi_software_*` | not set | Klipper does not use it for tmc2240 |
| TMC5160 / 5160T Pro | SPI | `cs_pin`, `spi_software_*` | 0.075 | |
| TMC5160T Plus | SPI | `cs_pin`, `spi_software_*` | 0.022 | the Klipper default (0.075) is wrong for the Plus |

Current and modes (`run_current`, `stealthchop_threshold`, `interpolate`) come from the reference (see above), **not** from the BTT examples: examples like `run_current: 0.80` are only for checking. If TMC2130, 2208 or 2209 is selected while the current from the reference is above 1.2 A (for example 1.6 A meant for the TMC2240), a warning is printed: reduce the current for these drivers (usually 0.8–1.2 A). Diagnostic pins (`diag1_pin`, `driver_SGT`) are not part of the presets: there are no sensorless endstops in this config.

## Board presets

They are applied to the template `templates/electronics_blank.cfg` in this order: Octopus Pro, then the toolhead boards.

- **Octopus Pro as in the guide** (`templates/boards/octopus_pro.cfg`): Y endstops (`PG6`, `PG9`), bed heater and thermistor (`PB0`, `PF3`), model fan (`!PD12`), electronics fan (`PD13`), LED (`PB11`). This is the stock H723 wiring.
- **Fysetc H36 v1.3 and v2** (`h36_v1.3.cfg`, `h36_v2.cfg`) and **BTT EBB42** (`ebb42.cfg`): one block per head (T0 and T1). Contents: extruder pins (step/dir/enable), the extruder TMC2209 (`uart_pin`, `sense_resistor 0.110`), heater, thermistor, hotend fan, the X endstop (W for T1), for T0 also the probe (`probe`, `probe_enable`), for H36 accelerometers and board and driver temperature sensors, for EBB42 the board fan. Pins are checked against the stock config and the configs from `user_configs/`. The names `[mcu T0CB]`/`[mcu T1CB]` (EBB42: `T0_EBB`/`T1_EBB`) are used as the pin prefix.
- **ALPS** (`templates/boards/alps.cfg`): a commented-out `[static_pwm_clock]` and `[load_cell_probe]` block with a hint is added. Why it is commented out: `printer_base.cfg` is built around `[probe]` (the virtual Z endstop, the macros read `configfile.config["probe"]`), two probes conflict. To use ALPS as the probe, comment out `[probe]`, uncomment the block and run `LOAD_CELL_CALIBRATE` (this needs an edit of `printer_base.cfg`).

## Heads without toolhead boards

When there are no CAN toolhead boards (the heads are wired directly to the Octopus), the required pins of the stock main sit on toolhead boards (`T0CB:PA8` etc.) and cannot be used. Then:

**Extruder motors** (if absent in the reference, H723 only): free sockets of the stock wiring.

| Motor | Socket | `step` / `dir` / `enable` | driver `cs`/`uart` |
|---|---|---|---|
| E0 (left head) | MOTOR4 | `PF9` / `PF10` / `!PG2` | `PF2` |
| E1 (right head) | MOTOR5 | `PC13` / `!PF0` / `!PF1` | `PE4` |

**Other head pins** come from the sockets of the Octopus Pro itself (`templates/boards/octopus_heads.cfg`):

| What | Socket | Pin |
|---|---|---|
| heater T0 / T1 | HE0 / HE1 | `PA2` / `PA3` |
| thermistor T0 / T1 | T0 / T1 | `PF4` / `PF5` |
| hotend fan T0 / T1 | FAN0 / FAN1 | `PA8` / `PE5` |
| endstop X / W | STOP2 / STOP3 | `^PG10` / `^PG11` (STOP0/STOP1 are used by the Y endstops in the stock wiring) |
| probe / probe enable | BLTouch | `^!PB7` / `PB6` |

**Where this table comes from and why it must be checked.** The pins are taken from repository configs for the Octopus Pro with heads on the board itself (`user_configs/electronics_octopus_pro_v1.0_f446_4x5160_3x2209.cfg`) and are not checked against the Octopus Pro v1.1 H723 documentation. Therefore:

- every block with such pins is marked in the file with the comment `# !!! СВЕРЬТЕ СО СВОЕЙ СХЕМОЙ …` (“check against your own wiring”), and the end of the run prints a warning listing these sections;
- if a pin from the table is already used by another section (the reference, a motor), it **stays empty** marked `ЗАПОЛНИТЕ`, and the warning says what uses it. For example, in the stock H723 `PA2` is the `enable_pin` of the left Y motor, so the `heater_pin` of extruder T0 stays empty;
- if the reference (your config) defines such pins on the mainboard, they are used instead of the table.

## Name of the generated file

The name follows the pattern of the files in `user_configs/`:

```text
electronics_<board>_<N>x<driver>[_<N>x<driver>…][_2x<heads>].cfg
```

- `<board>`: `octopus_pro_v1.1_h723` (H723) or `octopus_pro_v1.0_f446` (F446);
- driver groups — the number of mainboard motors with that driver, in descending count, then by name; with toolhead boards the extruders are not counted (their drivers are on the toolhead boards);
- `<heads>`: `H36v1.3`, `H36v2.0`, `ebb42`; no suffix without toolhead boards.

Driver tokens: `2130`, `2208`, `2209`, `2240`, `5160` (5160 and 5160T Pro), `5160tplus`.

| Configuration | File name |
|---|---|
| H723, no toolhead boards, all 5160 | `electronics_octopus_pro_v1.1_h723_7x5160.cfg` |
| H723, no toolhead boards, X/W/YL/YR 5160, Z and extruders 2209 | `electronics_octopus_pro_v1.1_h723_4x5160_3x2209.cfg` |
| H723, H36 v2.0, all 2240 | `electronics_octopus_pro_v1.1_h723_5x2240_2xH36v2.0.cfg` |
| H723, EBB42, all 2209 | `electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg` |
| H723, H36 v1.3, all 5160T Plus | `electronics_octopus_pro_v1.1_h723_5x5160tplus_2xH36v1.3.cfg` |

If a file with that name already exists in `~/printer_data/config`, it is first saved as `*.bak-<date>`.

## Structure of the generated file

1. **Header**: board, toolhead boards, drivers, a note about the markers.
2. **Motors**: `[stepper motor_x]`, `…_w`, `…_yl`, `…_yr`, `…_z`, `[extruder]`, `[extruder1]`.
3. **Drivers**: `[tmcXXXX …]` for each motor (for extruders with toolhead boards — from the head preset).
4. **Endstops and probe**: `[carriage xc]`, `[dual_carriage wc]`, `[carriage ylc]`, `[extra_carriage yrc]`, `[probe]`, `[output_pin probe_enable]`, the macros `PROBE_DEPLOY`/`PROBE_STOW`.
5. **Heaters and thermistors**, **fans**, host and mainboard temperatures.
6. **Additions**: LED, toolhead-board sections (accelerometers, temperature sensors), the ALPS block.

Markers in the file:

- `option: # ЗАПОЛНИТЕ: пин по схеме вашей платы` — the pin is not defined, fill it in, otherwise Klipper does not start;
- `# !!! СВЕРЬТЕ СО СВОЕЙ СХЕМОЙ …` before a block — the pins were filled in from the Octopus Pro socket table, check them.

The list of empty pins is also printed at the end of the run, per section.

## Optional modules and pin conflicts

Modules are files from the repository root that are enabled with an `[include …]` line. There is one now: **`chamber_heater.cfg`** (chamber heating, Smart Chamber Heater). Adding another is one line in `CFG_MODULES` in `lib/vostok_config.sh`.

For each module that is not yet enabled:

| State in `printer.cfg` | What the configurator does |
|---|---|
| an active `[include module.cfg]` exists | says “already enabled”, skips |
| a commented-out include exists (as in the stock `printer.cfg`) | uncomments the line if you agree |
| no include | if you agree, copies the file (if absent) and adds the include after the electronics include (or before the `SAVE_CONFIG` block, or at the end) |

The question defaults to “no”. `--modules chamber_heater|all|none` answers without asking (comma-separated names). With `-y` and without a terminal modules are left unchanged.

**The pin-conflict check** (`tools/pin_conflicts.py`) reads `printer.cfg` and all its `[include]`s, compares pins per board and looks for a pin used in several sections (it accounts for prefixes like `T0CB:` and the signs `!`, `^`, `~`). Not counted as a conflict: shared SPI lines (`spi_software_*`), repeats within one section, virtual endstops (`probe:z_virtual_endstop`). The check runs:

- before enabling a module: the config with and without the module is compared and only **new** conflicts matter. On a conflict the module is not enabled silently: the dialog asks “enable anyway?” (default no); without a terminal or with `-y` the module is not enabled;
- after the config is written: all conflicts are printed as a warning.

Example: with heads without toolhead boards the head thermistors sit on `PF4`/`PF5`, and `chamber_heater.cfg` uses the same pins (`temperature_sensor Chamber_Temperature` and `heater_generic chamber_heater`). The configurator shows the conflict and does not enable the module until you change the pins. Another example: `PA0` is `heater_bed` in the config for EBB42 and `fan_generic chamber_heater_fan` of the module.

## Backups and safety

- Before writing, `printer.cfg` and the electronics file of the same name are saved as `*.bak-<YYYYMMDD-HHMMSS>` next to the originals (on a clean install also `printer_base.cfg` and `chamber_heater.cfg`). In “Skip” mode and when enabling a module, `printer.cfg` is copied (only if the file actually changes).
- The `SAVE_CONFIG` block (PID, offsets) of an existing VOSTOK config is **kept**. On a clean install (a new `printer.cfg` from main) it stays only in the backup. Other options inside `[mcu …]` sections (e.g. `baud`) are not carried over when the `[mcu]` set is replaced: serial and `canbus_uuid` are taken from the previous sections.
- **Restoring the previous config:** `cp printer.cfg.bak-<date> printer.cfg` (and the same for the other files).
- Run `--dry-run` first. A convenient way to test on a copy: `./configure_vostok.sh --printer-data /path/to/copy`.
- Nothing runs as root, and the Klipper service is not restarted: restart it yourself after writing.

## Option reference

| Option | Purpose |
|---|---|
| `--main h723\|f446` | mainboard (otherwise detected or asked) |
| `--heads none\|v1.3\|v2\|ebb42` | CAN toolhead boards |
| `--alps 0\|1\|2` | number of ALPS sensors |
| `--config-source standard\|user\|generate\|skip` | electronics config source |
| `--electronics FILE` | a specific `electronics_*.cfg` (for `standard`/`user`) |
| `--drivers SPEC` | drivers for `generate`: `all=TYPE` or `x=…,w=…,yl=…,yr=…,z=…,e0=…,e1=…` |
| `--reference FILE\|none` | reference for pins and parameters (by default your electronics file, on a clean install the stock main) |
| `--modules NAMES` | enable modules without asking: `chamber_heater`, `all` or `none` |
| `--printer-data DIR` | the `printer_data` directory (default `~/printer_data`) |
| `--dry-run` | show what would be done, change nothing |
| `-y`, `--yes` | no questions where a default exists |
| `-V`, `--version` | installer version (file `VERSION`) |
| `-h`, `--help` | help |

Environment variables: `PRINTER_DATA`, `VOSTOK_CFG_LOCAL` (default `auto`: when the script runs from a `vostok_configuration` clone, files come from the clone; `0` always downloads `main`; a path uses your own directory), `VOSTOK_CFG_TARBALL` (URL of the configuration archive).

The script exits with code 1 on an error (no `python3`, no `printer_data` directory, generating or writing a file failed) and with 0 otherwise, including when there are warnings.

## Typical scenarios

```bash
# 1. Clean installation without toolhead boards, all drivers TMC5160 (pins from the stock main, heads from the Octopus table)
./configure_vostok.sh --config-source generate --main h723 --heads none --alps 0 --drivers all=5160

# 2. Change the drivers to TMC2209: pins and currents come from your current config
./configure_vostok.sh --config-source generate --drivers all=2209

# 3. Different wiring: EBB42 toolhead boards instead of H36 (look at --dry-run first)
./configure_vostok.sh --dry-run --config-source generate --heads ebb42 --drivers all=2209

# 4. Only add the new ALPS board to printer.cfg, leave the rest alone
./configure_vostok.sh --config-source skip --alps 2

# 5. Enable the chamber heater (with a pin-conflict check)
./configure_vostok.sh --config-source skip --modules chamber_heater
```

## Limitations

- **H723.** Taking pins from the stock main and from the MOTOR4/MOTOR5 table is designed for the Octopus Pro v1.1 H723. For the F446 without its own config pins stay empty (the head pin table also applies to the F446, it comes from F446 configs).
- **The head pin table is not checked** against the Octopus Pro v1.1 H723 documentation: check it against your wiring. Check the `dir_pin` sign and the motor directions after the first start.
- **`SAVE_CONFIG` is not carried over** only on a clean install over a foreign or empty `printer.cfg` (see above).
- **ALPS as the probe** needs an edit of `printer_base.cfg` (the block in the config is commented out).
- In the installer, `--skip-flash` skips the whole configuration stage: the `[mcu]` values come from the flashing stage. To set up the config without flashing, use `configure_vostok.sh`.
- Not tested on hardware: running the configurator on real H36 and EBB42 toolhead boards and on the Octopus Pro F446. Tested on copies of the config directory and in `--dry-run`: all combinations of toolhead boards and drivers, parsing the result as a Klipper config.

## Internals (for developers)

| File | Role |
|---|---|
| `configure_vostok.sh` | entry point: option parsing, hardware detection, `stage_config` |
| `lib/vostok_config.sh` | shared library for `install_vostok.sh` and `configure_vostok.sh`: `detect_hardware`, `pick_electronics` (source menu), `drivers_wizard`, `find_reference`, `gen_custom_electronics`, `print_gen_warnings`, `merge_mcus_into_cfg`, `stage_config`, `stage_modules` |
| `tools/gen_electronics.py` | builds the file: template + presets + drivers + reference; prints `NAME`, `FILL`, `EMPTY`, `WARN` |
| `tools/mcu_merge.py` | adds `[mcu …]` (`OK`/`ADD`/`DIFF`/`TODO`), `--list` mode |
| `tools/pin_conflicts.py` | finds duplicated pins |
| `templates/electronics_blank.cfg` | template with empty pins and the markers `;;DRIVERS;;`, `;;EXTRAS;;` |
| `templates/boards/*.cfg` | board presets: `octopus_pro`, `octopus_extruders`, `octopus_heads`, `h36_v1.3`, `h36_v2`, `ebb42`, `alps` |
| `templates/drivers/*.cfg` | driver presets (`{SEC}` is the motor section name) |

How to extend:

- **A new driver**: a file `templates/drivers/tmcNNNN.cfg` and an entry in `DRIVER_TYPES`, `DRIVER_FILES`, `DRIVER_TOKEN`, `DRIVER_TITLE` in `gen_electronics.py`, an item in `drv_pick` in `lib/vostok_config.sh`.
- **A new toolhead board**: a file `templates/boards/<name>.cfg` with `@@T0@@`/`@@T1@@` blocks and `{M}` instead of the MCU name, a value for `--heads` and the `head_*` functions of the library.
- **A new module**: an `"file.cfg|Title"` entry in `CFG_MODULES` and the file itself in the repository root.

How to test without touching the working config: copy `~/printer_data` to a temporary directory and run with `--printer-data` or `PRINTER_DATA=`. To check the generator: run `gen_electronics.py` with `--out-dir` for all combinations of `--heads` and `--drivers` and parse the result with `configparser` (as Klipper does).
