"""
Safe, Read-Only Source Reader.
Provides read-only access to disk images, raw devices (Linux /dev/sd* and Windows \\\\.\\*),
and handles I/O read errors / bad sectors gracefully.
"""
import os
import sys
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional, Generator, Tuple, BinaryIO, List


@dataclass
class SourceInfo:
    """Metadata about a scan target."""
    id: str
    name: str
    path: str
    source_type: str  # 'image_file', 'physical_disk', 'drive_volume', 'directory'
    size_bytes: int
    size_formatted: str
    is_read_only: bool = True
    filesystem: str = "Unknown"


def format_size(size_bytes: int) -> str:
    """Helper to format byte counts into human readable strings."""
    if size_bytes < 0:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0 or unit == "TB":
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


class SafeDiskReader:
    """
    Guaranteed read-only disk & image reader.
    Never opens devices with write permissions.
    """

    def __init__(self, target_path: str, sector_size: int = 512):
        self.target_path = target_path
        self.sector_size = sector_size
        self._file: Optional[BinaryIO] = None
        self.size = 0
        self.bad_blocks: List[int] = []
        self._open()

    def _open(self):
        """Open the target in strict read-only binary mode."""
        if not os.path.exists(self.target_path) and not self.target_path.startswith("\\\\.\\"):
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")

        # On POSIX systems, open with O_RDONLY
        try:
            if hasattr(os, "O_BINARY"):
                fd = os.open(self.target_path, os.O_RDONLY | os.O_BINARY)
            else:
                fd = os.open(self.target_path, os.O_RDONLY)
            self._file = os.fdopen(fd, "rb")
        except Exception as e:
            # Fallback to standard open
            self._file = open(self.target_path, "rb")

        # Determine total size
        try:
            self._file.seek(0, os.SEEK_END)
            self.size = self._file.tell()
            self._file.seek(0)
        except Exception:
            # For block devices where SEEK_END may fail
            self.size = self._get_device_size()

    def _get_device_size(self) -> int:
        """Query block device size if seek fails."""
        try:
            if platform.system() == "Linux":
                import fcntl
                import struct
                BLKGETSIZE64 = 0x80081272
                buf = bytearray(8)
                fcntl.ioctl(self._file.fileno(), BLKGETSIZE64, buf)
                return struct.unpack("Q", buf)[0]
        except Exception:
            pass
        return 0

    def read_at(self, offset: int, size: int) -> bytes:
        """
        Safely read `size` bytes at `offset`.
        If an I/O error or bad sector occurs, records the bad sector and returns zeros.
        """
        try:
            self._file.seek(offset)
            data = self._file.read(size)
            return data
        except (IOError, OSError) as err:
            self.bad_blocks.append(offset)
            return b"\x00" * size

    def stream_chunks(self, chunk_size: int = 1024 * 1024) -> Generator[Tuple[int, bytes, bool], None, None]:
        """
        Yields (offset, data_bytes, is_bad_block) in sequential chunks.
        """
        offset = 0
        self._file.seek(0)

        while True:
            try:
                chunk = self._file.read(chunk_size)
                if not chunk:
                    break
                yield (offset, chunk, False)
                offset += len(chunk)
            except (IOError, OSError):
                # Bad block encountered, try reading in single sectors to isolate
                for s_off in range(offset, offset + chunk_size, self.sector_size):
                    try:
                        self._file.seek(s_off)
                        s_data = self._file.read(self.sector_size)
                        if not s_data:
                            break
                        yield (s_off, s_data, False)
                    except Exception:
                        self.bad_blocks.append(s_off)
                        yield (s_off, b"\x00" * self.sector_size, True)
                offset += chunk_size

    def close(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def detect_available_sources() -> List[SourceInfo]:
    """
    Enumerate available physical disks, removable drives, and image files.
    Cross-platform (Linux, Windows via powershell/wmic, macOS).
    """
    sources: List[SourceInfo] = []
    seen_paths = set()

    # 1. Look for common disk image extensions in the workspace or home
    scan_dirs = [os.getcwd(), os.path.expanduser("~")]
    for s_dir in scan_dirs:
        try:
            for root, _, files in os.walk(s_dir, followlinks=False):
                # Limit depth to 2
                depth = root[len(s_dir):].count(os.sep)
                if depth > 2:
                    continue
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in [".img", ".raw", ".dd", ".bin", ".iso"]:
                        full_p = os.path.join(root, f)
                        if full_p not in seen_paths:
                            seen_paths.add(full_p)
                            sz = os.path.getsize(full_p)
                            sources.append(SourceInfo(
                                id=f"img_{len(sources)}",
                                name=f"Image: {f}",
                                path=full_p,
                                source_type="image_file",
                                size_bytes=sz,
                                size_formatted=format_size(sz),
                                filesystem="Raw Disk Image"
                            ))
        except Exception:
            pass

    # 2. On Windows or WSL host: detect Windows drives (D:, E:, etc.)
    is_windows = platform.system() == "Windows"
    is_wsl = "microsoft" in platform.uname().release.lower() or os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")

    if is_windows or is_wsl:
        cmd = ["powershell.exe", "-NoProfile", "-Command",
               "Get-Volume | Select-Object DriveLetter, FriendlyName, FileSystemType, DriveType, Size | ConvertTo-Json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                import json
                try:
                    data = json.loads(res.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for vol in data:
                        letter = vol.get("DriveLetter")
                        if letter and letter != "C":  # Highlight non-system drives like D: (SD card)
                            sz = vol.get("Size") or 0
                            fname = vol.get("FriendlyName") or f"Volume {letter}"
                            fstype = vol.get("FileSystemType") or "FAT32"
                            dtype = vol.get("DriveType") or "Removable"

                            # Accessible path
                            win_raw_path = f"\\\\.\\{letter}:"
                            wsl_path = f"/mnt/{letter.lower()}" if is_wsl else f"{letter}:\\"
                            sources.append(SourceInfo(
                                id=f"drive_{letter.lower()}",
                                name=f"{letter}: - {fname} ({dtype})",
                                path=wsl_path if os.path.exists(wsl_path) else win_raw_path,
                                source_type="drive_volume",
                                size_bytes=sz,
                                size_formatted=format_size(sz),
                                filesystem=fstype
                            ))
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Linux block devices / removable storage
    if os.path.exists("/sys/block"):
        try:
            for blk in os.listdir("/sys/block"):
                if blk.startswith("loop") or blk.startswith("ram"):
                    continue
                dev_path = f"/dev/{blk}"
                # Check removable flag
                removable_path = f"/sys/block/{blk}/removable"
                is_removable = False
                if os.path.exists(removable_path):
                    with open(removable_path, "r") as rf:
                        is_removable = (rf.read().strip() == "1")

                size_path = f"/sys/block/{blk}/size"
                sz = 0
                if os.path.exists(size_path):
                    with open(size_path, "r") as sf:
                        sz = int(sf.read().strip()) * 512

                if dev_path not in seen_paths and sz > 0:
                    seen_paths.add(dev_path)
                    label = f"Removable SD/USB ({blk})" if is_removable else f"Disk ({blk})"
                    sources.append(SourceInfo(
                        id=f"dev_{blk}",
                        name=f"{dev_path} - {label}",
                        path=dev_path,
                        source_type="physical_disk",
                        size_bytes=sz,
                        size_formatted=format_size(sz),
                        filesystem="Block Device"
                    ))
        except Exception:
            pass

    return sources
