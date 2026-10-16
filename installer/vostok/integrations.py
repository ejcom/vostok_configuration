"""Интеграции: кнопка прошивки MCU в Fluidd, тема Fluidd и тема KlipperScreen.

Бывшие install_fluidd_button.sh, install_fluidd_theme.sh и install_klipperscreen_theme.sh. Команды cli:
``button``, ``theme``, ``ks-theme``. Флаги, переменные окружения, тексты и коды возврата как в bash.
Системные действия (sudo, systemctl, apt) идут через ``system.Runner``, правка файлов - атомарно
(``cfgfile.atomic_write``, резервная копия ``*.bak-<дата>``), HTTP к Moonraker - через urllib вместо curl.
"""
from __future__ import annotations

import glob
import json
import os
import pwd
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import INSTALL_DIR, VostokError, cfgfile, ui
from .system import Runner, can_manage_services

THEME_MARK = "VOSTOK-THEME"          # маркер в первой строке нашего custom.css / style.css
THEME_NAME = "K3D VOSTOK"

USAGE_BUTTON = """\
Использование: install_fluidd_button.sh [опции]

  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --flash-args "..."  аргументы update_klipper_mcu.sh для кнопки (по умолчанию пусто:
                      обновить ветку klipper через git и прошить MCU; например
                      "--no-update --force-flash" = только перепрошить все MCU)
  --with-macro        создать mcu_update.cfg с макросом MCU_UPDATE
  --uninstall         удалить сервис, строку в moonraker.asvc и sudoers-файл
  --dry-run           ничего не менять, показать unit и план действий
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, KLIPPER_DIR, KATAPULT_DIR, MOONRAKER_URL.
"""

USAGE_THEME = """\
Использование: install_fluidd_theme.sh [опции]

  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --fluidd-dir DIR    каталог Fluidd (по умолчанию ~/fluidd)
  --no-activate       только добавить пресет и файлы, тему не включать
  --logo-copy         положить логотип ещё и в каталог Fluidd и брать его оттуда (нужно, если
                      Moonraker требует авторизацию и логотип из config не грузится;
                      после обновления Fluidd запустите скрипт снова)
  --force             перезаписать изменённый custom.css и сменить уже выбранную другую тему
  --uninstall         удалить пресет и файлы темы, вернуть тему Fluidd по умолчанию
  --dry-run           ничего не менять, только показать план
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, FLUIDD_DIR, MOONRAKER_URL.
"""

USAGE_KS = """\
Использование: install_klipperscreen_theme.sh [опции]

  --ks-dir DIR        каталог KlipperScreen (по умолчанию ~/KlipperScreen)
  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --no-activate       только установить тему и шрифт, в KlipperScreen.conf не писать
  --force             перезаписать чужой каталог styles/vostok и сменить уже выбранную другую тему
  --uninstall         удалить тему и шрифт, вернуть тему material-dark
  --dry-run           ничего не менять, только показать план
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, KS_DIR, FONT_DIR.
"""


# --------------------------------------------------------------------------- общее

def _env(name: str, default: str) -> str:
    """${NAME:-default}: пустое значение считается незаданным."""
    return os.environ.get(name) or default


def _home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def _version(install_dir: Path) -> str:
    """Первая строка VERSION без пробельных символов; нет файла - «неизвестна»."""
    try:
        with open(str(install_dir / "VERSION"), encoding="utf-8", errors="replace") as f:
            v = re.sub(r"\s", "", f.readline())
    except OSError:
        v = ""
    return v or "неизвестна"


def _prog(name: str, install_dir: Path) -> str:
    """Как запущен скрипт ($0 в bash): обёртка передаёт его в VOSTOK_PROG."""
    return os.environ.get("VOSTOK_PROG") or str(install_dir / name)


def _parse(argv: Sequence[str], valued: Dict[str, str], flags: Dict[str, str], usage: str,
           install_dir: Path) -> Tuple[Dict[str, object], Optional[int]]:
    """Разбор аргументов в том же порядке и с теми же сообщениями, что цикл ``case`` в bash.

    valued: опция -> ключ (берёт значение), flags: опция -> ключ (булев флаг). Второй элемент
    результата - код выхода, если разбор закончил работу (-h, -V), иначе None."""
    res: Dict[str, object] = {}
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a in valued:
            if i + 1 >= len(args):
                raise VostokError("%s требует аргумент" % a)
            res[valued[a]] = args[i + 1]
            i += 1
        elif a in flags:
            res[flags[a]] = True
        elif a in ("-y", "--yes"):
            res["yes"] = True
        elif a in ("-V", "--version"):
            print("VOSTOK installer %s" % _version(install_dir))
            return res, 0
        elif a in ("-h", "--help"):
            sys.stdout.write(usage)
            return res, 0
        else:
            sys.stderr.write(usage)
            raise VostokError("неизвестная опция: %s" % a)
        i += 1
    return res, None


def http_request(method: str, url: str, data: Optional[bytes] = None, timeout: float = 5) -> Optional[bytes]:
    """Запрос к Moonraker (замена ``curl -sf --max-time``): тело ответа или None при любой ошибке/коде >= 400."""
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _first_line_has(path: Path, mark: str) -> bool:
    """В первой строке файла есть маркер (``head -n1 | grep -q``)."""
    try:
        with open(str(path), encoding="utf-8", errors="replace") as f:
            return mark in f.readline()
    except OSError:
        return False


def _install_file(src: Path, dst: Path, mode: int = 0o644) -> None:
    """``install -m MODE src dst``: запись через временный файл и rename."""
    fd, tmp = tempfile.mkstemp(prefix=dst.name + ".", dir=str(dst.parent))
    try:
        with os.fdopen(fd, "wb") as out, open(str(src), "rb") as inp:
            shutil.copyfileobj(inp, out)
        os.chmod(tmp, mode)
        os.replace(tmp, str(dst))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _check_not_root() -> None:
    if os.geteuid() == 0:
        raise VostokError("не запускайте от root: файлы должны принадлежать обычному пользователю")


# --------------------------------------------------------------------------- кнопка Fluidd

@dataclass
class ButtonOptions:
    printer_data: str = ""
    flash_args: str = ""
    with_macro: bool = False
    uninstall: bool = False
    dry_run: bool = False
    yes: bool = False
    klipper_dir: str = ""
    katapult_dir: str = ""
    moonraker_url: str = ""


class FluiddButton:
    """install_fluidd_button.sh: сервис mcu-update для меню питания Fluidd."""

    SERVICE = "mcu-update"

    def __init__(self, opts: ButtonOptions, install_dir: Path = INSTALL_DIR, runner: Optional[Runner] = None,
                 query_runner: Optional[Runner] = None, unit_dir: str = "/etc/systemd/system",
                 sudoers_dir: str = "/etc/sudoers.d", http: Callable = http_request,
                 can_manage: Callable[[bool], bool] = can_manage_services) -> None:
        self.o = opts
        self.install_dir = Path(install_dir)
        self.runner = runner or Runner()
        # чтение (--list, list-unit-files) выполняется и при --dry-run
        self.query = query_runner or Runner(dry_run=False)
        self.http = http
        self.can_manage = can_manage
        self.unit_dir = unit_dir
        self.update_script = self.install_dir / "update_klipper_mcu.sh"
        self.unit_template = self.install_dir / "mcu-update.service.in"
        self.unit_path = "%s/%s.service" % (unit_dir, self.SERVICE)
        self.sudoers_path = "%s/%s" % (sudoers_dir, self.SERVICE)
        self.asvc = os.path.join(opts.printer_data, "moonraker.asvc")
        self.macro_cfg = os.path.join(opts.printer_data, "config", "mcu_update.cfg")

    # -- вспомогательное

    def render_unit(self) -> str:
        try:
            content = self.unit_template.read_text(encoding="utf-8").rstrip("\n")
        except OSError as e:
            raise VostokError("не удалось прочитать %s: %s" % (self.unit_template, e))
        user = pwd.getpwuid(os.geteuid()).pw_name
        for key, val in (("@USER@", user), ("@HOME@", _home()), ("@PRINTER_DATA@", self.o.printer_data),
                         ("@SCRIPT@", str(self.update_script)), ("@FLASH_ARGS@", self.o.flash_args)):
            content = content.replace(key, val)
        return content + "\n"

    def restart_moonraker(self) -> None:
        if not self.runner.systemctl("restart", "moonraker"):
            ui.warn("не удалось перезапустить Moonraker, сделайте это вручную")

    def _asvc_has_service(self) -> bool:
        try:
            with open(self.asvc, encoding="utf-8", errors="replace") as f:
                return self.SERVICE in f.read().split("\n")
        except OSError:
            return False

    def _sudo_install_text(self, text: str, dst: str, mode: str, make_dir: Optional[str] = None) -> None:
        """Записать text через временный файл командой ``sudo install`` (владелец root)."""
        fd, tmp = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            if make_dir:
                self.runner.sudo(["install", "-d", "-m", "0755", make_dir])
            self.runner.sudo(["install", "-m", mode, "-o", "root", "-g", "root", tmp, dst])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # -- удаление

    def uninstall(self) -> int:
        dry = self.o.dry_run
        ui.step("Удаление")
        if os.path.isfile(self.unit_path):
            self.runner.sudo(["systemctl", "stop", self.SERVICE], check=False)
            self.runner.sudo(["rm", "-f", self.unit_path])
            self.runner.sudo(["systemctl", "daemon-reload"])
            ui.ok("удалён %s" % self.unit_path)
        for dropin in sorted(glob.glob("%s/moonraker*.service.d/%s.conf" % (self.unit_dir, self.SERVICE))):
            if not os.path.isfile(dropin):
                continue
            self.runner.sudo(["rm", "-f", dropin])
            self.runner.sudo(["rmdir", "--ignore-fail-on-non-empty", os.path.dirname(dropin)])
            self.runner.sudo(["systemctl", "daemon-reload"])
            ui.ok("удалён %s" % dropin)
        if os.path.isfile(self.sudoers_path):
            self.runner.sudo(["rm", "-f", self.sudoers_path])
            ui.ok("удалён %s" % self.sudoers_path)
        if os.path.isfile(self.asvc) and self._asvc_has_service():
            if not dry:
                self._asvc_remove()
            else:
                ui.info("[dry-run] удалить строку %s из %s" % (self.SERVICE, self.asvc))
            ui.ok("строка %s удалена из %s" % (self.SERVICE, self.asvc))
            if not dry:
                self.restart_moonraker()
        if os.path.isfile(self.macro_cfg):
            ui.warn("%s не удалён; уберите [include mcu_update.cfg] из printer.cfg и удалите файл сами"
                    % self.macro_cfg)
        return 0

    def _asvc_remove(self) -> None:
        """``grep -vx SERVICE``: убрать строки, равные имени сервиса; запись атомарная."""
        with open(self.asvc, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        kept = [ln for ln in lines if ln != self.SERVICE]
        cfgfile.atomic_write(self.asvc, "".join(ln + "\n" for ln in kept), backup=False)

    # -- установка

    def checks(self) -> None:
        o = self.o
        ui.step("Проверки")
        if not os.path.isdir(os.path.join(o.klipper_dir, ".git")):
            raise VostokError("%s не git-репозиторий (KLIPPER_DIR)" % o.klipper_dir)
        if not os.path.isfile(os.path.join(o.katapult_dir, "scripts", "flashtool.py")):
            raise VostokError("нет %s/scripts/flashtool.py (KATAPULT_DIR)" % o.katapult_dir)
        if not os.path.isdir(o.printer_data):
            raise VostokError("нет каталога %s (--printer-data)" % o.printer_data)
        if not shutil.which("systemctl"):
            raise VostokError("нет systemctl")
        if self.http("GET", "%s/server/info" % o.moonraker_url, None, 5) is None:
            raise VostokError("Moonraker недоступен (%s)" % o.moonraker_url)

        missing: List[str] = []
        if not shutil.which("arm-none-eabi-gcc"):
            missing.append("gcc-arm-none-eabi")
        if not shutil.which("make"):
            missing.append("make")
        if not self._have_serial():
            missing.append("python3-serial")
        if missing:
            names = " ".join(missing)
            ui.warn("не хватает пакетов: %s" % names)
            if not o.dry_run and ui.confirm("Установить: sudo apt install %s?" % names):
                self.runner.sudo(["apt", "install", "-y"] + missing)
            else:
                ui.warn("поставьте вручную: sudo apt install %s" % names)

        ui.info("Найденные MCU и конфиги сборки:")
        env = {"PRINTER_DATA": o.printer_data} if "PRINTER_DATA" in os.environ else None
        cp = self.query.run([str(self.update_script), "--list"], check=False, env=env)
        if cp.returncode != 0:
            ui.warn("--list завершился с ошибкой, посмотрите вывод выше")
        ui.info("Напоминание: на каждом MCU должен стоять загрузчик katapult, иначе прошивка не сработает.")
        ui.ok("проверки закончены")

    @staticmethod
    def _have_serial() -> bool:
        try:
            import serial  # noqa: F401
        except ImportError:
            return False
        return True

    def step_rights(self) -> None:
        ui.step("Права на остановку klipper без пароля")
        if self.can_manage(False):
            ui.ok("достаточно polkit (права выданы Moonraker), sudoers не нужен")
            return
        ui.warn("polkit не разрешает управлять сервисами, потребуется sudoers-правило")
        user = pwd.getpwuid(os.geteuid()).pw_name
        rule = ("%s ALL=(root) NOPASSWD: /usr/bin/systemctl start klipper*.service, "
                "/usr/bin/systemctl stop klipper*.service, /bin/systemctl start klipper*.service, "
                "/bin/systemctl stop klipper*.service" % user)
        if self.o.dry_run:
            ui.info("[dry-run] %s: %s" % (self.sudoers_path, rule))
            return
        fd, tmp = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(rule + "\n")
            if self.runner.sudo(["visudo", "-cf", tmp], check=False, capture=True).returncode != 0:
                raise VostokError("sudoers-правило не прошло visudo")
            self.runner.sudo(["install", "-m", "0440", "-o", "root", "-g", "root", tmp, self.sudoers_path])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        ui.ok("создан %s" % self.sudoers_path)

    def step_unit(self) -> None:
        ui.step("Сервис %s" % self.SERVICE)
        if self.o.dry_run:
            ui.info("[dry-run] %s:" % self.unit_path)
            ui.info(self.render_unit().rstrip("\n"))
            return
        self._sudo_install_text(self.render_unit(), self.unit_path, "0644")
        self.runner.sudo(["systemctl", "daemon-reload"])
        ui.ok("установлен %s" % self.unit_path)

    def step_asvc_and_dropins(self) -> None:
        dry = self.o.dry_run
        ui.step("Moonraker: список разрешённых сервисов")
        need_restart = False
        if os.path.isfile(self.asvc) and self._asvc_has_service():
            ui.info("%s уже есть в %s" % (self.SERVICE, self.asvc))
        elif dry:
            ui.info("[dry-run] добавить %s в %s" % (self.SERVICE, self.asvc))
        else:
            try:
                with open(self.asvc, "rb") as f:
                    old = f.read()
            except OSError:
                old = b""
            text = old.decode("utf-8", errors="replace")
            if old and not old.endswith(b"\n"):  # файл может не заканчиваться переводом строки
                text += "\n"
            cfgfile.atomic_write(self.asvc, text + self.SERVICE + "\n", backup=False)
            ui.ok("добавлено в %s" % self.asvc)
            need_restart = True

        # Moonraker показывает в Fluidd только загруженные в systemd сервисы, а неактивный oneshot
        # systemd выгружает. Ссылка After= из moonraker.service держит юнит загруженным, не запуская его.
        ui.step("Moonraker: загрузка юнита %s в systemd" % self.SERVICE)
        out = self.query.capture(["systemctl", "list-unit-files", "moonraker*.service", "--no-legend"])
        want = "[Unit]\nAfter=%s.service" % self.SERVICE
        for line in out.split("\n"):
            parts = line.split()
            if not parts:
                continue
            mu = parts[0]
            dropin = "%s/%s.d/%s.conf" % (self.unit_dir, mu, self.SERVICE)
            have = None
            if os.path.isfile(dropin):
                try:
                    have = Path(dropin).read_text(encoding="utf-8").rstrip("\n")
                except OSError:
                    have = None
            if have == want:
                ui.info("%s уже есть" % dropin)
            elif dry:
                ui.info("[dry-run] %s: After=%s.service" % (dropin, self.SERVICE))
            else:
                self._sudo_install_text(want + "\n", dropin, "0644", make_dir="%s/%s.d" % (self.unit_dir, mu))
                self.runner.sudo(["systemctl", "daemon-reload"])
                ui.ok("создан %s" % dropin)
                need_restart = True
        if need_restart and not dry:
            self.restart_moonraker()

    def step_macro(self) -> None:
        ui.step("Макрос MCU_UPDATE")
        if not os.path.isfile(os.path.join(self.o.klipper_dir, "klippy", "extras", "gcode_shell_command.py")):
            ui.warn("нет gcode_shell_command.py: установите расширение через KIAUH (Extensions), "
                    "иначе макрос не загрузится")
        if os.path.isfile(self.macro_cfg):
            ui.info("%s уже существует, не трогаю" % self.macro_cfg)
        elif self.o.dry_run:
            ui.info("[dry-run] создать %s" % self.macro_cfg)
        else:
            cfgfile.atomic_write(self.macro_cfg, MACRO_TEMPLATE.replace("@SERVICE@", self.SERVICE), backup=False)
            ui.ok("создан %s" % self.macro_cfg)
        ui.info("Добавьте в printer.cfg после остальных [include]: [include mcu_update.cfg]")

    def install(self) -> int:
        self.checks()
        self.step_rights()
        self.step_unit()
        self.step_asvc_and_dropins()
        if self.o.with_macro:
            self.step_macro()
        ui.step("Готово")
        ui.info("В Fluidd: меню питания ⏻ вверху справа -> %s -> Start." % self.SERVICE)
        ui.info("Лог: %s/logs/klipper_mcu_update.log (Fluidd: Файлы -> logs), journalctl -u %s"
                % (self.o.printer_data, self.SERVICE))
        return 0

    def run(self) -> int:
        if os.geteuid() == 0:
            raise VostokError("не запускайте от root: сервис должен работать от обычного пользователя")
        if not self.update_script.is_file():
            raise VostokError("нет %s" % self.update_script)
        if not self.unit_template.is_file():
            raise VostokError("нет %s" % self.unit_template)
        return self.uninstall() if self.o.uninstall else self.install()


MACRO_TEMPLATE = """\
# Запуск сборки и прошивки MCU (сервис @SERVICE@). Работает, когда Klipper в состоянии ready;
# если Klipper не стартует из-за версии MCU, запускайте из меню питания Fluidd.
[gcode_shell_command mcu_update]
command: systemctl --no-ask-password start --no-block @SERVICE@
timeout: 10.
verbose: True

[gcode_macro MCU_UPDATE]
description: Собрать и прошить MCU (Klipper будет остановлен)
gcode:
    RESPOND MSG="Запуск обновления прошивок MCU, Klipper будет остановлен"
    RUN_SHELL_COMMAND CMD=mcu_update
"""


def main_button(argv: List[str]) -> int:
    """Точка входа install_fluidd_button.sh."""
    res, rc = _parse(argv, {"--printer-data": "printer_data", "--flash-args": "flash_args"},
                     {"--with-macro": "with_macro", "--uninstall": "uninstall", "--dry-run": "dry_run"},
                     USAGE_BUTTON, INSTALL_DIR)
    if rc is not None:
        return rc
    o = ButtonOptions(
        printer_data=str(res["printer_data"]) if "printer_data" in res
        else _env("PRINTER_DATA", _home() + "/printer_data"),
        flash_args=str(res.get("flash_args", "")),
        with_macro=bool(res.get("with_macro")), uninstall=bool(res.get("uninstall")),
        dry_run=bool(res.get("dry_run")), yes=bool(res.get("yes")),
        klipper_dir=_env("KLIPPER_DIR", _home() + "/klipper"),
        katapult_dir=_env("KATAPULT_DIR", _home() + "/katapult"),
        moonraker_url=_env("MOONRAKER_URL", "http://localhost:7125"))
    ui.set_options(yes=o.yes, dry_run=o.dry_run)
    return FluiddButton(o).run()


# --------------------------------------------------------------------------- тема Fluidd

@dataclass
class FluiddThemeOptions:
    printer_data: str = ""
    fluidd_dir: str = ""
    moonraker_url: str = ""
    activate: bool = True
    logo_copy: bool = False
    force: bool = False
    uninstall: bool = False
    dry_run: bool = False
    yes: bool = False


class FluiddTheme:
    """install_fluidd_theme.sh: пресет и стили темы K3D VOSTOK в Fluidd."""

    LOGO_NAME = "logo_vostok.svg"

    def __init__(self, opts: FluiddThemeOptions, install_dir: Path = INSTALL_DIR,
                 http: Callable = http_request, prog: Optional[str] = None) -> None:
        self.o = opts
        self.install_dir = Path(install_dir)
        self.http = http
        self.prog = prog or _prog("install_fluidd_theme.sh", self.install_dir)
        self.src = self.install_dir / "fluidd-theme"
        self.theme_dir = Path(opts.printer_data) / "config" / ".fluidd-theme"
        self.fluidd_cfg = Path(opts.fluidd_dir) / "config.json"
        self.logo_src = self.LOGO_NAME if opts.logo_copy else "server/files/config/.fluidd-theme/%s" % self.LOGO_NAME
        self.db_url = "%s/server/database/item" % opts.moonraker_url
        self.db_theme_url = "%s?namespace=fluidd&key=uiSettings.theme" % self.db_url

    # -- база Moonraker

    def db_get_theme(self) -> Optional[object]:
        """Значение uiSettings.theme из базы Moonraker; None, если нет/ошибка."""
        body = self.http("GET", self.db_theme_url, None, 5)
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))["result"]["value"]
        except (ValueError, KeyError, TypeError):
            return None

    def db_theme_logo(self) -> str:
        """Путь к логотипу активной темы (пусто, если тема не задана)."""
        theme = self.db_get_theme()
        if theme is None:
            return ""
        logo = theme.get("logo") if isinstance(theme, dict) else None
        src = logo.get("src", "") if isinstance(logo, dict) else ""
        return str(src or "")

    def is_ours(self, logo: str) -> bool:
        """Логотип относится к нам, если называется logo_vostok.svg."""
        return logo.endswith(self.LOGO_NAME)

    # -- config.json Fluidd

    def edit_fluidd_cfg(self, mode: str, preset: Dict[str, object]) -> str:
        """Правка themePresets в config.json: add|remove. Резервная копия + атомарная запись.
        Возвращает «обновлён» или «без изменений»."""
        path = self.fluidd_cfg
        try:
            with open(str(path), encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            raise VostokError("не удалось прочитать %s: %s" % (path, e))
        if not isinstance(cfg, dict):
            raise VostokError("%s: ожидался JSON-объект" % path)
        lst = cfg.setdefault("themePresets", [])
        rest = [p for p in lst if p.get("name") != preset["name"]]
        new = rest + [preset] if mode == "add" else rest
        if mode == "add" and lst == new:
            return "без изменений"
        if mode == "remove" and len(rest) == len(lst):
            return "без изменений"
        cfg["themePresets"] = new
        cfgfile.atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", backup=True)
        return "обновлён"

    def preset(self) -> Dict[str, object]:
        try:
            with open(str(self.src / "preset.json"), encoding="utf-8") as f:
                p = json.load(f)
            p["logo"]["src"] = self.logo_src
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise VostokError("не удалось прочитать %s: %s" % (self.src / "preset.json", e))
        return p

    # -- удаление

    def uninstall(self) -> int:
        dry = self.o.dry_run
        ui.step("Удаление темы %s" % THEME_NAME)
        if self.fluidd_cfg.is_file():
            if dry:
                ui.info("[dry-run] убрать пресет из %s" % self.fluidd_cfg)
            else:
                try:
                    ui.info("config.json: %s" % self.edit_fluidd_cfg("remove", {"name": THEME_NAME}))
                except VostokError as e:
                    ui.warn(str(e))
        cur = self.db_theme_logo()
        if cur and self.is_ours(cur):
            if dry:
                ui.info("[dry-run] DELETE uiSettings.theme (вернуть тему по умолчанию)")
            elif self.http("DELETE", self.db_theme_url, None, 10) is not None:
                ui.ok("активная тема сброшена на стандартную")
            else:
                ui.warn("не удалось сбросить тему, выберите другую в Настройки -> Тема")
        css = self.theme_dir / "custom.css"
        if css.is_file() and _first_line_has(css, THEME_MARK):
            if dry:
                ui.info("[dry-run] rm %s" % css)
            else:
                _rm(css)
                ui.ok("удалён custom.css")
        for name in (self.LOGO_NAME, "background.png"):
            f = self.theme_dir / name
            if not f.is_file():
                continue
            if dry:
                ui.info("[dry-run] rm %s" % f)
            else:
                _rm(f)
                ui.ok("удалён %s" % name)
        if not dry:
            try:
                os.rmdir(str(self.theme_dir))  # rmdir --ignore-fail-on-non-empty
            except OSError:
                pass
        copy = Path(self.o.fluidd_dir) / self.LOGO_NAME
        if copy.is_file():
            if dry:
                ui.info("[dry-run] rm %s" % copy)
            else:
                _rm(copy)
        ui.info("Обновите вкладку браузера (Ctrl+F5).")
        return 0

    # -- установка

    def checks(self) -> None:
        o = self.o
        ui.step("Проверки")
        if not all((self.src / n).is_file() for n in (self.LOGO_NAME, "custom.css", "preset.json")):
            raise VostokError("нет файлов темы в %s" % self.src)
        if not self.fluidd_cfg.is_file():
            raise VostokError("нет %s: Fluidd не установлен? (--fluidd-dir)" % self.fluidd_cfg)
        try:
            with open(str(self.fluidd_cfg), encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError):
            raise VostokError("%s не разобрать как JSON" % self.fluidd_cfg)
        if not os.path.isdir(os.path.join(o.printer_data, "config")):
            raise VostokError("нет каталога %s/config (--printer-data)" % o.printer_data)
        if o.activate and self.http("GET", "%s/server/info" % o.moonraker_url, None, 5) is None:
            raise VostokError("Moonraker недоступен (%s), либо запустите с --no-activate" % o.moonraker_url)
        ui.ok("проверки пройдены")

    def step_files(self) -> None:
        o = self.o
        ui.step("Файлы темы в %s" % self.theme_dir)
        if o.dry_run:
            ui.info("[dry-run] скопировать %s и custom.css в %s" % (self.LOGO_NAME, self.theme_dir))
            return
        self.theme_dir.mkdir(parents=True, exist_ok=True)
        _install_file(self.src / self.LOGO_NAME, self.theme_dir / self.LOGO_NAME)
        ui.ok("логотип: %s" % (self.theme_dir / self.LOGO_NAME))
        dst = self.theme_dir / "custom.css"
        src_css = self.src / "custom.css"
        if (not dst.is_file() or _same_file(src_css, dst) or _first_line_has(dst, THEME_MARK) or o.force):
            # файл свой (или совпадает, или перезапись разрешена): при --force сохраняем чужую версию
            if dst.is_file() and not _first_line_has(dst, THEME_MARK):
                cfgfile.backup_file(dst)
            _install_file(src_css, dst)
            ui.ok("стили: %s" % dst)
        else:
            ui.warn("%s уже есть и создан не нами, не перезаписываю (добавьте стили вручную из %s "
                    "или запустите с --force)" % (dst, src_css))
        if o.logo_copy:
            _install_file(self.src / self.LOGO_NAME, Path(o.fluidd_dir) / self.LOGO_NAME)
            ui.ok("логотип скопирован в %s (после обновления Fluidd запустите скрипт ещё раз)" % o.fluidd_dir)

    def step_preset(self) -> None:
        ui.step("Пресет в %s" % self.fluidd_cfg)
        if self.o.dry_run:
            ui.info('[dry-run] добавить пресет "%s" (logo.src=%s)' % (THEME_NAME, self.logo_src))
        else:
            ui.info(self.edit_fluidd_cfg("add", self.preset()))

    def step_activate(self) -> None:
        o = self.o
        activate = True
        ui.step("Включение темы")
        cur = self.db_theme_logo()
        if cur and not self.is_ours(cur) and not o.force:
            if not ui.confirm("В Fluidd уже выбрана другая тема (%s). Заменить на %s?" % (cur, THEME_NAME),
                              need=False):
                ui.warn('тему не меняю; выберите "%s" в Настройки -> Тема' % THEME_NAME)
                activate = False
        if not activate:
            return
        p = self.preset()
        value = json.dumps({"namespace": "fluidd", "key": "uiSettings.theme",
                            "value": {"color": p["color"], "isDark": p["isDark"],
                                      "logo": {"src": self.logo_src}, "backgroundLogo": True}})
        if o.dry_run:
            ui.info("[dry-run] POST %s %s" % (self.db_url, value))
        else:
            if self.http("POST", self.db_url, value.encode("utf-8"), 10) is None:
                raise VostokError("не удалось записать тему в базу Moonraker")
            ui.ok("тема включена")

    def install(self) -> int:
        self.checks()
        self.step_files()
        self.step_preset()
        if self.o.activate:
            self.step_activate()
        ui.step("Готово")
        ui.info("Обновите вкладку Fluidd (Ctrl+F5). Пресет «%s» также доступен в Настройки -> Тема." % THEME_NAME)
        ui.info("Удалить: %s --uninstall" % self.prog)
        return 0

    def run(self) -> int:
        _check_not_root()
        return self.uninstall() if self.o.uninstall else self.install()


def _rm(path: Path) -> None:
    """``rm -f``."""
    try:
        os.unlink(str(path))
    except FileNotFoundError:
        pass


def _same_file(a: Path, b: Path) -> bool:
    """``cmp -s``."""
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def main_theme(argv: List[str]) -> int:
    """Точка входа install_fluidd_theme.sh."""
    res, rc = _parse(argv, {"--printer-data": "printer_data", "--fluidd-dir": "fluidd_dir"},
                     {"--no-activate": "no_activate", "--logo-copy": "logo_copy", "--force": "force",
                      "--uninstall": "uninstall", "--dry-run": "dry_run"},
                     USAGE_THEME, INSTALL_DIR)
    if rc is not None:
        return rc
    o = FluiddThemeOptions(
        printer_data=str(res["printer_data"]) if "printer_data" in res
        else _env("PRINTER_DATA", _home() + "/printer_data"),
        fluidd_dir=str(res["fluidd_dir"]) if "fluidd_dir" in res else _env("FLUIDD_DIR", _home() + "/fluidd"),
        moonraker_url=_env("MOONRAKER_URL", "http://localhost:7125"),
        activate=not res.get("no_activate"), logo_copy=bool(res.get("logo_copy")),
        force=bool(res.get("force")), uninstall=bool(res.get("uninstall")),
        dry_run=bool(res.get("dry_run")), yes=bool(res.get("yes")))
    ui.set_options(yes=o.yes, dry_run=o.dry_run)
    return FluiddTheme(o).run()


# --------------------------------------------------------------------------- тема KlipperScreen

KS_SAVED_MARK = "#~# --- Do not edit below this line. This section is auto generated --- #~#"


def edit_ks_conf(path, mode: str, theme: str, base: str) -> Tuple[str, str]:
    """Правка KlipperScreen.conf: mode set|reset. Значение theme сначала ищется в машинном блоке (#~#),
    он перекрывает пользовательскую часть; иначе правится/добавляется [main] в пользовательской части.
    Возвращает (текущая_тема, «обновлён»|«без изменений»). Резервная копия + атомарная запись."""
    path = str(path)
    lines = []  # type: List[str]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    try:
        cut = lines.index(KS_SAVED_MARK)
    except ValueError:
        cut = len(lines)
    user, saved = lines[:cut], lines[cut:]
    want = theme if mode == "set" else base

    def find(block: List[str], prefix: str) -> Optional[int]:
        sec = None
        for i, ln in enumerate(block):
            s = ln[len(prefix):].strip() if prefix and ln.startswith(prefix) else ln.strip()
            m = re.match(r"^\[(.+)\]$", s)
            if m:
                sec = m.group(1)
                continue
            if sec == "main" and re.match(r"^theme\s*[=:]", s):
                return i
        return None

    def val(ln: str, prefix: str) -> str:
        return ln[len(prefix):].split("=", 1)[-1].strip() if "=" in ln else ""

    cur = ""
    si = find(saved, "#~# ")
    ui_ = find(user, "")
    if si is not None:
        cur = val(saved[si], "#~# ")
    elif ui_ is not None:
        cur = val(user[ui_], "")
    print_cur = cur or base
    if cur == want:
        return print_cur, "без изменений"
    if mode == "reset" and cur != theme:
        return print_cur, "без изменений"
    if si is not None:
        saved[si] = "#~# theme = " + want
    if ui_ is not None:
        user[ui_] = "theme = " + want
    if si is None and ui_ is None:
        mi = next((i for i, ln in enumerate(user) if ln.strip() == "[main]"), None)
        if mi is None:
            user = ["[main]", "theme = " + want, ""] + user
        else:
            user.insert(mi + 1, "theme = " + want)
    cfgfile.atomic_write(path, "\n".join(user + saved) + "\n", backup=True)
    return print_cur, "обновлён"


def current_ks_theme(path) -> str:
    """Значение theme в [main] (машинный блок приоритетнее), пусто если не задано."""
    path = str(path)
    if not os.path.exists(path):
        return ""
    theme = ""
    sec = None
    saved = False
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if ln.startswith("#~# ---"):
                saved = True
                continue
            if ln.startswith("#~#"):
                ln = ln[3:].strip()
            elif saved:
                continue
            s = ln.strip()
            m = re.match(r"^\[(.+)\]$", s)
            if m:
                sec = m.group(1)
                continue
            m = re.match(r"^theme\s*[=:]\s*(\S+)", s)
            if sec == "main" and m:
                theme = m.group(1)
    return theme


@dataclass
class KsThemeOptions:
    printer_data: str = ""
    ks_dir: str = ""
    font_dir: str = ""
    activate: bool = True
    force: bool = False
    uninstall: bool = False
    dry_run: bool = False
    yes: bool = False


class KlipperScreenTheme:
    """install_klipperscreen_theme.sh: тема K3D VOSTOK для KlipperScreen."""

    THEME_ID = "vostok"
    BASE_THEME = "material-dark"
    FONT_GLOB = "Tektur*.ttf"

    def __init__(self, opts: KsThemeOptions, install_dir: Path = INSTALL_DIR,
                 runner: Optional[Runner] = None, prog: Optional[str] = None) -> None:
        self.o = opts
        self.install_dir = Path(install_dir)
        self.runner = runner or Runner()
        self.prog = prog or _prog("install_klipperscreen_theme.sh", self.install_dir)
        self.src = self.install_dir / "klipperscreen-theme"
        self.styles_dir = Path(opts.ks_dir) / "styles"
        self.dst = self.styles_dir / self.THEME_ID
        self.ks_conf = Path(opts.printer_data) / "config" / "KlipperScreen.conf"

    def is_ours(self) -> bool:
        """Каталог темы создан нами (маркер в первой строке style.css)."""
        css = self.dst / "style.css"
        return css.is_file() and _first_line_has(css, THEME_MARK)

    def _fc_cache(self) -> bool:
        """fc-cache -f FONT_DIR; True - успех."""
        return self.runner.run(["fc-cache", "-f", self.o.font_dir], check=False, capture=True).returncode == 0

    def _fonts(self) -> List[str]:
        return sorted(glob.glob(os.path.join(self.o.font_dir, self.FONT_GLOB)))

    def uninstall(self) -> int:
        o = self.o
        dry = o.dry_run
        ui.step("Удаление темы %s" % THEME_NAME)
        if self.dst.is_dir():
            if self.is_ours():
                if dry:
                    ui.info("[dry-run] rm -r %s" % self.dst)
                else:
                    _rm_tree(self.dst)
                    ui.ok("удалён %s" % self.dst)
            else:
                ui.warn("%s создан не нами, не удаляю" % self.dst)
        if self.ks_conf.is_file():
            if dry:
                ui.info("[dry-run] theme = %s в %s, если выбран %s" % (self.BASE_THEME, self.ks_conf, self.THEME_ID))
            else:
                _, result = edit_ks_conf(self.ks_conf, "reset", self.THEME_ID, self.BASE_THEME)
                ui.info("KlipperScreen.conf: %s" % result)
        for f in self._fonts():
            if not os.path.isfile(f):
                continue
            if dry:
                ui.info("[dry-run] rm %s" % f)
            else:
                _rm(Path(f))
                ui.ok("удалён шрифт %s" % os.path.basename(f))
        if not dry and shutil.which("fc-cache"):
            self._fc_cache()
        ui.info("Перезапустите KlipperScreen: sudo systemctl restart KlipperScreen")
        return 0

    def checks(self) -> None:
        o = self.o
        ui.step("Проверки")
        for f in ("style.css", "style.conf", "images/klipper.svg"):
            if not (self.src / f).is_file():
                raise VostokError("нет %s" % (self.src / f))
        if not glob.glob(str(self.src / "fonts" / self.FONT_GLOB)):
            raise VostokError("нет шрифта Tektur в %s/fonts" % self.src)
        if not (self.styles_dir / self.BASE_THEME / "images").is_dir():
            raise VostokError("нет %s: KlipperScreen не установлен? (--ks-dir)" % (self.styles_dir / self.BASE_THEME))
        if not shutil.which("fc-cache"):
            ui.warn("нет fc-cache (fontconfig): шрифт Tektur может не подхватиться")
        if self.dst.is_dir() and not self.is_ours() and not o.force:
            raise VostokError("%s уже есть и создан не нами (используйте --force, чтобы перезаписать)" % self.dst)
        if o.activate and not os.path.isdir(os.path.join(o.printer_data, "config")):
            raise VostokError("нет каталога %s/config (--printer-data) или запустите с --no-activate"
                              % o.printer_data)
        ui.ok("проверки пройдены")

    def step_theme(self) -> None:
        ui.step("Тема в %s" % self.dst)
        if self.o.dry_run:
            ui.info("[dry-run] собрать %s: иконки из %s + klipper.svg, style.css, style.conf"
                    % (self.dst, self.BASE_THEME))
            return
        new = Path(str(self.dst) + ".new")
        _rm_tree(new)
        (new / "images").mkdir(parents=True)
        for d in (self.styles_dir / self.BASE_THEME / "images", self.src / "images"):
            for f in sorted(d.iterdir()):
                if f.is_file():
                    shutil.copy2(str(f), str(new / "images" / f.name))
        _install_file(self.src / "style.css", new / "style.css")
        _install_file(self.src / "style.conf", new / "style.conf")
        _rm_tree(self.dst)
        os.rename(str(new), str(self.dst))
        count = sum(1 for _, _, fs in os.walk(str(self.dst / "images")) for _f in fs)
        ui.ok("тема: %s (%d иконок)" % (self.dst, count))

    def step_font(self) -> None:
        o = self.o
        ui.step("Шрифт Tektur в %s" % o.font_dir)
        if o.dry_run:
            ui.info("[dry-run] скопировать %s/fonts/%s и OFL.txt, fc-cache -f" % (self.src, self.FONT_GLOB))
            return
        os.makedirs(o.font_dir, exist_ok=True)
        for f in sorted(glob.glob(str(self.src / "fonts" / self.FONT_GLOB))):
            _install_file(Path(f), Path(o.font_dir) / os.path.basename(f))
        ofl = self.src / "fonts" / "OFL.txt"
        if ofl.is_file():
            _install_file(ofl, Path(o.font_dir) / "Tektur-OFL.txt")
        if shutil.which("fc-cache") and not self._fc_cache():
            ui.warn("fc-cache завершился с ошибкой")
        ui.ok("шрифт установлен")

    def step_activate(self) -> None:
        o = self.o
        activate = True
        ui.step("Включение темы")
        cur = current_ks_theme(self.ks_conf)
        if cur and cur != self.THEME_ID and cur != self.BASE_THEME and not o.force:
            # с -y чужую тему без --force не меняем: установщик всегда зовёт скрипт с -y
            if o.yes or not ui.confirm("В KlipperScreen выбрана другая тема (%s). Заменить на %s?"
                                       % (cur, THEME_NAME), need=False):
                ui.warn('тему не меняю; выберите "%s" в Настройки -> Тема' % self.THEME_ID)
                activate = False
        if not activate:
            return
        if o.dry_run:
            ui.info("[dry-run] theme = %s в %s" % (self.THEME_ID, self.ks_conf))
        else:
            old, result = edit_ks_conf(self.ks_conf, "set", self.THEME_ID, self.BASE_THEME)
            ui.ok("KlipperScreen.conf: %s (была тема: %s)" % (result, old))

    def install(self) -> int:
        self.checks()
        self.step_theme()
        self.step_font()
        if self.o.activate:
            self.step_activate()
        ui.step("Готово")
        ui.info("Перезапустите KlipperScreen: sudo systemctl restart KlipperScreen")
        ui.info('(или выберите тему "%s" в Настройки -> Тема — применяется сразу).' % self.THEME_ID)
        ui.info("Удалить: %s --uninstall" % self.prog)
        return 0

    def run(self) -> int:
        _check_not_root()
        return self.uninstall() if self.o.uninstall else self.install()


def _rm_tree(path: Path) -> None:
    """``rm -rf``."""
    if path.is_symlink() or path.is_file():
        _rm(path)
    elif path.is_dir():
        shutil.rmtree(str(path))


def main_ks_theme(argv: List[str]) -> int:
    """Точка входа install_klipperscreen_theme.sh."""
    res, rc = _parse(argv, {"--ks-dir": "ks_dir", "--printer-data": "printer_data"},
                     {"--no-activate": "no_activate", "--force": "force", "--uninstall": "uninstall",
                      "--dry-run": "dry_run"},
                     USAGE_KS, INSTALL_DIR)
    if rc is not None:
        return rc
    o = KsThemeOptions(
        printer_data=str(res["printer_data"]) if "printer_data" in res
        else _env("PRINTER_DATA", _home() + "/printer_data"),
        ks_dir=str(res["ks_dir"]) if "ks_dir" in res else _env("KS_DIR", _home() + "/KlipperScreen"),
        font_dir=_env("FONT_DIR", _home() + "/.local/share/fonts"),
        activate=not res.get("no_activate"), force=bool(res.get("force")),
        uninstall=bool(res.get("uninstall")), dry_run=bool(res.get("dry_run")), yes=bool(res.get("yes")))
    ui.set_options(yes=o.yes, dry_run=o.dry_run)
    return KlipperScreenTheme(o).run()
