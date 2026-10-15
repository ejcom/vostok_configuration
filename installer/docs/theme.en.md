# Fluidd theme

[🇷🇺 Русский](theme.md) | 🇬🇧 English

[← Contents](../README.en.md)

`install_fluidd_theme.sh` (called by the installer, skip with `--skip-theme`) styles Fluidd like k3d.tech/vostok: teal `#009B98`, the K3D mark instead of the Fluidd logo, Tektur font in headings, background and cards in the site palette.

- The logo and `custom.css` go to `~/printer_data/config/.fluidd-theme/` (Fluidd picks them up itself and Fluidd updates leave the directory alone).
- The "K3D VOSTOK" preset is added to `~/fluidd/config.json` (it is in the Update Manager `persistent_files`) and activated through the Moonraker database. If another theme is already selected the script asks (`--force` replaces it without asking).
- A foreign `custom.css` is not overwritten without `--force` (the old one is kept as `.bak-<date>`). The font loads from Google Fonts; offline the default font stays.
- If the logo does not show (Moonraker requires authorization), run with `--logo-copy`; repeat after a Fluidd update.
- Reload the browser tab afterwards (Ctrl+F5). Options: `--no-activate`, `--dry-run`, `--uninstall`.

## KlipperScreen

`install_klipperscreen_theme.sh` (called by the installer when `~/KlipperScreen` exists; skip with `--skip-theme`) installs the "vostok" theme on the touchscreen: the site palette, the K3D mark on the splash screen, Tektur font in headings.

- `~/KlipperScreen/styles/vostok` is assembled from the `material-dark` icons plus our `style.css`, `style.conf` and `klipper.svg` (from `klipperscreen-theme/`). It is untracked by git, but KlipperScreen updates through Moonraker leave it alone.
- The Tektur font (OFL) goes to `~/.local/share/fonts` without sudo.
- `theme = vostok` is written to `KlipperScreen.conf` (backup `.bak-<date>`; if a theme was already picked on the screen, the machine-written block is edited). If another theme is selected the script asks (`--force` replaces it without asking). A foreign `styles/vostok` directory is not overwritten without `--force`.
- Then restart KlipperScreen: `sudo systemctl restart KlipperScreen`. After a KlipperScreen update run the script again to refresh the icons. Options: `--ks-dir`, `--printer-data`, `--no-activate`, `--dry-run`, `--uninstall`.
