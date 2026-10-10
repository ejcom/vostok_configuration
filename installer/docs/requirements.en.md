# Requirements and checks

[🇷🇺 Русский](requirements.md) | 🇬🇧 English

[← Contents](../README.en.md)

Before installing, the script checks the environment itself and stops with a clear message if something is wrong (`--only-detect` and `--dry-run` only report the result):

- **system**: `sudo`, `apt-get`, `dpkg`, `systemctl`, a running systemd, basic utilities; at least 2 GB free in the home directory; RAM + swap of at least 1 GB (otherwise a warning); `python3` 3.8 or newer;
- **access**: not run as root, a terminal for the dialog (when hardware steps are planned), membership in the `dialout` group (otherwise `sudo usermod -aG dialout $USER` and log in again), access to github.com;
- **tools** (missing ones are installed from packages automatically; with `--skip-software` the script only tells you what to install): `python3` (+ `venv`, `pyserial`), `git`, `curl`, `tar`, `make`, `arm-none-eabi-gcc`, `dfu-util`, `lsusb`, `ip`;
- **for the toolhead-board scheme (USB→CAN bridge)**: a kernel with `CONFIG_CAN`, `CONFIG_CAN_RAW`, `CONFIG_CAN_GS_USB`. If the kernel is built without CAN (as in some Orange Pi images), the script stops before flashing so that the Octopus is not left in bridge mode without a working `can0`.
