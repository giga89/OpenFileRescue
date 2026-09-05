"""
PNG (Portable Network Graphics) File Carver.
Walks chunk structures from IHDR to IEND with exact byte boundary precision.
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


class PngParser(BaseParser):
    name = "PNG Image"
    extensions = [".png"]
    mime_type = "image/png"

    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def match(self, header_sample: bytes) -> bool:
        return header_sample.startswith(self.PNG_SIGNATURE)

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 50 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        sig = reader.read(8)
        if sig != self.PNG_SIGNATURE:
            return None

        file_id = f"png_{offset:010x}"
        metadata: Dict[str, Any] = {
            "format": "PNG",
            "width": 0,
            "height": 0,
        }
        total_len = 8
        found_iend = False
        first_chunk = True

        while total_len < max_size:
            chunk_header = reader.read(8)
            if len(chunk_header) < 8:
                break

            chunk_len, chunk_type = struct.unpack(">I4s", chunk_header)
            total_len += 8

            # Sanity check chunk_len
            if chunk_len > 30 * 1024 * 1024 or total_len + chunk_len + 4 > max_size:
                break

            # Read chunk data + 4 bytes CRC
            chunk_body = reader.read(chunk_len + 4)
            if len(chunk_body) < chunk_len + 4:
                break
            total_len += chunk_len + 4

            # First chunk MUST be IHDR
            if first_chunk:
                first_chunk = False
                if chunk_type != b"IHDR" or chunk_len < 8:
                    return None
                w, h = struct.unpack(">II", chunk_body[:8])
                metadata["width"] = w
                metadata["height"] = h

            if chunk_type == b"IEND":
                found_iend = True
                break

        if not found_iend or metadata["width"] == 0:
            return None

        reader.seek(offset)
        png_bytes = reader.read(total_len)

        thumbnail_base64: Optional[str] = None
        if HAS_PIL and metadata["width"] > 0:
            try:
                with Image.open(io.BytesIO(png_bytes)) as im:
                    im.thumbnail((256, 256))
                    thumb_io = io.BytesIO()
                    im.save(thumb_io, format="PNG")
                    thumbnail_base64 = "data:image/png;base64," + base64.b64encode(thumb_io.getvalue()).decode("ascii")
            except Exception:
                pass

        if not thumbnail_base64 and len(png_bytes) <= 500 * 1024:
            thumbnail_base64 = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=total_len,
            extension=".png",
            mime_type="image/png",
            parser_name=self.name,
            integrity="intact",
            metadata=metadata,
            thumbnail_base64=thumbnail_base64,
            data_bytes=png_bytes if len(png_bytes) <= 2 * 1024 * 1024 else None
        )
