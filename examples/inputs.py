"""Generate original, deterministic RAD editor examples (CC0-1.0).

These fixtures exercise preservation, fields, multi-part shell/solid projection
and INCLUDE. They are editor inputs, not solver verification models.
Run ``python examples/inputs.py --output examples/rad`` to reproduce them.
"""

from pathlib import Path
import argparse


def _ints(*values):
    return "".join(f"{value:10d}" for value in values) + "\n"


def _reals(*values):
    return "".join(f"{value:20g}" for value in values) + "\n"


def _material(identifier, name, modulus):
    return f"/MAT/LAW1/{identifier}\n{name}\n" + _reals(7.8e-9) + _reals(modulus, .3)


def _begin(name):
    return f"# Original CAELab editor fixture; CC0-1.0\n/BEGIN\n{name}\n      2025         0\n" + "                  Mg                  mm                   s\n"


def _conditions(nodes):
    return ("/GRNOD/NODE/1\nFixed end\n" + _ints(*nodes)
            + "/BCS/1\nFixed end\n   111 111         0         1\n"
            + "/INIVEL/TRA/1\nInitial motion\n" + _reals(0, 0, -100).rstrip("\n")
            + _ints(1, 0) + "/FUNCT/1\nPiecewise response\n"
            + _reals(0, 0) + _reals(.1, 50) + _reals(.3, 80)
            + "/PRESERVED/EDITOR/91\nOriginal unsupported payload remains byte-identical.  \n")


def write_rad_examples(destination):
    """Write two different multi-part decks and return their root paths."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    shell = _begin("Three shell panels with independent thickness")
    for part in range(1, 4):
        shell += _material(part, f"Panel steel {part}", 210000 - part * 1000)
        shell += f"/PROP/SHELL/{part}\nPanel thickness {part}\n" + _ints(24, -1, 1, 0)
        shell += _reals(0, 0, 0, 0, .015) + f"{5:10d}{'':10}" + _reals(part, .833).rstrip("\n") + _ints(1, 1, 0)
        shell += f"/PART/{part}\nPanel {part} long readable engineering name\n" + _ints(part, part, 0)
    shell += "/NODE\n"
    for part in range(3):
        for y in range(3):
            for x in range(3):
                shell += f"{part * 9 + y * 3 + x + 1:10d}" + _reals(x * 10, y * 10, part * 8)
    for part in range(3):
        shell += f"/SHELL/{part + 1}\n"
        for y in range(2):
            for x in range(2):
                n = part * 9 + y * 3 + x + 1
                shell += _ints(part * 4 + y * 2 + x + 1, n, n + 1, n + 4, n + 3)
    shell += _conditions((1, 2, 3)) + "/END\n"
    shell_path = destination / "shell_panels_0000.rad"
    shell_path.write_text(shell, encoding="ascii", newline="\n")

    solid = _begin("Two solid blocks with separate INCLUDE geometry")
    for part in (11, 22):
        solid += _material(part, f"Block steel {part}", 205000)
        solid += f"/PROP/SOLID/{part}\nSolid property {part}\n" + _ints(1, 0, 0)
        solid += f"/PART/{part}\nBlock {part}\n" + _ints(part, part, 0)
    solid += "#include\nsolid_geometry.inc\n" + _conditions((101, 102, 103, 104)) + "/END\n"
    geometry = "# Original geometry include; CC0-1.0\n/NODE\n"
    for block in range(2):
        for layer in range(2):
            for corner, (x, y) in enumerate(((0, 0), (10, 0), (10, 8), (0, 8))):
                geometry += f"{101 + block * 8 + layer * 4 + corner:10d}" + _reals(x + block * 20, y, layer * 6)
    geometry += "/BRICK/11\n" + _ints(501, *range(101, 109))
    geometry += "/BRICK/22\n" + _ints(502, *range(109, 117)) + "#enddata\n"
    solid_path = destination / "solid_blocks_0000.rad"
    solid_path.write_text(solid, encoding="ascii", newline="\n")
    (destination / "solid_geometry.inc").write_text(geometry, encoding="ascii", newline="\n")
    return shell_path, solid_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "rad")
    for path in write_rad_examples(parser.parse_args().output):
        print(path)
