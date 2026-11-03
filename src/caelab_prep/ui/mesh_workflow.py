"""Candidate review and adoption UI; the session owns every model mutation."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import json
import threading

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from .shell import FileTask
from .widgets.numeric import NumericEdit


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
        self._stamp = session.describe()
        self.setWindowTitle("Mesh — review candidate")
        self._seed_recipe = None
        self._seed_source = None
        self.division_edits = []
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
        self.source = QLineEdit(); self.output = QLineEdit()
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
        self.load_divisions_button = QPushButton("Load quad divisions")
        self.load_divisions_button.clicked.connect(self.load_divisions)
        form.addRow(self.load_divisions_button)
        self.divisions = QTableWidget(0, 3)
        self.divisions.setHorizontalHeaderLabels(["Patch", "Edge 1–2", "Edge 2–3"])
        self.divisions.verticalHeader().hide()
        self.divisions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.divisions.setMaximumHeight(125)
        self.divisions.setToolTip("Segment counts along the patch's ordered corner edges, not global X/Y. Shared edges must agree.")
        form.addRow("Quad divisions", self.divisions)
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
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel); split.addWidget(scroll)
        split.setSizes([620, 480])
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setObjectName("inputError"); layout.addWidget(self.error)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.adopt_button = QPushButton("Adopt candidate"); self.adopt_button.setObjectName("primaryAction"); self.adopt_button.setEnabled(False)
        self.close_button = QPushButton("Close")
        self.adopt_button.clicked.connect(self.adopt); self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.adopt_button); buttons.addWidget(self.close_button); layout.addLayout(buttons)
        self.source_kind.currentIndexChanged.connect(self._source_changed)
        self.source.textChanged.connect(self._recipe_source_changed)
        self._source_controls()

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
        self.divisions.setVisible(structured and self._seed_recipe is not None)
        self.form.labelForField(self.divisions).setVisible(structured and self._seed_recipe is not None)
        self.pick_hint.setText(("Planar quad4 / sweep hex8. Load quad divisions to edit segment counts; units and geometry stay in the recipe. " +
                               ("Preview does not change the model." if self.viewport else "3D preview is disabled."))
                               if structured else "Click the preview to select an entity for local refinement.")
        self.quality.setSelectionMode(QTableWidget.SelectionMode.NoSelection if structured else QTableWidget.SelectionMode.ExtendedSelection)

    def _source_changed(self):
        self.source.clear(); self._clear_divisions()
        self._invalidate_candidate()
        self._source_controls()

    def _invalidate_candidate(self):
        self.candidate = None
        self.error.clear(); self.quality.setRowCount(0)
        self.summary.setText("No candidate. Generation does not change the model.")
        self.local_entity.clear(); self.local_entity.addItem("No patch selected" if self._structured() else "No local refinement", None)
        if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})
        self._running(False)

    def _clear_divisions(self):
        self._seed_recipe = self._seed_source = None
        self.division_edits = []
        self.divisions.setRowCount(0)

    def _recipe_source_changed(self):
        if self._structured():
            self._clear_divisions(); self._invalidate_candidate(); self._source_controls()

    def _set_divisions(self, recipe, source):
        self._clear_divisions()
        if recipe.get("mode") != "quad": return
        self._seed_recipe = deepcopy(recipe); self._seed_source = source
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
        self.summary.setText("Divisions changed. Generate a new candidate to check quality before adoption.")

    def load_divisions(self):
        from ..application.structured_mesh import read_recipe_input
        from ..application.structured_geometry import validate_recipe
        self._clear_divisions(); self._invalidate_candidate()
        try:
            recipe, source = read_recipe_input(self.source.text())
            validate_recipe(recipe)
            if recipe.get("mode") != "quad":
                raise ValueError("Division editing supports planar quad recipes. Edit sweep hex values in the JSON file.")
            self._set_divisions(recipe, source)
        except Exception as exc:
            self._show_error(exc); self._source_controls(); return False
        self._source_controls(); return True

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
        for widget in (*self._browse_buttons, self.source_kind, self.generate_button, self.open_button, self.source, self.output, self.size, self.dimension, self.policy, self.local_entity, self.local_size,
                       self.material, self.section, self.replace, self.preview_mode, self.quality, self.load_divisions_button, self.divisions): widget.setEnabled(not value)
        self.length.setEnabled(not value and bool(self.candidate and self.candidate.length_unit == "unknown"))
        self.preview_mode.setEnabled(not value and bool(self.candidate and self.candidate.dimension == 3))
        self.cancel_job.setEnabled(value)
        self.adopt_button.setEnabled(not value and self.candidate is not None and self.candidate.quality.passed)
        if self._structured():
            for widget in (self.size, self.dimension, self.policy, self.local_size, self.length, self.replace, self.preview_mode):
                widget.setEnabled(False)

    def _start(self, function):
        if self._task is not None: return False
        if not self._adopting:
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
        if self._structured():
            source, output = self.source.text(), self.output.text()
            recipe, origin = None, self._seed_source
            if self._seed_recipe is not None:
                from ..application.structured_geometry import validate_recipe
                recipe = deepcopy(self._seed_recipe)
                try:
                    for patch, edits in zip(recipe.get("patches", [recipe]), self.division_edits):
                        patch["divisions"] = [edit.numeric_value() for edit in edits]
                    validate_recipe(recipe)
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
        if self._closing: super().reject(); return
        if self._cancel.is_set(): self._running(False); self.summary.setText("Generation cancelled. The model is unchanged."); return
        self.present_candidate(candidate); self._running(False)

    def _failed(self, exc):
        stale = getattr(exc, "code", None) in ("document_conflict", "revision_conflict", "document_epoch_conflict")
        if stale:
            self.candidate = None
            self.quality.setRowCount(0)
            if self.viewport: self.viewport.set_mesh({"points": [], "node_ids": [], "cells": []})
        self._task = None; self._adopting = False; self.close_button.setEnabled(True); self._running(False)
        if self._closing: super().reject(); return
        if stale: self.summary.setText("The target model changed. Reopen or regenerate the candidate before adoption.")
        elif self.candidate is None: self.summary.setText("No candidate was accepted. The model is unchanged.")
        self._show_error(exc)

    def present_candidate(self, candidate):
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
            replaced = [self.replace.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.replace.count())
                        if not self._structured() and self.replace.item(row).checkState() == Qt.CheckState.Checked]
            material, section = self.material.currentData(), self.section.currentData()
            stamp = dict(self._stamp)
        except Exception as exc: self._show_error(exc); return False
        self._adopting = True
        self._start(lambda: self.session.adopt_mesh_candidate(mesh, material_id=material, property_id=section,
            replace_part_ids=replaced or None, expected_document_id=stamp["document_id"], expected_revision=stamp["revision"],
            expected_document_epoch=stamp.get("document_epoch")))
        self.cancel_job.setEnabled(False); self.close_button.setEnabled(False)
        self.summary.setText("Validating source assets and adopting the mesh…")
        return True

    def reject(self):
        if self._adopting: return
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
        if self.dialog.exec(): self.host.refresh_document(rebuild_viewport=True)

    def export(self):
        if self.host._busy or not self.host._finish_pending_edits(): return
        self.dialog = SolverExportDialog(self.host.session, self.host)
        if self.dialog.exec():
            result = self.dialog.result
            self.host.statusBar().showMessage(f"Exported {result['starter_path']} and {result['engine_path']}")
