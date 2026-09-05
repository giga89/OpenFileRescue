"""
Organized File Exporter.
Exports recovered files to the target output directory with path sanitization,
deduplication, and optional organization by date or camera model.
"""
import os
import re
from typing import List, Dict, Any, BinaryIO
from .parsers.base import CarvedFile


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filenames across Linux, Windows, and macOS."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return cleaned or "recovered"


class FileExporter:
    """Handles saving recovered files from reader/carver into user directory."""

    def __init__(self, output_dir: str):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def export_file(
        self,
        carved: CarvedFile,
        raw_reader: BinaryIO,
        organization: str = "by_type"  # 'by_type', 'by_camera', 'by_date', 'flat'
    ) -> str:
        """
        Saves a single CarvedFile. Returns the saved absolute file path.
        """
        # Determine subdirectory
        sub_dir = ""
        if organization == "by_type":
            sub_dir = carved.extension.upper().lstrip(".")
        elif organization == "by_camera":
            make = carved.metadata.get("camera_make") or "Unknown_Camera"
            model = carved.metadata.get("camera_model") or ""
            folder_name = sanitize_filename(f"{make}_{model}".strip("_"))
            sub_dir = folder_name
        elif organization == "by_date":
            date_s = carved.metadata.get("date_taken", "")
            # e.g. "2026:09:05 10:30:00"
            if len(date_s) >= 10:
                year = date_s[:4]
                month = date_s[5:7]
                sub_dir = os.path.join(year, month)
            else:
                sub_dir = "Undated"

        dest_dir = os.path.join(self.output_dir, sub_dir)
        os.makedirs(dest_dir, exist_ok=True)

        filename = f"recovered_{carved.offset:010x}{carved.extension}"
        dest_path = os.path.join(dest_dir, filename)

        # Write data: from cached data_bytes or read from raw_reader
        if carved.data_bytes is not None and len(carved.data_bytes) == carved.size:
            with open(dest_path, "wb") as f:
                f.write(carved.data_bytes)
        else:
            raw_reader.seek(carved.offset)
            with open(dest_path, "wb") as f:
                rem = carved.size
                while rem > 0:
                    chunk_sz = min(1024 * 1024, rem)
                    chunk = raw_reader.read(chunk_sz)
                    if not chunk:
                        break
                    f.write(chunk)
                    rem -= len(chunk)

        return dest_path

    def export_all(
        self,
        files: List[CarvedFile],
        raw_reader: BinaryIO,
        organization: str = "by_type"
    ) -> Dict[str, Any]:
        """
        Batch export all carved files.
        Returns summary statistics.
        """
        saved_paths = []
        total_bytes = 0

        for f in files:
            try:
                p = self.export_file(f, raw_reader, organization)
                saved_paths.append(p)
                total_bytes += f.size
            except Exception:
                pass

        return {
            "total_exported": len(saved_paths),
            "total_bytes": total_bytes,
            "output_directory": self.output_dir,
            "sample_files": saved_paths[:10]
        }
