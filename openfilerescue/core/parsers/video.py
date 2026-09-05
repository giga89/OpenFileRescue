"""
Enhanced MP4 / QuickTime (MOV) / 3GP Video File Carver.
Parses ISO base media file format atom chains (ftyp, moov, mdat, free) with precise length bounds
and supports action-camera 'mdat-first' unfinalized recordings.
"""
import struct
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile


class VideoParser(BaseParser):
    name = "MP4 / MOV / 3GP Video"
    extensions = [".mp4", ".mov", ".3gp", ".m4v"]
    mime_type = "video/mp4"

    VALID_TOP_ATOMS = {
        b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot", b"uuid"
    }

    KNOWN_BRANDS = {
        b"qt  ": (".mov", "video/quicktime", "QuickTime"),
        b"isom": (".mp4", "video/mp4", "MP4 (ISO)"),
        b"iso2": (".mp4", "video/mp4", "MP4 (ISO2)"),
        b"mp41": (".mp4", "video/mp4", "MP4 v1"),
        b"mp42": (".mp4", "video/mp4", "MP4 v2"),
        b"avc1": (".mp4", "video/mp4", "MP4 (AVC)"),
        b"M4V ": (".m4v", "video/x-m4v", "Apple M4V"),
        b"3gp4": (".3gp", "video/3gpp", "3GPP Mobile Video"),
        b"3gp5": (".3gp", "video/3gpp", "3GPP Mobile Video"),
        b"3gp6": (".3gp", "video/3gpp", "3GPP Mobile Video"),
        b"3g2a": (".3gp", "video/3gpp2", "3GPP2 Mobile Video"),
        b"MSNV": (".mp4", "video/mp4", "Sony Video"),
        b"XAVC": (".mp4", "video/mp4", "Sony XAVC"),
    }

    def match(self, header_sample: bytes) -> bool:
        if len(header_sample) < 12:
            return False
        # Offset 4..8 contains atom name
        atom_type = header_sample[4:8]
        if atom_type == b"ftyp":
            return True
        if atom_type in (b"moov", b"wide", b"mdat") and header_sample[:4] not in (b"\x00\x00\x00\x00",):
            return True
        return False

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 4 * 1024 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        header = reader.read(16)
        if len(header) < 12 or not self.match(header):
            return None

        file_id = f"vid_{offset:010x}"
        atom_type = header[4:8]
        major_brand_bytes = header[8:12] if atom_type == b"ftyp" else b""
        
        ext_info = self.KNOWN_BRANDS.get(major_brand_bytes, (".mp4", "video/mp4", "MP4 Video"))
        extension, mime_type, brand_label = ext_info

        metadata: Dict[str, Any] = {
            "format": brand_label,
            "major_brand": major_brand_bytes.decode("latin-1", errors="replace").strip(),
            "width": 0,
            "height": 0,
            "duration": 0
        }

        total_len = 0
        reader.seek(offset)
        seen_mdat = False
        seen_moov = False

        while total_len < max_size:
            atom_head = reader.read(8)
            if len(atom_head) < 8:
                break

            atom_size, a_type = struct.unpack(">I4s", atom_head)

            # Extended 64-bit size
            if atom_size == 1:
                ext_bytes = reader.read(8)
                if len(ext_bytes) < 8:
                    break
                atom_size = struct.unpack(">Q", ext_bytes)[0]
                content_len = atom_size - 16
            elif atom_size == 0:
                # Extends to end of medium
                break
            else:
                content_len = atom_size - 8

            # Validate atom type is printable ASCII
            if not all(32 <= b <= 126 for b in a_type):
                break

            if a_type == b"mdat":
                seen_mdat = True
            elif a_type == b"moov":
                seen_moov = True
                # Parse mvhd or tkhd if possible to extract dimensions and duration
                self._inspect_moov(reader, reader.tell(), content_len, metadata)

            total_len += atom_size

            # Seek to next atom
            try:
                reader.seek(reader.tell() + content_len)
            except Exception:
                break

            # Check next atom signature
            next_sample = reader.read(8)
            if len(next_sample) < 8:
                break
            next_type = next_sample[4:8]
            reader.seek(reader.tell() - 8)

            if next_type not in self.VALID_TOP_ATOMS and not all(32 <= b <= 126 for b in next_type):
                break

        if total_len < 4096:
            return None

        total_len = min(total_len, max_size)

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=total_len,
            extension=extension,
            mime_type=mime_type,
            parser_name=brand_label,
            integrity="intact" if (seen_mdat and seen_moov) else "partial",
            metadata=metadata
        )

    def _inspect_moov(self, reader: BinaryIO, moov_start: int, moov_len: int, metadata: Dict[str, Any]):
        """Safe inspection of moov children (mvhd, trak) for dimensions and duration."""
        try:
            cur_pos = reader.tell()
            chunk = reader.read(min(moov_len, 64 * 1024))
            reader.seek(cur_pos)

            # Search for mvhd (Movie Header)
            mvhd_idx = chunk.find(b"mvhd")
            if mvhd_idx != -1 and mvhd_idx + 24 < len(chunk):
                # mvhd structure: version (1 byte), flags (3 bytes), creation (4/8 bytes), mod (4/8), timescale (4), duration (4/8)
                ver = chunk[mvhd_idx + 4]
                if ver == 0 and mvhd_idx + 24 <= len(chunk):
                    timescale, duration = struct.unpack(">II", chunk[mvhd_idx + 16:mvhd_idx + 24])
                    if timescale > 0:
                        metadata["duration"] = round(duration / timescale, 1)

            # Search for tkhd (Track Header) for video track width and height
            tkhd_idx = chunk.find(b"tkhd")
            if tkhd_idx != -1 and tkhd_idx + 84 <= len(chunk):
                # Fixed-point 16.16 width and height at end of tkhd
                w_fixed, h_fixed = struct.unpack(">II", chunk[tkhd_idx + 76:tkhd_idx + 84])
                w = w_fixed >> 16
                h = h_fixed >> 16
                if 120 <= w <= 8192 and 120 <= h <= 8192:
                    metadata["width"] = w
                    metadata["height"] = h
        except Exception:
            pass
