"""A sufficient, exact positivity test for the straight-edge Tet10 profile.

The Jacobian is affine in barycentric coordinates. A strict matrix-norm
perturbation bound relative to the corner tetrahedron certifies positive
determinant throughout the reference element; failure is not proof of inversion.
Parent shape quality and collisions between different elements remain separate.
"""
from fractions import Fraction
import math


GMSH_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
NATIVE_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def native_tet10_nodes(node_ids):
    """Gmsh slots 9/10 and Radioss slots 9/10 have opposite edge roles."""
    if len(node_ids) != 10 or len(set(node_ids)) != 10:
        raise ValueError("Tet10 requires ten distinct node references")
    return tuple(node_ids[:8]) + (node_ids[9], node_ids[8])


def _det(a):
    return (a[0][0] * (a[1][1]*a[2][2] - a[1][2]*a[2][1])
            - a[0][1] * (a[1][0]*a[2][2] - a[1][2]*a[2][0])
            + a[0][2] * (a[1][0]*a[2][1] - a[1][1]*a[2][0]))


def _adjugate(a):
    return tuple(tuple((-1 if (row+column) % 2 else 1) *
                       _minor(a, column, row) for column in range(3)) for row in range(3))


def _minor(a, row, column):
    remaining = [[a[r][c] for c in range(3) if c != column] for r in range(3) if r != row]
    return remaining[0][0]*remaining[1][1] - remaining[0][1]*remaining[1][0]


def _approximate(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except OverflowError:
        return None


def certify_straight_tet10(points, *, ordering="gmsh", ulp_budget=8):
    """Use the actual ten finite float coordinates, including serialized values.

    Midpoint proximity is a source-profile gate, not a physical distance
    tolerance. The exact certificate uses every residual, even when its reported
    floating-point magnitude underflows. No determinant sampling is involved.
    """
    if ordering not in ("gmsh", "radioss") or type(ulp_budget) is not int or not 0 <= ulp_budget <= 32:
        raise ValueError("Unknown Tet10 ordering or ULP budget")
    try:
        if len(points) != 10 or any(len(point) != 3 for point in points):
            raise ValueError()
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for point in points for value in point):
            raise ValueError()
        p = tuple(tuple(Fraction.from_float(float(value)) for value in point) for point in points)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Tet10 requires ten finite three-dimensional coordinates") from None
    a = tuple(tuple(p[column+1][row] - p[0][row] for column in range(3)) for row in range(3))
    determinant = _det(a)
    edges = GMSH_EDGES if ordering == "gmsh" else NATIVE_EDGES
    residuals = {}
    within_budget = True
    maximum_residual = Fraction(0)
    for midpoint, (i, j) in zip(p[4:], edges):
        average = tuple((x+y)/2 for x, y in zip(p[i], p[j]))
        residual = tuple(x-y for x, y in zip(midpoint, average))
        residuals[frozenset((i, j))] = residual
        maximum_residual = max(maximum_residual, *(abs(value) for value in residual))
        within_budget &= all(abs(value) <= Fraction.from_float(math.ulp(float(expected))) * ulp_budget
                             for value, expected in zip(residual, average))
    report = {"certified_positive": False, "reason": "parent_not_positive",
              "method": "exact_corner_matrix_perturbation_norm",
              "relative_perturbation_bound": None, "midpoint_within_ulp_budget": within_budget,
              "maximum_midpoint_residual": _approximate(maximum_residual), "ulp_budget": ulp_budget}
    if determinant <= 0:
        return report
    gradients = ((-1, -1, -1), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    adjugate = _adjugate(a)
    maximum_norm_numerator = Fraction(0)
    for k in range(4):
        perturbation = tuple(tuple(4 * sum(residuals[frozenset((k, j))][row] * gradients[j][column]
                                               for j in range(4) if j != k)
                                   for column in range(3)) for row in range(3))
        product = tuple(tuple(sum(adjugate[row][j] * perturbation[j][column] for j in range(3))
                              for column in range(3)) for row in range(3))
        maximum_norm_numerator = max(maximum_norm_numerator,
                                     *(sum(abs(value) for value in row) for row in product))
    bound = maximum_norm_numerator / determinant
    report["relative_perturbation_bound"] = _approximate(bound)
    report["certified_positive"] = maximum_norm_numerator < determinant
    report["reason"] = None if report["certified_positive"] else "positivity_not_certified"
    return report
