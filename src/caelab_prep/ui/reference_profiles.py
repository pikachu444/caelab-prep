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
        "Curve editor: table left / plot right. Native multi-selection and CSV tools are not implemented. "
        "Prep retains whole-table Apply and its own reference/unit semantics."),
    "prepomax": ReferenceProfile("PrePoMax", "2.5.0 manual v1.0.0", "grid", "dialog", .17,
        ("manual p3 Fig1", "p5 Fig2", "p7", "p27-29 Fig14"),
        "Compact icon commands, tall left FE tree, model area and bottom output/status. "
        "The acquired manual shows the material library, not the material edit form: "
        "the working property dialog is provisional, not a verified visual reproduction. "
        "No CalculiX run, unit-expression parser or material creation is provided."),
    "abaqus": ReferenceProfile("Abaqus/CAE", "2025 documentation", "tabs", "dialog", .21,
        ("AB01", "AB04", "AB06", "AB07", "AB23", "AB27", "AB29"),
        "Property module, tree double-click, grouped material dialog and tabular entry. "
        "Only existing objects are editable. Expressions, multi-pick and native .cae are not supported. "
        "Prep unit/reference controls are explicit extensions, not Abaqus material-law mappings."),
    "comsol": ReferenceProfile("COMSOL", "6.3 documentation", "settings", "settings", .19,
        ("COM-T02", "COM-T03", "COM-T09a", "COM-T09b", "COM-T09c"),
        "Model Builder / selected-node Settings / Graphics, labeled groups and a separate table. "
        "Expression evaluation, physics, Build/Compute and named boundary sets are not implemented. "
        "Manual Apply and unit choices retain the Prep contract; original commit timing is unverified."),
    "nfx": ReferenceProfile("midas NFX", "2024 education; curve HTML separately", "form", "dialog", .23,
        ("nfx-workspace", "nfx-material", "nfx-property", "nfx-query", "nfx-plastic"),
        "Mesh/material command groups, model tree and labeled isotropic-material dialog; simultaneous table/graph. "
        "Only current fields can be edited. Creation, condition sets and solver operations are absent. "
        "Document screenshots are rendered excerpts, not measured native DPI."),
    "meshfree": ReferenceProfile("MIDAS MeshFree", "2026 education; UI build unknown", "form", "dialog", .25,
        ("meshfree-trees", "meshfree-assign", "meshfree-material", "meshfree-table", "meshfree-select"),
        "Material editing dialog and spreadsheet pages; model tree separated from editing. "
        "The source's analysis-case subset has no counterpart in this document, so no fake case tree is shown. "
        "Material assignment, case changes and exact cancel effects remain unsupported/unverified."),
    "naksha": ReferenceProfile("Naksha", "0.5.07; library build unknown", "columns", "details", .25,
        ("NA-01", "NA-02", "NA-03", "NA-05", "NA-07", "NA-09"),
        "Outline over Details, ID column, command tabs and a model-local selection strip; library table/plot. "
        "The acquired main image has an empty Details panel: scalar layout and commit timing are unverified. "
        "No library import, strain-rate model, box/multiple pick or unsupported filters are fabricated."),
    "beidprep": ReferenceProfile("BeidPrep", "2.0 web images; UI build unknown", "form", "adjacent", .16,
        ("BE-01", "BE-02", "BE-03", "BE-05", "BE-07", "BE-09"),
        "MODEL tree, adjacent FORM/TEXT card panel, model view and bottom selection band. "
        "The pictured bottom APPLY belongs to selection, not card editing. "
        "Card commit timing and curve-editor appearance are unverified; Prep retains explicit Apply. "
        "No node-move preview, plot digitizer or new card creation is fabricated."),
}


def profile(key):
    return PROFILES[key]
