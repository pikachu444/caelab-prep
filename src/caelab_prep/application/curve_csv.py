"""Bounded two-column curve CSV exchange, independent of Qt and solver codecs.

Files use UTF-8 (an input BOM is accepted), commas, an optional exact ``x,y``
header and finite decimal numbers. Blank rows, comments, metadata and additional
columns are errors. Values are in the host's displayed axes: this format neither
converts units nor stores units, names or references. Work documents own those.
"""

from __future__ import annotations

import csv
import io
import math
import os
from pathlib import Path
import re
import tempfile


MAX_CSV_BYTES = 8 * 1024 * 1024
MAX_CSV_POINTS = 100_000
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def read_curve_csv(path: str | os.PathLike[str]) -> tuple[tuple[float, float], ...]:
    """Read all points or raise without changing any host document or draft."""
    with Path(path).expanduser().open("rb") as stream:
        payload = stream.read(MAX_CSV_BYTES + 1)
    if len(payload) > MAX_CSV_BYTES:
        raise ValueError(f"Curve CSV exceeds the {MAX_CSV_BYTES} byte limit")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Curve CSV must be UTF-8 text") from exc
    rows = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
    points = []
    try:
        for index, row in enumerate(rows):
            if index == 0 and row == ["x", "y"]:
                continue
            if len(row) != 2:
                raise ValueError(f"CSV line {rows.line_num}: expected exactly two columns")
            fields = tuple(value.strip() for value in row)
            if not all(_DECIMAL.fullmatch(value) for value in fields):
                raise ValueError(f"CSV line {rows.line_num}: enter two finite decimal numbers")
            pair = tuple(float(value) for value in fields)
            if not all(math.isfinite(value) for value in pair):
                raise ValueError(f"CSV line {rows.line_num}: enter two finite decimal numbers")
            if len(points) == MAX_CSV_POINTS:
                raise ValueError(f"Curve CSV exceeds the {MAX_CSV_POINTS} point limit")
            points.append(pair)
    except csv.Error as exc:
        raise ValueError(f"Malformed curve CSV near line {rows.line_num}: {exc}") from exc
    if not points:
        raise ValueError("Curve CSV needs at least one point")
    return tuple(points)


def _validated_points(points):
    result = []
    for index, point in enumerate(points, 1):
        if index > MAX_CSV_POINTS:
            raise ValueError(f"Curve CSV exceeds the {MAX_CSV_POINTS} point limit")
        try:
            if isinstance(point, (str, bytes)) or len(point) != 2:
                raise ValueError
            if any(isinstance(value, bool) for value in point):
                raise ValueError
            pair = tuple(float(value) for value in point)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Point {index}: expected two finite numbers") from exc
        if not all(math.isfinite(value) for value in pair):
            raise ValueError(f"Point {index}: expected two finite numbers")
        result.append(pair)
    if not result:
        raise ValueError("Curve CSV needs at least one point")
    return result


def write_curve_csv(path: str | os.PathLike[str], points, *, overwrite: bool = False) -> Path:
    """Atomically export numeric values; replacing a file requires explicit opt-in.

    An exclusive hard link publishes a new file without a check/replace race.
    Confirmed replacement uses ``os.replace``. Both publish a fully written,
    flushed file from the same directory and clean up temporary files on errors.
    The caller owns overwrite confirmation and any unit/metadata explanation.
    """
    target = Path(path).expanduser()
    normalized = _validated_points(points)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("x", "y"))
    writer.writerows(normalized)
    payload = buffer.getvalue().encode("utf-8")
    if len(payload) > MAX_CSV_BYTES:
        raise ValueError(f"Curve CSV exceeds the {MAX_CSV_BYTES} byte limit")
    if not overwrite and os.path.lexists(target):
        raise FileExistsError(f"CSV file already exists: {target}")
    descriptor, temporary = tempfile.mkstemp(prefix=".curve-csv-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
