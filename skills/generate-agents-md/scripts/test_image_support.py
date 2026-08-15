from __future__ import annotations

import struct
import zlib


def png_bytes(
    width: int, height: int, *, truncate_pixels: bool = False,
    invalid_iend: bool = False, color_type: int = 0, unknown_critical: bool = False,
    split_idat: bool = False,
) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    pixels = b"\0" if truncate_pixels else b"".join(b"\0" + b"\0" * width for _ in range(height))
    iend = b"not-empty" if invalid_iend else b""
    unknown = chunk(b"ABCD", b"unknown") if unknown_critical else b""
    compressed = zlib.compress(pixels)
    middle = len(compressed) // 2
    image_data = (chunk(b"IDAT", compressed[:middle]) + chunk(b"tEXt", b"gap")
                  + chunk(b"IDAT", compressed[middle:])) if split_idat else chunk(b"IDAT", compressed)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + unknown + image_data + chunk(b"IEND", iend)
