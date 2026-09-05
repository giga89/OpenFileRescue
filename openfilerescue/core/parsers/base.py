"""
Base parser definition and data structures for file carving.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, BinaryIO
import base64


@dataclass
class CarvedFile:
    """Represents a successfully identified and recovered file."""
    file_id: str
    offset: int
    size: int
    extension: str
    mime_type: str
    parser_name: str
    integrity: str = "intact"  # "intact", "partial", "repaired"
    metadata: Dict[str, Any] = field(default_factory=dict)
    thumbnail_base64: Optional[str] = None
    data_bytes: Optional[bytes] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata for frontend communication."""
        return {
            "id": self.file_id,
            "offset": self.offset,
            "size": self.size,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "parser_name": self.parser_name,
            "integrity": self.integrity,
            "metadata": self.metadata,
            "has_thumbnail": bool(self.thumbnail_base64),
            "thumbnail": self.thumbnail_base64,
        }


class BaseParser:
    """Abstract base class for signature and structure carvers."""

    name: str = "Generic"
    extensions: list[str] = [".bin"]
    mime_type: str = "application/octet-stream"

    def match(self, header_sample: bytes) -> bool:
        """
        Fast signature check against the leading bytes of a sector.
        Must return True if header matches the format magic bytes.
        """
        raise NotImplementedError

    def parse(self, reader: BinaryIO, offset: int, max_size: int = 200 * 1024 * 1024) -> Optional[CarvedFile]:
        """
        Parse structure starting at offset, determine file boundaries and metadata.
        Returns CarvedFile on success, or None if validation fails.
        """
        raise NotImplementedError
