"""Tests for the command line interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from sortphotos import DEFAULT_EXTENSIONS, DEFAULT_SORT_FORMAT, cli
from tests.conftest import MakeFile


def test_defaults_are_passed_through(tmp_path: Path) -> None:
    with mock.patch.object(cli, "sort_photos") as sort:
        assert cli.main(["src", "dest"]) == 0
    sort.assert_called_once_with(
        "src",
        "dest",
        extensions=list(DEFAULT_EXTENSIONS),
        sort_format=DEFAULT_SORT_FORMAT,
        move_files=False,
        remove_duplicates=True,
        ignore_exif=False,
        day_begins=0,
        rename=None,
    )


def test_all_options(tmp_path: Path) -> None:
    argv = [
        "-m",
        "-s",
        "%Y",
        "--keep-duplicates",
        "--extensions",
        "gif",
        "avi",
        "--ignore-exif",
        "--day-begins",
        "4",
        "--rename",
        "Pic %s",
        "src",
        "dest",
    ]
    with mock.patch.object(cli, "sort_photos") as sort:
        assert cli.main(argv) == 0
    sort.assert_called_once_with(
        "src",
        "dest",
        extensions=["gif", "avi"],
        sort_format="%Y",
        move_files=True,
        remove_duplicates=False,
        ignore_exif=True,
        day_begins=4,
        rename="Pic %s",
    )


@pytest.mark.parametrize("value", ["24", "-1", "noon"])
def test_invalid_day_begins_rejected(value: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--day-begins", value, "src", "dest"])
    assert excinfo.value.code == 2
    assert "--day-begins" in capsys.readouterr().err


def test_missing_directory_reports_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([str(tmp_path / "nope"), str(tmp_path)]) == 1
    assert "Source directory does not exist" in capsys.readouterr().err


def test_end_to_end(tmp_path: Path, make_file: MakeFile) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    dest.mkdir()
    make_file(src / "a.jpg", exif_date="2010:06:01 13:14:15")
    assert cli.main([str(src), str(dest)]) == 0
    assert (dest / "2010" / "06-Jun" / "a.jpg").is_file()


def test_python_dash_m_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sortphotos", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("sortphotos ")
