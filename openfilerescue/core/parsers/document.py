"""
Generic Document and Archive File Carver.
Supports PDF documents, ZIP archives, and Microsoft Office / OpenDocument files (DOCX, XLSX, PPTX).
"""
import struct
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile


class DocumentParser(BaseParser):
    name = "Document / Archive"
    extensions = [".pdf", ".zip", ".docx", ".xlsx", ".pptx"]
    mime_type = "application/octet-stream"

    PDF_SIG = b"%PDF-"
    ZIP_SIG = b"PK\x03\x04"

    def match(self, header_sample: bytes) -> bool:
        if len(header_sample) < 5:
            return False
        return (
            header_sample.startswith(self.PDF_SIG)
            or header_sample.startswith(self.ZIP_SIG)
        )

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 500 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        sig = reader.read(8)
        if len(sig) < 5:
            return None

        if sig.startswith(self.PDF_SIG):
            return self._parse_pdf(reader, offset, max_size)
        elif sig.startswith(self.ZIP_SIG):
            return self._parse_zip_or_office(reader, offset, max_size)
        return None

    def _parse_pdf(self, reader: BinaryIO, offset: int, max_size: int) -> Optional[CarvedFile]:
        file_id = f"doc_{offset:010x}"
        reader.seek(offset)
        # Search forward for %%EOF marker
        chunk_size = 256 * 1024
        scanned = 0
        buf = bytearray()
        last_eof_pos = -1

        while scanned < max_size:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            buf.extend(chunk)
            scanned += len(chunk)

            # Look for %%EOF
            idx = buf.find(b"%%EOF")
            while idx != -1:
                # Keep updating to find the last %%EOF
                last_eof_pos = idx + 5
                idx = buf.find(b"%%EOF", last_eof_pos)

            # If no EOF found in first 2MB, probably truncated
            if scanned >= 10 * 1024 * 1024 and last_eof_pos == -1:
                break

        if last_eof_pos == -1:
            return None

        # Check for optional trailing whitespace / CR / LF
        final_len = last_eof_pos
        while final_len < len(buf) and buf[final_len] in (0x0A, 0x0D, 0x20):
            final_len += 1

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=final_len,
            extension=".pdf",
            mime_type="application/pdf",
            parser_name="PDF Document",
            integrity="intact",
            metadata={"format": "PDF Document"}
        )

    def _parse_zip_or_office(self, reader: BinaryIO, offset: int, max_size: int) -> Optional[CarvedFile]:
        file_id = f"zip_{offset:010x}"
        reader.seek(offset)
        
        # Walk ZIP chunks to locate End of Central Directory (EOCD: PK\x05\x06)
        probe_size = min(max_size, 20 * 1024 * 1024)
        buf = reader.read(probe_size)
        if len(buf) < 22:
            return None

        # Find EOCD marker
        eocd_sig = b"PK\x05\x06"
        eocd_idx = buf.rfind(eocd_sig)
        if eocd_idx == -1:
            return None

        # EOCD is at least 22 bytes: 4B sig, 2B disk, 2B start_disk, 2B entries_on_disk, 2B total_entries,
        # 4B central_dir_size, 4B central_dir_offset, 2B comment_len
        if eocd_idx + 22 > len(buf):
            return None

        comment_len = struct.unpack("<H", buf[eocd_idx + 20:eocd_idx + 22])[0]
        total_len = eocd_idx + 22 + comment_len

        # Inspect internal file paths to differentiate Office XML from generic ZIP
        extension = ".zip"
        mime_type = "application/zip"
        format_name = "ZIP Archive"

        if b"word/" in buf:
            extension = ".docx"
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            format_name = "Word Document (DOCX)"
        elif b"xl/" in buf:
            extension = ".xlsx"
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            format_name = "Excel Spreadsheet (XLSX)"
        elif b"ppt/" in buf:
            extension = ".pptx"
            mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            format_name = "PowerPoint Presentation (PPTX)"
        elif b"AndroidManifest.xml" in buf:
            extension = ".apk"
            mime_type = "application/vnd.android.package-archive"
            format_name = "Android Package (APK)"

        return CarvedFile(
            file_id=file_id,
            offset=offset,
            size=total_len,
            extension=extension,
            mime_type=mime_type,
            parser_name=format_name,
            integrity="intact",
            metadata={"format": format_name}
        )
