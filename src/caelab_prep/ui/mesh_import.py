"""Review a standalone mesh with the same native adoption command in every view."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from .shell import FileTask, default_asset_directory


def import_projection(candidate):
    """A mesh-only preview identity, deliberately unrelated to the open document."""
    resource = candidate.mesh_uuid
    parts = {part.uuid: index + 1 for index, part in enumerate(candidate.parts)}
    return {"document_id": resource, "document_epoch": resource, "revision": 0, "projection_revision": 0,
            "resource_revisions": {resource: 0}, "node_ids": [node.id for node in candidate.nodes],
            "node_resources": {node.id: [resource] for node in candidate.nodes},
            "points": [node.xyz for node in candidate.nodes],
            "cells": [{"id": cell.id, "type": cell.kind,
                       "nodes": _preview_nodes(cell),
                       "resource_id": resource, "part_id": parts.get(cell.part_uuid)}
                      for cell in candidate.cells if cell.kind and cell.dimension == candidate.dimension]}


def _preview_nodes(cell):
    if cell.kind == "tetra10":
        from ..application.tet10_geometry import native_tet10_nodes
        return native_tet10_nodes(cell.node_ids)
    return cell.node_ids


class ImportMeshDialog(QDialog):
    adopted = Signal(object)

    def __init__(self, session, parent=None, *, enable_viewport=True):
        super().__init__(parent)
        self.session, self.candidate, self.result = session, None, None
        self._task = None; self._cancel = threading.Event(); self._closing = False; self._adopting = False
        self._jobs = []
        self._stamp = session.describe()
        self.setWindowTitle("Import mesh — inspect before adoption")
        self.setMinimumSize(760, 480)
        available = self.screen().availableGeometry()
        self.resize(min(1060, available.width() - 40), min(720, available.height() - 60))
        layout = QVBoxLayout(self)
        split = QSplitter(); layout.addWidget(split, 1)
        self.viewport = None
        if enable_viewport:
            from .viewport import MeshViewport
            self.viewport = MeshViewport(self)
            self.viewport.diagnostic.connect(self._show_error)
            split.addWidget(self.viewport)
        panel = QWidget(); column = QVBoxLayout(panel)
        hint = QLabel("Import a CAD-independent Gmsh MSH 2.2/4.1 ASCII file using an explicit element profile. Physical regions become parts and element sets. Boundary face/edge groups become NODE sets; their elements remain source annotations, not shell/beam bodies or contact surfaces. Unsupported data blocks the whole import.")
        hint.setWordWrap(True); column.addWidget(hint)
        form = QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); column.addLayout(form)
        self.source, self.output = QLineEdit(), QLineEdit(default_asset_directory())
        self.browse_buttons = []
        self.source.setAccessibleName("Standalone MSH file"); self.output.setAccessibleName("Keep imported mesh assets")
        for label, field, callback in (("MSH file", self.source, self.browse_source), ("Keep import assets in", self.output, self.browse_output)):
            row = QHBoxLayout(); row.addWidget(field)
            button = QPushButton("Browse…"); button.clicked.connect(callback); row.addWidget(button); form.addRow(label, row)
            self.browse_buttons.append(button)
        self.length = QComboBox(); self.length.addItem("Declare source length unit", None)
        for unit in ("mm", "cm", "m"): self.length.addItem(unit, unit)
        self.length.setAccessibleName("Source mesh length unit"); form.addRow("Source length unit", self.length)
        self.element_profile = QComboBox()
        self.element_profile.addItem("Linear triangle3 / tetra4", "linear")
        self.element_profile.addItem("Straight Tet10 solids (explicit)", "straight_tet10")
        self.element_profile.setAccessibleName("Mesh element profile")
        form.addRow("Element profile", self.element_profile)
        self.profile_hint = QLabel(); self.profile_hint.setWordWrap(True); column.addWidget(self.profile_hint)
        note = QLabel("MSH has no standard length unit. Declare the source unit; it must match the model. Coordinates are not rescaled automatically.")
        note.setWordWrap(True); column.addWidget(note)
        commands = QHBoxLayout()
        self.inspect_button = QPushButton("Inspect mesh"); self.inspect_button.clicked.connect(self.inspect)
        self.cancel_button = QPushButton("Cancel inspection"); self.cancel_button.clicked.connect(self._cancel.set)
        self.cancel_button.setEnabled(False); commands.addWidget(self.inspect_button); commands.addWidget(self.cancel_button)
        column.addLayout(commands)
        self.summary = QLabel("No candidate. Inspection does not change the model."); self.summary.setWordWrap(True); column.addWidget(self.summary)
        self.inventory = QTableWidget(0, 4); self.inventory.setHorizontalHeaderLabels(["Dim.", "Type", "Count", "Role / support"])
        self.groups = QTableWidget(0, 3); self.groups.setHorizontalHeaderLabels(["Source physical group", "Native set", "Members"])
        self.quality = QTableWidget(0, 4); self.quality.setHorizontalHeaderLabels(["Element", "Type", "Quality", "Status"])
        for table in (self.inventory, self.groups, self.quality):
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setMaximumHeight(130); column.addWidget(table)
        self.quality.itemSelectionChanged.connect(self.highlight_quality)
        self.material, self.section = QComboBox(), QComboBox()
        self.material.setAccessibleName("Imported mesh material"); self.section.setAccessibleName("Imported mesh section")
        assign = QFormLayout(); assign.addRow("Material for imported parts", self.material); assign.addRow("Section for imported parts", self.section)
        column.addLayout(assign)
        note = QLabel("Adoption appends all parts and sets in one Undo step. Individual part assignments can be changed afterward.")
        note.setWordWrap(True); column.addWidget(note)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel); split.addWidget(scroll); split.setSizes([560, 480])
        self.error = QLabel(); self.error.setObjectName("inputError"); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.adopt_button = QPushButton("Adopt mesh"); self.adopt_button.setObjectName("primaryAction"); self.adopt_button.clicked.connect(self.adopt)
        self.close_button = QPushButton("Cancel / close"); self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.adopt_button); buttons.addWidget(self.close_button); layout.addLayout(buttons)
        self._references(); self._running(False)
        for field in (self.source, self.output): field.textEdited.connect(self._invalidate_candidate)
        self.length.currentIndexChanged.connect(self._invalidate_candidate)
        self.element_profile.currentIndexChanged.connect(self._profile_changed)
        self._profile_hint()

    def _show_error(self, error): self.error.setText(str(error))

    def _profile_hint(self):
        self.profile_hint.setText(
            "Straight Tet10: corner J ≥ 0.5, edge aspect ratio ≤ 4 and straight midsides. "
            "Adoption requires LAW1 and an explicitly created Tet10 solid section."
            if self.element_profile.currentData() == "straight_tet10" else
            "Linear profile: triangle3 surfaces or tetra4 solids. Higher-order elements block adoption.")

    def _profile_changed(self):
        self._profile_hint(); self._invalidate_candidate()

    def _invalidate_candidate(self):
        if self._task is not None: return
        self.candidate = None; self.adopt_button.setEnabled(False)
        self.summary.setText("Import settings changed. Inspect again before adoption.")
        for table in (self.inventory, self.groups, self.quality): table.setRowCount(0)
        if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Standalone mesh", self.source.text(), "Gmsh ASCII mesh (*.msh)")
        if path: self.source.setText(path); self._invalidate_candidate()

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Keep import assets", self.output.text())
        if path: self.output.setText(path); self._invalidate_candidate()

    def _references(self):
        for box in (self.material, self.section): box.clear(); box.addItem("Select an object", None)
        for card in self.session.list_cards():
            words = card["keyword"].upper().split("/")
            label = f"{card['title'] or card['keyword']} [{card['keyword']}]"
            if len(words) > 3 and words[1] == "MAT" and words[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"):
                self.material.addItem(label, card["id"])
            allowed = ("SHELL", "TYPE1") if self.candidate and self.candidate.dimension == 2 else ("SOLID", "TYPE14")
            if len(words) > 3 and words[1] == "PROP" and words[2] in allowed: self.section.addItem(label, card["id"])

    def _running(self, running):
        for widget in (self.source, self.output, self.length, self.element_profile, self.inspect_button, self.material, self.section, *self.browse_buttons): widget.setEnabled(not running)
        self.cancel_button.setEnabled(running and not self._adopting)
        self.adopt_button.setEnabled(not running and bool(self.candidate and self.candidate.quality.passed))
        self.close_button.setEnabled(not self._adopting)

    def _start(self, function):
        if self._task is not None: return False
        self.error.clear(); self._cancel.clear(); self._running(True)
        task = FileTask(function)
        # Own Python runnables until this dialog is released. A queued result
        # can arrive before QThreadPool has completed QRunnable cleanup.
        task.setAutoDelete(False)
        self._jobs.append(task); self._task = task
        task.signals.complete.connect(self._completed); task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task); return True

    def inspect(self):
        from ..application.external_mesh import import_standalone_mesh
        if self._task is not None: return False
        if not self.source.text().strip() or not self.output.text().strip() or self.length.currentData() is None:
            self._show_error("Choose an MSH file, an import folder and its source length unit."); return False
        self._invalidate_candidate()
        source, output, unit = self.source.text(), self.output.text(), self.length.currentData()
        profile = self.element_profile.currentData()
        self.summary.setText("Inspecting every source element. The model is unchanged.")
        return self._start(lambda: import_standalone_mesh(source, output, length_unit=unit,
            element_profile=profile, cancel_event=self._cancel))

    def _completed(self, result):
        self._task = None
        if self._adopting:
            self._adopting = False; self.result = result; self.adopted.emit(result); self.accept(); return
        if self._closing: super().reject(); return
        if self._cancel.is_set():
            self.summary.setText("Inspection cancelled. The model is unchanged."); self._running(False); return
        self.present_candidate(result); self._running(False)

    def _failed(self, error):
        self._task = None; self._adopting = False; self._running(False)
        if self._closing: super().reject(); return
        self._show_error(error)

    @staticmethod
    def _rows(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values): table.setItem(row, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def present_candidate(self, candidate):
        self.candidate = candidate; self._stamp = self.session.describe(); self._references()
        count = sum(cell.dimension == candidate.dimension for cell in candidate.cells)
        verdict = ("Passed admission checks" if candidate.quality.passed else
                   "Blocked: unsupported or invalid elements. Preview shows supported cells only; the inventory includes every source cell.")
        self.summary.setText(f"MSH {candidate.format_version} · {len(candidate.nodes)} nodes · {count} physical elements · {len(candidate.parts)} parts\n"
                             f"{len(candidate.cells) - count} boundary annotations retained in the source · {candidate.length_unit}\n{verdict}")
        self._rows(self.inventory, [(item.dimension, item.element_name, item.count,
            ("Body" if item.role == "physical" else "Boundary") if item.supported else "UNSUPPORTED") for item in candidate.inventory])
        self._rows(self.groups, [(group.name, group.kind, len(group.member_ids)) for group in candidate.groups])
        rows = [(item.element_id, item.kind, f"{item.q:.5g}", item.problem or "OK") for item in sorted(candidate.quality.cells, key=lambda item: (item.problem is None, item.q))]
        rows = [(identifier, "Unsupported", "—", "Blocks whole import") for identifier in candidate.quality.unsupported_ids] + rows
        self._rows(self.quality, rows[:100]); self.quality.setToolTip("The 100 worst elements. Every element is included in the inventory and validated.")
        if self.viewport: self.viewport.set_mesh(import_projection(candidate))

    def highlight_quality(self):
        if self.viewport is None or self.candidate is None: return
        ids = [int(self.quality.item(index.row(), 0).text()) for index in self.quality.selectionModel().selectedRows()]
        selected = [cell for cell in self.candidate.cells if cell.id in ids]
        # Boundary annotations have no separate adopted shell/beam actor. Show
        # their actual nodes instead of accepting a row click with no feedback.
        kind = "element"
        if any(cell.dimension < self.candidate.dimension or not cell.kind for cell in selected):
            kind = "node"
            ids = sorted({node for cell in selected for node in cell.node_ids})
        resource = self.candidate.mesh_uuid
        self.viewport.set_selection({"document_id": resource, "document_epoch": resource, "revision": 0,
            "projection_revision": 0, "kind": kind, "ids": ids, "resource_revisions": {resource: 0},
            "refs": [{"resource_id": resource, "entity_kind": kind, "local_id": value} for value in ids]})

    def adopt(self):
        if self._task is not None or self.candidate is None: return False
        try:
            native = self.candidate.to_native_mesh()
            material, section = self.material.currentData(), self.section.currentData()
            if not material or not section: raise ValueError("Select a compatible material and section.")
            stamp = dict(self._stamp)
        except Exception as error: self._show_error(error); return False
        self._adopting = True
        self.summary.setText("Revalidating the captured source and adopting parts and sets…")
        return self._start(lambda: self.session.adopt_mesh_candidate(native, material_id=material, property_id=section,
            expected_document_id=stamp["document_id"], expected_revision=stamp["revision"],
            expected_document_epoch=stamp["document_epoch"]))

    def reject(self):
        if self._adopting: return
        if self._task is not None:
            self._closing = True; self._cancel.set(); self.cancel_button.setEnabled(False)
            self.error.setText("Stopping the import worker…"); return
        super().reject()

    def closeEvent(self, event):
        if self._task is not None: event.ignore(); self.reject()
        else: super().closeEvent(event)


class MeshImportWorkflow(QObject):
    def __init__(self, host):
        super().__init__(host)
        self.host, self.dialog = host, None
        self.action = host._action("mesh", "Import standalone mesh…", self.open_dialog, action_id="mesh.import")

    def open_dialog(self):
        host = self.host
        if host._busy or not host._finish_pending_edits(): return
        if not host.session.describe().get("document_id"):
            host.statusBar().showMessage("Create or open a model and create its material and section first."); return
        self.dialog = ImportMeshDialog(host.session, host, enable_viewport=host.viewport is not None)
        if self.dialog.exec(): host.refresh_document(rebuild_viewport=True)
