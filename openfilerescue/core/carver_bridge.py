"""
Universal Carver Bridge for OpenFileRescue.
Executes deep signature carving on raw drives (Windows \\\\.\\D: or Linux /dev/sd* or .img),
saves recovered files immediately, and emits real-time JSON events on stdout for the Web UI.
"""
import sys
import os
import json
import time
from typing import Dict, Any

# Add workspace to path
workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from openfilerescue.core.parsers import DEFAULT_PARSERS
from openfilerescue.core.exporter import FileExporter


def run_bridge_scan(
    source_path: str,
    output_dir: str = "recovered_files",
    max_scan_gb: float = 32.0,
    sector_step: int = 512,
    grid_buckets: int = 120
):
    # Normalize Windows drive letter
    if len(source_path) == 2 and source_path[1] == ":":
        source_path = rf"\\.\{source_path}"
    elif source_path.startswith("/mnt/") and len(source_path) >= 6:
        # e.g. /mnt/d or /mnt/d/
        letter = source_path[5].upper()
        if os.name == "nt" or sys.platform.startswith("win"):
            source_path = rf"\\.\{letter}:"

    out_abs = os.path.abspath(os.path.join(workspace_dir, output_dir))
    os.makedirs(out_abs, exist_ok=True)
    exporter = FileExporter(out_abs)

    total_size = 31258738688  # 29.11 GB default for microSD
    try:
        if not source_path.startswith(r"\\."):
            total_size = os.path.getsize(source_path)
    except Exception:
        pass

    scan_limit = min(total_size, int(max_scan_gb * 1024 * 1024 * 1024))
    sector_map = [0] * grid_buckets
    found_files = []
    file_counts = {}

    start_time = time.time()
    last_event_time = start_time
    offset = 0
    buf_size = 4 * 1024 * 1024  # 4MB buffer

    try:
        reader = open(source_path, "rb")
    except Exception as e:
        print(json.dumps({"type": "error", "message": f"Failed to open source {source_path}: {e}"}), flush=True)
        return

    print(json.dumps({
        "type": "start",
        "source": source_path,
        "total_bytes": scan_limit,
        "output_dir": out_abs
    }), flush=True)

    with reader:
        while offset < scan_limit:
            to_read = min(buf_size, scan_limit - offset)
            try:
                reader.seek(offset)
                chunk = reader.read(to_read)
                if not chunk:
                    break
            except Exception:
                offset += 512
                continue

            chunk_len = len(chunk)
            chunk_pos = 0

            while chunk_pos < chunk_len:
                abs_offset = offset + chunk_pos
                sample = chunk[chunk_pos:chunk_pos + 64]

                bucket_idx = min(grid_buckets - 1, int((abs_offset / scan_limit) * grid_buckets))
                if sector_map[bucket_idx] == 0:
                    sector_map[bucket_idx] = 1

                file_found = None
                for p in DEFAULT_PARSERS:
                    if p.match(sample):
                        parsed = p.parse(reader, abs_offset)
                        if parsed and parsed.size > 0:
                            file_found = parsed
                            break

                if file_found:
                    found_files.append(file_found)
                    sector_map[bucket_idx] = 2

                    ext = file_found.extension.upper().lstrip(".")
                    file_counts[ext] = file_counts.get(ext, 0) + 1

                    # Save to disk
                    saved_path = ""
                    try:
                        saved_path = exporter.export_file(file_found, reader, organization="by_type")
                    except Exception:
                        pass

                    # Emit found event
                    event = {
                        "type": "found",
                        "file": {
                            "id": file_found.file_id,
                            "offset": file_found.offset,
                            "size": file_found.size,
                            "extension": file_found.extension,
                            "mime_type": file_found.mime_type,
                            "parser_name": file_found.parser_name,
                            "integrity": file_found.integrity,
                            "metadata": file_found.metadata,
                            "has_thumbnail": bool(file_found.thumbnail_base64),
                            "thumbnail": file_found.thumbnail_base64,
                            "saved_path": saved_path
                        }
                    }
                    print(json.dumps(event), flush=True)

                    skip = ((file_found.size + sector_step - 1) // sector_step) * sector_step
                    chunk_pos += skip
                else:
                    chunk_pos += sector_step

            offset += chunk_len

            # Progress event
            now = time.time()
            if now - last_event_time >= 0.35 or offset >= scan_limit:
                elapsed = max(0.001, now - start_time)
                pct = round((offset / scan_limit) * 100.0, 1)
                speed = (offset / elapsed)
                rem_sec = round((scan_limit - offset) / max(1.0, speed), 1)

                prog = {
                    "type": "progress",
                    "percent": pct,
                    "scanned_bytes": offset,
                    "total_bytes": scan_limit,
                    "files_found": len(found_files),
                    "bytes_per_second": speed,
                    "elapsed_seconds": round(elapsed, 1),
                    "eta_seconds": rem_sec,
                    "status_message": f"Scanning... ({len(found_files)} files discovered)",
                    "sector_map": sector_map,
                    "file_counts_by_type": file_counts
                }
                print(json.dumps(prog), flush=True)
                last_event_time = now

    sector_map = [2 if s == 2 else 1 for s in sector_map]
    print(json.dumps({
        "type": "finished",
        "total_files": len(found_files),
        "total_bytes": offset,
        "sector_map": sector_map,
        "output_dir": out_abs
    }), flush=True)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else r"\\.\D:"
    out = sys.argv[2] if len(sys.argv) > 2 else "recovered_sd"
    max_g = float(sys.argv[3]) if len(sys.argv) > 3 else 32.0
    run_bridge_scan(src, out, max_g)
