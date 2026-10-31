"""Generate an original CC0 editor fixture; no solver calculation is implied."""

from pathlib import Path


def generate():
    nodes = {}
    parts = []

    def node(xyz):
        xyz = tuple(round(v, 8) for v in xyz)
        return nodes.setdefault(xyz, len(nodes) + 1)

    def panel(name, origin, u, v, nu, nv, prop):
        grid = [[node(tuple(origin[k] + u[k] * i / nu + v[k] * j / nv for k in range(3)))
                 for i in range(nu + 1)] for j in range(nv + 1)]
        cells = [(grid[j][i], grid[j][i+1], grid[j+1][i+1], grid[j+1][i])
                 for j in range(nv) for i in range(nu)]
        parts.append((name, prop, cells))

    panel("Base plate", (0, 0, 0), (300, 0, 0), (0, 180, 0), 30, 18, 1)
    for y, suffix in ((40, "L"), (140, "R")):
        panel(f"Longitudinal web {suffix}", (0, y, 0), (300, 0, 0), (0, 0, 35), 30, 4, 2)
        panel(f"Upper flange {suffix}", (0, y-10, 35), (300, 0, 0), (0, 20, 0), 30, 2, 3)
    for x, suffix in ((30, "front"), (270, "rear")):
        panel(f"Transverse rib {suffix}", (x, 0, 0), (0, 180, 0), (0, 0, 25), 18, 3, 2)

    lines = ["# Original CAELab editor fixture; CC0-1.0",
             "# Mesh and existing-field editing fixture; not a validated analysis model.",
             "/BEGIN", "Stiffened panel assembly", f"{2025:10d}{0:10d}",
             f"{'Mg':>20}{'mm':>20}{'s':>20}", "/MAT/LAW1/1", "Steel S355",
             f"{7.85e-9:20.10g}", f"{210000:20.10g}{0.3:20.10g}"]
    for prop, thickness in ((1, 2.0), (2, 1.5), (3, 2.5)):
        lines.extend([f"/PROP/SHELL/{prop}", f"Shell {thickness:g} mm",
                      f"{24:10d}{-1:10d}{1:10d}{0:10d}",
                      "".join(f"{value:20.10g}" for value in (0, 0, 0, 0, .015)),
                      f"{5:10d}{'':20}{thickness:10g}{.833:10g}{1:10d}{1:10d}{0:10d}"])
    for identifier, (name, prop, cells) in enumerate(parts, 1):
        lines.extend([f"/PART/{identifier}", name, f"{prop:10d}{1:10d}{0:10d}"])
    lines.append("/NODE")
    lines.extend(f"{identifier:10d}" + "".join(f"{v:20.10g}" for v in xyz)
                 for xyz, identifier in nodes.items())
    eid = 0
    for identifier, (_, _, cells) in enumerate(parts, 1):
        lines.append(f"/SHELL/{identifier}")
        for cell in cells:
            eid += 1
            lines.append("".join(f"{v:10d}" for v in (eid, *cell)))
    fixed = [identifier for xyz, identifier in nodes.items() if xyz[0] == 0]
    lines.extend(["/GRNOD/NODE/1", "Fixed edge"])
    lines.extend("".join(f"{v:10d}" for v in fixed[i:i+10]) for i in range(0, len(fixed), 10))
    lines.extend(["/BCS/1", "Fixed edge", "   111 111         0         1", "/FUNCT/1", "Load amplitude",
                  f"{0:20g}{0:20g}", f"{.01:20g}{1:20g}", f"{.03:20g}{1:20g}", "/END", ""])
    return "\n".join(lines), len(nodes), eid


if __name__ == "__main__":
    text, nodes, elements = generate()
    output = Path(__file__).parent / "rad" / "stiffened_panel_0000.rad"
    output.write_text(text, encoding="utf-8")
    print(f"{output}: {nodes} nodes, {elements} elements, 7 parts")
