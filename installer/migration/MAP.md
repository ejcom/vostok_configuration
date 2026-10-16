# MAP: функция bash → Python

Чек-лист переноса. Колонка «Python» заполняет агент-владелец (`модуль.функция`), «статус»: todo | done | dropped(причина). Ревьюер R сверяет по этой таблице, что ни одна ветвь не потеряна.

## install_vostok.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `usage` | 104 |  | todo |
| `parse_args` | 153 |  | todo |
| `pause_hw` | 198 | ui.pause_hw (ответ возвращается строкой, TMP_ANS не нужен) | done |
| `run` | 211 | system.Runner.run | done |
| `start_sudo` | 215 | system.Runner.sudo_keepalive | done |
| `cleanup` | 224 |  | todo |
| `stage_preflight` | 236 |  | todo |
| `env_item` | 264 |  | todo |
| `env_conclude` | 273 |  | todo |
| `hw_steps_planned` | 282 |  | todo |
| `check_dialout` | 284 |  | todo |
| `check_bootstrap` | 297 |  | todo |
| `check_tools` | 335 |  | todo |
| `kernel_can_support` | 369 |  | todo |
| `check_hw_requirements` | 388 |  | todo |
| `stage_packages` | 409 |  | todo |
| `kiauh_set_fork_repo` | 432 |  | todo |
| `klipper_is_fork` | 459 |  | todo |
| `switch_klipper_to_fork` | 465 |  | todo |
| `kiauh_install` | 478 |  | todo |
| `stage_software` | 483 |  | todo |
| `choose_heads_flash` | 535 |  | todo |
| `print_plan` | 555 |  | todo |
| `stage_can` | 594 |  | todo |
| `bring_up_can` | 625 |  | todo |
| `check_can_health` | 640 |  | todo |
| `build_katapult` | 655 |  | todo |
| `wait_dfu` | 673 |  | todo |
| `dfu_run` | 706 |  | todo |
| `dfu_flash_katapult` | 718 |  | todo |
| `wait_new_katapult` | 741 |  | todo |
| `snapshot_katapult` | 754 |  | todo |
| `katapult_devices` | 758 |  | todo |
| `pick_katapult` | 761 |  | todo |
| `enter_katapult` | 772 |  | todo |
| `build_fw_safe` | 821 |  | todo |
| `flash_klipper_via_katapult` | 834 |  | todo |
| `dfu_flash_klipper` | 878 |  | todo |
| `board_opt_skipped` | 962 |  | todo |
| `version_ok` | 970 |  | todo |
| `flash_menu` | 976 |  | todo |
| `flash_board` | 996 |  | todo |
| `alps_candidates` | 1018 |  | todo |
| `alps_try_skip` | 1030 |  | todo |
| `try_alps` | 1051 |  | todo |
| `stage_flash_alps` | 1076 |  | todo |
| `can_uuids` | 1092 |  | todo |
| `heads_try_skip` | 1104 |  | todo |
| `head_dfu_all` | 1136 |  | todo |
| `try_head_katapult` | 1143 |  | todo |
| `stage_flash_heads_katapult` | 1164 |  | todo |
| `try_head_dfu` | 1185 |  | todo |
| `stage_flash_heads_dfu` | 1204 |  | todo |
| `set_bridge_uuid` | 1222 |  | todo |
| `stage_heads_uuid_check` | 1238 |  | todo |
| `try_head_klipper` | 1258 |  | todo |
| `stage_flash_heads_klipper` | 1307 |  | todo |
| `main_dfu_std` | 1364 |  | todo |
| `main_dfu_short` | 1366 |  | todo |
| `main_dfu_enter_text` | 1372 |  | todo |
| `main_dfu_after_text` | 1377 |  | todo |
| `main_dfu_mode_text` | 1384 |  | todo |
| `main_dfu_klipper_how` | 1389 |  | todo |
| `main_try_skip` | 1395 |  | todo |
| `try_main` | 1431 |  | todo |
| `stage_flash_main` | 1459 |  | todo |
| `stage_flash` | 1482 |  | todo |
| `save_devices` | 1507 |  | todo |
| `wait_moonraker` | 1534 |  | todo |
| `stage_start_klipper` | 1546 |  | todo |
| `stage_button` | 1561 |  | todo |
| `stage_theme` | 1568 |  | todo |
| `print_summary` | 1584 |  | todo |
| `write_uuid_to_cfg` | 1617 |  | todo |
| `check_can_uuids` | 1638 |  | todo |
| `check_can_main` | 1713 |  | todo |
| `install_main` | 1763 |  | todo |

## update_klipper_mcu.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `log_to_file` | 80 | ui.log | done |
| `info` | 84 | ui.info | done |
| `ok` | 85 | ui.ok | done |
| `warn` | 86 | ui.warn | done |
| `die` | 87 | ui.die (VostokError; печать в cli.main) | done |
| `step` | 88 | ui.step | done |
| `usage` | 90 | update.USAGE (+ update.parse_args) | done |
| `confirm` | 114 | ui.confirm | done |
| `mr_get` | 146 | update.Moonraker.fetch (urllib) | done |
| `json_get` | 149 | update.Moonraker.get_json/status (JSON без eval) | done |
| `check_moonraker` | 158 | update.Updater.check_moonraker | done |
| `check_not_printing` | 170 | update.Updater.check_not_printing | done |
| `preflight` | 182 | update.Updater.preflight | done |
| `by_id_chip` | 230 | hardware.by_id_chip | done |
| `by_id_serial` | 231 | hardware.by_id_serial | done |
| `cfg_mcus` | 234 | update.Moonraker.mcu_sections | done |
| `cfg_mcu_versions` | 250 | update.Moonraker.mcu_versions | done |
| `add_mcu` | 269 | update.Updater.add_mcu (Mcu - dataclass) | done |
| `devices_lookup` | 297 | state.DevicesFile.lookup | done |
| `can_iface_up` | 302 | hardware.can_iface_up | done |
| `add_can_mcu` | 304 | update.Updater.add_can_mcu | done |
| `discover_mcus` | 327 | update.Updater.discover_mcus | done |
| `host_version` | 374 | firmware.host_version | done |
| `norm_version` | 376 | firmware.norm_version | done |
| `state_get` | 378 | state.FlashedLog.get | done |
| `state_set` | 379 | state.FlashedLog.set | done |
| `print_mcus` | 387 | update.Updater.print_mcus | done |
| `pending_commits` | 421 | update.Updater.pending_commits | done |
| `post_update_checks` | 427 | update.Updater.post_update_checks | done |
| `update_host_git` | 445 | update.Updater.update_host_git | done |
| `update_host` | 473 | update.Updater.update_host | done |
| `build_firmware` | 493 | firmware.build_firmware | done |
| `klipper_units` | 518 | update.Updater.klipper_units | done |
| `sctl` | 524 | system.Runner.systemctl | done |
| `can_manage_services` | 530 | system.can_manage_services | done |
| `services` | 535 | update.Updater.services | done |
| `wait_for_device` | 547 | hardware.wait_for_device | done |
| `flash_can` | 559 | update.Updater.flash_can (+ firmware.flash_can_node/request_bootloader_can, hardware.wait_for_katapult) | done |
| `flash_all` | 588 | update.Updater.flash_all | done |
| `wait_for_klipper` | 634 | update.Updater.wait_for_klipper | done |
| `verify_versions` | 654 | update.Updater.verify_versions | done |
| `main` | 681 | update.Updater.run / update.main | done |

## lib/vostok_config.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `have_tty` | 28 | ui.have_tty | done |
| `need_tty` | 29 | ui.need_tty | done |
| `ask_yn` | 32 | ui.ask_yn | done |
| `ask_choice` | 43 | ui.ask_choice | done |
| `prev_keys` | 64 | Configurator.prev_keys | done |
| `byid_find` | 71 | configurator.byid_find | done |
| `dfu_count` | 77 | configurator.dfu_count | done |
| `dfu_family` | 80 | configurator.dfu_family | done |
| `family_name` | 92 |  | todo (только install: A5; hardware.py) |
| `uid_addr` | 104 |  | todo (только install: A5; hardware.py) |
| `dfu_read_uid` | 112 |  | todo (только install: A5; hardware.py) |
| `can_uuid_from_serial` | 126 | can_uuid.can_uuid(bytes.fromhex(serial)) | done |
| `bridge_usb_serial` | 131 |  | todo (только install: A5; hardware.py) |
| `show_usb_state` | 140 | configurator.show_usb_state | done |
| `mb` | 158 | Configurator._board_field / Hardware.board.field | done |
| `set_main_board` | 161 | Hardware.set_main_board (чип - Hardware.main) | done |
| `main_boards_hint` | 167 | HardwareDetector.main_boards_hint | done |
| `main_board_from_opt` | 177 | HardwareDetector.board_from_opt | done |
| `print_boards` | 186 |  | todo (--list-boards install: A5) |
| `prev_main_board` | 200 | HardwareDetector.prev_main_board | done |
| `main_candidates` | 214 | HardwareDetector.main_candidates + configurator.rank_main_boards (точка расширения под board_rank) | done |
| `ask_board` | 235 | HardwareDetector.ask_board | done |
| `detect_main_board` | 249 | HardwareDetector.detect_main_board | done |
| `check_main_bridge` | 284 | HardwareDetector.check_main_bridge | done |
| `detect_hardware` | 290 | HardwareDetector.detect (+ detect_heads, detect_alps) -> Hardware | done |
| `main_label` | 334 | Hardware.main_label | done |
| `main_short` | 336 | Hardware.main_short | done |
| `alps_side` | 337 | Hardware.alps_side | done |
| `head_board_id` | 340 | Hardware.head_board_id | done |
| `hb` | 345 | Hardware.head_field | done |
| `set_head_names` | 346 | Hardware.set_head_names | done |
| `head_side` | 352 | Hardware.head_side | done |
| `head_label` | 353 | Hardware.head_label | done |
| `head_chip` | 354 | Hardware.head_chip | done |
| `head_cfg_name` | 355 | Hardware.head_cfg_name | done |
| `head_dfu_hint` | 359 | Hardware.head_dfu_hint | done |
| `klipper_cfg_for_main` | 361 | Hardware.klipper_cfg | done |
| `katapult_cfg_for_main` | 364 | Hardware.katapult_cfg | done |
| `drv_pick` | 381 | Configurator.drv_pick | done |
| `drivers_wizard` | 391 | Configurator.drivers_wizard | done |
| `stock_electronics` | 425 | Configurator.stock_electronics | done |
| `elec_named_board` | 437 | Configurator.elec_named_board | done |
| `el_for_board` | 449 | Configurator.el_for_board | done |
| `cfg_state` | 472 | cfgfile.cfg_state | done |
| `find_reference` | 479 | Configurator.find_reference | done |
| `gen_custom_electronics` | 508 | Configurator.gen_custom_electronics (-> electronics.Generator) | done |
| `print_gen_warnings` | 554 | Configurator.print_gen_warnings | done |
| `merge_mcus_into_cfg` | 577 | cfgfile.merge_mcus (логика и .bak; сообщения info/ok/warn по Result - у вызывающего, A4) | done |
| `el_matches` | 608 | Configurator.el_matches | done |
| `pick_electronics` | 618 | Configurator.pick_electronics (+ _ask_source) | done |
| `sync_head_names` | 694 | Configurator.sync_head_names | done |
| `mcu_blocks` | 708 | configurator.mcu_blocks | done |
| `local_cfg_root` | 725 | Configurator.local_cfg_root | done |
| `stage_config` | 736 | Configurator.stage_config (+ _config_root, _write_config, _finish_config) | done |
| `report_pin_conflicts` | 884 | cfgfile.pin_conflicts (вывод предупреждения - у вызывающего, A4) | done |
| `module_state` | 894 | cfgfile.module_state | done |
| `module_wanted` | 901 | Configurator.module_wanted | done |
| `module_add_include` | 915 | cfgfile.module_add_include | done |
| `stage_modules` | 929 | Configurator.stage_modules (+ new_module_conflicts) | done |

## lib/boards.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `_board_err` | 30 | boards.BoardError (текст `boards: …`) | done |
| `_board_file` | 32 | boards.Registry.get (путь <boards_dir>/<id>.board) | done |
| `_board_parse` | 39 | boards.Registry.get (кэш в Registry) | done |
| `_board_parse_file` | 52 | boards.parse_board_file | done |
| `boards_preload` | 87 |  | dropped(ленивый кэш Registry, предзагрузка не нужна) |
| `board_load` | 96 | boards.Registry.get -> Board | done |
| `board_field` | 104 | boards.Board.field | done |
| `boards_list` | 109 | boards.Registry.list / ids | done |
| `board_resolve` | 119 | boards.Registry.resolve | done |
| `_boards_by` | 131 | boards.Registry._by | done |
| `boards_for_chip` | 138 | boards.Registry.for_chip | done |
| `boards_for_family` | 139 | boards.Registry.for_family | done |
| `board_has_bridge` | 141 | boards.Registry.has_bridge | done |
| `board_cfg` | 146 | boards.Registry.cfg_path | done |
| `board_by_cfg` | 159 | boards.Registry.by_cfg | done |

## configure_vostok.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `usage` | 36 | configurator.USAGE | done |
| `parse_args` | 66 | configurator.parse_args | done |
| `guess_main_board` | 95 | Configurator.guess_main_board (порядок - rank_main_boards) | done |
| `guess_from_printer_cfg` | 117 | Configurator.guess_from_printer_cfg | done |
| `collect_mcu_state` | 138 | Configurator.collect_mcu_state | done |
| `main` | 177 | configurator.main (команда configure) | done |

## install_fluidd_button.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 42 | ui.info | done |
| `ok` | 43 | ui.ok | done |
| `warn` | 44 | ui.warn | done |
| `die` | 45 | ui.die (VostokError; печать в cli.main) | done |
| `step` | 46 | ui.step | done |
| `usage` | 48 | integrations.USAGE_BUTTON | done |
| `confirm` | 67 | ui.confirm | done |
| `run` | 76 | system.Runner.run | done |
| `render_unit` | 102 | integrations.FluiddButton.render_unit | done |
| `can_manage_services` | 114 | system.can_manage_services(allow_sudo=False) | done |
| `restart_moonraker` | 118 | integrations.FluiddButton.restart_moonraker (Runner.systemctl) | done |

## install_fluidd_theme.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 37 | ui.info | done |
| `ok` | 38 | ui.ok | done |
| `warn` | 39 | ui.warn | done |
| `die` | 40 | ui.die (VostokError; печать в cli.main) | done |
| `step` | 41 | ui.step | done |
| `usage` | 43 | integrations.USAGE_THEME | done |
| `confirm` | 64 | ui.confirm(need=False) | done |
| `py` | 100 | не нужен (json в stdlib) | done |
| `db_get_theme` | 103 | integrations.FluiddTheme.db_get_theme (urllib вместо curl) | done |
| `db_theme_logo` | 111 | integrations.FluiddTheme.db_theme_logo | done |
| `is_ours` | 119 | integrations.FluiddTheme.is_ours | done |
| `edit_fluidd_cfg` | 122 | integrations.FluiddTheme.edit_fluidd_cfg | done |
| `preset_json` | 140 | integrations.FluiddTheme.preset | done |

## install_klipperscreen_theme.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 39 | ui.info | done |
| `ok` | 40 | ui.ok | done |
| `warn` | 41 | ui.warn | done |
| `die` | 42 | ui.die (VostokError; печать в cli.main) | done |
| `step` | 43 | ui.step | done |
| `usage` | 45 | integrations.USAGE_KS | done |
| `confirm` | 63 | ui.confirm(need=False) | done |
| `py` | 95 | не нужен (stdlib) | done |
| `is_ours` | 98 | integrations.KlipperScreenTheme.is_ours | done |
| `edit_ks_conf` | 103 | integrations.edit_ks_conf | done |
| `current_theme` | 145 | integrations.current_ks_theme | done |

## tools/gen_configs.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `gen` | 54 |  | todo |
| `clock_hz` | 73 |  | todo |
| `hex_addr` | 74 |  | todo |
| `can_lines` | 77 |  | todo |
| `gen_klipper_cfg` | 91 |  | todo |
| `gen_katapult_cfg` | 107 |  | todo |
| `gen_all` | 126 |  | todo |
| `sig` | 136 |  | todo |

## Python-утилиты (уже на Python, переносятся в пакет)

| файл | куда | статус |
|---|---|---|
| `tools/gen_electronics.py` | `vostok/electronics.py` (A4): Generator/GenOptions/GenResult, main() с прежними флагами и протоколом NAME/WARN/FILL/EMPTY | done (старый файл пока не тронут) |
| `tools/mcu_merge.py` | `vostok/cfgfile.py` (A1): list_mcus, merge_mcus, set_canbus_uuid | done (старый файл пока не тронут) |
| `tools/pin_conflicts.py` | `vostok/cfgfile.py` (A1): pin_conflicts | done (старый файл пока не тронут) |
| `tools/can_uuid.py` | `vostok/can_uuid.py` (A1, отдельный модуль, не electronics/hardware) | done (старый файл пока не тронут) |

## Встроенный Python в bash (heredoc / py -c)

| где | куда | статус |
|---|---|---|
| `install_vostok.sh` kiauh_set_fork_repo | `host.py` (A5) | todo |
| `lib/vostok_config.sh` stage_config (правка printer.cfg) | `cfgfile.rewrite_printer_cfg` / `rewrite_printer_text` (A1), вызывается из `Configurator._write_config` (A4) | done (heredoc в lib/vostok_config.sh остаётся для install_vostok.sh до A5) |
| `update_klipper_mcu.sh` json_get/cfg_mcus/cfg_mcu_versions | `update.Moonraker` (A2) | done |
| `install_fluidd_theme.sh` py -c (db_get_theme, edit_fluidd_cfg, preset_json) | `integrations.py` (A3) | done |
| `install_klipperscreen_theme.sh` edit_ks_conf/current_theme | `integrations.py` (A3) | done |
