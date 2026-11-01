# Editor inputs

Run `python examples/inputs.py --output examples/rad` to reproduce the shell
panels and solid blocks, and `python examples/create_stiffened_panel.py` for the
stiffened panel. The generators and generated input data are dedicated to the public
domain under CC0-1.0. No vendor or third-party example is copied.

| Input | Structure | Expected projection |
|---|---|---|
| `rad/shell_panels_0000.rad` | Three shell parts, three materials/thicknesses, constraints, initial velocity, FUNCT, preserved unknown card | 27 nodes, 12 quads |
| `rad/solid_blocks_0000.rad` | Two solid parts, separate geometry INCLUDE, two materials, constraints, initial velocity, FUNCT, preserved unknown card | 16 nodes, 2 hexahedra |
| `rad/stiffened_panel_0000.rad` | Seven shell parts, three thicknesses, shared nodes at matching coordinates, constraints and FUNCT | 1,075 nodes, 1,008 quads |

Open a root with `caelab-prep gui path/to/input.rad`, or use
`caelab-prep compare --rad path/to/input.rad` for the eight presentations.
Supported fields can be edited, undone, saved as `.caeprep`, reopened and
exported to a new RAD output directory. Current creation, assignment and
condition commands are listed in the [product support table](../README.md);
unsupported cards in these fixtures remain preserved and can prevent unsafe
deletion or replacement. Keep `solid_geometry.inc` beside its root deck. The
CLI accepts files supplied by the user; these examples are optional inputs.

These are editor and projection fixtures, not solver validation benchmarks.
They contain no generated Engine companion and make no solver-run claim.
Actual generated tri/tet solver checks use separate inputs in
[`tests/test_solver_generation.py`](../tests/test_solver_generation.py). The
Linux X11 layout/render/pick checks use a separate two-quad input; neither result
certifies these editor fixtures as complete analysis models. Standalone external
MSH import is not supplied by the candidate metadata/XAO/MSH adoption path.
See [current evidence](../docs/execution-stages.md#current-progress) and
[remaining work](../docs/execution-stages.md#remaining-work) before reusing these
examples as completion evidence.
