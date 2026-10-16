"""Тесты vostok.state: devices.tsv и flashed.tsv; сверка с awk-логикой update_klipper_mcu.sh."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from vostok.state import Device, DevicesFile, FlashedLog  # noqa: E402


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def awk_lookup(self, path, key):
        # devices_lookup из update_klipper_mcu.sh
        out = subprocess.run(["awk", "-F", "\t", "-v", "k=" + key, '$1 == k {print $2 "\\t" $3; exit}', str(path)],
                             stdout=subprocess.PIPE, universal_newlines=True).stdout
        return out.rstrip("\n")

    def awk_get(self, path, key):
        # state_get из update_klipper_mcu.sh
        out = subprocess.run(["awk", "-F", "\t", "-v", "s=" + key, '$1 == s {v = $2} END {if (v != "") print v}', str(path)],
                             stdout=subprocess.PIPE, universal_newlines=True).stdout
        return out.rstrip("\n")

    def test_devices_roundtrip(self):
        f = DevicesFile(self.dir / "sub" / "devices.tsv")
        self.assertEqual(f.load(), [])
        self.assertIsNone(f.lookup("x"))
        devs = [Device("ABC123", "stm32h723xx-canbridge.config", "bridge"),
                Device("0123456789ab", "stm32g0b1xx-can.config", "can"),
                Device("SER", "stm32f072xb.config", "usb")]
        f.save(devs)
        self.assertEqual((self.dir / "sub" / "devices.tsv").read_text(encoding="utf-8"),
                         "ABC123\tstm32h723xx-canbridge.config\tbridge\n"
                         "0123456789ab\tstm32g0b1xx-can.config\tcan\nSER\tstm32f072xb.config\tusb\n")
        self.assertEqual(f.load(), devs)
        self.assertEqual(f.lookup("SER"), devs[2])

    def test_devices_parse_oddities(self):
        p = self.dir / "devices.tsv"
        p.write_text("\n\tx\ty\nA\tcfg\n\nB\tcfg2\trole\textra\nA\tdup\tusb\n", encoding="utf-8")
        f = DevicesFile(p)
        self.assertEqual(f.load(), [Device("A", "cfg", ""), Device("B", "cfg2", "role"), Device("A", "dup", "usb")])
        for key in ("A", "B", "zzz"):
            d = f.lookup(key)
            got = "%s\t%s" % (d.cfg, d.role) if d else ""
            self.assertEqual(got, self.awk_lookup(p, key), key)

    def test_flashed_get_set(self):
        p = self.dir / "fw" / "flashed.tsv"
        log = FlashedLog(p)
        self.assertEqual(log.get("a"), "")
        log.set("a", "v0.12-1-gabc")
        log.set("b", "v0.12-2-gdef")
        log.set("a", "v0.12-3-g123-dirty")
        self.assertEqual(log.get("a"), "v0.12-3-g123-dirty")
        self.assertEqual(log.get("b"), "v0.12-2-gdef")
        self.assertEqual(log.get("c"), "")
        self.assertEqual(p.read_text(encoding="utf-8"), "b\tv0.12-2-gdef\na\tv0.12-3-g123-dirty\n")
        self.assertEqual([x.name for x in p.parent.iterdir()], ["flashed.tsv"])  # временных файлов нет

    def test_devices_save_atomic(self):
        p = self.dir / "sub" / "devices.tsv"
        df = DevicesFile(p)
        df.save([Device("k1", "a.config", "usb")])
        p.chmod(0o640)
        df.save([Device("k2", "b.config", "can")])
        self.assertEqual(p.read_text(encoding="utf-8"), "k2\tb.config\tcan\n")
        self.assertEqual(p.stat().st_mode & 0o777, 0o640)           # права сохраняются
        self.assertEqual([x.name for x in p.parent.iterdir()], ["devices.tsv"])
        # сбой записи не портит прежний файл
        import unittest.mock as mock
        with mock.patch("vostok.state.os.replace", side_effect=OSError("диск")):
            with self.assertRaises(OSError):
                df.save([Device("k3", "c.config", "usb")])
        self.assertEqual(p.read_text(encoding="utf-8"), "k2\tb.config\tcan\n")
        self.assertEqual([x.name for x in p.parent.iterdir()], ["devices.tsv"])

    def test_flashed_get_same_as_awk(self):
        p = self.dir / "flashed.tsv"
        p.write_text("a\t1\nb\t2\na\t3\nc\t\nd\n\n", encoding="utf-8")
        log = FlashedLog(p)
        for key in ("a", "b", "c", "d", "e"):
            self.assertEqual(log.get(key), self.awk_get(p, key), key)

    def test_flashed_set_same_as_awk(self):
        # state_set: файл без строк ключа плюс новая строка в конце
        p = self.dir / "flashed.tsv"
        p.write_text("a\t1\nb\t2\na\t3\n", encoding="utf-8")
        FlashedLog(p).set("a", "9")
        self.assertEqual(p.read_text(encoding="utf-8"), "b\t2\na\t9\n")


if __name__ == "__main__":
    unittest.main()
