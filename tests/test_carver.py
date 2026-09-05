"""
Automated unit and integration tests for OpenFileRescue carver.
"""
import os
import shutil
import tempfile
import unittest

from openfilerescue.core.reader import SafeDiskReader
from openfilerescue.core.carver import FileCarver
from openfilerescue.core.exporter import FileExporter
from tests.make_test_disk import create_test_image


class TestFileCarver(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="rescue_test_")
        cls.img_path = os.path.join(cls.temp_dir, "test_card.img")
        cls.test_info = create_test_image(cls.img_path, size_mb=10)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_disk_reader(self):
        with SafeDiskReader(self.img_path) as reader:
            self.assertEqual(reader.size, 10 * 1024 * 1024)
            # Check MBR boot signature
            mbr_tail = reader.read_at(510, 2)
            self.assertEqual(mbr_tail, b"\x55\xaa")

    def test_carving_all_files(self):
        found_files = []

        def on_found(carved):
            found_files.append(carved)

        with SafeDiskReader(self.img_path) as reader:
            carver = FileCarver(reader, sector_step=512)
            carver.set_callbacks(on_file_found=on_found)
            carver._scan_loop()  # Synchronous test run

            # Check stats
            self.assertTrue(carver.stats.is_finished)
            self.assertEqual(carver.stats.files_found, 4)
            self.assertEqual(len(found_files), 4)

            # Check extensions
            exts = [f.extension for f in found_files]
            self.assertEqual(exts.count(".jpg"), 3)
            self.assertEqual(exts.count(".png"), 1)

            # Verify EXIF metadata on JPEGs
            jpgs = [f for f in found_files if f.extension == ".jpg"]
            self.assertEqual(jpgs[0].metadata.get("camera_make"), "Kids Camera")
            self.assertEqual(jpgs[0].metadata.get("camera_model"), "KC-2026")

            # Verify thumbnails were generated
            for f in found_files:
                self.assertIsNotNone(f.thumbnail_base64)
                self.assertTrue(f.thumbnail_base64.startswith("data:image/"))

    def test_file_export(self):
        export_dir = os.path.join(self.temp_dir, "exported")
        exporter = FileExporter(export_dir)

        with SafeDiskReader(self.img_path) as reader:
            carver = FileCarver(reader, sector_step=512)
            carver._scan_loop()

            res = exporter.export_all(carver.discovered_files, reader._file, organization="by_camera")
            self.assertEqual(res["total_exported"], 4)
            self.assertTrue(res["total_bytes"] > 0)

            # Check files exist on disk
            camera_dir = os.path.join(export_dir, "Kids Camera_KC-2026")
            self.assertTrue(os.path.exists(camera_dir))
            exported_items = os.listdir(camera_dir)
            self.assertEqual(len(exported_items), 3)


if __name__ == "__main__":
    unittest.main()
