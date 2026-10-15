# MAP: функция bash → Python

Чек-лист переноса. Колонка «Python» заполняет агент-владелец (`модуль.функция`), «статус»: todo | done | dropped(причина). Ревьюер R сверяет по этой таблице, что ни одна ветвь не потеряна.

## install_vostok.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `usage` | 104 |  | todo |
| `parse_args` | 153 |  | todo |
| `pause_hw` | 198 |  | todo |
| `run` | 211 |  | todo |
| `start_sudo` | 215 |  | todo |
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
| `log_to_file` | 80 |  | todo |
| `info` | 84 |  | todo |
| `ok` | 85 |  | todo |
| `warn` | 86 |  | todo |
| `die` | 87 |  | todo |
| `step` | 88 |  | todo |
| `usage` | 90 |  | todo |
| `confirm` | 114 |  | todo |
| `mr_get` | 146 |  | todo |
| `json_get` | 149 |  | todo |
| `check_moonraker` | 158 |  | todo |
| `check_not_printing` | 170 |  | todo |
| `preflight` | 182 |  | todo |
| `by_id_chip` | 230 |  | todo |
| `by_id_serial` | 231 |  | todo |
| `cfg_mcus` | 234 |  | todo |
| `cfg_mcu_versions` | 250 |  | todo |
| `add_mcu` | 269 |  | todo |
| `devices_lookup` | 297 |  | todo |
| `can_iface_up` | 302 |  | todo |
| `add_can_mcu` | 304 |  | todo |
| `discover_mcus` | 327 |  | todo |
| `host_version` | 374 |  | todo |
| `norm_version` | 376 |  | todo |
| `state_get` | 378 |  | todo |
| `state_set` | 379 |  | todo |
| `print_mcus` | 387 |  | todo |
| `pending_commits` | 421 |  | todo |
| `post_update_checks` | 427 |  | todo |
| `update_host_git` | 445 |  | todo |
| `update_host` | 473 |  | todo |
| `build_firmware` | 493 |  | todo |
| `klipper_units` | 518 |  | todo |
| `sctl` | 524 |  | todo |
| `can_manage_services` | 530 |  | todo |
| `services` | 535 |  | todo |
| `wait_for_device` | 547 |  | todo |
| `flash_can` | 559 |  | todo |
| `flash_all` | 588 |  | todo |
| `wait_for_klipper` | 634 |  | todo |
| `verify_versions` | 654 |  | todo |
| `main` | 681 |  | todo |

## lib/vostok_config.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `have_tty` | 28 |  | todo |
| `need_tty` | 29 |  | todo |
| `ask_yn` | 32 |  | todo |
| `ask_choice` | 43 |  | todo |
| `prev_keys` | 64 |  | todo |
| `byid_find` | 71 |  | todo |
| `dfu_count` | 77 |  | todo |
| `dfu_family` | 80 |  | todo |
| `family_name` | 92 |  | todo |
| `uid_addr` | 104 |  | todo |
| `dfu_read_uid` | 112 |  | todo |
| `can_uuid_from_serial` | 126 |  | todo |
| `bridge_usb_serial` | 131 |  | todo |
| `show_usb_state` | 140 |  | todo |
| `mb` | 158 |  | todo |
| `set_main_board` | 161 |  | todo |
| `main_boards_hint` | 167 |  | todo |
| `main_board_from_opt` | 177 |  | todo |
| `print_boards` | 186 |  | todo |
| `prev_main_board` | 200 |  | todo |
| `main_candidates` | 214 |  | todo |
| `ask_board` | 235 |  | todo |
| `detect_main_board` | 249 |  | todo |
| `check_main_bridge` | 284 |  | todo |
| `detect_hardware` | 290 |  | todo |
| `main_label` | 334 |  | todo |
| `main_short` | 336 |  | todo |
| `alps_side` | 337 |  | todo |
| `head_board_id` | 340 |  | todo |
| `hb` | 345 |  | todo |
| `set_head_names` | 346 |  | todo |
| `head_side` | 352 |  | todo |
| `head_label` | 353 |  | todo |
| `head_chip` | 354 |  | todo |
| `head_cfg_name` | 355 |  | todo |
| `head_dfu_hint` | 359 |  | todo |
| `klipper_cfg_for_main` | 361 |  | todo |
| `katapult_cfg_for_main` | 364 |  | todo |
| `drv_pick` | 381 |  | todo |
| `drivers_wizard` | 391 |  | todo |
| `stock_electronics` | 425 |  | todo |
| `elec_named_board` | 437 |  | todo |
| `el_for_board` | 449 |  | todo |
| `cfg_state` | 472 |  | todo |
| `find_reference` | 479 |  | todo |
| `gen_custom_electronics` | 508 |  | todo |
| `print_gen_warnings` | 554 |  | todo |
| `merge_mcus_into_cfg` | 577 |  | todo |
| `el_matches` | 608 |  | todo |
| `pick_electronics` | 618 |  | todo |
| `sync_head_names` | 694 |  | todo |
| `mcu_blocks` | 708 |  | todo |
| `local_cfg_root` | 725 |  | todo |
| `stage_config` | 736 |  | todo |
| `report_pin_conflicts` | 884 |  | todo |
| `module_state` | 894 |  | todo |
| `module_wanted` | 901 |  | todo |
| `module_add_include` | 915 |  | todo |
| `stage_modules` | 929 |  | todo |

## lib/boards.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `_board_err` | 30 |  | todo |
| `_board_file` | 32 |  | todo |
| `_board_parse` | 39 |  | todo |
| `_board_parse_file` | 52 |  | todo |
| `boards_preload` | 87 |  | todo |
| `board_load` | 96 |  | todo |
| `board_field` | 104 |  | todo |
| `boards_list` | 109 |  | todo |
| `board_resolve` | 119 |  | todo |
| `_boards_by` | 131 |  | todo |
| `boards_for_chip` | 138 |  | todo |
| `boards_for_family` | 139 |  | todo |
| `board_has_bridge` | 141 |  | todo |
| `board_cfg` | 146 |  | todo |
| `board_by_cfg` | 159 |  | todo |

## configure_vostok.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `usage` | 36 |  | todo |
| `parse_args` | 66 |  | todo |
| `guess_main_board` | 95 |  | todo |
| `guess_from_printer_cfg` | 117 |  | todo |
| `collect_mcu_state` | 138 |  | todo |
| `main` | 177 |  | todo |

## install_fluidd_button.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 42 |  | todo |
| `ok` | 43 |  | todo |
| `warn` | 44 |  | todo |
| `die` | 45 |  | todo |
| `step` | 46 |  | todo |
| `usage` | 48 |  | todo |
| `confirm` | 67 |  | todo |
| `run` | 76 |  | todo |
| `render_unit` | 102 |  | todo |
| `can_manage_services` | 114 |  | todo |
| `restart_moonraker` | 118 |  | todo |

## install_fluidd_theme.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 37 |  | todo |
| `ok` | 38 |  | todo |
| `warn` | 39 |  | todo |
| `die` | 40 |  | todo |
| `step` | 41 |  | todo |
| `usage` | 43 |  | todo |
| `confirm` | 64 |  | todo |
| `py` | 100 |  | todo |
| `db_get_theme` | 103 |  | todo |
| `db_theme_logo` | 111 |  | todo |
| `is_ours` | 119 |  | todo |
| `edit_fluidd_cfg` | 122 |  | todo |
| `preset_json` | 140 |  | todo |

## install_klipperscreen_theme.sh

| bash-функция | строка | Python | статус |
|---|---|---|---|
| `info` | 39 |  | todo |
| `ok` | 40 |  | todo |
| `warn` | 41 |  | todo |
| `die` | 42 |  | todo |
| `step` | 43 |  | todo |
| `usage` | 45 |  | todo |
| `confirm` | 63 |  | todo |
| `py` | 95 |  | todo |
| `is_ours` | 98 |  | todo |
| `edit_ks_conf` | 103 |  | todo |
| `current_theme` | 145 |  | todo |

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
| `tools/gen_electronics.py` | `vostok/electronics.py` (A4) | todo |
| `tools/mcu_merge.py` | `vostok/cfgfile.py` (A1) | todo |
| `tools/pin_conflicts.py` | `vostok/cfgfile.py` (A1) | todo |
| `tools/can_uuid.py` | `vostok/electronics.py`/`hardware.py` (A1) | todo |

## Встроенный Python в bash (heredoc / py -c)

| где | куда | статус |
|---|---|---|
| `install_vostok.sh` kiauh_set_fork_repo | `host.py` (A5) | todo |
| `lib/vostok_config.sh` stage_config (правка printer.cfg) | `cfgfile.rewrite_printer_cfg` (A1) | todo |
| `update_klipper_mcu.sh` json_get/cfg_mcus/cfg_mcu_versions | `update.py` (A2) | todo |
| `install_fluidd_theme.sh` py -c (db_get_theme, edit_fluidd_cfg, preset_json) | `integrations.py` (A3) | todo |
| `install_klipperscreen_theme.sh` edit_ks_conf/current_theme | `integrations.py` (A3) | todo |
