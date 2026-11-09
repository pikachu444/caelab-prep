"""The GI3 negative cusp's 32 ULP difference is below the GI4 mm³ tolerance."""
import pytest

from scripts.evaluation.geometry_volume import compare_volumes


def data(volume, unit="mm"):
    return {"length_unit": unit, "volumes": [{"uuid": "volume", "volume": volume}]}


def test_gi3_negative_cusp_uses_absolute_volume_tolerance():
    result = compare_volumes(data(.6438055098076205), data(.643805509807617))
    assert result["passed"]
    assert result["absolute_tolerance_mm3"] == 1e-9
    assert result["differences_mm3"]["volume"] == -3.552713678800501e-15


@pytest.mark.parametrize("difference,passed", [(0., True), (1e-9, True), (1.01e-9, False), (-2e-9, False)])
def test_tolerance_boundary(difference, passed):
    assert compare_volumes(data(0.), data(difference))["passed"] is passed


def test_incompatible_units_and_volume_identities_are_not_comparable():
    with pytest.raises(ValueError, match="mm"):
        compare_volumes(data(1., "cm"), data(1.))
    other = data(1.)
    other["volumes"][0]["uuid"] = "other"
    with pytest.raises(ValueError, match="identities"):
        compare_volumes(data(1.), other)
