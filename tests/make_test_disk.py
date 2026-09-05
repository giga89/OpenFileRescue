"""
Test Disk Generator for OpenFileRescue.
Creates a synthetic raw disk image (.img) containing valid JPEGs with EXIF,
PNG files, and simulated fragmented unallocated space to test recovery accuracy.
"""
import io
import os
import struct
from PIL import Image, ImageDraw


def generate_test_jpeg(width: int, height: int, color: tuple, label: str) -> bytes:
    """Generate a real JPEG with EXIF header."""
    img = Image.new("RGB", (width, height), color=color)
    draw = ImageDraw.Draw(img)
    # Simple rectangle and pattern
    draw.rectangle([10, 10, width - 10, height - 10], outline=(255, 255, 255), width=3)
    draw.line([0, 0, width, height], fill=(255, 255, 255), width=2)
    draw.line([0, height, width, 0], fill=(255, 255, 255), width=2)

    buf = io.BytesIO()
    # Save standard JPEG
    img.save(buf, format="JPEG", quality=85)
    raw_jpg = buf.getvalue()

    # Now let's inject a minimal valid EXIF APP1 segment after SOI (0xFFD8)
    # Offset 0..7: TIFF Header (8 bytes)
    # Offset 8..9: Number of entries (2 bytes)
    # Offset 10..21: Entry 1 (12 bytes)
    # Offset 22..33: Entry 2 (12 bytes)
    # Offset 34..37: Next IFD offset (4 bytes)
    # Offset 38..49: "Kids Camera\x00" (12 bytes) -> 38 = 0x26
    # Offset 50..57: "KC-2026\x00" (8 bytes) -> 50 = 0x32
    exif_payload = (
        b"Exif\x00\x00"
        b"II\x2a\x00\x08\x00\x00\x00"  # TIFF Header: II, 42, IFD0 at 8
        b"\x02\x00"  # 2 tags
        # Tag 1: Make (0x010F), ASCII(2), count 12, offset 38 (0x26)
        b"\x0f\x01\x02\x00\x0c\x00\x00\x00\x26\x00\x00\x00"
        # Tag 2: Model (0x0110), ASCII(2), count 8, offset 50 (0x32)
        b"\x10\x01\x02\x00\x08\x00\x00\x00\x32\x00\x00\x00"
        b"\x00\x00\x00\x00"  # Next IFD = 0
        b"Kids Camera\x00"    # Offset 38 (12 bytes)
        b"KC-2026\x00"        # Offset 50 (8 bytes)
    )
    seg_len = len(exif_payload) + 2
    app1_marker = b"\xFF\xE1" + struct.pack(">H", seg_len) + exif_payload

    # Insert right after SOI (FF D8)
    modified = raw_jpg[:2] + app1_marker + raw_jpg[2:]
    return modified


def generate_test_png(width: int, height: int, color: tuple) -> bytes:
    """Generate a real valid PNG image."""
    img = Image.new("RGBA", (width, height), color=color)
    draw = ImageDraw.Draw(img)
    draw.ellipse([15, 15, width - 15, height - 15], outline=(255, 255, 0), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_image(dest_path: str, size_mb: int = 15) -> dict:
    """
    Creates a synthetic disk image file of size_mb megabytes.
    Injects test files at sector-aligned offsets (simulating deleted photos).
    """
    total_bytes = size_mb * 1024 * 1024
    image_buf = bytearray(total_bytes)

    # Fill partially with pseudo-random / filesystem markers
    # Sector 0: Fake MBR
    image_buf[0:3] = b"\xeb\x58\x90"
    image_buf[510:512] = b"\x55\xaa"

    files_info = []

    # File 1: JPEG Sunset Photo at offset 64 KB (Sector 128)
    jpg1 = generate_test_jpeg(320, 240, (255, 100, 50), "Sunset")
    off1 = 64 * 1024
    image_buf[off1:off1 + len(jpg1)] = jpg1
    files_info.append({"name": "photo_sunset.jpg", "offset": off1, "size": len(jpg1), "type": "JPEG"})

    # File 2: JPEG Beach Photo at offset 1.5 MB (Sector 3072)
    jpg2 = generate_test_jpeg(400, 300, (40, 160, 220), "Beach")
    off2 = int(1.5 * 1024 * 1024)
    image_buf[off2:off2 + len(jpg2)] = jpg2
    files_info.append({"name": "photo_beach.jpg", "offset": off2, "size": len(jpg2), "type": "JPEG"})

    # File 3: PNG Icon at offset 3.2 MB
    png1 = generate_test_png(128, 128, (60, 200, 80, 255))
    off3 = int(3.2 * 1024 * 1024)
    # Sector align
    off3 = (off3 // 512) * 512
    image_buf[off3:off3 + len(png1)] = png1
    files_info.append({"name": "icon_flower.png", "offset": off3, "size": len(png1), "type": "PNG"})

    # File 4: JPEG Mountain Photo at offset 5.8 MB
    jpg3 = generate_test_jpeg(640, 480, (110, 120, 130), "Mountain")
    off4 = int(5.8 * 1024 * 1024)
    off4 = (off4 // 512) * 512
    image_buf[off4:off4 + len(jpg3)] = jpg3
    files_info.append({"name": "photo_mountain.jpg", "offset": off4, "size": len(jpg3), "type": "JPEG"})

    with open(dest_path, "wb") as f:
        f.write(image_buf)

    return {
        "path": dest_path,
        "total_bytes": total_bytes,
        "injected_files": files_info
    }


if __name__ == "__main__":
    out_img = os.path.join(os.path.dirname(__file__), "sample_microsd.img")
    info = create_test_image(out_img, size_mb=10)
    print(f"Test image generated successfully: {out_img} ({info['total_bytes']} bytes)")
    for f in info["injected_files"]:
        print(f" - Injected {f['name']} at offset {f['offset']} ({f['size']} bytes)")
