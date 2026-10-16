"""Обновление Klipper и перепрошивка MCU (бывший update_klipper_mcu.sh).

Обновляет текущую ветку klipper (KIAUH или git fast-forward), собирает прошивку под каждый найденный MCU
и прошивает её через katapult (USB и CAN), затем сверяет версии MCU с версией хоста.

Режимы: --list, --no-update, --no-flash, --force-flash, --git-update (включается сам, если нет терминала:
кнопка Fluidd), --ignore-moonraker, -y. Поведение, тексты и коды возврата как у bash-версии 1.3a.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import INSTALL_DIR, VostokError, boards, firmware, hardware, ui
from .state import DevicesFile, FlashedLog
from .system import Runner, can_manage_services

USAGE = """\
Использование: update_klipper_mcu.sh [опции]

  --list              показать найденные MCU, конфиги сборки и версии, ничего не менять
  --no-update         не обновлять хост (KIAUH), только собрать и прошить MCU
  --no-flash          обновить только хост, прошивки MCU не трогать
  --force-flash       прошить все MCU, даже если версии уже совпадают с хостом
  --git-update        обновить хост без KIAUH (git fast-forward + pip, без sudo);
                      включается сам, если нет терминала (кнопка в Fluidd)
  -V, --version       показать версию установщика
  --ignore-moonraker  продолжить, если Moonraker недоступен (статус печати и
                      секции [mcu*] из printer.cfg не проверяются)
  -y, --yes           не задавать вопросов
  -h, --help          эта справка

Переменные окружения (значения по умолчанию в скобках):
  KLIPPER_DIR ($HOME/klipper)  KATAPULT_DIR ($HOME/katapult)  KIAUH_DIR ($HOME/kiauh)
  KLIPPY_ENV ($HOME/klippy-env)  PRINTER_DATA ($HOME/printer_data)
  MOONRAKER_URL (http://localhost:7125)  CONFIGS_DIR ($скрипт/configs)
  BOARDS_DIR ($скрипт/boards)  DEVICES_FILE ($скрипт/devices.tsv)  BYID_DIR (/dev/serial/by-id)
"""

# Порядок прошивки: сначала MCU вне printer.cfg, потом дополнительные, главный [mcu] (или мост) последним
ORDER_USB, ORDER_EXTRA, ORDER_MAIN = 1, 2, 3


# ---------------------------------------------------------------- настройки

@dataclass
class Config:
    """Пути и адреса; значения по умолчанию и переменные окружения как в update_klipper_mcu.sh."""
    install_dir: Path
    klipper_dir: str
    klippy_env: str
    katapult_dir: str
    kiauh_dir: str
    printer_data: str
    moonraker_url: str
    configs_dir: str
    firmware_dir: str
    build_dir: str
    state_file: str
    log_file: str
    can_iface: str
    devices_file: str
    byid_dir: str
    boards_dir: str
    gcode_shell_asset: str

    @classmethod
    def from_env(cls, env=None) -> "Config":
        """Прочитать окружение (пустое значение = не задано, как ``${VAR:-…}`` в bash)."""
        e = os.environ if env is None else env
        home = e.get("HOME") or os.path.expanduser("~")
        inst = str(INSTALL_DIR)

        def get(name: str, default: str) -> str:
            return e.get(name) or default

        printer_data = get("PRINTER_DATA", home + "/printer_data")
        kiauh = get("KIAUH_DIR", home + "/kiauh")
        firmware_dir = get("FIRMWARE_DIR", inst + "/firmware")
        return cls(
            install_dir=INSTALL_DIR,
            klipper_dir=get("KLIPPER_DIR", home + "/klipper"),
            klippy_env=get("KLIPPY_ENV", home + "/klippy-env"),
            katapult_dir=get("KATAPULT_DIR", home + "/katapult"),
            kiauh_dir=kiauh,
            printer_data=printer_data,
            moonraker_url=get("MOONRAKER_URL", "http://localhost:7125"),
            configs_dir=get("CONFIGS_DIR", inst + "/configs"),
            firmware_dir=firmware_dir,
            build_dir=get("BUILD_DIR", inst + "/build"),
            # Журнал версий, которые прошил этот скрипт: серийный_номер<TAB>версия
            state_file=get("STATE_FILE", firmware_dir + "/flashed.tsv"),
            log_file=get("LOG_FILE", printer_data + "/logs/klipper_mcu_update.log"),
            can_iface=get("CAN_IFACE", "can0"),
            devices_file=get("DEVICES_FILE", inst + "/devices.tsv"),
            byid_dir=get("BYID_DIR", "/dev/serial/by-id"),
            boards_dir=get("BOARDS_DIR", inst + "/boards"),
            gcode_shell_asset=get("GCODE_SHELL_ASSET",
                                  kiauh + "/kiauh/extensions/gcode_shell_cmd/assets/gcode_shell_command.py"),
        )


@dataclass
class Options:
    """Флаги командной строки."""
    do_update: bool = True
    do_flash: bool = True
    force_flash: bool = False
    assume_yes: bool = False
    list_only: bool = False
    ignore_moonraker: bool = False
    git_update: bool = False


@dataclass
class Mcu:
    """Найденный MCU (вместо девяти параллельных массивов bash)."""
    name: str
    path: str                  # USB: путь в by-id; CAN: "CAN <интерфейс> <uuid>"
    chip: str
    serial: str                # серийный номер USB или uuid CAN (ключ devices.tsv и flashed.tsv)
    cfg: str = ""              # путь к конфигу сборки ("" - конфига нет)
    version: str = "?"         # "?" неизвестна; "vX*" - из журнала прошивок
    order: int = ORDER_EXTRA
    uuid: str = ""             # canbus_uuid для MCU на CAN
    is_bridge: bool = False    # главная плата - мост USB-CAN


# ---------------------------------------------------------------- Moonraker

class Moonraker:
    """Клиент Moonraker на urllib (curl -sf --max-time 5 в bash)."""

    def __init__(self, url: str, timeout: float = 5) -> None:
        self.url = url
        self.timeout = timeout
        self.ok = False

    def fetch(self, path: str) -> Optional[str]:
        """Тело ответа или None при любой ошибке (в том числе HTTP >= 400)."""
        try:
            with urllib.request.urlopen(self.url + path, timeout=self.timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:   # сеть, HTTP-ошибка, таймаут: как ненулевой код curl
            return None

    def get_json(self, path: str) -> Optional[dict]:
        """Разобранный JSON-объект или None (нет ответа / не JSON)."""
        body = self.fetch(path)
        if body is None:
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def status(self, path: str) -> Optional[dict]:
        """``result.status`` ответа объектного запроса или None."""
        data = self.get_json(path)
        try:
            st = data["result"]["status"]   # type: ignore[index]
        except (TypeError, KeyError):
            return None
        return st if isinstance(st, dict) else None

    def mcu_sections(self) -> List[Tuple[str, str, str]]:
        """Секции [mcu*] из printer.cfg: (имя, serial, canbus_uuid); пустое значение - пустая строка."""
        if not self.ok:
            return []
        st = self.status("/printer/objects/query?configfile=settings")
        try:
            settings = st["configfile"]["settings"]   # type: ignore[index]
        except (TypeError, KeyError):
            return []
        res = []
        if not isinstance(settings, dict):
            return res
        for name, sect in settings.items():
            if name == "mcu" or name.startswith("mcu "):
                sect = sect if isinstance(sect, dict) else {}
                res.append((name, str(sect.get("serial") or ""), str(sect.get("canbus_uuid") or "")))
        return res

    def mcu_versions(self, names: List[str]) -> Dict[str, str]:
        """Версии прошивок: {имя объекта mcu*: mcu_version}."""
        if not self.ok or not names:
            return {}
        query = "&".join(urllib.parse.quote(n) for n in names)
        st = self.status("/printer/objects/query?" + query)
        if not st:
            return {}
        return {n: str(o["mcu_version"]) for n, o in st.items() if isinstance(o, dict) and "mcu_version" in o}

    def print_state(self) -> str:
        """print_stats.state или пустая строка."""
        st = self.status("/printer/objects/query?print_stats")
        try:
            return str(st["print_stats"]["state"])   # type: ignore[index]
        except (TypeError, KeyError):
            return ""

    def printer_info(self, key: str) -> str:
        """Поле result.<key> из /printer/info или пустая строка."""
        data = self.get_json("/printer/info")
        try:
            return str(data["result"][key])   # type: ignore[index]
        except (TypeError, KeyError):
            return ""


# ---------------------------------------------------------------- вспомогательное

def _pad(text: str, width: int) -> str:
    """Дополнить пробелами справа до ширины в БАЙТАХ UTF-8 (так делает printf %-Ns в bash)."""
    return text + " " * max(0, width - len(text.encode("utf-8")))


def read_version(install_dir=INSTALL_DIR) -> str:
    """Версия установщика: первая строка файла VERSION без пробелов ("неизвестна", если файла нет)."""
    try:
        with open(Path(install_dir) / "VERSION", encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        first = ""
    return re.sub(r"\s+", "", first) or "неизвестна"


def parse_args(argv: List[str]) -> Optional[Options]:
    """Разбор аргументов (в том же порядке и с теми же сообщениями, что в bash).
    None - уже обработано (--help, --version); неизвестная опция - справка в stderr и VostokError."""
    o = Options()
    for a in argv:
        if a == "--list":
            o.list_only = True
        elif a == "--no-update":
            o.do_update = False
        elif a == "--no-flash":
            o.do_flash = False
        elif a == "--force-flash":
            o.force_flash = True
        elif a == "--git-update":
            o.git_update = True
        elif a == "--ignore-moonraker":
            o.ignore_moonraker = True
        elif a in ("-y", "--yes"):
            o.assume_yes = True
        elif a in ("-V", "--version"):
            print("VOSTOK installer " + read_version())
            return None
        elif a in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return None
        else:
            sys.stderr.write(USAGE)
            raise VostokError("неизвестная опция: " + a)
    if not sys.stdin.isatty():
        o.git_update = True   # без терминала KIAUH (sudo) не вызвать
    return o


def _short(sha: str) -> str:
    return sha[:8]


# ---------------------------------------------------------------- обновление

class Updater:
    """Один запуск update: проверки, поиск MCU, обновление хоста, сборка и прошивка, проверка итогов."""

    def __init__(self, cfg: Config, opts: Options, runner: Optional[Runner] = None,
                 moon: Optional[Moonraker] = None) -> None:
        self.cfg = cfg
        self.opts = opts
        self.runner = runner or Runner()
        self.moon = moon or Moonraker(cfg.moonraker_url)
        self.devices = DevicesFile(cfg.devices_file)
        self.flashed = FlashedLog(cfg.state_file)
        self.mcus: List[Mcu] = []
        self.skipped: List[str] = []
        self.built: Dict[str, str] = {}
        self.klipper_stopped = False

    def registry(self) -> boards.Registry:
        """Реестр плат с каталогами из окружения (BOARDS_DIR, CONFIGS_DIR, KATAPULT_CONFIGS)."""
        return boards.Registry(self.cfg.boards_dir, self.cfg.configs_dir, os.environ.get("KATAPULT_CONFIGS") or None)

    # ---- git

    def _git(self, *args: str) -> Tuple[int, str]:
        """git -C klipper_dir …: (код, stdout); ошибки git на экран не выводятся."""
        return hardware.run_quiet(["git", "-C", self.cfg.klipper_dir] + list(args))

    def _git_out(self, *args: str) -> str:
        rc, out = self._git(*args)
        if rc != 0:
            raise VostokError("git %s не удался" % " ".join(args))
        return out.strip("\n")

    def host_version(self) -> str:
        return firmware.host_version(self.cfg.klipper_dir, self.runner)

    # ---- Moonraker

    def check_moonraker(self) -> None:
        if self.moon.fetch("/server/info") is not None:
            self.moon.ok = True
            return
        url = self.cfg.moonraker_url
        if self.opts.ignore_moonraker:
            ui.warn("Moonraker недоступен (%s): статус печати и секции [mcu*] не проверяются" % url)
            return
        ui.die("Moonraker недоступен (%s). Проверьте MOONRAKER_URL или запустите с --ignore-moonraker" % url)

    def check_not_printing(self) -> None:
        if not self.moon.ok:
            return
        state = self.moon.print_state()
        if state in ("printing", "paused"):
            ui.die("идёт печать (state=%s). Обновление остановит Klipper и сорвёт печать" % state)

    # ---- проверки

    def preflight(self) -> None:
        c, o = self.cfg, self.opts
        ui.step("Проверки")
        if os.geteuid() == 0:
            ui.die("не запускайте от root (KIAUH это запрещает), sudo спросит пароль сам")
        if not shutil.which("python3"):
            ui.die("нет python3")
        if not shutil.which("git"):
            ui.die("нет git")
        if not os.path.isdir(os.path.join(c.klipper_dir, ".git")):
            ui.die("%s не git-репозиторий (KLIPPER_DIR)" % c.klipper_dir)

        if o.do_update:
            if o.git_update:
                if not os.access(os.path.join(c.klippy_env, "bin", "pip"), os.X_OK):
                    ui.die("нет %s/bin/pip (KLIPPY_ENV)" % c.klippy_env)
            elif not os.access(os.path.join(c.kiauh_dir, "kiauh.sh"), os.X_OK):
                ui.die("нет %s/kiauh.sh (KIAUH_DIR)" % c.kiauh_dir)
            if self._git("rev-parse", "--abbrev-ref", "@{u}")[0] != 0:
                ui.die("у текущей ветки klipper не задан upstream, git pull не сработает")
        if o.do_flash:
            if not os.path.isfile(os.path.join(c.katapult_dir, "scripts", "flashtool.py")):
                ui.die("нет %s/scripts/flashtool.py (KATAPULT_DIR)" % c.katapult_dir)
            if hardware.run_quiet(["python3", "-c", "import serial"])[0] != 0:
                ui.die("для flashtool.py нужен pyserial (python3 -m pip install pyserial)")
            if not shutil.which("arm-none-eabi-gcc"):
                ui.die("нет arm-none-eabi-gcc (sudo apt install gcc-arm-none-eabi)")
            if not shutil.which("make"):
                ui.die("нет make")
            if not hardware.have_ip():
                ui.warn("нет ip (пакет iproute2): MCU на CAN не будут найдены")
            if not sys.stdin.isatty() and not o.list_only:
                if not can_manage_services(True):
                    ui.die("без терминала нет прав останавливать klipper (нужен polkit Moonraker "
                           "или sudo NOPASSWD, см. install_fluidd_button.sh)")

        # tracked-изменения ломают git pull и дают -dirty в версии прошивки; untracked не мешают
        _, dirty = self._git("status", "--porcelain", "--untracked-files=no")
        if dirty.strip():
            _, short = self._git("status", "--short", "--untracked-files=no")
            sys.stderr.write(short)
            sys.stderr.flush()
            ui.die("в %s есть изменённые отслеживаемые файлы, зафиксируйте или откатите их" % c.klipper_dir)

        self.check_moonraker()
        self.check_not_printing()
        ui.ok("проверки пройдены")

    # ---- обнаружение MCU

    def _config_chip_ok(self, rel: str, chip: str) -> bool:
        """Файл конфига существует и собирает именно этот чип."""
        if not rel:
            return False
        p = os.path.join(self.cfg.configs_dir, rel)
        return os.path.isfile(p) and firmware.config_mcu(p) == chip

    def add_mcu(self, name: str, path: str, origin: str) -> None:
        """Добавить USB-MCU; origin: cfg (из printer.cfg) или usb (только в by-id)."""
        real = os.path.realpath(path)
        if any(os.path.realpath(m.path) == real for m in self.mcus):
            return
        chip, serial = hardware.by_id_chip(path), hardware.by_id_serial(path)
        if not chip:
            self.skipped.append("%s (%s): не /dev/serial/by-id/usb-Klipper_*, тип чипа неизвестен" % (name, path))
            return
        dev = self.devices.lookup(serial)
        rel = dev.cfg if dev else ""
        cfg = ""
        # конфиг должен быть под чип устройства: устаревшая запись devices.tsv не должна подсунуть чужую прошивку
        for c in (rel, serial + ".config", chip + ".config"):
            if self._config_chip_ok(c, chip):
                cfg = os.path.join(self.cfg.configs_dir, c)
                break
        reg = self.registry()
        if (cfg and not rel and cfg == os.path.join(self.cfg.configs_dir, chip + ".config")
                and len(reg.for_chip(chip, "main")) > 1):
            found = reg.by_cfg(chip + ".config")
            label = reg.get(found[0]).label if found else ""
            ui.warn("%s: serial %s нет в devices.tsv, на чипе %s бывают разные платы; беру %s.config (%s). "
                    "Если плата другая, добавьте serial в devices.tsv" % (name, serial, chip, chip, label))
        # Порядок прошивки: сначала MCU вне printer.cfg, потом дополнительные, главный [mcu] последним
        if origin == "usb":
            order = ORDER_USB
        elif name == "mcu":
            order = ORDER_MAIN
        else:
            order = ORDER_EXTRA
        self.mcus.append(Mcu(name=name, path=path, chip=chip, serial=serial, cfg=cfg, order=order))

    def add_can_mcu(self, name: str, uuid: str) -> None:
        """Добавить MCU на CAN (по canbus_uuid)."""
        c = self.cfg
        dev = self.devices.lookup(uuid)
        rel = dev.cfg if dev else ""
        role = dev.role if dev else ""
        cfg = ""
        if rel and os.path.isfile(os.path.join(c.configs_dir, rel)):
            cfg = os.path.join(c.configs_dir, rel)
        elif os.path.isfile(os.path.join(c.configs_dir, uuid + ".config")):
            cfg = os.path.join(c.configs_dir, uuid + ".config")
        if not cfg:
            self.skipped.append("%s: CAN (canbus_uuid %s), нет конфига сборки (devices.tsv или configs/%s.config), "
                                "прошивается вручную: flashtool.py -i %s -u %s -f <bin>"
                                % (name, uuid, uuid, c.can_iface, uuid))
            return
        if not hardware.can_iface_up(c.can_iface):
            self.skipped.append("%s: CAN (canbus_uuid %s), интерфейс %s не поднят (ip link show %s)"
                                % (name, uuid, c.can_iface, c.can_iface))
            return
        chip = firmware.config_mcu(cfg)
        bridge = role == "bridge"
        order = ORDER_MAIN if (bridge or name == "mcu") else ORDER_EXTRA
        self.mcus.append(Mcu(name=name, path="CAN %s %s" % (c.can_iface, uuid), chip=chip, serial=uuid,
                             cfg=cfg, order=order, uuid=uuid, is_bridge=bridge))

    def discover_mcus(self) -> None:
        """Заполнить self.mcus и self.skipped: секции [mcu*] из Moonraker, затем остальное из by-id."""
        c = self.cfg
        self.mcus, self.skipped = [], []
        names: List[str] = []
        for name, serial, uuid in self.moon.mcu_sections():
            if not name:
                continue
            names.append(name)
            if uuid:
                self.add_can_mcu(name, uuid)
            elif serial:
                if os.path.exists(serial):
                    self.add_mcu(name, serial, "cfg")
                else:
                    self.skipped.append("%s: устройство %s не найдено (не подключено или в режиме загрузчика?)"
                                        % (name, serial))
        for dev in hardware.list_byid(c.byid_dir, "usb-Klipper_"):
            self.add_mcu("(не в printer.cfg)", dev, "usb")
        for dev in hardware.list_byid(c.byid_dir, "usb-katapult_"):
            self.skipped.append("%s: устройство в режиме загрузчика katapult, прошейте вручную: "
                                "flashtool.py -d %s -f <bin>" % (os.path.basename(dev), dev))
        # Текущие версии прошивок
        versions = self.moon.mcu_versions(names)
        for n, v in versions.items():
            if not n:
                continue
            for m in self.mcus:
                if m.name == n:
                    m.version = v
        # Версия неизвестна (нет в printer.cfg или Klipper не дошёл до MCU): берём из журнала, помечаем "*"
        for m in self.mcus:
            if m.version == "?":
                v = self.flashed.get(m.serial)
                if v:
                    m.version = v + "*"

    def print_mcus(self) -> None:
        c = self.cfg
        ui.info("Версия хоста: " + self.host_version())
        if not self.mcus:
            ui.info("MCU по USB не найдены")
        else:
            sys.stdout.write("%s %s %s %s %s\n" % (_pad("MCU", 20), _pad("чип", 13), _pad("версия", 26),
                                                  _pad("конфиг сборки", 24), "устройство"))
            for m in self.mcus:
                cfgname = os.path.basename(m.cfg) if m.cfg else "-- нет --"
                sys.stdout.write("%s %s %s %s %s\n" % (_pad(m.name, 20), _pad(m.chip, 13), _pad(m.version, 26),
                                                      _pad(cfgname, 24), m.path))
            sys.stdout.flush()
        # Подпись платы из реестра, если конфиг известен реестру (из devices.tsv); для обычного
        # <чип>.config (Octopus, ALPS) строку не добавляем, чтобы вывод не менялся
        reg = self.registry()
        for m in self.mcus:
            if not m.cfg or os.path.basename(m.cfg) == m.chip + ".config":
                continue
            found = reg.by_cfg(m.cfg)
            if not found:
                continue
            try:
                label = reg.get(found[0]).label
            except boards.BoardError:
                continue
            ui.info("Плата %s: %s (%s)" % (m.name, label, found[1]))
        for s in self.skipped:
            ui.info("Пропущено: " + s)
        for m in self.mcus:
            if not m.cfg:
                ui.warn("для %s (%s) нет конфига сборки; создайте его: cd %s && make menuconfig KCONFIG_CONFIG=%s/%s.config"
                        % (m.name, m.chip, c.klipper_dir, c.configs_dir, m.chip))

    # ---- обновление хоста

    def pending_commits(self) -> int:
        if self.runner.run(["git", "-C", self.cfg.klipper_dir, "fetch", "-q"], check=False).returncode != 0:
            ui.die("git fetch не удался")
        return int(self._git_out("rev-list", "--count", "HEAD..@{u}"))

    def post_update_checks(self) -> None:
        """Расширение KIAUH пропадает при смене/переустановке репозитория; затем проверка импорта."""
        c = self.cfg
        extras = Path(c.klipper_dir) / "klippy" / "extras"
        if self._has_gcode_shell_section() and not (extras / "gcode_shell_command.py").is_file():
            asset = Path(c.gcode_shell_asset)
            if asset.is_file():
                dest = extras / "gcode_shell_command.py"
                if not dest.exists():   # cp -n
                    shutil.copyfile(str(asset), str(dest))
                    shutil.copymode(str(asset), str(dest))
                ui.info("восстановлен gcode_shell_command.py")
            else:
                ui.warn("в конфигах есть [gcode_shell_command], но %s не найден" % c.gcode_shell_asset)
        py = os.path.join(c.klippy_env, "bin", "python")
        if os.access(py, os.X_OK):
            cp = self.runner.run([py, os.path.join(c.klipper_dir, "klippy", "klippy.py"), "--import-test"],
                                 capture=True, check=False)
            if cp.returncode != 0:
                ui.die("klippy --import-test не прошёл после обновления")

    def _has_gcode_shell_section(self) -> bool:
        cfg_dir = Path(self.cfg.printer_data) / "config"
        try:
            files = sorted(cfg_dir.glob("*.cfg"))
        except OSError:
            return False
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    if any(line.startswith("[gcode_shell_command") for line in fh):
                        return True
            except OSError:
                continue
        return False

    def update_host_git(self) -> None:
        """Обновление без KIAUH и без sudo: fast-forward ветки, зависимости в klippy-env.
        Klipper остановлен на время обновления (останавливает run)."""
        c = self.cfg
        ui.step("Обновление Klipper через git")
        before = self._git_out("rev-parse", "HEAD")
        upstream = self._git_out("rev-parse", "@{u}")
        git = ["git", "-C", c.klipper_dir]
        if self._git("merge-base", "--is-ancestor", "HEAD", upstream)[0] == 0:
            if self.runner.run(git + ["merge", "--ff-only", "-q", upstream], check=False).returncode != 0:
                ui.die("git merge --ff-only не удался")
        elif not self._git("rev-list", "HEAD", "--not", "--remotes")[1].strip():
            # upstream переписан (force-push), локальных коммитов, которых нет на сервере, нет
            ui.warn("история upstream переписана, перехожу на " + _short(upstream))
            if self.runner.run(git + ["reset", "-q", "--hard", upstream], check=False).returncode != 0:
                ui.die("git reset не удался")
        else:
            ui.die("в %s есть локальные коммиты, которых нет на сервере; обновите вручную" % c.klipper_dir)
        after = self._git_out("rev-parse", "HEAD")
        if after != upstream:
            ui.die("репозиторий не на upstream после обновления")
        ui.info("обновлено: %s -> %s" % (_short(before), _short(after)))

        ui.log("pip install -r klippy-requirements.txt")
        pip = self.runner.run([os.path.join(c.klippy_env, "bin", "pip"), "install", "-q", "-r",
                               os.path.join(c.klipper_dir, "scripts", "klippy-requirements.txt")], check=False)
        if pip.returncode != 0:
            ui.die("pip install зависимостей klippy не удался")
        if self._git("diff", "--quiet", before, after, "--", "scripts/install-debian.sh")[0] != 0:
            ui.warn("изменился scripts/install-debian.sh: возможно нужны новые системные пакеты; "
                    "запустите ./update_klipper_mcu.sh из терминала (KIAUH)")
        self.post_update_checks()
        ui.ok("хост обновлён: " + self.host_version())

    def update_host(self) -> None:
        """Обновление через KIAUH (нужен терминал: KIAUH вызывает sudo)."""
        c = self.cfg
        ui.step("Обновление Klipper через KIAUH")
        before = self._git_out("rev-parse", "HEAD")
        ui.log("запуск KIAUH: kiauh.sh update klipper")
        if self.runner.run([os.path.join(c.kiauh_dir, "kiauh.sh"), "update", "klipper"],
                           check=False).returncode != 0:
            ui.die("KIAUH завершился с ошибкой")
        # git_pull_wrapper в KIAUH глотает ошибки git pull, поэтому проверяем результат сами
        after = self._git_out("rev-parse", "HEAD")
        upstream = self._git_out("rev-parse", "@{u}")
        if after != upstream:
            ui.die("после KIAUH репозиторий не на upstream (HEAD=%s, upstream=%s); смотрите вывод git pull выше"
                   % (_short(after), _short(upstream)))
        if before == after:
            ui.info("репозиторий не изменился")
        else:
            ui.info("обновлено: %s -> %s" % (_short(before), _short(after)))
        self.post_update_checks()
        ui.ok("хост обновлён: " + self.host_version())

    # ---- службы

    def klipper_units(self) -> List[str]:
        rc, out = hardware.run_quiet(["systemctl", "list-unit-files", "klipper*.service", "--no-legend"])
        units = []
        for line in out.split("\n"):
            parts = line.split()
            if parts and re.match(r"^klipper(-[A-Za-z0-9_]+)?\.service$", parts[0]) \
                    and parts[0] != "klipper-mcu.service":
                units.append(parts[0])
        return units

    def services(self, action: str) -> None:
        units = self.klipper_units()
        if not units:
            ui.die("не найдены сервисы klipper*.service")
        for u in units:
            ui.info("systemctl %s %s" % (action, u))
            if not self.runner.systemctl(action, u):
                ui.die("systemctl %s %s не удалось" % (action, u))

    # ---- прошивка

    def flash_can(self, m: Mcu, binpath: str) -> bool:
        """Прошивка одного MCU по CAN. Обычная плата (H36/EBB): flashtool сам просит загрузчик по uuid.
        Octopus в режиме моста USB-CAN: загрузчик запрашивается по CAN, мост перезагружается в
        usb-katapult_* (шина CAN на это время пропадает), затем прошивка по USB."""
        c = self.cfg
        if m.is_bridge:
            if not firmware.request_bootloader_can(c.katapult_dir, c.can_iface, m.uuid, self.runner):
                return False
            dev = hardware.wait_for_katapult(c.byid_dir, m.chip)   # BYID_DIR, а не жёсткий /dev/serial/by-id
            if not dev:
                ui.warn("мост не перешёл в katapult за 20 с (usb-katapult_%s_*)" % m.chip)
                return False
            ui.log("flashtool -d %s -f %s (мост)" % (dev, binpath))
            if not firmware.flashtool(c.katapult_dir, ["-d", dev, "-f", binpath], self.runner):
                return False
            # мост вернулся: поднимается gs_usb и интерфейс CAN
            if not hardware.wait_for_can_iface(c.can_iface):
                ui.warn("интерфейс %s не появился после прошивки моста" % c.can_iface)
                return False
            if not hardware.can_iface_up(c.can_iface):
                hardware.ifup(c.can_iface)
            time.sleep(2)
        else:
            if not firmware.flash_can_node(c.katapult_dir, c.can_iface, m.uuid, binpath, self.runner):
                return False
            time.sleep(2)
        return True

    def _flash_failed_help(self, m: Mcu, binpath: str) -> None:
        c = self.cfg
        if m.uuid:
            text = """
Прошивка {name} по CAN не удалась. Klipper НЕ запущен.
Что делать: katapult остаётся в MCU, прошивку можно повторить.
  - проверьте шину: ip -s -d link show {iface} (state UP, bitrate 1000000, errors 0; BUS-OFF: перезапустите интерфейс);
  - терминаторы 120 Ом: на шине должно быть около 60 Ом (питание выключено);
  - python3 {kat}/scripts/flashtool.py -i {iface} -q покажет uuid плат, находящихся в katapult (двойной RESET);
  - повтор: python3 {kat}/scripts/flashtool.py -i {iface} -u {uuid} -f {bin}
"""
        else:
            text = """
Прошивка {name} не удалась. Klipper НЕ запущен.
Что делать: katapult остаётся в MCU, прошивку можно повторить.
  - посмотрите ls /dev/serial/by-id/ (устройство может быть usb-katapult_*);
  - если есть usb-katapult_*: python3 {kat}/scripts/flashtool.py -d /dev/serial/by-id/usb-katapult_... -f {bin}
  - иначе дважды быстро нажмите RESET на плате (двойной сброс входит в katapult).
"""
        sys.stderr.write(text.format(name=m.name, iface=c.can_iface, kat=c.katapult_dir, uuid=m.uuid, bin=binpath))
        sys.stderr.flush()

    def flash_all(self, ordered: List[Mcu]) -> None:
        c = self.cfg
        for m in ordered:
            binpath = self.built[m.cfg]
            ui.step("Прошивка %s (%s)" % (m.name, m.chip))
            if m.uuid:
                ok_flash = self.flash_can(m, binpath)
            else:
                ok_flash = firmware.flash_usb(c.katapult_dir, m.path, binpath, self.runner)
            if not ok_flash:
                self._flash_failed_help(m, binpath)
                ui.die("прошивка %s не удалась" % m.name)
            if not m.uuid:
                if not hardware.wait_for_device(m.path, 20):
                    ui.die("после прошивки %s не вернулось устройство %s; проверьте ls /dev/serial/by-id/"
                           % (m.name, m.path))
            self.flashed.set(m.serial, self.host_version())
            ui.ok("%s прошит" % m.name)

    # ---- проверка итогов

    def wait_for_klipper(self) -> bool:
        state = ""
        for _ in range(60):
            state = self.moon.printer_info("state")
            if state in ("ready", "shutdown", "error"):
                break
            time.sleep(1)
        if not state:
            ui.warn("Moonraker не ответил за 60 с; проверьте systemctl status klipper moonraker")
            return False
        if state != "ready":
            msg = self.moon.printer_info("state_message")
            ui.warn("состояние Klipper: " + state)
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()
            return False
        ui.ok("Klipper: ready")
        return True

    def verify_versions(self) -> bool:
        """True - все версии совпали с хостом."""
        host = firmware.norm_version(self.host_version())
        self.discover_mcus()
        good = True
        for m in self.mcus:
            v = m.version
            if v == "?":
                ui.info("%s: версию получить не удалось" % m.name)
            elif v.endswith("*"):
                # Версия из журнала: MCU вне printer.cfg, сам Klipper её не видит
                if firmware.norm_version(v) == host:
                    ui.ok("%s: %s (по журналу прошивок)" % (m.name, v[:-1]))
                else:
                    ui.warn("%s: %s по журналу, хост %s" % (m.name, v[:-1], host))
                    good = False
            elif firmware.norm_version(v) == host:
                ui.ok("%s: %s" % (m.name, v))
            else:
                ui.warn("%s: %s (хост %s)" % (m.name, v, host))
                good = False
        return good

    # ---- main

    def run(self) -> int:
        c, o = self.cfg, self.opts
        # В bash аргументы к этому моменту уже сняты (shift), поэтому в журнал попадал пустой список
        ui.log("=== запуск (VOSTOK installer %s):  ===" % read_version(c.install_dir))
        self.preflight()

        ui.step("Найденные MCU")
        self.discover_mcus()
        self.print_mcus()
        if o.list_only:
            return 0

        pending = 0
        host_before = self.host_version()
        if o.do_update:
            pending = self.pending_commits()
            ui.step("Обновления в ветке klipper")
            if pending > 0:
                _, log = self._git("log", "--oneline", "HEAD..@{u}")
                sys.stdout.write("".join(ln + "\n" for ln in log.split("\n")[:-1][:20]))
                sys.stdout.flush()
                if pending > 20:
                    ui.info("... и ещё %d" % (pending - 20))
                ui.info("Новых коммитов: %d" % pending)
            else:
                ui.info("Новых коммитов нет (версия %s)" % host_before)

        # Какие MCU нужно прошить: все, если хост обновится или --force-flash, иначе только отстающие
        host_norm = firmware.norm_version(host_before)
        targets: List[Mcu] = []
        if o.do_flash:
            for m in self.mcus:
                if not m.cfg:
                    continue
                if pending > 0 or o.force_flash or firmware.norm_version(m.version) != host_norm:
                    targets.append(m)

        if pending == 0 and not targets:
            ui.ok("всё актуально: хост %s, прошивки MCU совпадают" % host_before)
            return 0

        ui.info("")
        if pending > 0:
            if o.git_update:
                ui.info("Будет обновлён хост Klipper (git fast-forward, Klipper будет остановлен).")
            else:
                ui.info("Будет обновлён хост Klipper через KIAUH.")
        if targets:
            ui.info("Будут собраны и прошиты:")
            for m in targets:
                ui.info("  %s (%s) <- %s" % (m.name, m.chip, os.path.basename(m.cfg)))
            ui.info("Klipper будет остановлен на время прошивки.")
        if not ui.confirm("Продолжить?"):
            ui.info("отменено")
            return 0

        if pending > 0:
            if o.git_update:
                ui.step("Остановка Klipper")
                self.services("stop")
                self.klipper_stopped = True
                self.update_host_git()
            else:
                self.update_host()

        if targets:
            ui.step("Сборка прошивок")
            for m in targets:
                firmware.build_firmware(m.cfg, m.chip, klipper_dir=c.klipper_dir, build_dir=c.build_dir,
                                        firmware_dir=c.firmware_dir, built=self.built, runner=self.runner)
            # Порядок: MCU вне printer.cfg, затем дополнительные, главный [mcu] (или мост) последним
            ordered = [m for order in (ORDER_USB, ORDER_EXTRA, ORDER_MAIN) for m in targets if m.order == order]
            if not self.klipper_stopped:
                ui.step("Остановка Klipper")
                self.services("stop")
                self.klipper_stopped = True
            self.flash_all(ordered)
        if self.klipper_stopped:
            ui.step("Запуск Klipper")
            self.services("start")
            self.klipper_stopped = False

        ui.step("Проверка")
        rc = 0
        if not self.wait_for_klipper():
            rc = 1
        if not self.verify_versions():
            rc = 1
        if rc == 0:
            ui.ok("готово")
        else:
            ui.warn("завершено с замечаниями, смотрите вывод выше (лог: %s)" % c.log_file)
        return rc


def main(argv: List[str]) -> int:
    """Точка входа ``python3 -m vostok update``: код возврата как у update_klipper_mcu.sh."""
    cfg = Config.from_env()
    ui.set_options(yes=False, dry_run=False, log_file=Path(cfg.log_file))
    opts = parse_args(list(argv))
    if opts is None:
        return 0
    ui.set_options(yes=opts.assume_yes, dry_run=False, log_file=Path(cfg.log_file))
    return Updater(cfg, opts).run()
