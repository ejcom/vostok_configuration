# VOSTOK Installer Changelog

[🇷🇺 Русский](CHANGELOG.md) | 🇬🇧 English

The current version is stored in the `VERSION` file (`-V`/`--version` in every script). Description: [README.en.md](README.en.md).

## 1.6 — 2026-10-16

A `pinouts/` directory with board pinout images, and the installer now prints their path and web link.

- New directory `installer/pinouts/<Manufacturer>/<Board>/<revision>/`: official sheets from BTT (Octopus Pro v1.0 and v1.1, Manta M8P v1.0 / v1.1 / v2.0, EBB42 and EBB36), Fysetc (Spider v2.2 / v2.3 / v3.0, H36 v2.0 and the H36 v1.3 schematic), Mellow (FLY-C8). Source, commit, licence (not stated by the manufacturers), size and sha256 of every file are in `pinouts/SOURCES.tsv`; the board-to-files table and notes (light Octopus v1.0 sheet, schematic instead of a pinout for H36 v1.3, no pinout for ALPS and Spider v3.0 H723) are in `pinouts/README.en.md`.
- Octopus Pro v1.1: a warning is printed next to the image and link that some pins (HE0, HE2, Motor3-EN, RGB) differ from v1.0 (the `PINOUT_NOTE` `.board` field; the change list is in the BTT repository).
- `.board` format: optional `PINOUT` field (paths relative to `pinouts/`, space-separated), filled for every board except `alps` and `spider-v3-h723`. `Registry.pinout_paths`, `pinout_url` (address from `VOSTOK_PINOUT_URL`, by default the directory page on GitHub), `Board.pinout_list`; the `PINOUTS_DIR` variable overrides the directory. `ebb42` got a more precise `DOC`.
- The installer prints "Распиновка <board>: <path>" and "онлайн: <link>" (`DOC` when there are no images): in the install plan for an unverified board, in the DFU entry hints for the main board and head boards (once), in the configurator warnings (pins by connectors, ЗАПОЛНИТЕ), on pin conflicts, in the `configure_vostok.sh` summary and in the `install_vostok.sh` summary (a "Распиновка ваших плат" block: main board, head board, ALPS).
- The web link will work only after the merge into upstream main (until then the local path works; the address can be overridden with `VOSTOK_PINOUT_URL`).
- Tests: `tests/test_pinouts.py` (files, sha256, `SOURCES.tsv`, `PINOUT`, README), checks in `test_boards`, `test_install`, `test_configurator`. Golden references re-recorded: only the added pinout lines changed (`install/*`, `install_matrix/*`, `configure/*`).

## 1.5 — 2026-10-16

The installer was ported from bash to Python 3.8+ (standard library only). Commands, flags, environment variables, output texts, exit codes and file formats (`devices.tsv`, `*.board`, build configs) are unchanged: `install_vostok.sh`, `configure_vostok.sh`, `update_klipper_mcu.sh`, `install_fluidd_button.sh`, `install_fluidd_theme.sh` and `install_klipperscreen_theme.sh` remain the entry points and now run `python3 -m vostok <command>`.

- All logic lives in the `vostok/` package; `lib/vostok_config.sh` and `lib/boards.sh` are removed. `tools/gen_configs.sh` is replaced by `tools/gen_configs.py` (same `--force`, `--board`, `--check`, `--build` options, same 36 configs); `tools/gen_electronics.py` keeps its path and arguments but is now a wrapper over `vostok/`; the `tools/mcu_merge.py`, `tools/pin_conflicts.py` and `tools/can_uuid.py` wrappers are removed (their logic is available as `vostok.cfgfile` and `vostok.can_uuid`; the installer calls the modules directly).
- Added unit tests (`python3 -m unittest discover tests`) and golden output references taken from the old scripts (`tests/run_golden.sh`).
- Minor differences from 1.3a: Moonraker and the configuration download use `urllib`, `curl` is not called for them; without a terminal and without `-y` a question immediately gives `ОШИБКА: нужен терминал…` instead of bash internals (`/dev/tty: No such device`, `ans: unbound variable`), exit code 1 as before; files (`devices.tsv`, `moonraker.asvc`, `mcu_update.cfg`, themes) are written atomically; a failed external command or an unexpected error gives one `ОШИБКА: …` line instead of aborting the script or a traceback; `flash_can` looks for the bridge's katapult in `BYID_DIR` instead of a hard-coded `/dev/serial/by-id`; the configurator's temporary directory is always removed; the "bash 4.4+" check is gone.
- `python3` 3.8 or newer is required (Debian 11 has it); other requirements are unchanged.
- `configure_vostok.sh --printer-data <missing dir>` now stops with an error (`нет каталога … (укажите --printer-data)`); before (1.3) the directory was silently created and the config written there (the check existed in the code but never fired). Version 1.4 was never released: 1.5 is the first Python release.
- 1.5 includes the 1.3b changes (ported from bash to `vostok/`): marked as verified on hardware (from user reports): Manta M8P v2.0 (with CB1 and CB2), Fysetc H36 v1.3 and v2, BTT EBB36 (the `ebb42` entry, label "BTT EBB42/EBB36", alias `ebb36`). Confirmed: the USB→CAN bridge on the M8P v2.0, flashing toolheads "on the bench" and over CAN, `--check-can`. `VERIFIED="yes"` in `boards/*.board`; the installer plan no longer warns for these boards.
- Default mainboard choice: on the H723 the guide board (Octopus Pro) is offered first, then verified boards, then the rest (`Registry.rank` in `vostok/boards.py`, ordering in `rank_main_boards` in `vostok/configurator.py`), so the Manta M8P v2.0 does not displace the Octopus Pro once marked verified.
- Documentation: the warning in `docs/hardware.en.md` is cut to one paragraph, the details live in `docs/tested.en.md` (verified / dry-run only / not verified).

## 1.3a — 2026-10-15

- Configurator: main-board pin presets in `templates/boards/main/` (`octopus_pro_v1.0`, `manta_m8p_v1.0`, `manta_m8p_v1.1`, `manta_m8p_v2.0`); the `TEMPLATE` field of a `.board` file points at the preset and `tools/gen_configs.sh --check` verifies the file exists. For these boards `gen_electronics.py --template <name>` fills motors, sockets and driver SPI, bed, fans, endstops, probe, hotends (without head boards) and the "equipment → connector" table in the header; blocks carry the СВЕРЬТЕ note. The boards are not verified on hardware. Spider v2.x / v3.0 and FLY-C8 have no preset: no reliable pin source was found.
- Fixed: the driver SPI pins (`PA5/PA7/PA6`) are no longer applied to boards other than the Octopus Pro; the `--template octopus_pro` preset gave the F446 the v1.1 pins (bed `PB0`), whereas on the Octopus Pro v1.0 that is HE2 = `PB10`: F446 and F429 now use `octopus_pro_v1.0`. The H723 output is unchanged (compared byte for byte).
- Warning and installer messages name the preset's board instead of "Octopus Pro".

## 1.3 — 2026-10-15

- Board registry: `boards/*.board` (one file per board: chip, crystal, application offset, CAN pins, DFU hint, whether verified on hardware) and `lib/boards.sh`. Labels, build configs, DFU hints and checks in the installer come from the registry instead of being tied to the chip.
- New mainboards: BTT Octopus Pro v1.0 F429, BTT Manta M8P v1.0 / v1.1 / v2.0, Fysetc Spider v3.0 H723 / v3.0 F446 / v2.x, Mellow FLY-C8 (aliases `fly-c6`, `flyc6`). **None of the new boards are verified on hardware**: the parameters come from the manufacturers' documentation, and the installer warns about this in the plan.
- `--main` accepts ids and aliases (`h723`, `f446` work as before); `--list-boards` prints the registry. If several boards share the chip, the installer asks (default: the board from the previous `devices.tsv`, otherwise the verified one). Without questions (`-y`), with several possible boards and no `devices.tsv` entry, the installer stops and asks for `--main <id>`: it must not silently flash a board with another board's config.
- Refusal before flashing for boards without a USB-CAN bridge (M8P v1.0, Spider v2.x) when CAN toolhead boards are requested.
- `tools/gen_configs.sh` is built from the registry; options `--board ID`, `--check` (compare with `configs/`), `--build` (build all configs). Configs of the new boards: `configs/<id>.config`, `configs/<id>-canbridge.config`, `configs/katapult/<id>.config`; the config names of the earlier boards are unchanged.
- `update_klipper_mcu.sh` takes a USB MCU's config from `devices.tsv` (by serial number) and shows the board name in `--list`.
- `tools/gen_electronics.py`: `--board-name`, `--board-file`, `--template octopus_pro|none`. For boards without a stock config the configurator offers `generate` (template without pins) by default and never substitutes another board's (Octopus) pinout by default. `update_klipper_mcu.sh` ignores a `devices.tsv` entry whose config is built for another chip and warns when a board on a chip with several variants is missing from `devices.tsv`.
- A warning about unverified boards with a list in `docs/hardware.en.md` and `docs/tested.en.md`. The Octopus Pro F446 and the H36 v1.3/v2 and EBB42 toolhead boards are marked as not verified on hardware (F446 and H36 were wrongly listed as verified); only the Octopus Pro H723 and ALPS are verified.
- Documentation: the board table in `docs/hardware.en.md`, the "How to add a board" section in `docs/build-configs.en.md`.

## 1.2d — 2026-10-12

- K3D VOSTOK theme for KlipperScreen: `install_klipperscreen_theme.sh` and `klipperscreen-theme/` (k3d.tech/vostok palette, the K3D mark on the splash screen, Tektur font from `fonts/`, OFL license). `styles/vostok` is assembled from the `material-dark` icons, the font goes to `~/.local/share/fonts`, the theme is enabled in `KlipperScreen.conf`.
- The installer sets it up together with the Fluidd theme when `~/KlipperScreen` exists; skip with `--skip-theme`.
- Options: `--ks-dir`, `--printer-data`, `--no-activate`, `--force`, `--uninstall`, `--dry-run`.

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
