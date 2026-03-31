import gzip
import logging

from pathlib import Path
from typing import BinaryIO


logger = logging.getLogger(__name__)

# Old format (Blender <=4.x): 12-byte header
#   BLENDER (7) + pointer_size (1: '_'/'-') + endian (1: 'v'/'V') + version (3 digits)
# New format (Blender 5.0+): 17-byte header
#   BLENDER (7) + format_version (2) + pointer_size (1: '-') + flags (2) + endian (1: 'v'/'V') + version (4 digits)
_BLEND_HEADER_MAX_SIZE = 17
_BLEND_MAGIC = b"BLENDER"
_GZIP_MAGIC = b"\x1f\x8b"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def read_blend_file_version(file_path: Path) -> tuple[int, int, int] | None:
    """
    Reads the Blender version from a .blend file header.

    Handles raw, gzip-compressed, and zstd-compressed .blend files.
    Supports both the classic 12-byte header (Blender <=4.x) and the
    17-byte header introduced in Blender 5.0.

    Args:
        file_path: Path to the .blend file.

    Returns:
        A version tuple (major, minor, patch) or None if the version cannot be determined.
    """
    try:
        with file_path.open("rb") as f:
            magic = f.read(4)
            f.seek(0)

            if magic[:2] == _GZIP_MAGIC:
                header = _read_gzip_blend_header(file_path)
            elif magic[:4] == _ZSTD_MAGIC:
                header = _read_zstd_blend_header(f)
            else:
                header = f.read(_BLEND_HEADER_MAX_SIZE)

        return _parse_blend_header(header)
    except (OSError, ValueError, UnicodeDecodeError):
        logger.debug(f"Failed to read blend file version from {file_path}")
        return None


def _parse_blend_header(header: bytes | None) -> tuple[int, int, int] | None:
    """
    Parses a Blender file header and extracts the version.

    Supports:
        - Classic format (<=4.x): ``BLENDER`` + pointer_size + endian + 3-digit version (12 bytes)
        - New format (5.0+): ``BLENDER`` + format_version + pointer_size + flags + endian + 4-digit version (17 bytes)

    Detection: byte 7 is ``_`` or ``-`` for old format, a digit for new format.

    Args:
        header: The raw header bytes (at least 12, ideally 17).

    Returns:
        A version tuple (major, minor, patch) or None.
    """
    if not header or len(header) < 12 or header[:7] != _BLEND_MAGIC:
        return None

    byte7 = header[7:8]

    # Classic format: byte 7 is pointer_size ('_' or '-'), byte 8 is endian ('v' or 'V')
    if byte7 in (b"_", b"-"):
        version_int = int(header[9:12].decode("ascii"))
    # New format (Blender 5.0+): byte 7 is a digit, version at bytes 13-16
    elif byte7.isdigit() and len(header) >= 17:
        version_int = int(header[13:17].decode("ascii"))
    else:
        return None

    major = version_int // 100
    minor = version_int % 100
    return (major, minor, 0)


def _read_gzip_blend_header(file_path: Path) -> bytes:
    """Reads the first bytes from a gzip-compressed .blend file."""
    with gzip.open(file_path, "rb") as gz:
        return gz.read(_BLEND_HEADER_MAX_SIZE)


def _read_zstd_blend_header(f: "BinaryIO") -> bytes | None:
    """
    Reads the header from a zstd-compressed .blend file using streaming decompression.

    Blender's zstd .blend files are a series of individually-compressed zstd frames.
    The first frame contains the file header.
    """
    f.seek(0)

    try:
        import zstandard  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("zstandard module not available, cannot read zstd-compressed blend file")
        return None

    try:
        decompressor = zstandard.ZstdDecompressor()
        reader = decompressor.stream_reader(f)
        return reader.read(_BLEND_HEADER_MAX_SIZE)
    except Exception:
        logger.debug("Failed to decompress zstd blend file header")
        return None


def blend_file_version_string(version: tuple[int, int, int]) -> str:
    """Formats a Blender version tuple as a display string like '4.5.0'."""
    return f"{version[0]}.{version[1]}.{version[2]}"
