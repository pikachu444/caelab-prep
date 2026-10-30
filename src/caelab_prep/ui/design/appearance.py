"""Small, application-independent visual assets for the native desktop shell."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_PATHS = {
    "open": '<path d="M2.5 6.5h6l2-2h4.5v4M2.5 6.5v12h17l2-10h-17l-2 10"/>',
    "project": '<path d="M3 5h6l2 2h10v13H3z"/><path d="M7 12h10M7 16h7"/>',
    "save": '<path d="M4 3h14l3 3v15H3V3z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
    "export": '<path d="M13 4H4v17h16v-8M13 3h8v8M10 14 21 3"/>',
    "undo": '<path d="M8 5 3 10l5 5M3 10h11a6 6 0 0 1 0 12"/>',
    "redo": '<path d="m16 5 5 5-5 5M21 10H10a6 6 0 0 0 0 12"/>',
    "fit": '<path d="M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6"/><rect x="8" y="8" width="8" height="8"/>',
    "iso": '<path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10"/>',
    "edges": '<path d="M4 4h16v16H4zM4 4l16 16M20 4 4 20M4 12h16M12 4v16"/>',
    "material": '<path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9"/>',
    "constraint": '<path d="M4 5h16M6 5v8M12 5v8M18 5v8M4 13h16M5 14l-3 4M10 14l-3 4M15 14l-3 4M20 14l-3 4"/>',
    "card": '<path d="M6 3h9l4 4v14H6zM15 3v5h4M9 12h7M9 16h7"/>',
    "curve": '<path d="M4 3v17h17M6 17l4-6 4 2 6-8"/><circle cx="10" cy="11" r="1"/><circle cx="14" cy="13" r="1"/>',
    "vector": '<path d="M5 20V5m0 15h15M5 20 18 7M14 7h4v4"/>',
    "warning": '<path d="m12 3 10 18H2zM12 9v5M12 17v1"/>',
    "apply": '<path d="m4 12 5 5L21 5"/>',
    "mesh": '<path d="m3 19 9-16 9 16zM7 12h10M7 12l5 7 5-7M12 3v16"/>',
    "part": '<path d="m3 7 9-4 9 4v11l-9 4-9-4zM3 7l9 4 9-4M12 11v11"/>',
}


def icon(name: str) -> QIcon:
    """Draw original, consistently sized line icons, without bundled vendor art."""
    body = _PATHS.get(name, _PATHS["card"])
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24"><g fill="none" stroke="#40556a" '
        'stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">'
        + body + "</g></svg>"
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(source.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)


STYLESHEET = """
QMainWindow { background: #e7ebef; }
QWidget { color: #25313d; font-family: 'Segoe UI', 'Malgun Gothic', 'Noto Sans CJK KR', sans-serif; font-size: 12px; }
QMenuBar { background: #ffffff; border-bottom: 1px solid #d5dce3; padding: 3px 7px; }
QMenuBar::item { padding: 5px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background: #e3effa; color: #174b75; }
QMenu { background: #ffffff; border: 1px solid #cbd4dd; padding: 5px; }
QMenu::item { padding: 6px 27px 6px 20px; }
QToolBar { background: #f8fafc; border: none; border-bottom: 1px solid #d2dae2; spacing: 4px; padding: 5px 8px; }
QToolButton { border: 1px solid transparent; border-radius: 3px; padding: 5px; }
QToolButton:hover { background: #e7eff7; border-color: #c3d6e7; }
QToolButton:checked { background: #dcebf8; border-color: #acc9e2; }
QDockWidget { font-weight: 600; }
QDockWidget::title { background: #edf1f5; padding: 7px 9px; border-bottom: 1px solid #d5dde5; }
QTreeView, QTableView { background: #ffffff; border: none; alternate-background-color: #f8fafb; selection-background-color: #dcecf9; selection-color: #164d78; }
QTreeView::item { min-height: 24px; padding: 1px 3px; }
QTreeView::item:selected { background: #dcecf9; color: #164d78; }
QTreeView:focus, QTableView:focus { border: 1px solid #3788c4; }
QHeaderView::section { background: #f2f5f8; border: none; border-bottom: 1px solid #dbe2e8; padding: 6px; font-weight: 500; }
QScrollArea { border: none; background: #ffffff; }
QLineEdit, QComboBox { background: #ffffff; border: 1px solid #cbd4dd; border-radius: 3px; padding: 3px 5px; min-height: 19px; }
QLineEdit:focus, QComboBox:focus { border-color: #3788c4; }
QLineEdit:disabled { background: #f2f5f7; color: #6d7884; }
QPushButton { background: #f4f7fa; border: 1px solid #c4cfda; border-radius: 3px; padding: 6px 12px; }
QPushButton:hover { background: #e7f0f8; border-color: #9abbd7; }
QCheckBox { spacing: 7px; padding: 3px 0; }
QStatusBar { background: #f8fafc; border-top: 1px solid #d4dce4; }
QStatusBar::item { border: none; }
QLabel#propertyTitle { font-size: 15px; font-weight: 600; color: #243c52; }
QLabel#propertySubtitle, QLabel#unitsNote { color: #677582; }
QLabel#viewportHint { color: #6a7885; background: transparent; font-size: 15px; }
QLabel#groupTitle { font-weight: 600; color: #324d60; }
QLabel#inputError { color: #a42e2e; }
QLineEdit[invalid="true"] { border: 1px solid #b23838; background: #fff5f3; }
QPushButton#primaryAction { background: #217a90; border-color: #217a90; color: #ffffff; }
QPushButton#primaryAction:hover { background: #1b6679; }
QPushButton:pressed, QToolButton:pressed { background: #d8e6f0; }
QPushButton:focus, QToolButton:focus { border: 1px solid #3788c4; }
QPushButton:disabled, QToolButton:disabled { background: #f0f3f5; color: #818b94; border-color: #dce2e7; }
QPushButton#primaryAction:disabled { background: #e1e7ea; color: #7a8790; border-color: #d4dde3; }
QFrame#viewportFrame { background: #ffffff; border: 1px solid #d2dae2; }
QFrame#viewportBar { background: #f4f7f9; border-bottom: 1px solid #d5dde5; }
"""
