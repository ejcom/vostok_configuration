"""Хост установщика: модель данных (Options/Env/Results), проверки окружения, пакеты, KIAUH, форк Klipper,
интерфейс CAN, ожидание Moonraker (бывшие функции install_vostok.sh).

Здесь нет прошивки плат (flashing.py) и порядка этапов (install.py).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

from . import VostokError, cfgfile, firmware, hardware, ui, update
from . import configurator as cf
from .configurator import Hardware, McuValues
from .state import Device
from .system import Runner

PACKAGES = ["git", "curl", "python3", "python3-serial", "python3-venv", "python3-dev", "virtualenv", "make",
            "dfu-util", "gcc-arm-none-eabi", "binutils-arm-none-eabi", "libnewlib-arm-none-eabi",
            "libusb-1.0-0", "iproute2", "usbutils"]

BOOTSTRAP_COMMANDS = ["sudo", "apt-get", "dpkg", "systemctl", "uname", "awk", "sed", "grep", "sort", "tr", "cut",
                      "head", "tail", "mktemp", "xargs", "tar", "df"]

CAN_IFACE_FILE = "/etc/network/interfaces.d/can0"
CAN_IFACE_BODY = "allow-hotplug can0\niface can0 can static\n    bitrate 1000000\n    up ip link set can0 txqueuelen 128\n"
NETWORKD_NETWORK = "/etc/systemd/network/80-can0.network"
NETWORKD_LINK = "/etc/systemd/network/80-can0.link"


# ------------------------------------------------------------------ модель данных

@dataclass
class Options:
    """Опции командной строки install_vostok.sh (бывшие OPT_* и флаги)."""
    conf: cf.Options = field(default_factory=cf.Options)    # main, heads, alps, config_source, electronics, drivers, ...
    dry_run: bool = False
    only_detect: bool = False
    skip_software: bool = False
    skip_flash: bool = False
    skip_config: bool = False
    skip_button: bool = False
    skip_theme: bool = False
    upgrade: bool = False
    skip_boards: List[str] = field(default_factory=list)   # alps|alps0|alps1|main|heads
    reflash: bool = False
    main_flash: str = ""            # dfu|katapult
    heads_flash: str = ""           # dfu|can
    check_can: bool = False
    yes: bool = False

    def board_skipped(self, name: str) -> bool:
        """Задан ли --skip-board для этой платы."""
        return name in self.skip_boards


@dataclass
class Env:
    """Пути, адреса и пороги из окружения (имена переменных и значения по умолчанию как в bash)."""
    cfg: update.Config                      # каталоги ПО, прошивки, devices.tsv, by-id, Moonraker
    conf_env: cf.Env                        # окружение конфигуратора (printer_data, источник конфигурации)
    home: str
    install_dir: Path
    moonraker_dir: str
    klipper_repo_url: str
    klipper_branch: str
    katapult_repo_url: str
    kiauh_repo_url: str
    min_free_mb: int = 2048
    min_mem_mb: int = 1024
    kernel_config: str = ""
    user_groups: str = ""
    user_groups_db: str = ""

    @classmethod
    def from_environ(cls, environ=None) -> "Env":
        e = os.environ if environ is None else environ
        home = e.get("HOME") or os.path.expanduser("~")
        cfg = update.Config.from_env(e)
        conf_env = cf.Env.from_environ(e)
        if not e.get("LOG_FILE"):
            conf_env.log_file = conf_env.printer_data / "logs" / "vostok_install.log"
        cfg = replace(cfg, log_file=str(conf_env.effective_log_file), devices_file=str(conf_env.devices_file))

        def num(name: str, default: int) -> int:
            try:
                return int(e.get(name) or default)
            except ValueError:
                return default

        return cls(
            cfg=cfg, conf_env=conf_env, home=home, install_dir=cfg.install_dir,
            moonraker_dir=e.get("MOONRAKER_DIR") or home + "/moonraker",
            klipper_repo_url=e.get("KLIPPER_REPO_URL") or "https://github.com/dmbutyugin/klipper",
            klipper_branch=e.get("KLIPPER_BRANCH") or "generic-cartesian",
            katapult_repo_url=e.get("KATAPULT_REPO_URL") or "https://github.com/Arksine/katapult",
            kiauh_repo_url=e.get("KIAUH_REPO_URL") or "https://github.com/dw-0/kiauh",
            min_free_mb=num("MIN_FREE_MB", 2048), min_mem_mb=num("MIN_MEM_MB", 1024),
            kernel_config=e.get("KERNEL_CONFIG") or "", user_groups=e.get("USER_GROUPS") or "",
            user_groups_db=e.get("USER_GROUPS_DB") or "")

    # --- короткие имена
    @property
    def klipper_dir(self) -> str:
        return self.cfg.klipper_dir

    @property
    def klippy_env(self) -> str:
        return self.cfg.klippy_env

    @property
    def katapult_dir(self) -> str:
        return self.cfg.katapult_dir

    @property
    def kiauh_dir(self) -> str:
        return self.cfg.kiauh_dir

    @property
    def configs_dir(self) -> Path:
        return Path(self.cfg.configs_dir)

    @property
    def byid_dir(self) -> str:
        return self.cfg.byid_dir

    @property
    def can_iface(self) -> str:
        return self.cfg.can_iface

    @property
    def devices_file(self) -> Path:
        return Path(self.cfg.devices_file)

    @property
    def printer_cfg_dir(self) -> Path:
        return self.conf_env.printer_cfg_dir

    @property
    def log_file(self) -> Path:
        return self.conf_env.effective_log_file


@dataclass
class Results:
    """Итоги прошивки (бывшие RES_*, FLASH_FAILED, HEADS_SKIP …)."""
    mcu: McuValues = field(default_factory=McuValues)         # serial/uuid для devices.tsv и printer.cfg
    failed: List[str] = field(default_factory=list)           # "плата: причина"
    skipped: List[str] = field(default_factory=list)          # пропущены по просьбе или как уже прошитые
    head_uuid_src: List[str] = field(default_factory=lambda: ["", ""])   # uid|bus|пусто
    head_dfu_done: List[bool] = field(default_factory=lambda: [False, False])
    heads_skip: bool = False         # платы голов уже прошиты, этапы katapult/Klipper по CAN пропускаются
    heads_way: str = "dfu"           # dfu (на столе) | can (в собранном принтере)
    prev_devices: List[Device] = field(default_factory=list)  # devices.tsv прошлого запуска (до перезаписи)

    def prev_keys(self, cfg_name: str) -> List[str]:
        """Ключи (serial/uuid) из devices.tsv прошлого запуска для конфига сборки, по порядку."""
        return [d.key for d in self.prev_devices if d.cfg == cfg_name] if cfg_name else []


# ------------------------------------------------------------------ вспомогательное

def uname(runner: Runner, arg: str) -> str:
    """Вывод ``uname <arg>`` (через Runner, чтобы тесты могли подменить)."""
    return runner.capture(["uname", arg], readonly=True, quiet=True)


def read_os_release(path: str = "/etc/os-release") -> Dict[str, str]:
    """Переменные /etc/os-release (KEY=значение, кавычки снимаются); нет файла - пустой словарь."""
    res: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.rstrip("\n"))
                if m:
                    v = m.group(2).strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    res[m.group(1)] = v
    except OSError:
        pass
    return res


# ------------------------------------------------------------------ проверки окружения

class EnvChecks:
    """Блоки «Окружение», «Инструменты», «Требования схемы с мостом USB-CAN»: [ок] / [!] / [НЕТ] и итог."""

    def __init__(self, env: Env, opts: Options, runner: Runner) -> None:
        self.env, self.opts, self.runner = env, opts, runner
        self.problems: List[str] = []
        self.warnings: List[str] = []

    def item(self, kind: str, text: str) -> None:
        if kind == "ok":
            ui.info("  [ок]   " + text)
        elif kind == "warn":
            ui.info("  [!]    " + text)
            self.warnings.append(text)
        else:
            ui.info("  [НЕТ]  " + text)
            self.problems.append(text)

    def conclude(self, what: str) -> None:
        """Итог блока: при проблемах остановка (в --dry-run/--only-detect только предупреждение)."""
        if not self.problems:
            return
        if self.opts.dry_run or self.opts.only_detect:
            ui.warn("%s: найдено проблем: %d (при реальной установке скрипт остановится)" % (what, len(self.problems)))
            return
        ui.die("%s: найдено проблем: %d. Устраните их (подсказки выше) и запустите установку снова"
               % (what, len(self.problems)))

    def hw_steps_planned(self) -> bool:
        return not self.opts.skip_flash and not self.opts.dry_run and not self.opts.only_detect

    def _groups(self, argv: List[str]) -> List[str]:
        return self.runner.capture(argv, readonly=True, quiet=True).split()

    def check_dialout(self) -> None:
        env = self.env
        sess = env.user_groups.split() if env.user_groups else self._groups(["id", "-nG"])
        user = self.runner.capture(["id", "-un"], readonly=True, quiet=True)
        db = env.user_groups_db.split() if env.user_groups_db else self._groups(["id", "-nG", user])
        if "dialout" in sess:
            self.item("ok", "доступ к последовательным портам (группа dialout)")
        elif "dialout" in db:
            self.item("bad", "пользователь добавлен в группу dialout, но текущая сессия её не видит: выйдите и войдите "
                             "заново (или выполните newgrp dialout)")
        else:
            self.item("bad", "пользователь не в группе dialout (без неё нет доступа к /dev/serial/by-id): "
                             "sudo usermod -aG dialout %s, затем выйдите и войдите заново" % user)

    def _free_mb(self) -> str:
        out = self.runner.capture(["df", "-Pm", self.env.home], readonly=True, quiet=True)
        lines = out.split("\n")
        return lines[1].split()[3] if len(lines) > 1 and len(lines[1].split()) > 3 else ""

    @staticmethod
    def _mem_mb() -> int:
        total = 0
        try:
            with open("/proc/meminfo", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = re.match(r"^(MemTotal|SwapTotal):\s+(\d+)", line)
                    if m:
                        total += int(m.group(2))
        except OSError:
            return 0
        return total // 1024

    def check_bootstrap(self) -> None:
        """Блок «Окружение»: базовые утилиты, systemd, место, память, python3, терминал, группа dialout, порт 80."""
        env = self.env
        ui.step("Окружение")
        self.problems, self.warnings = [], []
        missing = [c for c in BOOTSTRAP_COMMANDS if not shutil.which(c)]
        if missing:
            self.item("bad", "нет команд: %s (нужна Debian-подобная система с apt и systemd)" % " ".join(missing))
        else:
            self.item("ok", "базовые утилиты, apt, dpkg, systemctl, sudo")
        if os.path.isdir("/run/systemd/system"):
            self.item("ok", "systemd запущен")
        else:
            self.item("bad", "systemd не запущен (службы klipper/moonraker ставятся как systemd-юниты; контейнеры и WSL "
                             "без systemd не подходят)")
        free = self._free_mb()
        if free.isdigit() and int(free) < env.min_free_mb:
            self.item("bad", "мало места в %s: %s МБ, нужно не менее %d МБ" % (env.home, free, env.min_free_mb))
        else:
            self.item("ok", "место на диске: %s МБ" % (free or "?"))
        mem = self._mem_mb()
        if mem < env.min_mem_mb:
            self.item("warn", "мало памяти (ОЗУ + swap): %d МБ, сборка и установка могут не завершиться "
                              "(рекомендуется от %d МБ)" % (mem, env.min_mem_mb))
        else:
            self.item("ok", "память (ОЗУ + swap): %d МБ" % mem)
        if shutil.which("python3"):
            ver = "%d.%d" % sys.version_info[:2]
            if sys.version_info >= (3, 8):
                self.item("ok", "python3 " + ver)
            else:
                self.item("bad", "python3 %s слишком старый, нужен 3.8 или новее (KIAUH, Klipper)" % ver)
        else:
            self.item("warn", "python3 не установлен (будет установлен на этапе пакетов)")
        if self.hw_steps_planned():
            if ui.have_tty():
                self.item("ok", "терминал для диалога")
            else:
                self.item("bad", "нет терминала: шаги с железом требуют ответов в диалоге (запустите в ssh/терминале или "
                                 "используйте --skip-flash)")
            self.check_dialout()
        if shutil.which("ss") and not os.path.isdir(os.path.join(env.home, "fluidd")):
            out = hardware.run_quiet(["ss", "-ltn"], self.runner)[1]
            if any(re.search(r"[:.]80[ \t\r\f\v]", ln) for ln in out.split("\n")) and \
                    hardware.run_quiet(["systemctl", "is-active", "--quiet", "nginx"], self.runner)[0] != 0:
                self.item("warn", "порт 80 занят другой программой: Fluidd (nginx) может не запуститься")
        self.conclude("Окружение")

    def check_tools(self, need_flash: bool, after_packages: bool) -> None:
        """Нужные команды и python-модули. after_packages - этап пакетов уже выполнен (или пропущен)."""
        self.problems, self.warnings = [], []
        st = "warn" if (not after_packages and not self.opts.skip_software) else "bad"
        reqs = [("python3", "python3", "скрипты, KIAUH"), ("git", "git", "клонирование репозиториев"),
                ("curl", "curl", "скачивание конфигурации"), ("tar", "tar", "распаковка архивов")]
        if need_flash:
            reqs += [("make", "make", "сборка прошивок"), ("arm-none-eabi-gcc", "gcc-arm-none-eabi", "компилятор прошивок"),
                     ("dfu-util", "dfu-util", "прошивка katapult по DFU"), ("lsusb", "usbutils", "обнаружение плат"),
                     ("ip", "iproute2", "интерфейс CAN")]
        pkgs: List[str] = []
        ui.step("Инструменты")
        for cmd, pkg, why in reqs:
            if shutil.which(cmd):
                self.item("ok", cmd)
            else:
                self.item(st, "нет %s (пакет %s): %s%s" % (cmd, pkg, why,
                                                            "; будет установлен на этапе пакетов" if st == "warn" else ""))
                pkgs.append(pkg)
        if shutil.which("python3"):
            if need_flash:
                if hardware.run_quiet(["python3", "-c", "import serial"], self.runner)[0] == 0:
                    self.item("ok", "python3: pyserial")
                else:
                    self.item(st, "нет python3-serial (pyserial): нужен flashtool.py")
                    pkgs.append("python3-serial")
            if not self.opts.skip_software:
                if hardware.run_quiet(["python3", "-c", "import venv, ensurepip"], self.runner)[0] == 0:
                    self.item("ok", "python3: venv")
                else:
                    self.item(st, "нет python3-venv: KIAUH не создаст окружение Klipper")
                    pkgs.append("python3-venv")
        if pkgs and st == "bad":
            ui.info("  Установить недостающее: sudo apt install " + " ".join(pkgs))
        self.conclude("Инструменты")

    def check_hw_requirements(self, hw: Hardware) -> None:
        """Требования схемы с платами голов: поддержка CAN в ядре и утилита ip."""
        if hw.heads == "none":
            return
        self.problems, self.warnings = [], []
        ui.step("Требования схемы с мостом USB-CAN")
        release = uname(self.runner, "-r")
        rc = hardware.kernel_can_support(self.env.kernel_config, release)
        if rc == 0:
            self.item("ok", "ядро %s поддерживает CAN и USB-CAN адаптеры (gs_usb)" % release)
        elif rc == 1:
            self.item("bad", "ядро %s собрано без CAN (нужны CONFIG_CAN, CONFIG_CAN_RAW, CONFIG_CAN_GS_USB): %s в режиме "
                             "моста USB-CAN работать не сможет. Нужно ядро с поддержкой CAN (gs_usb) либо сборка без плат "
                             "голов по CAN: --heads none" % (release, hw.main_short()))
        else:
            self.item("warn", "не удалось определить поддержку CAN в ядре (нет /proc/config.gz и /boot/config-*); "
                              "проверьте: modinfo gs_usb")
        if shutil.which("ip"):
            self.item("ok", "ip (iproute2)")
        else:
            self.item("bad", "нет ip (пакет iproute2): интерфейс can0 настроить нельзя")
        self.conclude("Требования схемы")


# ------------------------------------------------------------------ этап 0: предварительные проверки

def stage_preflight(env: Env, opts: Options, runner: Runner, checks: EnvChecks) -> None:
    ui.step("Проверки")
    if os.geteuid() == 0:
        ui.die("не запускайте от root; sudo спросит пароль сам")
    arch = uname(runner, "-m")
    if arch not in ("aarch64", "armv7l", "armv6l", "x86_64"):
        ui.warn("необычная архитектура " + arch)
    osr = read_os_release()
    if osr:
        ui.info("ОС: " + (osr.get("PRETTY_NAME") or "?"))
        if not (re.match(r"^(debian|ubuntu|armbian|raspbian|orangepi)$", osr.get("ID", ""))
                or "debian" in osr.get("ID_LIKE", "")):
            ui.warn("ОС не похожа на Debian/Ubuntu: apt и KIAUH могут не работать")
    if shutil.which("git"):
        if hardware.run_quiet(["git", "ls-remote", "-q", env.katapult_repo_url, "HEAD"], runner)[0] != 0:
            ui.die("нет доступа к github.com (проверьте интернет)")
    ui.ok("проверки пройдены")
    checks.check_bootstrap()


# ------------------------------------------------------------------ этап 1: пакеты

def stage_packages(env: Env, opts: Options, runner: Runner) -> None:
    ui.step("Пакеты")
    missing = [p for p in PACKAGES
               if hardware.run_quiet(["dpkg", "-s", p], runner)[0] != 0]
    if opts.upgrade:
        runner.run(["apt-get", "update"], sudo=True)
        runner.run(["apt-get", "-y", "upgrade"], sudo=True)
    elif missing:
        runner.run(["apt-get", "update"], sudo=True)
    if missing:
        ui.info("Устанавливаю: " + " ".join(missing))
        runner.run(["apt-get", "install", "-y"] + missing, sudo=True)
    else:
        ui.info("все нужные пакеты уже установлены")
    ui.ok("пакеты готовы")


# ------------------------------------------------------------------ этап 2: KIAUH, Klipper, Moonraker, Fluidd, katapult

def kiauh_cfg_with_repo(text: str, repo: str) -> str:
    """kiauh.cfg: в секции [klipper] единственный репозиторий ``repo`` (строки старых репозиториев удаляются)."""
    out: List[str] = []
    section: Optional[str] = None
    skipping = False
    for line in text.split("\n"):
        m = re.match(r"\[(.+)\]\s*$", line)
        if m:
            section, skipping = m.group(1), False
        if section == "klipper" and line.startswith("repositories:"):
            out.append("repositories:")
            out.append("    " + repo)
            skipping = True
            continue
        if skipping:
            if line.startswith((" ", "\t")) and line.strip():
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


class Software:
    """Установка и проверка ПО: KIAUH, форк Klipper, Moonraker, Fluidd, расширение gcode_shell_command, katapult."""

    def __init__(self, env: Env, opts: Options, runner: Runner) -> None:
        self.env, self.opts, self.runner = env, opts, runner

    def _git(self, *args: str) -> str:
        return hardware.run_quiet(["git", "-C", self.env.klipper_dir] + list(args), self.runner)[1]

    def kiauh_set_fork_repo(self) -> None:
        env = self.env
        repo = "%s, %s" % (env.klipper_repo_url, env.klipper_branch)
        if self.runner.dry_run:
            ui.info("[dry-run] kiauh.cfg: единственный репозиторий Klipper = %s, %s" % (env.klipper_repo_url, env.klipper_branch))
            return
        cfg = Path(env.kiauh_dir) / "kiauh.cfg"
        if not cfg.is_file():
            shutil.copyfile(str(Path(env.kiauh_dir) / "default.kiauh.cfg"), str(cfg))
        text = cfg.read_text(encoding="utf-8")
        cfgfile.atomic_write(cfg, kiauh_cfg_with_repo(text, repo), backup=False)

    def klipper_is_fork(self) -> bool:
        env = self.env
        if not os.path.isdir(os.path.join(env.klipper_dir, ".git")):
            return False
        rc, url = hardware.run_quiet(["git", "-C", env.klipper_dir, "remote", "get-url", "origin"], self.runner)
        if "dmbutyugin/klipper" not in url.lower():
            return False
        return self._git("rev-parse", "--abbrev-ref", "HEAD").rstrip("\n") == env.klipper_branch

    def switch_klipper_to_fork(self) -> None:
        env, run = self.env, self.runner.run
        ui.warn("%s не является форком %s (%s)" % (env.klipper_dir, env.klipper_repo_url, env.klipper_branch))
        if self._git("status", "--porcelain", "--untracked-files=no").strip("\n"):
            ui.die("в %s есть локальные изменения; зафиксируйте или откатите их и запустите снова" % env.klipper_dir)
        if not ui.ask_yn("Переключить %s на форк (локальная ветка будет заменена)?" % env.klipper_dir, "y"):
            ui.die("без форка VOSTOK работать не будет")
        g = ["git", "-C", env.klipper_dir]
        run(g + ["remote", "set-url", "origin", env.klipper_repo_url])
        run(g + ["fetch", "origin", env.klipper_branch])
        run(g + ["checkout", "-B", env.klipper_branch, "origin/" + env.klipper_branch])
        run(g + ["branch", "--set-upstream-to=origin/" + env.klipper_branch, env.klipper_branch])
        run([env.klippy_env + "/bin/pip", "install", "-q", "-r", env.klipper_dir + "/scripts/klippy-requirements.txt"])

    def kiauh_install(self, *args: str) -> None:
        ui.info("KIAUH: install " + " ".join(args))
        self.runner.run([self.env.kiauh_dir + "/kiauh.sh", "install"] + list(args))

    def stage_software(self) -> None:
        env, run = self.env, self.runner.run
        ui.step("KIAUH, Klipper (форк), Moonraker, Fluidd, katapult")
        if not os.path.isdir(os.path.join(env.kiauh_dir, ".git")):
            run(["git", "clone", env.kiauh_repo_url, env.kiauh_dir])
        else:
            ui.info("KIAUH уже установлен")

        if os.path.isdir(os.path.join(env.klipper_dir, ".git")):
            if self.klipper_is_fork():
                ui.info("Klipper: форк уже установлен (%s)" % firmware.host_version_or_empty(env.klipper_dir, self.runner))
            else:
                self.switch_klipper_to_fork()
        else:
            self.kiauh_set_fork_repo()
            self.kiauh_install("klipper", "--count", "1")
        if not os.path.isdir(os.path.join(env.moonraker_dir, ".git")):
            self.kiauh_install("moonraker", "--create-example-cfg")
        else:
            ui.info("Moonraker уже установлен")
        if not os.path.isdir(os.path.join(env.home, "fluidd")):
            self.kiauh_install("fluidd", "--install-config")
        else:
            ui.info("Fluidd уже установлен")

        # gcode_shell_command нужен макросам Input Shaping (гайд: KIAUH -> Extensions -> G-Code Shell Command, пример: N)
        extras = env.klipper_dir + "/klippy/extras"
        if not os.path.isfile(extras + "/gcode_shell_command.py"):
            asset = env.cfg.gcode_shell_asset
            if os.path.isfile(asset) or self.runner.dry_run:
                run(["cp", asset, extras + "/"])
                ui.info("установлено расширение gcode_shell_command")
            else:
                ui.warn("не найден %s: поставьте расширение через KIAUH -> Extensions" % asset)
        else:
            ui.info("gcode_shell_command уже установлен")

        if not os.path.isdir(os.path.join(env.katapult_dir, ".git")):
            run(["git", "clone", env.katapult_repo_url, env.katapult_dir])
        else:
            ui.info("katapult уже установлен")

        if not self.runner.dry_run:
            cp = run([env.klippy_env + "/bin/python", env.klipper_dir + "/klippy/klippy.py", "--import-test"],
                     check=False, capture=True)
            if cp.returncode != 0:
                ui.die("klippy --import-test не прошёл")
        ui.ok("программное обеспечение готово")


# ------------------------------------------------------------------ этап 4: интерфейс CAN

def stage_can(env: Env, opts: Options, hw: Hardware, runner: Runner) -> None:
    """Настройка интерфейса can0 (1 Мбит, txqueuelen 128): ifupdown или systemd-networkd."""
    if hw.heads == "none":
        return
    ui.step("Интерфейс CAN (%s)" % env.can_iface)
    dry = runner.dry_run
    if not dry:
        runner.run(["modprobe", "-a", "can", "can_raw", "gs_usb"], sudo=True, check=False, quiet=True)
    if hardware.run_quiet(["dpkg", "-s", "ifupdown"], runner)[0] == 0:
        f = Path(CAN_IFACE_FILE)
        try:
            configured = f.is_file() and "bitrate 1000000" in f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            configured = False
        if configured:
            ui.info("%s уже настроен" % f)
        else:
            ui.info("создаю %s (по гайду)" % f)
            if dry:
                ui.info("[dry-run] sudo tee %s <<< '%s'" % (f, CAN_IFACE_BODY))
            else:
                _sudo_write(runner, f, CAN_IFACE_BODY)
    else:
        ui.info("ifupdown не установлен: настраиваю systemd-networkd")
        if dry:
            ui.info("[dry-run] /etc/systemd/network/80-can0.network + .link (BitRate=1000000, TransmitQueueLength=128)")
        else:
            _sudo_write(runner, Path(NETWORKD_NETWORK), "[Match]\nName=can0\n\n[CAN]\nBitRate=1M\n")
            _sudo_write(runner, Path(NETWORKD_LINK), "[Match]\nOriginalName=can0\n\n[Link]\nTransmitQueueLength=128\n")
            runner.run(["systemctl", "enable", "systemd-networkd"], sudo=True, check=False, quiet=True)
    ui.ok("настройка CAN записана (интерфейс появится, когда будет прошит мост)")


def _sudo_write(runner: Runner, dest: Path, text: str) -> None:
    """Записать системный файл через ``sudo install -m 644`` (как ``sudo tee``: владелец root, права 644)."""
    fd, tmp = tempfile.mkstemp(prefix="vostok-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        runner.run(["install", "-m", "644", tmp, str(dest)], sudo=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------ Moonraker

def wait_moonraker(updater: update.Updater, tries: int = 60) -> bool:
    """Ждать Moonraker до ``tries`` секунд (после запуска служб он отвечает не сразу). Включает updater.moon.ok."""
    for _ in range(tries):
        if updater.moon.fetch("/server/info") is not None:
            updater.moon.ok = True
            return True
        time.sleep(1)
    updater.moon.ok = False
    return False
