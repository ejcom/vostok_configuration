# Установщик VOSTOK

🇷🇺 Русский | [🇬🇧 English](README.en.md)

Скрипты, которые разворачивают VOSTOK на чистой системе по гайду [💾 Прошивка электроники](https://k3d.tech/vostok/manual/electronics/firmware/) и потом обновляют Klipper и прошивки плат одной кнопкой в Fluidd.

> ⚠️ Установщик прошивает платы и просит вручную переключать джамперы и кабели. Читайте подсказки на каждом шаге. Без `--dry-run` он меняет систему: ставит пакеты, службы и прошивки.

## Быстрый старт

Нужны Debian-подобная система (Armbian, Raspberry Pi OS, BTT Pi и т. п.), обычный пользователь с `sudo`, интернет и платы, подключённые по USB.

```bash
git clone https://github.com/dmitry-sorkin/vostok_configuration.git
cd vostok_configuration/installer

./install_vostok.sh --dry-run   # показать все шаги, ничего не меняя (по желанию)
./install_vostok.sh             # установка: ответьте на вопросы и следуйте подсказкам
```

Установщик сам определит платы, поставит ПО, прошьёт платы, соберёт конфиг принтера, поставит кнопку обновления и тему Fluidd. После установки сверьте `electronics_*.cfg` со своей проводкой и проверьте термисторы голов ([подробнее](docs/install.md)). Каталог клона должен остаться на месте: кнопка обновления запускает скрипты из него.

Главные платы: Octopus Pro (H723 — проверена; F446, F429), Manta M8P (v2.0 — проверена), Fysetc Spider, FLY-C8, Octopus (не Pro) и Max EZ, Kraken, LDO Leviathan, FLY Super8 / Super8 Pro, MKS Monster8 V2; выбор — `--main <id>`, список — `./install_vostok.sh --list-boards`. ⚠️ Остальные платы пока **не проверены на железе**; список непроверенного: [docs/hardware.md](docs/hardware.md#главные-платы).

## Содержание

| Раздел | О чём |
|---|---|
| [Платы и состав каталога](docs/hardware.md) | какие платы поддерживаются (реестр плат), что лежит в `installer/` |
| [Распиновка плат](pinouts/README.md) | картинки pinout по платам, источники, как добавить |
| [Требования и проверки](docs/requirements.md) | что проверяет скрипт перед установкой |
| [Установка](docs/install.md) | запуск, этапы установщика, опции `install_vostok.sh` |
| [Настройка конфига](docs/configure.md) | `configure_vostok.sh` отдельно от установки; полное описание: [CONFIGURATOR.md](CONFIGURATOR.md) |
| [Тема Fluidd и KlipperScreen](docs/theme.md) | оформление Fluidd и сенсорного экрана в стиле K3D VOSTOK |
| [Кнопка обновления](docs/update-button.md) | обновление Klipper и прошивок плат из Fluidd |
| [Если прошивка не удалась](docs/troubleshooting.md) | повтор, DFU, CAN, ручная прошивка |
| [Параметры сборки прошивок](docs/build-configs.md) | `configs/`, `devices.tsv` |
| [Что проверено](docs/tested.md) | что проверено на железе, что нет |
| [Удаление](docs/uninstall.md) | как убрать кнопку и тему |
| [История изменений](CHANGELOG.md) | что нового в каждой версии |
