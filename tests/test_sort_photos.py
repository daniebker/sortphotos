"""Integration-style tests for :func:`sortphotos.sort_photos`."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from sortphotos import core, sort_photos
from tests.conftest import MakeFile, mtime_of


@pytest.fixture(autouse=True)
def deterministic_timestamps() -> Iterator[None]:
    """Use mtime as the creation time so tests can control it via ``os.utime``."""
    with mock.patch.object(core, "get_creation_time", side_effect=mtime_of):
        yield


def run(src: Path, dest: Path, **kwargs: object) -> None:
    kwargs.setdefault("progress", None)
    sort_photos(src, dest, **kwargs)  # type: ignore[arg-type]


def tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_copies_into_default_year_month_structure(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    make_file(src_dir / "nested" / "b.jpg", exif_date="2012:02:03 10:00:00")

    run(src_dir, dest_dir)

    assert tree(dest_dir) == {"2010/06-Jun/a.jpg", "2012/02-Feb/b.jpg"}
    # copy leaves the source untouched
    assert tree(src_dir) == {"a.jpg", "nested/b.jpg"}


def test_move_removes_source(src_dir: Path, dest_dir: Path, make_file: MakeFile) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    run(src_dir, dest_dir, move_files=True)
    assert tree(dest_dir) == {"2010/06-Jun/a.jpg"}
    assert tree(src_dir) == set()


def test_custom_sort_format(src_dir: Path, dest_dir: Path, make_file: MakeFile) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    run(src_dir, dest_dir, sort_format="%Y/%m/%d")
    assert tree(dest_dir) == {"2010/06/01/a.jpg"}


def test_uses_timestamp_for_files_without_exif(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "clip.mov", mtime=datetime(2014, 3, 9, 12, 0))
    run(src_dir, dest_dir)
    assert tree(dest_dir) == {"2014/03-Mar/clip.mov"}


def test_ignore_exif(src_dir: Path, dest_dir: Path, make_file: MakeFile) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15", mtime=datetime(2014, 3, 9, 12))
    run(src_dir, dest_dir, ignore_exif=True)
    assert tree(dest_dir) == {"2014/03-Mar/a.jpg"}


def test_only_matching_extensions_are_sorted(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    make_file(src_dir / "notes.txt", mtime=datetime(2014, 3, 9, 12))
    run(src_dir, dest_dir, extensions=["txt"])
    assert tree(dest_dir) == {"2014/03-Mar/notes.txt"}


def test_day_begins_groups_with_previous_day(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "late.jpg", exif_date="2010:06:02 03:00:00")
    make_file(src_dir / "morning.jpg", exif_date="2010:06:02 05:00:00")
    run(src_dir, dest_dir, sort_format="%Y-%m-%d", day_begins=4)
    assert tree(dest_dir) == {"2010-06-01/late.jpg", "2010-06-02/morning.jpg"}


def test_identical_duplicate_is_skipped_on_copy(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    src = make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    (dest_dir / "2010" / "06-Jun").mkdir(parents=True)
    (dest_dir / "2010" / "06-Jun" / "a.jpg").write_bytes(src.read_bytes())

    run(src_dir, dest_dir)

    assert tree(dest_dir) == {"2010/06-Jun/a.jpg"}
    assert src.exists()


def test_identical_duplicate_on_move_removes_source(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    src = make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    (dest_dir / "2010" / "06-Jun").mkdir(parents=True)
    (dest_dir / "2010" / "06-Jun" / "a.jpg").write_bytes(src.read_bytes())

    run(src_dir, dest_dir, move_files=True)

    assert tree(dest_dir) == {"2010/06-Jun/a.jpg"}
    assert not src.exists()


def test_keep_duplicates(src_dir: Path, dest_dir: Path, make_file: MakeFile) -> None:
    src = make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    (dest_dir / "2010" / "06-Jun").mkdir(parents=True)
    (dest_dir / "2010" / "06-Jun" / "a.jpg").write_bytes(src.read_bytes())

    run(src_dir, dest_dir, remove_duplicates=False)

    assert tree(dest_dir) == {"2010/06-Jun/a.jpg", "2010/06-Jun/a_1.jpg"}


def test_name_collision_with_different_content(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "one" / "a.jpg", exif_date="2010:06:01 13:14:15")
    make_file(src_dir / "two" / "a.jpg", exif_date="2010:06:20 09:00:00")
    run(src_dir, dest_dir)
    assert tree(dest_dir) == {"2010/06-Jun/a.jpg", "2010/06-Jun/a_1.jpg"}


@pytest.mark.parametrize("move", [False, True])
def test_rename(src_dir: Path, dest_dir: Path, make_file: MakeFile, move: bool) -> None:
    make_file(src_dir / "IMG_1.JPG", exif_date="2010:06:01 13:14:15")
    run(src_dir, dest_dir, rename="Trip %s", move_files=move)
    assert tree(dest_dir) == {"2010/06-Jun/Trip Jun 01 13-14-15 2010.JPG"}
    assert (tree(src_dir) == set()) is move


def test_rename_collisions_do_not_overwrite(
    src_dir: Path, dest_dir: Path, make_file: MakeFile
) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    make_file(src_dir / "b.jpg", exif_date="2010:06:01 13:14:15")
    run(src_dir, dest_dir, rename="%s", move_files=True)
    assert tree(dest_dir) == {
        "2010/06-Jun/Jun 01 13-14-15 2010.jpg",
        "2010/06-Jun/Jun 01 13-14-15 2010_1.jpg",
    }


def test_progress_output(src_dir: Path, dest_dir: Path, make_file: MakeFile) -> None:
    make_file(src_dir / "a.jpg", exif_date="2010:06:01 13:14:15")
    make_file(src_dir / "b.jpg", exif_date="2010:06:01 13:14:15")
    out = io.StringIO()
    run(src_dir, dest_dir, progress=out)
    text = out.getvalue()
    assert "1 of 2" in text
    assert "[====================] 2 of 2" in text
    assert text.endswith("\n")


def test_no_files_is_a_noop(src_dir: Path, dest_dir: Path) -> None:
    out = io.StringIO()
    run(src_dir, dest_dir, progress=out)
    assert tree(dest_dir) == set()
    assert out.getvalue() == ""


def test_missing_source_dir(tmp_path: Path, dest_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Source"):
        run(tmp_path / "missing", dest_dir)


def test_missing_dest_dir(tmp_path: Path, src_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Destination"):
        run(src_dir, tmp_path / "missing")


@pytest.mark.parametrize("hour", [-1, 24])
def test_invalid_day_begins(src_dir: Path, dest_dir: Path, hour: int) -> None:
    with pytest.raises(ValueError):
        run(src_dir, dest_dir, day_begins=hour)
