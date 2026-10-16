"""Сборка прошивок Klipper, версия хоста и обёртки flashtool.py katapult.

Перенос из update_klipper_mcu.sh (host_version, norm_version, build_firmware, вызовы flashtool.py).
Расширяется A5 (сборка katapult, dfu-util).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import VostokError, ui
from .system import Runner

_CONFIG_MCU_RE = re.compile(r'^CONFIG_MCU="(.*)"$')


def host_version(klipper_dir, runner: Optional[Runner] = None) -> str:
    """Версия хоста: ``git describe --always --tags --long`` в каталоге klipper."""
    runner = runner or Runner()
    cp = runner.run(["git", "-C", str(klipper_dir), "describe", "--always", "--tags", "--long"],
                    capture=True, check=False, readonly=True)
    if cp.returncode != 0:
        raise VostokError("git describe в %s не удался" % klipper_dir)
    return (cp.stdout or "").rstrip("\n")


def host_version_or_empty(klipper_dir, runner: Optional[Runner] = None) -> str:
    """Как ``$(host_version)`` в bash: версия или пустая строка, если git describe не удался (сообщение git остаётся
    на экране). Выполняется и в dry-run (запрос состояния)."""
    runner = runner or Runner()
    cp = runner.run(["git", "-C", str(klipper_dir), "describe", "--always", "--tags", "--long"],
                    capture=True, check=False, readonly=True)
    return (cp.stdout or "").rstrip("\n") if cp.returncode == 0 else ""


def norm_version(v: str) -> str:
    """Убирает ``*`` (версия взята из журнала) и ``-dirty``."""
    if v.endswith("*"):
        v = v[:-1]
    if v.endswith("-dirty"):
        v = v[:-len("-dirty")]
    return v


def config_mcu(cfg_path) -> str:
    """Значение CONFIG_MCU из файла .config сборки (пустая строка, если нет файла/строки)."""
    try:
        with open(cfg_path, encoding="utf-8", errors="replace") as f:
            for line in f.read().split("\n"):
                m = _CONFIG_MCU_RE.match(line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def cpu_count() -> int:
    """Число доступных процессоров (как ``nproc``)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _tail(path: Path, n: int) -> None:
    """Последние n строк файла в stderr (``tail -n N file >&2``)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except OSError:
        return
    if lines and lines[-1] == "":
        lines.pop()
    sys.stderr.write("".join(ln + "\n" for ln in lines[-n:]))
    sys.stderr.flush()


def _make(runner: Runner, argv: List[str], log: Path, append: bool) -> int:
    """make с выводом (stdout+stderr) в файл; нет make - код 127. Вывод make не идёт на экран (как в bash)."""
    return runner.run(argv, check=False, stdout_file=log, append=append).returncode


def build_firmware(cfg, chip: str, *, klipper_dir, build_dir, firmware_dir, built: Dict[str, str],
                   runner: Optional[Runner] = None) -> str:
    """Собрать прошивку по конфигу ``cfg`` для чипа ``chip``; вернуть путь к bin в firmware_dir.

    ``built`` - кэш «конфиг -> bin» (повторно один конфиг не собирается). Сборка вне репозитория:
    KCONFIG_CONFIG и OUT указывают в build_dir/<ключ>. Ошибки - VostokError с теми же текстами, что в bash.
    """
    runner = runner or Runner()
    cfg = str(cfg)
    key = os.path.basename(cfg)[:-len(".config")] if cfg.endswith(".config") else os.path.basename(cfg)
    if built.get(cfg):
        return built[cfg]
    work = Path(build_dir) / key
    if runner.dry_run:
        # dry-run: ни каталогов, ни конфига не трогаем, make только печатается
        ui.info("[dry-run] сборка %s: make -C %s KCONFIG_CONFIG=%s OUT=%s" % (key, klipper_dir, work / ".config",
                                                                            work / "out") + "/")
        return str(Path(firmware_dir) / ("%s-%s.bin" % (key, host_version(klipper_dir, runner))))
    out = str(work / "out") + "/"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    Path(firmware_dir).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cfg, work / ".config")
    ui.info("сборка %s ..." % key)
    log = work / "make.log"
    mk = ["make", "-C", str(klipper_dir), "KCONFIG_CONFIG=%s" % (work / ".config"), "OUT=%s" % out]
    if _make(runner, mk + ["olddefconfig"], log, append=False) != 0:
        _tail(log, 20)
        raise VostokError("make olddefconfig (%s) не удался" % key)
    cfg_mcu = config_mcu(work / ".config")
    if cfg_mcu != chip:
        raise VostokError("конфиг %s собирает CONFIG_MCU=%s, а устройству нужен %s" % (cfg, cfg_mcu, chip))
    if _make(runner, mk + ["-j%d" % cpu_count()], log, append=True) != 0:
        _tail(log, 30)
        raise VostokError("сборка %s не удалась, лог: %s" % (key, log))
    binpath = Path(out) / "klipper.bin"
    if not binpath.is_file():
        raise VostokError("сборка %s не создала klipper.bin" % key)
    ver = host_version(klipper_dir, runner)
    dest = str(Path(firmware_dir) / ("%s-%s.bin" % (key, ver)))
    shutil.copyfile(binpath, dest)
    shutil.copyfile(work / ".config", cfg)   # olddefconfig мог добавить новые опции
    built[cfg] = dest
    ui.ok("собрано: %s (%d байт)" % (dest, binpath.stat().st_size))
    return dest


# ------------------------------------------------------------------ flashtool.py

def flashtool(katapult_dir, args: List[str], runner: Optional[Runner] = None) -> bool:
    """``python3 <katapult>/scripts/flashtool.py <args>``; вывод идёт на экран. True - код 0."""
    runner = runner or Runner()
    cp = runner.run(["python3", str(Path(katapult_dir) / "scripts" / "flashtool.py")] + list(args),
                    check=False)
    return cp.returncode == 0


def flash_usb(katapult_dir, dev: str, binpath: str, runner: Optional[Runner] = None) -> bool:
    """Прошивка USB-устройства: ``flashtool.py -d <dev> -f <bin>``."""
    ui.log("flashtool -d %s -f %s" % (dev, binpath))
    return flashtool(katapult_dir, ["-d", dev, "-f", binpath], runner)


def flash_can_node(katapult_dir, iface: str, uuid: str, binpath: str, runner: Optional[Runner] = None) -> bool:
    """Прошивка узла по CAN: ``flashtool.py -i <iface> -u <uuid> -f <bin>``."""
    ui.log("flashtool -i %s -u %s -f %s" % (iface, uuid, binpath))
    return flashtool(katapult_dir, ["-i", iface, "-u", uuid, "-f", binpath], runner)


def request_bootloader_can(katapult_dir, iface: str, uuid: str, runner: Optional[Runner] = None) -> bool:
    """Запрос загрузчика у моста по CAN: ``flashtool.py -i <iface> -u <uuid> -r``."""
    ui.log("flashtool -i %s -u %s -r (мост)" % (iface, uuid))
    return flashtool(katapult_dir, ["-i", iface, "-u", uuid, "-r"], runner)


# ------------------------------------------------------------------ katapult и dfu-util (install_vostok.sh)

def katapult_key(cfg) -> str:
    """Ключ конфига katapult: имя файла без ``.config``."""
    name = os.path.basename(str(cfg))
    return name[:-len(".config")] if name.endswith(".config") else name


def katapult_work_dir(build_dir, cfg) -> Path:
    """Каталог сборки katapult для конфига: <build_dir>/katapult-<ключ>."""
    return Path(build_dir) / ("katapult-" + katapult_key(cfg))


def build_katapult(cfg, *, katapult_dir, build_dir, runner: Optional[Runner] = None) -> str:
    """Собрать katapult вне репозитория; вернуть путь к katapult.bin (в dry-run - ожидаемый путь, без сборки).
    Ошибки - VostokError с теми же текстами, что в bash."""
    runner = runner or Runner()
    cfg = str(cfg)
    work = katapult_work_dir(build_dir, cfg)
    key = katapult_key(cfg)
    if not os.path.isfile(cfg):
        raise VostokError("нет конфига katapult: %s (создайте: tools/gen_configs.sh)" % cfg)
    binpath = work / "out" / "katapult.bin"
    if runner.dry_run:
        ui.info("[dry-run] сборка katapult (%s)" % key)
        return str(binpath)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cfg, work / ".config")
    ui.info("сборка katapult (%s) ..." % key)
    log = work / "make.log"
    mk = ["make", "-C", str(katapult_dir), "KCONFIG_CONFIG=%s" % (work / ".config"), "OUT=%s/" % (work / "out")]
    if _make(runner, mk + ["olddefconfig"], log, append=False) != 0:
        _tail(log, 20)
        raise VostokError("olddefconfig katapult (%s) не удался" % key)
    if _make(runner, mk + ["-j%d" % cpu_count()], log, append=True) != 0:
        _tail(log, 30)
        raise VostokError("сборка katapult (%s) не удалась, лог: %s" % (key, log))
    if not binpath.is_file():
        raise VostokError("сборка katapult (%s) не создала katapult.bin" % key)
    ui.ok("katapult собран: %s (%d байт)" % (binpath, binpath.stat().st_size))
    return str(binpath)


def dfu_run(runner: Runner, argv: List[str], sudo: bool = False) -> bool:
    """Запуск dfu-util (или make flash): вывод на экран и в журнал. Успехом считается запись данных
    («Download done»), даже если dfu-util вернул ошибку get_status после 100%: плата к этому моменту уже перезагрузилась."""
    cp = runner.run(argv, sudo=sudo, check=False, tee=True)
    out = cp.stdout or ""
    return "Download done" in out or "File downloaded successfully" in out
