from __future__ import annotations

import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_DEPTHS = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}


def screenshot_covers_viewport(payload: bytes, viewport: object) -> bool:
    if not isinstance(viewport, list) or len(viewport) != 2 or any(type(item) is not int for item in viewport):
        return False
    dimensions = _valid_png_dimensions(payload)
    return dimensions is not None and dimensions[0] >= viewport[0] and dimensions[1] >= viewport[1]


def _valid_png_dimensions(payload: bytes) -> tuple[int, int] | None:
    chunks = _png_chunks(payload)
    if (chunks is None or not chunks or chunks[0][0] != b"IHDR" or chunks[-1] != (b"IEND", b"")
            or sum(kind == b"IHDR" for kind, _ in chunks) != 1):
        return None
    known_critical = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
    if any(kind[0] & 0x20 == 0 and kind not in known_critical for kind, _ in chunks):
        return None
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        return None
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", ihdr)
    channels = PNG_CHANNELS.get(color)
    if (not width or not height or channels is None or depth not in PNG_DEPTHS[color]
            or compression != 0 or filtering != 0 or interlace != 0):
        return None
    row_bytes = (width * channels * depth + 7) // 8
    expected = height * (row_bytes + 1)
    compressed = b"".join(data for kind, data in chunks if kind == b"IDAT")
    idat_indexes = [index for index, (kind, _) in enumerate(chunks) if kind == b"IDAT"]
    if color == 3 and not _valid_palette(chunks):
        return None
    if (not compressed or idat_indexes != list(range(min(idat_indexes), max(idat_indexes) + 1))
            or expected > 100 * 1024 * 1024):
        return None
    return (width, height) if _decoded_scanlines(compressed, expected, row_bytes, height) else None


def _valid_palette(chunks: list[tuple[bytes, bytes]]) -> bool:
    palette = [(index, data) for index, (kind, data) in enumerate(chunks) if kind == b"PLTE"]
    idat_indexes = [index for index, (kind, _) in enumerate(chunks) if kind == b"IDAT"]
    return (len(palette) == 1 and bool(idat_indexes) and palette[0][0] < min(idat_indexes)
            and 3 <= len(palette[0][1]) <= 768 and len(palette[0][1]) % 3 == 0)


def _png_chunks(payload: bytes) -> list[tuple[bytes, bytes]] | None:
    if not payload.startswith(PNG_SIGNATURE):
        return None
    offset, chunks = len(PNG_SIGNATURE), []
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(payload):
            return None
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:offset + 8 + length]
        checksum = struct.unpack(">I", payload[offset + 8 + length:end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != checksum:
            return None
        chunks.append((kind, data))
        offset = end
        if kind == b"IEND":
            return chunks if offset == len(payload) else None
    return None


def _decoded_scanlines(compressed: bytes, expected: int, row_bytes: int, height: int) -> bool:
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(compressed, expected + 1)
        stride = row_bytes + 1
        return (len(decoded) == expected and decoder.eof and not decoder.unused_data
                and all(decoded[row * stride] <= 4 for row in range(height)))
    except zlib.error:
        return False
