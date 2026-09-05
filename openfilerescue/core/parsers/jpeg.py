"""
High-performance JPEG / JFIF / EXIF File Carver.
Accurately reconstructs JPEG streams, parses EXIF metadata, and extracts embedded thumbnails.
"""
import io
import struct
import base64
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class JpegParser(BaseParser):
    name = "JPEG Image"
    extensions = [".jpg", ".jpeg"]
    mime_type = "image/jpeg"

    # Known valid markers immediately following SOI (0xFFD8)
    VALID_POST_SOI_MARKERS = {
        0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
        0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF,
        0xDB, 0xC0, 0xC2, 0xDD, 0xFE
    }

    def match(self, header_sample: bytes) -> bool:
        """Fast check: SOI (0xFFD8) + valid marker."""
        if len(header_sample) < 4:
            return False
        return (
            header_sample[0] == 0xFF
            and header_sample[1] == 0xD8
            and header_sample[2] == 0xFF
            and header_sample[3] in self.VALID_POST_SOI_MARKERS
        )

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 50 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        # Read header block
        initial_chunk = reader.read(min(max_size, 1024 * 1024))
        if len(initial_chunk) < 4 or not self.match(initial_chunk[:4]):
            return None

        file_id = f"jpg_{offset:010x}"
        pos = 2  # skip 0xFFD8
        metadata: Dict[str, Any] = {
            "format": "JPEG",
            "camera_make": "",
            "camera_model": "",
            "date_taken": "",
            "width": 0,
            "height": 0,
        }
        thumbnail_base64: Optional[str] = None
        has_sos = False
        sos_offset = -1

        # Walk standard segments before Start Of Scan (SOS)
        chunk_buf = bytearray(initial_chunk)
        read_total = len(chunk_buf)

        while pos < len(chunk_buf) - 4:
            if chunk_buf[pos] != 0xFF:
                # Corrupted segment marker before SOS
                break

            marker = chunk_buf[pos + 1]

            # RST markers (D0-D7), TEM (01), SOI (D8) don't have lengths
            if marker in (0x00, 0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8):
                pos += 2
                continue

            if marker == 0xD9:  # EOI premature
                pos += 2
                break

            # Need 2 bytes for segment length
            if pos + 4 > len(chunk_buf):
                break

            seg_len = struct.unpack(">H", chunk_buf[pos + 2:pos + 4])[0]
            seg_end = pos + 2 + seg_len

            if seg_end > len(chunk_buf):
                # Need more data
                needed = seg_end - len(chunk_buf)
                if read_total + needed > max_size:
                    break
                more = reader.read(max(needed, 64 * 1024))
                if not more:
                    break
                chunk_buf.extend(more)
                read_total += len(more)
                if seg_end > len(chunk_buf):
                    break

            seg_data = chunk_buf[pos + 4:seg_end]

            # EXIF (APP1 - 0xFFE1)
            if marker == 0xE1 and seg_data.startswith(b"Exif\x00\x00"):
                self._parse_exif(seg_data[6:], metadata)

            # SOF0 / SOF2 for Dimensions (0xFFC0, 0xFFC2)
            elif marker in (0xC0, 0xC2) and len(seg_data) >= 5:
                h, w = struct.unpack(">HH", seg_data[1:5])
                metadata["height"] = h
                metadata["width"] = w

            # Start of Scan (0xFFDA)
            elif marker == 0xDA:
                has_sos = True
                pos = seg_end
                sos_offset = pos
                break

            pos = seg_end

        if not has_sos:
            return None

        # Now scan entropy data for EOI (0xFFD9)
        # We search in blocks
        eoi_found = False
        final_len = 0
        search_start = pos

        while True:
            # Look for 0xFFD9 from search_start
            eoi_idx = chunk_buf.find(b"\xFF\xD9", search_start)
            if eoi_idx != -1:
                # Check if this 0xFFD9 is followed by another SOI or end of image
                final_len = eoi_idx + 2
                eoi_found = True
                break

            # If not found, read more if below max_size
            if read_total >= max_size:
                # Truncate at max_size
                final_len = len(chunk_buf)
                break

            to_read = min(256 * 1024, max_size - read_total)
            more = reader.read(to_read)
            if not more:
                final_len = len(chunk_buf)
                break

            search_start = max(0, len(chunk_buf) - 1)
            chunk_buf.extend(more)
            read_total += len(more)

        if final_len < 1024:
            return None

        img_bytes = bytes(chunk_buf[:final_len])

        # Generate thumbnail
        if HAS_PIL and metadata["width"] > 0:
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    im.thumbnail((256, 256))
                    thumb_io = io.BytesIO()
                    im.save(thumb_io, format="JPEG", quality=75)
                    thumbnail_base64 = "data:image/jpeg;base64," + base64.b64encode(thumb_io.getvalue()).decode("ascii")
            except Exception:
                pass

        if not thumbnail_base64 and len(img_bytes) <= 500 * 1024:
            # For small images, we can embed directly
            thumbnail_base64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode("ascii")

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=final_len,
            extension=".jpg",
            mime_type="image/jpeg",
            parser_name=self.name,
            integrity="intact" if eoi_found else "partial",
            metadata=metadata,
            thumbnail_base64=thumbnail_base64,
            data_bytes=img_bytes if len(img_bytes) <= 2 * 1024 * 1024 else None
        )

    def _parse_exif(self, tiff_data: bytes, metadata: Dict[str, Any]):
        """Safe extraction of TIFF/EXIF tags (Make, Model, DateTime)."""
        if len(tiff_data) < 8:
            return
        endian_marker = tiff_data[:2]
        if endian_marker == b"II":
            endian = "<"
        elif endian_marker == b"MM":
            endian = ">"
        else:
            return

        try:
            magic = struct.unpack(f"{endian}H", tiff_data[2:4])[0]
            if magic != 42:
                return

            ifd0_offset = struct.unpack(f"{endian}I", tiff_data[4:8])[0]
            if ifd0_offset + 2 > len(tiff_data):
                return

            entries_count = struct.unpack(f"{endian}H", tiff_data[ifd0_offset:ifd0_offset + 2])[0]
            p = ifd0_offset + 2

            for _ in range(min(entries_count, 100)):
                if p + 12 > len(tiff_data):
                    break
                tag, tag_type, count, val_or_offset = struct.unpack(f"{endian}HHI I", tiff_data[p:p + 12])
                p += 12

                # 0x010F = Make, 0x0110 = Model, 0x0132 = DateTime
                if tag in (0x010F, 0x0110, 0x0132) and tag_type == 2:  # ASCII string
                    if count <= 4:
                        s_bytes = struct.pack(f"{endian}I", val_or_offset)[:count]
                    elif val_or_offset + count <= len(tiff_data):
                        s_bytes = tiff_data[val_or_offset:val_or_offset + count]
                    else:
                        continue

                    val_str = s_bytes.split(b"\x00")[0].decode("utf-8", errors="replace").strip()
                    if tag == 0x010F:
                        metadata["camera_make"] = val_str
                    elif tag == 0x0110:
                        metadata["camera_model"] = val_str
                    elif tag == 0x0132:
                        metadata["date_taken"] = val_str
        except Exception:
            pass
