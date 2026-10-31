"""VTK projection of mesh data with source-ID preserving selection."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget


def pick_candidate(projection, kind, entity_id=None, resource_id=None):
    """Keep the original projection identity with a queued renderer candidate."""
    result = {key: projection.get(key) for key in ("document_id", "document_epoch", "revision", "projection_revision")}
    result["kind"] = kind
    if kind is not None:
        result.update(id=entity_id, resource_id=resource_id,
                      resource_revision=projection.get("resource_revisions", {}).get(resource_id))
    return result


class MeshViewport(QWidget):
    entityPicked = Signal(dict)
    diagnostic = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        import vtk
        from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

        self.vtk = vtk
        self._initialized = False
        self._node_ids = []
        self._cells = []
        self._document_id = None
        self._projection_stamp = {}
        self._node_resources = {}
        self._render_failed = False
        self._pick_mode = "element"
        self._grid = vtk.vtkUnstructuredGrid()
        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(0.955, 0.967, 0.98)
        self._renderer.GetActiveCamera().ParallelProjectionOn()
        self._widget = QVTKRenderWindowInteractor(self)
        self._widget.GetRenderWindow().AddRenderer(self._renderer)
        self._widget.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self._widget.AddObserver("LeftButtonPressEvent", self._on_pick, 1.0)
        self._mapper = vtk.vtkDataSetMapper()
        self._mapper.SetInputData(self._grid)
        self._actor = vtk.vtkActor()
        self._actor.SetMapper(self._mapper)
        self._actor.GetProperty().EdgeVisibilityOn()
        self._actor.GetProperty().SetEdgeColor(0.24, 0.32, 0.4)
        self._actor.GetProperty().SetLineWidth(1.0)
        self._renderer.AddActor(self._actor)
        self._highlight = vtk.vtkActor()
        self._highlight.GetProperty().SetColor(0.95, 0.52, 0.12)
        self._highlight.GetProperty().SetRepresentationToWireframe()
        self._highlight.GetProperty().SetLineWidth(3)
        self._highlight.SetVisibility(False)
        self._renderer.AddActor(self._highlight)

        self._hint = QLabel("Open a Radioss model to begin", self)
        self._hint.setObjectName("viewportHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        layout.addWidget(self._widget)
        layout.addWidget(self._hint)
        self._output_window = vtk.vtkOutputWindow.GetInstance()
        self._error_observer = self._output_window.AddObserver("ErrorEvent", self._graphics_error)

    def _graphics_error(self, caller, event):
        if self._render_failed:
            return
        self._render_failed = True
        self._hint.setText("3D rendering failed. Check Messages for graphics errors.")
        self._hint.setStyleSheet("color: #8c3030; background: #fff6f4; padding: 18px;")
        self._hint.show()
        self.diagnostic.emit("The 3D renderer reported an error. Check the graphics driver or rendering environment. The model document remains available.")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            self._widget.Initialize()
            self._initialized = True

    def set_mesh(self, projection: dict, *, reset_camera=True):
        vtk = self.vtk
        self._document_id = projection.get("document_id")
        self._projection_stamp = {key: projection.get(key) for key in
            ("document_id", "document_epoch", "revision", "projection_revision")}
        self._projection_stamp["resource_revisions"] = dict(projection.get("resource_revisions", {}))
        self._node_resources = projection.get("node_resources", {})
        points = vtk.vtkPoints()
        coordinates = projection.get("points", [])
        self._node_ids = list(projection.get("node_ids", []))
        if len(coordinates) != len(self._node_ids):
            raise ValueError("Mesh projection has inconsistent node IDs and coordinates")
        id_to_index = {node_id: i for i, node_id in enumerate(self._node_ids)}
        for xyz in coordinates:
            points.InsertNextPoint(*xyz)
        grid = vtk.vtkUnstructuredGrid()
        grid.SetPoints(points)
        types = {
            "triangle": (vtk.VTK_TRIANGLE, 3), "triangle3": (vtk.VTK_TRIANGLE, 3),
            "quad": (vtk.VTK_QUAD, 4), "shell4": (vtk.VTK_QUAD, 4),
            "tetra": (vtk.VTK_TETRA, 4), "tetra4": (vtk.VTK_TETRA, 4),
            "hexahedron": (vtk.VTK_HEXAHEDRON, 8), "brick8": (vtk.VTK_HEXAHEDRON, 8),
            "line": (vtk.VTK_LINE, 2), "wedge": (vtk.VTK_WEDGE, 6),
            "pyramid": (vtk.VTK_PYRAMID, 5),
        }
        palette = [(107, 156, 194), (119, 177, 157), (197, 159, 112), (155, 145, 190), (190, 142, 153)]
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Part colour")
        self._cells = []
        omitted = 0
        part_colors = {}
        for cell in projection.get("cells", []):
            spec = types.get(str(cell.get("type", "")).lower())
            nodes = cell.get("nodes", [])
            if spec is None or len(nodes) != spec[1] or any(n not in id_to_index for n in nodes):
                omitted += 1
                continue
            ids = vtk.vtkIdList()
            for node_id in nodes:
                ids.InsertNextId(id_to_index[node_id])
            grid.InsertNextCell(spec[0], ids)
            self._cells.append(dict(cell))
            part = cell.get("part_id", 0)
            if part not in part_colors:
                part_colors[part] = palette[len(part_colors) % len(palette)]
            colors.InsertNextTuple3(*part_colors[part])
        grid.GetCellData().SetScalars(colors)
        self._grid = grid
        self._mapper.SetInputData(grid)
        self._mapper.SetScalarModeToUseCellData()
        self._mapper.SetColorModeToDirectScalars()
        self._mapper.ScalarVisibilityOn()
        self._highlight.SetVisibility(False)
        if not self._render_failed:
            self._hint.setVisible(grid.GetNumberOfCells() == 0)
            self._hint.setText("No supported mesh elements to display" if coordinates else "Open a Radioss model to begin")
        if omitted:
            self.diagnostic.emit(f"The 3D view omitted {omitted} unsupported or unresolved elements. The deck is preserved.")
        if reset_camera and grid.GetNumberOfPoints():
            self.isometric_view()
        self.render()

    def set_pick_mode(self, mode: str):
        self._pick_mode = mode

    def set_edges_visible(self, visible: bool):
        self._actor.GetProperty().SetEdgeVisibility(bool(visible))
        self.render()

    def fit_view(self):
        self._renderer.ResetCamera()
        self._renderer.ResetCameraClippingRange()
        self.render()

    def isometric_view(self):
        camera = self._renderer.GetActiveCamera()
        camera.SetPosition(1, -1, 0.8)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(0, 0, 1)
        self.fit_view()

    def _on_pick(self, caller, event):
        x, y = self._widget.GetEventPosition()
        vtk = self.vtk
        if self._pick_mode == "node":
            picker = vtk.vtkPointPicker()
            picker.SetTolerance(0.02)
            picker.AddPickList(self._actor)
            picker.PickFromListOn()
            if picker.Pick(x, y, 0, self._renderer):
                point_id = picker.GetPointId()
                if 0 <= point_id < len(self._node_ids):
                    identifier = self._node_ids[point_id]
                    resources = self._node_resources.get(identifier, [])
                    self.entityPicked.emit(pick_candidate(self._projection_stamp, "node", identifier,
                                                          resources[0] if len(resources) == 1 else None))
                    return
            self.entityPicked.emit(pick_candidate(self._projection_stamp, None))
            return
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        picker.AddPickList(self._actor)
        picker.PickFromListOn()
        if not picker.Pick(x, y, 0, self._renderer):
            self.entityPicked.emit(pick_candidate(self._projection_stamp, None))
            return
        index = picker.GetCellId()
        if not 0 <= index < len(self._cells):
            return
        cell = self._cells[index]
        self.entityPicked.emit({**pick_candidate(self._projection_stamp, "element", cell["id"], cell.get("resource_id")), "part_id": cell.get("part_id"),
                                "resource_id": cell.get("resource_id"), "card_id": cell.get("card_id")})

    def set_selection(self, selection):
        """Only an approved canonical session selection may alter the highlight."""
        self._highlight.SetVisibility(False)
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            self.render()
            return
        # Scalar edits do not rebuild geometry, but future picks use current tokens.
        self._projection_stamp["revision"] = selection.get("revision")
        self._projection_stamp["resource_revisions"] = dict(selection.get("resource_revisions", {}))
        ids = selection.get("ids", [])
        if selection.get("document_id") != self._document_id or not ids:
            self.render()
            return
        if selection.get("kind") == "node":
            try:
                index = self._node_ids.index(ids[0])
            except ValueError:
                self.render()
                return
            point = self._grid.GetPoint(index)
            bounds = self._grid.GetBounds()
            span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1e-9)
            sphere = self.vtk.vtkSphereSource()
            sphere.SetCenter(*point)
            sphere.SetRadius(span * 0.012)
            sphere.SetThetaResolution(16)
            sphere.SetPhiResolution(12)
            mapper = self.vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(sphere.GetOutputPort())
            self._highlight.GetProperty().SetRepresentationToSurface()
            self._highlight.SetMapper(mapper)
            self._highlight.SetVisibility(True)
            self.render()
            return
        if selection.get("kind") != "element":
            self.render()
            return
        refs = selection.get("refs", [])
        keys = {(ref.get("resource_id"), ref.get("local_id")) for ref in refs if ref.get("entity_kind") == "element"}
        indices = [i for i, cell in enumerate(self._cells) if (cell.get("resource_id"), cell["id"]) in keys]
        if not keys or len(indices) != len(keys):
            self.render()
            return
        vtk = self.vtk
        ids = vtk.vtkIdList()
        for index in indices:
            ids.InsertNextId(index)
        extract = vtk.vtkExtractCells()
        extract.SetInputData(self._grid)
        extract.SetCellList(ids)
        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputConnection(extract.GetOutputPort())
        mapper.ScalarVisibilityOff()
        self._highlight.GetProperty().SetRepresentationToWireframe()
        self._highlight.SetMapper(mapper)
        self._highlight.SetVisibility(True)
        self.render()

    def render(self):
        if self._initialized:
            self._widget.GetRenderWindow().Render()

    def shutdown(self):
        if self._error_observer is not None:
            self._output_window.RemoveObserver(self._error_observer)
            self._error_observer = None
        if self._initialized:
            self._widget.GetRenderWindow().Finalize()
            self._initialized = False
