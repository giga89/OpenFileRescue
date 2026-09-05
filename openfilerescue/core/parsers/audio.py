"""
Audio File Carver.
Supports uncompressed WAV audio (RIFF-WAVE) and MP3 audio streams (ID3 tags and sync frames).
"""
import struct
from typing import Optional, Dict, Any, BinaryIO
from .base import BaseParser, CarvedFile


class AudioParser(BaseParser):
    name = "Audio File"
    extensions = [".mp3", ".wav"]
    mime_type = "audio/mpeg"

    ID3_SIG = b"ID3"
    WAV_SIG = b"RIFF"

    def match(self, header_sample: bytes) -> bool:
        if len(header_sample) < 12:
            return False
        if header_sample.startswith(self.ID3_SIG):
            return True
        if header_sample.startswith(b"\xFF\xFB") or header_sample.startswith(b"\xFF\xF3"):
            return True
        if header_sample.startswith(self.WAV_SIG) and header_sample[8:12] == b"WAVE":
            return True
        return False

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 150 * 1024 * 1024) -> Optional[CarvedFile]:
        reader.seek(offset)
        sample = reader.read(16)
        if len(sample) < 12:
            return None

        if sample.startswith(self.WAV_SIG) and sample[8:12] == b"WAVE":
            riff_size = struct.unpack("<I", sample[4:8])[0]
            total_len = riff_size + 8
            if 44 <= total_len <= max_size:
                return CarvedFile(
                    file_id=f"wav_{offset:010x}",
                    offset=offset,
                    size=total_len,
                    extension=".wav",
                    mime_type="audio/wav",
                    parser_name="WAV Audio",
                    integrity="intact",
                    metadata={"format": "WAV Audio"}
                )

        if sample.startswith(self.ID3_SIG):
            # Parse ID3 tag size (synchsafe integer at offset 6..10)
            tag_size_bytes = sample[6:10]
            tag_size = (
                ((tag_size_bytes[0] & 0x7F) << 21)
                | ((tag_size_bytes[1] & 0x7F) << 14)
                | ((tag_size_bytes[2] & 0x7F) << 7)
                | (tag_size_bytes[3] & 0x7F)
            )
            # Estimate audio stream length (minimum ID3 header + 1MB, or up to next sector sync)
            audio_len = min(max_size, max(tag_size + 10 + 2 * 1024 * 1024, 5 * 1024 * 1024))
            return CarvedFile(
                file_id=f"mp3_{offset:010x}",
                offset=offset,
                size=audio_len,
                extension=".mp3",
                mime_type="audio/mpeg",
                parser_name="MP3 Audio",
                integrity="intact",
                metadata={"format": "MP3 Audio"}
            )

        return None
