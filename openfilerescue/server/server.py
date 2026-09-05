"""
Embedded Web Server and REST API for OpenFileRescue.
Provides web-based control, real-time status polling, image/video preview, and file export.
Seamlessly bridges Windows raw physical drives (\\\\.\\D:) and Linux images/block devices.
"""
import os
import sys
import json
import urllib.parse
import mimetypes
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional, Dict, Any, List

from openfilerescue.core.reader import SafeDiskReader, detect_available_sources
from openfilerescue.core.carver import FileCarver, CarverStats
from openfilerescue.core.exporter import FileExporter
from openfilerescue.core.parsers.base import CarvedFile
from tests.make_test_disk import create_test_image


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RecoveryState:
    """Global state manager for active scan sessions."""
    def __init__(self):
        self.reader: Optional[SafeDiskReader] = None
        self.carver: Optional[FileCarver] = None
        self.bridge_proc: Optional[subprocess.Popen] = None
        self.bridge_thread: Optional[threading.Thread] = None
        self.active_source_path: str = ""
        self.output_dir: str = os.path.join(os.getcwd(), "recovered_files")
        os.makedirs(self.output_dir, exist_ok=True)

        # Unified stats and discovered files
        self.stats = CarverStats()
        self.discovered_files: List[Dict[str, Any]] = []
        self._file_map: Dict[str, Dict[str, Any]] = {}
        self.is_scanning = False

    def reset(self):
        if self.bridge_proc:
            try:
                self.bridge_proc.terminate()
            except Exception:
                pass
            self.bridge_proc = None
        if self.carver:
            self.carver.stop()
            self.carver = None
        if self.reader:
            self.reader.close()
            self.reader = None
        self.is_scanning = False
        self.active_source_path = ""
        self.stats = CarverStats()
        self.discovered_files.clear()
        self._file_map.clear()


STATE = RecoveryState()
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))


class RescueRequestHandler(BaseHTTPRequestHandler):
    """Handles REST API and static UI asset serving."""

    def log_message(self, format, *args):
        pass

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"success": False, "error": message}, status=status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/sources":
            sources = detect_available_sources()
            data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "path": s.path,
                    "type": s.source_type,
                    "size_bytes": s.size_bytes,
                    "size_formatted": s.size_formatted,
                    "filesystem": s.filesystem
                }
                for s in sources
            ]
            self._send_json({"success": True, "sources": data})
            return

        elif path == "/api/scan/status":
            st = STATE.stats
            self._send_json({
                "success": True,
                "is_running": STATE.is_scanning,
                "is_paused": st.is_paused,
                "is_finished": st.is_finished,
                "percent": st.percent,
                "scanned_bytes": st.scanned_bytes,
                "total_bytes": st.total_bytes,
                "files_found": len(STATE.discovered_files),
                "bad_sectors_count": st.bad_sectors_count,
                "bytes_per_second": st.bytes_per_second,
                "elapsed_seconds": st.elapsed_seconds,
                "eta_seconds": st.eta_seconds,
                "status_message": st.status_message,
                "sector_map": st.sector_map,
                "file_counts_by_type": st.file_counts_by_type
            })
            return

        elif path == "/api/files":
            self._send_json({"success": True, "files": STATE.discovered_files})
            return

        elif path.startswith("/api/file/") and path.endswith("/preview"):
            # /api/file/{file_id}/preview
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                file_id = parts[2]
                file_info = STATE._file_map.get(file_id)
                if file_info:
                    saved_path = file_info.get("saved_path")
                    if saved_path and os.path.exists(saved_path):
                        with open(saved_path, "rb") as f:
                            data = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", file_info.get("mime_type", "image/jpeg"))
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "public, max-age=3600")
                        self.end_headers()
                        self.wfile.write(data)
                        return

                # If carver has in-memory file
                if STATE.carver:
                    carved = STATE.carver.get_file(file_id)
                    if carved and STATE.reader:
                        data = carved.data_bytes or STATE.reader.read_at(carved.offset, carved.size)
                        self.send_response(200)
                        self.send_header("Content-Type", carved.mime_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return

            self._send_error_json("File not found", status=404)
            return

        self._serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if path == "/api/scan/start":
            source_path = payload.get("source_path", "").strip()
            sector_step = int(payload.get("sector_step", 512))

            if not source_path:
                self._send_error_json("Source path is required.")
                return

            STATE.reset()
            STATE.active_source_path = source_path
            STATE.is_scanning = True
            STATE.stats = CarverStats()
            STATE.stats.is_running = True
            STATE.stats.status_message = "Starting scan..."

            # Determine whether this is a Windows physical drive (D:, /mnt/d, \\.\D:)
            is_win_drive = (
                source_path.startswith(r"\\.") or
                (len(source_path) >= 2 and source_path[1] == ":") or
                source_path.startswith("/mnt/") and os.path.isdir(source_path)
            )

            if is_win_drive:
                # Launch Windows Carver Bridge via background thread
                self._start_windows_bridge(source_path, sector_step)
            else:
                # Launch native FileCarver
                self._start_native_carver(source_path, sector_step)

            self._send_json({
                "success": True,
                "message": f"Scan successfully initiated on {source_path}",
                "mode": "Windows Bridge" if is_win_drive else "Native Carver"
            })
            return

        elif path == "/api/scan/pause":
            if STATE.carver:
                STATE.carver.pause()
            STATE.stats.is_paused = True
            self._send_json({"success": True, "message": "Scan paused"})
            return

        elif path == "/api/scan/resume":
            if STATE.carver:
                STATE.carver.resume()
            STATE.stats.is_paused = False
            self._send_json({"success": True, "message": "Scan resumed"})
            return

        elif path == "/api/scan/stop":
            STATE.reset()
            STATE.stats.is_running = False
            STATE.stats.status_message = "Scan stopped by user"
            self._send_json({"success": True, "message": "Scan stopped"})
            return

        elif path == "/api/export":
            out_dir = payload.get("output_dir", "").strip() or STATE.output_dir
            org = payload.get("organization", "by_type")
            exporter = FileExporter(out_dir)
            total_exported = 0
            total_bytes = 0
            saved_paths = []

            if STATE.carver and STATE.reader and hasattr(STATE.reader, "_file") and STATE.reader._file:
                res = exporter.export_all(STATE.carver.discovered_files, STATE.reader._file, organization=org)
                total_exported = res["total_exported"]
                total_bytes = res["total_bytes"]
                saved_paths = res["sample_files"]
            else:
                for item in STATE.discovered_files:
                    try:
                        ext = item.get("extension", "").lstrip(".")
                        sub_dir = ext.upper() if org == "by_type" else ""
                        dest_dir = os.path.join(out_dir, sub_dir)
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, f"recovered_{item.get('id', 'file')}.{ext}")

                        src_path = item.get("saved_path")
                        if src_path and os.path.exists(src_path):
                            import shutil
                            shutil.copy2(src_path, dest_path)
                            total_exported += 1
                            total_bytes += os.path.getsize(dest_path)
                            saved_paths.append(dest_path)
                    except Exception:
                        pass

            self._send_json({
                "success": True,
                "summary": {
                    "total_exported": total_exported,
                    "total_bytes": total_bytes,
                    "output_directory": out_dir,
                    "sample_files": saved_paths[:10]
                }
            })
            return

        elif path == "/api/create_sample_disk":
            target_img = os.path.join(os.getcwd(), "sample_microsd_card.img")
            info = create_test_image(target_img, size_mb=15)
            self._send_json({
                "success": True,
                "message": "Demo 15MB SD card image created!",
                "image_path": target_img,
                "injected_count": len(info["injected_files"])
            })
            return

        self._send_error_json("Endpoint not found", status=404)

    def _start_windows_bridge(self, source_path: str, sector_step: int):
        """Launches the Windows carver bridge and pipes real-time events to STATE."""
        # Convert /mnt/d to \\.\D:
        win_path = r"\\.\D:"
        if source_path.startswith("/mnt/") and len(source_path) >= 6:
            letter = source_path[5].upper()
            win_path = rf"\\.\{letter}:"
        elif source_path.startswith(r"\\."):
            win_path = source_path
        elif len(source_path) >= 2 and source_path[1] == ":":
            win_path = rf"\\.\{source_path[:2]}"

        bridge_script = os.path.join(os.path.dirname(__file__), "..", "core", "carver_bridge.py")
        wsl_bridge_path = rf"\\wsl.localhost\Ubuntu{os.path.abspath(bridge_script)}"

        cmd = [
            "powershell.exe", "-NoProfile", "-Command",
            f"py {wsl_bridge_path} {win_path} recovered_sd 32.0"
        ]

        def _bridge_worker():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
                STATE.bridge_proc = proc

                for line in proc.stdout:
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        ev = json.loads(line)
                        ev_type = ev.get("type")

                        if ev_type == "progress":
                            STATE.stats.percent = ev.get("percent", 0.0)
                            STATE.stats.scanned_bytes = ev.get("scanned_bytes", 0)
                            STATE.stats.total_bytes = ev.get("total_bytes", 0)
                            STATE.stats.bytes_per_second = ev.get("bytes_per_second", 0.0)
                            STATE.stats.elapsed_seconds = ev.get("elapsed_seconds", 0.0)
                            STATE.stats.eta_seconds = ev.get("eta_seconds", 0.0)
                            STATE.stats.status_message = ev.get("status_message", "Scanning...")
                            STATE.stats.sector_map = ev.get("sector_map", STATE.stats.sector_map)
                            STATE.stats.file_counts_by_type = ev.get("file_counts_by_type", {})

                        elif ev_type == "found":
                            finfo = ev.get("file")
                            if finfo and finfo["id"] not in STATE._file_map:
                                STATE.discovered_files.append(finfo)
                                STATE._file_map[finfo["id"]] = finfo
                                STATE.stats.files_found = len(STATE.discovered_files)

                        elif ev_type == "finished":
                            STATE.stats.is_finished = True
                            STATE.stats.status_message = "Scan completed!"
                            STATE.is_scanning = False
                    except Exception:
                        pass

                proc.wait()
            finally:
                STATE.is_scanning = False
                STATE.stats.is_finished = True

        t = threading.Thread(target=_bridge_worker, daemon=True)
        STATE.bridge_thread = t
        t.start()

    def _start_native_carver(self, source_path: str, sector_step: int):
        """Runs standard FileCarver on an image file or Linux block device."""
        try:
            reader = SafeDiskReader(source_path, sector_size=sector_step)
            carver = FileCarver(reader, sector_step=sector_step)
            STATE.reader = reader
            STATE.carver = carver

            def on_found(carved: CarvedFile):
                d = carved.to_dict()
                if d["id"] not in STATE._file_map:
                    STATE.discovered_files.append(d)
                    STATE._file_map[d["id"]] = d

            def on_prog(st: CarverStats):
                STATE.stats = st

            carver.set_callbacks(on_file_found=on_found, on_progress=on_prog)
            carver.start()
        except Exception as e:
            STATE.stats.status_message = f"Error: {e}"
            STATE.is_scanning = False

    def _serve_static(self, req_path: str):
        if req_path in ("/", ""):
            req_path = "/index.html"

        clean_path = os.path.normpath(req_path.lstrip("/"))
        file_path = os.path.join(WEB_DIR, clean_path)

        if not file_path.startswith(WEB_DIR) or not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(500)
            self.end_headers()


def run_server(host: str = "127.0.0.1", port: int = 8765):
    server = ThreadedHTTPServer((host, port), RescueRequestHandler)
    print(f"==================================================")
    print(f" OpenFileRescue Web UI running at http://{host}:{port}")
    print(f"==================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        STATE.reset()
        server.server_close()


if __name__ == "__main__":
    run_server()
