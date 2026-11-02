"""One analysis-case editor shared by all presentation profiles."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QListWidget,
    QListWidgetItem, QLineEdit, QComboBox, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QSplitter, QWidget)

from ..cae_core import PrepError


class AnalysisCasesDialog(QDialog):
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Analysis cases")
        self.setObjectName("analysisCasesDialog")
        self.resize(920, 600)
        self._loading = self._committing = self._dirty = False
        self._case_id = None
        self._epoch = None
        layout = QVBoxLayout(self)
        scope = QLabel("Each case stores its active conditions and run times. Conditions and their target groups remain shared by the model.\n"
                       "Supported activation: boundary constraints, nodal loads, initial translation velocity and TYPE7 contact.")
        scope.setWordWrap(True)
        layout.addWidget(scope)
        split = QSplitter()
        left = QWidget(); left_layout = QVBoxLayout(left)
        self.case_list = QListWidget(); self.case_list.setObjectName("analysisCaseList")
        left_layout.addWidget(self.case_list)
        row = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.copy_button = QPushButton("Copy")
        self.delete_button = QPushButton("Delete")
        for button in (self.new_button, self.copy_button, self.delete_button): row.addWidget(button)
        left_layout.addLayout(row)
        split.addWidget(left)
        right = QWidget(); right_layout = QVBoxLayout(right)
        form = QFormLayout()
        self.name_edit = QLineEdit(); self.name_edit.setObjectName("analysisCaseName")
        self.end_edit = QLineEdit(); self.end_edit.setObjectName("analysisCaseEndTime")
        self.interval_edit = QLineEdit(); self.interval_edit.setObjectName("analysisCaseOutputInterval")
        self.unit_combo = QComboBox(); self.unit_combo.addItems(["s", "ms", "mus"])
        form.addRow("Case name", self.name_edit)
        form.addRow("End time", self.end_edit)
        form.addRow("Output interval", self.interval_edit)
        form.addRow("Time unit", self.unit_combo)
        right_layout.addLayout(form)
        right_layout.addWidget(QLabel("Active conditions — unchecked conditions are excluded from this case’s output"))
        self.conditions = QTableWidget(0, 3)
        self.conditions.setObjectName("analysisCaseConditions")
        self.conditions.setHorizontalHeaderLabels(["Active / condition", "Kind", "Target"])
        self.conditions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.conditions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.conditions, 1)
        self.apply_button = QPushButton("Create case")
        self.apply_button.setObjectName("analysisCaseApply")
        right_layout.addWidget(self.apply_button)
        split.addWidget(right); split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setObjectName("analysisCaseStatus")
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.use_button = QPushButton("Use this case")
        self.export_button = QPushButton("Export this case…")
        self.reload_button = QPushButton("Reload")
        close = QPushButton("Close")
        for button in (self.use_button, self.export_button, self.reload_button): actions.addWidget(button)
        actions.addStretch(); actions.addWidget(close); layout.addLayout(actions)
        self.case_list.currentItemChanged.connect(self._choose)
        self.new_button.clicked.connect(self._new)
        self.copy_button.clicked.connect(self._copy)
        self.delete_button.clicked.connect(self._delete)
        self.apply_button.clicked.connect(self._apply)
        self.use_button.clicked.connect(self._use)
        self.export_button.clicked.connect(self._export)
        self.reload_button.clicked.connect(self._reload)
        close.clicked.connect(self.reject)
        for edit in (self.name_edit, self.end_edit, self.interval_edit): edit.textChanged.connect(self._edited)
        self.unit_combo.currentTextChanged.connect(self._edited)
        self.conditions.itemChanged.connect(self._edited)
        self.sessionEvent.connect(self._changed)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(lambda _: self._unsubscribe())
        self.refresh()

    def _edited(self, *_):
        if not self._loading: self._dirty = True

    def _guards(self):
        return {"expected_revision": self._revision, "expected_document_id": self._document_id}

    def _discard(self):
        return not self._dirty or QMessageBox.question(self, "Unapplied changes", "Discard unapplied case changes?") == QMessageBox.StandardButton.Yes

    def refresh(self, case_id=None):
        """Reload from the shared session. Call after external document commands."""
        state = self.session.analysis_cases()
        self._document_id, self._revision = state["document_id"], state["revision"]
        self._epoch = self.session.describe()["document_epoch"]
        self._loading = True
        self.case_list.clear()
        target = case_id or state["active_case_id"]
        selected = None
        for case in state["cases"]:
            item = QListWidgetItem(case["name"] + ("  • active" if case["id"] == state["active_case_id"] else ""))
            item.setData(Qt.ItemDataRole.UserRole, case["id"])
            self.case_list.addItem(item)
            if case["id"] == target: selected = item
        self.case_list.setCurrentItem(selected)
        self._loading = False
        self._load(target if selected else None)

    def _load(self, case_id):
        self._loading = True
        self._case_id = case_id
        state = self.session.analysis_cases()
        self._document_id, self._revision = state["document_id"], state["revision"]
        case = self.session.analysis_case(case_id) if case_id else {"name": "", "end_time": "", "output_interval": "", "time_unit": "s", "condition_ids": []}
        self.name_edit.setText(case["name"])
        self.end_edit.setText(str(case["end_time"]))
        self.interval_edit.setText(str(case["output_interval"]))
        self.unit_combo.setCurrentText(case["time_unit"])
        cards = {item["id"]: item for item in self.session.list_cards()}
        conditions = self.session.analysis_case_conditions()
        self.conditions.setRowCount(len(conditions))
        for row, condition in enumerate(conditions):
            item = QTableWidgetItem(condition["title"] or condition["keyword"])
            item.setData(Qt.ItemDataRole.UserRole, condition["id"])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if condition["id"] in case["condition_ids"] else Qt.CheckState.Unchecked)
            self.conditions.setItem(row, 0, item)
            values = condition["values"]
            targets = []
            for key, label in (("group_id", "Nodes"), ("secondary_group_id", "Secondary"), ("main_surface_id", "Main")):
                if key in values:
                    target = cards.get(values[key], {})
                    targets.append(label + ": " + (target.get("title") or "Unresolved"))
            if values.get("diagnostics"): targets.append("Invalid target — repair in model")
            for column, text in ((1, condition["condition_kind"]), (2, "; ".join(targets))):
                cell = QTableWidgetItem(text); cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.conditions.setItem(row, column, cell)
        self.apply_button.setText("Apply case" if case_id else "Create case")
        for button in (self.copy_button, self.delete_button, self.use_button, self.export_button): button.setEnabled(bool(case_id))
        self.status.setText("Selected for export: " + (self.session.analysis_case()["name"] if state["active_case_id"] else "none"))
        self._dirty = self._loading = False

    def _choose(self, current, previous):
        if self._loading: return
        if not self._discard():
            self._loading = True; self.case_list.setCurrentItem(previous); self._loading = False
            return
        self._load(current.data(Qt.ItemDataRole.UserRole) if current else None)

    def _new(self):
        if self._discard():
            self._loading = True; self.case_list.setCurrentRow(-1); self._loading = False
            self._load(None); self.name_edit.setFocus()

    def _execute(self, operation):
        try:
            self._committing = True
            result = operation()
            self.refresh(result.get("case_id"))
            return result
        except (PrepError, ValueError) as exc:
            self.status.setText(str(exc)); return None
        finally:
            self._committing = False

    def _apply(self):
        def operation():
            values = dict(name=self.name_edit.text(), end_time=float(self.end_edit.text()),
                          output_interval=float(self.interval_edit.text()), time_unit=self.unit_combo.currentText(),
                          condition_ids=[self.conditions.item(row, 0).data(Qt.ItemDataRole.UserRole)
                            for row in range(self.conditions.rowCount()) if self.conditions.item(row, 0).checkState() == Qt.CheckState.Checked])
            if self._case_id: return self.session.set_analysis_case(self._case_id, values, **self._guards())
            return self.session.create_analysis_case(**values, **self._guards())
        self._execute(operation)

    def _copy(self):
        if self._discard(): self._execute(lambda: self.session.copy_analysis_case(self._case_id, **self._guards()))

    def _delete(self):
        if self._discard() and QMessageBox.question(self, "Delete case", "Delete this analysis case? Model conditions remain available.") == QMessageBox.StandardButton.Yes:
            self._execute(lambda: self.session.delete_analysis_case(self._case_id, **self._guards()))

    def _use(self):
        if self._dirty:
            self.status.setText("Apply case changes before selecting this case for export."); return
        self._execute(lambda: self.session.select_analysis_case(self._case_id, **self._guards()))

    def _export(self):
        if self._dirty:
            self.status.setText("Apply case changes before exporting."); return
        try:
            epoch, document_id, revision, case_id = self._epoch, self._document_id, self._revision, self._case_id
            if self.session.describe()["document_epoch"] != epoch or self.session.describe()["revision"] != revision:
                raise PrepError("revision_conflict", "The model changed. Reload the case before exporting.")
            self.session.validate_analysis_case(case_id)
            path, _ = QFileDialog.getSaveFileName(self, "Export case Starter and Engine", "case_0000.rad", "Radioss Starter (*_0000.rad)")
            if path:
                if self.session.describe()["document_epoch"] != epoch:
                    raise PrepError("document_conflict", "The document changed. Reload the case before exporting.")
                result = self.session.export_analysis_case(path, case_id,
                    expected_document_id=document_id, expected_revision=revision)
                self.status.setText("Exported " + result["analysis_case"]["name"] + ": " + result["starter_path"])
        except PrepError as exc: self.status.setText(str(exc))

    def _reload(self):
        if self._discard(): self.refresh(self._case_id)

    def _changed(self, _event):
        if self._committing: return
        if self.session.describe()["document_epoch"] != self._epoch:
            self.status.setText("The document changed. Close this editor and reopen analysis cases.")
            self.case_list.setEnabled(False)
            for widget in (self.name_edit, self.end_edit, self.interval_edit, self.unit_combo, self.conditions): widget.setEnabled(False)
            for button in (self.apply_button, self.copy_button, self.delete_button, self.use_button, self.export_button, self.reload_button, self.new_button): button.setEnabled(False)
        elif self._dirty:
            self.status.setText("The model changed while this draft was open. Reload before applying.")
        else: self.refresh(self._case_id)

    def reject(self):
        if self._discard(): super().reject()
