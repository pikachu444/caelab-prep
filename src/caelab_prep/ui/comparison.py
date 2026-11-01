"""Interactive program-by-program views sharing one real document and history."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QMainWindow,
                              QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout,
                              QWidget)

from .reference_profiles import PROFILES


class ComparisonWindow(QMainWindow):
    def __init__(self, session=None, *, native=False, enable_viewport=True):
        super().__init__()
        if session is None:
            from ..application.neutral import CurveSession
            session = CurveSession()
        self.session = session
        self.native = native
        self.enable_viewport = enable_viewport
        self.views = {}
        self._active_key = None
        self._allow_close = False
        self.setWindowTitle("CAELab Prep — Program UI comparison")
        self.resize(1360, 900)
        self.setMinimumSize(960, 680)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 8, 4)
        bar.addWidget(QLabel("Program approach"))
        self.selector = QComboBox()
        self.selector.setAccessibleName("Program UI approach")
        for key, spec in PROFILES.items():
            self.selector.addItem(spec.name + " — " + spec.version, key)
        bar.addWidget(self.selector)
        self.document_state = QLabel()
        bar.addWidget(self.document_state, 1)
        evidence = QPushButton("Reference / differences")
        evidence.clicked.connect(self.show_evidence)
        bar.addWidget(evidence)
        layout.addLayout(bar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(body)
        self.selector.currentIndexChanged.connect(self._selected)
        self.select_profile(next(iter(PROFILES)))

    @property
    def active_view(self):
        return self.views.get(self._active_key)

    def _selected(self, index):
        self.select_profile(self.selector.itemData(index))

    def select_profile(self, key):
        if key not in PROFILES:
            raise ValueError("Unknown UI reference: " + str(key))
        if key == self._active_key:
            return True
        current = self.active_view
        if current is not None:
            finish = current._finish_pending_edits if self.native else current._finish_drafts
            if current._busy or not finish():
                self.selector.blockSignals(True)
                self.selector.setCurrentIndex(self.selector.findData(self._active_key))
                self.selector.blockSignals(False)
                self.document_state.setText("Draft retained — correct or revert before changing approach")
                return False
            dialog = getattr(current, "property_dialog", None)
            if dialog is not None:
                dialog.hide()
        if key not in self.views:
            selected = self.session.active_object()
            if self.native:
                from .main_window import MainWindow
                view = MainWindow(self.session, presentation=key, enable_viewport=self.enable_viewport)
            else:
                from .gallery import GalleryWindow
                view = GalleryWindow(self.session, presentation=key)
            view.setWindowFlags(Qt.WindowType.Widget)
            view.close_action.triggered.disconnect()
            view.close_action.triggered.connect(self.close)
            self.stack.addWidget(view)
            self.views[key] = view
            if selected is not None:
                view.select_card(selected.object_id) if self.native else view.select_ref(selected)
            elif not self.native:
                self.session.select(None)
                view._pending_selection = True
                view._consume_pending_selection()
        else:
            selected = self.session.active_object()
            view = self.views[key]
            if self.native:
                view.refresh_document()
                if selected is not None:
                    view.select_card(selected.object_id)
            else:
                view.reload_values()
                if selected is not None:
                    view.select_ref(selected)
                else:
                    view._pending_selection = True
                    view._consume_pending_selection()
        self._active_key = key
        self.stack.setCurrentWidget(self.views[key])
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.selector.findData(key))
        self.selector.blockSignals(False)
        self.document_state.setText("Same RAD document / Undo history" if self.native else "Same material / curves / Undo history")
        return True

    def show_evidence(self):
        spec = PROFILES[self._active_key]
        dialog = QDialog(self)
        dialog.setWindowTitle("Reference coverage — " + spec.name)
        dialog.resize(680, 400)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        source = ("official PrePoMax 2.5.0 manual, pp3, 5, 7, 27–29" if self._active_key == "prepomax"
                  else "docs/benchmarks/2026-10-30/products/" + self._active_key + ".json")
        text.setPlainText(spec.name + " / " + spec.version + "\n\n" + spec.differences
                          + "\n\nSource scenes: " + ", ".join(spec.scenes) + "\nSource: " + source)
        layout.addWidget(text)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def closeEvent(self, event):
        current = self.active_view
        if current is not None and current._busy:
            self.document_state.setText("Wait for the file operation to finish")
            event.ignore()
            return
        if not self._allow_close and current is not None:
            deciding = True
            def finish():
                self._allow_close = True
                if not deciding:
                    self.close()
            proceed = current.file_edits.guard(finish)
            deciding = False
            if not proceed:
                event.ignore()
                return
        for view in self.views.values():
            view._allow_close = True
            view.close()
        event.accept()
