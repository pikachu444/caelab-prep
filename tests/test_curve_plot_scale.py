"""Engineering axis labels must describe finite plotted values accurately."""

import math

import pytest

pytest.importorskip("PySide6")

from caelab_prep.ui.widgets.curve import _Axis


@pytest.mark.parametrize("bounds", [
    (-1e308, 1e308), (1e9, 1e9 + 1), (1e-300, 2e-300), (250, 450),
    (1e16, 1e16 + 2), (1e9, 1e9 + 1e-6),
    (.1, math.nextafter(.1, math.inf)),
])
def test_axis_keeps_extreme_or_offset_values_ordered_and_ticks_unambiguous(bounds):
    low, high = bounds
    axis = _Axis(bounds)
    assert axis.fraction(low) == pytest.approx(0)
    assert axis.fraction(high) == pytest.approx(1)
    ticks = axis.ticks(4)
    positions, labels = zip(*ticks)
    assert all(math.isfinite(value) and 0 <= value <= 1.000001 for value in positions)
    assert all(a < b for a, b in zip(positions, positions[1:]))
    assert len(set(labels)) == len(labels)
    values = [float(label) for label in labels]
    assert all(low <= value <= high for value in values)
    assert len(values) >= 2
    assert all(a < b for a, b in zip(values, values[1:]))
    assert positions == pytest.approx(tuple(axis.fraction(value) for value in values))


def test_constant_curve_axis_centers_the_value_in_a_finite_range():
    axis = _Axis((0, 0))
    assert axis.fraction(0) == pytest.approx(.5)
    assert len(axis.ticks(4)) >= 2
