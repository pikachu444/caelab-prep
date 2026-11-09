"""Compare STEP/XAO inspection volumes in mm³ without requiring bit identity.

Usage: python scripts/evaluation/geometry_volume.py step-metadata.json xao-metadata.json
This evaluates saved observations; it does not execute the CAD SDK.
"""
import argparse
import json
import math
from pathlib import Path


VOLUME_ABSOLUTE_TOLERANCE_MM3 = 1e-9


def compare_volumes(step, xao):
    if step.get("length_unit") != "mm" or xao.get("length_unit") != "mm":
        raise ValueError("Volume comparison requires mm inspection coordinates.")
    before = {row["uuid"]: row["volume"] for row in step["volumes"]}
    after = {row["uuid"]: row["volume"] for row in xao["volumes"]}
    if not before or before.keys() != after.keys():
        raise ValueError("STEP and XAO must contain the same volume identities.")
    differences = {key: after[key] - value for key, value in before.items()}
    return {"passed": all(math.isfinite(before[key]) and math.isfinite(after[key])
                          and abs(delta) <= VOLUME_ABSOLUTE_TOLERANCE_MM3
                          for key, delta in differences.items()),
            "absolute_tolerance_mm3": VOLUME_ABSOLUTE_TOLERANCE_MM3,
            "differences_mm3": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step_metadata", type=Path)
    parser.add_argument("xao_metadata", type=Path)
    args = parser.parse_args()
    result = compare_volumes(*(json.loads(path.read_text(encoding="utf-8"))
                               for path in (args.step_metadata, args.xao_metadata)))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
