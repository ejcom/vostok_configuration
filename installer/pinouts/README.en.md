# Board pinouts

[🇷🇺 Русский](README.md) | 🇬🇧 English

[← Installer index](../README.en.md)

Pinout images for the boards in the `../boards/*.board` registry. The installer prints the path and the web link of a board's image wherever you need to check the wiring: in the install plan for an unverified board, at DFU entry, in the configurator warnings (empty pins, pin conflicts) and in the final summary. If a board has no image, its `DOC` field is shown instead.

The images belong to the board manufacturers and are stored here unchanged. Their repositories do not state a licence, so they are kept as reference material with the source named; if a rights holder objects, tell us and the file will be removed. Source, commit, licence and sha256 of every file: [SOURCES.tsv](SOURCES.tsv).

The web address comes from `VOSTOK_PINOUT_URL` (default `https://github.com/dmitry-sorkin/vostok_configuration/blob/main/installer/pinouts/`); point it at your fork if needed. The directory can be overridden with `PINOUTS_DIR`.

## Board to files

| Board (id in `boards/`) | Files | Manufacturer, notes |
|---|---|---|
| `octopus-pro-h723` | `BTT/Octopus_Pro/v1_1/pinout.jpg` | BIGTREETECH Octopus Pro V1.1. **Some pins differ from v1.0** (HE0=PA0, HE2=PB0, Motor3-EN=PA2, RGB=PB10; Motor3-EN is not on the image); the installer prints this warning next to the link (the `PINOUT_NOTE` field); [BTT change list](https://github.com/bigtreetech/BIGTREETECH-OCTOPUS-Pro#changes-in-v11-compared-to-v10) |
| `octopus-pro-f446`, `octopus-pro-f429` | `BTT/Octopus_Pro/v1_0/pinout.pdf` | BIGTREETECH Octopus Pro, the light (0.8 MB) `Octopus Pro - PIN` sheet. The revision is not confirmed by the file name. The colour V1.0 sheet (16 MB) is not included |
| `manta-m8p-v1.0` | `BTT/Manta_M8P/v1_0/pinout.png` | BIGTREETECH Manta M8P V1.0 |
| `manta-m8p-v1.1` | `BTT/Manta_M8P/v1_1/pinout.png` | BIGTREETECH Manta M8P V1.1 |
| `manta-m8p-v2.0` | `BTT/Manta_M8P/v2_0/pinout.png` | BIGTREETECH Manta M8P V2.0 |
| `ebb42` (EBB42 and EBB36) | `BTT/EBB/ebb42_v1_1_v1_2/pinout.png`, `BTT/EBB/ebb36_v1_1_v1_2/pinout.png` | BIGTREETECH EBB42 / EBB36 CAN V1.1 and V1.2 (the ADXL345 sheet is not included) |
| `spider-v2-f446` | `Fysetc/Spider/v2_3/pinout.jpg`, `Fysetc/Spider/v2_2/pinout.jpg` | Fysetc Spider v2.3 and v2.2 |
| `spider-v3-f446` | `Fysetc/Spider/v3_0/pinout.png` | Fysetc Spider v3.0 (image from the FYSETC-SPIDER README, hosted on a CDN) |
| `spider-v3-h723` | — | Fysetc has no separate H723 pinout and the pins were not verified to match the v3.0 F446 sheet: the installer shows `DOC` |
| `h36-v2` | `Fysetc/H36/v2_0/pinout.pdf` | Fysetc H36 v2.0 |
| `h36-v1.3` | `Fysetc/H36/v1_3/schematic.pdf` | Fysetc H36 v1.3: a **schematic**, not a pinout image (there is no separate pinout for v1.3) |
| `fly-c8` | `Mellow/FLY-C8/pinout.jpg` | Mellow FLY-C8 (named `.png` upstream, but it is a JPEG) |
| `alps` | — | There is no official ALPS pinout: the installer shows `DOC` |
| `octopus-f446`, `octopus-f429` | `BTT/Octopus/v1_0_v1_1/pinout.jpg` | BIGTREETECH Octopus (non-Pro) v1.0/v1.1; the sheet revision is not stated in the file |
| `octopus-max-ez` | `BTT/Octopus_Max_EZ/v1_0/pinout.png` | BIGTREETECH Octopus Max EZ V1.0 |
| `kraken` | `BTT/Kraken/v1_0/pinout.png` | BIGTREETECH Kraken V1.0 (v1.1 differs only in driver Rsense) |
| `ebb36-v1.0` | `BTT/EBB/ebb36_v1_0/pinout.png`, `BTT/EBB/ebb42_v1_0/pinout.png` | BIGTREETECH EBB36 / EBB42 CAN V1.0 (F072) |
| `ebb-gen2` | `BTT/EBB/ebb36_gen2/pinout.jpg`, `BTT/EBB/ebb42_gen2/pinout.jpg` | BIGTREETECH EBB36 / EBB42 Gen2, English version of the sheet |
| `mks-monster8-v2` | `MKS/Monster8/v2_0/pinout.pdf` | MKS Monster8 V2.0_003 (repository licence GPL-3.0) |
| `ldo-leviathan-v1.2` | `LDO/Leviathan/v1_2/pinout.jpg` | LDO Leviathan: a pin assignment table, sheet revision not stated (repository licence GPL-3.0) |
| `fly-super8` | `Mellow/FLY-Super8/pinout.jpg` | Mellow FLY Super8 (named `.png` upstream, but it is a JPEG; the sheet says Super v1.3) |
| `fly-super8-pro-h723` | `Mellow/FLY-Super8-Pro/schematic.pdf` | Mellow FLY Super8 Pro: a **schematic**, Mellow has no pinout sheet. **The schematic shows an STM32H743 and an 8 MHz crystal, the documentation says H723 and 25 MHz**: check the chip marking on the board before flashing |
| `sht36-v2` | `Mellow/FLY-SHT36/v2_0/schematic.pdf`, `Mellow/FLY-SHT42/schematic.pdf` | Mellow FLY SHT36 v2 and SHT42: **schematics**, there is no pinout sheet |

## VOSTOK wiring diagrams

Wiring diagrams (what connects where in the printer) are not stored here: they are in the guide on the site — <https://k3d.tech/vostok/manual/electronics/wiring/>.

## How to add a board

1. Download the manufacturer's official sheet from its repository (not from third-party collections), check it with `file` and check the board revision shown on the image. Do not add files over 3 MB: pick a lighter sheet or put a link into `DOC`.
2. Put the file at `<Manufacturer>/<Board>/<revision>/pinout.<extension>` (several sheets: `pinout_1.png`, `pinout_2.png`). Do not convert the format.
3. Add a row to `SOURCES.tsv` (columns: path, board_id, source_url, permalink to the commit, license or "не указана" (not stated), sha256, size, note); use `sha256sum file`.
4. Put the path into the `PINOUT` field of `../boards/<id>.board` (several, separated by spaces) and add the board to the table above and in `README.md`.
5. Check with `python3 -m unittest discover installer/tests` (the `test_pinouts` test checks the files, `SOURCES.tsv`, `PINOUT` and both READMEs). Boards without an image are listed explicitly in the test.
