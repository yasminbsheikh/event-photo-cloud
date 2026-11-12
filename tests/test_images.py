import tempfile
import unittest
from pathlib import Path

from photocloud.images import FolderError, resolve_folder, scan_folder


class ScanTests(unittest.TestCase):
    def test_scan_filters_and_sorts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for n in ["b.JPG", "a.png", "c.webp", "d.jpeg", "notes.txt", ".hidden.jpg"]:
                (root / n).write_bytes(b"x")
            (root / "sub").mkdir()
            (root / "sub" / "e.png").write_bytes(b"x")
            flat = [p.name for p in scan_folder(root)]
            self.assertEqual(flat, ["a.png", "b.JPG", "c.webp", "d.jpeg"])
            self.assertEqual(len(scan_folder(root, recursive=True)), 5)

    def test_bad_folders(self):
        with self.assertRaises(FolderError):
            resolve_folder("")
        with self.assertRaises(FolderError):
            resolve_folder("/definitely/not/here")


if __name__ == "__main__":
    unittest.main()
