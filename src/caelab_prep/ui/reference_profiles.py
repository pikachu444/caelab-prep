"""Source-bounded UI studies. Names identify references, never the application brand."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceProfile:
    name: str
    version: str
    property_mode: str
    editor: str
    tree_fraction: float
    scenes: tuple[str, ...]
    differences: str


PROFILES = {
    "hypermesh": ReferenceProfile("HyperMesh", "2025 / curve 2025.1", "grid", "inline", .28,
        ("HM03", "HM04", "HM05", "HM21", "HM22"),
        "Entity Editor: Name/Value, gray read-only fields, immediate scalar changes. "
        "Curve editor: table left / plot right. Prep supports shared creation/assignment, multi-selection, "
        "CSV files and curve editing, with whole-table Apply and its own reference/unit semantics. "
        "The source scenes are 2025/2025.1; the requested HyperMesh 2024.1 workflow and native interaction are unverified."),
    "prepomax": ReferenceProfile("PrePoMax", "2.5.0 manual v1.0.0", "grid", "dialog", .17,
        ("manual p3 Fig1", "p5 Fig2", "p7", "p27-29 Fig14"),
        "Compact icon commands, tall left FE tree, model area and bottom output/status. "
        "The acquired manual shows the material library, not the material edit form: "
        "the working property dialog is provisional, not a verified visual reproduction. "
        "Prep material/section creation, assignment and cancellation are connected to shared commands. "
        "Those tasks still need a source-product run; library/contour images do not verify them. "
        "CalculiX execution, PMX files and unit-expression parsing are not provided by this Prep view."),
    "abaqus": ReferenceProfile("Abaqus/CAE", "2025 documentation", "tabs", "dialog", .21,
        ("AB01", "AB04", "AB06", "AB07", "AB23", "AB27", "AB29"),
        "Property module, tree double-click, grouped material dialog and tabular entry. "
        "Prep supports material/section creation and part assignment through shared commands. "
        "The Property-to-material-to-section-to-assignment workflow, units and cancel behavior need native comparison. "
        "Expressions and native .cae are unsupported; Prep unit/reference controls do not establish Abaqus law mappings."),
    "comsol": ReferenceProfile("COMSOL", "6.3 documentation", "settings", "settings", .19,
        ("COM-T02", "COM-T03", "COM-T09a", "COM-T09b", "COM-T09c"),
        "Model Builder / selected-node Settings / Graphics, labeled groups and a separate table. "
        "Prep groups, conditions, saved analysis cases and native export remain RAD operations, not COMSOL physics or Build/Compute. "
        "Expression evaluation and native COMSOL model/selection semantics are unsupported. "
        "Manual Apply and unit choices retain the Prep contract; original commit timing is unverified."),
    "nfx": ReferenceProfile("midas NFX", "2024 education; curve HTML separately", "form", "dialog", .23,
        ("nfx-workspace", "nfx-material", "nfx-property", "nfx-query", "nfx-plastic"),
        "Mesh/material command groups, model tree and labeled isotropic-material dialog; simultaneous table/graph. "
        "Prep creation, assignment, groups, conditions and curve editing use shared commands. "
        "The 2024 education and separate curve sources do not verify one native version or a continuous task. "
        "NFX analysis semantics, cancellation and native DPI still require an actual run."),
    "meshfree": ReferenceProfile("MIDAS MeshFree", "2026 education; UI build unknown", "form", "dialog", .25,
        ("meshfree-trees", "meshfree-assign", "meshfree-material", "meshfree-table", "meshfree-select"),
        "Material editing dialog and spreadsheet pages; model tree separated from editing. "
        "Prep material assignment and saved cases are supported, but are not a verified mapping to MeshFree analysis cases. "
        "Geometry/body selection, mesh-free discretization, units and conditions need an explicit physical mapping. "
        "A non-FE task must retain its engineering goal through a documented equivalent flow; no automatic N/A or native cancel claim."),
    "naksha": ReferenceProfile("Naksha", "0.5.07; library build unknown", "columns", "details", .25,
        ("NA-01", "NA-02", "NA-03", "NA-05", "NA-07", "NA-09"),
        "Outline over Details, ID column, command tabs and a model-local selection strip; library table/plot. "
        "The acquired main image has an empty Details panel: scalar layout and commit timing are unverified. "
        "Prep shared creation, assignment, multi-selection and curves do not prove Naksha library import or strain-rate behavior. "
        "The native desktop workflow still requires execution; the empty image is not evidence of commit timing."),
    "beidprep": ReferenceProfile("BeidPrep", "2.0 web images; UI build unknown", "form", "adjacent", .16,
        ("BE-01", "BE-02", "BE-03", "BE-05", "BE-07", "BE-09"),
        "MODEL tree, adjacent FORM/TEXT card panel, model view and bottom selection band. "
        "The pictured bottom APPLY belongs to selection, not card editing. "
        "The old 1.0.1 small-deck run and 2.0 website images are different evidence. "
        "Prep supported card creation and curve CSV/drag use shared commands; native card commit/cancel and curve behavior remain unverified. "
        "Prep retains explicit Apply; node-move preview and plot digitizer are not supplied by this view."),
}


def profile(key):
    return PROFILES[key]
