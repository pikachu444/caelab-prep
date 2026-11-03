"""Read-only geometry feature review using the shared worker and viewport."""
from dataclasses import asdict
import math
from pathlib import Path
import threading
from uuid import uuid4

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .shell import FileTask, ViewportFrame
from .widgets.numeric import NumericEdit
from ..application.geometry_features import recognize_geometry_features
from ..application.geometry_inspection import read_geometry_inspection


def geometry_projection(inspection, report, preview_id):
    """Display primitives have private IDs; they are never physical FE cells."""
    inspection.verify_assets()
    if (report["geometry_resource_uuid"] != inspection.geometry_resource_uuid
            or report["geometry_revision"] != inspection.geometry_revision
            or report["assets"] != [asdict(asset) for asset in inspection.assets]):
        raise ValueError("Feature results do not belong to this geometry inspection.")
    resource = "geometry-preview:" + preview_id
    projection = {"document_id": preview_id, "document_epoch": preview_id, "revision": 0,
                  "projection_revision": 0, "resource_revisions": {resource: 0},
                  "points": [], "node_ids": [], "cells": [], "node_resources": {}}
    owners = {}
    features = {feature["surface_uuid"]: index for index, feature in enumerate(report["features"], 1)}

    def path(points, *, closed=False, owner=None):
        ids = []
        for point in points:
            identifier = len(projection["node_ids"]) + 1
            projection["node_ids"].append(identifier)
            projection["points"].append(tuple(point))
            projection["node_resources"][identifier] = [resource]
            ids.append(identifier)
        pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if closed else [])
        for first, second in pairs:
            identifier = len(projection["cells"]) + 1
            projection["cells"].append({"id": identifier, "type": "line", "nodes": (first, second),
                "part_id": features.get(owner, 0), "resource_id": resource})
            owners[identifier] = owner

    for curve in inspection.to_dict()["curves"]:
        endpoints = curve["endpoints"]
        if curve["geometry_type"] != "Line" or len(endpoints) != 2 or endpoints[0]["xyz"] == endpoints[1]["xyz"]:
            continue
        matches = set(curve["adjacent_surface_uuids"]) & features.keys()
        path([point["xyz"] for point in endpoints], owner=next(iter(matches)) if len(matches) == 1 else None)
    for feature in report["features"]:
        if feature["kind"] in ("cylindrical_blend_candidate", "conical_blend_candidate"):
            for arc in feature["end_arcs"]:
                center = arc["center"]
                radius = arc.get("radius", feature["radius"])
                directions = [[(value - c) / radius for value, c in zip(point, center)]
                              for point in arc["endpoints"]]
                angle = math.acos(max(-1., min(1., sum(a * b for a, b in zip(*directions)))))
                points = [arc["endpoints"][0]]
                for step in range(1, 16):
                    fraction = step / 16
                    points.append([c + radius * (math.sin((1-fraction)*angle)*a
                        + math.sin(fraction*angle)*b) / math.sin(angle)
                        for c, a, b in zip(center, *directions)])
                points.append(arc["endpoints"][1])
                path(points, owner=feature["surface_uuid"])
            path([arc["center"] for arc in feature["end_arcs"]], owner=feature["surface_uuid"])
            continue
        axis = next(index for index, value in enumerate(feature["axis_direction"]) if value != 0)
        plane = [index for index in range(3) if index != axis]
        for cap in feature["caps"]:
            points = []
            for index in range(64):
                angle = math.tau * index / 64
                point = list(cap["center"])
                point[plane[0]] += feature["radius"] * math.cos(angle)
                point[plane[1]] += feature["radius"] * math.sin(angle)
                points.append(point)
            path(points, closed=True, owner=feature["surface_uuid"])
        path([cap["center"] for cap in feature["caps"]], owner=feature["surface_uuid"])
    inspection.verify_assets()
    return projection, owners


class GeometryFeaturesDialog(QDialog):
    def __init__(self, parent=None, *, backend=None, enable_viewport=True):
        super().__init__(parent)
        self.backend = backend
        self.inspection = self.report = self._task = None
        self._cancel = threading.Event()
        self._closing = False
        self.preview_id = str(uuid4())
        self.projection, self._primitive_owners = {}, {}
        self.setWindowTitle("Geometry features")
        self.resize(1040, 700); self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        title = QLabel("Inspect hole and blend candidates"); title.setObjectName("groupTitle")
        layout.addWidget(title)
        form = QFormLayout(); layout.addLayout(form)
        self.source, self.output = QLineEdit(), QLineEdit()
        self.source.setPlaceholderText("STEP, IGES or saved XAO")
        self.output.setPlaceholderText("Folder for inspection evidence")
        self.source_button, self.output_button = QPushButton("Browse…"), QPushButton("Browse…")
        for label, field, button in (("CAD source", self.source, self.source_button),
                                     ("Evidence folder", self.output, self.output_button)):
            row = QHBoxLayout(); row.addWidget(field, 1); row.addWidget(button); form.addRow(label, row)
        self.source_button.clicked.connect(self.browse_source)
        self.output_button.clicked.connect(self.browse_output)
        self.source.textChanged.connect(self._source_changed)
        self.output.textChanged.connect(self._source_changed)
        controls = QHBoxLayout(); layout.addLayout(controls)
        controls.addWidget(QLabel("Recognition tolerance (mm)"))
        self.tolerance = NumericEdit(1e-6, unit="mm", minimum=0)
        self.tolerance.setMaximumWidth(130); controls.addWidget(self.tolerance)
        self.tolerance.editingFinished.connect(self.reclassify)
        self.tolerance.draftChanged.connect(self._tolerance_changed)
        filters = QHBoxLayout(); layout.addLayout(filters)
        self.limit_blend_radius = QCheckBox("Maximum blend radius (mm)")
        self.limit_blend_radius.setToolTip("For cones, use the maximum finite principal radius r / |cos(alpha)| over the trim.")
        filters.addWidget(self.limit_blend_radius)
        self.blend_radius = NumericEdit(1., unit="mm", minimum=0)
        self.blend_radius.setMaximumWidth(130); self.blend_radius.setEnabled(False)
        filters.addWidget(self.blend_radius); filters.addStretch()
        self.limit_blend_radius.toggled.connect(self._blend_filter_changed)
        self.blend_radius.draftChanged.connect(self._tolerance_changed)
        self.blend_radius.editingFinished.connect(self.reclassify)
        controls.addStretch()
        self.open_button = QPushButton("Open inspection…")
        self.inspect_button = QPushButton("Inspect geometry")
        self.inspect_button.setObjectName("primaryAction")
        self.cancel_button = QPushButton("Cancel inspection"); self.cancel_button.setEnabled(False)
        for button in (self.open_button, self.inspect_button, self.cancel_button):
            button.setAutoDefault(False); controls.addWidget(button)
        self.inspect_button.setShortcut("Alt+I")
        self.open_button.clicked.connect(self.open_inspection)
        self.inspect_button.clicked.connect(self.inspect)
        self.cancel_button.clicked.connect(self.cancel)
        self.summary = QLabel("Choose a CAD source or open existing inspection evidence.")
        self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.error = QLabel(); self.error.setObjectName("inputError"); self.error.setWordWrap(True); layout.addWidget(self.error)
        split = QSplitter(); layout.addWidget(split, 1)
        self.viewport = None
        if enable_viewport:
            from .viewport import MeshViewport
            self.viewport = MeshViewport(self)
            self.viewport.entityPicked.connect(self.pick_entity)
            self.viewport.diagnostic.connect(self._show_error)
            content = self.viewport
        else:
            content = QLabel("The 3D viewer is disabled. Candidate values remain available.")
            content.setWordWrap(True); content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view_frame = ViewportFrame(content, "Feature wireframe", "CAD lines and candidate markers")
        split.addWidget(self.view_frame)
        panel = QWidget(); panel.setMinimumWidth(290); side = QVBoxLayout(panel)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Candidate", "Radius (mm)", "Length (mm)"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2): self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.highlight_selection)
        side.addWidget(self.table, 1)
        self.details = QLabel("Select a candidate to inspect its axis and boundary evidence.")
        self.details.setWordWrap(True); self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.details)
        self.washer_button = QPushButton("Washer controls…")
        self.washer_button.setEnabled(False); self.washer_button.clicked.connect(self.open_washer_controls)
        side.addWidget(self.washer_button)
        split.addWidget(panel); split.setSizes([650, 340])
        note = QLabel("Review units: mm. Supported: axis-aligned circular holes, quarter cylinders and finite quarter cones. "
                      "Cone radius is max(r / |cos(alpha)|); section radii are shown in the details. "
                      "Blend joins require material-oriented tangency on connected planar supports. "
                      "Markers are display lines. No mesh or edge suppression is applied.")
        note.setObjectName("propertySubtitle"); note.setWordWrap(True); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setAutoDefault(False)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _show_error(self, error):
        self.error.setText(str(error))

    def _clear_result(self, *, keep_inspection=False):
        if not keep_inspection: self.inspection = None
        self.report = None; self.projection = {}; self._primitive_owners = {}
        self.preview_id = str(uuid4())
        self.table.setRowCount(0)
        self.washer_button.setEnabled(False)
        self.view_frame.context.setText("No current review")
        self.details.setText("Select a candidate to inspect its axis and boundary evidence.")
        if self.viewport:
            self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})

    def _source_changed(self):
        if self._task is not None: self.cancel()
        self._clear_result(); self.error.clear()
        self.summary.setText("Inputs changed. Inspect geometry or open existing evidence.")

    def _blend_filter_changed(self, checked):
        self.blend_radius.setEnabled(checked and self._task is None)
        if self.inspection is not None: self.reclassify()

    def _tolerance_changed(self):
        if self._task is not None or self.inspection is None: return
        self._clear_result(keep_inspection=True)
        if not self.tolerance.isModified() and not (self.limit_blend_radius.isChecked() and self.blend_radius.isModified()):
            self.reclassify()  # NumericEdit.revert uses setText, restoring the accepted value.
        else:
            self.summary.setText("Finish editing the recognition controls to refresh candidates.")

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "CAD geometry", "", "CAD (*.step *.stp *.iges *.igs *.xao)")
        if path: self.source.setText(path)

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Inspection evidence folder")
        if path: self.output.setText(path)

    def _running(self, busy):
        for control in (self.source, self.output, self.source_button, self.output_button,
                        self.tolerance, self.limit_blend_radius, self.open_button, self.inspect_button):
            control.setEnabled(not busy)
        self.blend_radius.setEnabled(not busy and self.limit_blend_radius.isChecked())
        self.cancel_button.setEnabled(busy and not self._cancel.is_set())

    def _start(self, function):
        if self._task is not None: return False
        self._clear_result(); self.error.clear(); self._cancel.clear(); self._running(True)
        self.summary.setText("Inspecting geometry…")
        task = FileTask(function); self._task = task
        task.signals.complete.connect(self._completed); task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)
        return True

    def inspect(self):
        if not self.source.text().strip() or not self.output.text().strip():
            self._show_error("Choose a CAD source and an evidence folder."); return False
        try:
            if self.tolerance.numeric_value() <= 0: raise ValueError("Enter a positive recognition tolerance.")
            if self.limit_blend_radius.isChecked() and self.blend_radius.numeric_value() < 0:
                raise ValueError("Enter a nonnegative maximum blend radius.")
        except Exception as exc:
            self._show_error(exc); return False
        from ..adapters.gmsh_backend import GmshBackend
        backend = self.backend or GmshBackend()
        source, output = self.source.text(), self.output.text()
        return self._start(lambda: read_geometry_inspection(backend.inspect_geometry(source, output,
            expected_coordinate_length_unit="mm", probe_cylinder_material_side=True,
            probe_cylindrical_blends=True, probe_conical_blends=True, cancel_event=self._cancel)))

    def open_inspection(self, path=None):
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(self, "Geometry inspection", "", "Inspection metadata (*.json)")
        if path: return self._start(lambda: read_geometry_inspection(path))
        return False

    def cancel(self):
        self._cancel.set(); self.cancel_button.setEnabled(False)
        self.summary.setText("Stopping inspection…")

    def _completed(self, inspection):
        self._task = None; self._running(False)
        if self._closing: self._finish_close(); return
        if self._cancel.is_set(): self.summary.setText("Inspection cancelled."); return
        self.present_inspection(inspection)

    def _failed(self, error):
        self._task = None; self._running(False)
        if self._closing: self._finish_close(); return
        self.summary.setText("Inspection cancelled." if self._cancel.is_set() else "Inspection did not complete.")
        if not self._cancel.is_set(): self._show_error(error)

    def present_inspection(self, inspection):
        if inspection.length_unit != "mm":
            self._clear_result()
            self.summary.setText("Review requires mm coordinates.")
            self._show_error("This review supports mm inspection coordinates; saved evidence is not rescaled.")
            return False
        self.inspection = inspection
        source = inspection.to_dict()["source"]["path"]
        blocked = self.source.blockSignals(True); self.source.setText(source); self.source.blockSignals(blocked)
        return self.reclassify()

    def reclassify(self):
        if self._task is not None or self.inspection is None: return False
        self._clear_result(keep_inspection=True); self.error.clear()
        try:
            report = recognize_geometry_features(self.inspection, length_tolerance=self.tolerance.numeric_value(),
                blend_radius_threshold=self.blend_radius.numeric_value() if self.limit_blend_radius.isChecked() else None)
            projection, owners = geometry_projection(self.inspection, report, self.preview_id)
        except Exception as exc:
            self.summary.setText("Review needs valid evidence, a positive tolerance and a valid radius filter.")
            self._show_error(exc); return False
        self.report, self.projection, self._primitive_owners = report, projection, owners
        self.tolerance.accept_value(report["length_tolerance"])
        if self.limit_blend_radius.isChecked(): self.blend_radius.accept_value(report["blend_review"]["radius_threshold"])
        self.table.setRowCount(len(report["features"]))
        for row, feature in enumerate(report["features"]):
            blend = feature["kind"] in ("cylindrical_blend_candidate", "conical_blend_candidate")
            depth = (feature["axial_range"][1] - feature["axial_range"][0]) if blend else math.dist(*(cap["center"] for cap in feature["caps"]))
            label = ("Conical blend" if feature["kind"] == "conical_blend_candidate" else "Cylindrical blend") if blend else (
                "Through hole" if feature["kind"] == "through_hole_candidate" else "Blind hole")
            for column, value in enumerate((label, f"{feature['radius']:.6g}", f"{depth:.6g}")):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if feature["kind"] == "conical_blend_candidate":
                self.table.item(row, 1).setToolTip("Maximum finite principal radius over the conical trim.")
        count = len(report["features"])
        self.summary.setText(f"{count} feature candidate{'s' if count != 1 else ''}. "
                             f"{len(report['unclassified'])} cylinder/cone surface(s) unclassified. Geometry is read-only.")
        self.summary.setToolTip("\n".join("; ".join(reason.replace("_", " ") for reason in
            (row["reason"], row.get("blend_reason")) if reason) for row in report["unclassified"]))
        if self.viewport: self.viewport.set_mesh(projection)
        self.view_frame.context.setText(f"{count} feature candidate{'s' if count != 1 else ''}")
        if count: self.table.selectRow(0)
        return True

    def highlight_selection(self):
        if not self.table.selectionModel().selectedRows():
            self.washer_button.setEnabled(False)
            return
        if self.report is None: return
        row = self.table.currentRow()
        if not 0 <= row < len(self.report["features"]): return
        feature = self.report["features"][row]
        self.washer_button.setEnabled(any(cap["kind"] == "rectangular_opening" for cap in feature.get("caps", [])))
        if feature["kind"] in ("cylindrical_blend_candidate", "conical_blend_candidate"):
            boundary = "Material-oriented tangent joins: " + ", ".join(
                f"edge {join['shared_line_tag']} ({join['angle_radians']:.6g} rad)" for join in feature["tangent_edges"])
            if feature["kind"] == "conical_blend_candidate":
                sections = ", ".join(f"{value:.6g}" for value in feature["cross_section_radius_range"])
                boundary = f"Section radii: {sections} mm\n" + boundary
        else:
            boundary = "End caps: " + ", ".join(cap["kind"].replace("_", " ") for cap in feature["caps"])
        radius_label = "Max normal radius" if feature["kind"] == "conical_blend_candidate" else "Radius"
        self.details.setText(f"{radius_label}: {feature['radius']:.6g} mm\n"
            f"Axis point: {', '.join(f'{value:.6g}' for value in feature['axis_point'])} mm\n"
            f"Axis direction: {', '.join(f'{value:.6g}' for value in feature['axis_direction'])}\n"
            + boundary)
        if self.viewport:
            ids = [identifier for identifier, owner in self._primitive_owners.items() if owner == feature["surface_uuid"]]
            resource = "geometry-preview:" + self.preview_id
            self.viewport.set_selection({**{key: self.projection[key] for key in
                ("document_id", "document_epoch", "revision", "projection_revision", "resource_revisions")},
                "kind": "element", "ids": ids, "refs": [{"resource_id": resource, "entity_kind": "element", "local_id": identifier} for identifier in ids]})

    def pick_entity(self, picked):
        if self.report is None or picked.get("document_id") != self.preview_id: return
        owner = self._primitive_owners.get(picked.get("id"))
        row = next((index for index, feature in enumerate(self.report["features"]) if feature["surface_uuid"] == owner), None)
        if row is not None: self.table.selectRow(row)

    def open_washer_controls(self):
        if self.report is None or not self.table.selectionModel().selectedRows(): return False
        row = self.table.currentRow()
        if not 0 <= row < len(self.report["features"]): return False
        feature = self.report["features"][row]
        if not any(cap["kind"] == "rectangular_opening" for cap in feature.get("caps", [])): return False
        from .washer_controls import WasherControlsDialog
        WasherControlsDialog(self.inspection, feature, length_tolerance=self.report["length_tolerance"], parent=self).exec()
        return True

    def reject(self):
        if self._task is not None:
            self._closing = True; self.cancel(); return
        self._finish_close()

    def _finish_close(self):
        if self.viewport: self.viewport.close()
        super().reject()

    def closeEvent(self, event):
        if self._task is not None: event.ignore(); self.reject()
        else: super().closeEvent(event)
