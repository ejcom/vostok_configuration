# История изменений установщика VOSTOK

🇷🇺 Русский | [🇬🇧 English](CHANGELOG.en.md)

Текущая версия записана в файле `VERSION` (`-V`/`--version` у всех скриптов). Описание: [README.md](README.md).

## 1.2b — 2026-10-10

- Тема Fluidd K3D VOSTOK: `install_fluidd_theme.sh` и `fluidd-theme/` (бирюзовый `#009B98`, логотип K3D, шрифт Tektur, пресет в базе Moonraker).
- Установщик ставит тему отдельным этапом, пропуск: `--skip-theme`.
- Опции темы: `--force`, `--logo-copy`, `--no-activate`, `--dry-run`, `--uninstall`.

## 1.2a — 2026-10-09

- Автономный `configure_vostok.sh` и общая библиотека `lib/vostok_config.sh`: настройка конфига отдельно от установки.
- Генерация `electronics_*.cfg` под ваши платы и драйверы (`templates/`, `tools/gen_electronics.py`), дописывание `[mcu]` (`tools/mcu_merge.py`), поиск пересечений пинов (`tools/pin_conflicts.py`), дополнительные модули (`chamber_heater.cfg`).
- Чистая установка берёт всё из main, а существующий конфиг VOSTOK сохраняется: заменяются только `electronics_*.cfg`, `[mcu]` и include, а `printer_base.cfg`, `chamber_heater.cfg` и `SAVE_CONFIG` остаются.
- Исправлено: замена `[mcu]` съедала блок `SAVE_CONFIG`.
- В меню плат голов добавлен пункт «нет (пассивная плата, например fly miniAB)».

## 1.0a — 2026-10-09

Первая версия с номером. В неё вошло всё, что было сделано до введения версий (с 2026-10-08).

- `install_vostok.sh`: пакеты, KIAUH, форк Klipper, Moonraker, Fluidd, katapult, прошивка ALPS, плат голов (H36 v1.3/v2, EBB42) и Octopus Pro (H723/F446) по USB или через мост USB-CAN, запись `printer.cfg`.
- `update_klipper_mcu.sh` и кнопка `mcu-update` в меню питания Fluidd: обновление Klipper и перепрошивка плат.
- Проверки окружения перед установкой и прошивкой (sudo, место, инструменты, поддержка CAN в ядре).
- Прошивка не прерывается на ошибке одной платы: меню «повторить / через DFU / Klipper напрямую по DFU / пропустить / прервать».
- Опции `--skip-board` и `--reflash`, автопропуск плат с актуальным Klipper.
- Непрошитые платы получают в `printer.cfg` заглушку `ЗАПОЛНИТЕ`, в конце выводится список проблемных плат.
- Версионирование: файл `VERSION` и опция `-V`/`--version`.
