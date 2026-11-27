"""PNG and JPEG header parsing for upload checks."""

from __future__ import annotations

import struct

import pytest

from app.shared.image_header import ImageInfo, image_info

pytestmark = pytest.mark.unit


def png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00" * 4


def jpeg(width: int, height: int, *, sof: int = 0xC0) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    frame = b"\xff" + bytes([sof]) + struct.pack(">HBHH", 17, 8, height, width) + b"\x00" * 10
    return b"\xff\xd8" + b"\xff\x01" + b"\xff" + app0 + frame + b"\xff\xd9"


def test_png_and_jpeg_sizes() -> None:
    assert image_info(png(640, 480)) == ImageInfo("image/png", 640, 480)
    assert image_info(jpeg(800, 600)) == ImageInfo("image/jpeg", 800, 600)
    assert image_info(jpeg(300, 200, sof=0xC2)) == ImageInfo("image/jpeg", 300, 200)  # progressive


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a" + b"\x00" * 20,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,  # no IHDR
        b"\xff\xd8\xff\xe0\x00\x10" + b"\x00" * 4,  # truncated before any frame
        b"\xff\xd8\xff\xda\x00\x08" + b"\x00" * 10,  # scan before frame
        b"\xff\xd8\xff\xe0\x00\x01" + b"\x00" * 10,  # bad segment length
        b"\xff\xd8\x00\x00\x00\x00",  # not a marker
        b"\xff\xd8\xff\xc0\x00\x11\x08\x00",  # frame cut short
    ],
)
def test_rejects_other_or_broken_bytes(data: bytes) -> None:
    assert image_info(data) is None
