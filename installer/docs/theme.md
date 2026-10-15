# Тема Fluidd

🇷🇺 Русский | [🇬🇧 English](theme.en.md)

[← К оглавлению](../README.md)

`install_fluidd_theme.sh` (его же вызывает установщик, пропуск: `--skip-theme`) оформляет Fluidd в стиле k3d.tech/vostok: бирюзовый цвет `#009B98`, знак K3D вместо логотипа Fluidd, шрифт Tektur в заголовках, фон и карточки в палитре сайта.

- Логотип и `custom.css` кладутся в `~/printer_data/config/.fluidd-theme/` (Fluidd подхватывает их сам, обновления Fluidd каталог не трогают).
- Пресет «K3D VOSTOK» добавляется в `~/fluidd/config.json` (он в `persistent_files` Update Manager), тема включается через базу Moonraker. Если в Fluidd уже выбрана другая тема, скрипт спросит (`--force` заменит без вопроса).
- Чужой `custom.css` не перезаписывается без `--force` (прежний сохраняется как `.bak-<дата>`). Шрифт грузится с Google Fonts, без интернета остаётся стандартный.
- Если логотип не показывается (Moonraker требует авторизацию), запустите с `--logo-copy`; после обновления Fluidd повторите.
- После установки обновите вкладку (Ctrl+F5). Опции: `--no-activate`, `--dry-run`, `--uninstall`.

## KlipperScreen

`install_klipperscreen_theme.sh` (установщик вызывает его, если есть `~/KlipperScreen`; пропуск: `--skip-theme`) ставит тему «vostok» на сенсорный экран: палитра сайта, знак K3D на заставке, шрифт Tektur в заголовках.

- Каталог `~/KlipperScreen/styles/vostok` собирается из иконок `material-dark` и наших `style.css`, `style.conf`, `klipper.svg` (из `klipperscreen-theme/`). Он не отслеживается git, но обновления KlipperScreen через Moonraker его не трогают.
- Шрифт Tektur (OFL) ставится в `~/.local/share/fonts` без sudo.
- В `KlipperScreen.conf` пишется `theme = vostok` (резервная копия `.bak-<дата>`; если тема уже выбрана через экран, правится машинный блок). Если выбрана другая тема, скрипт спросит (`--force` заменит без вопроса). Чужой каталог `styles/vostok` без `--force` не перезаписывается.
- Затем перезапустите KlipperScreen: `sudo systemctl restart KlipperScreen`. После обновления KlipperScreen запустите скрипт ещё раз, чтобы обновить иконки. Опции: `--ks-dir`, `--printer-data`, `--no-activate`, `--dry-run`, `--uninstall`.
