"""Edit a geometry-bound Washer request using the existing criteria model."""
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFileDialog,
                              QHBoxLayout, QLabel, QPushButton)

from .mesh_workflow import _FormDialog
from .widgets.numeric import NumericEdit
from ..application.meshing_criteria import MeshingCriteria
from ..application.washer_controls import (create_washer_control_draft,
    read_washer_control_draft, save_washer_control_draft)


class WasherControlsDialog(_FormDialog):
    def __init__(self, inspection, feature, *, length_tolerance, parent=None):
        super().__init__("Washer controls", parent)
        self.setMinimumWidth(540)
        self.inspection, self.feature = inspection, feature
        self.length_tolerance = length_tolerance
        self.profile = self.draft = None
        hint = QLabel("Request one or two rings around a hole opening. Mesh generation is unavailable.")
        hint.setWordWrap(True); self.layout.insertWidget(0, hint)
        files = QHBoxLayout()
        self.load_button = QPushButton("Load criteria profile…")
        self.open_button = QPushButton("Open control draft…")
        files.addWidget(self.load_button); files.addWidget(self.open_button)
        self.layout.insertLayout(1, files)
        self.profile_label = QLabel("Load a profile to preserve its target and minimum mesh sizes.")
        self.profile_label.setWordWrap(True); self.layout.insertWidget(2, self.profile_label)
        self.load_button.clicked.connect(self.load_profile)
        self.open_button.clicked.connect(self.open_draft)
        self.opening = QComboBox(); self.opening.addItem("Select an opening", None)
        for cap in feature.get("caps", []):
            if cap["kind"] == "rectangular_opening":
                center = ", ".join(f"{value:.6g}" for value in cap["center"])
                self.opening.addItem(f"Opening at ({center}) mm", cap["surface_uuid"])
        self.family = QComboBox(); self.family.addItem("Select elements", None)
        for label, value in (("Quad", "quad"), ("Tria", "tria")): self.family.addItem(label, value)
        self.layers = QComboBox(); self.layers.addItem("Select layers", None)
        for value in (1, 2): self.layers.addItem(str(value), value)
        self.radial_width = NumericEdit(unit="mm", minimum=0)
        self.divisions = NumericEdit(integer=True, minimum=3)
        for label, field in (("Target opening", self.opening), ("Elements", self.family),
                             ("Radial layers", self.layers), ("Total radial width (mm)", self.radial_width),
                             ("Rim divisions", self.divisions)):
            self.form.addRow(label, field)
        spacing = QLabel("Layers use equal radial spacing. Width runs from the hole boundary to the outer ring.")
        spacing.setWordWrap(True); self.form.addRow(spacing)
        self.status = QLabel("No controls reviewed."); self.status.setWordWrap(True)
        self.layout.insertWidget(self.layout.count()-1, self.status)
        self.review_button = self.buttons.addButton("Review controls", QDialogButtonBox.ButtonRole.ActionRole)
        self.review_button.clicked.connect(self.review)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save draft…")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Close")
        self.buttons.accepted.connect(self.save_draft)
        for box in (self.opening, self.family, self.layers): box.currentIndexChanged.connect(self._changed)
        for field in (self.radial_width, self.divisions): field.draftChanged.connect(self._changed)

    def _changed(self, *unused):
        self.draft = None
        self.status.setText("Review the requested controls. No mesh has been generated.")

    def _fill_profile(self, profile):
        self.profile = profile
        for box, value in ((self.family, profile.washer_element_family), (self.layers, profile.washer_layers)):
            box.setCurrentIndex(max(0, box.findData(value)))
        self.radial_width.accept_value(profile.washer_width if profile.washer_width is not None else "")
        self.divisions.accept_value(profile.washer_rim_divisions if profile.washer_rim_divisions is not None else "")
        self.profile_label.setText(f"Target {profile.target_size:.6g} mm; minimum {profile.minimum_size:.6g} mm. "
                                  "Other profile controls are preserved.")
        if profile.washer_layers not in (None, 1, 2):
            self.profile_label.setText(self.profile_label.text() + " Choose one or two layers for this draft.")
        self._changed()

    def load_profile(self, path=None):
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(self, "Meshing criteria", "", "Criteria (*.json)")
        if not path: return False
        self.error.clear(); self._changed()
        try:
            profile = MeshingCriteria.load(path)
            if profile.length_unit != "mm": raise ValueError("Choose a profile in mm; values are not rescaled.")
            self._fill_profile(profile)
            return True
        except Exception as exc:
            self.error.setText(str(exc)); return False

    def _requested_profile(self):
        if self.profile is None: raise ValueError("Load a meshing criteria profile first.")
        return replace(self.profile, washer_element_family=self.family.currentData(),
            washer_layers=self.layers.currentData(), washer_width=self.radial_width.numeric_value(),
            washer_rim_divisions=self.divisions.numeric_value())

    def _target(self):
        return {"hole_surface_uuid": self.feature["surface_uuid"],
                "opening_surface_uuid": self.opening.currentData(), "length_tolerance": self.length_tolerance}

    def review(self):
        self.error.clear(); self.draft = None
        try:
            requested = self._requested_profile()
            draft = create_washer_control_draft(self.inspection, requested, **self._target())
            self.draft = draft
            self.radial_width.accept_value(requested.washer_width)
            self.divisions.accept_value(requested.washer_rim_divisions)
            radii = ", ".join(f"{radius:.6g}" for radius in draft["radial_layer_radii"])
            self.status.setText(f"Controls and opening are valid. Layer radii: {radii} mm. "
                                "Mesh generation is unavailable.")
            return draft
        except Exception as exc:
            self.status.setText("Controls need valid values and a current opening.")
            self.error.setText(str(exc)); return None

    def save_draft(self, path=None):
        if self.review() is None: return False
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getSaveFileName(self, "Save Washer control draft", "washer-controls.washer.json",
                                                 "Washer controls (*.washer.json)")
        if not path: return False
        try:
            self.draft = save_washer_control_draft(path, self.inspection, self._requested_profile(), **self._target())
            self.status.setText("Control draft saved. No mesh has been generated.")
            return True
        except Exception as exc:
            self.draft = None; self.error.setText(str(exc)); return False

    def open_draft(self, path=None):
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(self, "Washer control draft", "", "Washer controls (*.washer.json)")
        if not path: return False
        self.error.clear(); self._changed()
        try:
            draft = read_washer_control_draft(path)
            if (draft["geometry_resource_uuid"] != self.inspection.geometry_resource_uuid
                    or draft["geometry_revision"] != self.inspection.geometry_revision
                    or draft["assets"] != [asdict(asset) for asset in self.inspection.assets]
                    or draft["hole_surface_uuid"] != self.feature["surface_uuid"]):
                raise ValueError("Select the hole and inspection belonging to this draft first.")
            if draft["length_tolerance"] != self.length_tolerance:
                raise ValueError("Use the saved draft's recognition tolerance in the feature review first.")
            self._fill_profile(MeshingCriteria.from_dict(draft["criteria"]))
            self.opening.setCurrentIndex(self.opening.findData(draft["opening_surface_uuid"]))
            return self.review() is not None
        except Exception as exc:
            self.error.setText(str(exc)); return False
