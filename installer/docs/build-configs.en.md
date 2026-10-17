# Firmware build settings

[🇷🇺 Русский](build-configs.md) | 🇬🇧 English

[← Contents](../README.en.md)

They live in `configs/` (Klipper) and `configs/katapult/` (katapult). Regenerate with `tools/gen_configs.py --force` (built from the `boards/*.board` board registry). Values come from the guide; for the Octopus Pro F446 (not covered by the guide: 12 MHz, 32KiB bootloader, USB PA11/PA12) and the EBB42 (STM32G0B1, 8 MHz, CAN PB0/PB1) they come from documentation and board schematics. If your board has a different crystal or bootloader offset, edit the config: `make menuconfig KCONFIG_CONFIG=…` in the Klipper directory. The installer writes the "serial number / UUID → build config" map to `devices.tsv` (the button reads it).

File names come from the board's `CFG` field: Klipper USB is `configs/<CFG>.config`, the USB→CAN bridge is `configs/<CFG>-canbridge.config`, a CAN toolhead is `configs/<CFG>-can.config`, katapult is `configs/katapult/<CFG>.config` (for toolheads `<CFG>-can.config`). The earlier boards keep the old names where `CFG` is the chip (`stm32h723xx`, `stm32f446xx`, `stm32g0b1xx`, `stm32g431xx`, `stm32g0b1xx-ebb42`, `stm32f072xb`) so that already written `devices.tsv` files keep working; for the new boards `CFG` equals the id (`configs/fly-c8.config`, `configs/katapult/spider-v3-h723.config`, etc.). `devices.tsv` stores the build config name; `update_klipper_mcu.sh` looks for a USB MCU's config in `devices.tsv` first (by serial number), then `configs/<serial>.config`, then `configs/<chip>.config`.

## How to add a board

1. Create `boards/<id>.board` (easiest is to copy a similar board). Format: `KEY="value"` lines without code, `#` comments. Fields:

   | Field | Value |
   |---|---|
   | `LABEL` | display name |
   | `ROLE` | `main`, `head` or `alps` |
   | `CHIP` | Klipper chip name, e.g. `stm32h723xx` |
   | `FAMILY` | `f0`, `f4`, `h7` or `g` |
   | `MACH` | chip name in Kconfig, e.g. `STM32H723` |
   | `CLOCK` | crystal: `8M`, `12M` or `25M` |
   | `APP_OFFSET` | where Klipper starts after the bootloader: `2000`, `8000` or `20000` |
   | `USB` | `PA11_PA12` or empty |
   | `CAN` | CAN pins (e.g. `PD0_PD1`) or empty if there is no bridge/CAN |
   | `CAN_KIND` | `cmenu` (bridge on a mainboard), `mmenu` or `direct` (toolheads); required if `CAN` is set |
   | `INITIAL_PINS`, `BRIDGE_INITIAL_PINS`, `KATAPULT_INITIAL_PINS` | pins to keep off at start (Klipper USB, bridge, katapult) |
   | `KATAPULT_LED`, `KATAPULT_DOUBLE_RESET` | katapult LED; `y` means start by double RESET |
   | `CFG` | base of the file names (equals the id for new boards) |
   | `ALIASES` | space-separated aliases for `--main` |
   | `DFU_HINT`, `DFU_HOW` | DFU entry hint text; `jumper` or `button` |
   | `ELEC_PATTERN` | part of an `electronics_*.cfg` name that ties a file to the board (empty means no stock config) |
   | `TEMPLATE` | for a mainboard: `octopus_pro` (Octopus pin presets) or the name of `templates/boards/main/<name>.cfg`; for a toolhead board: the name of `templates/boards/<name>.cfg` (head pin preset); empty means no template, the head cannot be selected with `--heads` |
   | `HEAD_NAMES` | toolhead section names (for `ROLE=head`) |
   | `VERIFIED` | `yes` if verified on hardware, `no` if only from documentation |
   | `DOC`, `NOTE` | data source and a note |

   A board without a USB→CAN bridge (empty `CAN`) cannot be used with CAN toolhead boards: the installer refuses.
2. Create the build configs: `tools/gen_configs.py --board <id>` (add `--force` to overwrite existing ones). The script builds the Kconfig lines from the fields and checks that each one survives `olddefconfig`.
3. Check: `tools/gen_configs.py --check` generates into a temporary directory and compares with `configs/` by the significant keys (exit code 1 on a mismatch).
4. Build: `tools/gen_configs.py --build` builds every config in a temporary directory; for katapult it checks that `katapult.bin` is smaller than the application offset.
5. Check the board: `./install_vostok.sh --list-boards`, `./install_vostok.sh --dry-run --main <id>`. Until the board has been flashed on real hardware, keep `VERIFIED="no"`.

The registry boards and their parameters: [hardware.en.md](hardware.en.md#mainboards).
