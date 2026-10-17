# Распиновка плат

🇷🇺 Русский | [🇬🇧 English](README.en.md)

[← К оглавлению установщика](../README.md)

Картинки распиновки плат из реестра `../boards/*.board`. Установщик показывает путь и веб-ссылку на картинку платы там, где нужно сверить проводку: в плане установки для непроверенной платы, при входе в DFU, в предупреждениях конфигуратора (пустые пины, пересечения пинов) и в итоге установки. Если у платы картинки нет, показывается поле `DOC`.

Картинки принадлежат производителям плат и лежат здесь без изменений. Лицензия в их репозиториях не указана, поэтому они хранятся как справочный материал с указанием источника; если правообладатель против, напишите, файл будет удалён. Источник, коммит, лицензия и sha256 каждого файла: [SOURCES.tsv](SOURCES.tsv).

Веб-адрес берётся из `VOSTOK_PINOUT_URL` (по умолчанию `https://github.com/dmitry-sorkin/vostok_configuration/blob/main/installer/pinouts/`), его можно заменить адресом своего форка. Каталог можно подменить переменной `PINOUTS_DIR`.

## Какая плата — какие файлы

| Плата (id в `boards/`) | Файлы | Производитель, примечание |
|---|---|---|
| `octopus-pro-h723` | `BTT/Octopus_Pro/v1_1/pinout.jpg` | BIGTREETECH Octopus Pro V1.1. **Часть пинов изменена относительно v1.0** (HE0=PA0, HE2=PB0, Motor3-EN=PA2, RGB=PB10; на картинке Motor3-EN нет), установщик печатает это предупреждение рядом со ссылкой (поле `PINOUT_NOTE`); [список изменений BTT](https://github.com/bigtreetech/BIGTREETECH-OCTOPUS-Pro#changes-in-v11-compared-to-v10) |
| `octopus-pro-f446`, `octopus-pro-f429` | `BTT/Octopus_Pro/v1_0/pinout.pdf` | BIGTREETECH Octopus Pro, лёгкий (0,8 МБ) лист `Octopus Pro - PIN`. Ревизия по имени файла не подтверждена. Цветной лист V1.0 (16 МБ) не включён |
| `manta-m8p-v1.0` | `BTT/Manta_M8P/v1_0/pinout.png` | BIGTREETECH Manta M8P V1.0 |
| `manta-m8p-v1.1` | `BTT/Manta_M8P/v1_1/pinout.png` | BIGTREETECH Manta M8P V1.1 |
| `manta-m8p-v2.0` | `BTT/Manta_M8P/v2_0/pinout.png` | BIGTREETECH Manta M8P V2.0 |
| `ebb42` (EBB42 и EBB36) | `BTT/EBB/ebb42_v1_1_v1_2/pinout.png`, `BTT/EBB/ebb36_v1_1_v1_2/pinout.png` | BIGTREETECH EBB42 / EBB36 CAN V1.1 и V1.2 (лист ADXL345 не включён) |
| `spider-v2-f446` | `Fysetc/Spider/v2_3/pinout.jpg`, `Fysetc/Spider/v2_2/pinout.jpg` | Fysetc Spider v2.3 и v2.2 |
| `spider-v3-f446` | `Fysetc/Spider/v3_0/pinout.png` | Fysetc Spider v3.0 (картинка из README репозитория FYSETC-SPIDER, лежит на CDN) |
| `spider-v3-h723` | — | Отдельной распиновки H723 у Fysetc нет, совпадение пинов с листом v3.0 F446 не проверено: установщик показывает `DOC` |
| `h36-v2` | `Fysetc/H36/v2_0/pinout.pdf` | Fysetc H36 v2.0 |
| `h36-v1.3` | `Fysetc/H36/v1_3/schematic.pdf` | Fysetc H36 v1.3: **принципиальная схема**, а не картинка pinout (отдельного pinout для v1.3 нет) |
| `fly-c8` | `Mellow/FLY-C8/pinout.jpg` | Mellow FLY-C8 (в репозитории файл назван `.png`, но это JPEG) |
| `alps` | — | Официальной распиновки ALPS нет: установщик показывает `DOC` |
| `octopus-f446`, `octopus-f429` | `BTT/Octopus/v1_0_v1_1/pinout.jpg` | BIGTREETECH Octopus (не Pro) v1.0/v1.1; ревизия листа в файле не указана |
| `octopus-max-ez` | `BTT/Octopus_Max_EZ/v1_0/pinout.png` | BIGTREETECH Octopus Max EZ V1.0 |
| `kraken` | `BTT/Kraken/v1_0/pinout.png` | BIGTREETECH Kraken V1.0 (v1.1 отличается только Rsense драйверов) |
| `ebb36-v1.0` | `BTT/EBB/ebb36_v1_0/pinout.png`, `BTT/EBB/ebb42_v1_0/pinout.png` | BIGTREETECH EBB36 / EBB42 CAN V1.0 (F072) |
| `ebb-gen2` | `BTT/EBB/ebb36_gen2/pinout.jpg`, `BTT/EBB/ebb42_gen2/pinout.jpg` | BIGTREETECH EBB36 / EBB42 Gen2, английская версия листа |
| `mks-monster8-v2` | `MKS/Monster8/v2_0/pinout.pdf` | MKS Monster8 V2.0_003 (лицензия репозитория GPL-3.0) |
| `ldo-leviathan-v1.2` | `LDO/Leviathan/v1_2/pinout.jpg` | LDO Leviathan: таблица назначения пинов, ревизия листа не указана (лицензия репозитория GPL-3.0) |
| `fly-super8` | `Mellow/FLY-Super8/pinout.jpg` | Mellow FLY Super8 (в репозитории файл назван `.png`, но это JPEG; на листе надпись Super v1.3) |
| `fly-super8-pro-h723` | `Mellow/FLY-Super8-Pro/schematic.pdf` | Mellow FLY Super8 Pro: **принципиальная схема**, листа pinout у Mellow нет. **На схеме МК STM32H743 и кварц 8 МГц, в документации H723 и 25 МГц**: сверьте маркировку чипа на плате до прошивки |
| `sht36-v2` | `Mellow/FLY-SHT36/v2_0/schematic.pdf`, `Mellow/FLY-SHT42/schematic.pdf` | Mellow FLY SHT36 v2 и SHT42: **принципиальные схемы**, листа pinout нет |

## Схемы подключения VOSTOK

Схемы проводки (куда что подключается в принтере) здесь не хранятся: они есть в гайде на сайте — <https://k3d.tech/vostok/manual/electronics/wiring/>.

## Как добавить плату

1. Скачайте официальный лист производителя из репозитория (не из сторонних сборников), проверьте `file` и ревизию платы на картинке. Файлы больше 3 МБ не кладите: выберите облегчённый лист или дайте ссылку в `DOC`.
2. Положите файл в `<Производитель>/<Плата>/<ревизия>/pinout.<расширение>` (несколько листов — `pinout_1.png`, `pinout_2.png`). Формат не конвертируйте.
3. Добавьте строку в `SOURCES.tsv` (колонки: path, board_id, source_url, permalink на коммит, license или «не указана», sha256, size, note); `sha256sum файл`.
4. Впишите путь в поле `PINOUT` файла `../boards/<id>.board` (несколько — через пробел) и добавьте плату в таблицу выше и в `README.en.md`.
5. Проверьте: `python3 -m unittest discover installer/tests` (тест `test_pinouts` сверяет файлы, `SOURCES.tsv`, `PINOUT` и README). Платы без картинки перечислены в тесте явно.
