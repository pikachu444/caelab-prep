"""Qt entry point joining the preserved Prep adapter and new workspace."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QSettings, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox

from .design import DARK_TOKENS, build_stylesheet, icon, tokens_for_theme
from .prep_controller import PrepController
from .prep_workspace import PrepWorkspace, _EN_TREE_HEADERS, _KO_TREE_HEADERS
from .reference_components import reference_style
from .shell import FileTask as _FileTask


def _resolve_theme_mode(theme_mode: str | None) -> str:
    if theme_mode is not None:
        return "dark" if str(theme_mode).strip().lower() == "dark" else "light"
    if os.environ.get("CAELAB_THEME_MODE", "").strip().lower() == "dark":
        return "dark"
    return "light"


def _resolve_ui_language(ui_language: str | None) -> str:
    if ui_language is not None:
        return "ko" if str(ui_language).strip().lower() == "ko" else "en"
    if os.environ.get("CAELAB_UI_LANGUAGE", "").strip().lower() == "ko":
        return "ko"
    return "en"


_KO_MENU_TITLES = {
    "File": "&파일",
    "Edit": "&편집",
    "Model": "&모델",
    "Mesh": "&메시",
    "Conditions": "&조건",
    "View": "&보기",
}

_KO_ACTION_LABELS = {
    "file.new": "새 모델…",
    "file.open": "Radioss 덱 열기…",
    "file.open_project": "프로젝트 열기…",
    "model.sources": "소스 모델 / RAD 가져오기…",
    "file.save": "프로젝트 저장",
    "file.save_as": "다른 이름으로 프로젝트 저장…",
    "file.export": "Radioss 덱 내보내기…",
    "file.export_solver": "Starter 및 Engine 내보내기…",
    "file.close": "종료",
    "edit.undo": "실행 취소",
    "edit.redo": "다시 실행",
    "edit.reload": "속성 다시 읽기",
    "mesh.import": "외부 메시 가져오기…",
    "mesh.candidate": "CAD / 메시 후보 검토…",
    "mesh.structured_builder": "구조화 사각 / 스윕 육면체 메시…",
    "mesh.geometry_features": "형상 특징선 검사…",
    "mesh.move_nodes": "절점 좌표 이동…",
    "mesh.merge_nodes": "절점 병합 (허용오차)…",
    "mesh.flip_shell_normals": "셸 법선 반전…",
    "mesh.split_triangle_edge": "삼각형 변 분할…",
    "mesh.delete_elements": "요소 삭제…",
    "mesh.reassign_parts": "요소 PART 변경…",
    "mesh.replace_prepared": "준비된 메시 교체 / 대상 재연결…",
    "model.analysis_cases": "해석 케이스…",
    "view.fit": "모델 맞춤",
    "view.fit_selected": "선택 맞춤",
    "view.isometric": "등각 보기",
    "view.front": "정면 보기",
    "view.top": "평면 보기",
    "view.right": "우측면 보기",
    "view.edges": "요소선 표시",
    "view.hide_selected": "선택 숨기기",
    "view.isolate": "선택 격리",
    "view.show_all": "모든 파트 표시",
}

_KO_MODELING_LABELS = {
    "material.create": "재료 생성…",
    "section.create": "셸 단면 속성 생성…",
    "solid_section.create": "솔리드 단면 속성 생성…",
    "coordinate_system.create": "고정 좌표계 생성…",
    "curve.create": "하중 곡선 생성…",
    "group.create": "절점 집합 생성…",
    "element_group.create": "요소 집합 생성…",
    "surface.create": "셸 표면 생성…",
    "constraint.create": "경계 조건 생성…",
    "load.create": "절점 하중 생성…",
    "velocity.create": "초기 속도 생성…",
    "contact.create": "TYPE7 접촉 생성…",
    "object.edit": "객체 편집…",
    "object.copy": "객체 복제…",
    "object.delete": "객체 삭제…",
    "part.assign": "재료 / 단면 할당…",
}

_KO_COMMAND_BUTTONS = {
    "Model": ("모델", "모델 명령"),
    "Mesh": ("메시", "메시 명령"),
    "Conditions": ("조건", "조건 명령"),
}


class MainWindow(PrepController, PrepWorkspace, QMainWindow):
    """One native document window; model ownership remains in PrepSession."""

    operationFinished = Signal(str, bool)
    selectionChanged = Signal(dict)
    _sessionEvent = Signal(object)
    LAYOUT_VERSION = 4

    def __init__(self, session=None, *, enable_viewport: bool = True, presentation=None,
                 settings=None, theme_mode: str | None = None, ui_language: str | None = None):
        super().__init__()
        self.presentation = presentation
        self.theme_mode = _resolve_theme_mode(theme_mode)
        self.ui_language = _resolve_ui_language(ui_language)
        self._live_control = None
        if session is None:
            from ..application.session import PrepSession
            session = PrepSession()
        self.initialize_controller(
            session, file_dialog=lambda: QFileDialog, message_box=lambda: QMessageBox,
            task_factory=lambda *args, **kwargs: _FileTask(*args, **kwargs))
        self._settings = settings if settings is not None else QSettings("CAELab", "Prep" + ("-" + presentation if presentation else ""))
        self._register_commands()
        self._en_modeling_labels = {key: act.text() for key, act in self.modeling.actions.items()}
        from .reference_workspace import _edit_action, configure_native
        self.edit_properties_action = _edit_action(self)
        self.build_workspace(enable_viewport=enable_viewport)
        configure_native(self, presentation or "beidprep", native_commands=presentation in (None, "beidprep"))
        self._en_dock_titles = (
            self.model_dock.windowTitle(),
            self.properties_dock.windowTitle(),
            self.messages_dock.windowTitle(),
        )
        self._en_property_tabs = (
            self.property_tabs.tabText(0),
            self.property_tabs.tabText(1),
        )
        self._en_menu_titles = {key: menu.title() for key, menu in self.command_menus.items()}
        geometry = self._settings.value("windowGeometry")
        state = self._settings.value("windowState")
        geometry_restored = bool(geometry) and self.restoreGeometry(geometry)
        if not geometry_restored:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        restored = bool(state) and self.restoreState(state, self.LAYOUT_VERSION)
        self._initial_sidebar_pending = not restored
        self._automatic_sidebar = not restored
        if not restored:
            self.messages_dock.setVisible(bool(presentation and self.reference_adapter.docks.output))
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False
        self._sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self._sessionEvent.emit)
        self._live_control = None
        self._live_label = QLabel("Live control: off")
        self.statusBar().addPermanentWidget(self._live_label)
        menu = QMenu("&Automation", self.menuBar())
        self.menuBar().addMenu(menu)
        self.automation_menu = menu
        self.start_live_action = menu.addAction("Start live control…", self._start_live_dialog)
        self.stop_live_action = menu.addAction("Stop live control", self.stop_live_ipc)
        self.stop_live_action.setEnabled(False)
        self.refresh_document(rebuild_viewport=bool(self._summary().get("document_id")))
        if self.theme_mode == "dark":
            self.apply_theme_mode("dark")
        if self.ui_language == "ko":
            self.apply_ui_language("ko")

    def _refresh_actions(self, summary=None):
        super()._refresh_actions(summary)
        summary = summary or self._summary()
        loaded = bool(summary.get("document_id"))
        editable = not self._busy and not self._replacement_conflict
        self.mesh_workflow.structured_mesh_action.setEnabled(loaded and editable)

    def _compose_window_stylesheet(self) -> str:
        adapter_key = self.presentation or "beidprep"
        qss = build_stylesheet(self.theme_mode) + reference_style(adapter_key)
        if adapter_key == "beidprep":
            qss += "QMainWindow::separator { width: 2px; height: 2px; }"
        if self.theme_mode == "dark":
            qss += (
                f"\nQWidget {{ font-family: {DARK_TOKENS['font_family']}; color: {DARK_TOKENS['text']}; }}\n"
                f"QLabel#commandGroup {{ color: {DARK_TOKENS['muted']}; }}\n"
            )
        elif self.ui_language == "ko":
            qss += "\nQWidget { font-family: 'Malgun Gothic', 'Segoe UI'; }\n"
        return qss

    def apply_theme_mode(self, mode: str) -> None:
        target = "dark" if str(mode).strip().lower() == "dark" else "light"
        self.theme_mode = target
        if hasattr(self, "dark_theme_action"):
            with QSignalBlocker(self.dark_theme_action):
                self.dark_theme_action.setChecked(target == "dark")
        self.setStyleSheet(self._compose_window_stylesheet())
        palette = tokens_for_theme(target)
        self.property_editor.setStyleSheet(
            f"QFrame#propertySectionHeading {{ background: {palette['raised']}; "
            f"border-top: 1px solid {palette['divider']}; border-bottom: 1px solid {palette['divider']}; }}"
            f"QFrame#propertyRow {{ background: {palette['surface']}; border-bottom: 1px solid {palette['alternate']}; }}"
            f"QLabel#propertyLabel[invalid='true'] {{ color: {palette['error']}; font-weight: bold; }}"
        )
        for key, spec in self.actions.specs.items():
            self.actions.actions[key].setIcon(icon(spec.icon or spec.key, theme=target))
        if hasattr(self, "edit_properties_action"):
            self.edit_properties_action.setIcon(icon("card", theme=target))
        for button, primary in getattr(self, "_command_menu_buttons", {}).values():
            button.setIcon(primary.icon())
        if self.viewport is not None and hasattr(self.viewport, "set_theme_mode"):
            self.viewport.set_theme_mode(target)
        if hasattr(self, "viewport_inspection_bar"):
            self.viewport_inspection_bar.apply_theme_mode(target)
        active_dialog = getattr(self.mesh_workflow, "dialog", None)
        if active_dialog is not None and hasattr(active_dialog, "apply_theme_mode"):
            active_dialog.apply_theme_mode(target)

    def apply_ui_language(self, lang: str) -> None:
        target = "ko" if str(lang).strip().lower() == "ko" else "en"
        self.ui_language = target
        ko = target == "ko"
        if hasattr(self, "korean_ui_action"):
            with QSignalBlocker(self.korean_ui_action):
                self.korean_ui_action.setChecked(ko)
        self.setStyleSheet(self._compose_window_stylesheet())

        for key, menu in self.command_menus.items():
            menu.setTitle(_KO_MENU_TITLES.get(key, f"&{key}") if ko else self._en_menu_titles.get(key, f"&{key}"))
        if hasattr(self, "automation_menu"):
            self.automation_menu.setTitle("&자동화" if ko else "&Automation")
            self.start_live_action.setText("실시간 제어 시작…" if ko else "Start live control…")
            self.stop_live_action.setText("실시간 제어 중지" if ko else "Stop live control")

        for key, spec in self.actions.specs.items():
            action = self.actions.actions[key]
            label = _KO_ACTION_LABELS.get(key, spec.label) if ko else spec.label
            action.setText(label)
            action.setStatusTip(label.replace("…", ""))

        for key, action in self.modeling.actions.items():
            en_label = self._en_modeling_labels.get(key, action.text())
            action.setText(_KO_MODELING_LABELS.get(key, en_label) if ko else en_label)

        if hasattr(self, "edit_properties_action"):
            self.edit_properties_action.setText("속성 편집…" if ko else "Edit properties…")
            self.edit_properties_action.setIconText("편집" if ko else "Edit")

        # Document toolbar labels & tooltips
        self.document_toolbar.setWindowTitle("문서" if ko else "Document")
        for action, en_text, ko_text in (
            (self.open_rad_action, "Open deck", "덱 열기"),
            (self.save_action, "Save", "저장"),
            (self.export_action, "Export", "내보내기"),
        ):
            action.setIconText(ko_text if ko else en_text)
            action.setToolTip(action.text().replace("…", ""))
        for key, (button, _primary) in getattr(self, "_command_menu_buttons", {}).items():
            if ko and key in _KO_COMMAND_BUTTONS:
                btn_text, tip_text = _KO_COMMAND_BUTTONS[key]
            else:
                btn_text, tip_text = key, f"{key} commands"
            button.setText(btn_text)
            button.setToolTip(tip_text)

        # Viewport toolbar actions & pick combo
        if hasattr(self, "_model_view_toolbar"):
            self._model_view_toolbar.setWindowTitle("모델 보기" if ko else "Model view")
        for action, en_label, ko_label in (
            (self.fit_action, "Fit", "맞춤"),
            (self.iso_action, "Isometric", "등각"),
            (self.edges_action, "Edges", "요소선"),
            (self.fit_selected_action, "Fit selection", "선택 맞춤"),
            (self.hide_selected_action, "Hide", "숨기기"),
            (self.isolate_action, "Isolate", "격리"),
            (self.show_all_action, "Show all", "모두 표시"),
        ):
            action.setIconText(ko_label if ko else en_label)
            action.setToolTip(action.text().replace("…", ""))
        with QSignalBlocker(self.pick_mode):
            self.pick_mode.setItemText(0, "요소" if ko else "Elements")
            self.pick_mode.setItemText(1, "절점" if ko else "Nodes")
        self.selection_type_menu.setTitle("선택 대상" if ko else "Selection type")
        self._selection_type_menu.actions[0].setText("요소" if ko else "Elements")
        self._selection_type_menu.actions[1].setText("절점" if ko else "Nodes")
        self.dark_theme_action.setText("다크 테마" if ko else "Dark theme")
        self.korean_ui_action.setText("한국어 UI" if ko else "Korean UI")

        # Dock titles, filter placeholder, tree & message headers, inspector tabs
        if ko:
            self.model_dock.setWindowTitle("모델 트리")
            self.properties_dock.setWindowTitle("속성 검사기")
            self.messages_dock.setWindowTitle("메시지")
            self.property_tabs.setTabText(0, "속성")
            self.property_tabs.setTabText(1, "카드 원본")
        else:
            model_title, prop_title, msg_title = self._en_dock_titles
            self.model_dock.setWindowTitle(model_title)
            self.properties_dock.setWindowTitle(prop_title)
            self.messages_dock.setWindowTitle(msg_title)
            tab0, tab1 = self._en_property_tabs
            self.property_tabs.setTabText(0, tab0)
            self.property_tabs.setTabText(1, tab1)

        self.model_filter.setPlaceholderText("모델 객체 검색" if ko else "Filter model objects")
        headers = _KO_TREE_HEADERS if ko else _EN_TREE_HEADERS
        for col, title in enumerate(headers):
            self.model_tree.model().setHeaderData(col, Qt.Orientation.Horizontal, title)
        if ko:
            self.model_tree.setColumnWidth(2, 72)
            self.model_tree.setColumnWidth(3, 46)
            self.model_tree.setColumnWidth(4, 46)
        else:
            self.model_tree.setColumnWidth(2, 95)
            self.model_tree.setColumnWidth(3, 40)
            self.model_tree.setColumnWidth(4, 40)
        self.messages.setHeaderLabels(["수준", "메시지"] if ko else ["Level", "Message"])

        if getattr(self, "_automatic_sidebar", False):
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False

        if self.viewport is not None and hasattr(self.viewport, "_hint") and not self.viewport._render_failed:
            if not self.viewport._visible_cell_count:
                if ko:
                    self.viewport._hint.setText(
                        "모든 요소 숨김" if self.viewport._grid.GetNumberOfCells()
                        else ("표시 가능한 요소 없음" if self.viewport._node_ids else "모델 없음")
                    )
                else:
                    self.viewport._hint.setText(
                        "All elements hidden" if self.viewport._grid.GetNumberOfCells()
                        else ("No displayable elements" if self.viewport._node_ids else "No model")
                    )
        elif hasattr(self, "_viewport_placeholder"):
            failure = self._viewport_placeholder.toolTip()
            if ko:
                self._viewport_placeholder.setText("3D 뷰어를 사용할 수 없음" if failure else "이 세션에서는 3D 뷰어가 비활성화됨")
            else:
                self._viewport_placeholder.setText("3D viewer unavailable" if failure else "3D viewer disabled for this session")

        if hasattr(self, "viewport_inspection_bar"):
            self.viewport_inspection_bar.apply_ui_language(target)
        self._present_document(self._summary())
        if getattr(self, "_candidate_preview", None) and hasattr(self, "_present_candidate_preview"):
            self._present_candidate_preview(reset_camera=False)
        self._refresh_tree()
        self._refresh_tree_appearances()
        self._refresh_fields()
        self._live_status_changed({})
        active_dialog = getattr(self.mesh_workflow, "dialog", None)
        if active_dialog is not None and hasattr(active_dialog, "apply_ui_language"):
            active_dialog.apply_ui_language(target)

    def _start_live_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "New live-control connection file", "prep-connection.json", "Connection file (*.json)")
        if path:
            try: self.start_live_ipc(path)
            except Exception as exc: self._show_error(exc)

    def start_live_ipc(self, descriptor_path):
        """Explicitly share this owner; a connection file contains its local credential."""
        from .live_control import LiveControl
        if self._live_control is not None and self._live_control.status()["status"] != "closed":
            raise ValueError("Live control is already running; stop it before starting another endpoint.")
        self._live_control = LiveControl(self, descriptor_path)
        self._live_control.changed.connect(self._live_status_changed)
        self._live_status_changed({})
        return self.live_ipc_status()

    def live_ipc_status(self):
        return self._live_control.status() if self._live_control else {"status": "closed"}

    def _live_status_changed(self, _):
        state = self.live_ipc_status()
        active = state["status"] != "closed"
        ko = self.ui_language == "ko"
        if ko:
            text = f"실시간 제어: {state['host']}:{state['port']}" if active else "실시간 제어: 꺼짐"
            if state["status"] == "stopping": text = "실시간 제어: 워커 종료 중…"
            elif state.get("active_jobs"): text += " · 메싱 중"
        else:
            text = f"Live control: {state['host']}:{state['port']}" if active else "Live control: off"
            if state["status"] == "stopping": text = "Live control: stopping worker…"
            elif state.get("active_jobs"): text += " · meshing"
        self._live_label.setText(text)
        self._live_label.setToolTip(state.get("descriptor_path", ""))
        self.start_live_action.setEnabled(not active); self.stop_live_action.setEnabled(active)

    def stop_live_ipc(self):
        result = self._live_control.close() if self._live_control else True
        self._live_status_changed({})
        return result

    def closeEvent(self, event):
        if getattr(self, "_live_control", None) and self._live_control.status().get("active_jobs"):
            self.stop_live_ipc()
            self.statusBar().showMessage("Stopping the live mesh worker. Close after it has stopped.")
            event.ignore(); return
        super().closeEvent(event)
        if event.isAccepted(): self.stop_live_ipc()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_sidebar_pending:
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False
            self._initial_sidebar_pending = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_automatic_sidebar", False):
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False

    def event(self, event):
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and getattr(self, "_automatic_sidebar", False)):
            # QMainWindow owns dock separators; preserve the first manual drag.
            x, y = event.position().x(), event.position().y()
            panels = sorted((dock.geometry() for dock in (self.model_dock, self.properties_dock)
                             if dock.isVisible() and not dock.isFloating()), key=lambda rect: rect.left())
            for rect in panels:
                if rect.top() <= y <= rect.bottom() and rect.right() < x <= rect.right() + 8:
                    self._automatic_sidebar = False
                    break
        return super().event(event)

    def resizeDocks(self, docks, sizes, orientation):
        if not getattr(self, '_sizing_initial_sidebar', False):
            self._automatic_sidebar = False
        super().resizeDocks(docks, sizes, orientation)


def run(session=None, argv=None):
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("CAELab Prep")
    app.setOrganizationName("CAELab")
    window = MainWindow(session)
    window.show()
    return app.exec()
