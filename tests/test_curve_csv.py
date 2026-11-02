"""Actual curve CSV files, bounded parsing and atomic publication failures."""

import math

import pytest

from caelab_prep.application import curve_csv
from caelab_prep.application.curve_csv import read_curve_csv, write_curve_csv


@pytest.mark.parametrize("points", [
    ((0.0, 0.0), (0.125, -73.2), (2.5, 102.125)),
    ((-1e-210, 2.2250738585072014e-308), (0.0, -0.0), (1e110, 1.7976931348623157e308)),
])
def test_csv_file_roundtrip_preserves_two_distinct_curves(tmp_path, points):
    target = tmp_path / "곡선 data.csv"
    assert write_curve_csv(target, points) == target
    assert target.read_text().startswith("x,y\n")
    reopened = read_curve_csv(target)
    assert reopened == points
    for actual, expected in zip(reopened, points):
        for value, original in zip(actual, expected):
            assert math.copysign(1, value) == math.copysign(1, original)
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("payload", [
    b"\xef\xbb\xbfx,y\r\n0,0\r\n.5,1.25e2\r\n",
    b'"0", "0"\n.5,1.25e2\n'.replace(b' ', b''),
    b"0,0\n +.5 , 125. \n",
])
def test_csv_bom_header_crlf_and_headerless_numbers(tmp_path, payload):
    source = tmp_path / "input.csv"
    source.write_bytes(payload)
    assert read_curve_csv(source) == ((0.0, 0.0), (0.5, 125.0))


@pytest.mark.parametrize("payload, message", [
    (b"", "at least one"),
    (b"x,y\n", "at least one"),
    (b"\n", "two columns"),
    (b"0,1\n\n2,3\n", "two columns"),
    (b"0,1,2\n", "two columns"),
    (b"0\n", "two columns"),
    (b"0,\n", "finite decimal"),
    (b"X,Y\n0,1\n", "finite decimal"),
    (b"# units: s,N\n0,1\n", "finite decimal"),
    (b"0,nan\n", "finite decimal"),
    (b"0,inf\n", "finite decimal"),
    (b"0,1e400\n", "finite decimal"),
    (b"0,1_000\n", "finite decimal"),
    (b"0,1D2\n", "finite decimal"),
    (b'0,"1\n', "Malformed"),
    (b'0,"1"2\n', "Malformed"),
    (b"0,\xff\n", "UTF-8"),
])
def test_invalid_complete_file_never_returns_partial_points(tmp_path, payload, message):
    source = tmp_path / "bad.csv"
    source.write_bytes(payload)
    with pytest.raises(ValueError, match=message):
        read_curve_csv(source)
    assert source.read_bytes() == payload


def test_reader_and_writer_enforce_byte_and_row_limits(tmp_path, monkeypatch):
    source = tmp_path / "limit.csv"
    source.write_bytes(b"0,1\n2,3\n")
    monkeypatch.setattr(curve_csv, "MAX_CSV_BYTES", 7)
    with pytest.raises(ValueError, match="byte limit"):
        read_curve_csv(source)
    with pytest.raises(ValueError, match="byte limit"):
        write_curve_csv(tmp_path / "output.csv", ((0, 1), (2, 3)))
    monkeypatch.setattr(curve_csv, "MAX_CSV_BYTES", 1024)
    monkeypatch.setattr(curve_csv, "MAX_CSV_POINTS", 1)
    with pytest.raises(ValueError, match="point limit"):
        read_curve_csv(source)
    with pytest.raises(ValueError, match="point limit"):
        write_curve_csv(tmp_path / "output.csv", ((0, 1), (2, 3)))
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("points", [(), ((0,),), ((0, 1, 2),), ((False, 1),),
                                        ((0, float("nan")),), ((0, float("inf")),), ("12",)])
def test_invalid_export_does_not_touch_existing_file_or_make_temporary(tmp_path, points):
    target = tmp_path / "curve.csv"
    target.write_bytes(b"existing content")
    with pytest.raises(ValueError):
        write_curve_csv(target, points, overwrite=True)
    assert target.read_bytes() == b"existing content"
    assert list(tmp_path.iterdir()) == [target]


def test_export_requires_explicit_overwrite_and_then_replaces_atomically(tmp_path):
    target = tmp_path / "curve.csv"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        write_curve_csv(target, ((0, 2),))
    assert target.read_bytes() == b"original"
    write_curve_csv(target, ((0, 2),), overwrite=True)
    assert read_curve_csv(target) == ((0.0, 2.0),)
    assert list(tmp_path.iterdir()) == [target]


def test_publish_failure_keeps_original_and_removes_temporary(tmp_path, monkeypatch):
    target = tmp_path / "curve.csv"
    target.write_bytes(b"original")
    def fail_replace(source, destination):
        assert read_curve_csv(source) == ((0.0, 2.0),)
        assert target.read_bytes() == b"original"
        raise OSError("publication failed")
    monkeypatch.setattr(curve_csv.os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication failed"):
        write_curve_csv(target, ((0, 2),), overwrite=True)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_racing_new_file_is_not_overwritten_and_temporary_is_removed(tmp_path, monkeypatch):
    target = tmp_path / "curve.csv"
    link = curve_csv.os.link
    def race(source, destination):
        target.write_bytes(b"created after initial check")
        link(source, destination)
    monkeypatch.setattr(curve_csv.os, "link", race)
    with pytest.raises(FileExistsError):
        write_curve_csv(target, ((0, 2),))
    assert target.read_bytes() == b"created after initial check"
    assert list(tmp_path.iterdir()) == [target]


def test_flush_failure_never_publishes_and_removes_temporary(tmp_path, monkeypatch):
    def fail_fsync(descriptor):
        raise OSError("disk flush failed")
    monkeypatch.setattr(curve_csv.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="disk flush failed"):
        write_curve_csv(tmp_path / "curve.csv", ((0, 2),))
    assert list(tmp_path.iterdir()) == []
