"""VTK projection of mesh data with source-ID preserving selection."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget


def part_key(reference):
    """A part belongs to a resource and native scope, never an integer alone."""
    if isinstance(reference, dict):
        resource, scope = reference.get("resource_id"), reference.get("native_scope")
    elif isinstance(reference, tuple) and len(reference) == 2:
        resource, scope = reference
    else:
        resource = getattr(reference, "resource_id", None)
        scope = getattr(reference, "native_scope", None)
    if not isinstance(resource, str) or not resource or not isinstance(scope, str):
        raise ValueError("A resource-qualified PART reference is required")
    segments = scope.upper().split("/")
    if (len(segments) not in (3, 4) or segments[:2] != ["", "PART"] or
            not segments[2].isdigit() or (len(segments) == 4 and not segments[3].isdigit())):
        raise ValueError("A PART native scope is required")
    return resource, f"/PART/{int(segments[2])}"


def cell_part_key(cell):
    """Prefer the resolved PART owner over the element's INCLUDE resource."""
    reference = cell.get("part_ref") if "part_ref" in cell else (
        cell.get("resource_id"), f"/PART/{cell.get('part_id')}")
    try:
        return part_key(reference)
    except ValueError:
        return None


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
        self._hidden_parts = set()
        self._selection = {}
        self._visible_indices = []
        self._visible_grid = vtk.vtkUnstructuredGrid()
        self._render_failed = False
        self._pick_mode = "element"
        self._grid = vtk.vtkUnstructuredGrid()
        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(0.84, 0.87, 0.90)
        self._renderer.SetBackground2(0.97, 0.98, 0.985)
        self._renderer.GradientBackgroundOn()
        self._renderer.GetActiveCamera().ParallelProjectionOn()
        self._widget = QVTKRenderWindowInteractor(self)
        self._widget.GetRenderWindow().AddRenderer(self._renderer)
        self._widget.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self._axes = vtk.vtkAxesActor()
        self._axes.SetShaftTypeToCylinder()
        self._axes.SetCylinderRadius(0.025)
        self._axes.SetConeRadius(0.12)
        for caption in (self._axes.GetXAxisCaptionActor2D(), self._axes.GetYAxisCaptionActor2D(), self._axes.GetZAxisCaptionActor2D()):
            caption.GetCaptionTextProperty().SetColor(0.16, 0.20, 0.24)
            caption.GetCaptionTextProperty().ShadowOff()
            caption.GetCaptionTextProperty().ItalicOff()
        self._orientation = vtk.vtkOrientationMarkerWidget()
        self._orientation.SetOrientationMarker(self._axes)
        self._orientation.SetInteractor(self._widget)
        self._orientation.SetViewport(0.0, 0.0, 0.15, 0.19)
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

        self._hint = QLabel("No model", self)
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
            self._orientation.SetEnabled(1)
            self._orientation.InteractiveOff()
            self._initialized = True

    def set_mesh(self, projection: dict, *, reset_camera=True):
        vtk = self.vtk
        identity = (projection.get("document_id"), projection.get("document_epoch"))
        previous = (self._projection_stamp.get("document_id"), self._projection_stamp.get("document_epoch"))
        if identity != previous:
            self._hidden_parts.clear()
            self._selection = {}
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
            part = cell_part_key(cell)
            if part not in part_colors:
                part_colors[part] = palette[len(part_colors) % len(palette)]
            colors.InsertNextTuple3(*part_colors[part])
        grid.GetCellData().SetScalars(colors)
        for attributes, count, name in ((grid.GetPointData(), len(self._node_ids), "ProjectionPointIndex"),
                                        (grid.GetCellData(), len(self._cells), "ProjectionCellIndex")):
            indices = vtk.vtkIdTypeArray()
            indices.SetName(name)
            for index in range(count):
                indices.InsertNextValue(index)
            attributes.AddArray(indices)
        self._grid = grid
        self._mapper.SetScalarModeToUseCellData()
        self._mapper.SetColorModeToDirectScalars()
        self._mapper.ScalarVisibilityOn()
        self._apply_visibility()
        if omitted:
            self.diagnostic.emit(f"The 3D view omitted {omitted} unsupported or unresolved elements. The deck is preserved.")
        if reset_camera and grid.GetNumberOfPoints():
            self.isometric_view()
        self.render()

    def _part_keys(self, references):
        keys = set()
        for reference in references:
            document_id = reference.get("document_id") if isinstance(reference, dict) else getattr(reference, "document_id", None)
            if document_id is not None and document_id != self._document_id:
                raise ValueError("The part belongs to another document")
            keys.add(part_key(reference))
        return keys

    def hide_parts(self, part_refs):
        """Hide qualified parts without changing document selection or history."""
        self._hidden_parts.update(self._part_keys(part_refs))
        self._apply_visibility()

    def isolate_parts(self, part_refs):
        """Show only the specified parts; an empty selection is a no-op."""
        keys = self._part_keys(part_refs)
        if not keys:
            return
        available = {cell_part_key(cell) for cell in self._cells}
        if not keys & available:
            raise ValueError("None of the requested parts is present in the mesh")
        self._hidden_parts = available - keys
        self._apply_visibility()

    def show_all_parts(self):
        self._hidden_parts.clear()
        self._apply_visibility()

    def _apply_visibility(self):
        self._visible_indices = [i for i, cell in enumerate(self._cells)
                                 if cell_part_key(cell) not in self._hidden_parts]
        ids = self.vtk.vtkIdList()
        for index in self._visible_indices:
            ids.InsertNextId(index)
        extract = self.vtk.vtkExtractCells()
        extract.SetInputData(self._grid)
        extract.SetCellList(ids)
        extract.Update()
        self._visible_grid = extract.GetOutput()
        self._mapper.SetInputData(self._visible_grid)
        if not self._render_failed:
            self._hint.setVisible(not self._visible_indices)
            self._hint.setText("All elements hidden" if self._cells else
                               ("No displayable elements" if self._node_ids else "No model"))
        self.set_selection(self._selection)

    def _selection_cell_indices(self, selection):
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return []
        keys = {(ref.get("resource_id"), ref.get("local_id")) for ref in selection.get("refs", [])
                if ref.get("entity_kind") == "element"}
        matches = [i for i, cell in enumerate(self._cells) if (cell.get("resource_id"), cell["id"]) in keys]
        if not keys or len(matches) != len(keys):
            return []
        visible = set(getattr(self, "_visible_indices", range(len(self._cells))))
        return [i for i in matches if i in visible]

    def _selection_node_indices(self, selection):
        visible_nodes = {node for i in getattr(self, "_visible_indices", range(len(self._cells)))
                         for node in self._cells[i].get("nodes", [])}
        refs = {(ref.get("resource_id"), ref.get("local_id")) for ref in selection.get("refs", [])
                if ref.get("entity_kind") == "node"}
        return [i for i, node in enumerate(self._node_ids) if node in visible_nodes and
                any((resource, node) in refs for resource in self._node_resources.get(node, []))]

    def fit_selection(self, selection=None):
        """Fit the visible portion of an approved selection, without revealing it."""
        selection = self._selection if selection is None else selection
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return False
        if selection.get("kind") == "node":
            indices = self._selection_node_indices(selection)
        elif selection.get("kind") == "element":
            indices = {node for index in self._selection_cell_indices(selection)
                       for node in self._cells[index]["nodes"]}
            indices = [i for i, node in enumerate(self._node_ids) if node in indices]
        else:
            return False
        if not indices:
            return False
        points = [self._grid.GetPoint(i) for i in indices]
        bounds = tuple(value for axis in range(3) for value in
                       (min(point[axis] for point in points), max(point[axis] for point in points)))
        self._renderer.ResetCamera(bounds)
        self._renderer.ResetCameraClippingRange()
        self.render()
        return True

    def set_pick_mode(self, mode: str):
        self._pick_mode = mode

    def set_edges_visible(self, visible: bool):
        self._actor.GetProperty().SetEdgeVisibility(bool(visible))
        self.render()

    def fit_view(self):
        if not self._visible_indices:
            return False
        self._renderer.ResetCamera(self._visible_grid.GetBounds())
        self._renderer.ResetCameraClippingRange()
        self.render()
        return True

    def isometric_view(self):
        camera = self._renderer.GetActiveCamera()
        camera.SetPosition(1, -1, 0.8)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(0, 0, 1)
        self.fit_view()

    def standard_view(self, axis: str):
        camera = self._renderer.GetActiveCamera()
        position, up = {
            "front": ((0, -1, 0), (0, 0, 1)),
            "top": ((0, 0, 1), (0, 1, 0)),
            "right": ((1, 0, 0), (0, 0, 1)),
        }[axis]
        camera.SetPosition(*position)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(*up)
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
                indices = self._visible_grid.GetPointData().GetArray("ProjectionPointIndex")
                if indices is not None and 0 <= point_id < indices.GetNumberOfTuples():
                    point_id = int(indices.GetValue(point_id))
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
        indices = self._visible_grid.GetCellData().GetArray("ProjectionCellIndex")
        if indices is None or not 0 <= index < indices.GetNumberOfTuples():
            return
        index = int(indices.GetValue(index))
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
            self._selection = {}
            self.render()
            return
        self._selection = dict(selection)
        # Scalar edits do not rebuild geometry, but future picks use current tokens.
        self._projection_stamp["revision"] = selection.get("revision")
        self._projection_stamp["resource_revisions"] = dict(selection.get("resource_revisions", {}))
        ids = selection.get("ids", [])
        if selection.get("document_id") != self._document_id or not ids:
            self.render()
            return
        if selection.get("kind") == "node":
            indices = MeshViewport._selection_node_indices(self, selection)
            if not indices:
                self.render()
                return
            index = indices[0]
            point = self._grid.GetPoint(index)
            bounds = getattr(self, "_visible_grid", self._grid).GetBounds()
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
        indices = MeshViewport._selection_cell_indices(self, selection)
        if not indices:
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
            self._orientation.SetEnabled(0)
            self._widget.GetRenderWindow().Finalize()
            self._initialized = False
