"""Целостность каталога installer/pinouts: файлы, SOURCES.tsv (sha256, размер), PINOUT в реестре плат, README."""
import hashlib
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = Path(os.path.dirname(HERE))
sys.path.insert(0, str(INSTALL))

from vostok import boards  # noqa: E402

DIR = INSTALL / "pinouts"
COLUMNS = ["path", "board_id", "source_url", "permalink", "license", "sha256", "size", "note"]
# Платы без картинки распиновки: официального листа нет (причина - в NOTE платы и в pinouts/README)
NO_PINOUT = {"alps", "spider-v3-h723",
             # платы реестра 1.7: лицензия на картинки не указана (смотрите DOC платы)
             "octopus-f446", "octopus-f429", "octopus-max-ez", "kraken", "ldo-leviathan-v1.2", "fly-super8-pro-h723",
             "fly-super8", "mks-monster8-v2", "ebb36-v1.0", "ebb-gen2", "sht36-v2"}
MAX_SIZE = 3 * 1024 * 1024
EXTRA_FILES = {"SOURCES.tsv", "README.md", "README.en.md"}


def load_sources():
    lines = (DIR / "SOURCES.tsv").read_text(encoding="utf-8").rstrip("\n").split("\n")
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        rows.append(dict(zip(header, ln.split("\t"))))
        assert len(ln.split("\t")) == len(COLUMNS), ln
    return header, rows


class PinoutsTest(unittest.TestCase):
    def setUp(self):
        self.header, self.rows = load_sources()
        self.by_path = {r["path"]: r for r in self.rows}
        self.reg = boards.registry()

    def test_header_and_unique(self):
        self.assertEqual(self.header, COLUMNS)
        self.assertEqual(len(self.by_path), len(self.rows))

    def test_files_match_sources(self):
        for r in self.rows:
            f = DIR / r["path"]
            self.assertTrue(f.is_file(), r["path"])
            data = f.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), r["sha256"], r["path"])
            self.assertEqual(len(data), int(r["size"]), r["path"])
            self.assertLessEqual(len(data), MAX_SIZE, r["path"])
            for k in ("source_url", "permalink", "license"):
                self.assertTrue(r[k], "%s: пустое %s" % (r["path"], k))
            self.assertTrue(r["permalink"].startswith("https://"), r["path"])

    def test_no_untracked_files(self):
        on_disk = {str(p.relative_to(DIR)) for p in DIR.rglob("*") if p.is_file()}
        self.assertEqual(on_disk - EXTRA_FILES, set(self.by_path))

    def test_board_pinouts_registered(self):
        for bid in self.reg.ids():
            b = self.reg.get(bid)
            for rel in b.pinout_list:
                self.assertIn(rel, self.by_path, "%s: %s нет в SOURCES.tsv" % (bid, rel))
                self.assertIn(bid, self.by_path[rel]["board_id"].split(), "%s: %s" % (bid, rel))
                self.assertTrue((DIR / rel).is_file(), "%s: %s" % (bid, rel))
            if bid in NO_PINOUT:
                self.assertEqual(b.pinout_list, [], bid)
            else:
                self.assertTrue(b.pinout_list, "у платы %s нет PINOUT (или добавьте в NO_PINOUT с причиной)" % bid)

    def test_sources_board_ids_exist(self):
        for r in self.rows:
            for bid in r["board_id"].split():
                self.assertIn(bid, self.reg.ids(), r["path"])

    def test_readmes_list_every_file(self):
        for name in ("README.md", "README.en.md"):
            text = (DIR / name).read_text(encoding="utf-8")
            for path in self.by_path:
                # схемы подключения перечислены списком по имени файла в общем каталоге
                ok = path in text or (os.path.dirname(path) + "/" in text and os.path.basename(path) in text)
                self.assertTrue(ok, "%s: нет %s" % (name, path))


if __name__ == "__main__":
    unittest.main()
