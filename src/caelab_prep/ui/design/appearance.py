"""Engineering glyphs and native surface rules, independent of app providers."""

from string import Template

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .tokens import TOKENS


ICON_PURPOSES = {
    "open": "Open an existing document", "project": "Working document",
    "save": "Save the working document", "export": "Export a separate solver file",
    "undo": "Undo one command", "redo": "Redo one command", "fit": "Fit model",
    "iso": "Orient model", "edges": "Show element edges", "material": "Material definition",
    "constraint": "Boundary condition", "card": "Native card", "curve": "Curve definition",
    "vector": "Vector quantity", "warning": "Model warning", "apply": "Apply draft",
    "mesh": "Mesh resource", "part": "Model part", "section": "Section property",
    "load": "Applied load", "contact": "Contact relationship", "set": "Entity set",
    "select": "Entity selection", "result": "Result quantity", "job": "Operation",
}

# Original glyphs on one 24-unit construction grid; no vendor artwork.
_GLYPHS = {
    "open": '<path d="M3 8V5h6l2 3h10l-3 12H3V8h15M3 20l4-9h13"/>',
    "project": '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "save": '<path d="M4 3h14l3 3v15H3V3h1M7 3v6h9V3M7 21v-7h10v7M13 4v3"/>',
    "export": '<path d="M10 4H4v16h16v-6M12 3h9v9M10 14 21 3M7 17h6"/>',
    "undo": '<path d="m8 4-5 5 5 5M3 9h10a6 6 0 0 1 0 12"/>',
    "redo": '<path d="m16 4 5 5-5 5M21 9H11a6 6 0 0 0 0 12"/>',
    "fit": '<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5M8 8h8v8H8z"/>',
    "iso": '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9"/>',
    "edges": '<path d="M3 4h18v16H3zM3 4l18 16M21 4 3 20M3 12h18M12 4v16"/>',
    "material": '<path d="m12 3 9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v8M8 5l9 5v8"/>',
    "constraint": '<path d="M3 6h18M5 6v9M12 6v9M19 6v9M3 15h18M5 15l-3 5M10 15l-3 5M15 15l-3 5M20 15l-3 5"/>',
    "card": '<path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h6"/>',
    "curve": '<path d="M4 3v17h17M7 17l4-7 4 3 5-8"/><circle cx="11" cy="10" r="1.2"/><circle cx="15" cy="13" r="1.2"/>',
    "vector": '<path d="M4 20h16M4 20V4M4 20 18 6M12 6h6v6"/>',
    "warning": '<path d="m12 3 10 18H2zM12 8v6"/><circle cx="12" cy="17.5" r=".7"/>',
    "apply": '<path d="m3 12 6 6L21 5"/>',
    "mesh": '<path d="m12 3 9 17H3zM7 12h10M7 12l5 8 5-8M12 3v17"/>',
    "part": '<path d="m4 6 9-3 7 4v12l-9 3-7-4zM4 6l7 4 9-3M11 10v12M11 10v-4l5-2"/>',
    "section": '<path d="M5 3h14v4h-5v10h5v4H5v-4h5V7H5z"/>',
    "load": '<path d="M3 20h18M7 3v12m-4-4 4 4 4-4M17 3v12m-4-4 4 4 4-4"/>',
    "contact": '<path d="M3 4h6v16H3M21 4h-6v16h6M9 9l6 3-6 3"/>',
    "set": '<path d="M7 3H3v18h4M17 3h4v18h-4"/><circle cx="9" cy="8" r="1.5"/><circle cx="15" cy="8" r="1.5"/><circle cx="9" cy="16" r="1.5"/><circle cx="15" cy="16" r="1.5"/>',
    "select": '<path d="m5 3 14 9-7 2-3 7zM14 15l5 6"/>',
    "result": '<path d="M3 3v18h18M7 17v-4h3v4M12 17V9h3v8M17 17V5h3v12"/>',
    "job": '<rect x="3" y="4" width="18" height="17" rx="1"/><path d="M3 9h18M7 2v4M17 2v4m-8 6 6 3-6 3z"/>',
}


def icon(name):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="{TOKENS["icon_stroke"]}" stroke-width="{TOKENS["icon_stroke_width"]}" '
           'stroke-linecap="round" stroke-linejoin="round">'
           + _GLYPHS.get(name, _GLYPHS["card"]) + '</g></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        renderer.render(painter)
        painter.end()
        result.addPixmap(canvas)
    return result


STYLESHEET = Template("""
QWidget { font-family: $font_family; font-size: ${font_size}px; color: $text; }
QMainWindow { background: $workspace; }
QMenuBar, QMenu { background: $surface; }
QMenuBar { border-bottom: 1px solid $divider; padding: 1px 4px; }
QMenuBar::item { padding: 3px 8px; }
QMenu { border: 1px solid $border; padding: 3px; }
QMenu::item { padding: 4px 24px 4px 18px; }
QMenuBar::item:selected, QMenu::item:selected { background: $hover; color: $text; }
QToolTip { padding: 4px 7px; background: $surface; border: 1px solid $border; color: $text; font-size: 10px; }
QToolBar { background: $subtle; border: none; border-bottom: 1px solid $divider; padding: 2px 4px; spacing: 3px; }
QToolBar::separator { background: $divider; width: 1px; margin: 3px 4px; }
QToolButton { min-height: ${control_min_height}px; padding: 2px 5px; border: 1px solid transparent; border-radius: 2px; }
QToolButton:hover { background: $hover; border-color: $hover_border; }
QToolButton:checked { background: $checked; border-color: $checked_border; }
QToolButton::menu-button { subcontrol-origin: padding; subcontrol-position: top right; width: 14px; border: none; border-left: 1px solid $divider; background: $subtle; }
QToolButton::menu-button:hover { background: $hover; }
QToolButton::menu-button:disabled { background: $subtle; border-color: $divider; }
QToolButton[primaryCommand="true"] { color: $selection_text; background: $checked; border-color: $accent; font-weight: 600; }
QToolButton[primaryCommand="true"]:hover { background: $selection; border-color: $accent_hover; }
QToolBar#modelViewCommands QToolButton { min-height: 18px; padding: 2px 4px; }
QToolButton:pressed, QPushButton:pressed { background: $pressed; }
QPushButton { padding: 2px 8px; min-height: ${control_min_height}px; background: $button; border: 1px solid $button_border; border-radius: 2px; }
QPushButton:hover { background: $hover; border-color: $button_hover_border; }
QPushButton#primaryAction { color: $surface; background: $accent; border-color: $accent; }
QPushButton#primaryAction:hover { background: $accent_hover; }
QPushButton:focus, QToolButton:focus { border-color: $focus; }
QPushButton:disabled, QToolButton:disabled, QPushButton#primaryAction:disabled { color: $disabled_text; background: $disabled; border-color: $disabled_border; }
QToolButton:disabled { background: transparent; border-color: transparent; }
QMainWindow::separator, QSplitter::handle { background: $workspace; width: 4px; height: 4px; }
QMainWindow::separator:hover, QSplitter::handle:hover { background: $hover_border; }
QDockWidget::title { background: $raised; border-bottom: 1px solid $divider; padding: 3px 6px; font-weight: 600; font-size: ${title_size}px; }
QTabWidget::pane { background: $surface; border: none; border-top: 1px solid $divider; }
QTabBar::tab { padding: 3px 8px; border-bottom: 2px solid transparent; background: $raised; }
QTabBar::tab:selected { background: $surface; border-bottom-color: $accent; }
QScrollArea { background: $surface; border: none; }
QTreeView, QTableView { background: $surface; border: none; alternate-background-color: $alternate; selection-background-color: $selection; selection-color: $selection_text; }
QTreeView::item { min-height: ${tree_row_height}px; padding: 0px 2px; }
QTreeView::item:hover { background: $hover; }
QTreeView::item:selected, QTreeView::item:selected:hover { background: $selection; color: $selection_text; }
QTreeView:focus, QTableView:focus { outline: 1px solid $focus; }
QTableView { gridline-color: $divider; }
QHeaderView::section { padding: 2px 5px; color: $muted; background: $subtle; border: none; border-right: 1px solid $divider; border-bottom: 1px solid $divider; font-size: 9px; font-weight: 600; }
QTableCornerButton::section { border: none; border-bottom: 1px solid $divider; background: $subtle; }
QLineEdit, QComboBox { min-height: ${control_min_height}px; padding: 1px 4px; background: $surface; border: 1px solid $border; border-radius: 1px; }
QLineEdit:focus, QComboBox:focus { border-color: $focus; }
QLineEdit:disabled, QComboBox:disabled { color: $disabled_text; background: $raised; }
QComboBox::drop-down { width: 16px; border: none; }
QCheckBox { spacing: 4px; padding: 1px 0; }
QPlainTextEdit { background: $surface; border: 1px solid $divider; selection-background-color: $selection; selection-color: $selection_text; }
QWidget#propertyEditor, QWidget#propertyBody, QFrame#propertyGroup { background: $surface; }
QFrame#propertyHeader { background: $surface; border-bottom: 1px solid $divider; }
QFrame#propertyGroup { border-bottom: 1px solid $divider; }
QLabel#propertyGroupTitle { padding: 3px 6px; color: $group_heading; background: $raised; font-weight: 600; font-size: 10px; }
QLabel#propertyTitle { color: $heading; font-size: ${title_size}px; font-weight: 600; }
QLabel#propertyLabel { color: $muted; font-size: 10px; }
QLabel#propertySubtitle, QLabel#unitsNote { color: $muted; font-size: 9px; }
QLabel#groupTitle { color: $group_heading; font-weight: 600; font-size: 10px; }
QLabel#inputError, QLabel[invalid="true"] { color: $error; font-size: 9px; }
QLineEdit[invalid="true"] { background: $error_surface; border-color: $error; }
QLabel#viewportHint { color: $muted; background: transparent; font-size: ${title_size}px; }
QFrame#viewportFrame { background: $surface; border: 1px solid $divider; }
QFrame#viewportBar, QFrame#curveCommands, QFrame#inspectorCommands { background: $subtle; border-bottom: 1px solid $divider; }
QLabel#applicationBrand { color: $surface; background: $accent; font-weight: 700; font-size: 10px; letter-spacing: 0.8px; padding: 2px 7px; border-radius: 2px; }
QLabel#documentState { color: $accent; background: $subtle; border: 1px solid $hover_border; font-weight: 600; font-size: 9px; padding: 1px 5px; border-radius: 2px; }
QStatusBar { background: $subtle; border-top: 1px solid $divider; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $muted; padding: 1px 4px; font-size: 9px; }
QScrollBar:vertical { width: 10px; margin: 0; background: $subtle; }
QScrollBar:horizontal { height: 10px; margin: 0; background: $subtle; }
QScrollBar::handle { background: $border; border: 2px solid $subtle; border-radius: 4px; min-height: 20px; min-width: 20px; }
QScrollBar::handle:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""").substitute(TOKENS)
