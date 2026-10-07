"""Interactive multi-curve plotting for the TreeLab Qt application.

The plotting session deliberately lives outside :mod:`window`.  A session
stores references to nodes from any open document, while the Qt renderer is
free to redraw them with a fast, linked overview plot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from . import pyqtgraph_compat as pg_compat


PLOT_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
)
INDEX_LABEL = "index"
LINE_STYLES = ("-", "--", ":", ".-")
LINE_STYLE_QT = {
    "-": QtCore.Qt.PenStyle.SolidLine,
    "--": QtCore.Qt.PenStyle.DashLine,
    ":": QtCore.Qt.PenStyle.DotLine,
    ".-": QtCore.Qt.PenStyle.DashDotLine,
}
_UNSET = object()
ICON_DIR = Path(__file__).resolve().parent / "icons"


def _icon(relative_path: str) -> QtGui.QIcon:
    return QtGui.QIcon(str(ICON_DIR / relative_path))


def _format_value(value: float) -> str:
    return f"{float(value):.7g}"


def expanded_curve_color(base_color: str, index: int, count: int) -> str:
    """Return a deterministic, distinct color for an expanded curve.

    A user-selected color remains unchanged for a single curve.  When one
    logical curve expands into several columns, hue is distributed around the
    color wheel while retaining the selected color's approximate saturation
    and brightness.
    """

    if count <= 1:
        return base_color
    base = QtGui.QColor(base_color)
    hue = base.hsvHue()
    if hue < 0:
        hue = 0
    saturation = base.hsvSaturation() or 210
    value = base.value() or 220
    color = QtGui.QColor.fromHsv(
        int((hue + 360.0 * index / count) % 360),
        min(saturation, 255),
        min(value, 255),
    )
    return color.name()


def expand_matching_axes(
    x: np.ndarray, y: np.ndarray
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expand compatible X/Y arrays into one-dimensional curve pairs.

    The first equal-length axis found in X-major order is used as the sample
    axis.  All remaining dimensions represent independent curves.  A single
    remaining X or Y column is broadcast across the other side, which is what
    permits a 1D abscissa to drive several columns of a 2D ordinate array.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    if x.ndim == 0:
        x = x.reshape(1)
    if y.ndim == 0:
        y = y.reshape(1)
    if not x.size or not y.size:
        raise ValueError("X/Y payload is empty")

    matching_axes = next(
        (
            (x_axis, y_axis)
            for x_axis, x_size in enumerate(x.shape)
            for y_axis, y_size in enumerate(y.shape)
            if x_size == y_size
        ),
        None,
    )
    if matching_axes is None:
        raise ValueError(
            f"no matching X/Y dimension ({x.shape} versus {y.shape})"
        )
    x_axis, y_axis = matching_axes
    sample_count = x.shape[x_axis]
    if sample_count == 0:
        raise ValueError("X/Y payload is empty")

    x_columns = np.moveaxis(x, x_axis, 0).reshape(sample_count, -1)
    y_columns = np.moveaxis(y, y_axis, 0).reshape(sample_count, -1)
    x_curve_count = x_columns.shape[1]
    y_curve_count = y_columns.shape[1]
    if x_curve_count != 1 and y_curve_count != 1 and x_curve_count != y_curve_count:
        raise ValueError(
            "remaining X/Y dimensions cannot be paired "
            f"({x.shape} versus {y.shape})"
        )
    curve_count = max(x_curve_count, y_curve_count)
    if x_curve_count == 1 and curve_count > 1:
        x_columns = np.broadcast_to(x_columns, (sample_count, curve_count))
    if y_curve_count == 1 and curve_count > 1:
        y_columns = np.broadcast_to(y_columns, (sample_count, curve_count))
    return [
        (x_columns[:, index], y_columns[:, index])
        for index in range(curve_count)
    ]


@dataclass(eq=False)
class PlotSource:
    """A node selected as a possible X or Y source.

    The node object is retained for the common case.  ``path`` is a recovery
    key used when a full save reloads a document and replaces its root tree.
    """

    document: object
    node: object | None
    path: str = ""
    values: np.ndarray | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.path and self.node is not None:
            self.path = str(self.node.path())

    @property
    def key(self) -> tuple[int, int]:
        return id(self.document), id(self.node) if self.node is not None else id(self)

    def resolve(self):
        if self.node is None:
            return None
        document_root = getattr(self.document, "root", None)
        if document_root is None:
            return None
        try:
            if self.node.root() is document_root:
                self.path = str(self.node.path())
                return self.node
        except Exception:
            pass

        parts = [part for part in self.path.split("/") if part]
        if parts and parts[0] == document_root.name():
            parts = parts[1:]
        node = document_root
        try:
            for part in parts:
                node.ensure_children_loaded()
                child = next(
                    (candidate for candidate in node.loaded_children()
                     if candidate.name() == part),
                    None,
                )
                if child is None:
                    child = next(
                        (candidate for candidate in node.children()
                         if candidate.name() == part),
                        None,
                    )
                if child is None:
                    return None
                node = child
        except Exception:
            return None
        self.node = node
        self.path = str(node.path())
        return node

    def display_label(self, tab_index: int | None = None) -> str:
        node = self.resolve()
        path = self.label or self.path
        if node is not None:
            try:
                path = str(node.path())
            except Exception:
                pass
        root = getattr(getattr(self.document, "root", None), "name", lambda: "")()
        if root and path.startswith(root + "/"):
            path = path[len(root) + 1:]
        prefix = f"tab{tab_index}" if tab_index is not None else getattr(
            self.document, "title", "tree"
        )
        return f"{prefix}@{path or root or '<root>'}"


@dataclass(eq=False)
class CurveSpec:
    x: PlotSource | None = None
    y: PlotSource | None = None
    axis: int = 0
    color: str = PLOT_COLORS[0]
    line_style: str = LINE_STYLES[0]
    visible: bool = True


class PlotSession:
    """Document-independent curve/source state."""

    def __init__(self) -> None:
        self.x_sources: list[PlotSource] = []
        self.y_sources: list[PlotSource] = []
        self.curves: list[CurveSpec] = []

    @staticmethod
    def _add_unique(
        destination: list[PlotSource], document: object, nodes: Iterable[object]
    ) -> list[PlotSource]:
        existing = {(id(source.document), id(source.node)) for source in destination}
        added = []
        for node in nodes:
            key = (id(document), id(node))
            node_path = str(node.path())
            if key in existing or any(
                source.document is document and source.path == node_path
                for source in destination
            ):
                continue
            source = PlotSource(document, node)
            destination.append(source)
            added.append(source)
            existing.add(key)
        return added

    def add_x(self, document: object, nodes: Iterable[object]) -> list[PlotSource]:
        return self._add_unique(self.x_sources, document, nodes)

    def add_y(self, document: object, nodes: Iterable[object]) -> list[PlotSource]:
        return self._add_unique(self.y_sources, document, nodes)

    @staticmethod
    def _add_values(
        destination: list[PlotSource],
        document: object,
        values: np.ndarray,
        path: str,
        label: str,
    ) -> list[PlotSource]:
        source = PlotSource(
            document,
            None,
            path=path,
            values=np.array(values, copy=True),
            label=label,
        )
        destination.append(source)
        return [source]

    def add_x_values(
        self, document: object, values: np.ndarray, path: str, label: str
    ) -> list[PlotSource]:
        return self._add_values(self.x_sources, document, values, path, label)

    def add_y_values(
        self, document: object, values: np.ndarray, path: str, label: str
    ) -> list[PlotSource]:
        return self._add_values(self.y_sources, document, values, path, label)

    def add_curve(self, x=_UNSET, y=_UNSET, *, allow_duplicate: bool = False) -> CurveSpec:
        if x is _UNSET:
            x = self.x_sources[0] if self.x_sources else None
        if y is _UNSET:
            y = self.y_sources[0] if self.y_sources else None
        if not allow_duplicate:
            for curve in self.curves:
                if curve.x is x and curve.y is y:
                    return curve
        curve = CurveSpec(
            x=x,
            y=y,
            color=PLOT_COLORS[len(self.curves) % len(PLOT_COLORS)],
        )
        self.curves.append(curve)
        return curve

    def remove_curve(self, curve: CurveSpec) -> None:
        if curve in self.curves:
            self.curves.remove(curve)

    def remove_document(self, document: object) -> None:
        self.x_sources = [source for source in self.x_sources
                          if source.document is not document]
        self.y_sources = [source for source in self.y_sources
                          if source.document is not document]
        self.curves = [curve for curve in self.curves
                       if (curve.x is None or curve.x.document is not document)
                       and (curve.y is None or curve.y.document is not document)]


class CurveRow(QtWidgets.QWidget):
    removed = QtCore.Signal(object)
    changed = QtCore.Signal()

    def __init__(self, curve: CurveSpec, session: PlotSession, parent=None):
        super().__init__(parent)
        self.curve = curve
        self.session = session
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.addWidget(QtWidgets.QLabel("X="))
        self.x_combo = QtWidgets.QComboBox(self)
        self.x_combo.setMinimumWidth(210)
        layout.addWidget(self.x_combo, 2)
        layout.addWidget(QtWidgets.QLabel("Y="))
        self.y_combo = QtWidgets.QComboBox(self)
        self.y_combo.setMinimumWidth(210)
        layout.addWidget(self.y_combo, 2)
        self.axis_combo = QtWidgets.QComboBox(self)
        self.axis_combo.addItems(["Y1", "Y2"])
        self.axis_combo.setToolTip("Assign this curve to the first or second Y axis")
        layout.addWidget(self.axis_combo)
        self.visible = QtWidgets.QCheckBox("Show", self)
        self.visible.setChecked(curve.visible)
        layout.addWidget(self.visible)
        self.color_button = QtWidgets.QPushButton("■", self)
        self.color_button.setFixedWidth(30)
        self.color_button.setToolTip("Change curve color")
        layout.addWidget(self.color_button)
        self.line_style_combo = QtWidgets.QComboBox(self)
        self.line_style_combo.addItems(LINE_STYLES)
        self.line_style_combo.setToolTip("Change curve line style")
        layout.addWidget(self.line_style_combo)
        remove = QtWidgets.QToolButton(self)
        remove.setIcon(_icon("OwnIcons/remove-curve-16.png"))
        remove.setToolTip("Remove curve")
        layout.addWidget(remove)

        self.x_combo.currentIndexChanged.connect(self._x_changed)
        self.y_combo.currentIndexChanged.connect(self._y_changed)
        self.axis_combo.currentIndexChanged.connect(self._axis_changed)
        self.visible.toggled.connect(self._visibility_changed)
        self.color_button.clicked.connect(self._choose_color)
        self.line_style_combo.currentTextChanged.connect(self._line_style_changed)
        remove.clicked.connect(lambda: self.removed.emit(self.curve))
        self._refreshing = False
        self.refresh()

    @staticmethod
    def _find_source(combo: QtWidgets.QComboBox, source: PlotSource | None) -> int:
        if source is None:
            return 0 if combo.count() else -1
        for index in range(combo.count()):
            item = combo.itemData(index)
            if item is source or (
                isinstance(item, PlotSource) and item.key == source.key
            ):
                return index
        return 0 if combo.count() else -1

    def refresh(self) -> None:
        self._refreshing = True
        try:
            self.x_combo.clear()
            self.x_combo.addItem(INDEX_LABEL, None)
            for source in self.session.x_sources:
                self.x_combo.addItem(source.display_label(), source)
            self.y_combo.clear()
            self.y_combo.addItem("Select Y source", None)
            for source in self.session.y_sources:
                self.y_combo.addItem(source.display_label(), source)
            x_index = self._find_source(self.x_combo, self.curve.x)
            y_index = self._find_source(self.y_combo, self.curve.y)
            if x_index >= 0:
                self.x_combo.setCurrentIndex(x_index)
            if y_index >= 0:
                self.y_combo.setCurrentIndex(y_index)
            self.axis_combo.setCurrentIndex(1 if self.curve.axis else 0)
            self.visible.setChecked(self.curve.visible)
            self.line_style_combo.setCurrentText(self.curve.line_style)
            self._set_color_button()
        finally:
            self._refreshing = False

    def _x_changed(self, _index: int) -> None:
        if not self._refreshing:
            self.curve.x = self.x_combo.currentData()
            self.changed.emit()

    def _y_changed(self, _index: int) -> None:
        if not self._refreshing:
            self.curve.y = self.y_combo.currentData()
            self.changed.emit()

    def _axis_changed(self, index: int) -> None:
        if not self._refreshing:
            self.curve.axis = index
            self.changed.emit()

    def _visibility_changed(self, visible: bool) -> None:
        if not self._refreshing:
            self.curve.visible = visible
            self.changed.emit()

    def _line_style_changed(self, line_style: str) -> None:
        if not self._refreshing:
            self.curve.line_style = line_style
            self.changed.emit()

    def _set_color_button(self) -> None:
        self.color_button.setStyleSheet(
            f"color: {self.curve.color}; font-size: 18px;"
        )

    def _choose_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.curve.color), self)
        if color.isValid():
            self.curve.color = color.name()
            self._set_color_button()
            self.changed.emit()


class PlotWindow(QtWidgets.QMainWindow):
    """Cross-tab curve editor and fast interactive plot."""

    def __init__(self, host, parent=None):
        super().__init__(parent or host)
        self.host = host
        self.session = PlotSession()
        self.rows: list[CurveRow] = []
        self._rendered: list[tuple[object, object]] = []
        self._hover_entries: list[dict] = []
        self._allow_close = False
        self._updating_region = False
        self.setWindowTitle("TreeLab plots")
        self.resize(1120, 760)
        self._make_ui()

    def _make_ui(self) -> None:
        toolbar = QtWidgets.QToolBar("Plot tools", self)
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        toolbar.setIconSize(QtCore.QSize(22, 22))
        self.addToolBar(toolbar)

        action_x = QtGui.QAction(_icon("OwnIcons/x-16.png"), "Add selected to X", self)
        action_x.setToolTip("Add selected node(s) to the X source list")
        action_x.triggered.connect(self.add_selected_to_x)
        toolbar.addAction(action_x)
        action_y = QtGui.QAction(_icon("OwnIcons/y-16.png"), "Add selected to Y", self)
        action_y.setToolTip("Add selected node(s) to the Y source list")
        action_y.triggered.connect(self.add_selected_to_y)
        toolbar.addAction(action_y)
        toolbar.addSeparator()
        action_curve = QtGui.QAction(_icon("OwnIcons/add-curve-16.png"), "Add curve", self)
        action_curve.triggered.connect(self.add_curve)
        toolbar.addAction(action_curve)
        action_draw = QtGui.QAction(_icon("OwnIcons/see-curve-16.png"), "Draw curves", self)
        action_draw.triggered.connect(self.draw)
        toolbar.addAction(action_draw)
        toolbar.addSeparator()
        action_clear = QtGui.QAction("Clear", self)
        action_clear.triggered.connect(self.clear_session)
        toolbar.addAction(action_clear)

        central = QtWidgets.QWidget(self)
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        self.source_label = QtWidgets.QLabel(central)
        self.source_label.setWordWrap(True)
        root_layout.addWidget(self.source_label)

        self.rows_container = QtWidgets.QWidget(central)
        self.rows_layout = QtWidgets.QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(1)
        rows_scroll = QtWidgets.QScrollArea(central)
        rows_scroll.setWidgetResizable(True)
        rows_scroll.setMaximumHeight(190)
        rows_scroll.setWidget(self.rows_container)
        root_layout.addWidget(rows_scroll)

        self.main_plot = pg.PlotWidget(central)
        self.overview_plot = pg.PlotWidget(central)
        self._configure_plot(self.main_plot, show_y=True)
        self._configure_plot(self.overview_plot, show_y=False)
        self.overview_plot.setMinimumHeight(105)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, central)
        splitter.addWidget(self.main_plot)
        splitter.addWidget(self.overview_plot)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        self.status_label = QtWidgets.QLabel(central)
        self.status_label.setWordWrap(True)
        root_layout.addWidget(self.status_label)
        self.setCentralWidget(central)

        self.main_item = self.main_plot.getPlotItem()
        self.main_view = self.main_item.getViewBox()
        self.y2_view = pg_compat.make_view_box()
        self.main_plot.scene().addItem(self.y2_view)
        self.main_item.showAxis("right")
        self.main_item.getAxis("right").linkToView(self.y2_view)
        self.main_item.getAxis("right").setPen("#d62728")
        self.main_item.getAxis("right").setTextPen("#d62728")
        self.y2_view.setXLink(self.main_view)
        self.y2_view.setMouseEnabled(x=False, y=True)
        self.y2_view.setVisible(False)
        self.main_view.sigResized.connect(self._update_y2_geometry)
        self._update_y2_geometry()

        self.legend = self.main_item.addLegend(offset=(10, 10))
        self.crosshair = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#666666", width=1)
        )
        self.main_view.addItem(self.crosshair, ignoreBounds=True)
        self.crosshair.setVisible(False)
        self.hover_label = QtWidgets.QLabel(self.main_plot)
        self.hover_label.setStyleSheet(
            "background: rgba(255,255,255,225); color: #202124; "
            "border: 1px solid #888; padding: 3px;"
        )
        self.hover_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hover_label.hide()
        self._mouse_proxy = pg.SignalProxy(
            self.main_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved,
        )
        self.overview_region = pg.LinearRegionItem([0, 1], brush=(80, 120, 220, 55))
        self.overview_region.setZValue(10)
        self.overview_plot.addItem(self.overview_region)
        self.overview_region.sigRegionChanged.connect(self._overview_region_changed)
        self.main_view.sigXRangeChanged.connect(self._main_x_range_changed)

        self.refresh_sources()

    @staticmethod
    def _configure_plot(plot: pg.PlotWidget, *, show_y: bool) -> None:
        plot.setBackground("#ffffff")
        plot.showGrid(x=True, y=show_y, alpha=0.18)
        plot.hideButtons()
        pg_compat.set_menu_enabled(plot, False)
        plot.setMouseEnabled(x=True, y=show_y)
        if not show_y:
            plot.hideAxis("left")
        for axis_name in ("bottom", "left", "right"):
            try:
                axis = plot.getAxis(axis_name)
                axis.setPen("#444444")
                axis.setTextPen("#202124")
            except KeyError:
                pass

    def _update_y2_geometry(self) -> None:
        self.y2_view.setGeometry(self.main_view.sceneBoundingRect())
        self.y2_view.linkedViewChanged(self.main_view, self.y2_view.XAxis)

    def _tab_index(self, document: object) -> int | None:
        try:
            return self.host.documents.index(document)
        except (ValueError, AttributeError):
            return None

    def refresh_sources(self, *, redraw: bool = False) -> None:
        for row in self.rows:
            row.refresh()
        parts = []
        if self.session.x_sources:
            parts.append(f"X sources: {len(self.session.x_sources)}")
        if self.session.y_sources:
            parts.append(f"Y sources: {len(self.session.y_sources)}")
        self.source_label.setText(
            " | ".join(parts) or "Select numeric nodes in a tree, then add them to X or Y."
        )
        if redraw:
            self.draw()

    def _add_nodes(
        self,
        axis: str,
        document: object,
        nodes: Iterable[object],
        *,
        ensure_curve: bool = True,
    ):
        sources = self.session.add_x(document, nodes) if axis == "x" else self.session.add_y(document, nodes)
        if sources and ensure_curve and not self.session.curves:
            self.add_curve(draw=False)
        if sources and ensure_curve:
            pending = [
                curve for curve in self.session.curves
                if getattr(curve, axis) is None
            ]
            for source, curve in zip(sources, pending):
                setattr(curve, axis, source)
        self.refresh_sources()
        return sources

    def _add_values(
        self,
        axis: str,
        document: object,
        values: np.ndarray,
        path: str,
        label: str,
    ) -> list[PlotSource]:
        sources = (
            self.session.add_x_values(document, values, path, label)
            if axis == "x"
            else self.session.add_y_values(document, values, path, label)
        )
        if sources and not self.session.curves:
            self.add_curve(draw=False)
        if sources:
            pending = [
                curve for curve in self.session.curves
                if getattr(curve, axis) is None
            ]
            for source, curve in zip(sources, pending):
                setattr(curve, axis, source)
        self.refresh_sources()
        return sources

    def add_selected_to_x(self) -> None:
        document = self.host.current_document()
        nodes = self.host._current_nodes()
        if document is not None and nodes:
            sources = self._add_nodes("x", document, nodes)
            self._report_registered_sources(sources, "X")

    def add_selected_to_y(self) -> None:
        document = self.host.current_document()
        nodes = self.host._current_nodes()
        if document is not None and nodes:
            sources = self._add_nodes("y", document, nodes)
            self._report_registered_sources(sources, "Y")

    def add_values_to_axis(
        self,
        axis: str,
        document: object,
        values: np.ndarray,
        path: str,
        label: str,
    ) -> list[PlotSource]:
        sources = self._add_values(axis, document, values, path, label)
        self._report_registered_sources(
            sources, axis.upper(), detail=" from selected cells of table"
        )
        return sources

    def _report_registered_sources(
        self,
        sources: list[PlotSource],
        axis: str,
        *,
        detail: str = "",
    ) -> None:
        status_bar = getattr(self.host, "statusBar", lambda: None)()
        if status_bar is None:
            return
        if len(sources) == 1:
            status_bar.showMessage(
                f"data of node {sources[0].path}{detail} added to {axis}"
            )
        elif sources:
            status_bar.showMessage(
                f"data of {len(sources)} nodes added to {axis}"
            )
        else:
            status_bar.showMessage(f"selected data already registered in {axis}")

    def plot_selected(self, document: object, nodes: list[object]) -> None:
        if not document or not nodes:
            self.show_and_raise()
            return
        if len(nodes) >= 2:
            x_sources = self._add_nodes("x", document, [nodes[0]], ensure_curve=False)
            y_sources = self._add_nodes("y", document, nodes[1:], ensure_curve=False)
            x_source = x_sources[0] if x_sources else next(
                (source for source in self.session.x_sources if source.node is nodes[0]),
                None,
            )
            for y_source in y_sources:
                self.session.add_curve(x=x_source, y=y_source)
        else:
            y_sources = self._add_nodes("y", document, nodes, ensure_curve=False)
            for y_source in y_sources:
                self.session.add_curve(x=None, y=y_source)
        self._rebuild_rows()
        self.draw()
        self.show_and_raise()

    def add_curve(self, *, draw: bool = True) -> None:
        self.session.add_curve(allow_duplicate=True)
        self._rebuild_rows()
        if draw:
            self.draw()

    def _rebuild_rows(self) -> None:
        for row in self.rows:
            row.setParent(None)
            row.deleteLater()
        self.rows = []
        for curve in self.session.curves:
            row = CurveRow(curve, self.session, self.rows_container)
            row.removed.connect(self._remove_curve)
            row.changed.connect(self.draw)
            self.rows_layout.addWidget(row)
            self.rows.append(row)
        self.refresh_sources()

    def _remove_curve(self, curve: CurveSpec) -> None:
        self.session.remove_curve(curve)
        self._rebuild_rows()
        self.draw()

    def clear_session(self) -> None:
        self.session = PlotSession()
        self._rebuild_rows()
        self._clear_rendered()
        self.status_label.clear()

    def remove_document(self, document: object) -> None:
        self.session.remove_document(document)
        self._rebuild_rows()
        self.draw()

    def _source_array(self, source: PlotSource) -> tuple[np.ndarray, str]:
        if source.values is not None:
            array = np.asarray(source.values)
            if not np.issubdtype(array.dtype, np.number):
                raise ValueError(f"Payload is not numeric: {source.path}")
            values = array if array.ndim else array.reshape(1)
            return values, source.label or source.path
        node = source.resolve()
        if node is None:
            raise ValueError(f"Source is no longer available: {source.path}")
        if not node.has_data():
            raise ValueError(f"Node has no payload: {node.path()}")
        if hasattr(node, "data_is_loaded") and not node.data_is_loaded():
            node.data()
        values = node.numpy()
        if values is None:
            raise ValueError(f"Node has no numeric payload: {node.path()}")
        array = np.asarray(values)
        if not np.issubdtype(array.dtype, np.number):
            raise ValueError(f"Payload is not numeric: {node.path()}")
        values = array if array.ndim else array.reshape(1)
        return values, str(node.name())

    @staticmethod
    def _set_downsampling(item: pg.PlotDataItem, *, overview: bool = False) -> None:
        pg_compat.configure_downsampling(item)

    @staticmethod
    def _curve_pen(color, line_style: str, width: int):
        return pg.mkPen(
            color=color,
            width=width,
            style=LINE_STYLE_QT.get(
                line_style, QtCore.Qt.PenStyle.SolidLine
            ),
        )

    def _clear_rendered(self) -> None:
        for target, item in self._rendered:
            try:
                target.removeItem(item)
            except Exception:
                pass
        self._rendered.clear()
        self._hover_entries.clear()
        self.legend.clear()
        self.y2_view.setVisible(False)
        self.main_item.hideAxis("right")
        self.crosshair.setVisible(False)
        self.hover_label.hide()

    def draw(self) -> None:
        self._clear_rendered()
        valid = []
        errors = []
        for index, curve in enumerate(self.session.curves, start=1):
            if curve.y is None:
                errors.append(f"Curve {index}: select a Y source")
                continue
            try:
                y, ylabel = self._source_array(curve.y)
                if curve.x is None:
                    x = np.arange(y.shape[0], dtype=float)
                    xlabel = INDEX_LABEL
                else:
                    x, xlabel = self._source_array(curve.x)
                expanded = expand_matching_axes(x, y)
                for curve_index, (curve_x, curve_y) in enumerate(expanded):
                    curve_label = (
                        ylabel
                        if len(expanded) == 1
                        else f"{ylabel}[{curve_index}]"
                    )
                    valid.append(
                        (
                            curve,
                            curve_x,
                            curve_y,
                            xlabel,
                            curve_label,
                            ylabel,
                            expanded_curve_color(
                                curve.color, curve_index, len(expanded)
                            ),
                        )
                    )
            except Exception as error:
                errors.append(f"Curve {index}: {error}")

        if not valid:
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText("; ".join(errors) or "No curves configured")
            return

        self.status_label.setStyleSheet("color: #202124;")
        self.status_label.setText(
            f"{len(valid)} curve(s) drawn"
            + ("; " + "; ".join(errors) if errors else "")
        )
        overview_items = []
        x_values = []
        y1_labels = []
        y2_labels = []
        for curve, x, y, xlabel, ylabel, axis_label, rendered_color in valid:
            color = pg.mkColor(rendered_color)
            pen = self._curve_pen(color, curve.line_style, 2)
            target = self.y2_view if curve.axis else self.main_item
            item = pg_compat.make_plot_data_item(
                x=x, y=y, pen=pen, antialias=False
            )
            self._set_downsampling(item)
            item.setVisible(curve.visible)
            target.addItem(item)
            pg_compat.set_clip_to_view(item)
            self._rendered.append((target, item))
            marker = pg.ScatterPlotItem(
                size=10, brush=pg.mkBrush(color), pen=pg.mkPen("#202124", width=1)
            )
            marker.hide()
            target.addItem(marker)
            self._rendered.append((target, marker))
            self._hover_entries.append({
                "curve": curve,
                "x": x,
                "y": y,
                "label": ylabel,
                "color": rendered_color,
                "item": item,
                "marker": marker,
            })
            overview_item = pg_compat.make_plot_data_item(
                x=x, y=y, pen=self._curve_pen(color, curve.line_style, 1)
            )
            self._set_downsampling(overview_item, overview=True)
            overview_item.setVisible(curve.visible)
            self.overview_plot.addItem(overview_item)
            pg_compat.set_clip_to_view(overview_item)
            self._rendered.append((self.overview_plot.getPlotItem(), overview_item))
            overview_items.append(overview_item)
            x_values.append(x[np.isfinite(x)])
            (y2_labels if curve.axis else y1_labels).append(axis_label)

        has_y2 = any(curve.axis for curve, *_ in valid)
        self.y2_view.setVisible(has_y2)
        if has_y2:
            self.main_item.showAxis("right")
            self.main_item.setLabel("right", ", ".join(dict.fromkeys(y2_labels)))
        else:
            self.main_item.hideAxis("right")
        self.main_item.setLabel("bottom", valid[0][3])
        self.main_item.setLabel("left", ", ".join(dict.fromkeys(y1_labels)))
        self.legend.clear()
        for entry in self._hover_entries:
            self.legend.addItem(entry["item"], entry["label"])

        finite_x = np.concatenate([values for values in x_values if values.size])
        x_min, x_max = float(np.min(finite_x)), float(np.max(finite_x))
        if x_min == x_max:
            x_min -= 0.5
            x_max += 0.5
        self.main_view.enableAutoRange()
        self.y2_view.enableAutoRange()
        self.main_view.setXRange(x_min, x_max, padding=0.02)
        self.overview_plot.getPlotItem().enableAutoRange()
        self.overview_plot.getPlotItem().setXRange(x_min, x_max, padding=0.02)
        self._set_region((x_min, x_max))

    def _set_region(self, region: tuple[float, float]) -> None:
        self._updating_region = True
        try:
            self.overview_region.setRegion(region)
        finally:
            self._updating_region = False

    def _overview_region_changed(self) -> None:
        if self._updating_region:
            return
        lower, upper = self.overview_region.getRegion()
        if upper <= lower:
            return
        self.main_view.setXRange(lower, upper, padding=0)

    def _main_x_range_changed(self, _view, ranges) -> None:
        if self._updating_region:
            return
        # PyQtGraph 0.14 emits ``[xmin, xmax]`` here; older releases may
        # provide the complete ``[[xmin, xmax], [ymin, ymax]]`` range.
        x_range = ranges[0] if len(ranges) == 2 and not np.isscalar(ranges[0]) else ranges
        self._set_region((float(x_range[0]), float(x_range[1])))

    @staticmethod
    def _nearest_index(x: np.ndarray, y: np.ndarray, target: float) -> int | None:
        valid = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
        if valid.size == 0:
            return None
        xv = x[valid]
        if xv.size > 1 and np.all(np.diff(xv) >= 0):
            position = int(np.searchsorted(xv, target))
            position = min(max(position, 0), xv.size - 1)
            if position and abs(xv[position - 1] - target) < abs(xv[position] - target):
                position -= 1
            return int(valid[position])
        return int(valid[np.argmin(np.abs(xv - target))])

    def _mouse_moved(self, event) -> None:
        position = event[0]
        view_rect = self.main_view.sceneBoundingRect()
        if not view_rect.contains(position):
            self.crosshair.setVisible(False)
            self.hover_label.hide()
            for entry in self._hover_entries:
                entry["marker"].hide()
            return
        point = self.main_view.mapSceneToView(position)
        x_position = float(point.x())
        self.crosshair.setPos(x_position)
        self.crosshair.setVisible(True)
        lines = []
        for entry in self._hover_entries:
            curve = entry["curve"]
            marker = entry["marker"]
            if not curve.visible:
                marker.hide()
                continue
            index = self._nearest_index(entry["x"], entry["y"], x_position)
            if index is None:
                marker.hide()
                continue
            x_value = float(entry["x"][index])
            y_value = float(entry["y"][index])
            marker.setData([x_value], [y_value])
            marker.show()
            lines.append(f"{entry['label']}={_format_value(y_value)}")
        if lines:
            self.hover_label.setText(f"X={_format_value(x_position)}\n" + "\n".join(lines))
            self.hover_label.adjustSize()
            self.hover_label.move(8, 8)
            self.hover_label.show()
        else:
            self.hover_label.hide()

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def shutdown(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:
        if self._allow_close:
            event.accept()
        else:
            self.hide()
            event.ignore()
