# Editor inputs

Run `python examples/inputs.py --output examples/rad` to reproduce these original
fixtures. The generator and generated input data are dedicated to the public
domain under CC0-1.0. No vendor or third-party example is copied.

| Input | Structure | Expected projection |
|---|---|---|
| `rad/shell_panels_0000.rad` | Three shell parts, three materials/thicknesses, constraints, initial velocity, FUNCT, preserved unknown card | 27 nodes, 12 quads |
| `rad/solid_blocks_0000.rad` | Two solid parts, separate geometry INCLUDE, two materials, constraints, initial velocity, FUNCT, preserved unknown card | 16 nodes, 2 hexahedra |

Open either root with `caelab-prep gui path/to/input.rad`. Supported existing
fields can be edited, undone, saved as `.caeprep`, reopened and exported to a new
RAD output directory. Keep `solid_geometry.inc` beside its root deck. The CLI
accepts files supplied by the user; these examples are optional inputs.

These are editor and projection fixtures, not solver validation benchmarks.
They contain no generated Engine companion and make no solver-run claim.
