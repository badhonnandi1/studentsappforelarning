"""Read an image's format and pixel size from its header bytes (PNG and JPEG only).

Enough for upload checks without an imaging library: nothing is decoded or rendered.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
# Start-of-frame markers that carry the image size (baseline, progressive, lossless, ...).
SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})  # markers with no length field


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    width: int
    height: int


def _png(data: bytes) -> ImageInfo | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return ImageInfo("image/png", width, height)


def _jpeg(data: bytes) -> ImageInfo | None:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in STANDALONE:
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in SOF_MARKERS:
            if i + 9 > len(data):
                return None
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return ImageInfo("image/jpeg", width, height)
        if marker in (0xD9, 0xDA) or length < 2:  # end of image or start of scan before a frame
            return None
        i += 2 + length
    return None


def image_info(data: bytes) -> ImageInfo | None:
    """``None`` when the bytes are not a PNG or JPEG with a readable size."""
    if data.startswith(PNG_MAGIC):
        return _png(data)
    if data.startswith(JPEG_MAGIC):
        return _jpeg(data)
    return None
