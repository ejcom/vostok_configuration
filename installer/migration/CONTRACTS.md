# CONTRACTS: публичные интерфейсы модулей `installer/vostok/`

Фиксирует A1 (сигнатуры с докстрингами отдельным первым коммитом). Остальные агенты не меняют чужие модули; нужна правка — записать запрос в `STATUS.md` («Решения»), изменение вносит оркестратор здесь. Python ≥ 3.8, stdlib.

## ui
- `set_options(yes: bool, dry_run: bool, log_file: Path | None)` (состояние в `ui.opts`); `info/ok/warn/step(msg)`; `ask_yn(q, default="n") -> bool`; `ask_choice(q, default, options) -> str`; `pause_hw(msg, allow_skip=False) -> str` (ответ пользователя); `have_tty()`.
- Исключение `UserAbort(VostokError)`. Тексты, цвета и формат лога — как в bash (`ВНИМАНИЕ:`/`ОШИБКА:`, `== шаг ==`).

## system
- `Runner.run(cmd, *, sudo=False, check=True, capture=False, tee=False, env=None) -> CompletedProcess`; dry-run печатает `[dry-run] …` и возвращает успех. Единственное место с `subprocess`.
- Методы `Runner.systemctl(action, unit)` и `Runner.sudo_keepalive()` (контекстный менеджер); функция модуля `can_manage_services(allow_sudo)`.
- Исключение `system.CommandError(VostokError)`.

## boards
- `Board` (dataclass, поля `.board`: label, role, chip, family, mach, clock, app_offset, usb, can, can_kind, initial_pins, …, verified, doc, note); `Registry(boards_dir)`: `get(id)`, `resolve(name)`, `list(role=None)`, `for_chip(chip, role=None)`, `for_family(fam, role=None)`, `by_cfg(path) -> (id, kind)`, `cfg_path(id, kind)`, `has_bridge(id)`. Формат `.board` не меняется.

## state
- `DevicesFile(path)`: `load() -> list[Device]`, `save(devices)`, `lookup(key)`; `Device(key, cfg, role)`.
- `FlashedLog(path)`: `get(key)`, `set(key, version)`.

## cfgfile
- `list_mcus`, `Result.line()` (формат OK/ADD/DIFF/TODO, SET/SAME/NOSECTION, CONFLICT как в bash), `backup_file`; `merge_mcus` сама делает `.bak` (только если есть ADD) и не возвращает его путь (A4: брать путь через `backup_file`, если нужна строка «Резервная копия»); `can_uuid` — отдельный модуль `vostok/can_uuid.py`.
- `read_with_includes(path)`, `sections(text)`, `merge_mcus(cfg_path, blocks_text, dry=False) -> list[Result]`, `set_canbus_uuid(cfg_path, name, uuid, force=False)`, `pin_conflicts(cfg_path)`, `cfg_state(path) -> none|blank|foreign|vostok`, `rewrite_printer_cfg(path, electronics, blocks_text)`, `module_state/module_add_include`, `atomic_write(path, text, backup=True)`.

## Ошибки
- `boards.BoardError(VostokError)`; `VostokError`, `FlashError`, `UserAbort` определены в `vostok/__init__.py`, `ui` их реэкспортирует.
- `VostokError` (сообщение показывается пользователем, код выхода 1), `FlashError(VostokError)`, `UserAbort(VostokError)`.

## cli
- `COMMANDS: dict[str, Callable[[list[str]], int]]` — `update`, `install`, `configure`, `button`, `theme`, `ks-theme`; обёртка `.sh` вызывает `PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok <команда> "$@"` (флаг `-I` не использовать: он отключает PYTHONPATH). Служебные `can-uuid`/`mcu-merge` не регистрируются. Каждый агент добавляет только свою строку.

## Общие переменные окружения (читаются так же, как в bash)
`PRINTER_DATA, KLIPPER_DIR, KLIPPY_ENV, KATAPULT_DIR, KIAUH_DIR, MOONRAKER_URL, CONFIGS_DIR, FIRMWARE_DIR, BUILD_DIR, STATE_FILE, LOG_FILE, CAN_IFACE, DEVICES_FILE, BYID_DIR, BOARDS_DIR, VOSTOK_CFG_LOCAL, VOSTOK_CFG_TARBALL, KERNEL_CONFIG, USER_GROUPS, USER_GROUPS_DB, MIN_FREE_MB, MIN_MEM_MB, FLUIDD_DIR, KS_DIR, FONT_DIR`.
