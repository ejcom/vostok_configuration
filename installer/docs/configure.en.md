# Config setup separately from the installation

[🇷🇺 Русский](configure.md) | 🇬🇧 English

[← Contents](../README.en.md)

`./configure_vostok.sh` runs only the configuration stage and does not touch flashing or software. It is handy after the installation: change drivers, regenerate the config for different wiring, add a new board, enable a module.

```bash
./configure_vostok.sh --dry-run            # what would be done, changes nothing
./configure_vostok.sh                      # dialog: config source, drivers, modules
./configure_vostok.sh --config-source generate --drivers all=2209 --modules chamber_heater
```

The main rule: if you already have your own `electronics_*.cfg`, it is always the base (pins and parameters are taken from it); the stock main is used only on a clean installation. The full description, preset tables, file names, modules, backups and the option reference: **[CONFIGURATOR.en.md](../CONFIGURATOR.en.md)**. Log: `~/printer_data/logs/vostok_configure.log`.
