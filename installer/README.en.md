# VOSTOK Installer

[🇷🇺 Русский](README.md) | 🇬🇧 English

Scripts that set up a VOSTOK on a clean system following the [💾 Electronics firmware](https://k3d.tech/vostok/manual/electronics/firmware/) guide and then update Klipper and the board firmware with a single button in Fluidd.

> ⚠️ The installer flashes boards and asks you to move jumpers and cables by hand. Read the prompts at every step. Without `--dry-run` it changes the system: it installs packages, services and firmware.

## Quick start

You need a Debian-like system (Armbian, Raspberry Pi OS, BTT Pi, etc.), a regular user with `sudo`, internet access and the boards connected over USB.

```bash
git clone https://github.com/dmitry-sorkin/vostok_configuration.git
cd vostok_configuration/installer

./install_vostok.sh --dry-run   # show all steps without changing anything (optional)
./install_vostok.sh             # installation: answer the questions and follow the prompts
```

The installer detects the boards, installs the software, flashes the boards, builds the printer config, and installs the update button and the Fluidd theme. Afterwards check `electronics_*.cfg` against your wiring and check the toolhead thermistors ([details](docs/install.en.md)). Keep the clone directory in place: the update button runs the scripts from it.

## Contents

| Section | What it covers |
|---|---|
| [Boards and directory contents](docs/hardware.en.md) | supported boards, what is in `installer/` |
| [Requirements and checks](docs/requirements.en.md) | what the script checks before installing |
| [Installation](docs/install.en.md) | launch, installer stages, `install_vostok.sh` options |
| [Config setup](docs/configure.en.md) | `configure_vostok.sh` separately from the installation; full description: [CONFIGURATOR.en.md](CONFIGURATOR.en.md) |
| [Fluidd theme](docs/theme.en.md) | Fluidd in the K3D VOSTOK style |
| [Update button](docs/update-button.en.md) | updating Klipper and board firmware from Fluidd |
| [If flashing failed](docs/troubleshooting.en.md) | retry, DFU, CAN, manual flashing |
| [Firmware build settings](docs/build-configs.en.md) | `configs/`, `devices.tsv` |
| [What has been tested](docs/tested.en.md) | what was tested on hardware and what was not |
| [Removal](docs/uninstall.en.md) | how to remove the button and the theme |
| [Changelog](CHANGELOG.en.md) | what is new in each version |
