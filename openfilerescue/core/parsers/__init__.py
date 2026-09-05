"""
Parser registry and exports.
Includes Image (JPEG, PNG, Camera RAW), Video (MP4, MOV, 3GP, AVI),
Documents (PDF, ZIP, DOCX, XLSX, PPTX), and Audio (MP3, WAV).
"""
from .base import BaseParser, CarvedFile
from .jpeg import JpegParser
from .png import PngParser
from .raw import RawPhotoParser
from .video import VideoParser
from .avi import AviParser
from .document import DocumentParser
from .audio import AudioParser

DEFAULT_PARSERS = [
    JpegParser(),
    PngParser(),
    RawPhotoParser(),
    VideoParser(),
    AviParser(),
    DocumentParser(),
    AudioParser(),
]

__all__ = [
    "BaseParser",
    "CarvedFile",
    "JpegParser",
    "PngParser",
    "RawPhotoParser",
    "VideoParser",
    "AviParser",
    "DocumentParser",
    "AudioParser",
    "DEFAULT_PARSERS",
]
