"""Unit tests for the helper functions in :mod:`sortphotos.core`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from sortphotos import core
from tests.conftest import MakeFile, build_exif_jpeg, mtime_of


class TestParseDateExif:
    def test_full_datetime(self) -> None:
        assert core.parse_date_exif("2010:06:01 13:14:15") == datetime(2010, 6, 1, 13, 14, 15)

    def test_date_only_defaults_to_noon(self) -> None:
        assert core.parse_date_exif("2010:06:01") == datetime(2010, 6, 1, 12, 0, 0)

    def test_strips_whitespace_and_accepts_objects(self) -> None:
        class Tag:
            def __str__(self) -> str:
                return "  2001:02:03 04:05:06  "

        assert core.parse_date_exif(Tag()) == datetime(2001, 2, 3, 4, 5, 6)

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError):
            core.parse_date_exif("2010:13:01 00:00:00")


class TestValidDate:
    @pytest.mark.parametrize(
        "value",
        ["2010:06:01 13:14:15", "2010:06:01", "1999:12:31 23:59:59"],
    )
    def test_valid(self, value: str) -> None:
        assert core.valid_date(value)

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "0000:00:00 00:00:00",
            "2010-06-01 13:14:15",
            "2010:06:01 13:14",
            "2010:06",
        ],
    )
    def test_invalid(self, value: str) -> None:
        assert not core.valid_date(value)


class TestEarlyMorning:
    def test_before_day_begins_moves_to_previous_day(self) -> None:
        result = core.check_for_early_morning_photos(datetime(2010, 6, 2, 3, 30), 4)
        assert result.date() == datetime(2010, 6, 1).date()
        assert result.hour == 23

    def test_after_day_begins_unchanged(self) -> None:
        date = datetime(2010, 6, 2, 4, 0)
        assert core.check_for_early_morning_photos(date, 4) == date

    def test_midnight_default_never_shifts(self) -> None:
        date = datetime(2010, 6, 2, 0, 0)
        assert core.check_for_early_morning_photos(date, 0) == date

    def test_crosses_month_boundary(self) -> None:
        result = core.check_for_early_morning_photos(datetime(2010, 7, 1, 1, 0), 3)
        assert result.date() == datetime(2010, 6, 30).date()


class TestTimestamps:
    def test_parse_date_tstamp_uses_creation_time(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("x")
        with mock.patch.object(core, "get_creation_time", return_value=0.0):
            assert core.parse_date_tstamp(f) == datetime.fromtimestamp(0)

    def test_get_creation_time_prefers_birthtime(self, tmp_path: Path) -> None:
        fake = mock.Mock(st_birthtime=123.0, st_ctime=456.0, st_mtime=789.0)
        with mock.patch.object(core.Path, "stat", return_value=fake):
            assert core.get_creation_time(tmp_path) == 123.0

    def test_get_creation_time_falls_back_to_mtime(self, tmp_path: Path) -> None:
        fake = mock.Mock(spec=["st_ctime", "st_mtime"], st_ctime=456.0, st_mtime=789.0)
        with (
            mock.patch.object(core.Path, "stat", return_value=fake),
            mock.patch.object(core.os, "name", "posix"),
        ):
            assert core.get_creation_time(tmp_path) == 789.0

    def test_get_creation_time_uses_ctime_on_windows(self, tmp_path: Path) -> None:
        fake = mock.Mock(spec=["st_ctime", "st_mtime"], st_ctime=456.0, st_mtime=789.0)
        with (
            mock.patch.object(core.Path, "stat", return_value=fake),
            mock.patch.object(core.os, "name", "nt"),
        ):
            assert core.get_creation_time(tmp_path) == 456.0

    def test_get_creation_time_real_file(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("x")
        assert core.get_creation_time(f) == pytest.approx(f.stat().st_mtime, abs=86400)


class TestGetDate:
    def test_reads_date_time_original(self, tmp_path: Path, make_file: MakeFile) -> None:
        f = make_file(tmp_path / "a.jpg", exif_date="2010:06:01 13:14:15")
        assert core.get_date(f) == datetime(2010, 6, 1, 13, 14, 15)

    def test_tag_priority(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jpg"
        f.write_bytes(
            build_exif_jpeg(
                date_time_original="2001:01:01 01:01:01",
                date_time_digitized="2002:02:02 02:02:02",
                image_date_time="2003:03:03 03:03:03",
            )
        )
        assert core.get_date(f) == datetime(2001, 1, 1, 1, 1, 1)

    def test_falls_back_to_digitized(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jpg"
        f.write_bytes(
            build_exif_jpeg(
                date_time_original="0000:00:00 00:00:00",
                date_time_digitized="2002:02:02 02:02:02",
                image_date_time="2003:03:03 03:03:03",
            )
        )
        assert core.get_date(f) == datetime(2002, 2, 2, 2, 2, 2)

    def test_falls_back_to_image_datetime(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jpg"
        f.write_bytes(build_exif_jpeg(image_date_time="2003:03:03 03:03:03"))
        assert core.get_date(f) == datetime(2003, 3, 3, 3, 3, 3)

    def test_falls_back_to_timestamp_without_exif(
        self, tmp_path: Path, make_file: MakeFile
    ) -> None:
        mtime = datetime(2015, 5, 5, 10, 0, 0)
        f = make_file(tmp_path / "a.mov", mtime=mtime)
        with mock.patch.object(core, "get_creation_time", side_effect=mtime_of):
            assert core.get_date(f) == mtime

    def test_ignore_exif_uses_timestamp(self, tmp_path: Path, make_file: MakeFile) -> None:
        mtime = datetime(2015, 5, 5, 10, 0, 0)
        f = make_file(tmp_path / "a.jpg", exif_date="2010:06:01 13:14:15", mtime=mtime)
        with mock.patch.object(core, "get_creation_time", side_effect=mtime_of):
            assert core.get_date(f, ignore_exif=True) == mtime

    def test_unparseable_exif_date_falls_back(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jpg"
        f.write_bytes(build_exif_jpeg(date_time_original="2010:13:45 13:14:15"))
        assert core.read_exif_date(f) is None

    def test_exifread_errors_are_tolerated(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jpg"
        f.write_bytes(b"not an image")
        with mock.patch.object(core.exifread, "process_file", side_effect=RuntimeError("boom")):
            assert core.read_exif_date(f) is None


class TestRenameFile:
    def test_uses_pattern_and_keeps_extension(self, tmp_path: Path) -> None:
        result = core.rename_file(
            tmp_path / "2010" / "IMG_001.JPG", "Holiday %s", datetime(2010, 6, 1, 13, 14, 15)
        )
        assert result == tmp_path / "2010" / "Holiday Jun 01 13-14-15 2010.JPG"


class TestFindFiles:
    def test_matches_extensions_case_insensitively_and_recursively(
        self, src_dir: Path, make_file: MakeFile
    ) -> None:
        for name in ["a.jpg", "b.JPG", "c.JpG", "sub/d.mov", "e.txt", "sub/deeper/f.Mov"]:
            make_file(src_dir / name)

        found = {
            p.relative_to(src_dir).as_posix() for p in core.find_files(src_dir, ["jpg", "mov"])
        }
        assert found == {"a.jpg", "b.JPG", "c.JpG", "sub/d.mov", "sub/deeper/f.Mov"}

    def test_wildcard_matches_everything_once(self, src_dir: Path, make_file: MakeFile) -> None:
        for name in ["a.jpg", "b.txt", ".hidden.cfg"]:
            make_file(src_dir / name)
        found = core.find_files(src_dir, ["*"])
        assert sorted(p.name for p in found) == [".hidden.cfg", "a.jpg", "b.txt"]

    def test_empty_directory(self, src_dir: Path) -> None:
        assert core.find_files(src_dir, ["jpg"]) == []


class TestResolveDestination:
    def test_free_name_is_kept(self, tmp_path: Path, make_file: MakeFile) -> None:
        src = make_file(tmp_path / "s" / "a.jpg")
        dest = tmp_path / "d" / "a.jpg"
        assert core.resolve_destination(src, dest, True) == (dest, False)

    def test_identical_file_detected(self, tmp_path: Path, make_file: MakeFile) -> None:
        src = make_file(tmp_path / "s" / "a.jpg", content=b"same")
        dest = make_file(tmp_path / "d" / "a.jpg", content=b"same")
        assert core.resolve_destination(src, dest, True) == (dest, True)

    def test_identical_file_kept_when_not_removing_duplicates(
        self, tmp_path: Path, make_file: MakeFile
    ) -> None:
        src = make_file(tmp_path / "s" / "a.jpg", content=b"same")
        dest = make_file(tmp_path / "d" / "a.jpg", content=b"same")
        assert core.resolve_destination(src, dest, False) == (tmp_path / "d" / "a_1.jpg", False)

    def test_collisions_get_incrementing_suffix(self, tmp_path: Path, make_file: MakeFile) -> None:
        src = make_file(tmp_path / "s" / "a.jpg", content=b"new")
        make_file(tmp_path / "d" / "a.jpg", content=b"old1")
        make_file(tmp_path / "d" / "a_1.jpg", content=b"old2")
        result = core.resolve_destination(src, tmp_path / "d" / "a.jpg", True)
        assert result == (tmp_path / "d" / "a_2.jpg", False)

    def test_identical_file_found_after_suffix(self, tmp_path: Path, make_file: MakeFile) -> None:
        src = make_file(tmp_path / "s" / "a.jpg", content=b"new")
        make_file(tmp_path / "d" / "a.jpg", content=b"old")
        make_file(tmp_path / "d" / "a_1.jpg", content=b"new")
        result = core.resolve_destination(src, tmp_path / "d" / "a.jpg", True)
        assert result == (tmp_path / "d" / "a_1.jpg", True)
