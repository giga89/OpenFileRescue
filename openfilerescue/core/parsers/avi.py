"""
AVI (Audio Video Interleave) / DivX Video Carver.
Reconstructs RIFF-AVI containers commonly produced by action cams, dashcams, and digital cameras.
"""
import struct
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile


class AviParser(BaseParser):
    name = "AVI Video"
    extensions = [".avi"]
    mime_type = "video/x-msvideo"

    def match(self, header_sample: bytes) -> bool:
        if len(header_sample) < 12:
            return False
        return (
            header_sample[:4] == b"RIFF"
            and header_sample[8:12] in (b"AVI ", b"AVIX")
        )

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 4 * 1024 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        head = reader.read(64)
        if len(head) < 12 or not self.match(head):
            return None

        file_id = f"avi_{offset:010x}"
        riff_size = struct.unpack("<I", head[4:8])[0]
        total_len = riff_size + 8

        metadata: Dict[str, Any] = {
            "format": "AVI Video",
            "width": 0,
            "height": 0,
            "fps": 0.0
        }

        # Inspect avih chunk in first 2KB for resolution and framerate
        try:
            reader.seek(offset)
            probe = reader.read(min(2048, total_len))
            avih_idx = probe.find(b"avih")
            if avih_idx != -1 and avih_idx + 44 <= len(probe):
                # avih structure: 4 bytes size, dwMicroSecPerFrame (4B), dwMaxBytesPerSec (4B),
                # dwPaddingGranularity (4B), dwFlags (4B), dwTotalFrames (4B), dwInitialFrames (4B),
                # dwStreams (4B), dwSuggestedBufferSize (4B), dwWidth (4B), dwHeight (4B)
                microsec = struct.unpack("<I", probe[avih_idx + 8:avih_idx + 12])[0]
                total_frames = struct.unpack("<I", probe[avih_idx + 24:avih_idx + 28])[0]
                w, h = struct.unpack("<II", probe[avih_idx + 40:avih_idx + 48])
                if 120 <= w <= 8192 and 120 <= h <= 8192:
                    metadata["width"] = w
                    metadata["height"] = h
                if microsec > 0:
                    metadata["fps"] = round(1_000_000.0 / microsec, 2)
                    if total_frames > 0:
                        metadata["duration"] = round((total_frames * microsec) / 1_000_000.0, 1)
        except Exception:
            pass

        if total_len < 1024 or total_len > max_size:
            return None

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=total_len,
            extension=".avi",
            mime_type="video/x-msvideo",
            parser_name=self.name,
            integrity="intact",
            metadata=metadata
        )
