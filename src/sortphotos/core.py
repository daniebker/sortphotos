"""Core logic for sorting files into date-based directory hierarchies.

Originally created on 3/2/2013.
Copyright (c) S. Andrew Ning. All rights reserved.
"""

from __future__ import annotations

import filecmp
import fnmatch
import logging
import os
import shutil
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

import exifread

logger = logging.getLogger(__name__)

DEFAULT_SORT_FORMAT = "%Y/%m-%b"
DEFAULT_EXTENSIONS: tuple[str, ...] = (
    "jpg",
    "jpeg",
    "tiff",
    "arw",
    "avi",
    "mov",
    "mp4",
    "mts",
    "dng",
)

# EXIF tags checked for a date, in order of preference.
EXIF_DATE_TAGS: tuple[str, ...] = (
    "EXIF DateTimeOriginal",
    "EXIF DateTimeDigitized",
    "Image DateTime",
)

RENAME_DATE_FORMAT = "%b %d %H-%M-%S %Y"


# -------- convenience functions -------------


def parse_date_exif(date_string: object) -> datetime:
    """Parse an EXIF date string of the form ``YYYY:MM:DD HH:MM:SS``.

    If no time component is present the time defaults to noon.
    """
    elements = str(date_string).strip().split()

    year, month, day = (int(part) for part in elements[0].split(":"))

    if len(elements) > 1:
        hour, minute, second = (int(part) for part in elements[1].split(":"))
    else:
        hour, minute, second = 12, 0, 0  # default to noon if no time data provided

    return datetime(year, month, day, hour, minute, second)


def get_creation_time(path: str | os.PathLike[str]) -> float:
    """Return the best available creation timestamp for ``path``.

    Uses the file's birth time where the platform exposes it (macOS, BSD and
    Windows on recent Python versions), the creation time on Windows, and the
    last modification time otherwise (e.g. Linux).
    """
    stat_result = Path(path).stat()
    birthtime = getattr(stat_result, "st_birthtime", None)
    if birthtime is not None:
        return float(birthtime)
    if os.name == "nt":
        return stat_result.st_ctime
    return stat_result.st_mtime


def parse_date_tstamp(path: str | os.PathLike[str]) -> datetime:
    """Extract date info from the file's timestamp."""
    return datetime.fromtimestamp(get_creation_time(path))


def check_for_early_morning_photos(date: datetime, day_begins: int) -> datetime:
    """Shift early-morning dates so they are grouped with the previous day."""
    if date.hour < day_begins:
        # push it to the day before for classification purposes
        date = date - timedelta(hours=date.hour + 1)
    return date


def valid_date(date: object) -> bool:
    """Check the date is not zero time and matches the EXIF format ``YYYY:MM:DD HH:MM:SS``."""
    elements = str(date).strip().split()

    if not elements:
        return False

    date_entries = elements[0].split(":")
    is_valid_date = len(date_entries) == 3 and date_entries[0] > "0000"
    is_valid_time = True

    if len(elements) > 1:
        is_valid_time = len(elements[1].split(":")) == 3

    return is_valid_date and is_valid_time


def read_exif_date(path: str | os.PathLike[str]) -> datetime | None:
    """Return the date stored in the file's EXIF data, or ``None`` if unavailable."""
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:  # exifread can raise a variety of errors on odd files
        logger.debug("Could not read EXIF data from %s", path, exc_info=True)
        return None

    for tag in EXIF_DATE_TAGS:
        if tag in tags and valid_date(tags[tag]):
            try:
                return parse_date_exif(tags[tag])
            except ValueError:
                logger.debug("Invalid EXIF date %r in %s", str(tags[tag]), path)
    return None


def get_date(path: str | os.PathLike[str], ignore_exif: bool = False) -> datetime:
    """Return the date for ``path``, preferring EXIF data over the file timestamp."""
    if not ignore_exif:
        exif_date = read_exif_date(path)
        if exif_date is not None:
            return exif_date
    return parse_date_tstamp(path)


def rename_file(dest_file: str | os.PathLike[str], title_pattern: str, date: datetime) -> Path:
    """Build a new destination path whose name is ``title_pattern`` filled in with ``date``.

    ``title_pattern`` is a ``%``-style format string receiving a single string
    argument, e.g. ``"Holiday %s"``.  The original file extension is kept.
    """
    dest = Path(dest_file)
    created_str = date.strftime(RENAME_DATE_FORMAT)
    return dest.with_name(title_pattern % created_str + dest.suffix)


def find_files(src_dir: str | os.PathLike[str], extensions: Iterable[str]) -> list[Path]:
    """Recursively find files in ``src_dir`` whose extension matches (case-insensitively)."""
    patterns = ["*." + ext.lower() for ext in extensions]
    matched: list[Path] = []
    for root, _dirnames, filenames in os.walk(src_dir):
        for filename in sorted(filenames):
            lowered = filename.lower()
            if any(fnmatch.fnmatchcase(lowered, pattern) for pattern in patterns):
                matched.append(Path(root) / filename)
    return matched


def resolve_destination(
    src_file: Path, dest_file: Path, remove_duplicates: bool
) -> tuple[Path, bool]:
    """Find a non-colliding destination path.

    Returns the destination path and whether an identical file already exists
    there (only checked when ``remove_duplicates`` is true).
    """
    stem, suffix = dest_file.stem, dest_file.suffix
    candidate = dest_file
    append = 1
    while candidate.is_file():
        if remove_duplicates and filecmp.cmp(src_file, candidate, shallow=False):
            return candidate, True
        candidate = dest_file.with_name(f"{stem}_{append}{suffix}")
        append += 1
    return candidate, False


def _print_progress(idx: int, total: int, stream: TextIO) -> None:
    numdots = int(20.0 * idx / total)
    stream.write(f"\r[{'=' * numdots:<20}] {idx} of {total} ")
    stream.flush()


# --------- main entry point -----------------


def sort_photos(
    src_dir: str | os.PathLike[str],
    dest_dir: str | os.PathLike[str],
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    sort_format: str = DEFAULT_SORT_FORMAT,
    move_files: bool = False,
    remove_duplicates: bool = True,
    ignore_exif: bool = False,
    day_begins: int = 0,
    rename: str | None = None,
    progress: TextIO | None = sys.stdout,
) -> None:
    """Copy or move files from ``src_dir`` into a date-based hierarchy in ``dest_dir``.

    Args:
        src_dir: Directory searched recursively for files.
        dest_dir: Top-level destination directory.
        extensions: File extensions to include (case-insensitive, ``*`` for all).
        sort_format: ``strftime`` format; ``/`` separates sub-directories.
        move_files: Move files instead of copying them.
        remove_duplicates: Skip files identical to an existing destination file.
        ignore_exif: Always use the file timestamp, never EXIF data.
        day_begins: Hour (0-23) at which a new day begins.
        rename: Optional ``%``-pattern used to rename files with their date.
        progress: Stream for the progress bar, or ``None`` to disable it.
    """
    src_path = Path(src_dir)
    dest_path = Path(dest_dir)

    if not src_path.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {src_path}")
    if not dest_path.is_dir():
        raise FileNotFoundError(f"Destination directory does not exist: {dest_path}")
    if not 0 <= day_begins <= 23:
        raise ValueError("day_begins must be between 0 and 23")

    matched_files = find_files(src_path, extensions)
    num_files = len(matched_files)

    for idx, src_file in enumerate(matched_files, start=1):
        if progress is not None:
            _print_progress(idx, num_files, progress)

        date = get_date(src_file, ignore_exif=ignore_exif)

        # early morning photos can be grouped with previous day (depending on user setting)
        sort_date = check_for_early_morning_photos(date, day_begins)

        # create folder structure
        target_dir = dest_path.joinpath(*sort_date.strftime(sort_format).split("/"))
        target_dir.mkdir(parents=True, exist_ok=True)

        dest_file = target_dir / src_file.name
        if rename:
            dest_file = rename_file(dest_file, rename, date)

        dest_file, is_identical = resolve_destination(src_file, dest_file, remove_duplicates)

        if move_files:
            if is_identical:
                # identical copy already present; just remove the source
                src_file.unlink()
            else:
                shutil.move(src_file, dest_file)
        elif not is_identical:
            shutil.copy2(src_file, dest_file)

    if progress is not None and num_files:
        progress.write("\n")
        progress.flush()
