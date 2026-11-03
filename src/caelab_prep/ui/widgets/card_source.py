"""Explicit source-edit lifetime, independent of any solver or document model."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class CardSourceEditor(QWidget):
    editRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = QPlainTextEdit()
        self.editor.setAccessibleName("Selected card source")
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("cardSourceMessage")
        self.edit_button = QPushButton("Edit supported values")
        self.apply_button = QPushButton("Apply TEXT")
        self.cancel_button = QPushButton("Cancel TEXT")
        self.edit_button.clicked.connect(self.editRequested)
        self.apply_button.clicked.connect(self.applyRequested)
        self.cancel_button.clicked.connect(self.cancelRequested)
        buttons = QHBoxLayout()
        buttons.addWidget(self.edit_button)
        buttons.addStretch()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.message)
        layout.addLayout(buttons)
        self.present("", available=False)

    def present(self, text, *, available):
        self.editor.setReadOnly(True)
        self.editor.setPlainText(text)
        self.edit_button.setVisible(True)
        self.edit_button.setEnabled(available)
        self.apply_button.hide()
        self.cancel_button.hide()
        self.message.setText("Edit supported fixed-width values in the input deck units. Headers, IDs and other source remain preserved."
                             if available else "This card is preserved read-only.")

    def begin(self, text):
        self.editor.setPlainText(text)
        self.editor.setReadOnly(False)
        self.edit_button.hide()
        self.apply_button.show()
        self.cancel_button.show()
        self.message.setText("Apply or cancel TEXT before editing FORM. Keep the existing field widths and card structure.")
        self.editor.setFocus()

    def show_error(self, message):
        self.message.setText(str(message))
