"""Treelab's Qt window and the small set of editing interactions it owns."""

from __future__ import annotations

import ast
from pathlib import Path

from .. import __version__
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from noder.core import Node
import noder.core.io as noder_io

from .document import TreeDocument
from .model import rename_node_unique, unique_sibling_name
from .style import (
    apply_fixed_dark_palette,
    apply_fixed_light_palette,
    make_theme_icon,
    palette_is_dark,
)
from .payload import (
    PAYLOAD_ELEMENT_LIMIT,
    UNLOADED_MARKER,
    payload_array,
    payload_dump_filename,
    payload_dump_lines,
)
from .new_payload import NewPayloadDialog, PayloadExpressionError, evaluate_payload_expression
from .plotter import PlotWindow


GUI_PATH = Path(__file__).resolve().parent
MOLA_ICON = GUI_PATH / "icons" / "OwnIcons" / "mola_v2_only_logo.svg"
ICON_DIR = GUI_PATH / "icons"


def _icon(relative_path: str) -> QtGui.QIcon:
    return QtGui.QIcon(str(ICON_DIR / relative_path))


class TreeView(QtWidgets.QTreeView):
    def __init__(self, document: TreeDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.setModel(document.model)
        self.setHeaderHidden(False)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(not document.read_only)
        self.setAcceptDrops(not document.read_only)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setIconSize(QtCore.QSize(18, 18))
        self.setIndentation(20)
        self.setRootIsDecorated(True)
        header = self.header()
        header.setStretchLastSection(False)
        for section in range(3):
            header.setSectionResizeMode(section, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 250)
        header.resizeSection(1, 120)
        header.resizeSection(2, 300)
        self._view_state = ([], [])
        document.model.modelAboutToBeReset.connect(self._capture_view_state)
        document.model.modelReset.connect(self._restore_view_state)

    def _branch_path(self, index: QtCore.QModelIndex) -> list[QtCore.QModelIndex]:
        path = []
        current = index
        while current.isValid():
            path.append(current)
            current = current.parent()
        path.reverse()
        return path

    def _branch_continues(self, parent: QtCore.QModelIndex, child: QtCore.QModelIndex) -> bool:
        """Whether the connector for ``child`` continues below this row."""
        model = self.model()
        visible_siblings = model.rowCount(parent)
        if child.row() < visible_siblings - 1:
            return True
        # A lazy parent may have more children than are currently materialised.
        # Keep the vertical connector open without fetching another page.
        return bool(getattr(model, "canFetchMore", lambda _index: False)(parent))

    def drawBranches(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRect,
        index: QtCore.QModelIndex,
    ) -> None:
        """Paint stable tree connectors while retaining native tree behavior."""
        path = self._branch_path(index)
        if not path:
            return

        indentation = self.indentation()
        left = rect.left()
        center_y = rect.center().y()
        line_role = (
            QtGui.QPalette.ColorRole.Midlight
            if palette_is_dark(self)
            else QtGui.QPalette.ColorRole.Mid
        )
        line_color = self.palette().color(line_role)
        if not line_color.isValid():
            line_color = self.palette().color(QtGui.QPalette.ColorRole.Text)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pen = QtGui.QPen(line_color)
        pen.setWidth(1)
        painter.setPen(pen)

        # Draw an ancestor connector while that branch has a later sibling.
        # For the last direct child, retain only the short vertical segment
        # above the horizontal connector, forming the expected L shape. Do
        # not repeat that segment for deeper descendants: that was the source
        # of the previous dashed-looking continuation.
        depth = len(path) - 1
        for level in range(len(path) - 1):
            parent = path[level]
            child = path[level + 1]
            x = left + int((level + 0.5) * indentation)
            if self._branch_continues(parent, child):
                painter.drawLine(x, rect.top(), x, rect.bottom())
            elif level + 1 == depth:
                painter.drawLine(x, rect.top(), x, center_y)

        node_x = left + int((depth + 0.5) * indentation)
        if depth:
            parent_x = left + int((depth - 0.5) * indentation)
            painter.drawLine(parent_x, center_y, node_x, center_y)

        # Use the existing square glyphs. Their 16-pixel footprint nearly fills
        # the indentation and leaves only a minimal gap before the node icon.
        # QTreeView still owns branch hit-testing and expansion state.
        if self.model().hasChildren(index):
            icon_name = (
                "qtvsc/minus_square.png"
                if self.isExpanded(index)
                else "qtvsc/plus_square.png"
            )
            branch_icon = _icon(icon_name)
            branch_icon.paint(
                painter,
                QtCore.QRect(node_x - 8, center_y - 8, 16, 16),
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        else:
            # A small dot makes leaves immediately distinguishable without
            # competing visually with the larger plus/minus controls.
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(line_color)
            painter.drawEllipse(QtCore.QRect(node_x - 3, center_y - 3, 6, 6))
        painter.restore()

    def _capture_view_state(self) -> None:
        expanded = []
        selected = self.selected_nodes()

        def visit(parent_index):
            for row in range(self.model().rowCount(parent_index)):
                index = self.model().index(row, 0, parent_index)
                node = self.model().node(index)
                if node is None:
                    continue
                if self.isExpanded(index):
                    expanded.append((node, node.path()))
                visit(index)

        visit(QtCore.QModelIndex())
        self._view_state = (expanded, [(node, node.path()) for node in selected])

    def _resolve_path(self, path: str):
        root = self.document.root
        parts = [part for part in path.split("/") if part]
        if parts and parts[0] == root.name():
            parts = parts[1:]
        node = root
        for part in parts:
            node.ensure_children_loaded()
            node = next((child for child in node.loaded_children() if child.name() == part), None)
            if node is None:
                return None
        return node

    def _restore_view_state(self) -> None:
        if not self._view_state:
            return
        expanded, selected = self._view_state
        for old_node, path in expanded:
            node = old_node if old_node is not None else None
            if node is None or self.document.model.index_for_node(node).isValid() is False:
                node = self._resolve_path(path)
            index = self.document.model.index_for_node(node)
            if index.isValid():
                self.expand(index)
        selection_model = self.selectionModel()
        selection_model.clearSelection()
        first = True
        for old_node, path in selected:
            node = old_node
            index = self.document.model.index_for_node(node)
            if not index.isValid():
                node = self._resolve_path(path)
                index = self.document.model.index_for_node(node)
            if not index.isValid():
                continue
            flags = QtCore.QItemSelectionModel.SelectionFlag.Select
            if first:
                flags |= QtCore.QItemSelectionModel.SelectionFlag.Clear
                first = False
            selection_model.select(index, flags)

    def selected_nodes(self) -> list:
        nodes = []
        seen = set()
        for index in self.selectionModel().selectedRows(0):
            node = self.document.model.node(index)
            if id(node) not in seen:
                seen.add(id(node))
                nodes.append(node)
        return nodes


class DocumentView(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(object)

    def __init__(self, document: TreeDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.tree = TreeView(document, self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)
        self.tree.selectionModel().selectionChanged.connect(self._selection_changed)

    def _selection_changed(self):
        nodes = self.tree.selected_nodes()
        self.selection_changed.emit(nodes[0] if nodes else None)


class MainWindow(QtWidgets.QMainWindow):
    """Main tabbed editor, intentionally independent of the old treelab API."""

    def __init__(
        self,
        filenames=(),
        *,
        read_only: bool = False,
        full_load: bool = False,
        safe_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.read_only = read_only
        self.full_load = full_load
        self.safe_mode = safe_mode
        self._safe_warning_documents = set()
        self._loading_children = set()
        self.documents: list[TreeDocument] = []
        self.views: list[DocumentView] = []
        self.clipboard_nodes: list = []
        self.search_expression = ""
        self.search_results: list = []
        self.search_index = -1
        self.plot_window: PlotWindow | None = None
        self.resize(1070, 800)
        self.setWindowTitle(f"MOLA TreeLab {__version__}")
        if MOLA_ICON.exists():
            self.setWindowIcon(QtGui.QIcon(str(MOLA_ICON)))

        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
        self.tabs.tabBar().tabBarClicked.connect(self._tab_bar_clicked)
        self._plus_tab_page = QtWidgets.QWidget(self.tabs)
        plus_index = self.tabs.addTab(
            self._plus_tab_page,
            _icon("fugue-icons-3.5.6/plus.png"),
            "",
        )
        self.tabs.tabBar().setTabButton(
            plus_index,
            QtWidgets.QTabBar.ButtonPosition.RightSide,
            None,
        )
        self.tabs.tabBar().setTabToolTip(plus_index, "New tab (Ctrl+Shift+T)")
        self.setCentralWidget(self.tabs)

        self._make_actions()
        self._make_property_dock()
        self.statusBar().showMessage("Ready")

        for filename in filenames:
            self.open_file(filename)
        if not self.documents and not filenames:
            self.new_document()
        elif not self.documents:
            self.statusBar().showMessage("No input tree was opened.")

    def _make_actions(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        edit_menu = self.menuBar().addMenu("Edit")
        view_menu = self.menuBar().addMenu("View")

        def help_text(action, text: str, shortcut: str | None = None) -> None:
            description = f"{text} ({shortcut})" if shortcut else text
            action.setToolTip(description)
            action.setStatusTip(description)

        self.action_open = QtGui.QAction(_icon("fugue-icons-3.5.6/folder-horizontal-open.png"), "Open…", self)
        self.action_open.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_dialog)
        help_text(self.action_open, "Open", "Ctrl+O")
        file_menu.addAction(self.action_open)

        self.action_new_tab = QtGui.QAction(_icon("fugue-icons-3.5.6/plus.png"), "New tab", self)
        self.action_new_tab.setShortcut(QtGui.QKeySequence("Ctrl+Shift+T"))
        self.action_new_tab.triggered.connect(self.new_document)
        help_text(self.action_new_tab, "New tab", "Ctrl+Shift+T")
        file_menu.addAction(self.action_new_tab)

        self.action_save = QtGui.QAction(_icon("fugue-icons-3.5.6/disk.png"), "Save", self)
        self.action_save.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_current)
        help_text(self.action_save, "Save", "Ctrl+S")
        file_menu.addAction(self.action_save)

        self.action_save_as = QtGui.QAction(_icon("fugue-icons-3.5.6/disk--plus.png"), "Save As…", self)
        self.action_save_as.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self.save_as_current)
        help_text(self.action_save_as, "Save As", "Ctrl+Shift+S")
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()
        self.action_close_tab = QtGui.QAction("Close current tab", self)
        self.action_close_tab.setShortcut(QtGui.QKeySequence("Ctrl+W"))
        self.action_close_tab.triggered.connect(self.close_current_tab)
        help_text(self.action_close_tab, "Close current tab", "Ctrl+W")
        file_menu.addAction(self.action_close_tab)

        file_menu.addSeparator()
        action_quit = QtGui.QAction("Quit", self)
        action_quit.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        self.action_new_node = QtGui.QAction(_icon("fugue-icons-3.5.6/plus.png"), "New node", self)
        self.action_new_node.setShortcut(QtGui.QKeySequence("Ctrl+N"))
        self.action_new_node.triggered.connect(self.new_nodes)
        help_text(self.action_new_node, "New node", "Ctrl+N")
        edit_menu.addAction(self.action_new_node)

        self.action_rename_nodes = QtGui.QAction(
            _icon("fugue-icons-3.5.6/blue-document-rename.png"),
            "Rename node(s)",
            self,
        )
        self.action_rename_nodes.triggered.connect(self.rename_selected_nodes)
        help_text(self.action_rename_nodes, "Rename selected node(s)")
        edit_menu.addAction(self.action_rename_nodes)

        self.action_set_node_type = QtGui.QAction(
            _icon("fugue-icons-3.5.6/blue-document-attribute.png"),
            "Set type of node(s)",
            self,
        )
        self.action_set_node_type.triggered.connect(self.set_selected_node_type)
        help_text(self.action_set_node_type, "Set type of selected node(s)")
        edit_menu.addAction(self.action_set_node_type)

        self.action_cut = QtGui.QAction(_icon("fugue-icons-3.5.6/scissors-blue.png"), "Cut node(s)", self)
        self.action_cut.setShortcut(QtGui.QKeySequence.StandardKey.Cut)
        self.action_cut.triggered.connect(self.cut_nodes)
        help_text(self.action_cut, "Cut node(s)", "Ctrl+X")
        edit_menu.addAction(self.action_cut)

        self.action_copy = QtGui.QAction(_icon("fugue-icons-3.5.6/blue-document-copy.png"), "Copy node(s)", self)
        self.action_copy.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        self.action_copy.triggered.connect(self.copy_nodes)
        help_text(self.action_copy, "Copy node(s)", "Ctrl+C")
        edit_menu.addAction(self.action_copy)

        self.action_paste = QtGui.QAction(_icon("fugue-icons-3.5.6/clipboard-paste.png"), "Paste node(s)", self)
        self.action_paste.setShortcut(QtGui.QKeySequence.StandardKey.Paste)
        self.action_paste.triggered.connect(self.paste_nodes)
        help_text(self.action_paste, "Paste node(s)", "Ctrl+V")
        edit_menu.addAction(self.action_paste)

        self.action_delete = QtGui.QAction(_icon("fugue-icons-3.5.6/cross.png"), "Delete node(s)", self)
        self.action_delete.setShortcut(QtGui.QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self.delete_nodes)
        help_text(self.action_delete, "Delete node(s)", "Del")
        edit_menu.addAction(self.action_delete)

        self.action_swap = QtGui.QAction(_icon("fugue-icons-3.5.6/arrow-switch.png"), "Swap nodes", self)
        self.action_swap.triggered.connect(self.swap_nodes)
        help_text(self.action_swap, "Swap nodes")
        edit_menu.addAction(self.action_swap)

        self.action_new_payload = QtGui.QAction("New payload", self)
        # Qt distinguishes the regular Return key from the keypad Enter key.
        # Support both physical keys while displaying the customary binding.
        self.action_new_payload.setShortcuts([
            QtGui.QKeySequence("Shift+Enter"),
            QtGui.QKeySequence("Shift+Return"),
        ])
        self.action_new_payload.setShortcutContext(
            QtCore.Qt.ShortcutContext.WindowShortcut
        )
        self.action_new_payload.triggered.connect(self.new_payload)
        help_text(self.action_new_payload, "New payload", "Shift+Enter")
        edit_menu.addAction(self.action_new_payload)

        self.action_search = QtGui.QAction(_icon("fugue-icons-3.5.6/node-magnifier.png"), "Search…", self)
        self.action_search.setShortcut(QtGui.QKeySequence("Ctrl+F"))
        self.action_search.triggered.connect(self.search_nodes)
        help_text(self.action_search, "Search", "Ctrl+F")
        view_menu.addAction(self.action_search)

        initial_dark = palette_is_dark(QtWidgets.QApplication.instance())
        theme_label = "Switch to light mode" if initial_dark else "Switch to dark mode"
        self.action_toggle_theme = QtGui.QAction(
            make_theme_icon(initial_dark), theme_label, self
        )
        self.action_toggle_theme.triggered.connect(self.toggle_theme)
        help_text(self.action_toggle_theme, theme_label)
        view_menu.addAction(self.action_toggle_theme)

        self.action_plot = QtGui.QAction(_icon("OwnIcons/see-curve-16.png"), "Plot selected data", self)
        self.action_plot.triggered.connect(self.plot_selected)
        help_text(self.action_plot, "Plot selected data")
        view_menu.addAction(self.action_plot)

        self.action_plot_add_x = QtGui.QAction(_icon("OwnIcons/x-16.png"), "Add selected data to X", self)
        self.action_plot_add_x.setShortcut(QtGui.QKeySequence("X"))
        self.action_plot_add_x.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action_plot_add_x.triggered.connect(self.add_selected_to_plot_x)
        help_text(self.action_plot_add_x, "Add selected data to X", "X")
        view_menu.addAction(self.action_plot_add_x)

        self.action_plot_add_y = QtGui.QAction(_icon("OwnIcons/y-16.png"), "Add selected data to Y", self)
        self.action_plot_add_y.setShortcut(QtGui.QKeySequence("Y"))
        self.action_plot_add_y.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action_plot_add_y.triggered.connect(self.add_selected_to_plot_y)
        help_text(self.action_plot_add_y, "Add selected data to Y", "Y")
        view_menu.addAction(self.action_plot_add_y)

        self.action_plot_add_curve = QtGui.QAction(_icon("OwnIcons/add-curve-16.png"), "Add plot curve", self)
        self.action_plot_add_curve.triggered.connect(self.add_plot_curve)
        help_text(self.action_plot_add_curve, "Add plot curve")
        view_menu.addAction(self.action_plot_add_curve)

        self.action_plot_draw = QtGui.QAction(_icon("OwnIcons/see-curve-16.png"), "Draw plot curves", self)
        self.action_plot_draw.setShortcut(QtGui.QKeySequence("P"))
        self.action_plot_draw.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action_plot_draw.triggered.connect(self.draw_plot_curves)
        help_text(self.action_plot_draw, "Draw plot curves", "P")
        view_menu.addAction(self.action_plot_draw)

        self.action_search_next = QtGui.QAction("Next search match (F3)", self)
        self.action_search_next.setShortcut(QtGui.QKeySequence("F3"))
        self.action_search_next.triggered.connect(lambda: self.navigate_search(1))
        view_menu.addAction(self.action_search_next)

        self.action_search_previous = QtGui.QAction("Previous search match (Shift+F3)", self)
        self.action_search_previous.setShortcut(QtGui.QKeySequence("Shift+F3"))
        self.action_search_previous.triggered.connect(lambda: self.navigate_search(-1))
        view_menu.addAction(self.action_search_previous)

        self.action_load_payload = QtGui.QAction(_icon("fugue-icons-3.5.6/disk--arrow.png"), "Load data (F5)", self)
        self.action_load_payload.setShortcut(QtGui.QKeySequence("F5"))
        self.action_load_payload.triggered.connect(self.load_current_data)
        help_text(self.action_load_payload, "Load data", "F5")
        view_menu.addAction(self.action_load_payload)

        self.action_load_payload_recursive = QtGui.QAction("Load descendants (Shift+F5)", self)
        self.action_load_payload_recursive.setShortcut(QtGui.QKeySequence("Shift+F5"))
        self.action_load_payload_recursive.triggered.connect(self.load_recursive_data)
        help_text(self.action_load_payload_recursive, "Load descendants", "Shift+F5")
        view_menu.addAction(self.action_load_payload_recursive)

        self.action_unload_payload = QtGui.QAction(_icon("fugue-icons-3.5.6/arrow-circle.png"), "Unload data (F6)", self)
        self.action_unload_payload.setShortcut(QtGui.QKeySequence("F6"))
        self.action_unload_payload.triggered.connect(self.unload_current_data)
        help_text(self.action_unload_payload, "Unload data", "F6")
        view_menu.addAction(self.action_unload_payload)

        self.action_unload_payload_recursive = QtGui.QAction("Unload descendants (Shift+F6)", self)
        self.action_unload_payload_recursive.setShortcut(QtGui.QKeySequence("Shift+F6"))
        self.action_unload_payload_recursive.triggered.connect(self.unload_recursive_data)
        help_text(self.action_unload_payload_recursive, "Unload descendants", "Shift+F6")
        view_menu.addAction(self.action_unload_payload_recursive)

        self.action_read_link = QtGui.QAction(_icon("fugue-icons-3.5.6/external.png"), "Read link (F7)", self)
        self.action_read_link.setShortcut(QtGui.QKeySequence("F7"))
        self.action_read_link.triggered.connect(self.read_current_links)
        help_text(self.action_read_link, "Read link", "F7")
        view_menu.addAction(self.action_read_link)

        self.action_read_link_recursive = QtGui.QAction("Read links recursively (Shift+F7)", self)
        self.action_read_link_recursive.setShortcut(QtGui.QKeySequence("Shift+F7"))
        self.action_read_link_recursive.triggered.connect(self.read_recursive_links)
        help_text(self.action_read_link_recursive, "Read links recursively", "Shift+F7")
        view_menu.addAction(self.action_read_link_recursive)

        self.action_previous_tab = QtGui.QAction("Previous tab", self)
        self.action_previous_tab.setShortcut(QtGui.QKeySequence("Ctrl+PgUp"))
        self.action_previous_tab.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action_previous_tab.triggered.connect(lambda: self._switch_tab(-1))
        help_text(self.action_previous_tab, "Previous tab", "Ctrl+PgUp")
        view_menu.addAction(self.action_previous_tab)

        self.action_next_tab = QtGui.QAction("Next tab", self)
        self.action_next_tab.setShortcut(QtGui.QKeySequence("Ctrl+PgDown"))
        self.action_next_tab.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action_next_tab.triggered.connect(lambda: self._switch_tab(1))
        help_text(self.action_next_tab, "Next tab", "Ctrl+PgDown")
        view_menu.addAction(self.action_next_tab)

        toolbar = QtWidgets.QToolBar("Tree tools", self)
        toolbar.setObjectName("treeToolsToolbar")
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        toolbar.setAllowedAreas(QtCore.Qt.ToolBarArea.AllToolBarAreas)
        toolbar.setIconSize(QtCore.QSize(24, 24))
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_save_as)
        toolbar.addAction(self.action_new_node)
        toolbar.addAction(self.action_rename_nodes)
        toolbar.addAction(self.action_set_node_type)
        toolbar.addAction(self.action_delete)
        toolbar.addAction(self.action_cut)
        toolbar.addAction(self.action_copy)
        toolbar.addAction(self.action_paste)
        toolbar.addAction(self.action_search)
        toolbar.addAction(self.action_plot)
        toolbar.addAction(self.action_plot_add_x)
        toolbar.addAction(self.action_plot_add_y)
        toolbar.addAction(self.action_plot_add_curve)
        toolbar.addAction(self.action_plot_draw)
        toolbar.addSeparator()
        toolbar.addAction(self.action_load_payload)
        toolbar.addAction(self.action_unload_payload)
        toolbar.addAction(self.action_read_link)
        toolbar.addSeparator()
        toolbar.addAction(self.action_swap)
        toolbar.addSeparator()
        toolbar.addAction(self.action_toggle_theme)

        if self.read_only:
            for action in (self.action_new_node, self.action_save, self.action_save_as,
                           self.action_rename_nodes, self.action_set_node_type,
                           self.action_cut, self.action_paste, self.action_delete, self.action_swap,
                           self.action_read_link, self.action_read_link_recursive,
                           self.action_new_payload):
                action.setEnabled(False)

    def _make_property_dock(self) -> None:
        self.dock = QtWidgets.QDockWidget("Node", self)
        self.dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        panel = QtWidgets.QWidget(self.dock)
        form = QtWidgets.QFormLayout(panel)
        self.node_path_edit = QtWidgets.QLineEdit(panel)
        self.node_path_edit.setReadOnly(True)
        self.node_path_edit.setPlaceholderText("Select a node to copy its path")
        self.payload_info = QtWidgets.QLabel(panel)
        self.payload_info.setWordWrap(True)
        self.siblings_info = QtWidgets.QLabel("Number of siblings: 0", panel)
        self.payload_table = QtWidgets.QTableWidget(panel)
        self.payload_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.payload_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.payload_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.payload_table.setAlternatingRowColors(True)
        self.payload_table.setMinimumHeight(180)
        self.payload_table.itemChanged.connect(self._payload_item_changed)
        self.payload_mode_spaces = QtWidgets.QRadioButton("Split using spaces", panel)
        self.payload_mode_axis = QtWidgets.QRadioButton("Split using axis", panel)
        self.payload_mode_raw = QtWidgets.QRadioButton("Raw", panel)
        self.payload_mode_spaces.setChecked(True)
        mode_group = QtWidgets.QButtonGroup(panel)
        mode_group.addButton(self.payload_mode_spaces)
        mode_group.addButton(self.payload_mode_axis)
        mode_group.addButton(self.payload_mode_raw)
        mode_controls = QtWidgets.QWidget(panel)
        mode_layout = QtWidgets.QHBoxLayout(mode_controls)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        for button in (self.payload_mode_spaces, self.payload_mode_axis, self.payload_mode_raw):
            mode_layout.addWidget(button)
            button.toggled.connect(self._refresh_payload_table)
        self.payload_axis = QtWidgets.QComboBox(panel)
        self.payload_axis.addItems(["axis 0", "axis 1", "axis 2"])
        self.payload_slice = QtWidgets.QSpinBox(panel)
        self.payload_slice.setMinimum(0)
        slice_controls = QtWidgets.QWidget(panel)
        slice_layout = QtWidgets.QHBoxLayout(slice_controls)
        slice_layout.setContentsMargins(0, 0, 0, 0)
        slice_layout.addWidget(self.payload_axis)
        slice_layout.addWidget(self.payload_slice)
        self.save_node_button = QtWidgets.QPushButton("Save Node", panel)
        self.dump_data_button = QtWidgets.QPushButton("Dump data", panel)
        self.new_payload_button = QtWidgets.QPushButton("New payload", panel)
        form.addRow("Path", self.node_path_edit)
        form.addRow(self.siblings_info)
        form.addRow("Payload", self.payload_info)
        form.addRow("String view", mode_controls)
        form.addRow(self.payload_table)
        form.addRow("Slice", slice_controls)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.save_node_button)
        buttons.addWidget(self.dump_data_button)
        form.addRow(buttons)
        form.addRow(self.new_payload_button)
        self.dock.setWidget(panel)
        self.save_node_button.clicked.connect(self.save_current_node)
        self.dump_data_button.clicked.connect(self.dump_current_node_data)
        self.new_payload_button.clicked.connect(self.new_payload)
        self.payload_axis.currentIndexChanged.connect(self._refresh_payload_table)
        self.payload_slice.valueChanged.connect(self._refresh_payload_table)
        self._selected_node = None
        self._refresh_payload_table()
        if self.read_only:
            self.payload_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.save_node_button.setEnabled(False)
            self.new_payload_button.setEnabled(False)
        else:
            self._update_save_node_state()

    def current_view(self) -> DocumentView | None:
        index = self.tabs.currentIndex()
        return self.views[index] if 0 <= index < len(self.views) else None

    def current_document(self) -> TreeDocument | None:
        view = self.current_view()
        return view.document if view else None

    def toggle_theme(self) -> None:
        """Switch between TreeLab's fixed light and dark palettes."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        dark = not palette_is_dark(app)
        if dark:
            apply_fixed_dark_palette(app)
        else:
            apply_fixed_light_palette(app)

        label = "Switch to light mode" if dark else "Switch to dark mode"
        self.action_toggle_theme.setText(label)
        self.action_toggle_theme.setIcon(make_theme_icon(dark))
        self.action_toggle_theme.setToolTip(label)
        self.action_toggle_theme.setStatusTip(label)
        for view in self.views:
            view.tree.viewport().update()
            view.tree.header().viewport().update()
        if self.plot_window is not None:
            self.plot_window.apply_theme()

    def new_document(self) -> None:
        document = TreeDocument(
            read_only=self.read_only,
            safe_mode=self.safe_mode,
            parent=self,
        )
        self._add_document(document)

    def open_dialog(self) -> None:
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open CGNS file", ".", "CGNS files (*.cgns *.hdf *.hdf5);;All files (*)"
        )
        for filename in filenames:
            self.open_file(filename)

    def open_file(self, filename: str) -> None:
        progress = self._progress("Opening tree", f"Opening {Path(filename).name}…")
        try:
            document = TreeDocument(
                filename,
                read_only=self.read_only,
                safe_mode=self.safe_mode,
                parent=self,
            )
            QtWidgets.QApplication.processEvents()
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(error))
            progress.close()
            return
        try:
            self._add_document(document)
            if self.full_load:
                self._run_payload_operation([document.root], recursive=True, operation="load")
            self._show_safe_mode_warning(document)
        finally:
            progress.close()

    def _add_document(self, document: TreeDocument) -> None:
        view = DocumentView(document, self)
        view.selection_changed.connect(self.show_node)
        view.tree.expanded.connect(
            lambda index, view=view: self._load_remaining_children(view, index)
        )
        document.changed.connect(self._document_changed)
        self.documents.append(document)
        self.views.append(view)
        tab_index = self.tabs.insertTab(self._plus_tab_index(), view, document.title)
        self.tabs.tabBar().setTabToolTip(tab_index, document.title)
        self.tabs.setCurrentWidget(view)
        root_index = document.model.index(0, 0)
        self._expand_root_and_bases(view, root_index)
        selection_model = view.tree.selectionModel()
        selection_model.select(
            root_index,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect |
            QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        view.tree.selectionModel().setCurrentIndex(
            root_index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
        )
        view.tree.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def _plus_tab_index(self) -> int:
        return self.tabs.count() - 1

    def _tab_bar_clicked(self, index: int) -> None:
        if index == self._plus_tab_index():
            self.new_document()

    def _show_safe_mode_warning(self, document: TreeDocument) -> None:
        if not self.safe_mode or not document.has_read_warnings:
            return
        marker = id(document)
        if marker in self._safe_warning_documents:
            return
        self._safe_warning_documents.add(marker)
        QtWidgets.QMessageBox.warning(
            self,
            "Malformed nodes found",
            "Malformed nodes where found during reading, search using / t:Corrupted_t",
        )

    def _expand_root_and_bases(self, view: DocumentView, root_index) -> None:
        view.tree.expand(root_index)
        for row in range(view.document.model.rowCount(root_index)):
            view.tree.collapse(view.document.model.index(row, 0, root_index))

    def close_tab(self, index: int) -> None:
        if index < 0 or index >= len(self.documents):
            return
        document = self.documents[index]
        if document.dirty and not self.read_only:
            answer = QtWidgets.QMessageBox.question(
                self, "Unsaved changes", f"Save changes to {document.title}?",
                QtWidgets.QMessageBox.StandardButton.Save |
                QtWidgets.QMessageBox.StandardButton.Discard |
                QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
                return
            if answer == QtWidgets.QMessageBox.StandardButton.Save:
                if not self._save_document(document):
                    return
        if self.plot_window is not None:
            self.plot_window.remove_document(document)
        document.close()
        self.tabs.removeTab(index)
        self.views.pop(index)
        self.documents.pop(index)
        if not self.documents:
            self.new_document()

    def close_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        if 0 <= index < len(self.documents):
            self.close_tab(index)

    def _current_nodes(self) -> list:
        view = self.current_view()
        return view.tree.selected_nodes() if view else []

    @staticmethod
    def _node_path_without_root(node) -> str:
        path = str(node.path()).strip("/")
        try:
            root_name = str(node.root().name()).strip("/")
        except Exception:
            root_name = ""
        if path == root_name:
            return ""
        prefix = root_name + "/"
        return path[len(prefix):] if root_name and path.startswith(prefix) else path

    def show_node(self, node) -> None:
        self._selected_node = node
        if node is None:
            self.dock.setWindowTitle("Node")
            self.node_path_edit.clear()
            self.payload_info.clear()
            self.siblings_info.setText("Number of siblings: 0")
            self._update_save_node_state()
            self._refresh_payload_table()
            return
        self.dock.setWindowTitle(node.path())
        self.node_path_edit.setText(self._node_path_without_root(node))
        self._update_sibling_info(node)
        self._update_save_node_state()
        try:
            if not node.has_data():
                self.payload_info.setText("No payload")
            elif not getattr(node, "data_is_loaded", lambda: True)():
                self.payload_info.setText(UNLOADED_MARKER)
        except Exception as error:
            self.payload_info.setText(f"Payload unavailable: {error}")
        self._refresh_payload_table()

    def _update_sibling_info(self, node) -> None:
        if node is None:
            self.siblings_info.setText("Number of siblings: 0")
            return
        try:
            parent = node.parent()
            if parent is None:
                sibling_count = 0
            else:
                hidden_children = sum(
                    child.name() == "CGNSLibraryVersion"
                    for child in parent.loaded_children()
                )
                sibling_count = max(
                    0, parent.child_count() - hidden_children - 1
                )
            self.siblings_info.setText(f"Number of siblings: {sibling_count}")
        except Exception:
            self.siblings_info.setText("Number of siblings: unavailable")

    def _resolve_payload_reference(
        self, filename: str, path: str, *, relative_to=None
    ) -> np.ndarray:
        if not filename:
            node = relative_to or self._selected_node
            if node is None or node.parent() is None:
                raise PayloadExpressionError(
                    f"Sibling payload reference {path!r} requires a selected node"
                )
            sibling_name = path.strip("/")
            parent = node.parent()
            parent.ensure_children_loaded()
            sibling = next(
                (candidate for candidate in parent.loaded_children()
                 if candidate.name() == sibling_name),
                None,
            )
            if sibling is None:
                raise PayloadExpressionError(
                    f"Sibling node {sibling_name!r} was not found next to {node.name()!r}"
                )
            node = sibling
            if not node.has_data():
                raise PayloadExpressionError(
                    f"Node {node.path()} has no payload"
                )
            if hasattr(node, "data_is_loaded") and not node.data_is_loaded():
                node.data()
            values = node.numpy()
            if values is None:
                raise PayloadExpressionError(
                    f"Node {node.path()} has no NumPy-compatible payload"
                )
            array = np.array(values, copy=True)
            array.setflags(write=False)
            return array

        requested_name = Path(filename).name
        matches = []
        for document in self.documents:
            candidates = {document.title}
            if document.filename:
                candidates.add(str(document.filename))
                candidates.add(Path(document.filename).name)
            if filename in candidates or requested_name in candidates:
                matches.append(document)
        if not matches:
            raise PayloadExpressionError(
                f"No open tab matches payload file {filename!r}"
            )
        if len(matches) > 1:
            raise PayloadExpressionError(
                f"Payload file {filename!r} is ambiguous across open tabs"
            )

        document = matches[0]
        node = document.root
        parts = [part for part in path.strip("/").split("/") if part]
        if parts and parts[0] == document.root.name():
            parts = parts[1:]
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
                raise PayloadExpressionError(
                    f"Node path {path!r} was not found in {document.title!r}"
                )
            node = child

        if not node.has_data():
            raise PayloadExpressionError(
                f"Node {node.path()} has no payload"
            )
        if hasattr(node, "data_is_loaded") and not node.data_is_loaded():
            node.data()
        values = node.numpy()
        if values is None:
            raise PayloadExpressionError(
                f"Node {node.path()} has no NumPy-compatible payload"
            )
        array = np.array(values, copy=True)
        array.setflags(write=False)
        return array

    def new_payload(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._selected_nodes_or_current()
        if not nodes or document is None:
            self.statusBar().showMessage("Select a node before creating a payload")
            return
        dialog = NewPayloadDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        expression = dialog.expression()
        try:
            # Evaluate every target before changing any of them.  This keeps
            # sibling references relative to each selected node and avoids a
            # partial update if one target has a missing sibling.
            values = [
                evaluate_payload_expression(
                    expression,
                    lambda filename, path, node=node: self._resolve_payload_reference(
                        filename, path, relative_to=node
                    ),
                )
                for node in nodes
            ]
            for node, value in zip(nodes, values):
                document.edit_node_data(node, value)
        except PayloadExpressionError as error:
            QtWidgets.QMessageBox.warning(self, "New payload failed", str(error))
            return
        self.show_node(nodes[0])
        if all(value is None for value in values):
            self.statusBar().showMessage(f"Removed payload from {len(nodes)} node(s)")
        else:
            self.statusBar().showMessage(f"Created payload for {len(nodes)} node(s)")

    def _refresh_payload_table(self, *_args) -> None:
        table = getattr(self, "payload_table", None)
        if table is None:
            return
        self._updating_table = True
        table.clear()
        table.setRowCount(0)
        table.setColumnCount(0)
        self._updating_table = False
        node = self._selected_node
        if node is None:
            self.payload_info.setText("Select a node to inspect its payload.")
            return
        try:
            if not node.has_data():
                self.payload_info.setText("No payload")
                self._set_table_values([[""]])
                return
            if not getattr(node, "data_is_loaded", lambda: True)():
                self.payload_info.setText(UNLOADED_MARKER)
                self._set_table_values([[UNLOADED_MARKER]])
                return
            data = node.data()
            if data is not None and data.hasString():
                values, label = self._string_payload_view(node, data)
                self.payload_info.setText(f"string shape={data.shape()}{label}")
                self._set_table_values(values)
                return
            array = payload_array(node)
            if array is None or array.size == 0:
                self.payload_info.setText("Empty payload")
                self._set_table_values([["None" if array is None else "empty array"]])
                return
            if array.size > PAYLOAD_ELEMENT_LIMIT:
                self.payload_info.setText(
                    f"Payload has {array.size} elements; table limit is {PAYLOAD_ELEMENT_LIMIT}."
                )
                self._set_table_values([["Payload too large for table"]])
                return
            values, label = self._payload_view(array)
            self.payload_info.setText(f"{array.dtype} shape={array.shape}{label}")
            self._set_table_values(values)
        except Exception as error:
            self.payload_info.setText(f"Payload unavailable: {error}")
            self._set_table_values([["Payload unavailable"]])

    def _string_payload_view(self, node, data) -> tuple[list[list[str]], str]:
        if self.payload_mode_raw.isChecked():
            return [[data.extractString()]], ", raw"
        if self.payload_mode_spaces.isChecked():
            try:
                interpreted = node.interpret_data("spaces")
                if isinstance(interpreted, (list, tuple)):
                    return [[_table_value(value)] for value in interpreted], ", split using spaces"
            except Exception:
                pass
            return [[word] for word in data.extractString().split()], ", split using spaces"
        array = np.asarray(data.getPyArray())
        if array.ndim == 0:
            return [[_table_value(array.item())]], ", split using axis"
        if array.ndim == 1:
            return [[_table_value(value)] for value in array], ", split using axis"
        if array.ndim == 2:
            return [[_table_value(value) for value in row] for row in array], ", split using axis"
        flattened = array.reshape(array.shape[0], -1)
        return [[_table_value(value) for value in row] for row in flattened], ", split using axis"

    def _payload_view(self, array: np.ndarray) -> tuple[list[list[str]], str]:
        array = np.asarray(array)
        if array.ndim == 0:
            return [[_table_value(array.item())]], ""
        if array.ndim == 1:
            return [[_table_value(value)] for value in array], ""
        if array.ndim == 2:
            return [[_table_value(value) for value in row] for row in array], ""
        if array.ndim == 3:
            axis = min(self.payload_axis.currentIndex(), 2)
            maximum = array.shape[axis] - 1
            blocker = QtCore.QSignalBlocker(self.payload_slice)
            self.payload_slice.setMaximum(maximum)
            del blocker
            slice_index = min(self.payload_slice.value(), maximum)
            plane = np.take(array, slice_index, axis=axis)
            if plane.ndim == 2:
                values = [[_table_value(value) for value in row] for row in plane]
            else:
                values = [[_table_value(value)] for value in plane.reshape(-1)]
            return values, f", showing axis {axis} slice {slice_index}"
        flattened = array.reshape(array.shape[0], -1)
        return [[_table_value(value) for value in row] for row in flattened], ", flattened"

    def _set_table_values(self, values: list[list[str]]) -> None:
        rows = len(values)
        columns = max((len(row) for row in values), default=1)
        previous = getattr(self, "_updating_table", False)
        self._updating_table = True
        try:
            self.payload_table.setRowCount(rows)
            self.payload_table.setColumnCount(columns)
            for row_index, row in enumerate(values):
                for column_index, value in enumerate(row):
                    self.payload_table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(str(value)))
            self.payload_table.resizeColumnsToContents()
            self.payload_table.resizeRowsToContents()
        finally:
            self._updating_table = previous

    def _payload_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if getattr(self, "_updating_table", False) or self.read_only:
            return
        node = self._selected_node
        document = self.current_document()
        if node is None or document is None or not node.has_data():
            return
        try:
            data = node.data()
            text = item.text()
            if data.hasString():
                if self.payload_mode_raw.isChecked():
                    document.edit_node_data(node, text)
                elif self.payload_mode_spaces.isChecked():
                    words = [self.payload_table.item(row, 0).text()
                             for row in range(self.payload_table.rowCount())]
                    document.edit_node_data(node, " ".join(words))
                else:
                    array = np.asarray(data.getPyArray())
                    array[item.row(), item.column()] = np.asarray(text, dtype=array.dtype)
                    document.mark_changed(full=False, node=node)
            else:
                array = np.asarray(data.getPyArray())
                parsed = ast.literal_eval(text)
                value = np.asarray(parsed, dtype=array.dtype).item()
                if array.ndim == 0:
                    array[...] = value
                elif array.ndim == 1:
                    array[item.row()] = value
                elif array.ndim == 2:
                    array[item.row(), item.column()] = value
                elif array.ndim == 3:
                    axis = min(self.payload_axis.currentIndex(), 2)
                    index = self.payload_slice.value()
                    if axis == 0:
                        array[index, item.row(), item.column()] = value
                    elif axis == 1:
                        array[item.row(), index, item.column()] = value
                    else:
                        array[item.row(), item.column(), index] = value
                else:
                    raise ValueError("in-place editing is limited to three table dimensions")
                document.mark_changed(full=False, node=node)
            index = document.model.index_for_node(node)
            if index.isValid():
                document.model.dataChanged.emit(index, index.siblingAtColumn(2))
            self._refresh_payload_table()
        except (ValueError, SyntaxError, IndexError, TypeError) as error:
            self.statusBar().showMessage(f"Value not changed: {error}")

    def _selected_table_values(self) -> np.ndarray | None:
        items = self.payload_table.selectedItems()
        if not items:
            return None
        parsed = {}
        for item in items:
            text = item.text().strip()
            try:
                value = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                try:
                    value = float(text)
                except ValueError as error:
                    raise ValueError("selected table cells are not numeric") from error
            if isinstance(value, (str, bytes)):
                raise ValueError("selected table cells are not numeric")
            if isinstance(value, bool):
                value = int(value)
            parsed[(item.row(), item.column())] = value

        rows = sorted({row for row, _column in parsed})
        columns = sorted({column for _row, column in parsed})
        rectangular = (
            len(parsed) == len(rows) * len(columns)
            and all((row, column) in parsed for row in rows for column in columns)
        )
        if rectangular and len(rows) > 1 and len(columns) > 1:
            values = [[parsed[(row, column)] for column in columns] for row in rows]
            result = np.asarray(values)
        else:
            result = np.asarray([parsed[key] for key in sorted(parsed)])
        if not np.issubdtype(result.dtype, np.number):
            raise ValueError("selected table cells are not numeric")
        return result

    def _add_table_selection_to_plot(self, axis: str) -> bool:
        values = self._selected_table_values()
        if values is None:
            return False
        document = self.current_document()
        node = self._selected_node
        if document is None or node is None:
            return False
        path = str(node.path())
        label = f"{self._node_path_without_root(node)} [selected cells]"
        try:
            self._ensure_plot_window().add_values_to_axis(
                axis, document, values, path, label
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error))
        return True

    def _progress(self, title: str, label: str) -> QtWidgets.QProgressDialog:
        progress = QtWidgets.QProgressDialog(label, "Cancel", 0, 0, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)
        progress.setMinimumDuration(0)
        progress.show()
        QtWidgets.QApplication.processEvents()
        return progress

    def _load_remaining_children(self, view: DocumentView, index: QtCore.QModelIndex) -> None:
        """Load later child pages after a branch is unfolded, with progress feedback."""
        model = view.document.model
        node = model.node(index)
        if node is None or node in self._loading_children or not model.canFetchMore(index):
            return

        self._loading_children.add(node)
        progress = self._progress(
            "Loading children", f"Loading children of {node.name()}…"
        )
        progress.setRange(0, max(1, node.child_count()))
        progress.setValue(model.rowCount(index))
        try:
            while model.canFetchMore(index) and not progress.wasCanceled():
                model.fetchMore(index)
                progress.setValue(model.rowCount(index))
                QtWidgets.QApplication.processEvents()
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self, "Loading children failed", str(error)
            )
        finally:
            progress.close()
            self._loading_children.discard(node)

    @staticmethod
    def _walk_nodes(nodes, recursive: bool):
        seen = set()

        def visit(node):
            # Keep the Python wrappers themselves alive.  Noder may create a
            # temporary wrapper when returning a child; tracking ``id(node)``
            # alone lets CPython reuse wrapper IDs and silently skips later
            # descendants during large recursive loads.
            if node in seen:
                return
            seen.add(node)
            yield node
            if recursive:
                node.ensure_children_loaded()
                # Recursive/full operations must not stop at the model's
                # currently paged child set.  ``children()`` asks noder for
                # the complete direct-child set, including UDD descendants.
                for child in node.children():
                    yield from visit(child)

        for node in nodes:
            yield from visit(node)

    def _run_payload_operation(self, nodes, *, recursive: bool, operation: str) -> None:
        if not nodes:
            return
        progress = self._progress(
            "Loading payload" if operation == "load" else "Unloading payload",
            "Loading tree payload…" if operation == "load" else "Releasing tree payload…",
        )
        count = 0
        try:
            for node in self._walk_nodes(nodes, recursive):
                if progress.wasCanceled():
                    break
                if operation == "load":
                    # Calling data() is intentional even for metadata-only
                    # nodes: noder records the payload as inspected and the
                    # lazy backend remains responsible for deciding whether
                    # an HDF5 dataset exists.
                    node.data()
                elif operation == "unload":
                    node.unload_data()
                count += 1
                if count % 32 == 0:
                    QtWidgets.QApplication.processEvents()
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Payload operation failed", str(error))
        finally:
            progress.close()
        for view in self.views:
            view.document.model.layoutChanged.emit()
        self.statusBar().showMessage(f"{operation.title()}ed payload for {count} node(s)")
        self.show_node(nodes[0])

    def load_current_data(self) -> None:
        self._run_payload_operation(self._current_nodes(), recursive=False, operation="load")

    def load_recursive_data(self) -> None:
        self._run_payload_operation(self._current_nodes(), recursive=True, operation="load")

    def unload_current_data(self) -> None:
        self._run_payload_operation(self._current_nodes(), recursive=False, operation="unload")

    def unload_recursive_data(self) -> None:
        self._run_payload_operation(self._current_nodes(), recursive=True, operation="unload")

    # Kept as a small API alias for callers of the previous GUI implementation.
    def load_selected_data(self) -> None:
        self.load_recursive_data()

    def _visible_index(self, node, view: DocumentView, document: TreeDocument):
        if node is None or node.root() is not document.root:
            return QtCore.QModelIndex()
        ancestors = []
        parent = node.parent()
        while parent is not None:
            ancestors.append(parent)
            parent = parent.parent()
        for ancestor in reversed(ancestors):
            ancestor.ensure_children_loaded()
            index = document.model.index_for_node(ancestor)
            if index.isValid():
                view.tree.expand(index)
        return document.model.index_for_node(node)

    def _select_nodes(self, nodes, *, focus=None) -> bool:
        view = self.current_view()
        document = self.current_document()
        if view is None or document is None:
            return False
        indexes = []
        for node in nodes:
            index = self._visible_index(node, view, document)
            if index.isValid():
                indexes.append(index)
        if not indexes:
            return False
        selection = view.tree.selectionModel()
        blocker = QtCore.QSignalBlocker(selection)
        selection.clearSelection()
        for position, index in enumerate(indexes):
            flags = (
                QtCore.QItemSelectionModel.SelectionFlag.Select |
                QtCore.QItemSelectionModel.SelectionFlag.Rows
            )
            if position == 0:
                flags |= QtCore.QItemSelectionModel.SelectionFlag.Clear
            selection.select(index, flags)
        del blocker
        focus_index = self._visible_index(focus, view, document) if focus is not None else indexes[0]
        if not focus_index.isValid():
            focus_index = indexes[0]
        selection.setCurrentIndex(focus_index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        view.tree.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        view.tree.scrollTo(focus_index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        self.show_node(focus if focus is not None else view.document.model.node(focus_index))
        return True

    def _reveal_node(self, node) -> bool:
        return self._select_nodes([node], focus=node)

    def _focus_node(self, node) -> bool:
        view = self.current_view()
        document = self.current_document()
        if view is None or document is None:
            return False
        index = self._visible_index(node, view, document)
        if not index.isValid():
            return False
        view.tree.selectionModel().setCurrentIndex(
            index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
        )
        view.tree.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        view.tree.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        self.show_node(node)
        return True

    def search_nodes(self) -> None:
        document = self.current_document()
        if document is None:
            return
        expression, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Search tree",
            "Noder predicate (for example: n:Coordinate* or t:Zone_t):",
            text=self.search_expression,
        )
        if not accepted:
            return
        expression = expression.strip()
        if not expression:
            self.search_expression = ""
            self.search_results = []
            self.search_index = -1
            return
        if not expression.startswith(("/", "\\")):
            expression = "/ " + expression
        try:
            self.search_expression = expression
            self.search_results = self._find_nodes_by_predicate(document, expression)
            if not self.search_results:
                self.search_index = -1
                self.statusBar().showMessage(f"No match for {expression}")
                return
            self.search_index = 0
            self._select_nodes(self.search_results, focus=self.search_results[0])
            self.statusBar().showMessage(f"{len(self.search_results)} match(es) for {expression}")
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Search failed", str(error))

    def _find_nodes_by_predicate(self, document: TreeDocument, expression: str) -> list:
        progress = self._progress("Search tree", f"Searching for {expression}…")
        progress.setCancelButton(None)
        try:
            return document.root.pick().all_by_predicate(expression)
        finally:
            progress.close()

    def navigate_search(self, step: int) -> None:
        if not self.search_results:
            if self.search_expression:
                try:
                    document = self.current_document()
                    if document is None:
                        self.search_results = []
                    else:
                        self.search_results = self._find_nodes_by_predicate(
                            document, self.search_expression
                        )
                except Exception:
                    self.search_results = []
            if not self.search_results:
                self.search_nodes()
                return
        self.search_index = (self.search_index + step) % len(self.search_results)
        self._focus_node(self.search_results[self.search_index])

    def new_nodes(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        if document is None:
            return
        targets = self._current_nodes() or [document.root]
        created = []
        document.model.beginResetModel()
        try:
            for target in targets:
                document.model.prepare_for_structural_edit(target)
                name = unique_sibling_name(target, "NewNode")
                node = Node(name, "UserDefinedData_t")
                target.add_child(node, override_sibling_by_name=False)
                created.append(node)
        finally:
            document.model.endResetModel()
        document.mark_changed(full=True)
        if created:
            self._reveal_node(created[0])

    def _selected_nodes_or_current(self) -> list:
        nodes = self._current_nodes()
        if self._selected_node is not None and self._selected_node not in nodes:
            nodes = [self._selected_node]
        return nodes

    def rename_selected_nodes(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._selected_nodes_or_current()
        if document is None or not nodes:
            self.statusBar().showMessage("Select at least one node to rename")
            return
        requested, accepted = QtWidgets.QInputDialog.getText(
            self, "Rename node(s)", "New name:", text=nodes[0].name()
        )
        requested = str(requested).strip()
        if not accepted or not requested:
            return
        renamed = 0
        for node in nodes:
            if node is document.root:
                continue
            document.model.prepare_for_structural_edit(node.parent())
            rename_node_unique(node, requested)
            index = document.model.index_for_node(node)
            if index.isValid():
                document.model.dataChanged.emit(
                    index,
                    index.siblingAtColumn(2),
                    [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole],
                )
            renamed += 1
        if renamed:
            document.mark_changed(full=True)
            self.show_node(nodes[0])
            self.statusBar().showMessage(f"Renamed {renamed} node(s)")

    def set_selected_node_type(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._selected_nodes_or_current()
        if document is None or not nodes:
            self.statusBar().showMessage("Select at least one node to set its type")
            return
        requested, accepted = QtWidgets.QInputDialog.getText(
            self, "Set node type", "New type:", text=nodes[0].type()
        )
        requested = str(requested).strip()
        if not accepted or not requested:
            return
        changed = 0
        changed_nodes = []
        for node in nodes:
            if node is document.root:
                continue
            node.set_type(requested)
            index = document.model.index_for_node(node)
            if index.isValid():
                document.model.dataChanged.emit(
                    index,
                    index.siblingAtColumn(2),
                    [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole],
                )
            changed += 1
            changed_nodes.append(node)
        if changed:
            # Type is an attribute edit at the existing HDF5 path and is
            # supported by noder's targeted node writer.
            for node in changed_nodes:
                document.mark_changed(full=False, node=node)
            self.show_node(nodes[0])
            self.statusBar().showMessage(f"Set type for {changed} node(s)")

    def cut_nodes(self) -> None:
        if self.read_only:
            return
        self.copy_nodes()
        self.delete_nodes()

    def swap_nodes(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._current_nodes()
        if document is None or len(nodes) != 2 or nodes[0].parent() is not nodes[1].parent():
            self.statusBar().showMessage("Select exactly two sibling nodes to swap")
            return
        document.model.beginResetModel()
        try:
            document.model.prepare_for_structural_edit(nodes[0].parent())
            nodes[0].swap(nodes[1])
        finally:
            document.model.endResetModel()
        document.mark_changed(full=True)

    def _update_save_node_state(self) -> None:
        document = self.current_document()
        nodes = self._selected_nodes_or_current()
        enabled = (
            not self.read_only
            and document is not None
            and bool(document.filename)
            and any(node is not document.root for node in nodes)
            and not document.requires_full_write
        )
        self.save_node_button.setEnabled(enabled)

    def save_current_node(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._selected_nodes_or_current()
        if document is None:
            return
        nodes = [node for node in nodes if node is not document.root]
        if not nodes:
            return
        node = nodes[0]
        progress = self._progress("Save node", f"Saving {node.name()}…")
        try:
            for node in nodes:
                document.save_node_only(node)
            self.statusBar().showMessage(f"Saved {len(nodes)} node(s)")
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Save node failed", str(error))
        finally:
            progress.close()
            self._update_save_node_state()

    def dump_current_node_data(self) -> None:
        node = self._selected_node
        if node is None:
            self.statusBar().showMessage("Select a node with payload data first")
            return
        try:
            if not node.has_data():
                raise ValueError(f"Node {node.path()} has no payload")
            node.data()
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Dump node data",
                payload_dump_filename(node),
                "Text files (*.txt);;All files (*)",
            )
            if not filename:
                return
            if not filename.lower().endswith(".txt"):
                filename += ".txt"
            progress = self._progress("Dump data", f"Writing {Path(filename).name}â€¦")
            try:
                Path(filename).write_text(
                    "\n".join(payload_dump_lines(node)) + "\n",
                    encoding="utf-8",
                )
            finally:
                progress.close()
            self.statusBar().showMessage(f"Dumped data of node {node.path()} to {filename}")
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Dump data failed", str(error))

    def copy_nodes(self) -> None:
        nodes = self._current_nodes()
        self.clipboard_nodes = [node.copy(deep=True) for node in nodes]
        self.statusBar().showMessage(f"Copied {len(self.clipboard_nodes)} node(s)")

    def paste_nodes(self) -> None:
        if self.read_only or not self.clipboard_nodes:
            return
        document = self.current_document()
        nodes = self._current_nodes()
        if not document or not nodes:
            return
        document.model.beginResetModel()
        try:
            for target in nodes:
                document.model.prepare_for_structural_edit(target)
                for node in self.clipboard_nodes:
                    copied = node.copy(deep=True)
                    copied.set_name(unique_sibling_name(target, copied.name()))
                    target.add_child(copied, override_sibling_by_name=False)
        finally:
            document.model.endResetModel()
        document.mark_changed(full=True)

    def _read_link(self, document: TreeDocument, node) -> None:
        if not node.has_link_target():
            return
        target_file = node.link_target_file()
        if target_file:
            link_file = Path(target_file)
            if not link_file.is_absolute() and document.filename:
                link_file = Path(document.filename).resolve().parent / link_file
            target_filename = str(link_file)
        else:
            target_filename = document.filename
        if not target_filename:
            raise ValueError(f"No source file is available for link {node.path()}")
        reader = noder_io.LazyHdf5Reader(target_filename)
        try:
            target_root = reader.root()
            target_path = node.link_target_path()
            target = target_root.get_at_path(target_path)
            if target is None:
                raise ValueError(f"Link target does not exist: {target_filename}:{target_path}")
            self._materialise_node(target)
            parent = node.parent()
            if parent is None:
                raise ValueError("Cannot read a detached link node")
            children = list(node.children())
            for child in children:
                child.detach()
            node.clear_link_target()
            node.set_type(target.type())
            node.set_data(target.numpy() if target.has_data() else None)
            for child in target.children():
                node.add_child(child.copy(deep=True), override_sibling_by_name=False)
        finally:
            reader.close()

    @staticmethod
    def _materialise_node(node) -> None:
        node.ensure_children_loaded()
        if node.has_data():
            node.data()
        for child in node.children():
            MainWindow._materialise_node(child)

    def _read_links_operation(self, recursive: bool) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._current_nodes()
        if document is None or not nodes:
            return
        progress = self._progress("Read links", "Reading linked nodes…")
        count = 0
        read_nodes = []
        document.model.beginResetModel()
        try:
            for node in self._walk_nodes(nodes, recursive):
                if progress.wasCanceled():
                    break
                if node.has_link_target():
                    self._read_link(document, node)
                    count += 1
                    read_nodes.append(node)
                QtWidgets.QApplication.processEvents()
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Read link failed", str(error))
        finally:
            document.model.endResetModel()
            progress.close()
        view = self.current_view()
        if view is not None and view.document is document:
            for node in read_nodes:
                index = document.model.index_for_node(node)
                if index.isValid():
                    view.tree.expand(index)
        if count:
            document.mark_changed(full=True)
        self.statusBar().showMessage(f"Read {count} link(s)")

    def read_current_links(self) -> None:
        self._read_links_operation(False)

    def read_recursive_links(self) -> None:
        self._read_links_operation(True)

    def delete_nodes(self) -> None:
        view = self.current_view()
        if view:
            view.document.model.remove_nodes(view.tree.selected_nodes())

    def apply_current_tab_title(self) -> None:
        index = self.tabs.currentIndex()
        if 0 <= index < len(self.documents):
            document = self.documents[index]
            title = ("*" if document.dirty else "") + document.title
            self.tabs.setTabText(index, title)

    def _document_changed(self) -> None:
        self.apply_current_tab_title()
        self._update_sibling_info(self._selected_node)
        self._update_save_node_state()
        if self.plot_window is not None:
            self.plot_window.refresh_sources(redraw=self.plot_window.isVisible())

    def _switch_tab(self, step: int) -> None:
        count = len(self.documents)
        if count < 2:
            return
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % count)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # QTabWidget normally gives the tab bar focus when a QMainWindow is
        # first shown.  Defer one event turn so keyboard tree navigation starts
        # immediately on the newly opened root node.
        QtCore.QTimer.singleShot(0, self._focus_current_tree)

    def _focus_current_tree(self) -> None:
        view = self.current_view()
        if view is not None:
            view.tree.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def _current_tab_changed(self, _index: int) -> None:
        if _index == self._plus_tab_index():
            if self.documents:
                self.tabs.setCurrentIndex(min(self.tabs.currentIndex(), len(self.documents) - 1))
            return
        self.search_expression = ""
        self.search_results = []
        self.search_index = -1
        view = self.current_view()
        if view:
            nodes = view.tree.selected_nodes()
            self.show_node(nodes[0] if nodes else None)
            view.tree.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            self.apply_current_tab_title()
        if self.plot_window is not None:
            self.plot_window.refresh_sources()

    def _save_document(self, document: TreeDocument) -> bool:
        progress = self._progress("Save tree", f"Saving {document.title}…")
        try:
            document.save()
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(error))
            return False
        finally:
            progress.close()
        return True

    def save_current(self) -> None:
        document = self.current_document()
        if document and document.filename:
            self._save_document(document)
        elif document:
            self.save_as_current()

    def save_as_current(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        if not document:
            return
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CGNS file", document.filename or "tree.cgns", "CGNS files (*.cgns)"
        )
        if filename:
            self._save_document_as(document, filename)

    def _save_document_as(self, document: TreeDocument, filename: str) -> bool:
        progress = self._progress("Save tree", f"Saving {Path(filename).name}…")
        try:
            document.save(filename)
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(error))
            return False
        finally:
            progress.close()
        self.apply_current_tab_title()
        return True

    def _ensure_plot_window(self) -> PlotWindow:
        if self.plot_window is None:
            self.plot_window = PlotWindow(self)
        self.plot_window.refresh_sources()
        return self.plot_window

    def plot_selected(self) -> None:
        plot_window = self._ensure_plot_window()
        plot_window.plot_selected(self.current_document(), self._current_nodes())

    def add_selected_to_plot_x(self) -> None:
        if self._add_table_selection_to_plot("x"):
            return
        self._ensure_plot_window().add_selected_to_x()

    def add_selected_to_plot_y(self) -> None:
        if self._add_table_selection_to_plot("y"):
            return
        self._ensure_plot_window().add_selected_to_y()

    def add_plot_curve(self) -> None:
        plot_window = self._ensure_plot_window()
        plot_window.add_curve()
        plot_window.show_and_raise()

    def draw_plot_curves(self) -> None:
        plot_window = self._ensure_plot_window()
        plot_window.draw()
        plot_window.show_and_raise()

    def closeEvent(self, event) -> None:
        for document in reversed(self.documents):
            if document.dirty and not self.read_only:
                answer = QtWidgets.QMessageBox.question(
                    self, "Unsaved changes", f"Save changes to {document.title}?",
                    QtWidgets.QMessageBox.StandardButton.Save |
                    QtWidgets.QMessageBox.StandardButton.Discard |
                    QtWidgets.QMessageBox.StandardButton.Cancel,
                )
                if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if answer == QtWidgets.QMessageBox.StandardButton.Save and not self._save_document(document):
                    event.ignore()
                    return
            document.close()
        if self.plot_window is not None:
            self.plot_window.shutdown()
        event.accept()


def _table_value(value) -> str:
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", errors="replace").rstrip("\x00 ")
    if isinstance(value, (float, np.floating)):
        return f"{float(value):g}"
    return str(value)
