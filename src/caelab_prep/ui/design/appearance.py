"""Small, application-independent visual assets for the native desktop shell."""

from string import Template

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .tokens import TOKENS


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
    "section": '<path d="M4 3h16v4h-6v10h6v4H4v-4h6V7H4z"/>',
    "load": '<path d="M4 20h16M7 3v12m-3-3 3 3 3-3M17 3v12m-3-3 3 3 3-3"/>',
    "contact": '<path d="M3 5h7v14H3M21 5h-7v14h7M10 9l4 3-4 3"/>',
    "set": '<path d="M7 3H3v18h4M17 3h4v18h-4"/><circle cx="9" cy="8" r="1"/><circle cx="15" cy="8" r="1"/><circle cx="9" cy="16" r="1"/><circle cx="15" cy="16" r="1"/>',
    "select": '<path d="m5 3 14 10-7 1-3 7zM14 14l5 6"/>',
    "result": '<path d="M3 3v18h18M7 17v-5h3v5M12 17V8h3v9M17 17V4h3v13"/>',
    "job": '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M7 2v4M17 2v4M3 9h18m-12 3 5 3-5 3z"/>',
}

ICON_PURPOSES = {
    "open": "Open an existing document", "project": "Work document or project",
    "save": "Save the current document", "export": "Write a separate exchange or native file",
    "undo": "Undo one committed command", "redo": "Redo one committed command",
    "fit": "Fit the view to its contents", "iso": "Isometric view",
    "edges": "Display mesh edges", "material": "Material object",
    "constraint": "Prescribed or constrained degrees of freedom", "card": "Generic document record",
    "curve": "Curve data and plot", "vector": "Vector quantity or direction",
    "warning": "Warning requiring attention", "apply": "Apply a validated draft",
    "mesh": "Mesh resource", "part": "Geometry or part object", "section": "Section property",
    "load": "Applied load", "contact": "Contact relationship", "set": "Entity set",
    "select": "Select an object or entity", "result": "Result quantity", "job": "Operation or job",
}


def icon(name: str) -> QIcon:
    """Draw original, consistently sized line icons, without bundled vendor art."""
    body = _PATHS.get(name, _PATHS["card"])
    source = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TOKENS["icon_canvas"]}" height="{TOKENS["icon_canvas"]}" '
        f'viewBox="0 0 24 24"><g fill="none" stroke="{TOKENS["icon_stroke"]}" '
        f'stroke-width="{TOKENS["icon_stroke_width"]}" stroke-linecap="round" stroke-linejoin="round">'
        + body + "</g></svg>"
    )
    pixmap = QPixmap(TOKENS["icon_render_size"], TOKENS["icon_render_size"])
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(source.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)


STYLESHEET = Template("""
QMainWindow { background: $workspace; }
QWidget { color: $text; font-family: $font_family; font-size: ${font_size}px; }
QMenuBar { background: $surface; border-bottom: ${border_width}px solid $divider; padding: ${menu_bar_pad_y}px ${menu_bar_pad_x}px; }
QMenuBar::item { padding: ${menu_item_pad_y}px ${menu_item_pad_x}px; }
QMenuBar::item:selected, QMenu::item:selected { background: $hover; color: $selection_text; }
QMenu { background: $surface; border: ${border_width}px solid $border; padding: ${menu_pad}px; }
QMenu::item { padding: ${menu_popup_pad_y}px ${menu_popup_pad_right}px ${menu_popup_pad_y}px ${menu_popup_pad_left}px; }
QToolBar { background: $subtle; border: none; border-bottom: ${border_width}px solid $divider; spacing: ${space_sm}px; padding: ${toolbar_pad_y}px ${toolbar_pad_x}px; }
QToolButton { border: ${border_width}px solid transparent; border-radius: ${radius}px; padding: ${toolbutton_pad}px; }
QToolButton:hover { background: $hover; border-color: $hover_border; }
QToolButton:checked { background: $checked; border-color: $checked_border; }
QDockWidget { font-weight: $heading_weight; }
QDockWidget::title { background: $raised; padding: ${dock_pad_y}px ${dock_pad_x}px; border-bottom: ${border_width}px solid $divider; }
QTreeView, QTableView { background: $surface; border: none; alternate-background-color: $alternate; selection-background-color: $selection; selection-color: $selection_text; }
QTreeView::item { min-height: ${tree_row_height}px; padding: ${tree_pad_y}px ${tree_pad_x}px; }
QTreeView::item:selected { background: $selection; color: $selection_text; }
QTreeView:focus, QTableView:focus { border: ${border_width}px solid $focus; }
QHeaderView::section { background: $raised; border: none; border-bottom: ${border_width}px solid $divider; padding: ${space_md}px; font-weight: $header_weight; }
QScrollArea { border: none; background: $surface; }
QLineEdit, QComboBox { background: $surface; border: ${border_width}px solid $border; border-radius: ${radius}px; padding: ${control_pad_y}px ${control_pad_x}px; min-height: ${control_min_height}px; }
QLineEdit:focus, QComboBox:focus { border-color: $focus; }
QLineEdit:disabled, QComboBox:disabled { background: $raised; color: $disabled_text; }
QPushButton { background: $button; border: ${border_width}px solid $button_border; border-radius: ${radius}px; padding: ${button_pad_y}px ${button_pad_x}px; }
QPushButton:hover { background: $hover; border-color: $button_hover_border; }
QCheckBox { spacing: ${checkbox_spacing}px; padding: ${checkbox_pad_y}px 0; }
QStatusBar { background: $subtle; border-top: ${border_width}px solid $divider; }
QStatusBar::item { border: none; }
QLabel#propertyTitle { font-size: ${title_size}px; font-weight: $heading_weight; color: $heading; }
QLabel#propertySubtitle, QLabel#unitsNote { color: $muted; }
QLabel#viewportHint { color: $muted; background: transparent; font-size: ${title_size}px; }
QLabel#groupTitle { font-weight: $heading_weight; color: $group_heading; }
QLabel#inputError { color: $error; }
QLineEdit[invalid="true"] { border: ${border_width}px solid $error; background: $error_surface; }
QPushButton#primaryAction { background: $accent; border-color: $accent; color: $surface; }
QPushButton#primaryAction:hover { background: $accent_hover; }
QPushButton:pressed, QToolButton:pressed { background: $pressed; }
QPushButton:focus, QToolButton:focus { border: ${border_width}px solid $focus; }
QPushButton:disabled, QToolButton:disabled { background: $disabled; color: $disabled_text; border-color: $disabled_border; }
QPushButton#primaryAction:disabled { background: $disabled_accent; color: $disabled_text; border-color: $divider; }
QFrame#viewportFrame { background: $surface; border: ${border_width}px solid $divider; }
QFrame#viewportBar { background: $button; border-bottom: ${border_width}px solid $divider; }
""").substitute(TOKENS)
