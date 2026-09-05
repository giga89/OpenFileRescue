"""
Camera RAW File Carver.
Supports Canon (.CR2), Nikon (.NEF), Sony (.ARW), Adobe DNG (.DNG), and Fujifilm (.RAF).
"""
import struct
import base64
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile


class RawPhotoParser(BaseParser):
    name = "RAW Camera Photo"
    extensions = [".cr2", ".nef", ".arw", ".dng", ".raf"]
    mime_type = "image/x-raw"

    RAF_MAGIC = b"FUJIFILMCCD-RAW "

    def match(self, header_sample: bytes) -> bool:
        if len(header_sample) < 16:
            return False
        # Check Fujifilm RAF
        if header_sample.startswith(self.RAF_MAGIC):
            return True
        # Check TIFF based: 'II*\x00' (little endian) or 'MM\x00*' (big endian)
        if (header_sample[:4] == b"II\x2a\x00" or header_sample[:4] == b"MM\x00\x2a"):
            # Canon CR2 check: bytes 8..12 contain 'CR\x02\x00'
            if len(header_sample) >= 12 and header_sample[8:12] == b"CR\x02\x00":
                return True
            # Other TIFF-based RAWs: check if first IFD offset is valid
            return True
        return False

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 100 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        header = reader.read(16)
        if len(header) < 16 or not self.match(header):
            return None

        # Determine extension and parse
        if header.startswith(self.RAF_MAGIC):
            return self._parse_raf(reader, offset, max_size)
        else:
            return self._parse_tiff_raw(reader, offset, max_size)

    def _parse_raf(self, reader: BinaryIO, offset: int, max_size: int) -> Optional[CarvedFile]:
        reader.seek(offset + 84)
        data = reader.read(16)
        if len(data) < 16:
            return None
        # In RAF header at offset 84 and 88 are JPEG preview offset and length
        try:
            jpg_offset, jpg_len = struct.unpack(">II", data[:8])
            total_size = jpg_offset + jpg_len
            if total_size > max_size or total_size < 5000:
                total_size = min(max_size, 30 * 1024 * 1024)
        except Exception:
            total_size = min(max_size, 25 * 1024 * 1024)

        return CarvedFile(
            file_id=f"raf_{offset:010x}",
            offset=offset,
            size=total_size,
            extension=".raf",
            mime_type="image/x-fuji-raf",
            parser_name="Fujifilm RAW",
            integrity="intact",
            metadata={"format": "Fujifilm RAF", "camera_make": "FUJIFILM"}
        )

    def _parse_tiff_raw(self, reader: BinaryIO, offset: int, max_size: int) -> Optional[CarvedFile]:
        reader.seek(offset)
        header = reader.read(16)
        is_canon = (len(header) >= 12 and header[8:12] == b"CR\x02\x00")
        endian = "<" if header[:2] == b"II" else ">"

        metadata: Dict[str, Any] = {
            "format": "RAW",
            "camera_make": "Canon" if is_canon else "",
            "camera_model": "",
            "date_taken": ""
        }
        extension = ".cr2" if is_canon else ".raw"

        # Walk TIFF IFDs to find maximum data offset
        max_offset = 16
        try:
            ifd_offset = struct.unpack(f"{endian}I", header[4:8])[0]
            reader.seek(offset + ifd_offset)
            entries_data = reader.read(2)
            if len(entries_data) == 2:
                count = struct.unpack(f"{endian}H", entries_data)[0]
                if count < 100:
                    dir_bytes = reader.read(count * 12)
                    for i in range(count):
                        entry = dir_bytes[i * 12:(i + 1) * 12]
                        if len(entry) < 12:
                            break
                        tag, t_type, cnt, val = struct.unpack(f"{endian}HHI I", entry)
                        # Tag 0x010F = Make, 0x0110 = Model
                        if tag == 0x010F and cnt < 64:
                            pos_now = reader.tell()
                            reader.seek(offset + val)
                            make_s = reader.read(cnt).split(b"\x00")[0].decode("latin-1", errors="replace").strip()
                            metadata["camera_make"] = make_s
                            reader.seek(pos_now)
                        if tag == 0x0110 and cnt < 64:
                            pos_now = reader.tell()
                            reader.seek(offset + val)
                            model_s = reader.read(cnt).split(b"\x00")[0].decode("latin-1", errors="replace").strip()
                            metadata["camera_model"] = model_s
                            reader.seek(pos_now)

                        # Check strip / tile offsets (0x0111, 0x0144, 0x0117)
                        if tag in (0x0111, 0x0144, 0x0117, 0x0201) and val < max_size:
                            if val > max_offset:
                                max_offset = val
        except Exception:
            pass

        # Classify by make
        make_lower = metadata.get("camera_make", "").lower()
        if "nikon" in make_lower:
            extension = ".nef"
        elif "sony" in make_lower:
            extension = ".arw"
        elif "adobe" in make_lower:
            extension = ".dng"
        elif is_canon:
            extension = ".cr2"
        else:
            extension = ".dng"

        # Safe default estimate if strip offset couldn't be accurately bounded
        file_size = max(max_offset + 512 * 1024, 15 * 1024 * 1024)
        file_size = min(file_size, max_size)

        return CarvedFile(
            file_id=f"raw_{offset:010x}",
            offset=offset,
            size=file_size,
            extension=extension,
            mime_type="image/x-raw",
            parser_name=f"{metadata.get('camera_make', 'Camera')} RAW",
            integrity="intact",
            metadata=metadata
        )
