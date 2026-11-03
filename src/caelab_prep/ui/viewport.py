"""VTK projection of mesh data with source-ID preserving selection."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget


def part_key(reference):
    """A part belongs to a resource and native scope, never an integer alone."""
    if isinstance(reference, Mapping):
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
        self._selection_visual_key = None
        self._geometry_stamp = None
        self._buffers = {}
        self._part_data = {}
        self._part_cells = {}
        self._part_nodes = {}
        self._part_slots = {}
        self._part_colors = {}
        self._cell_parts = ()
        self._element_index = {}
        self._node_index = {}
        self._applied_hidden = set()
        self._visible_cell_count = 0
        self._visible_grid = vtk.vtkMultiBlockDataSet()
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
        self._mapper = vtk.vtkCompositePolyDataMapper()
        self._mapper.SetInputDataObject(self._visible_grid)
        self._actor = vtk.vtkActor()
        self._actor.SetMapper(self._mapper)
        self._actor.GetProperty().EdgeVisibilityOn()
        self._actor.GetProperty().SetEdgeColor(0.24, 0.32, 0.4)
        self._actor.GetProperty().SetLineWidth(1.0)
        self._renderer.AddActor(self._actor)
        self._highlight = vtk.vtkActor()
        self._highlight.GetProperty().SetColor(0.95, 0.52, 0.12)
        self._highlight.GetProperty().SetRepresentationToWireframe()
        self._highlight.GetProperty().SetLineWidth(1.5)
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

    def set_mesh(self, projection: Mapping, *, reset_camera=True):
        """Build geometry once per revision; scalar commands only refresh tokens.

        The canonical projection owns its immutable cells and node identities.
        NumPy buffers below own the VTK zero-copy numeric arrays. Part surfaces
        are built once, so hiding a part changes only its composite block.
        """
        import numpy as np
        from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy

        vtk = self.vtk
        identity = (projection.get("document_id"), projection.get("document_epoch"))
        previous = (self._projection_stamp.get("document_id"), self._projection_stamp.get("document_epoch"))
        stamp = (*identity, projection.get("projection_revision"))
        self._projection_stamp = {key: projection.get(key) for key in
            ("document_id", "document_epoch", "revision", "projection_revision")}
        self._projection_stamp["resource_revisions"] = dict(projection.get("resource_revisions", {}))
        self._document_id = projection.get("document_id")
        if stamp == self._geometry_stamp and all(value is not None for value in stamp):
            if self._selection:
                self._selection = {**self._selection, **self._projection_stamp}
                self.set_selection(self._selection)
            return
        self._selection_visual_key = None
        self._highlight.SetVisibility(False)
        self._highlight.SetMapper(None)
        if identity != previous:
            self._hidden_parts.clear()
            self._selection = {}
        self._node_ids = projection.get("node_ids", ())
        self._node_resources = projection.get("node_resources", {})
        self._cells = projection.get("cells", ())
        coordinates = projection.get("points", ())
        if len(coordinates) != len(self._node_ids):
            raise ValueError("Mesh projection has inconsistent node IDs and coordinates")
        self._node_index = {node_id: i for i, node_id in enumerate(self._node_ids)}
        types = {
            "triangle": (vtk.VTK_TRIANGLE, 3), "triangle3": (vtk.VTK_TRIANGLE, 3),
            "quad": (vtk.VTK_QUAD, 4), "shell4": (vtk.VTK_QUAD, 4),
            "tetra": (vtk.VTK_TETRA, 4), "tetra4": (vtk.VTK_TETRA, 4),
            "hexahedron": (vtk.VTK_HEXAHEDRON, 8), "brick8": (vtk.VTK_HEXAHEDRON, 8),
            "line": (vtk.VTK_LINE, 2), "wedge": (vtk.VTK_WEDGE, 6),
            "pyramid": (vtk.VTK_PYRAMID, 5),
        }
        palette = np.asarray([(107, 156, 194), (119, 177, 157), (197, 159, 112),
                              (155, 145, 190), (190, 142, 153)], dtype=np.uint8)
        original_indices, cell_types, sizes, cell_parts, part_numbers = [], [], [], [], []
        part_cells, canonical_parts, self._element_index = {}, {}, {}
        omitted = 0
        for original_index, cell in enumerate(self._cells):
            spec = types.get(str(cell.get("type", "")).lower())
            nodes = cell.get("nodes", ())
            if spec is None or len(nodes) != spec[1] or any(n not in self._node_index for n in nodes):
                omitted += 1
                continue
            row = len(original_indices)
            original_indices.append(original_index)
            cell_types.append(spec[0]); sizes.append(spec[1])
            part = cell_part_key(cell)
            part = canonical_parts.setdefault(part, part)
            if part not in part_cells:
                part_cells[part] = []
            part_cells[part].append(row)
            cell_parts.append(part)
            # Keep duplicate typed IDs explicit; an ambiguous selection is refused.
            key = (cell.get("resource_id"), cell["id"])
            self._element_index[key] = None if key in self._element_index else row
        part_slots = {part: i for i, part in enumerate(part_cells)}
        part_numbers = np.fromiter((part_slots[part] % len(palette) for part in cell_parts),
                                  dtype=np.intp, count=len(cell_parts))
        offsets = np.empty(len(sizes) + 1, dtype=np.int64); offsets[0] = 0
        np.cumsum(sizes, dtype=np.int64, out=offsets[1:])
        connectivity = np.fromiter((self._node_index[node]
            for index in original_indices for node in self._cells[index]["nodes"]),
            dtype=np.int64, count=int(offsets[-1]))
        self._buffers = {
            "points": np.asarray(coordinates, dtype=np.float64).reshape((-1, 3)),
            "offsets": offsets, "connectivity": connectivity,
            "types": np.asarray(cell_types, dtype=np.uint8),
            "point_indices": np.arange(len(self._node_ids), dtype=np.int64),
            "cell_indices": np.asarray(original_indices, dtype=np.int64),
            "colors": np.ascontiguousarray(palette[part_numbers]),
        }
        points = vtk.vtkPoints()
        points.SetData(numpy_to_vtk(self._buffers["points"], deep=False))
        cells = vtk.vtkCellArray()
        cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=False),
                      numpy_to_vtkIdTypeArray(connectivity, deep=False))
        grid = vtk.vtkUnstructuredGrid(); grid.SetPoints(points)
        grid.SetCells(numpy_to_vtk(self._buffers["types"], deep=False), cells)
        colors = numpy_to_vtk(self._buffers["colors"], deep=False)
        colors.SetName("Part colour"); grid.GetCellData().SetScalars(colors)
        for attributes, values, name in (
                (grid.GetPointData(), self._buffers["point_indices"], "ProjectionPointIndex"),
                (grid.GetCellData(), self._buffers["cell_indices"], "ProjectionCellIndex")):
            indices = numpy_to_vtkIdTypeArray(values, deep=False)
            indices.SetName(name); attributes.AddArray(indices)
        self._grid = grid
        self._cell_parts = tuple(cell_parts)
        self._part_cells = {part: np.asarray(indices, dtype=np.int64) for part, indices in part_cells.items()}
        self._part_slots = part_slots
        self._part_colors = {part: "#%02x%02x%02x" % tuple(palette[slot % len(palette)])
                             for part, slot in part_slots.items() if part is not None}
        self._part_data, self._part_nodes = {}, {}
        visible = vtk.vtkMultiBlockDataSet(); visible.SetNumberOfBlocks(len(part_slots))
        for part, indices in self._part_cells.items():
            extract = vtk.vtkExtractCells(); extract.SetInputData(grid)
            extract.SetCellIds(indices, len(indices))
            extract.AssumeSortedAndUniqueIdsOn()
            surface = vtk.vtkGeometryFilter(); surface.SetInputConnection(extract.GetOutputPort())
            surface.Update()
            data = vtk.vtkPolyData(); data.ShallowCopy(surface.GetOutput())
            self._part_data[part] = data
            # Surface points need not include interior solid nodes. Logical node
            # selection uses all element connectivity, not just visible faces.
            point_rows = extract.GetOutput().GetPointData().GetArray("ProjectionPointIndex")
            self._part_nodes[part] = np.array(vtk_to_numpy(point_rows), copy=True) if point_rows is not None else np.empty(0, dtype=np.int64)
            visible.SetBlock(part_slots[part], data)
        self._visible_grid = visible
        self._mapper.SetInputDataObject(visible)
        self._mapper.SetScalarModeToUseCellData(); self._mapper.SetColorModeToDirectScalars()
        self._mapper.ScalarVisibilityOn()
        self._visible_node_counts = np.zeros(len(self._node_ids), dtype=np.int32)
        for indices in self._part_nodes.values(): self._visible_node_counts[indices] += 1
        self._visible_cell_count = len(original_indices)
        self._hidden_parts.intersection_update(part_slots)
        self._applied_hidden = set()
        self._geometry_stamp = stamp
        self._apply_visibility()
        if omitted:
            self.diagnostic.emit(f"The 3D view omitted {omitted} unsupported or unresolved elements. The deck is preserved.")
        if reset_camera and self._visible_cell_count:
            self.isometric_view()
        self.render()

    def _part_keys(self, references):
        keys = set()
        for reference in references:
            document_id = reference.get("document_id") if isinstance(reference, Mapping) else getattr(reference, "document_id", None)
            if document_id is not None and document_id != self._document_id:
                raise ValueError("The part belongs to another document")
            keys.add(part_key(reference))
        return keys

    def part_colors(self):
        """Read-only presentation colours from the same slots as VTK scalars."""
        return dict(self._part_colors)

    def hide_parts(self, part_refs):
        """Hide qualified parts without changing document selection or history."""
        self._hidden_parts.update(self._part_keys(part_refs))
        self._apply_visibility()

    def isolate_parts(self, part_refs):
        """Show only the specified parts; an empty selection is a no-op."""
        keys = self._part_keys(part_refs)
        if not keys:
            return
        available = set(self._part_data)
        if not keys & available:
            raise ValueError("None of the requested parts is present in the mesh")
        self._hidden_parts = available - keys
        self._apply_visibility()

    def show_all_parts(self):
        self._hidden_parts.clear()
        self._apply_visibility()

    def _apply_visibility(self):
        changed = self._hidden_parts ^ self._applied_hidden
        if changed:
            self._selection_visual_key = None
        for part in changed:
            if part not in self._part_slots:
                continue
            hidden = part in self._hidden_parts
            self._visible_grid.SetBlock(self._part_slots[part], None if hidden else self._part_data[part])
            direction = -1 if hidden else 1
            self._visible_node_counts[self._part_nodes[part]] += direction
            self._visible_cell_count += direction * len(self._part_cells[part])
        self._applied_hidden = set(self._hidden_parts)
        if not self._render_failed:
            self._hint.setVisible(not self._visible_cell_count)
            self._hint.setText("All elements hidden" if self._grid.GetNumberOfCells() else
                               ("No displayable elements" if self._node_ids else "No model"))
        self.set_selection(self._selection)

    def visible_cell_indices(self):
        """Explicit diagnostic snapshot; normal display/selection never expands it."""
        return sorted(int(index) for part, indices in self._part_cells.items()
                      if part not in self._hidden_parts for index in indices)

    def _visible_bounds(self):
        bounds = [0.] * 6
        self._visible_grid.GetBounds(bounds)
        return tuple(bounds)

    def _selection_cell_indices(self, selection):
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return []
        keys = {(ref.get("resource_id"), ref.get("local_id")) for ref in selection.get("refs", ())
                if ref.get("entity_kind") == "element"}
        matches = []
        for key in keys:
            index = self._element_index.get(key)
            if index is None:
                return []
            if self._cell_parts[index] not in self._hidden_parts:
                matches.append(index)
        return sorted(matches)

    def _selection_node_indices(self, selection):
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return []
        indices = set()
        for ref in selection.get("refs", ()):
            if ref.get("entity_kind") != "node": continue
            node = ref.get("local_id"); index = self._node_index.get(node)
            if (index is not None and self._visible_node_counts[index] > 0
                    and ref.get("resource_id") in self._node_resources.get(node, ())):
                indices.add(index)
        return sorted(indices)

    def fit_selection(self, selection=None):
        """Fit the visible portion of an approved selection, without revealing it."""
        selection = self._selection if selection is None else selection
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return False
        if selection.get("kind") == "node":
            indices = self._selection_node_indices(selection)
        elif selection.get("kind") == "element":
            indices = {int(node) for index in self._selection_cell_indices(selection)
                       for node in self._buffers["connectivity"][self._buffers["offsets"][index]:self._buffers["offsets"][index + 1]]}
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
        if not self._visible_cell_count:
            return False
        self._renderer.ResetCamera(self._visible_bounds())
        self._renderer.ResetCameraClippingRange()
        self.render()
        return True

    def isometric_view(self):
        camera = self._renderer.GetActiveCamera()
        camera.SetPosition(1, -1, 0.8)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(0, 0, 1)
        self.fit_view()

    def orient_view(self, direction, up):
        """Fit the visible mesh along an explicit source direction."""
        camera = self._renderer.GetActiveCamera()
        camera.SetPosition(*direction)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(*up)
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
                data = picker.GetDataSet()
                indices = data.GetPointData().GetArray("ProjectionPointIndex") if data is not None else None
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
        data = picker.GetDataSet()
        indices = data.GetCellData().GetArray("ProjectionCellIndex") if data is not None else None
        if indices is None or not 0 <= index < indices.GetNumberOfTuples():
            return
        index = int(indices.GetValue(index))
        if not 0 <= index < len(self._cells):
            return
        cell = self._cells[index]
        self.entityPicked.emit({**pick_candidate(self._projection_stamp, "element", cell["id"], cell.get("resource_id")), "part_id": cell.get("part_id"),
                                "resource_id": cell.get("resource_id"), "card_id": cell.get("card_id")})

    def set_selection(self, selection):
        """Only an approved canonical selection changes geometry or highlight.

        A scalar document revision changes pick tokens, not the displayed mesh.
        Preserve the highlight pipeline and avoid a full render in that case.
        """
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            self._selection = {}
            self._selection_visual_key = None
            self._highlight.SetVisibility(False)
            self._highlight.SetMapper(None)
            self.render()
            return
        self._selection = dict(selection)
        # Scalar edits do not rebuild geometry, but future picks use current tokens.
        self._projection_stamp["revision"] = selection.get("revision")
        self._projection_stamp["resource_revisions"] = dict(selection.get("resource_revisions", {}))
        key = (selection.get("document_id"), selection.get("document_epoch"),
               selection.get("projection_revision"), selection.get("kind"), tuple(selection.get("ids", ())),
               tuple((ref.get("resource_id"), ref.get("entity_kind"), ref.get("local_id"))
                     for ref in selection.get("refs", ())))
        if key == self._selection_visual_key:
            return
        self._selection_visual_key = key
        self._highlight.SetVisibility(False)
        self._highlight.SetMapper(None)
        ids = selection.get("ids", [])
        if selection.get("document_id") != self._document_id or not ids:
            self.render()
            return
        if selection.get("kind") == "node":
            indices = MeshViewport._selection_node_indices(self, selection)
            if not indices:
                self.render()
                return
            bounds = self._visible_bounds()
            span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1e-9)
            points = self.vtk.vtkPoints()
            for index in indices:
                points.InsertNextPoint(self._grid.GetPoint(index))
            nodes = self.vtk.vtkPolyData()
            nodes.SetPoints(points)
            sphere = self.vtk.vtkSphereSource()
            sphere.SetRadius(span * 0.012)
            sphere.SetThetaResolution(16)
            sphere.SetPhiResolution(12)
            mapper = self.vtk.vtkGlyph3DMapper()
            mapper.SetInputData(nodes)
            mapper.SetSourceConnection(sphere.GetOutputPort())
            mapper.ScalingOff()
            prop = self._highlight.GetProperty()
            prop.SetRepresentationToSurface()
            prop.SetColor(0.95, 0.52, 0.12)
            prop.SetOpacity(1.0)
            prop.EdgeVisibilityOff()
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
        # Build only selected cells. Extracting a tiny selection from the full
        # grid can allocate a point map sized to the entire million-node model.
        highlight = vtk.vtkUnstructuredGrid()
        points = vtk.vtkPoints(); points.SetDataTypeToDouble()
        point_indices = vtk.vtkIdTypeArray(); point_indices.SetName("ProjectionPointIndex")
        cell_indices = vtk.vtkIdTypeArray(); cell_indices.SetName("ProjectionCellIndex")
        selected_points = {}
        for index in indices:
            ids = vtk.vtkIdList()
            start, stop = self._buffers["offsets"][index:index + 2]
            for node in self._buffers["connectivity"][start:stop]:
                node = int(node)
                if node not in selected_points:
                    selected_points[node] = points.InsertNextPoint(self._buffers["points"][node])
                    point_indices.InsertNextValue(node)
                ids.InsertNextId(selected_points[node])
            highlight.InsertNextCell(int(self._buffers["types"][index]), ids)
            cell_indices.InsertNextValue(int(self._buffers["cell_indices"][index]))
        highlight.SetPoints(points)
        highlight.GetPointData().AddArray(point_indices)
        highlight.GetCellData().AddArray(cell_indices)
        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputData(highlight)
        mapper.ScalarVisibilityOff()
        prop = self._highlight.GetProperty()
        prop.SetRepresentationToSurface()
        prop.SetColor(0.95, 0.52, 0.12)
        prop.SetOpacity(0.35)
        prop.EdgeVisibilityOn()
        prop.SetEdgeColor(0.95, 0.52, 0.12)
        prop.SetLineWidth(1.5)
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
