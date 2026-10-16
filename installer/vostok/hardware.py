"""Оборудование хоста: устройства в by-id, DFU (lsusb/dfu-util), UID чипа, интерфейс CAN и устройства на шине.

Перенос из update_klipper_mcu.sh (by_id_chip/by_id_serial, can_iface_up, wait_for_device и поиск
usb-katapult_* в flash_can) и из install_vostok.sh / lib/vostok_config.sh (byid_find, dfu_*, show_usb_state,
bridge_usb_serial, can_uuids, bring_up_can, kernel_can_support ...).
Запросы состояния (lsusb, ip, dfu-util -l) идут через Runner с readonly=True: они выполняются и в dry-run.
"""
from __future__ import annotations

import glob
import gzip
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import can_uuid as can_uuid_mod, ui
from .system import Runner

# usb-Klipper_<чип>_<серийный номер>-if00 (как sed в bash: чип жадный, серийный без "_")
_BYID_RE = re.compile(r"^usb-Klipper_(.*)_([^_]*)-if[0-9]*$")


def run_quiet(argv: List[str], runner: Optional[Runner] = None) -> Tuple[int, str]:
    """Запрос состояния без вывода ошибок на экран (``2>/dev/null``): (код, stdout). Нет программы - код 127.
    Выполняется и в dry-run (readonly), потому что ничего не меняет."""
    runner = runner or Runner()
    cp = runner.run(argv, quiet=True, capture=True, check=False, readonly=True)
    return cp.returncode, cp.stdout or ""


def probe(runner: Optional[Runner], argv: Sequence[str]) -> Tuple[int, str]:
    """Запрос состояния: (код, stdout), stderr скрыт (``2>/dev/null``), в dry-run выполняется."""
    return run_quiet(list(argv), runner)


def by_id_chip(path: str) -> str:
    """Чип из имени usb-Klipper_<чип>_<серийный>-if00 (пустая строка, если имя не подходит)."""
    m = _BYID_RE.match(os.path.basename(path))
    return m.group(1) if m else ""


def by_id_serial(path: str) -> str:
    """Серийный номер из имени usb-Klipper_<чип>_<серийный>-if00 (пустая строка, если имя не подходит)."""
    m = _BYID_RE.match(os.path.basename(path))
    return m.group(2) if m else ""


def list_byid(byid_dir: str, prefix: str) -> List[str]:
    """Полные пути BYID_DIR/<prefix>* (существующие, с учётом ссылок), отсортированные как glob в bash."""
    try:
        names = sorted(n for n in os.listdir(byid_dir) if n.startswith(prefix))
    except OSError:
        return []
    return [os.path.join(byid_dir, n) for n in names if os.path.exists(os.path.join(byid_dir, n))]


def find_katapult(byid_dir: str, chip: str) -> Optional[str]:
    """Первое устройство BYID_DIR/usb-katapult_<чип>_* или None."""
    devs = list_byid(byid_dir, "usb-katapult_%s_" % chip)
    return devs[0] if devs else None


def can_iface_up(iface: str, runner: Optional[Runner] = None) -> bool:
    """Интерфейс CAN поднят: в выводе ``ip link show`` встречается ``UP`` (как ``grep -q UP`` в bash)."""
    rc, out = run_quiet(["ip", "link", "show", iface], runner)
    return rc == 0 and "UP" in out


def can_iface_exists(iface: str, runner: Optional[Runner] = None) -> bool:
    """Интерфейс существует (``ip link show`` успешен)."""
    return run_quiet(["ip", "link", "show", iface], runner)[0] == 0


def ifup(iface: str, runner: Optional[Runner] = None) -> None:
    """``sudo -n ifup <iface>`` без вывода; результат игнорируется (как в bash). В dry-run только печатается."""
    (runner or Runner()).run(["sudo", "-n", "ifup", iface], quiet=True, check=False)


def have_ip() -> bool:
    """Есть ли команда ip (пакет iproute2)."""
    return shutil.which("ip") is not None


def wait_for_device(path: str, seconds: int) -> bool:
    """Ждать появления пути до ``seconds`` секунд (опрос каждые 0.5 с). True - появился."""
    for _ in range(seconds * 2):
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    return False


def wait_for_katapult(byid_dir: str, chip: str, tries: int = 40) -> Optional[str]:
    """Ждать устройство usb-katapult_<чип>_* до ``tries`` * 0.5 с (20 с). Путь или None."""
    for _ in range(tries):
        dev = find_katapult(byid_dir, chip)
        if dev:
            return dev
        time.sleep(0.5)
    return None


def wait_for_can_iface(iface: str, tries: int = 40, runner: Optional[Runner] = None) -> bool:
    """Ждать появления интерфейса CAN до ``tries`` * 0.5 с (20 с); True - интерфейс есть."""
    for _ in range(tries):
        if can_iface_exists(iface, runner):
            return True
        time.sleep(0.5)
    return can_iface_exists(iface, runner)


# ------------------------------------------------------------------ USB / DFU (бывшие функции lib/vostok_config.sh)

def byid_find(byid_dir, pattern: str) -> List[str]:
    """Пути из каталога by-id по шаблону (glob), по возрастанию; битые ссылки не считаются."""
    found = sorted(glob.glob(os.path.join(glob.escape(str(byid_dir)), pattern)))
    return [f for f in found if os.path.exists(f)]


def serial_from_path(path: str) -> str:
    """Серийный номер из имени ``…usb-Klipper_<чип>_<serial>-if00`` (пусто, если имя другое)."""
    m = re.match(r"^.*usb-Klipper_[^_]*_(.*)-if00$", path)
    return m.group(1) if m else ""


def dfu_count(runner: Optional[Runner]) -> int:
    """Число устройств в режиме DFU (``lsusb -d 0483:df11 | wc -l``)."""
    return probe(runner, ["lsusb", "-d", "0483:df11"])[1].count("\n")


def dfu_family(runner: Optional[Runner]) -> str:
    """Семейство чипа в DFU по адресу Option Bytes: f0|f4|h7|g|unknown."""
    rc, out = probe(runner, ["sudo", "-n", "dfu-util", "-l"])
    if rc != 0:
        rc, out = probe(runner, ["dfu-util", "-l"])
        if rc != 0:
            out = ""
    low = out.lower()
    for marker, fam in (("0x1ffff800", "f0"), ("0x1fffc000", "f4"), ("0x5200", "h7"), ("0x1fff7800", "g")):
        if marker in low:
            return fam
    return "unknown"


_FAMILY_NAMES = {"f0": "STM32F0", "f4": "STM32F4", "h7": "STM32H7", "g": "STM32G0/G4"}


def family_name(reg, fam: str) -> str:
    """Семейство -> «STM32xx (платы семейства из реестра)»; неизвестное - «не определён»."""
    name = _FAMILY_NAMES.get(fam)
    if not name:
        return "не определён"
    labels = []
    for bid in reg.list():
        b = reg.get(bid)
        if b.field("FAMILY") == fam:
            labels.append(b.field("LABEL"))
    return name + (" (%s)" % " / ".join(labels) if labels else "")


_UID_ADDR = {"f0": "0x1FFFF7AC", "f4": "0x1FFF7A10", "h7": "0x1FF1E800", "g": "0x1FFF7590"}


def uid_addr(fam: str) -> str:
    """Адрес 12-байтного UID чипа по семейству (ROM-загрузчик отдаёт его по DFU); пусто, если семейство неизвестно."""
    return _UID_ADDR.get(fam, "")


def dfu_read_uid(runner: Runner, fam: str, log_file=None) -> str:
    """canbus_uuid по UID, прочитанному из платы в DFU (плата остаётся в DFU). Пустая строка при ошибке.
    В dry-run только печатает команду и возвращает 000000000000."""
    addr = uid_addr(fam)
    if not addr:
        return ""
    if runner.dry_run:
        ui.info("[dry-run] dfu-util -U UID (%s) -> canbus_uuid" % addr)
        return "000000000000"
    with tempfile.TemporaryDirectory() as tmp:
        uid_file = Path(tmp) / "uid.bin"
        cp = runner.run(["dfu-util", "-a", "0", "-s", "%s:12:force" % addr, "-U", str(uid_file), "-d", "0483:df11"],
                        sudo=True, check=False, stdout_file=log_file or os.devnull, append=True)
        if cp.returncode != 0:
            return ""
        try:
            return can_uuid_mod.can_uuid(uid_file.read_bytes())
        except (ValueError, OSError):
            return ""


def bridge_usb_serial(sys_usb_dir: str = "/sys/bus/usb/devices") -> str:
    """USB-serial моста USB-CAN (1d50:606f); пусто, если моста нет."""
    def rd(path: str) -> str:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read().rstrip("\n")
        except OSError:
            return ""

    for d in sorted(glob.glob(os.path.join(sys_usb_dir, "*"))):
        if rd(os.path.join(d, "idVendor")) == "1d50" and rd(os.path.join(d, "idProduct")) == "606f":
            ser = rd(os.path.join(d, "serial"))
            if ser:
                return ser
    return ""


def usb_bridge_present(runner: Optional[Runner]) -> bool:
    """Есть ли мост USB-CAN Klipper (1d50:606f)."""
    return probe(runner, ["lsusb", "-d", "1d50:606f"])[0] == 0


def show_usb_state(runner: Optional[Runner], can_iface: str = "can0") -> None:
    """Печатает устройства by-id, число плат в DFU и мост USB-CAN. Список by-id берётся из /dev/serial/by-id
    (как в bash, в обход BYID_DIR)."""
    ui.info("Устройства в /dev/serial/by-id:")
    names = sorted(f for f in glob.glob("/dev/serial/by-id/*") if os.path.exists(f))
    for f in names:
        ui.info("  " + os.path.basename(f))
    if not names:
        ui.info("  (пусто)")
    ui.info("Устройств в режиме DFU (0483:df11): %d" % dfu_count(runner))
    if usb_bridge_present(runner):
        out = probe(runner, ["ip", "-br", "link", "show", can_iface])[1]
        state = "\n".join((ln.split() + ["", ""])[1] for ln in out.split("\n") if ln.strip())
        ui.info("Найден мост USB-CAN Klipper (1d50:606f); интерфейс %s: %s" % (can_iface, state))


# ------------------------------------------------------------------ CAN (бывшие kernel_can_support / bring_up_can / can_uuids)

def kernel_can_support(kernel_config: str = "", release: Optional[str] = None) -> int:
    """Поддержка CAN в ядре: 0 есть, 1 нет, 2 неизвестно. kernel_config - путь к конфигу ядра (иначе /proc/config.gz,
    затем /boot/config-<релиз>); без конфига смотрит модуль gs_usb."""
    release = release if release is not None else os.uname().release
    content = ""
    cfg = ""
    if kernel_config:
        cfg = kernel_config
    elif os.access("/proc/config.gz", os.R_OK):
        try:
            with gzip.open("/proc/config.gz", "rt", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, EOFError):
            content = ""
    elif os.access("/boot/config-" + release, os.R_OK):
        cfg = "/boot/config-" + release
    if cfg and os.access(cfg, os.R_OK):
        try:
            with open(cfg, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            content = ""
    if content.strip():
        for opt in ("CONFIG_CAN", "CONFIG_CAN_RAW", "CONFIG_CAN_GS_USB"):
            if not re.search(r"(?m)^%s=(y|m)$" % opt, content):
                return 1
        return 0
    if os.path.isdir("/sys/module/gs_usb") or glob.glob("/lib/modules/%s/kernel/drivers/net/can/usb/gs_usb.ko*" % release):
        return 0
    return 2


def can_uuids(runner: Runner, app: str, *, katapult_dir, klippy_env, klipper_dir, iface: str) -> List[str]:
    """UUID устройств на шине CAN с ``Application: Klipper`` или ``Application: Katapult`` (вывод flashtool.py -q /
    canbus_query.py; код возврата и ошибки команды игнорируются)."""
    if app == "Katapult":
        argv = ["python3", str(Path(katapult_dir) / "scripts" / "flashtool.py"), "-i", iface, "-q"]
        rx = re.compile(r".*Detected UUID: ([0-9a-fA-F]{12}),.*Application: Katapult.*")
    else:
        argv = [str(Path(klippy_env) / "bin" / "python"), str(Path(klipper_dir) / "scripts" / "canbus_query.py"), iface]
        rx = re.compile(r".*canbus_uuid=([0-9a-fA-F]{12}),.*Application: Klipper.*")
    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "out"
        runner.run(argv, check=False, stdout_file=out_file, readonly=True, quiet=True)
        try:
            text = out_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    res = []
    for line in text.split("\n"):
        m = rx.match(line)
        if m:
            res.append(m.group(1))
    return res


def bring_up_can(runner: Runner, iface: str) -> bool:
    """Поднять интерфейс CAN вручную, если автоматически не поднялся (1 Мбит, txqueuelen 128). True - интерфейс UP."""
    for _ in range(40):
        if can_iface_exists(iface, runner):
            break
        time.sleep(0.5)
    if not can_iface_exists(iface, runner):
        return False
    if not can_iface_up(iface, runner):
        runner.run(["ip", "link", "set", iface, "down", "type", "can"], sudo=True, check=False, quiet=True)
        if runner.run(["ip", "link", "set", iface, "up", "type", "can", "bitrate", "1000000"], sudo=True,
                      check=False).returncode != 0:
            return False
    runner.run(["ip", "link", "set", iface, "txqueuelen", "128"], sudo=True, check=False)
    return can_iface_up(iface, runner)


def check_can_health(runner: Runner, iface: str) -> bool:
    """Показать первые строки ``ip -s -d link show`` и предупредить о BUS-OFF. False - есть BUS-OFF."""
    out = run_quiet(["ip", "-s", "-d", "link", "show", iface], runner)[1]
    ui.info("\n".join(out.rstrip("\n").split("\n")[:3]) if out else "")
    if "bus-off" in out.lower():
        ui.warn("CAN в состоянии BUS-OFF. Перезапуск: sudo ip link set %s down type can && sudo ip link set %s up type can "
                "bitrate 1000000" % (iface, iface))
        ui.warn("Если повторяется: проверьте терминаторы (около 60 Ом между CAN_H и CAN_L при выключенном питании) "
                "и перепрошейте Klipper на платах голов")
        return False
    return True
