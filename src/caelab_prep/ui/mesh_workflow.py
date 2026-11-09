"""Candidate review and adoption UI; the session owns every model mutation."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import json
import threading
from uuid import uuid4

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget)

from .shell import FileTask, default_asset_directory
from .widgets.numeric import NumericEdit, VectorEdit


def candidate_projection(candidate, *, dimension=None):
    """A separate preview identity; candidate picks cannot address the document."""
    dimension = candidate.dimension if dimension is None else dimension
    parts = {part.uuid: index + 1 for index, part in enumerate(candidate.parts)}
    resource = candidate.geometry_resource_uuid or candidate.mesh_uuid
    from ..application.structured_mesh import StructuredMeshCandidate
    structured = isinstance(candidate, StructuredMeshCandidate)
    return {"document_id": candidate.mesh_uuid, "document_epoch": candidate.mesh_uuid,
            "revision": 0, "projection_revision": 0, "resource_revisions": {resource: 0},
            "node_ids": [node.id for node in candidate.nodes],
            "points": [node.xyz for node in candidate.nodes],
            "node_resources": {node.id: [resource] for node in candidate.nodes},
            "cells": [{"id": cell.id, "type": "quad" if structured and
                       (cell.dimension, cell.element_type, cell.order, len(cell.node_ids)) == (2, 3, 1, 4)
                       else "hexahedron" if structured and
                       (cell.dimension, cell.element_type, cell.order, len(cell.node_ids)) == (3, 5, 1, 8)
                       else cell.kind, "nodes": cell.node_ids,
                       "part_id": parts.get(cell.part_uuid), "resource_id": resource}
                      for cell in candidate.cells if cell.dimension == dimension]}


class _FormDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.layout = QVBoxLayout(self)
        self.form = QFormLayout()
        self.layout.addLayout(self.form)
        self.error = QLabel(); self.error.setWordWrap(True)
        self.error.setObjectName("inputError")
        self.layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)


class NewDocumentDialog(_FormDialog):
    def __init__(self, session, parent=None):
        super().__init__("New model — working units", parent)
        self.session = session
        self.name = QLineEdit(); self.name.setPlaceholderText("Model name")
        self.form.addRow("Name", self.name)
        self.units = {}
        for key, choices in (("mass", ("Mg", "kg", "g")), ("length", ("mm", "cm", "m")), ("time", ("s", "ms"))):
            box = QComboBox(); box.addItem("Select a unit", None)
            for choice in choices: box.addItem(choice, choice)
            self.units[key] = box; self.form.addRow(key.title(), box)
        hint = QLabel("Material, load and time values use these units. Select all three before creating the model.")
        hint.setWordWrap(True); self.layout.insertWidget(0, hint)
        self.buttons.accepted.connect(self.apply)

    def apply(self):
        try:
            self.session.new_document(self.name.text(), {key: box.currentData() for key, box in self.units.items()})
        except Exception as exc:
            self.error.setText(str(exc)); return False
        self.accept(); return True


class SolverExportDialog(_FormDialog):
    def __init__(self, session, parent=None):
        super().__init__("Export Starter and Engine", parent)
        self.session = session
        self._stamp = session.describe()
        self.path = QLineEdit(); self.path.setPlaceholderText("New folder / model_0000.rad")
        browse = QPushButton("Browse…"); browse.clicked.connect(self.browse)
        row = QHBoxLayout(); row.addWidget(self.path); row.addWidget(browse)
        self.form.addRow("Starter file", row)
        self.end = NumericEdit(minimum=0)
        self.interval = NumericEdit(minimum=0)
        self.form.addRow("End time", self.end); self.form.addRow("Output interval", self.interval)
        self.case = QComboBox()
        self.case.addItem("Manual settings — all native conditions", None)
        cases = session.analysis_cases()
        self._saved_cases = {item["id"]: item for item in cases["cases"]}
        for item in cases["cases"]:
            self.case.addItem(item["name"], item["id"])
        self.form.insertRow(1, "Analysis case", self.case)
        self.hint = QLabel()
        self.hint.setWordWrap(True); self.layout.insertWidget(0, self.hint)
        self.case.currentIndexChanged.connect(self._case_changed)
        self.case.setCurrentIndex(max(0, self.case.findData(cases["active_case_id"])))
        self._case_changed()
        self.result = None
        self.buttons.accepted.connect(self.apply)

    def _case_changed(self):
        current = self.session.describe()
        if any(current.get(key) != self._stamp.get(key) for key in ("document_id", "document_epoch", "revision")):
            self.error.setText("The model changed while export was open. Close and reopen export to review the current cases.")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return
        case_id = self.case.currentData()
        self.end.setEnabled(case_id is None); self.interval.setEnabled(case_id is None)
        if case_id is None:
            self.end.clear(); self.interval.clear()
            self.hint.setText("Manual export uses all native conditions and times in the model's declared time unit. Choose a saved analysis case to use its active conditions and settings. Export does not run a solver.")
        else:
            case = self._saved_cases[case_id]
            self.end.setText(format(case["end_time"], ".16g"))
            self.interval.setText(format(case["output_interval"], ".16g"))
            self.hint.setText(f"Saved case: {case['name']} — times in {case['time_unit']}, {len(case['condition_ids'])} active conditions. Edit this case in Analysis cases to change these settings. Export does not run a solver.")

    def browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "New solver input", self.path.text(), "Radioss Starter (*_0000.rad)")
        if path: self.path.setText(path)

    def apply(self):
        try:
            current = self.session.describe()
            if any(current.get(key) != self._stamp.get(key) for key in ("document_id", "document_epoch", "revision")):
                raise ValueError("The model changed while export was open. Close and reopen export to review the current case.")
            if self.case.currentData() is not None:
                self.result = self.session.export_analysis_case(self.path.text(), self.case.currentData(),
                    expected_revision=self._stamp["revision"], expected_document_id=self._stamp["document_id"])
            else:
                self.result = self.session.export_solver_inputs(self.path.text(), self.end.numeric_value(), self.interval.numeric_value())
        except Exception as exc:
            self.error.setText(str(exc)); return False
        self.accept(); return True


class MeshCandidateDialog(QDialog):
    """Generate off the GUI thread, review, then commit once with a revision guard."""
    adopted = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, enable_viewport=True, backend=None):
        super().__init__(parent)
        self.session = session
        self.backend = backend
        self.candidate = None
        self.result = None
        self._task = None
        self._cancel = threading.Event()
        self._closing = False
        self._adopting = False
        self._reviewing = self._presenting = False
        self._running_job = False
        self._replacement_plan = None
        self._review_generation = 0
        self._stamp = session.describe()
        self.setWindowTitle("Mesh — review candidate")
        self._seed_recipe = None
        self._seed_source = None
        self.division_edits = []
        self.geometry_edits = []
        self._geometry_dirty = False
        self.setMinimumSize(760, 480)
        available = self.screen().availableGeometry()
        self.resize(min(1100, available.width() - 40), min(760, available.height() - 60))
        layout = QVBoxLayout(self)
        preview_bar = QHBoxLayout()
        self.preview_mode = QComboBox(); self.preview_mode.addItem("Physical mesh", None)
        self.preview_mode.addItem("Boundary surfaces", 2)
        self.preview_mode.currentIndexChanged.connect(self.refresh_preview)
        preview_bar.addWidget(self.preview_mode)
        self.pick_hint = QLabel("Click the preview to select an entity for local refinement.")
        self.pick_hint.setWordWrap(True); preview_bar.addWidget(self.pick_hint, 1)
        layout.addLayout(preview_bar)
        split = QSplitter(); layout.addWidget(split, 1)
        self.viewport = None
        if enable_viewport:
            from .viewport import MeshViewport
            self.viewport = MeshViewport(self)
            self.viewport.diagnostic.connect(self._show_error)
            self.viewport.entityPicked.connect(self.pick_entity)
            split.addWidget(self.viewport)
        panel = QWidget(); form_layout = QVBoxLayout(panel)
        form = QFormLayout(); self.form = form
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); form_layout.addLayout(form)
        self.source_kind = QComboBox()
        self.source_kind.addItem("CAD / XAO", "cad_gmsh")
        self.source_kind.addItem("Structured quad / sweep hex recipe", "structured_recipe")
        form.addRow("Source type", self.source_kind)
        self.source = QLineEdit(); self.output = QLineEdit(default_asset_directory())
        self._browse_buttons = []
        for label, field, callback in (("CAD / XAO", self.source, self.browse_source), ("Candidate folder", self.output, self.browse_output)):
            row = QHBoxLayout(); row.addWidget(field)
            button = QPushButton("Browse…"); button.clicked.connect(callback); row.addWidget(button)
            self._browse_buttons.append(button)
            form.addRow(label, row)
            if field is self.source: self.source_label = form.labelForField(row)
        self.size = NumericEdit(minimum=0); self.size.setPlaceholderText("Positive target size")
        self.dimension = QComboBox(); self.dimension.addItem("3D tetrahedra", 3); self.dimension.addItem("2D triangles", 2)
        self.policy = QComboBox()
        for label, key in (("Preserve source topology", "preserve"), ("Conformal touching solids", "conformal"), ("Verify independent solids", "independent")):
            self.policy.addItem(label, key)
        form.addRow("Global size", self.size); form.addRow("Mesh", self.dimension); form.addRow("Interfaces", self.policy)
        self.local_entity = QComboBox(); self.local_entity.addItem("No local refinement", None)
        self.local_entity.currentIndexChanged.connect(self.highlight_entity)
        self.local_size = NumericEdit(minimum=0)
        form.addRow("Refine entity", self.local_entity); form.addRow("Local size", self.local_size)
        self.project_recipe_button = QPushButton("Open project recipe…")
        self.project_recipe_button.setToolTip("Use inputs saved when a structured mesh was adopted. Later mesh edits are not reconstructed.")
        self.project_recipe_button.clicked.connect(self.open_project_recipe)
        form.addRow(self.project_recipe_button)
        self.load_divisions_button = QPushButton("Load recipe divisions")
        self.load_divisions_button.clicked.connect(self.load_divisions)
        form.addRow(self.load_divisions_button)
        self.divisions = QTableWidget(0, 3)
        self.divisions.setHorizontalHeaderLabels(["Patch", "Edge 1–2", "Edge 2–3"])
        self.divisions.verticalHeader().hide()
        self.divisions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.divisions.setMaximumHeight(125)
        self.divisions.setToolTip("Segment counts along the patch's ordered corner edges, not global X/Y. Shared edges must agree.")
        form.addRow("Patch divisions", self.divisions)
        self.layers = NumericEdit(integer=True, minimum=1, maximum=10000)
        self.layers.setAccessibleName("Shared sweep layers")
        self.layers.setToolTip("One sweep layer count for the whole hex recipe, shared by both patches.")
        self.layers.textChanged.connect(self._divisions_changed)
        form.addRow("Sweep layers", self.layers)
        self.geometry_toggle = QPushButton("Edit single-patch geometry…")
        self.geometry_toggle.setCheckable(True)
        form.addRow(self.geometry_toggle)
        self.geometry_panel = QWidget()
        geometry_layout = QVBoxLayout(self.geometry_panel)
        geometry_layout.setContentsMargins(0,0,0,0)
        self.geometry_hint = QLabel("Corner order follows the input. Save changed geometry as a new recipe before generation.")
        self.geometry_hint.setWordWrap(True); geometry_layout.addWidget(self.geometry_hint)
        self.geometry_form = QFormLayout()
        self.geometry_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        geometry_layout.addLayout(self.geometry_form)
        self.fork_button = QPushButton("Save as new recipe…")
        self.fork_button.clicked.connect(self.fork_geometry)
        geometry_layout.addWidget(self.fork_button)
        self.geometry_toggle.toggled.connect(self._sync_geometry)
        form.addRow(self.geometry_panel)
        self.generate_button = QPushButton("Generate candidate")
        self.cancel_job = QPushButton("Cancel generation"); self.cancel_job.setEnabled(False)
        self.generate_button.clicked.connect(self.generate)
        self.cancel_job.clicked.connect(self._cancel.set)
        row = QHBoxLayout(); row.addWidget(self.generate_button); row.addWidget(self.cancel_job); form_layout.addLayout(row)
        self.open_button = QPushButton("Open saved candidate…"); self.open_button.clicked.connect(self.open_candidate)
        form_layout.addWidget(self.open_button)
        self.summary = QLabel("No candidate. Generation does not change the model.")
        self.summary.setWordWrap(True); form_layout.addWidget(self.summary)
        self.quality = QTableWidget(0, 4); self.quality.setHorizontalHeaderLabels(["Element", "Type", "Quality", "Status"])
        self.quality.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.quality.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.quality.itemSelectionChanged.connect(self.highlight_quality)
        self.quality.setMaximumHeight(170); form_layout.addWidget(self.quality)
        adopt_form = QFormLayout(); self.adopt_form = adopt_form; form_layout.addLayout(adopt_form)
        self.length = QComboBox()
        self.length.addItem("Declare unknown source units", None)
        for unit in ("mm", "cm", "m"): self.length.addItem(unit, unit)
        self.material = QComboBox(); self.section = QComboBox()
        adopt_form.addRow("Length unit", self.length)
        adopt_form.addRow("Material", self.material); adopt_form.addRow("Section", self.section)
        self.replace = QListWidget(); self.replace.setMaximumHeight(95)
        adopt_form.addRow("Replace parts\n(optional)", self.replace)
        self._fill_references()
        self.replacement_details = QTextBrowser()
        self.replacement_details.setObjectName("cadReplacementReview")
        self.replacement_details.setMinimumHeight(120)
        form_layout.addWidget(self.replacement_details)
        self.replacement_reviewed = QCheckBox("Replacement reviewed")
        self.replacement_reviewed.setToolTip("I reviewed the replacement and targets that will become stale.")
        self.replacement_reviewed.setAccessibleName("Replacement and stale targets reviewed")
        self.replacement_reviewed.toggled.connect(self._sync_adoption)
        form_layout.addWidget(self.replacement_reviewed)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel); split.addWidget(scroll)
        split.setSizes([620, 480])
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setObjectName("inputError"); layout.addWidget(self.error)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.review_button = QPushButton("Review replacement")
        self.review_button.clicked.connect(self.review_replacement)
        self.adopt_button = QPushButton("Adopt candidate"); self.adopt_button.setObjectName("primaryAction"); self.adopt_button.setEnabled(False)
        self.close_button = QPushButton("Close")
        self.adopt_button.clicked.connect(self.adopt); self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.review_button); buttons.addWidget(self.adopt_button); buttons.addWidget(self.close_button); layout.addLayout(buttons)
        self.source_kind.currentIndexChanged.connect(self._source_changed)
        self.source.textChanged.connect(self._recipe_source_changed)
        for field in (self.size, self.local_size): field.textChanged.connect(self._cad_inputs_changed)
        for field in (self.dimension, self.policy): field.currentIndexChanged.connect(self._cad_inputs_changed)
        for field in (self.material, self.section, self.length): field.currentIndexChanged.connect(self._invalidate_replacement)
        self.replace.itemChanged.connect(self._invalidate_replacement)
        self.local_entity.currentIndexChanged.connect(self._local_selection_changed)
        self.sessionEvent.connect(self._session_changed)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.destroyed.connect(self._unsubscribe)
        self.finished.connect(self._finished)
        self._source_controls()
        self._sync_adoption()

    def _sync_geometry(self):
        supported = bool(self._structured() and self._seed_recipe and 'patches' not in self._seed_recipe)
        self.geometry_toggle.setVisible(self._structured())
        self.geometry_toggle.setEnabled(supported and not self._running_job)
        self.geometry_toggle.setToolTip("Fixed corner order; a new input file. Two-patch geometry editing is not connected.")
        self.geometry_panel.setVisible(supported and self.geometry_toggle.isChecked())
        self.geometry_panel.setEnabled(not self._running_job)
        self.generate_button.setEnabled(not self._running_job and not self._geometry_dirty)

    def _geometry_changed(self):
        try:
            points = [list(editor.numeric_value()) for editor in self.geometry_edits]
            expected = [*self._seed_recipe['corners'], *([self._seed_recipe['vector']] if self._seed_recipe['mode'] == 'hex' else [])]
            self._geometry_dirty = points != expected
        except ValueError:
            self._geometry_dirty = True
        self._invalidate_candidate()
        self.summary.setText("Geometry changed. Save it as a new recipe before generating a new candidate." if self._geometry_dirty
                             else "Geometry restored. Generate a new candidate to check quality before adoption.")

    def _current_recipe(self):
        from ..application.structured_geometry import validate_recipe
        recipe = deepcopy(self._seed_recipe)
        for patch, edits in zip(recipe.get('patches', [recipe]), self.division_edits):
            patch['divisions'] = [edit.numeric_value() for edit in edits]
        if recipe['mode'] == 'hex': recipe['layers'] = self.layers.numeric_value()
        validate_recipe(recipe)
        return recipe

    def fork_geometry(self):
        if self._task is not None or not self.geometry_edits: return False
        try:
            from ..application.structured_mesh import fork_geometry_recipe
            base, origin = self._current_recipe(), self._seed_source
            corners = [editor.numeric_value() for editor in self.geometry_edits[:4]]
            vector = self.geometry_edits[4].numeric_value() if base['mode'] == 'hex' else None
            from ..application.structured_geometry import validate_recipe
            edited = deepcopy(base); edited['corners'] = [list(point) for point in corners]
            if vector is not None: edited['vector'] = list(vector)
            validate_recipe(edited)
            path, _ = QFileDialog.getSaveFileName(self, "New geometry recipe", "", "Recipe (*.json)")
            if not path: return False
            forked = fork_geometry_recipe(base, origin, path, corners=corners, vector=vector)
            self.source.setText(forked)
            if not self.load_divisions(): return False
            self.summary.setText("New geometry recipe saved. Generate a new candidate to check quality before adoption.")
            return True
        except Exception as exc:
            self._show_error(exc); return False

    def _selected_parts(self):
        return [self.replace.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.replace.count())
                if not self._structured() and self.replace.item(row).checkState() == Qt.CheckState.Checked]

    def _sync_adoption(self):
        replacement = bool(self._selected_parts())
        ready = not self._running_job and self._task is None and self.candidate is not None and self.candidate.quality.passed
        self.review_button.setVisible(replacement)
        self.review_button.setEnabled(ready)
        self.replacement_details.setVisible(replacement)
        self.replacement_reviewed.setVisible(replacement)
        self.replacement_reviewed.setEnabled(ready and self._replacement_plan is not None)
        self.adopt_button.setText("Apply replacement" if replacement else "Adopt candidate")
        self.adopt_button.setEnabled(ready and (not replacement or
            (self._replacement_plan is not None and self.replacement_reviewed.isChecked())))

    def _invalidate_replacement(self, *_):
        if self._presenting: return
        self._review_generation += 1
        if self._replacement_plan is not None:
            self.session.cancel_cad_mesh_replacement(self._replacement_plan["plan_id"])
        self._replacement_plan = None
        self.replacement_details.clear(); self.replacement_reviewed.setChecked(False)
        self._sync_adoption()

    def _session_changed(self, event):
        if not self._adopting and any(event.get(key) != self._stamp.get(key)
                for key in ("document_id", "revision", "document_epoch")):
            self._invalidate_replacement()

    def _finished(self, _):
        self._invalidate_replacement()
        self._unsubscribe()

    def _cad_inputs_changed(self, *_):
        if self._presenting or self._structured(): return
        self._invalidate_candidate(keep_entities=True)
        self.summary.setText("Mesh inputs changed. Generate a new candidate to check quality before adoption.")

    def _local_selection_changed(self, *_):
        if self._presenting: return
        self._invalidate_replacement()
        if not self._structured() and self.local_size.text().strip(): self._cad_inputs_changed()

    def _structured(self):
        return self.source_kind.currentData() == "structured_recipe"

    def _source_controls(self):
        structured = self._structured()
        for widget in (self.size, self.dimension, self.policy, self.local_size):
            widget.setVisible(not structured)
            self.form.labelForField(widget).setVisible(not structured)
        self.replace.setVisible(not structured)
        self.adopt_form.labelForField(self.replace).setVisible(not structured)
        self.source_label.setText("Mesh recipe (JSON)" if structured else "CAD / XAO")
        self.form.labelForField(self.local_entity).setText(("Highlight patch" if self.viewport else "Patch") if structured else "Refine entity")
        self.preview_mode.setVisible(not structured)
        self.load_divisions_button.setVisible(structured)
        self.project_recipe_button.setVisible(structured)
        self.divisions.setVisible(structured and self._seed_recipe is not None)
        self.form.labelForField(self.divisions).setVisible(structured and self._seed_recipe is not None)
        hex_layers = structured and self._seed_recipe is not None and self._seed_recipe.get("mode") == "hex"
        self.layers.setVisible(hex_layers); self.form.labelForField(self.layers).setVisible(hex_layers)
        self._sync_geometry()
        self.pick_hint.setText(("Planar quad4 / sweep hex8. Load recipe divisions to edit segment counts and hex layers; units and geometry stay in the recipe. " +
                               ("Preview does not change the model." if self.viewport else "3D preview is disabled."))
                               if structured else "Click the preview to select an entity for local refinement.")
        self.quality.setSelectionMode(QTableWidget.SelectionMode.NoSelection if structured else QTableWidget.SelectionMode.ExtendedSelection)

    def _source_changed(self):
        self.source.clear(); self._clear_divisions()
        self._invalidate_candidate()
        self._source_controls()

    def _invalidate_candidate(self, *, keep_entities=False):
        self._invalidate_replacement()
        self.candidate = None
        self.error.clear(); self.quality.setRowCount(0)
        self.summary.setText("No candidate. Generation does not change the model.")
        if not keep_entities:
            self.local_entity.blockSignals(True)
            self.local_entity.clear(); self.local_entity.addItem("No patch selected" if self._structured() else "No local refinement", None)
            self.local_entity.blockSignals(False)
        if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})
        self._running(False)

    def _clear_divisions(self):
        self._seed_recipe = self._seed_source = None
        self.division_edits = []
        self.divisions.setRowCount(0)
        self.layers.blockSignals(True); self.layers.accept_value(""); self.layers.blockSignals(False)
        self._geometry_dirty = False
        self.geometry_edits = []
        while self.geometry_form.rowCount(): self.geometry_form.removeRow(0)
        self.geometry_toggle.blockSignals(True); self.geometry_toggle.setChecked(False); self.geometry_toggle.blockSignals(False)
        self.geometry_panel.hide()

    def _recipe_source_changed(self):
        if self._presenting: return
        if self._structured():
            self._clear_divisions(); self._invalidate_candidate(); self._source_controls()
        else: self._invalidate_candidate()

    def _set_divisions(self, recipe, source):
        self._clear_divisions()
        if recipe.get("mode") not in ("quad", "hex"): return
        self._seed_recipe = deepcopy(recipe); self._seed_source = source
        if 'patches' not in recipe:
            points = [*recipe['corners'], *([recipe['vector']] if recipe['mode'] == 'hex' else [])]
            for index, point in enumerate(points):
                editor = VectorEdit(point, unit=recipe['unit'])
                editor.draftChanged.connect(self._geometry_changed)
                self.geometry_edits.append(editor)
                self.geometry_form.addRow(f"Corner {index + 1}" if index < 4 else "Sweep vector", editor)
        if recipe["mode"] == "hex":
            self.layers.blockSignals(True); self.layers.accept_value(recipe["layers"]); self.layers.blockSignals(False)
        patches = recipe.get("patches", [recipe])
        self.divisions.setRowCount(len(patches))
        for row, patch in enumerate(patches):
            item = QTableWidgetItem(patch.get("id") or recipe.get("name") or "Patch 1")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(item.text()); self.divisions.setItem(row, 0, item)
            edits = []
            for column, value in enumerate(patch["divisions"], 1):
                edit = NumericEdit(value, integer=True, minimum=1, maximum=10000)
                edit.setAccessibleName(f"{item.text()} edge {column}–{column + 1} divisions")
                edit.textChanged.connect(self._divisions_changed)
                self.divisions.setCellWidget(row, column, edit); edits.append(edit)
            self.division_edits.append(edits)

    def _divisions_changed(self):
        self._invalidate_candidate()
        self.summary.setText("Geometry changed. Save it as a new recipe before generating a new candidate." if self._geometry_dirty
                             else "Divisions changed. Generate a new candidate to check quality before adoption.")

    def load_divisions(self):
        from ..application.structured_mesh import read_recipe_input
        from ..application.structured_geometry import validate_recipe
        self._clear_divisions(); self._invalidate_candidate()
        try:
            recipe, source = read_recipe_input(self.source.text())
            validate_recipe(recipe)
            self._set_divisions(recipe, source)
        except Exception as exc:
            self._show_error(exc); self._source_controls(); return False
        self._source_controls(); return True

    def open_project_recipe(self):
        if self._task is not None: return False
        try:
            records = self.session.structured_mesh_recipes()
            if not records:
                self._show_error("This project has no archived structured recipes. Earlier projects require their external recipe files.")
                return False
            choices = [f"{index + 1}. {record['name']} ({record['mode']}, {record['length_unit']})"
                       for index, record in enumerate(records)]
            choice, accepted = QInputDialog.getItem(self, "Project generation inputs", "Recipe saved at adoption", choices, 0, False)
            if not accepted: return False
            parent = QFileDialog.getExistingDirectory(self, "Extract inputs into a new child folder", self.output.text())
            if not parent: return False
            selected = records[choices.index(choice)]
            result = self.session.export_structured_recipe(selected["id"], Path(parent) / ("recipe-" + str(uuid4())),
                expected_document_id=selected["document_id"], expected_document_epoch=selected["document_epoch"],
                expected_revision=selected["revision"])
            self.source.setText(result["recipe_path"]); self.output.setText(parent)
            if not self.load_divisions(): return False
            self.summary.setText("Adoption-time recipe extracted. Generate a new candidate to check current geometry and quality. Later mesh edits are not reconstructed.")
            return True
        except Exception as exc:
            self._show_error(exc); return False

    def _show_error(self, error):
        self.error.setText(str(error))

    def _fill_references(self):
        for box in (self.material, self.section): box.clear(); box.addItem("Select an object", None)
        self.replace.clear()
        for card in self.session.list_cards():
            words = card["keyword"].upper().split("/")
            label = f"{card['title'] or card['keyword']}  [{card['keyword']}]"
            if len(words) >= 4 and words[1] == "MAT" and words[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"): self.material.addItem(label, card["id"])
            allowed = ("SHELL", "TYPE1") if self.candidate and self.candidate.dimension == 2 else ("SOLID", "TYPE14") if self.candidate else ("SHELL", "TYPE1", "SOLID", "TYPE14")
            if len(words) >= 4 and words[1] == "PROP" and words[2] in allowed: self.section.addItem(label, card["id"])
            if len(words) >= 3 and words[1] == "PART":
                item = QListWidgetItem(label); item.setData(Qt.ItemDataRole.UserRole, card["id"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Unchecked); self.replace.addItem(item)

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Structured mesh recipe" if self._structured() else "CAD geometry", self.source.text(),
            "Recipe (*.json)" if self._structured() else "CAD (*.step *.stp *.brep *.brp *.iges *.igs *.xao)")
        if path: self.source.setText(path)

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Keep candidate assets", self.output.text())
        if path: self.output.setText(path)

    def _running(self, value):
        self._running_job = value
        for widget in (*self._browse_buttons, self.source_kind, self.generate_button, self.open_button, self.source, self.output, self.size, self.dimension, self.policy, self.local_entity, self.local_size,
                       self.material, self.section, self.replace, self.preview_mode, self.quality, self.project_recipe_button, self.load_divisions_button, self.divisions, self.layers): widget.setEnabled(not value)
        self.length.setEnabled(not value and bool(self.candidate and self.candidate.length_unit == "unknown"))
        self.preview_mode.setEnabled(not value and bool(self.candidate and self.candidate.dimension == 3))
        self.cancel_job.setEnabled(value)
        self._sync_adoption()
        if self._structured():
            for widget in (self.size, self.dimension, self.policy, self.local_size, self.length, self.replace, self.preview_mode):
                widget.setEnabled(False)
        self._sync_geometry()

    def _start(self, function):
        if self._task is not None: return False
        if not self._adopting and not self._reviewing:
            self._invalidate_replacement()
            self.candidate = None
            self.quality.setRowCount(0)
            self.local_entity.clear(); self.local_entity.addItem("No local refinement", None)
            self.summary.setText("Generating or inspecting a candidate. The model is unchanged.")
            if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})
        self.error.clear(); self._cancel.clear(); self._running(True)
        task = FileTask(function); self._task = task
        task.signals.complete.connect(self._completed)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task); return True

    def generate(self):
        if self._geometry_dirty:
            self._show_error("Save changed geometry as a new recipe before generation."); return False
        if self._structured():
            source, output = self.source.text(), self.output.text()
            recipe, origin = None, self._seed_source
            if self._seed_recipe is not None:
                try:
                    recipe = self._current_recipe()
                except Exception as exc:
                    self._show_error(exc); return False
            def generate_recipe():
                from ..application.structured_mesh import read_recipe_input, generate_structured_mesh
                original, current = read_recipe_input(source)
                if origin is not None and current != origin:
                    raise ValueError("The original recipe changed after review. Load its divisions again.")
                edited = original if recipe is None else recipe
                if not isinstance(edited, dict) or edited.get("mode") not in ("quad", "hex"):
                    raise ValueError("Choose a quad or sweep hex recipe; other families are not connected to adoption.")
                if edited != original:
                    return generate_structured_mesh(edited, output, source_recipe=current, cancel_event=self._cancel)
                return generate_structured_mesh(edited, output, recipe_path=source, cancel_event=self._cancel)
            return self._start(generate_recipe)
        from ..adapters.gmsh_backend import GmshBackend
        from ..application.mesh_candidates import read_mesh_candidate
        try:
            size = self.size.numeric_value()
            if not self.output.text().strip(): raise ValueError("Choose a folder to keep candidate assets.")
            source, output = self.source.text(), self.output.text()
            dimension, policy = self.dimension.currentData(), self.policy.currentData()
            local = {self.local_entity.currentData(): self.local_size.numeric_value()} if self.local_entity.currentData() else {}
        except Exception as exc: self._show_error(exc); return False
        backend = self.backend or GmshBackend()
        return self._start(lambda: read_mesh_candidate(backend.generate(source, output, size,
            dimension=dimension, interface_policy=policy, local_sizes=local, cancel_event=self._cancel)))

    def open_candidate(self, path=None):
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(self, "Saved candidate", "", "Candidate metadata (*.json)")
        if path:
            if self._structured():
                def read_recipe_candidate():
                    from ..application.structured_mesh import read_structured_mesh_candidate
                    candidate = read_structured_mesh_candidate(path, cancel_event=self._cancel)
                    if candidate.dimension not in (2, 3):
                        raise ValueError("Only planar quad4 and sweep hex8 candidates can be adopted here.")
                    return candidate
                return self._start(read_recipe_candidate)
            from ..application.mesh_candidates import read_mesh_candidate
            return self._start(lambda: read_mesh_candidate(path))
        return False

    def _completed(self, candidate):
        self._task = None
        if self._adopting:
            self._adopting = False
            self.result = candidate
            self.adopted.emit(self.result); self.accept(); return
        if self._reviewing:
            self._reviewing = False
            current = self.session.describe()
            if (self._closing or self._cancel.is_set() or self._task_review_generation != self._review_generation or
                    any(candidate[key] != current[key] for key in ("document_id", "revision", "document_epoch"))):
                self.session.cancel_cad_mesh_replacement(candidate["plan_id"])
                self._running(False)
                if self._closing: super().reject()
                else: self._show_error("The model or replacement inputs changed. Review the replacement again.")
                return
            self._replacement_plan = candidate
            lines = [f"Model nodes: {candidate['old_node_count']} → {candidate['node_count']}",
                     f"Model elements: {candidate['old_element_count']} → {candidate['element_count']}",
                     "Replacement and stale markers form one Undo.", "", "Targets that will become stale:"]
            lines += [f"{candidate['target_labels'][key]} · {value['family']} · {len(value['members'])} old members"
                      for key, value in candidate["stale_targets"].items()]
            if not candidate["stale_targets"]: lines.append("None")
            lines += ["", "Affected conditions:"]
            for condition in candidate["affected_conditions"]:
                lines.append(candidate["condition_labels"][condition["card_id"]])
            if not candidate["affected_conditions"]: lines.append("None")
            lines += ["", "Old groups and conditions remain unchanged. Analysis export stays blocked until every stale target is explicitly reconnected. New boundary nodes are not added automatically; review the physical region and load distribution after reconnection."]
            self.replacement_details.setPlainText("\n".join(lines))
            self._running(False); return
        if self._closing: super().reject(); return
        if self._cancel.is_set(): self._running(False); self.summary.setText("Generation cancelled. The model is unchanged."); return
        self.present_candidate(candidate); self._running(False)

    def _failed(self, exc):
        stale = getattr(exc, "code", None) in ("document_conflict", "revision_conflict", "document_epoch_conflict")
        if stale:
            self.candidate = None
            self.quality.setRowCount(0)
            if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})
        self._task = None; self._adopting = self._reviewing = False; self.close_button.setEnabled(True)
        self._invalidate_replacement(); self._running(False)
        if self._closing: super().reject(); return
        if stale: self.summary.setText("The target model changed. Reopen or regenerate the candidate before adoption.")
        elif self.candidate is None: self.summary.setText("No candidate was accepted. The model is unchanged.")
        self._show_error(exc)

    def present_candidate(self, candidate):
        self._invalidate_replacement()
        self._presenting = True
        try: self._present_candidate(candidate)
        finally: self._presenting = False
        self._sync_adoption()

    def _present_candidate(self, candidate):
        from ..application.structured_mesh import StructuredMeshCandidate
        structured = isinstance(candidate, StructuredMeshCandidate)
        if structured and candidate.dimension not in (2, 3):
            self.candidate = None
            self.summary.setText("Unsupported recipe family. Only planar quad4 and sweep hex8 are connected to adoption.")
            self.adopt_button.setEnabled(False)
            return
        self.source_kind.blockSignals(True)
        self.source_kind.setCurrentIndex(self.source_kind.findData("structured_recipe" if structured else "cad_gmsh"))
        self.source_kind.blockSignals(False)
        self._clear_divisions()
        self._source_controls()
        self.candidate = candidate
        self._stamp = self.session.describe()
        self._fill_references()
        physical = [cell for cell in candidate.cells if cell.dimension == candidate.dimension]
        excluded = len(candidate.cells) - len(physical)
        minimum = candidate.quality.minimum(("quad4" if candidate.dimension == 2 else "hex8") if structured else "triangle3" if candidate.dimension == 2 else "tetra4")
        minimum_text = "unavailable" if minimum is None else f"{minimum:.4f}"
        verdict = "Passed" if candidate.quality.passed else "Blocked — inspect flagged elements"
        self.summary.setText(f"{len(candidate.nodes)} nodes · {len(physical)} physical elements · {len([p for p in candidate.parts if p.dimension == candidate.dimension])} parts\n"
                             f"{'Minimum scaled Jacobian' if structured else 'Minimum quality'} {minimum_text} · {verdict}\n{excluded} lower-dimensional cells excluded from adoption. Units: {candidate.length_unit}.")
        self.length.setCurrentIndex(max(0, self.length.findData(candidate.length_unit)))
        self.length.setEnabled(candidate.length_unit == "unknown")
        self.local_entity.clear(); self.local_entity.addItem("No patch selected" if structured else "No local refinement", None)
        for part in candidate.parts: self.local_entity.addItem(f"{part.name} ({part.dimension}D)", part.uuid)
        xao = next((asset.path for asset in candidate.assets if asset.kind == "xao"), None)
        if xao: self.source.setText(xao); self.policy.setCurrentIndex(0)
        if structured:
            from ..application.mesh_candidates import AssetDigest
            source = next((asset for asset in candidate.assets if asset.kind == "source_recipe"),
                          next(asset for asset in candidate.assets if asset.kind == "recipe"))
            self.source.blockSignals(True); self.source.setText(source.path); self.source.blockSignals(False)
            self._set_divisions(json.loads(candidate.recipe_json), AssetDigest("source_recipe", source.path, source.sha256))
            self._source_controls()
        self.dimension.setCurrentIndex(self.dimension.findData(candidate.dimension))
        if structured:
            from ..application.structured_geometry import CONTRACT
            quality = candidate.quality
            quad = candidate.dimension == 2
            self.preview_mode.setCurrentIndex(0)
            self.quality.setHorizontalHeaderLabels(["Scope", "Metric", "Value", "Admission"])
            rows = [("Whole mesh", "Min scaled Jacobian", f"{quality.minimum_scaled_jacobian:.6g}",
                     f">= {CONTRACT['quad_min_corner_signed_scaled_jacobian' if quad else 'hex_min_sampled_scaled_jacobian']}"),
                    ("Whole mesh", "Max edge aspect", f"{quality.maximum_edge_aspect_ratio:.6g}",
                     f"<= {CONTRACT['quad_max_edge_aspect_ratio' if quad else 'hex_max_edge_aspect_ratio']}"),
                    ("Whole mesh", f"Area ({candidate.length_unit}^2)" if quad else f"Volume ({candidate.length_unit}^3)",
                     f"{quality.measure:.8g}", f"Expected {quality.expected_measure:.8g}")]
            self.quality.setRowCount(len(rows))
            for row, values in enumerate(rows):
                for col, value in enumerate(values): self.quality.setItem(row, col, QTableWidgetItem(value))
            self.quality.resizeColumnsToContents()
            self.quality.setToolTip("Whole-candidate metrics, not individual element quality. Patch selection highlights physical elements.")
            self.refresh_preview()
            self._running(False)
            return
        self.quality.setHorizontalHeaderLabels(["Element", "Type", "Quality", "Status"])
        unsupported = candidate.quality.unsupported_ids[:100]
        rows = sorted(candidate.quality.cells, key=lambda item: (item.problem is None, item.q))[:100 - len(unsupported)]
        self.quality.setRowCount(len(rows) + len(unsupported))
        for row, item in enumerate(rows, len(unsupported)):
            for col, value in enumerate((item.element_id, item.kind, f"{item.q:.5g}", item.problem or "OK")):
                self.quality.setItem(row, col, QTableWidgetItem(str(value)))
        for row, identifier in enumerate(unsupported):
            for col, value in enumerate((identifier, "Unsupported", "—", "Unsupported element type")):
                self.quality.setItem(row, col, QTableWidgetItem(str(value)))
        self.quality.resizeColumnsToContents()
        self.quality.setToolTip("Up to 100 worst elements; full inventory is preserved in candidate metadata.")
        self.preview_mode.setEnabled(candidate.dimension == 3)
        if candidate.dimension != 3: self.preview_mode.setCurrentIndex(0)
        self.refresh_preview()
        self.adopt_button.setEnabled(candidate.quality.passed)

    def refresh_preview(self):
        if self.viewport is not None and self.candidate is not None:
            dimension = self.preview_mode.currentData() or self.candidate.dimension
            self.viewport.set_mesh(candidate_projection(self.candidate, dimension=dimension))
            if self._structured() and self.candidate.dimension == 2:
                from ..application.structured_geometry import sub, validate_recipe
                source = validate_recipe(json.loads(self.candidate.recipe_json))
                corners = source["singles"][0]["corners"]
                # An arbitrary isometric direction can be edge-on to an oblique patch.
                self.viewport.orient_view(source["source_normal"], sub(corners[3], corners[0]))

    def _highlight(self, ids):
        if self.viewport is None or self.candidate is None: return
        candidate = self.candidate
        self.viewport.set_selection({"document_id": candidate.mesh_uuid, "document_epoch": candidate.mesh_uuid,
            "projection_revision": 0, "revision": 0, "kind": "element", "ids": ids,
            "resource_revisions": {candidate.geometry_resource_uuid or candidate.mesh_uuid: 0},
            "refs": [{"resource_id": candidate.geometry_resource_uuid or candidate.mesh_uuid, "entity_kind": "element", "local_id": identifier} for identifier in ids]})

    def pick_entity(self, picked):
        candidate = self.candidate
        if candidate is None or picked.get("document_id") != candidate.mesh_uuid: return
        cell = next((cell for cell in candidate.cells if cell.id == picked.get("id")), None)
        if cell is None: return
        self.local_entity.setCurrentIndex(self.local_entity.findData(cell.part_uuid))
        self.highlight_entity()

    def highlight_entity(self):
        if self.candidate is None: return
        identifier = self.local_entity.currentData()
        part = next((part for part in self.candidate.parts if part.uuid == identifier), None)
        if part is None: self._highlight([]); return
        desired = 1 if part.dimension == 2 and self.candidate.dimension == 3 else 0
        if self.preview_mode.currentIndex() != desired: self.preview_mode.setCurrentIndex(desired)
        self._highlight(list(part.element_ids))
        self.pick_hint.setText(f"Selected {part.name} ({part.dimension}D). " +
                              (("Seeds are defined in the recipe." if self.viewport else "3D preview is disabled.")
                               if self._structured() else "Enter a local size, then generate a new candidate."))

    def highlight_quality(self):
        if self.viewport is None or self.candidate is None or self._structured(): return
        ids = [int(self.quality.item(index.row(), 0).text()) for index in self.quality.selectionModel().selectedRows()]
        dimensions = {cell.dimension for cell in self.candidate.cells if cell.id in ids}
        desired = 1 if dimensions == {2} and self.candidate.dimension == 3 else 0
        if self.preview_mode.currentIndex() != desired: self.preview_mode.setCurrentIndex(desired)
        if len(dimensions) > 1:
            self.pick_hint.setText("Select elements from one dimension to highlight them together.")
            self._highlight([]); return
        self._highlight(ids)

    def adopt(self):
        if self._task is not None or self.candidate is None: return False
        try:
            mesh = self.candidate.to_native_mesh(length_unit=self.length.currentData())
            replaced = self._selected_parts()
            material, section = self.material.currentData(), self.section.currentData()
            stamp = dict(self._stamp)
        except Exception as exc: self._show_error(exc); return False
        if replaced:
            if self._replacement_plan is None or not self.replacement_reviewed.isChecked():
                self._show_error("Review the replacement and stale targets before applying it."); return False
            plan = self._replacement_plan
            publish = lambda: self.session.apply_cad_mesh_replacement(plan["plan_id"],
                expected_document_id=plan["document_id"], expected_revision=plan["revision"])
        else:
            publish = lambda: self.session.adopt_mesh_candidate(mesh, material_id=material, property_id=section,
                expected_document_id=stamp["document_id"], expected_revision=stamp["revision"],
                expected_document_epoch=stamp.get("document_epoch"))
        self._adopting = True
        self._start(publish)
        self.cancel_job.setEnabled(False); self.close_button.setEnabled(False)
        self.summary.setText("Validating source assets and adopting the mesh…")
        return True

    def review_replacement(self):
        if self._task is not None or self.candidate is None or not self._selected_parts(): return False
        self._invalidate_replacement()
        try:
            from ..cae_core import PrepError
            current = self.session.describe()
            if any(current[key] != self._stamp[key] for key in ("document_id", "revision", "document_epoch")):
                raise PrepError("document_conflict", "The model changed. Reopen the candidate before reviewing replacement.")
            mesh = self.candidate.to_native_mesh(length_unit=self.length.currentData())
            parts, material, section = self._selected_parts(), self.material.currentData(), self.section.currentData()
        except Exception as exc: self._show_error(exc); return False
        self._reviewing = True; self._task_review_generation = self._review_generation
        return self._start(lambda: self.session.plan_cad_mesh_replacement(mesh,
            replace_part_ids=parts, material_id=material, property_id=section))

    def reject(self):
        if self._adopting: return
        self._invalidate_replacement()
        if self._task is not None:
            self._closing = True; self._cancel.set(); self.cancel_job.setEnabled(False)
            self.error.setText("Stopping the mesh worker…"); return
        super().reject()

    def closeEvent(self, event):
        if self._task is not None: event.ignore(); self.reject()
        else: super().closeEvent(event)


class MeshWorkflow(QObject):
    """Host guard and public entry points shared by all native presentations."""
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.new_action = host._action("project", "New model…", self.new_document, "Ctrl+N", action_id="file.new")
        self.mesh_action = host._action("mesh", "CAD / mesh candidate…", self.mesh, action_id="mesh.candidate")
        self.features_action = host._action("mesh", "Inspect geometry features…", self.geometry_features,
                                            action_id="mesh.geometry_features")
        self.export_action = host._action("export", "Export Starter and Engine…", self.export, action_id="file.export_solver")
        self.cases_action = host._action("card", "Analysis cases…", self.cases, action_id="model.analysis_cases")
        self.dialog = None

    def geometry_features(self):
        if self.host._busy: return
        from .geometry_features import GeometryFeaturesDialog
        self.dialog = GeometryFeaturesDialog(self.host, enable_viewport=self.host.viewport is not None)
        self.dialog.exec()

    def cases(self):
        if self.host._busy or not self.host._finish_pending_edits(): return
        if not self.host.session.describe().get("document_id"): return
        from .analysis_cases import AnalysisCasesDialog
        self.dialog = AnalysisCasesDialog(self.host.session, self.host)
        self.dialog.exec()
        self.host.refresh_document()

    def new_document(self):
        if self.host._busy: return
        def create():
            self.dialog = NewDocumentDialog(self.host.session, self.host)
            if self.dialog.exec(): self.host.refresh_document(rebuild_viewport=True)
        self.host._before_replace(create)

    def mesh(self):
        if self.host._busy or not self.host._finish_pending_edits(): return
        if not self.host.session.describe().get("document_id"):
            self.host.statusBar().showMessage("Create or open a model, then create its material and section first."); return
        self.dialog = MeshCandidateDialog(self.host.session, self.host, enable_viewport=self.host.viewport is not None)
        if self.dialog.exec():
            self.host.refresh_document(rebuild_viewport=True)
            if self.dialog.result and self.dialog.result.get("mesh_relationships", {}).get("stale_targets"):
                dialog = self.host.open_prepared_mesh()
                if dialog is not None: dialog.tabs.setCurrentIndex(1)

    def export(self):
        if self.host._busy or not self.host._finish_pending_edits(): return
        self.dialog = SolverExportDialog(self.host.session, self.host)
        if self.dialog.exec():
            result = self.dialog.result
            self.host.statusBar().showMessage(f"Exported {result['starter_path']} and {result['engine_path']}")
