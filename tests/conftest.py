"""Shared fixtures and helpers for the sortphotos test-suite."""

from __future__ import annotations

import os
import struct
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

# EXIF tag ids
_TAG_DATETIME = 0x0132  # IFD0 "Image DateTime"
_TAG_EXIF_IFD = 0x8769  # pointer to the EXIF sub-IFD
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_DATETIME_DIGITIZED = 0x9004
_ASCII = 2
_LONG = 4


def _ifd(entries: list[tuple[int, int, int, bytes]], offset: int) -> tuple[bytes, bytes]:
    """Build a little-endian IFD located at ``offset``.

    Each entry is ``(tag, type, count, payload)``. Payloads larger than four
    bytes are stored after the IFD. Returns ``(ifd_bytes, data_bytes)``.
    """
    ifd_size = 2 + 12 * len(entries) + 4
    data_offset = offset + ifd_size
    ifd = struct.pack("<H", len(entries))
    data = b""
    for tag, typ, count, payload in sorted(entries):
        if len(payload) <= 4:
            ifd += struct.pack("<HHI", tag, typ, count) + payload.ljust(4, b"\x00")
        else:
            ifd += struct.pack("<HHII", tag, typ, count, data_offset + len(data))
            data += payload
    ifd += struct.pack("<I", 0)
    return ifd, data


def build_exif_jpeg(
    date_time_original: str | None = None,
    date_time_digitized: str | None = None,
    image_date_time: str | None = None,
    payload: bytes = b"",
) -> bytes:
    """Return the bytes of a minimal JPEG file containing the given EXIF dates."""

    def ascii_entry(tag: int, value: str) -> tuple[int, int, int, bytes]:
        raw = value.encode("ascii") + b"\x00"
        return (tag, _ASCII, len(raw), raw)

    exif_entries = []
    if date_time_original is not None:
        exif_entries.append(ascii_entry(_TAG_DATETIME_ORIGINAL, date_time_original))
    if date_time_digitized is not None:
        exif_entries.append(ascii_entry(_TAG_DATETIME_DIGITIZED, date_time_digitized))

    ifd0_entries = []
    if image_date_time is not None:
        ifd0_entries.append(ascii_entry(_TAG_DATETIME, image_date_time))

    tiff_header = b"II*\x00" + struct.pack("<I", 8)
    if exif_entries:
        # compute size of IFD0 (with pointer entry) to know where the EXIF IFD goes
        placeholder = [*ifd0_entries, (_TAG_EXIF_IFD, _LONG, 1, b"\x00" * 4)]
        ifd0, ifd0_data = _ifd(placeholder, 8)
        exif_offset = 8 + len(ifd0) + len(ifd0_data)
        ifd0_entries.append((_TAG_EXIF_IFD, _LONG, 1, struct.pack("<I", exif_offset)))
        ifd0, ifd0_data = _ifd(ifd0_entries, 8)
        exif_ifd, exif_data = _ifd(exif_entries, exif_offset)
        tiff = tiff_header + ifd0 + ifd0_data + exif_ifd + exif_data
    else:
        ifd0, ifd0_data = _ifd(ifd0_entries, 8)
        tiff = tiff_header + ifd0 + ifd0_data

    app1_body = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(app1_body) + 2) + app1_body
    # SOI + APP1 + (fake) payload + EOI
    return b"\xff\xd8" + app1 + payload + b"\xff\xd9"


MakeFile = Callable[..., Path]


def mtime_of(path: str | os.PathLike[str]) -> float:
    """Return the modification time of ``path`` (used to stub creation times)."""
    return Path(path).stat().st_mtime


@pytest.fixture
def make_file() -> MakeFile:
    """Factory creating files, optionally with EXIF data and a given mtime."""

    def _make(
        path: Path,
        *,
        exif_date: str | None = None,
        mtime: datetime | None = None,
        content: bytes | None = None,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            content = (
                build_exif_jpeg(date_time_original=exif_date, payload=path.name.encode())
                if exif_date is not None
                else path.name.encode()
            )
        path.write_bytes(content)
        if mtime is not None:
            ts = mtime.timestamp()
            os.utime(path, (ts, ts))
        return path

    return _make


@pytest.fixture
def src_dir(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    return d


@pytest.fixture
def dest_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dest"
    d.mkdir()
    return d
