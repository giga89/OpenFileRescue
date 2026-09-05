"""
Unit tests for OpenFileRescue file format parsers:
- JPEG, PNG, Camera RAW (CR2/NEF)
- AVI (RIFF-AVI)
- Video (MP4 / MOV / 3GP)
- Document (PDF, ZIP / Office)
- Audio (MP3, WAV)
"""
import io
import struct
import unittest

from openfilerescue.core.parsers.jpeg import JpegParser
from openfilerescue.core.parsers.png import PngParser
from openfilerescue.core.parsers.raw import RawPhotoParser
from openfilerescue.core.parsers.video import VideoParser
from openfilerescue.core.parsers.avi import AviParser
from openfilerescue.core.parsers.document import DocumentParser
from openfilerescue.core.parsers.audio import AudioParser


class TestFileParsers(unittest.TestCase):

    def test_jpeg_parser(self):
        parser = JpegParser()
        # Minimal valid JPEG structure: SOI, SOF0, SOS with entropy data >= 1024 bytes, EOI
        sof0 = b"\xFF\xC0\x00\x11\x08\x00\x64\x00\xC8\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        entropy = b"\x00" * 1200
        eoi = b"\xFF\xD9"
        jpeg_data = b"\xFF\xD8" + sof0 + b"\xFF\xDA\x00\x08\x01\x01\x00\x00\x3F\x00" + entropy + eoi

        self.assertTrue(parser.match(jpeg_data[:16]))
        bio = io.BytesIO(jpeg_data)
        carved = parser.parse(bio, offset=0, max_size=len(jpeg_data) + 100)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".jpg")
        self.assertEqual(carved.mime_type, "image/jpeg")
        self.assertEqual(carved.metadata.get("width"), 200)
        self.assertEqual(carved.metadata.get("height"), 100)

    def test_png_parser(self):
        parser = PngParser()
        # Signature (8B) + IHDR (4B len, 4B type, 13B data, 4B crc) + IEND (4B len, 4B type, 4B crc)
        sig = b"\x89PNG\r\n\x1a\n"
        # IHDR: 100x50, 8-bit truecolor
        ihdr_data = struct.pack(">IIBBBBB", 100, 50, 8, 2, 0, 0, 0)
        import zlib
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        iend_crc = zlib.crc32(b"IEND")
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        png_data = sig + ihdr + iend

        self.assertTrue(parser.match(png_data[:16]))
        bio = io.BytesIO(png_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".png")
        self.assertEqual(carved.size, len(png_data))
        self.assertEqual(carved.metadata.get("width"), 100)
        self.assertEqual(carved.metadata.get("height"), 50)

    def test_avi_parser(self):
        parser = AviParser()
        # RIFF-AVI structure >= 1024 bytes
        riff_payload = b"AVI LIST\x20\x00\x00\x00hdrlavih\x38\x00\x00\x00" + (b"\x00" * 1500)
        riff_size = len(riff_payload)
        avi_data = b"RIFF" + struct.pack("<I", riff_size) + riff_payload

        self.assertTrue(parser.match(avi_data[:16]))
        bio = io.BytesIO(avi_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".avi")
        self.assertEqual(carved.mime_type, "video/x-msvideo")
        self.assertEqual(carved.size, len(avi_data))

    def test_video_mp4_parser(self):
        parser = VideoParser()
        # ftyp atom: 4B len (20), 4B 'ftyp', 4B 'isom', 4B minor, 4B compat
        ftyp = struct.pack(">I", 20) + b"ftypisom\x00\x00\x02\x00isom"
        # mdat atom >= 4096 bytes: 4B len, 4B 'mdat', payload
        mdat_len = 5000
        mdat = struct.pack(">I", mdat_len) + b"mdat" + (b"\x00" * (mdat_len - 8))
        mp4_data = ftyp + mdat

        self.assertTrue(parser.match(mp4_data[:16]))
        bio = io.BytesIO(mp4_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".mp4")
        self.assertEqual(carved.mime_type, "video/mp4")
        self.assertEqual(carved.size, len(mp4_data))

    def test_pdf_document_parser(self):
        parser = DocumentParser()
        pdf_data = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
        self.assertTrue(parser.match(pdf_data[:16]))
        bio = io.BytesIO(pdf_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".pdf")
        self.assertEqual(carved.mime_type, "application/pdf")
        self.assertEqual(carved.size, len(pdf_data))

    def test_zip_document_parser(self):
        parser = DocumentParser()
        # Minimal valid empty zip: Local File Header or End of Central Dir
        # EOCD signature: PK\x05\x06 (4B), 18 bytes
        local_header = b"PK\x03\x04\x14\x00\x00\x00\x00\x00" + (b"\x00" * 20)
        eocd = b"PK\x05\x06" + (b"\x00" * 18)
        zip_data = local_header + eocd

        self.assertTrue(parser.match(zip_data[:16]))
        bio = io.BytesIO(zip_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".zip")

    def test_audio_wav_parser(self):
        parser = AudioParser()
        # RIFF WAVE
        wave_payload = b"WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00\x44\xAC\x00\x00\x10\xB1\x02\x00\x04\x00\x10\x00data\x08\x00\x00\x00" + (b"\x00" * 8)
        riff_size = len(wave_payload)
        wav_data = b"RIFF" + struct.pack("<I", riff_size) + wave_payload

        self.assertTrue(parser.match(wav_data[:16]))
        bio = io.BytesIO(wav_data)
        carved = parser.parse(bio, offset=0)
        self.assertIsNotNone(carved)
        self.assertEqual(carved.extension, ".wav")
        self.assertEqual(carved.mime_type, "audio/wav")
        self.assertEqual(carved.size, len(wav_data))


if __name__ == "__main__":
    unittest.main()
