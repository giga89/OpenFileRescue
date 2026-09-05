"""
High-Performance File Carving Engine (Deep Scan).
Analyzes raw disk sectors, isolates signatures, extracts metadata,
and streams real-time sector map updates and discovered files.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from .parsers.base import BaseParser, CarvedFile
from .parsers import DEFAULT_PARSERS
from .reader import SafeDiskReader


@dataclass
class CarverStats:
    """Real-time scan statistics."""
    total_bytes: int = 0
    scanned_bytes: int = 0
    percent: float = 0.0
    files_found: int = 0
    bad_sectors_count: int = 0
    bytes_per_second: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    is_running: bool = False
    is_paused: bool = False
    is_finished: bool = False
    status_message: str = "Idle"
    file_counts_by_type: Dict[str, int] = field(default_factory=dict)
    sector_map: List[int] = field(default_factory=lambda: [0] * 120)  # 120 grid buckets: 0=pending, 1=scanned, 2=found, 3=bad


class FileCarver:
    """
    Asynchronous file carving worker with real-time callbacks.
    """

    def __init__(
        self,
        reader: SafeDiskReader,
        parsers: Optional[List[BaseParser]] = None,
        sector_step: int = 512,
        grid_buckets: int = 120
    ):
        self.reader = reader
        self.parsers = parsers or DEFAULT_PARSERS
        self.sector_step = sector_step
        self.grid_buckets = grid_buckets

        self.stats = CarverStats(
            total_bytes=reader.size,
            sector_map=[0] * grid_buckets
        )
        self.discovered_files: List[CarvedFile] = []
        self._file_id_map: Dict[str, CarvedFile] = {}

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Unpaused initially
        self._worker_thread: Optional[threading.Thread] = None

        self._on_file_found: Optional[Callable[[CarvedFile], None]] = None
        self._on_progress: Optional[Callable[[CarverStats], None]] = None

    def set_callbacks(
        self,
        on_file_found: Optional[Callable[[CarvedFile], None]] = None,
        on_progress: Optional[Callable[[CarverStats], None]] = None
    ):
        self._on_file_found = on_file_found
        self._on_progress = on_progress

    def start(self):
        """Start the background carving thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._worker_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._worker_thread.start()

    def pause(self):
        """Pause the scan."""
        self._pause_event.clear()
        self.stats.is_paused = True
        self.stats.status_message = "Paused"

    def resume(self):
        """Resume scanning."""
        self._pause_event.set()
        self.stats.is_paused = False
        self.stats.status_message = "Scanning..."

    def stop(self):
        """Request immediate scan cancellation."""
        self._stop_event.set()
        self._pause_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
        self.stats.is_running = False
        self.stats.status_message = "Stopped"

    def get_file(self, file_id: str) -> Optional[CarvedFile]:
        """Retrieve a carved file by its ID."""
        return self._file_id_map.get(file_id)

    def _scan_loop(self):
        """Main carving loop processing the source sequentially."""
        self.stats.is_running = True
        self.stats.is_finished = False
        self.stats.status_message = "Scanning disk..."

        start_time = time.time()
        last_progress_time = start_time
        total_size = max(1, self.reader.size)

        offset = 0
        buf_size = 2 * 1024 * 1024  # 2MB read chunks
        recent_bytes_read = 0
        speed_measure_start = time.time()

        while offset < total_size and not self._stop_event.is_set():
            # Handle pause
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            to_read = min(buf_size, total_size - offset)
            chunk = self.reader.read_at(offset, to_read)
            if not chunk:
                break

            chunk_len = len(chunk)
            chunk_pos = 0

            while chunk_pos < chunk_len and not self._stop_event.is_set():
                abs_offset = offset + chunk_pos
                sample = chunk[chunk_pos:chunk_pos + 64]

                # Update sector map bucket
                bucket_idx = min(self.grid_buckets - 1, int((abs_offset / total_size) * self.grid_buckets))
                if self.stats.sector_map[bucket_idx] == 0:
                    self.stats.sector_map[bucket_idx] = 1  # Scanned

                # Fast check across parsers
                file_found: Optional[CarvedFile] = None
                for parser in self.parsers:
                    if parser.match(sample):
                        # Attempt structure parsing using raw file reader
                        parsed = parser.parse(self.reader._file, abs_offset)
                        if parsed and parsed.size > 0:
                            file_found = parsed
                            break

                if file_found:
                    self.discovered_files.append(file_found)
                    self._file_id_map[file_found.file_id] = file_found
                    self.stats.files_found += 1

                    # Track file counts by extension
                    ext = file_found.extension.upper().lstrip(".")
                    self.stats.file_counts_by_type[ext] = self.stats.file_counts_by_type.get(ext, 0) + 1

                    # Mark bucket as file found
                    self.stats.sector_map[bucket_idx] = 2

                    if self._on_file_found:
                        try:
                            self._on_file_found(file_found)
                        except Exception:
                            pass

                    # Advance past the file to next sector boundary
                    skip_bytes = ((file_found.size + self.sector_step - 1) // self.sector_step) * self.sector_step
                    chunk_pos += skip_bytes
                else:
                    chunk_pos += self.sector_step

            offset += chunk_len
            recent_bytes_read += chunk_len
            self.stats.scanned_bytes = min(offset, total_size)
            self.stats.percent = round((self.stats.scanned_bytes / total_size) * 100, 1)

            # Recalculate speed every 0.3 seconds
            now = time.time()
            if now - last_progress_time >= 0.3:
                elapsed_speed = max(0.001, now - speed_measure_start)
                self.stats.bytes_per_second = recent_bytes_read / elapsed_speed
                recent_bytes_read = 0
                speed_measure_start = now

                self.stats.elapsed_seconds = round(now - start_time, 1)
                if self.stats.bytes_per_second > 0:
                    rem_bytes = max(0, total_size - self.stats.scanned_bytes)
                    self.stats.eta_seconds = round(rem_bytes / self.stats.bytes_per_second, 0)

                self.stats.bad_sectors_count = len(self.reader.bad_blocks)
                last_progress_time = now

                if self._on_progress:
                    try:
                        self._on_progress(self.stats)
                    except Exception:
                        pass

        # Finalize
        self.stats.is_running = False
        self.stats.is_finished = not self._stop_event.is_set()
        self.stats.status_message = "Scan completed!" if self.stats.is_finished else "Scan cancelled."
        self.stats.percent = 100.0 if self.stats.is_finished else self.stats.percent

        if self._on_progress:
            try:
                self._on_progress(self.stats)
            except Exception:
                pass
