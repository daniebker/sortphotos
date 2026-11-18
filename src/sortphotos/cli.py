"""Command line interface for sortphotos."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from sortphotos import __version__
from sortphotos.core import DEFAULT_EXTENSIONS, DEFAULT_SORT_FORMAT, sort_photos


def _hour(value: str) -> int:
    hour = int(value)
    if not 0 <= hour <= 23:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 23")
    return hour


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the ``sortphotos`` command."""
    parser = argparse.ArgumentParser(
        prog="sortphotos",
        formatter_class=argparse.RawTextHelpFormatter,
        description=(
            "Sort files (primarily photos) into folders by date\n"
            "using EXIF data if possible and file creation date if not"
        ),
    )
    parser.add_argument("src_dir", help="source directory (searched recursively)")
    parser.add_argument("dest_dir", help="destination directory")
    parser.add_argument("-m", "--move", action="store_true", help="move files instead of copy")
    parser.add_argument(
        "-s",
        "--sort",
        default=DEFAULT_SORT_FORMAT,
        help=(
            "choose destination folder structure using datetime format\n"
            "https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior.\n"
            "Use forward slashes / to indicate subdirectory(ies)\n"
            "(independent of your OS convention).\n"
            "The default is '%%Y/%%m-%%b', which separates by year then month\n"
            "with both the month number and name (e.g., 2012/02-Feb)."
        ),
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="If file is a duplicate keep it anyway (after renaming).",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_EXTENSIONS),
        help="file types to sort",
    )
    parser.add_argument(
        "--ignore-exif",
        action="store_true",
        help="always use file time stamp even if EXIF data exists",
    )
    parser.add_argument(
        "--day-begins",
        type=_hour,
        default=0,
        help=(
            "hour of day that new day begins (0-23),\n"
            "defaults to 0 which corresponds to midnight. "
            "Useful for grouping pictures with previous day."
        ),
    )
    parser.add_argument(
        "--rename",
        help="rename files using this pattern, where %%s is replaced by the date\n"
        "(e.g. 'Holiday %%s' -> 'Holiday Jun 01 12-30-00 2010.jpg')",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # ExifRead warns about every non-image file (e.g. videos); that's expected here.
    logging.getLogger("exifread").setLevel(logging.ERROR)

    try:
        sort_photos(
            args.src_dir,
            args.dest_dir,
            extensions=args.extensions,
            sort_format=args.sort,
            move_files=args.move,
            remove_duplicates=not args.keep_duplicates,
            ignore_exif=args.ignore_exif,
            day_begins=args.day_begins,
            rename=args.rename,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"sortphotos: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
