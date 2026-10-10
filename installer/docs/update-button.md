# Кнопка обновления

🇷🇺 Русский | [🇬🇧 English](update-button.en.md)

[← К оглавлению](../README.md)

В Fluidd: ⏻ (вверху справа) → `mcu-update` → Start. Скрипт обновит ветку Klipper (`git fast-forward`, без KIAUH и sudo-пароля), соберёт прошивки, прошьёт все платы через katapult (USB и CAN; Octopus-мост последним) и проверит, что версии прошивок совпадают с хостом. Если обновлений нет, напишет «всё актуально». Лог: `~/printer_data/logs/klipper_mcu_update.log`.

Из терминала:

```bash
./update_klipper_mcu.sh --list                    # что найдено, ничего не меняет
./update_klipper_mcu.sh                           # обновить хост (KIAUH), собрать и прошить
./update_klipper_mcu.sh --no-update --force-flash # перепрошить текущей версией
```

**Не нажимайте Stop** на `mcu-update` во время прошивки. Кнопку можно поставить и отдельно, без установщика: `./install_fluidd_button.sh` (`--dry-run`, `--uninstall`). Форк Klipper нельзя обновить штатной кнопкой Update Manager, поэтому и нужна эта: после обновления хоста прошивки плат обязательно обновить, иначе Klipper не запустится (`MCU Protocol error`).
