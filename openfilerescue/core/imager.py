"""
Safe Bitstream Disk Imager (Clone to .img / .raw).
Creates a byte-for-byte read-only image copy of damaged flash cards
to prevent hardware degradation during repeated scan passes.
"""
import os
import time
import threading
from typing import Optional, Callable
from .reader import SafeDiskReader


class SafeImager:
    """
    Copies a physical drive or volume into a raw .img file safely.
    Zero-fills any unreadable bad sectors to preserve filesystem geometry.
    """

    def __init__(
        self,
        source_path: str,
        dest_image_path: str,
        chunk_size: int = 1024 * 1024,
        max_retries: int = 2
    ):
        self.source_path = source_path
        self.dest_image_path = dest_image_path
        self.chunk_size = chunk_size
        self.max_retries = max_retries

        self.bytes_copied = 0
        self.total_bytes = 0
        self.bad_sectors = 0
        self.is_running = False
        self.is_finished = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, on_progress: Optional[Callable[[float, int, int], None]] = None):
        """Starts cloning in a background thread."""
        self._stop_event.clear()
        self.is_running = True
        self.is_finished = False

        def _worker():
            try:
                with SafeDiskReader(self.source_path) as reader:
                    self.total_bytes = max(1, reader.size)
                    with open(self.dest_image_path, "wb") as out_f:
                        for offset, chunk, is_bad in reader.stream_chunks(self.chunk_size):
                            if self._stop_event.is_set():
                                break
                            if is_bad:
                                self.bad_sectors += 1
                            out_f.write(chunk)
                            self.bytes_copied += len(chunk)

                            if on_progress:
                                pct = min(100.0, (self.bytes_copied / self.total_bytes) * 100.0)
                                on_progress(pct, self.bytes_copied, self.bad_sectors)

                    self.is_finished = not self._stop_event.is_set()
            finally:
                self.is_running = False

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self):
        """Abort disk imaging."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.is_running = False
