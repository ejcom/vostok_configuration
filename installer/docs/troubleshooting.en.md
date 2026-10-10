# If flashing failed

[🇷🇺 Русский](troubleshooting.md) | 🇬🇧 English

[← Contents](../README.en.md)

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
