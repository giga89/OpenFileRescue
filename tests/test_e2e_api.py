"""
End-to-End API and Recovery Workflow Test.
Tests the full lifecycle: API server startup, sample disk creation,
scan initiation, live telemetry polling, file discovery, and organized export.
"""
import os
import time
import json
import urllib.request
import threading
import unittest

from openfilerescue.server.server import ThreadedHTTPServer, RescueRequestHandler, STATE


class TestEndToEndAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.host = "127.0.0.1"
        cls.port = 8789
        cls.server = ThreadedHTTPServer((cls.host, cls.port), RescueRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://{cls.host}:{cls.port}"
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        STATE.reset()
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path: str, data: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.base_url}{path}") as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_full_recovery_cycle(self):
        # 1. Check sources
        sources_res = self._get("/api/sources")
        self.assertTrue(sources_res["success"])
        self.assertTrue(len(sources_res["sources"]) > 0)

        # 2. Create sample test disk image
        sample_res = self._post("/api/create_sample_disk", {})
        self.assertTrue(sample_res["success"])
        img_path = sample_res["image_path"]
        self.assertTrue(os.path.exists(img_path))

        # 3. Start scan on sample disk
        start_res = self._post("/api/scan/start", {"source_path": img_path, "sector_step": 512})
        self.assertTrue(start_res["success"])

        # 4. Wait for scan completion
        max_wait = 10
        start_t = time.time()
        completed = False

        while time.time() - start_t < max_wait:
            st = self._get("/api/scan/status")
            if st["is_finished"]:
                completed = True
                break
            time.sleep(0.3)

        self.assertTrue(completed, "Scan did not complete in time")
        self.assertEqual(st["files_found"], 4)

        # 5. Fetch discovered files
        files_res = self._get("/api/files")
        self.assertTrue(files_res["success"])
        files = files_res["files"]
        self.assertEqual(len(files), 4)

        # Verify preview endpoint returns image bytes
        first_file_id = files[0]["id"]
        preview_url = f"{self.base_url}/api/file/{first_file_id}/preview"
        with urllib.request.urlopen(preview_url) as resp:
            data = resp.read()
            self.assertTrue(len(data) > 0)

        # 6. Test organized export
        export_dir = os.path.join(os.getcwd(), "test_recovered_export")
        export_res = self._post("/api/export", {
            "output_dir": export_dir,
            "organization": "by_type"
        })
        self.assertTrue(export_res["success"])
        self.assertEqual(export_res["summary"]["total_exported"], 4)
        self.assertTrue(os.path.exists(os.path.join(export_dir, "JPG")))
        self.assertTrue(os.path.exists(os.path.join(export_dir, "PNG")))

        # Clean up test output
        import shutil
        shutil.rmtree(export_dir, ignore_errors=True)
        if os.path.exists(img_path):
            os.remove(img_path)


if __name__ == "__main__":
    unittest.main()
