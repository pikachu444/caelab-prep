"""VTK projection of mesh data with source-ID preserving selection."""

from __future__ import annotations

from collections.abc import Mapping
import math
import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .design import element_family_palette, tokens_for_theme


_OFFSCREEN_FONTS_CHECKED = False


def ensure_windows_offscreen_fonts() -> None:
    """Register Windows UI fonts when running under QT_QPA_PLATFORM=offscreen."""
    global _OFFSCREEN_FONTS_CHECKED
    if _OFFSCREEN_FONTS_CHECKED or os.name != "nt":
        return
    if QGuiApplication.instance() is None or QGuiApplication.platformName() != "offscreen":
        return
    _OFFSCREEN_FONTS_CHECKED = True
    existing = set(QFontDatabase.families())
    if "Malgun Gothic" in existing and "Segoe UI" in existing:
        return
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for fname in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf", "segoeuib.ttf"):
        fpath = fonts_dir / fname
        if fpath.is_file():
            QFontDatabase.addApplicationFont(str(fpath))


SOLID_ELEMENT_FAMILIES = (
    "Hex8",
    "Wedge6",
    "Pyramid5",
    "Tet4",
    "Tet10",
    "Hex20",
    "Wedge15",
)

ELEMENT_FAMILY_ORDER = (
    *SOLID_ELEMENT_FAMILIES,
    "Quad4",
    "Tri3",
    "Quad8",
    "Tri6",
    "Line2",
)

_CELL_SPECS = {
    "triangle": ("VTK_TRIANGLE", 3, "Tri3"),
    "triangle3": ("VTK_TRIANGLE", 3, "Tri3"),
    "tri3": ("VTK_TRIANGLE", 3, "Tri3"),
    "triangle 3": ("VTK_TRIANGLE", 3, "Tri3"),
    "triangle6": ("VTK_QUADRATIC_TRIANGLE", 6, "Tri6"),
    "tri6": ("VTK_QUADRATIC_TRIANGLE", 6, "Tri6"),
    "triangle 6": ("VTK_QUADRATIC_TRIANGLE", 6, "Tri6"),
    "quad": ("VTK_QUAD", 4, "Quad4"),
    "quad4": ("VTK_QUAD", 4, "Quad4"),
    "shell4": ("VTK_QUAD", 4, "Quad4"),
    "quadrilateral 4": ("VTK_QUAD", 4, "Quad4"),
    "quad8": ("VTK_QUADRATIC_QUAD", 8, "Quad8"),
    "quadrilateral 8": ("VTK_QUADRATIC_QUAD", 8, "Quad8"),
    "tetra": ("VTK_TETRA", 4, "Tet4"),
    "tetra4": ("VTK_TETRA", 4, "Tet4"),
    "tet4": ("VTK_TETRA", 4, "Tet4"),
    "tetrahedron 4": ("VTK_TETRA", 4, "Tet4"),
    "tetra10": ("VTK_QUADRATIC_TETRA", 10, "Tet10"),
    "tet10": ("VTK_QUADRATIC_TETRA", 10, "Tet10"),
    "tetrahedron 10": ("VTK_QUADRATIC_TETRA", 10, "Tet10"),
    "hexahedron": ("VTK_HEXAHEDRON", 8, "Hex8"),
    "brick8": ("VTK_HEXAHEDRON", 8, "Hex8"),
    "hex8": ("VTK_HEXAHEDRON", 8, "Hex8"),
    "hexahedron 8": ("VTK_HEXAHEDRON", 8, "Hex8"),
    "hex20": ("VTK_QUADRATIC_HEXAHEDRON", 20, "Hex20"),
    "hexahedron20": ("VTK_QUADRATIC_HEXAHEDRON", 20, "Hex20"),
    "hexahedron 20": ("VTK_QUADRATIC_HEXAHEDRON", 20, "Hex20"),
    "wedge": ("VTK_WEDGE", 6, "Wedge6"),
    "wedge6": ("VTK_WEDGE", 6, "Wedge6"),
    "prism6": ("VTK_WEDGE", 6, "Wedge6"),
    "prism 6": ("VTK_WEDGE", 6, "Wedge6"),
    "wedge15": ("VTK_QUADRATIC_WEDGE", 15, "Wedge15"),
    "prism15": ("VTK_QUADRATIC_WEDGE", 15, "Wedge15"),
    "prism 15": ("VTK_QUADRATIC_WEDGE", 15, "Wedge15"),
    "pyramid": ("VTK_PYRAMID", 5, "Pyramid5"),
    "pyramid5": ("VTK_PYRAMID", 5, "Pyramid5"),
    "pyramid 5": ("VTK_PYRAMID", 5, "Pyramid5"),
    "line": ("VTK_LINE", 2, "Line2"),
    "line2": ("VTK_LINE", 2, "Line2"),
    "line 2": ("VTK_LINE", 2, "Line2"),
}

_KO_FAMILY_CHIP_LABELS = {
    "Hex8": "육면체(Hex8)",
    "Wedge6": "쐐기(Wedge6)",
    "Pyramid5": "피라미드(Pyramid5)",
    "Tet4": "사면체(Tet4)",
    "Tet10": "2차사면체(Tet10)",
    "Hex20": "2차육면체(Hex20)",
    "Wedge15": "2차쐐기(Wedge15)",
    "Quad4": "사각셸(Quad4)",
    "Tri3": "삼각셸(Tri3)",
    "Quad8": "2차사각(Quad8)",
    "Tri6": "2차삼각(Tri6)",
    "Line2": "선요소(Line2)",
}

_KO_FAMILY_TOOLTIPS = {
    "Hex8": "8절점 육면체 솔리드 요소 (Hex8)",
    "Wedge6": "6절점 쐐기형 솔리드 요소 (Wedge6)",
    "Pyramid5": "5절점 피라미드 천이 요소 (Pyramid5)",
    "Tet4": "4절점 사면체 솔리드 요소 (Tet4)",
    "Tet10": "10절점 2차 사면체 요소 (Tet10)",
    "Hex20": "20절점 2차 육면체 요소 (Hex20)",
    "Wedge15": "15절점 2차 쐐기형 요소 (Wedge15)",
    "Quad4": "4절점 사각형 요소 (Quad4)",
    "Tri3": "3절점 삼각형 요소 (Tri3)",
    "Quad8": "8절점 2차 사각형 요소 (Quad8)",
    "Tri6": "6절점 2차 삼각형 요소 (Tri6)",
    "Line2": "2절점 선 요소 (Line2)",
}

_EN_FAMILY_TOOLTIPS = {
    "Hex8": "8-node hexahedral solid elements (Hex8)",
    "Wedge6": "6-node wedge/prism solid elements (Wedge6)",
    "Pyramid5": "5-node pyramid transition elements (Pyramid5)",
    "Tet4": "4-node tetrahedral solid elements (Tet4)",
    "Tet10": "10-node quadratic tetrahedral elements (Tet10)",
    "Hex20": "20-node quadratic hexahedral elements (Hex20)",
    "Wedge15": "15-node quadratic wedge elements (Wedge15)",
    "Quad4": "4-node quadrilateral elements (Quad4)",
    "Tri3": "3-node triangular elements (Tri3)",
    "Quad8": "8-node quadratic quadrilateral elements (Quad8)",
    "Tri6": "6-node quadratic triangular elements (Tri6)",
    "Line2": "2-node line elements (Line2)",
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    token = hex_color.strip().lstrip("#")
    return int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16)


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
    inspectionStateChanged = Signal()

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
        self._active_part_data = {}
        self._active_part_cells = {}
        self._active_part_nodes = {}
        self._poly_color_buffers = {}
        self._part_slots = {}
        self._part_colors = {}
        self._cell_parts = ()
        self._cell_families = ()
        self._present_families = ()
        self._family_counts = {}
        self._element_index = {}
        self._node_index = {}
        self._applied_hidden = set()
        self._visibility_applied = False
        self._visible_cell_count = 0
        self._visible_node_counts = None
        self._visible_grid = vtk.vtkMultiBlockDataSet()
        self._render_failed = False
        self._pick_mode = "element"
        self._theme_mode = "light"
        self._color_mode = "part"
        self._slice_axis: str | None = None
        self._slice_fraction: float = 0.5
        self._slice_flip: bool = False
        self._slice_mask = None
        self._grid = vtk.vtkUnstructuredGrid()
        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(0.84, 0.87, 0.90)
        self._renderer.SetBackground2(0.97, 0.98, 0.985)
        self._renderer.GradientBackgroundOn()
        self._renderer.GetActiveCamera().ParallelProjectionOn()
        self._offscreen_qpa = os.name == "nt" and QGuiApplication.platformName() == "offscreen"
        if self._offscreen_qpa:
            class _OffscreenSafeInteractor(QVTKRenderWindowInteractor):
                def paintEngine(self_w):
                    return QWidget.paintEngine(self_w)

                def resizeEvent(self_w, ev):
                    w = max(1, self_w.width())
                    h = max(1, self_w.height())
                    self_w._RenderWindow.SetSize(w, h)
                    self_w._Iren.SetSize(w, h)

                def paintEvent(self_w, ev):
                    if not self._initialized:
                        return
                    w = max(1, self_w.width())
                    h = max(1, self_w.height())
                    self_w._RenderWindow.SetSize(w, h)
                    self_w._RenderWindow.Render()
                    w2i = vtk.vtkWindowToImageFilter()
                    w2i.SetInput(self_w._RenderWindow)
                    w2i.SetInputBufferTypeToRGBA()
                    w2i.ReadFrontBufferOff()
                    w2i.Update()
                    img_data = w2i.GetOutput()
                    dims = img_data.GetDimensions()
                    scalars = img_data.GetPointData().GetScalars()
                    if scalars is not None and dims[0] > 0 and dims[1] > 0:
                        from vtkmodules.util.numpy_support import vtk_to_numpy
                        import numpy as np
                        arr = np.flipud(vtk_to_numpy(scalars).reshape(dims[1], dims[0], 4)).copy()
                        qimg = QImage(arr.data, dims[0], dims[1], dims[0] * 4, QImage.Format.Format_RGBA8888)
                        painter = QPainter(self_w)
                        painter.drawImage(self_w.rect(), qimg)
                        painter.end()

            self._widget = _OffscreenSafeInteractor(self)
            offscreen_rw = vtk.vtkRenderWindow()
            offscreen_rw.SetOffScreenRendering(1)
            offscreen_rw.SetSize(640, 480)
            self._widget._RenderWindow = offscreen_rw
            self._widget._Iren.SetRenderWindow(offscreen_rw)
            self._widget.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, False)
            self._widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        else:
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
        if hasattr(vtk.vtkMapper, "SetResolveCoincidentTopologyToPolygonOffset"):
            vtk.vtkMapper.SetResolveCoincidentTopologyToPolygonOffset()
        self._mapper = vtk.vtkCompositePolyDataMapper()
        self._mapper.SetInputDataObject(self._visible_grid)
        if hasattr(self._mapper, "SetResolveCoincidentTopologyToPolygonOffset"):
            self._mapper.SetResolveCoincidentTopologyToPolygonOffset()
        if hasattr(self._mapper, "SetRelativeCoincidentTopologyPolygonOffsetParameters"):
            self._mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(1, 1)
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
        self._hint.setStyleSheet(
            "color: #f47067; background: #3a1e20; padding: 18px;"
            if self._theme_mode == "dark"
            else "color: #8c3030; background: #fff6f4; padding: 18px;"
        )
        self._hint.show()
        self.diagnostic.emit("The 3D renderer reported an error. Check the graphics driver or rendering environment. The model document remains available.")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            if self._offscreen_qpa:
                w = max(1, self._widget.width())
                h = max(1, self._widget.height())
                self._widget.GetRenderWindow().SetSize(w, h)
                self._initialized = True
            else:
                self._widget.Initialize()
                self._orientation.SetEnabled(1)
                self._orientation.InteractiveOff()
                self._initialized = True

    def _compute_active_colors(self):
        import numpy as np

        if not self._buffers:
            return np.zeros((0, 3), dtype=np.uint8)
        if self._color_mode == "part":
            return self._buffers["part_colors"]
        palette = element_family_palette(self._theme_mode)
        ordered = self._buffers["family_order"]
        if not ordered:
            return np.zeros((0, 3), dtype=np.uint8)
        rgb_table = np.asarray([_hex_to_rgb(palette[fam]) for fam in ordered], dtype=np.uint8)
        return np.ascontiguousarray(rgb_table[self._buffers["family_slots"]])

    def _apply_colors_to_polydata(self, data, active_colors):
        import numpy as np
        from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy

        if data is None:
            return
        row_arr = data.GetCellData().GetArray("GridCellRow")
        if row_arr is not None and row_arr.GetNumberOfTuples() > 0:
            rows = vtk_to_numpy(row_arr)
            poly_colors = np.ascontiguousarray(active_colors[rows])
        else:
            poly_colors = np.zeros((0, 3), dtype=np.uint8)
        self._poly_color_buffers[id(data)] = poly_colors
        scalars = numpy_to_vtk(poly_colors, deep=False)
        scalars.SetName("Element family colour" if self._color_mode == "element_family" else "Part colour")
        data.GetCellData().SetScalars(scalars)
        data.Modified()

    def _refresh_cell_colors(self):
        from vtkmodules.util.numpy_support import numpy_to_vtk

        if not self._buffers:
            return
        active_colors = self._compute_active_colors()
        self._buffers["colors"] = active_colors
        scalars = numpy_to_vtk(active_colors, deep=False)
        scalars.SetName("Element family colour" if self._color_mode == "element_family" else "Part colour")
        self._grid.GetCellData().SetScalars(scalars)
        self._grid.Modified()
        seen = {}
        for d in (*self._part_data.values(), *self._active_part_data.values()):
            if d is not None:
                seen[id(d)] = d
        for d in seen.values():
            self._apply_colors_to_polydata(d, active_colors)
        self._mapper.Modified()

    def _rebuild_slice_pipeline(self):
        import numpy as np
        from vtkmodules.util.numpy_support import vtk_to_numpy

        # Drop stale sliced polydata buffer refs while retaining base _part_data refs.
        base_ids = {id(d) for d in self._part_data.values() if d is not None}
        self._poly_color_buffers = {k: v for k, v in self._poly_color_buffers.items() if k in base_ids}

        if not self._buffers or len(self._buffers["types"]) == 0 or self._slice_axis is None:
            self._slice_mask = None
            self._active_part_cells = dict(self._part_cells)
            self._active_part_data = dict(self._part_data)
            self._active_part_nodes = dict(self._part_nodes)
            return

        if "centroids" not in self._buffers:
            pts = self._buffers["points"]
            conn = self._buffers["connectivity"]
            offs = self._buffers["offsets"]
            sizes = np.diff(offs)
            conn_pts = pts[conn]
            self._buffers["centroids"] = np.add.reduceat(conn_pts, offs[:-1], axis=0) / sizes[:, None]
            self._buffers["used_min"] = conn_pts.min(axis=0)
            self._buffers["used_max"] = conn_pts.max(axis=0)

        axis_idx = {"x": 0, "y": 1, "z": 2}[self._slice_axis]
        lo = float(self._buffers["used_min"][axis_idx])
        hi = float(self._buffers["used_max"][axis_idx])
        cut = lo + self._slice_fraction * (hi - lo)
        coord = self._buffers["centroids"][:, axis_idx]
        mask = (coord >= cut) if self._slice_flip else (coord <= cut)
        self._slice_mask = mask

        vtk = self.vtk
        active_colors = self._buffers["colors"]
        self._active_part_cells = {}
        self._active_part_data = {}
        self._active_part_nodes = {}
        for part, full_indices in self._part_cells.items():
            kept = full_indices[mask[full_indices]]
            self._active_part_cells[part] = kept
            if len(kept) == 0:
                self._active_part_data[part] = None
                self._active_part_nodes[part] = np.empty(0, dtype=np.int64)
            elif len(kept) == len(full_indices):
                self._active_part_data[part] = self._part_data[part]
                self._active_part_nodes[part] = self._part_nodes[part]
            else:
                extract = vtk.vtkExtractCells()
                extract.SetInputData(self._grid)
                extract.SetCellIds(kept, len(kept))
                extract.AssumeSortedAndUniqueIdsOn()
                surface = vtk.vtkGeometryFilter()
                surface.SetInputConnection(extract.GetOutputPort())
                surface.Update()
                data = vtk.vtkPolyData()
                data.ShallowCopy(surface.GetOutput())
                self._apply_colors_to_polydata(data, active_colors)
                self._active_part_data[part] = data
                point_rows = extract.GetOutput().GetPointData().GetArray("ProjectionPointIndex")
                self._active_part_nodes[part] = (
                    np.array(vtk_to_numpy(point_rows), copy=True)
                    if point_rows is not None
                    else np.empty(0, dtype=np.int64)
                )

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
            key: (getattr(vtk, vtk_attr), arity, family)
            for key, (vtk_attr, arity, family) in _CELL_SPECS.items()
        }
        palette = np.asarray([(107, 156, 194), (119, 177, 157), (197, 159, 112),
                              (155, 145, 190), (190, 142, 153)], dtype=np.uint8)
        original_indices, cell_types, sizes, cell_parts, cell_families = [], [], [], [], []
        family_counts = {}
        part_cells, canonical_parts, self._element_index = {}, {}, {}
        omitted = 0
        for original_index, cell in enumerate(self._cells):
            spec = types.get(str(cell.get("type", "")).strip().lower())
            nodes = cell.get("nodes", ())
            if spec is None or len(nodes) != spec[1] or any(n not in self._node_index for n in nodes):
                omitted += 1
                continue
            row = len(original_indices)
            original_indices.append(original_index)
            cell_types.append(spec[0])
            sizes.append(spec[1])
            family = spec[2]
            cell_families.append(family)
            family_counts[family] = family_counts.get(family, 0) + 1
            part = cell_part_key(cell)
            part = canonical_parts.setdefault(part, part)
            if part not in part_cells:
                part_cells[part] = []
            part_cells[part].append(row)
            cell_parts.append(part)
            # Keep duplicate typed IDs explicit; an ambiguous selection is refused.
            key = (cell.get("resource_id"), cell["id"])
            qualified = (*key, cell.get("formulation"))
            self._element_index[qualified] = None if qualified in self._element_index else row
            self._element_index[key] = None if key in self._element_index else row
        part_slots = {part: i for i, part in enumerate(part_cells)}
        part_numbers = np.fromiter((part_slots[part] % len(palette) for part in cell_parts),
                                  dtype=np.intp, count=len(cell_parts))
        present_families = tuple(fam for fam in ELEMENT_FAMILY_ORDER if fam in family_counts)
        family_slot_map = {fam: idx for idx, fam in enumerate(present_families)}
        family_slots = np.fromiter((family_slot_map[fam] for fam in cell_families),
                                   dtype=np.intp, count=len(cell_families))
        offsets = np.empty(len(sizes) + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(sizes, dtype=np.int64, out=offsets[1:])
        connectivity = np.fromiter((self._node_index[node]
            for index in original_indices for node in self._cells[index]["nodes"]),
            dtype=np.int64, count=int(offsets[-1]))
        part_colors_buf = np.ascontiguousarray(palette[part_numbers])
        self._cell_families = tuple(cell_families)
        self._present_families = present_families
        self._family_counts = dict(family_counts)
        self._buffers = {
            "points": np.asarray(coordinates, dtype=np.float64).reshape((-1, 3)),
            "offsets": offsets,
            "connectivity": connectivity,
            "types": np.asarray(cell_types, dtype=np.uint8),
            "point_indices": np.arange(len(self._node_ids), dtype=np.int64),
            "cell_indices": np.asarray(original_indices, dtype=np.int64),
            "grid_rows": np.arange(len(original_indices), dtype=np.int64),
            "part_colors": part_colors_buf,
            "family_order": present_families,
            "family_slots": family_slots,
        }
        active_colors = self._compute_active_colors()
        self._buffers["colors"] = active_colors
        points = vtk.vtkPoints()
        points.SetData(numpy_to_vtk(self._buffers["points"], deep=False))
        cells = vtk.vtkCellArray()
        cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=False),
                      numpy_to_vtkIdTypeArray(connectivity, deep=False))
        grid = vtk.vtkUnstructuredGrid()
        grid.SetPoints(points)
        grid.SetCells(numpy_to_vtk(self._buffers["types"], deep=False), cells)
        colors = numpy_to_vtk(self._buffers["colors"], deep=False)
        colors.SetName("Element family colour" if self._color_mode == "element_family" else "Part colour")
        grid.GetCellData().SetScalars(colors)
        for attributes, values, name in (
                (grid.GetPointData(), self._buffers["point_indices"], "ProjectionPointIndex"),
                (grid.GetCellData(), self._buffers["cell_indices"], "ProjectionCellIndex"),
                (grid.GetCellData(), self._buffers["grid_rows"], "GridCellRow")):
            indices = numpy_to_vtkIdTypeArray(values, deep=False)
            indices.SetName(name)
            attributes.AddArray(indices)
        self._grid = grid
        self._cell_parts = tuple(cell_parts)
        self._part_cells = {part: np.asarray(indices, dtype=np.int64) for part, indices in part_cells.items()}
        self._part_slots = part_slots
        self._part_colors = {part: "#%02x%02x%02x" % tuple(palette[slot % len(palette)])
                             for part, slot in part_slots.items() if part is not None}
        self._part_data, self._part_nodes, self._poly_color_buffers = {}, {}, {}
        for part, indices in self._part_cells.items():
            extract = vtk.vtkExtractCells()
            extract.SetInputData(grid)
            extract.SetCellIds(indices, len(indices))
            extract.AssumeSortedAndUniqueIdsOn()
            surface = vtk.vtkGeometryFilter()
            surface.SetInputConnection(extract.GetOutputPort())
            surface.Update()
            data = vtk.vtkPolyData()
            data.ShallowCopy(surface.GetOutput())
            self._apply_colors_to_polydata(data, active_colors)
            self._part_data[part] = data
            # Surface points need not include interior solid nodes. Logical node
            # selection uses all element connectivity, not just visible faces.
            point_rows = extract.GetOutput().GetPointData().GetArray("ProjectionPointIndex")
            self._part_nodes[part] = np.array(vtk_to_numpy(point_rows), copy=True) if point_rows is not None else np.empty(0, dtype=np.int64)

        self._rebuild_slice_pipeline()
        visible = vtk.vtkMultiBlockDataSet()
        visible.SetNumberOfBlocks(len(part_slots))
        self._visible_grid = visible
        self._mapper.SetInputDataObject(visible)
        self._mapper.SetScalarModeToUseCellData()
        self._mapper.SetColorModeToDirectScalars()
        self._mapper.ScalarVisibilityOn()
        self._hidden_parts.intersection_update(part_slots)
        self._applied_hidden = set()
        self._visibility_applied = False
        self._geometry_stamp = stamp
        self._apply_visibility(force=True)
        if omitted:
            self.diagnostic.emit(f"The 3D view omitted {omitted} unsupported or unresolved elements. The deck is preserved.")
        if reset_camera and self._visible_cell_count:
            self.isometric_view()
        self.inspectionStateChanged.emit()
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

    def color_mode(self) -> str:
        return self._color_mode

    def element_family_colors(self, *, all_families: bool = False) -> dict[str, str]:
        """Active hex colour mapping for element families matching VTK cell scalars."""
        palette = element_family_palette(self._theme_mode)
        if all_families or not self._present_families:
            keys = list(SOLID_ELEMENT_FAMILIES)
            for fam in self._present_families:
                if fam not in keys:
                    keys.append(fam)
            return {fam: palette[fam] for fam in keys}
        return {fam: palette[fam] for fam in self._present_families}

    def element_family_counts(self) -> dict[str, int]:
        return dict(self._family_counts)

    def set_color_mode(self, mode: str):
        norm = str(mode).strip().lower()
        if norm not in ("part", "element_family"):
            raise ValueError("Color mode must be 'part' or 'element_family'")
        if norm == self._color_mode:
            return
        self._color_mode = norm
        self._refresh_cell_colors()
        self.inspectionStateChanged.emit()
        self.render()

    def section_slice(self) -> dict[str, object]:
        return {
            "axis": self._slice_axis,
            "fraction": self._slice_fraction,
            "flip": self._slice_flip,
        }

    def set_section_slice(self, axis: str | None = None, fraction: float = 0.5, *, flip: bool = False):
        """Crinkle-cut 3D volume cells by centroid along a coordinate axis."""
        if axis is None:
            norm_axis = None
        elif isinstance(axis, str) and axis.strip().lower() in ("", "off", "none"):
            norm_axis = None
        elif isinstance(axis, str) and axis.strip().lower() in ("x", "y", "z"):
            norm_axis = axis.strip().lower()
        else:
            raise ValueError("Section slice axis must be 'x', 'y', 'z' or None")

        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
            raise ValueError("Section slice fraction must be a finite number between 0.0 and 1.0")
        norm_fraction = float(fraction)
        if not math.isfinite(norm_fraction) or not 0.0 <= norm_fraction <= 1.0:
            raise ValueError("Section slice fraction must be between 0.0 and 1.0")
        norm_flip = bool(flip)

        if (norm_axis == self._slice_axis
                and norm_fraction == self._slice_fraction
                and norm_flip == self._slice_flip):
            return
        self._slice_axis = norm_axis
        self._slice_fraction = norm_fraction
        self._slice_flip = norm_flip
        self._rebuild_slice_pipeline()
        self._apply_visibility(force=True)
        self.inspectionStateChanged.emit()
        self.render()

    def set_hidden_parts(self, part_refs):
        """Atomically apply the target hidden part set in a single delta pass."""
        self._hidden_parts = self._part_keys(part_refs)
        self._apply_visibility()

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

    def _apply_visibility(self, *, force: bool = False):
        import numpy as np

        if force:
            self._visible_node_counts = np.zeros(len(self._node_ids), dtype=np.int32)
            self._visible_cell_count = 0
            for part, slot in self._part_slots.items():
                hidden = part in self._hidden_parts
                block = None if hidden else self._active_part_data.get(part)
                self._visible_grid.SetBlock(slot, block)
                if not hidden:
                    nodes = self._active_part_nodes.get(part)
                    if nodes is not None and len(nodes):
                        self._visible_node_counts[nodes] += 1
                    self._visible_cell_count += len(self._active_part_cells.get(part, ()))
            self._visible_grid.Modified()
            self._applied_hidden = set(self._hidden_parts)
            self._visibility_applied = True
            self._selection_visual_key = None
            if not self._render_failed:
                self._hint.setVisible(not self._visible_cell_count)
                self._hint.setText("All elements hidden" if self._grid.GetNumberOfCells() else
                                   ("No displayable elements" if self._node_ids else "No model"))
            self.set_selection(self._selection)
            return

        changed = self._hidden_parts ^ self._applied_hidden
        if not changed and self._visibility_applied and (not self._selection or self._selection_visual_key is not None):
            return
        blocks_changed = False
        for part in changed:
            if part not in self._part_slots:
                continue
            blocks_changed = True
            hidden = part in self._hidden_parts
            self._visible_grid.SetBlock(self._part_slots[part], None if hidden else self._active_part_data.get(part))
            direction = -1 if hidden else 1
            nodes = self._active_part_nodes.get(part)
            if nodes is not None and len(nodes):
                self._visible_node_counts[nodes] += direction
            self._visible_cell_count += direction * len(self._active_part_cells.get(part, ()))
        self._applied_hidden = set(self._hidden_parts)
        first_apply = not self._visibility_applied
        self._visibility_applied = True
        if blocks_changed:
            self._selection_visual_key = None
        if (first_apply or blocks_changed) and not self._render_failed:
            self._hint.setVisible(not self._visible_cell_count)
            self._hint.setText("All elements hidden" if self._grid.GetNumberOfCells() else
                               ("No displayable elements" if self._node_ids else "No model"))
        if first_apply or blocks_changed or (self._selection and self._selection_visual_key is None):
            self.set_selection(self._selection)

    def visible_cell_indices(self):
        """Explicit diagnostic snapshot; normal display/selection never expands it."""
        return sorted(int(index) for part, indices in self._active_part_cells.items()
                      if part not in self._hidden_parts for index in indices)

    def _visible_bounds(self):
        bounds = [0.] * 6
        self._visible_grid.GetBounds(bounds)
        return tuple(bounds)

    def _selection_cell_indices(self, selection):
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return []
        keys = {(ref.get("resource_id"), ref.get("local_id"), ref.get("formulation")) for ref in selection.get("refs", ())
                if ref.get("entity_kind") == "element"}
        matches = []
        for key in keys:
            index = self._element_index.get(key[:2] if key[2] is None else key)
            if index is None:
                return []
            if (self._cell_parts[index] not in self._hidden_parts
                    and (self._slice_mask is None or bool(self._slice_mask[index]))):
                matches.append(index)
        return sorted(matches)

    def _selection_node_indices(self, selection):
        if any(selection.get(key) != self._projection_stamp.get(key) for key in
               ("document_id", "document_epoch", "projection_revision")):
            return []
        indices = set()
        for ref in selection.get("refs", ()):
            if ref.get("entity_kind") != "node":
                continue
            node = ref.get("local_id")
            index = self._node_index.get(node)
            if (index is not None and self._visible_node_counts is not None
                    and self._visible_node_counts[index] > 0
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

    def set_theme_mode(self, mode: str):
        dark = str(mode).strip().lower() == "dark"
        self._theme_mode = "dark" if dark else "light"
        if dark:
            self._renderer.SetBackground(0.09, 0.12, 0.16)
            self._renderer.SetBackground2(0.16, 0.21, 0.27)
            caption_color = (0.86, 0.90, 0.95)
            edge_color = (0.76, 0.84, 0.93)
        else:
            self._renderer.SetBackground(0.84, 0.87, 0.90)
            self._renderer.SetBackground2(0.97, 0.98, 0.985)
            caption_color = (0.16, 0.20, 0.24)
            edge_color = (0.24, 0.32, 0.4)
        self._renderer.GradientBackgroundOn()
        for caption in (
            self._axes.GetXAxisCaptionActor2D(),
            self._axes.GetYAxisCaptionActor2D(),
            self._axes.GetZAxisCaptionActor2D(),
        ):
            caption.GetCaptionTextProperty().SetColor(*caption_color)
        self._actor.GetProperty().SetEdgeColor(*edge_color)
        if self._render_failed:
            self._hint.setStyleSheet(
                "color: #f47067; background: #3a1e20; padding: 18px;"
                if dark
                else "color: #8c3030; background: #fff6f4; padding: 18px;"
            )
        if self._color_mode == "element_family" and self._buffers:
            self._refresh_cell_colors()
        self.inspectionStateChanged.emit()
        self.render()

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
        candidate = pick_candidate(self._projection_stamp, "element", cell["id"], cell.get("resource_id"))
        candidate.update(part_id=cell.get("part_id"), card_id=cell.get("card_id"))
        self.entityPicked.emit(candidate)

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
               tuple((ref.get("resource_id"), ref.get("entity_kind"), ref.get("local_id"), ref.get("formulation"))
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
        points = vtk.vtkPoints()
        points.SetDataTypeToDouble()
        point_indices = vtk.vtkIdTypeArray()
        point_indices.SetName("ProjectionPointIndex")
        cell_indices = vtk.vtkIdTypeArray()
        cell_indices.SetName("ProjectionCellIndex")
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
        if hasattr(vtk.vtkMapper, "SetResolveCoincidentTopologyToPolygonOffset"):
            vtk.vtkMapper.SetResolveCoincidentTopologyToPolygonOffset()
        if hasattr(mapper, "SetResolveCoincidentTopologyToPolygonOffset"):
            mapper.SetResolveCoincidentTopologyToPolygonOffset()
        if hasattr(mapper, "SetRelativeCoincidentTopologyPolygonOffsetParameters"):
            mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        if hasattr(mapper, "SetRelativeCoincidentTopologyLineOffsetParameters"):
            mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2, -2)
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
            if not self._offscreen_qpa:
                self._orientation.SetEnabled(0)
            self._widget.GetRenderWindow().Finalize()
            self._initialized = False


class _ChipFlowLayout(QLayout):
    """Left-aligned wrapping flow layout for element-family legend chips."""

    def __init__(self, parent: QWidget | None = None, *, h_spacing: int = 5, v_spacing: int = 3):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, max(0, width), 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        max_h = 0
        for item in self._items:
            w = item.widget()
            ih = w.minimumHeight() if w is not None else item.minimumSize().height()
            max_h = max(max_h, ih)
        m = self.contentsMargins()
        return QSize(0, max_h + m.top() + m.bottom())

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = eff.x()
        y = eff.y()
        line_height = 0
        for item in self._items:
            w = item.widget()
            sz = w.minimumSize().expandedTo(w.sizeHint()).boundedTo(w.maximumSize()) if w is not None else item.sizeHint()
            next_x = x + sz.width() + self._h_spacing
            if line_height > 0 and x + sz.width() > eff.right() + 1:
                x = eff.x()
                y = y + line_height + self._v_spacing
                next_x = x + sz.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x = next_x
            line_height = max(line_height, sz.height())
        return (y + line_height - rect.y()) + m.bottom()


class ViewportInspectionBar(QFrame):
    """Compact inline 3D inspection strip for crinkle-cut slicing and family colors."""

    def __init__(self, viewport: QWidget | None = None, parent: QWidget | None = None, *,
                 language: str = "en", theme_mode: str = "light"):
        ensure_windows_offscreen_fonts()
        super().__init__(parent)
        self.setObjectName("viewportInspectionBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._viewport: QWidget | None = None
        self.ui_language = "ko" if str(language).strip().lower() == "ko" else "en"
        self.theme_mode = "dark" if str(theme_mode).strip().lower() == "dark" else "light"
        self._chips: list[tuple[str, QFrame, QFrame, QLabel]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 2, 8, 2)
        outer.setSpacing(3)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        outer.addLayout(row)

        self.section_label = QLabel()
        self.section_label.setObjectName("propertyLabel")
        row.addWidget(self.section_label)

        self.axis_group = QButtonGroup(self)
        self.axis_group.setExclusive(True)
        self.axis_buttons: dict[str, QToolButton] = {}
        for key, obj_name in (
            ("off", "sliceAxisOff"),
            ("x", "sliceAxisX"),
            ("y", "sliceAxisY"),
            ("z", "sliceAxisZ"),
        ):
            btn = QToolButton(self)
            btn.setObjectName(obj_name)
            btn.setCheckable(True)
            self.axis_group.addButton(btn)
            self.axis_buttons[key] = btn
            row.addWidget(btn)
        self.axis_buttons["off"].setChecked(True)

        self.slice_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slice_slider.setObjectName("sliceFractionSlider")
        self.slice_slider.setRange(5, 95)
        self.slice_slider.setValue(50)
        self.slice_slider.setSingleStep(1)
        self.slice_slider.setPageStep(5)
        self.slice_slider.setMinimumWidth(60)
        self.slice_slider.setMaximumWidth(100)
        row.addWidget(self.slice_slider)

        self.slice_value_label = QLabel("50%", self)
        self.slice_value_label.setObjectName("propertySubtitle")
        self.slice_value_label.setMinimumWidth(30)
        self.slice_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.slice_value_label)

        self.flip_button = QToolButton(self)
        self.flip_button.setObjectName("sliceFlipButton")
        self.flip_button.setCheckable(True)
        row.addWidget(self.flip_button)

        self._divider = QFrame(self)
        self._divider.setFrameShape(QFrame.Shape.VLine)
        self._divider.setFixedWidth(1)
        row.addWidget(self._divider)

        self.color_label = QLabel()
        self.color_label.setObjectName("propertyLabel")
        row.addWidget(self.color_label)

        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        self.color_buttons: dict[str, QToolButton] = {}
        for key, obj_name in (
            ("part", "colorModePart"),
            ("element_family", "colorModeElementFamily"),
        ):
            btn = QToolButton(self)
            btn.setObjectName(obj_name)
            btn.setCheckable(True)
            self.color_group.addButton(btn)
            self.color_buttons[key] = btn
            row.addWidget(btn)
        self.color_buttons["part"].setChecked(True)
        row.addStretch(1)

        self.legend_container = QWidget(self)
        self.legend_container.setObjectName("elementFamilyLegend")
        legend_sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        legend_sp.setHeightForWidth(True)
        self.legend_container.setSizePolicy(legend_sp)
        self.legend_layout = _ChipFlowLayout(self.legend_container, h_spacing=5, v_spacing=3)
        self.legend_layout.setContentsMargins(0, 1, 0, 1)
        self.legend_container.hide()
        outer.addWidget(self.legend_container)

        self.axis_group.buttonClicked.connect(self._push_slice_to_viewport)
        self.slice_slider.valueChanged.connect(self._on_slider_changed)
        self.flip_button.toggled.connect(self._push_slice_to_viewport)
        self.color_group.buttonClicked.connect(self._push_color_mode_to_viewport)

        self.apply_ui_language(self.ui_language)
        self.apply_theme_mode(self.theme_mode)
        self.bind_viewport(viewport)

    def sizeHint(self) -> QSize:
        sh = super().sizeHint()
        mh = super().minimumSizeHint()
        return QSize(sh.width(), max(sh.height(), mh.height()))

    def minimumSizeHint(self) -> QSize:
        sh = super().sizeHint()
        mh = super().minimumSizeHint()
        return QSize(0, max(sh.height(), mh.height()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_legend_height()

    def _invalidate_bar_geometry(self) -> None:
        if self.layout() is not None:
            self.layout().invalidate()
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().invalidate()
            parent.layout().activate()

    def _sync_legend_height(self) -> None:
        if not self.legend_container.isVisible() or self.legend_layout.count() == 0:
            return
        outer_m = self.layout().contentsMargins()
        avail_w = max(160, self.width() - outer_m.left() - outer_m.right())
        needed_h = max(20, self.legend_layout.heightForWidth(avail_w))
        if self.legend_container.height() != needed_h or self.legend_container.minimumHeight() != needed_h:
            self.legend_container.setFixedHeight(needed_h)
        self.legend_layout.invalidate()
        self._invalidate_bar_geometry()

    def bind_viewport(self, viewport: QWidget | None) -> None:
        if self._viewport is viewport:
            return
        if self._viewport is not None and hasattr(self._viewport, "inspectionStateChanged"):
            try:
                self._viewport.inspectionStateChanged.disconnect(self.refresh_from_viewport)
            except (RuntimeError, TypeError):
                pass
        self._viewport = viewport
        if viewport is not None and hasattr(viewport, "inspectionStateChanged"):
            viewport.inspectionStateChanged.connect(self.refresh_from_viewport)
        self.refresh_from_viewport()

    def _selected_axis(self) -> str | None:
        for key, btn in self.axis_buttons.items():
            if btn.isChecked():
                return None if key == "off" else key
        return None

    def _selected_color_mode(self) -> str:
        return "element_family" if self.color_buttons["element_family"].isChecked() else "part"

    def _on_slider_changed(self, value: int) -> None:
        self.slice_value_label.setText(f"{int(value)}%")
        self._push_slice_to_viewport()

    def _push_slice_to_viewport(self, *_):
        axis = self._selected_axis()
        active = axis is not None and self._viewport is not None and hasattr(self._viewport, "set_section_slice")
        self.slice_slider.setEnabled(active)
        self.flip_button.setEnabled(active)
        if self._viewport is not None and hasattr(self._viewport, "set_section_slice"):
            self._viewport.set_section_slice(
                axis,
                self.slice_slider.value() / 100.0,
                flip=self.flip_button.isChecked(),
            )

    def _push_color_mode_to_viewport(self, *_):
        mode = self._selected_color_mode()
        if self._viewport is not None and hasattr(self._viewport, "set_color_mode"):
            self._viewport.set_color_mode(mode)
        self._rebuild_legend()

    def refresh_from_viewport(self) -> None:
        vp = self._viewport
        capable = vp is not None and hasattr(vp, "set_section_slice") and hasattr(vp, "set_color_mode")
        for btn in (*self.axis_buttons.values(), *self.color_buttons.values()):
            btn.setEnabled(capable)
        if not capable:
            self.slice_slider.setEnabled(False)
            self.flip_button.setEnabled(False)
            self.legend_container.hide()
            return

        state = vp.section_slice()
        axis_key = state["axis"] or "off"
        if axis_key in self.axis_buttons and not self.axis_buttons[axis_key].isChecked():
            with QSignalBlocker(self.axis_group):
                self.axis_buttons[axis_key].setChecked(True)
        slider_val = max(5, min(95, round(float(state["fraction"]) * 100)))
        if self.slice_slider.value() != slider_val:
            with QSignalBlocker(self.slice_slider):
                self.slice_slider.setValue(slider_val)
        self.slice_value_label.setText(f"{round(float(state['fraction']) * 100)}%")
        with QSignalBlocker(self.flip_button):
            self.flip_button.setChecked(bool(state["flip"]))
        slice_active = state["axis"] is not None
        self.slice_slider.setEnabled(slice_active)
        self.flip_button.setEnabled(slice_active)

        cmode = vp.color_mode()
        if cmode in self.color_buttons and not self.color_buttons[cmode].isChecked():
            with QSignalBlocker(self.color_group):
                self.color_buttons[cmode].setChecked(True)
        self._rebuild_legend()

    def _rebuild_legend(self) -> None:
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._chips.clear()

        vp = self._viewport
        if (vp is None or not hasattr(vp, "color_mode") or vp.color_mode() != "element_family"
                or not hasattr(vp, "element_family_colors")):
            if not self.legend_container.isHidden():
                self.legend_container.hide()
                self._invalidate_bar_geometry()
            return

        has_counts = hasattr(vp, "element_family_counts")
        counts = vp.element_family_counts() if has_counts else {}
        colors = vp.element_family_colors()
        shown = {fam: col for fam, col in colors.items() if (counts.get(fam, 0) > 0 if has_counts else True)}
        if not shown:
            if not self.legend_container.isHidden():
                self.legend_container.hide()
                self._invalidate_bar_geometry()
            return

        ko = self.ui_language == "ko"
        palette = tokens_for_theme(self.theme_mode)
        self.legend_container.show()
        for fam, hex_color in shown.items():
            chip = QFrame(self.legend_container)
            chip.setObjectName("familyLegendChip")
            chip.setProperty("elementFamily", fam)
            chip.setProperty("swatchHex", hex_color)
            chip_row = QHBoxLayout(chip)
            chip_row.setContentsMargins(5, 2, 5, 2)
            chip_row.setSpacing(4)
            swatch = QFrame(chip)
            swatch.setFixedSize(10, 10)
            swatch.setStyleSheet(
                f"background: {hex_color}; border: 1px solid {palette['border']}; border-radius: 1px;"
            )
            label_text = _KO_FAMILY_CHIP_LABELS.get(fam, fam) if ko else fam
            count = counts.get(fam)
            lbl = QLabel(label_text, chip)
            lbl.setStyleSheet(f"color: {palette['text']}; background: transparent;")
            lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            base_tip = (_KO_FAMILY_TOOLTIPS if ko else _EN_FAMILY_TOOLTIPS).get(fam, fam)
            if count is not None:
                chip.setToolTip(f"{base_tip}: {count:,}개" if ko else f"{base_tip}: {count:,}")
            else:
                chip.setToolTip(base_tip)
            chip_row.addWidget(swatch)
            chip_row.addWidget(lbl)
            chip.ensurePolished()
            lbl.ensurePolished()
            text_w = lbl.fontMetrics().horizontalAdvance(label_text)
            text_h = lbl.fontMetrics().height()
            lbl.setMinimumWidth(text_w + 4)
            chip_m = chip.contentsMargins()
            row_m = chip_row.contentsMargins()
            chip_w = (
                chip_m.left()
                + chip_m.right()
                + row_m.left()
                + row_m.right()
                + swatch.width()
                + chip_row.spacing()
                + text_w
                + 4
            )
            chip_h = max(20, text_h + chip_m.top() + chip_m.bottom() + row_m.top() + row_m.bottom() + 2)
            chip.setFixedSize(chip_w, chip_h)
            chip.show()
            self.legend_layout.addWidget(chip)
            self._chips.append((fam, chip, swatch, lbl))
        self.legend_layout.activate()
        self._sync_legend_height()

    def apply_theme_mode(self, mode: str) -> None:
        self.theme_mode = "dark" if str(mode).strip().lower() == "dark" else "light"
        palette = tokens_for_theme(self.theme_mode)
        self._divider.setStyleSheet(f"background: {palette['divider']}; border: none;")
        self._rebuild_legend()

    def apply_ui_language(self, lang: str) -> None:
        self.ui_language = "ko" if str(lang).strip().lower() == "ko" else "en"
        ko = self.ui_language == "ko"
        self.section_label.setText("단면 절단" if ko else "Section cut")
        self.axis_buttons["off"].setText("해제" if ko else "Off")
        self.axis_buttons["off"].setToolTip("단면 절단 해제" if ko else "Disable section cut")
        for axis in ("x", "y", "z"):
            upper = axis.upper()
            self.axis_buttons[axis].setText(upper)
            self.axis_buttons[axis].setToolTip(
                f"{upper}축 수직 단면으로 내부 3D 요소 확인" if ko else f"Cut along {upper}-axis to inspect internal 3D cells"
            )
        self.slice_slider.setAccessibleName("단면 절단 위치" if ko else "Section cut position")
        self.slice_slider.setToolTip("단면 절단 위치 (5%–95%)" if ko else "Section plane position (5%–95%)")
        self.flip_button.setText("반전" if ko else "Flip")
        self.flip_button.setToolTip(
            "절단 평면 반대쪽 요소 표시" if ko else "Show elements on the opposite side of the section plane"
        )
        self.color_label.setText("색상 기준" if ko else "Color by")
        self.color_buttons["part"].setText("파트" if ko else "Part")
        self.color_buttons["part"].setToolTip("파트별 고유 색상으로 표시" if ko else "Color elements by part ownership")
        self.color_buttons["element_family"].setText("요소 계열" if ko else "Element family")
        self.color_buttons["element_family"].setToolTip(
            "3D 요소 계열(Hex8 / Wedge6 / Pyramid5 / Tet4 등)별 색상 표시"
            if ko
            else "Color elements by 3D element family (Hex8 / Wedge6 / Pyramid5 / Tet4)"
        )
        self._rebuild_legend()
