"""Treelab's Qt window and the small set of editing interactions it owns."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .document import TreeDocument
from .payload import (
    PAYLOAD_ELEMENT_LIMIT,
    UNLOADED_MARKER,
    payload_array,
)


GUI_PATH = Path(__file__).resolve().parent
TREE_ICON = GUI_PATH / "icons" / "fugue-icons-3.5.6" / "tree.png"


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
        header = self.header()
        header.setStretchLastSection(False)
        for section in range(3):
            header.setSectionResizeMode(section, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 360)
        header.resizeSection(1, 130)
        header.resizeSection(2, 300)

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

    def __init__(self, filenames=(), *, read_only: bool = False, parent=None):
        super().__init__(parent)
        self.read_only = read_only
        self.documents: list[TreeDocument] = []
        self.views: list[DocumentView] = []
        self.clipboard_nodes: list = []
        self.setWindowTitle("TreeLab")
        if TREE_ICON.exists():
            self.setWindowIcon(QtGui.QIcon(str(TREE_ICON)))

        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
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

        self.action_open = QtGui.QAction("Open…", self)
        self.action_open.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_dialog)
        file_menu.addAction(self.action_open)

        self.action_new = QtGui.QAction("New", self)
        self.action_new.setShortcut(QtGui.QKeySequence.StandardKey.New)
        self.action_new.triggered.connect(self.new_document)
        file_menu.addAction(self.action_new)

        self.action_save = QtGui.QAction("Save", self)
        self.action_save.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_current)
        file_menu.addAction(self.action_save)

        self.action_save_as = QtGui.QAction("Save As…", self)
        self.action_save_as.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self.save_as_current)
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()
        action_quit = QtGui.QAction("Quit", self)
        action_quit.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        self.action_copy = QtGui.QAction("Copy node(s)", self)
        self.action_copy.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        self.action_copy.triggered.connect(self.copy_nodes)
        edit_menu.addAction(self.action_copy)

        self.action_paste = QtGui.QAction("Paste node(s)", self)
        self.action_paste.setShortcut(QtGui.QKeySequence.StandardKey.Paste)
        self.action_paste.triggered.connect(self.paste_nodes)
        edit_menu.addAction(self.action_paste)

        self.action_delete = QtGui.QAction("Delete node(s)", self)
        self.action_delete.setShortcut(QtGui.QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self.delete_nodes)
        edit_menu.addAction(self.action_delete)

        self.action_plot = QtGui.QAction("Plot selected data", self)
        self.action_plot.triggered.connect(self.plot_selected)
        view_menu.addAction(self.action_plot)

        self.action_load_payload = QtGui.QAction("Load data (F5)", self)
        self.action_load_payload.setShortcut(QtGui.QKeySequence("F5"))
        self.action_load_payload.triggered.connect(self.load_selected_data)
        view_menu.addAction(self.action_load_payload)

        toolbar = self.addToolBar("Tree")
        toolbar.setMovable(False)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_copy)
        toolbar.addAction(self.action_paste)
        toolbar.addAction(self.action_plot)

        if self.read_only:
            for action in (self.action_new, self.action_save, self.action_save_as,
                           self.action_paste, self.action_delete):
                action.setEnabled(False)

    def _make_property_dock(self) -> None:
        self.dock = QtWidgets.QDockWidget("Node", self)
        self.dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        panel = QtWidgets.QWidget(self.dock)
        form = QtWidgets.QFormLayout(panel)
        self.name_edit = QtWidgets.QLineEdit(panel)
        self.type_edit = QtWidgets.QLineEdit(panel)
        self.value_edit = QtWidgets.QPlainTextEdit(panel)
        self.value_edit.setPlaceholderText("Replacement value (optional)")
        self.payload_info = QtWidgets.QLabel(panel)
        self.payload_info.setWordWrap(True)
        self.payload_table = QtWidgets.QTableWidget(panel)
        self.payload_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.payload_table.setAlternatingRowColors(True)
        self.payload_table.setMinimumHeight(180)
        self.payload_axis = QtWidgets.QComboBox(panel)
        self.payload_axis.addItems(["axis 0", "axis 1", "axis 2"])
        self.payload_slice = QtWidgets.QSpinBox(panel)
        self.payload_slice.setMinimum(0)
        slice_controls = QtWidgets.QWidget(panel)
        slice_layout = QtWidgets.QHBoxLayout(slice_controls)
        slice_layout.setContentsMargins(0, 0, 0, 0)
        slice_layout.addWidget(self.payload_axis)
        slice_layout.addWidget(self.payload_slice)
        self.apply_button = QtWidgets.QPushButton("Apply", panel)
        self.plot_button = QtWidgets.QPushButton("Plot", panel)
        form.addRow("Name", self.name_edit)
        form.addRow("Type", self.type_edit)
        form.addRow("Payload", self.payload_info)
        form.addRow(self.payload_table)
        form.addRow("Slice", slice_controls)
        form.addRow("Replacement", self.value_edit)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.plot_button)
        form.addRow(buttons)
        self.dock.setWidget(panel)
        self.apply_button.clicked.connect(self.apply_node_edits)
        self.plot_button.clicked.connect(self.plot_selected)
        self.payload_axis.currentIndexChanged.connect(self._refresh_payload_table)
        self.payload_slice.valueChanged.connect(self._refresh_payload_table)
        self._selected_node = None
        self._refresh_payload_table()
        if self.read_only:
            self.name_edit.setReadOnly(True)
            self.type_edit.setReadOnly(True)
            self.value_edit.setReadOnly(True)
            self.apply_button.setEnabled(False)

    def current_view(self) -> DocumentView | None:
        index = self.tabs.currentIndex()
        return self.views[index] if index >= 0 else None

    def current_document(self) -> TreeDocument | None:
        view = self.current_view()
        return view.document if view else None

    def new_document(self) -> None:
        document = TreeDocument(read_only=self.read_only, parent=self)
        self._add_document(document)

    def open_dialog(self) -> None:
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open CGNS file", ".", "CGNS files (*.cgns *.hdf *.hdf5);;All files (*)"
        )
        for filename in filenames:
            self.open_file(filename)

    def open_file(self, filename: str) -> None:
        try:
            document = TreeDocument(filename, read_only=self.read_only, parent=self)
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(error))
            return
        self._add_document(document)

    def _add_document(self, document: TreeDocument) -> None:
        view = DocumentView(document, self)
        view.selection_changed.connect(self.show_node)
        document.changed.connect(self._document_changed)
        self.documents.append(document)
        self.views.append(view)
        self.tabs.addTab(view, document.title)
        self.tabs.setCurrentWidget(view)
        root_index = document.model.index(0, 0)
        self._expand_root_and_bases(view, root_index)

    def _expand_root_and_bases(self, view: DocumentView, root_index) -> None:
        view.tree.expand(root_index)
        for row in range(view.document.model.rowCount(root_index)):
            view.tree.collapse(view.document.model.index(row, 0, root_index))

    def close_tab(self, index: int) -> None:
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
        document.close()
        self.tabs.removeTab(index)
        self.views.pop(index)
        self.documents.pop(index)
        if not self.documents:
            self.new_document()

    def _current_nodes(self) -> list:
        view = self.current_view()
        return view.tree.selected_nodes() if view else []

    def show_node(self, node) -> None:
        self._selected_node = node
        if node is None:
            self.dock.setWindowTitle("Node")
            self.name_edit.clear()
            self.type_edit.clear()
            self.value_edit.clear()
            self.payload_info.clear()
            self._refresh_payload_table()
            return
        self.dock.setWindowTitle(node.path())
        self.name_edit.setText(node.name())
        self.type_edit.setText(node.type())
        try:
            if not node.has_data():
                self.value_edit.setPlainText("")
            elif getattr(node, "data_is_loaded", lambda: True)():
                self.value_edit.setPlainText(_format_value(node.numpy()))
            else:
                self.value_edit.clear()
        except Exception as error:
            self.value_edit.clear()
            self.payload_info.setText(f"Payload unavailable: {error}")
        self._refresh_payload_table()

    def _refresh_payload_table(self, *_args) -> None:
        table = getattr(self, "payload_table", None)
        if table is None:
            return
        table.clear()
        table.setRowCount(0)
        table.setColumnCount(0)
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
            self.payload_slice.setMaximum(maximum)
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
        self.payload_table.setRowCount(rows)
        self.payload_table.setColumnCount(columns)
        for row_index, row in enumerate(values):
            for column_index, value in enumerate(row):
                self.payload_table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(str(value)))
        self.payload_table.resizeColumnsToContents()
        self.payload_table.resizeRowsToContents()

    def load_selected_data(self) -> None:
        nodes = self._current_nodes()
        if not nodes:
            return

        def load_subtree(node) -> None:
            if node.has_data():
                node.data()
            node.ensure_children_loaded()
            for child in node.loaded_children():
                load_subtree(child)

        try:
            for node in nodes:
                load_subtree(node)
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Payload unavailable", str(error))
            return
        for view in self.views:
            view.document.model.layoutChanged.emit()
        self.statusBar().showMessage(f"Loaded data for {len(nodes)} selected node(s)")
        self.show_node(nodes[0])

    def apply_node_edits(self) -> None:
        if self.read_only:
            return
        document = self.current_document()
        nodes = self._current_nodes()
        if not document or len(nodes) != 1:
            return
        node = nodes[0]
        name = self.name_edit.text().strip()
        node_type = self.type_edit.text().strip()
        if name and name != node.name():
            node.set_name(name)
            document.mark_changed(full=True)
        if node_type and node_type != node.type():
            node.set_type(node_type)
            document.mark_changed(full=True)
        text = self.value_edit.toPlainText().strip()
        if text:
            try:
                value = _parse_value(text)
            except (ValueError, SyntaxError) as error:
                QtWidgets.QMessageBox.warning(self, "Value not changed", str(error))
            else:
                document.edit_node_data(node, value)
        document.model.layoutChanged.emit()
        self.show_node(node)

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
        target = nodes[0]
        document.model.beginResetModel()
        try:
            document.model.prepare_for_structural_edit(target)
            for node in self.clipboard_nodes:
                target.add_child(node.copy(deep=True))
        finally:
            document.model.endResetModel()
        document.mark_changed(full=True)

    def delete_nodes(self) -> None:
        view = self.current_view()
        if view:
            view.document.model.remove_nodes(view.tree.selected_nodes())

    def apply_current_tab_title(self) -> None:
        index = self.tabs.currentIndex()
        if index >= 0:
            document = self.documents[index]
            title = ("*" if document.dirty else "") + document.title
            self.tabs.setTabText(index, title)

    def _document_changed(self) -> None:
        self.apply_current_tab_title()

    def _current_tab_changed(self, _index: int) -> None:
        view = self.current_view()
        if view:
            nodes = view.tree.selected_nodes()
            self.show_node(nodes[0] if nodes else None)
            self.apply_current_tab_title()

    def _save_document(self, document: TreeDocument) -> bool:
        try:
            document.save()
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(error))
            return False
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
        try:
            document.save(filename)
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(error))
            return False
        self.apply_current_tab_title()
        return True

    def plot_selected(self) -> None:
        nodes = self._current_nodes()
        if not nodes:
            return
        try:
            import matplotlib
            matplotlib.use("QtAgg", force=True)
            import matplotlib.pyplot as plt
            figure, axes = plt.subplots()
            series = []
            for node in nodes:
                array = node.numpy()
                if array is None or not np.issubdtype(np.asarray(array).dtype, np.number):
                    continue
                series.append((node, np.asarray(array).ravel(order="K")))
            if not series:
                raise ValueError("The selected node(s) have no numeric payload")
            if len(series) == 2 and series[0][1].size == series[1][1].size:
                axes.plot(series[0][1], series[1][1], label=f"{series[1][0].name()} vs {series[0][0].name()}")
                axes.set_xlabel(series[0][0].name())
                axes.set_ylabel(series[1][0].name())
            else:
                for node, values in series:
                    axes.plot(values, label=node.name())
            axes.set_title(nodes[0].path())
            axes.legend()
            figure.show()
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Plot unavailable", str(error))

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
        event.accept()


def _format_value(value) -> str:
    if value is None:
        return ""
    array = np.asarray(value)
    if array.size > 2000:
        return f"{array.dtype} shape={array.shape} ({array.size} values)"
    return repr(value)


def _table_value(value) -> str:
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", errors="replace").rstrip("\x00 ")
    if isinstance(value, (float, np.floating)):
        return f"{float(value):g}"
    return str(value)


def _parse_value(text: str):
    parsed = ast.literal_eval(text)
    if parsed is None or isinstance(parsed, (int, float, complex, str, bool)):
        return parsed
    return np.asarray(parsed)
