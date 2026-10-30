"""Dialogs for assigning links to nodes in a CGNS tree."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .document import TreeDocument


_CGNS_FILE_FILTER = "CGNS files (*.cgns *.hdf *.hdf5);;All files (*)"


def _path_without_root(node) -> str:
    path = str(node.path()).strip("/")
    root_name = str(node.root().name()).strip("/")
    if path == root_name:
        return ""
    prefix = root_name + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


class LinkTargetDialog(QtWidgets.QDialog):
    """Browse a target file without allowing edits or loading payloads."""

    def __init__(self, filename: str, *, safe_mode: bool = False, parent=None):
        super().__init__(parent)
        # Import here so MainWindow can import this dialog without a module cycle.
        from .window import TreeView

        self.setWindowTitle(f"Select link target — {Path(filename).name}")
        self.resize(800, 620)
        self.target_node_path: str | None = None
        self.document = TreeDocument(
            filename, read_only=True, safe_mode=safe_mode, parent=self
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Select a node in the target tree. Double-click it or press Enter to use it.",
                self,
            )
        )
        self.tree = TreeView(self.document, self)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.NoDragDrop)
        self.tree.setDropIndicatorShown(False)
        self.tree.setDefaultDropAction(QtCore.Qt.DropAction.IgnoreAction)
        self.tree.hideColumn(2)
        self.tree.header().resizeSection(0, 450)
        self.tree.header().resizeSection(1, 250)
        self.tree.installEventFilter(self)
        self.tree.selectionModel().selectionChanged.connect(self._update_accept_button)
        self.tree.doubleClicked.connect(lambda _index: self.accept_selected_node())
        self.tree.expanded.connect(self._load_remaining_children)
        layout.addWidget(self.tree, 1)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        self.select_button = self.buttons.addButton(
            "Use selected node", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.accept_selected_node)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        root_index = self.document.model.index(0, 0)
        self.tree.expand(root_index)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.tree
            and event.type() == QtCore.QEvent.Type.KeyPress
            and event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
        ):
            self.accept_selected_node()
            return True
        return super().eventFilter(watched, event)

    def _update_accept_button(self, *_args) -> None:
        self.select_button.setEnabled(bool(self.tree.selected_nodes()))

    def _load_remaining_children(self, index: QtCore.QModelIndex) -> None:
        """Load node metadata in pages, leaving every payload lazy."""
        model = self.document.model
        node = model.node(index)
        if node is None or not model.canFetchMore(index):
            return
        progress = QtWidgets.QProgressDialog(
            f"Loading children of {node.name()}…", "Cancel", 0,
            max(1, node.child_count()), self,
        )
        progress.setWindowTitle("Loading target tree")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()
        try:
            while model.canFetchMore(index) and not progress.wasCanceled():
                model.fetchMore(index)
                progress.setValue(model.rowCount(index))
                QtWidgets.QApplication.processEvents()
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self, "Loading target tree failed", str(error)
            )
        finally:
            progress.close()

    def accept_selected_node(self) -> None:
        nodes = self.tree.selected_nodes()
        if not nodes:
            return
        self.target_node_path = _path_without_root(nodes[0])
        self.accept()

    def closeEvent(self, event) -> None:
        self.document.close()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self.document.close()
        super().done(result)


class SetLinkDialog(QtWidgets.QDialog):
    """Choose a link target by entering its path or browsing a target tree."""

    def __init__(
        self,
        *,
        source_filename: str | None = None,
        safe_mode: bool = False,
        existing_link_file: str | None = None,
        existing_link_path: str | None = None,
        existing_link_root_name: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Set link")
        self.resize(650, 300)
        self.source_filename = source_filename
        self.safe_mode = safe_mode
        self.target_filename: str | None = None
        self.target_node_path: str | None = None
        self.use_relative_path = False

        layout = QtWidgets.QVBoxLayout(self)
        self.modes = QtWidgets.QTabWidget(self)
        layout.addWidget(self.modes)

        textual = QtWidgets.QWidget(self.modes)
        text_form = QtWidgets.QFormLayout(textual)
        self.node_path_edit = QtWidgets.QLineEdit(textual)
        self.node_path_edit.setPlaceholderText("Base/Zone/FlowSolution/Pressure")
        text_form.addRow("Target node path (without root)", self.node_path_edit)

        file_row = QtWidgets.QWidget(textual)
        file_layout = QtWidgets.QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.file_path_edit = QtWidgets.QLineEdit(file_row)
        self.file_path_edit.setPlaceholderText("Target CGNS file path")
        self.file_path_edit.textChanged.connect(self._update_accept_button)
        file_layout.addWidget(self.file_path_edit, 1)
        self.file_browse_button = QtWidgets.QPushButton("Browse…", file_row)
        self.file_browse_button.clicked.connect(self._browse_text_file)
        file_layout.addWidget(self.file_browse_button)
        text_form.addRow("Target file", file_row)
        self.node_path_edit.setText(
            self._path_without_root_component(
                existing_link_path, existing_link_root_name
            )
        )
        self.modes.addTab(textual, "Textual")

        visual = QtWidgets.QWidget(self.modes)
        visual_layout = QtWidgets.QVBoxLayout(visual)
        self.use_relative_checkbox = QtWidgets.QCheckBox("Use relative path", visual)
        visual_layout.addWidget(self.use_relative_checkbox)
        self.visual_file_label = QtWidgets.QLabel("No target file selected", visual)
        self.visual_file_label.setWordWrap(True)
        visual_layout.addWidget(self.visual_file_label)
        self.visual_target_label = QtWidgets.QLabel("No target node selected", visual)
        self.visual_target_label.setWordWrap(True)
        visual_layout.addWidget(self.visual_target_label)
        self.select_target_button = QtWidgets.QPushButton(
            "Select target file and node…", visual
        )
        self.select_target_button.clicked.connect(self._browse_visual_target)
        visual_layout.addWidget(self.select_target_button)
        visual_layout.addStretch(1)
        self.modes.addTab(visual, "Visual")

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        self.set_link_button = self.buttons.addButton(
            "Set Link", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.set_link_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.modes.currentChanged.connect(self._update_accept_button)
        self.file_path_edit.setText(existing_link_file or "")
        self._update_accept_button()

    def _update_accept_button(self, *_args) -> None:
        if self.modes.currentIndex() == 0:
            ready = bool(self.file_path_edit.text().strip())
        else:
            ready = self.target_filename is not None and self.target_node_path is not None
        self.set_link_button.setEnabled(ready)

    @staticmethod
    def _path_without_root_component(
        path: str | None, root_name: str | None
    ) -> str:
        parts = [part for part in str(path or "").strip("/").split("/") if part]
        if parts and root_name and parts[0] == root_name.strip("/"):
            parts = parts[1:]
        return "/".join(parts)

    def _browse_text_file(self) -> None:
        start = "."
        if self.source_filename:
            start = str(Path(self.source_filename).resolve().parent)
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select target CGNS file", start, _CGNS_FILE_FILTER
        )
        if filename:
            self.file_path_edit.setText(filename)

    def _browse_visual_target(self) -> None:
        start = "."
        if self.source_filename:
            start = str(Path(self.source_filename).resolve().parent)
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select target CGNS file", start, _CGNS_FILE_FILTER
        )
        if not filename:
            return
        try:
            browser = LinkTargetDialog(
                filename, safe_mode=self.safe_mode, parent=self
            )
        except Exception as error:
            QtWidgets.QMessageBox.warning(self, "Open target file failed", str(error))
            return
        if browser.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self.target_filename = Path(filename).resolve().as_posix()
        self.target_node_path = browser.target_node_path
        self.visual_file_label.setText(self.target_filename)
        self.visual_target_label.setText(
            self.target_node_path or "(target file root)"
        )
        self._update_accept_button()

    def target(self) -> tuple[str, str, bool]:
        """Return the chosen file path, path without root, and relative flag."""
        if self.modes.currentIndex() == 0:
            return (
                self.file_path_edit.text().strip(),
                self.node_path_edit.text().strip(),
                False,
            )
        return (
            self.target_filename or "",
            self.target_node_path or "",
            self.use_relative_checkbox.isChecked(),
        )
