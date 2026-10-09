from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtTest import QTest

from noder.core import Node
import noder.core.io as noder_io

from treelab.gui.document import TreeDocument
from treelab.gui.main import MainWindow
from treelab.gui.model import NoderTreeModel
from treelab.gui.new_payload import NewPayloadDialog
from treelab.gui.payload import UNLOADED_MARKER
from treelab.gui.style import (
    apply_fixed_dark_palette,
    apply_fixed_light_palette,
    apply_system_palette,
    palette_is_dark,
    system_prefers_dark,
)


@pytest.fixture(scope="session")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication(["treelab-tests"])


def _tree(children):
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    root.add_child(base)
    for name in children:
        base.add_child(Node(name, "Zone_t"))
    return root


def _base(document):
    root_index = document.model.index(0, 0)
    base = next(child for child in document.root.loaded_children() if child.name() != "CGNSLibraryVersion")
    return base, document.model.index(0, 0, root_index)


def _names(filename):
    root = noder_io.read(str(filename))
    return [child.name() for child in root.get_at_path("Base").children()]


def test_fixed_light_palette_covers_native_state_groups(qapp):
    apply_fixed_light_palette(qapp)
    palette = qapp.palette()
    for group in (QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorGroup.Inactive):
        assert palette.color(group, QtGui.QPalette.ColorRole.Window).name() == "#f2f2f2"
        assert palette.color(group, QtGui.QPalette.ColorRole.WindowText).name() == "#202124"
        assert palette.color(group, QtGui.QPalette.ColorRole.Button).name() == "#eeeeee"
    assert palette.color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText).name() == "#8a8a8a"


def test_dark_palette_and_toolbar_theme_switcher(qapp):
    apply_fixed_dark_palette(qapp)
    assert palette_is_dark(qapp)
    assert qapp.palette().color(QtGui.QPalette.ColorRole.Base).name() == "#17181a"
    assert "QMenuBar" in qapp.styleSheet()

    window = MainWindow([])
    try:
        assert window.action_toggle_theme.text() == "Switch to light mode"
        window.toggle_theme()
        assert not palette_is_dark(qapp)
        assert window.action_toggle_theme.text() == "Switch to dark mode"
    finally:
        window.close()
        apply_fixed_light_palette(qapp)


def test_system_palette_follows_qt_color_scheme(qapp):
    expected_dark = system_prefers_dark(qapp)
    apply_system_palette(qapp)
    assert palette_is_dark(qapp) is expected_dark
    apply_fixed_light_palette(qapp)


def test_open_file_tree_has_visible_model_rows(tmp_path, qapp):
    filename = tmp_path / "visible-tree.cgns"
    _tree(["Zone"]).write(str(filename))
    apply_fixed_light_palette(qapp)

    window = MainWindow([str(filename)])
    window.resize(800, 600)
    window.show()
    qapp.processEvents()
    tree = window.current_view().tree
    root_index = tree.model().index(0, 0)

    assert tree.model().rowCount(root_index) == 1
    assert tree.visualRect(root_index).height() > 0
    assert tree.selected_nodes() == [tree.model().node(root_index)]
    assert tree.hasFocus()
    toolbar = window.findChild(QtWidgets.QToolBar, "treeToolsToolbar")
    assert toolbar is not None
    assert toolbar.isMovable()
    assert toolbar.isFloatable()
    assert window.action_open.statusTip() == "Open (Ctrl+O)"
    assert window.action_new_payload.shortcut().toString() == "Shift+Enter"
    assert [shortcut.toString() for shortcut in window.action_new_payload.shortcuts()] == [
        "Shift+Enter", "Shift+Return"
    ]
    assert window.action_new_payload.statusTip() == "New payload (Shift+Enter)"
    window.close()
    qapp.processEvents()


def test_new_payload_shortcut_opens_dialog_from_tree(qapp, monkeypatch):
    opened = []

    class RejectedPayloadDialog:
        def __init__(self, parent):
            opened.append(parent)

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "treelab.gui.window.NewPayloadDialog", RejectedPayloadDialog
    )
    window = MainWindow([])
    window.show()
    tree = window.current_view().tree
    tree.setFocus()
    qapp.processEvents()
    QTest.keyClick(
        tree,
        QtCore.Qt.Key.Key_Return,
        QtCore.Qt.KeyboardModifier.ShiftModifier,
    )
    qapp.processEvents()
    assert opened == [window]
    window.close()


def test_safe_mode_shows_dialog_and_corrupted_marker(tmp_path, qapp, monkeypatch):
    h5py = pytest.importorskip("h5py")
    filename = tmp_path / "safe-mode.cgns"
    with h5py.File(filename, "w", track_order=True) as h5file:
        h5file.attrs["name"] = np.bytes_("HDF5 MotherNode")
        h5file.attrs["label"] = np.bytes_("Root Node of HDF5 File")
        h5file.attrs["type"] = np.bytes_("MT")
        malformed = h5file.create_group("MissingLabel", track_order=True)
        malformed.attrs["name"] = np.bytes_("MissingLabel")
        malformed.attrs["type"] = np.bytes_("MT")
        valid = h5file.create_group("Valid", track_order=True)
        valid.attrs["name"] = np.bytes_("Valid")
        valid.attrs["label"] = np.bytes_("UserDefinedData_t")
        valid.attrs["type"] = np.bytes_("MT")

    dialogs = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        staticmethod(lambda *args: dialogs.append(args)),
    )
    window = MainWindow([str(filename)], safe_mode=True)
    document = window.current_document()
    assert document.reader.has_warnings()
    assert [child.name() for child in document.root.loaded_children()] == [
        "Corrupted", "Valid"
    ]
    assert any(
        "Malformed nodes where found during reading, search using / t:Corrupted_t" in args[-1]
        for args in dialogs
    )
    window.close()


def test_full_load_materialises_user_defined_descendants(tmp_path, qapp):
    filename = tmp_path / "full-udd.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    metadata = Node("Metadata", "UserDefinedData_t")
    nested = Node("Nested", "UserDefinedData_t")
    payload = Node("Payload", "DataArray_t")
    payload.set_data(np.arange(5, dtype=np.float64))
    nested.add_child(payload)
    metadata.add_child(nested)
    for index in range(180):
        extra = Node(f"Extra{index}", "UserDefinedData_t")
        extra_payload = Node("Value", "DataArray_t")
        extra_payload.set_data(np.array([index], dtype=np.float64))
        extra.add_child(extra_payload)
        metadata.add_child(extra)
    base.add_child(metadata)
    root.add_child(base)
    root.write(str(filename))

    window = MainWindow([str(filename)], full_load=True)
    loaded = window.current_document().root.get_at_path("Base/Metadata/Nested/Payload")
    assert loaded.data_is_loaded()
    assert loaded.numpy().tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]
    window.current_document().dirty = False
    window.close()


def test_search_selects_all_matches_and_f3_only_moves_focus(tmp_path, qapp, monkeypatch):
    filename = tmp_path / "search-selection.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    for index in range(3):
        base.add_child(Node(f"Zone{index}", "Zone_t"))
    root.add_child(base)
    root.write(str(filename))

    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: ("/ t:Zone_t", True)),
    )
    window = MainWindow([str(filename)])
    progress_titles = []
    original_progress = window._progress

    def tracked_progress(title, label):
        progress_titles.append(title)
        return original_progress(title, label)

    monkeypatch.setattr(window, "_progress", tracked_progress)
    window.search_nodes()
    assert "Search tree" in progress_titles
    tree = window.current_view().tree
    assert [node.name() for node in tree.selected_nodes()] == ["Zone0", "Zone1", "Zone2"]
    window.navigate_search(1)
    assert [node.name() for node in tree.selected_nodes()] == ["Zone0", "Zone1", "Zone2"]
    assert tree.model().node(tree.currentIndex()).name() == "Zone1"
    window.current_document().dirty = False
    window.close()


def test_paste_keeps_duplicate_names_by_suffixing(tmp_path, qapp):
    filename = tmp_path / "paste-suffix.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    target = Node("Target", "UserDefinedData_t")
    target.add_child(Node("Child", "DataArray_t"))
    source = Node("Source", "UserDefinedData_t")
    source.add_child(Node("Child", "DataArray_t"))
    root.add_child(target)
    root.add_child(source)
    root.write(str(filename))

    window = MainWindow([str(filename)])
    tree = window.current_view().tree
    root_index = tree.model().index(0, 0)
    source_index = tree.model().index(1, 0, root_index)
    target_index = tree.model().index(0, 0, root_index)
    tree.model().fetchMore(source_index)
    source_child_index = tree.model().index(0, 0, source_index)
    selection = tree.selectionModel()
    selection.select(
        source_child_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect |
        QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
    window.copy_nodes()
    selection.clearSelection()
    selection.select(
        target_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect |
        QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
    window.paste_nodes()
    target_node = window.current_document().root.get_at_path("Target")
    assert [child.name() for child in target_node.children()] == ["Child", "Child.0"]
    window.current_document().dirty = False
    window.close()


def test_save_node_targets_only_the_edited_payload(tmp_path, qapp):
    filename = tmp_path / "save-node.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    payload = Node("Value", "DataArray_t")
    payload.set_data(np.array([1.0, 2.0]))
    root.add_child(payload)
    root.write(str(filename))

    window = MainWindow([str(filename)])
    node = window.current_document().root.get_at_path("Value")
    window.show_node(node)
    window.payload_table.item(0, 0).setText("9.5")
    assert window.save_node_button.isEnabled()
    window.save_current_node()
    saved = noder_io.read(str(filename)).get_at_path("Value")
    assert saved.numpy().tolist() == [9.5, 2.0]
    assert not window.current_document().dirty
    assert not hasattr(window, "name_edit")
    assert window.action_close_tab.shortcut().toString() == "Ctrl+W"
    window.close()


def test_save_node_button_handles_name_and_type_edits(tmp_path, qapp):
    filename = tmp_path / "save-node-metadata.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    node = Node("Value", "UserDefinedData_t")
    node.set_data(np.array([1.0]))
    root.add_child(node)
    root.write(str(filename))

    window = MainWindow([str(filename)])
    document = window.current_document()
    tree = window.current_view().tree
    root_index = tree.model().index(0, 0)
    node_index = tree.model().index(0, 0, root_index)
    tree.selectionModel().select(
        node_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect |
        QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
    tree.selectionModel().setCurrentIndex(
        node_index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
    )

    assert document.model.setData(
        node_index.siblingAtColumn(1),
        "DataArray_t",
        QtCore.Qt.ItemDataRole.EditRole,
    )
    assert window.save_node_button.isEnabled()
    window.save_current_node()
    saved = noder_io.read(str(filename))
    assert saved.get_at_path("Value").type() == "DataArray_t"
    assert not document.dirty

    assert document.model.setData(node_index, "Renamed")
    assert not window.save_node_button.isEnabled()
    window.save_current()
    saved = noder_io.read(str(filename))
    assert saved.get_at_path("Renamed") is not None
    assert not document.dirty
    window.close()


def test_new_payload_and_save_node_propagate_to_all_selected_nodes(tmp_path, qapp, monkeypatch):
    filename = tmp_path / "multi-save-node.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    for name in ("First", "Second"):
        node = Node(name, "DataArray_t")
        node.set_data(np.array([0.0, 0.0]))
        root.add_child(node)
    root.write(str(filename))

    window = MainWindow([str(filename)])
    tree = window.current_view().tree
    root_index = tree.model().index(0, 0)
    first = tree.model().index(0, 0, root_index)
    second = tree.model().index(1, 0, root_index)
    selection = tree.selectionModel()
    selection.clearSelection()
    selection.select(
        first,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect |
        QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )
    selection.select(
        second,
        QtCore.QItemSelectionModel.SelectionFlag.Select |
        QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )

    class AcceptedPayloadDialog:
        def __init__(self, parent):
            pass

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def expression(self):
            return "np.arange(2) + 4"

    monkeypatch.setattr(
        "treelab.gui.window.NewPayloadDialog", AcceptedPayloadDialog
    )
    window.new_payload()
    assert [node.numpy().tolist() for node in window._current_nodes()] == [
        [4.0, 5.0], [4.0, 5.0]
    ]
    window.save_current_node()
    saved = noder_io.read(str(filename))
    assert saved.get_at_path("First").numpy().tolist() == [4.0, 5.0]
    assert saved.get_at_path("Second").numpy().tolist() == [4.0, 5.0]
    assert not window.current_document().dirty
    window.close()


def test_new_payload_direct_sibling_references(qapp, monkeypatch):
    window = MainWindow([])
    root = window.current_document().root
    for name, values in (
        ("CoordinateX", [1.0, 2.0, 3.0]),
        ("CoordinateY", [1.0, 4.0, 2.0]),
        ("CoordinateZ", [0.0, 0.0, 0.0]),
    ):
        node = Node(name, "DataArray_t")
        node.set_data(np.asarray(values))
        root.add_child(node)
    target = root.get_at_path("CoordinateZ")
    window.show_node(target)

    class AcceptedPayloadDialog:
        def __init__(self, parent):
            pass

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def expression(self):
            return '"{CoordinateX}" / "{CoordinateY}"'

    monkeypatch.setattr(
        "treelab.gui.window.NewPayloadDialog", AcceptedPayloadDialog
    )
    window.new_payload()

    np.testing.assert_allclose(target.numpy(), [1.0, 0.5, 1.5])
    window.current_document().dirty = False
    window.close()


def test_new_payload_dialog_remembers_text_and_shift_enter(qapp):
    previous = NewPayloadDialog._last_expression
    try:
        NewPayloadDialog._last_expression = ""
        first = NewPayloadDialog()
        first.editor.setPlainText("np.arange(3)")
        first.reject()

        second = NewPayloadDialog()
        assert second.expression() == "np.arange(3)"
        second.show()
        second.editor.setFocus()
        qapp.processEvents()
        QTest.keyClick(
            second.editor,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        qapp.processEvents()
        assert second.result() == QtWidgets.QDialog.DialogCode.Accepted
        second.close()
    finally:
        NewPayloadDialog._last_expression = previous


def test_rename_paths_suffix_duplicate_siblings_and_multi_edit(qapp, monkeypatch):
    window = MainWindow([])
    root = window.current_document().root
    first = Node("First", "UserDefinedData_t")
    second = Node("Second", "UserDefinedData_t")
    root.add_child(first)
    root.add_child(second)
    model = window.current_document().model
    root_index = model.index(0, 0)
    second_index = model.index(1, 0, root_index)

    assert model.setData(second_index, "First")
    assert [node.name() for node in root.children()] == ["First", "First.0"]

    tree = window.current_view().tree
    indexes = [model.index(0, 0, root_index), model.index(1, 0, root_index)]
    selection = tree.selectionModel()
    selection.clearSelection()
    for position, index in enumerate(indexes):
        selection.select(
            index,
            (QtCore.QItemSelectionModel.SelectionFlag.Clear if position == 0 else
             QtCore.QItemSelectionModel.SelectionFlag.NoUpdate) |
            QtCore.QItemSelectionModel.SelectionFlag.Select |
            QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: ("Renamed", True)),
    )
    window.rename_selected_nodes()
    assert [node.name() for node in root.children()] == ["Renamed", "Renamed.0"]

    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: ("DataArray_t", True)),
    )
    window.set_selected_node_type()
    assert [node.type() for node in root.children()] == ["DataArray_t", "DataArray_t"]
    window.current_document().dirty = False
    window.close()


def test_structural_delete_preserves_unloaded_lazy_siblings(tmp_path, qapp):
    filename = tmp_path / "lazy-delete.cgns"
    _tree([f"Zone{index:03d}" for index in range(300)]).write(str(filename))

    document = TreeDocument(str(filename), parent=qapp)
    base, base_index = _base(document)
    assert document.model.rowCount(base_index) == 0
    document.model.fetchMore(base_index)
    removed = document.model.node(document.model.index(0, 0, base_index))

    document.model.remove_nodes([removed])
    document.save()

    names = _names(filename)
    assert len(names) == 299
    assert "Zone000" not in names
    assert "Zone299" in names
    document.close()


def test_targeted_payload_save_keeps_unrelated_children_lazy(tmp_path, qapp):
    filename = tmp_path / "lazy-payload.cgns"
    _tree([f"Zone{index:03d}" for index in range(300)]).write(str(filename))

    document = TreeDocument(str(filename), parent=qapp)
    base, base_index = _base(document)
    document.model.fetchMore(base_index)
    target = document.model.node(document.model.index(0, 0, base_index))
    document.edit_node_data(target, np.array([42], dtype=np.int32))
    assert base.children_load_state() == "partial"

    document.save()

    assert base.children_load_state() == "partial"
    saved = noder_io.read(str(filename)).get_at_path("Base/Zone000")
    assert int(saved.data().getPyArray()[0]) == 42
    document.close()


def test_cross_document_move_marks_and_persists_both_documents(tmp_path, qapp):
    source_filename = tmp_path / "source.cgns"
    target_filename = tmp_path / "target.cgns"
    _tree(["MovedZone"]).write(str(source_filename))
    _tree(["ExistingZone"]).write(str(target_filename))

    source = TreeDocument(str(source_filename), parent=qapp)
    target = TreeDocument(str(target_filename), parent=qapp)
    source_base, source_base_index = _base(source)
    target_base, target_base_index = _base(target)
    source_base.ensure_children_loaded()
    source_index = source.model.index(0, 0, source_base_index)
    mime = source.model.mimeData([source_index])

    assert target.model.dropMimeData(
        mime,
        QtCore.Qt.DropAction.MoveAction,
        -1,
        0,
        target_base_index,
    )
    assert source.dirty
    assert target.dirty

    source.save()
    target.save()
    assert _names(source_filename) == []
    assert _names(target_filename) == ["ExistingZone", "MovedZone"]
    source.close()
    target.close()


def test_drag_move_suffixes_a_conflicting_sibling_name(tmp_path, qapp):
    source_filename = tmp_path / "drag-source.cgns"
    target_filename = tmp_path / "drag-target.cgns"
    _tree(["Child"]).write(str(source_filename))
    _tree(["Child"]).write(str(target_filename))

    source = TreeDocument(str(source_filename), parent=qapp)
    target = TreeDocument(str(target_filename), parent=qapp)
    _source_base, source_base_index = _base(source)
    _target_base, target_base_index = _base(target)
    source.model.fetchMore(source_base_index)
    source_index = source.model.index(0, 0, source_base_index)
    mime = source.model.mimeData([source_index])

    assert target.model.dropMimeData(
        mime,
        QtCore.Qt.DropAction.MoveAction,
        -1,
        0,
        target_base_index,
    )
    target_base = target.root.get_at_path("Base")
    assert [child.name() for child in target_base.children()] == ["Child", "Child.0"]
    source.dirty = False
    target.dirty = False
    source.close()
    target.close()


def test_model_columns_icons_and_payload_marker(qapp):
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    zone = Node("Zone", "Zone_t")
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.arange(12, dtype=np.float64).reshape(3, 4))
    zone.add_child(payload)
    base.add_child(zone)
    root.add_child(base)
    model = NoderTreeModel(root, parent=qapp)

    root_index = model.index(0, 0)
    base_index = model.index(0, 0, root_index)
    zone_index = model.index(0, 0, base_index)
    data_index = model.index(0, 0, zone_index)
    assert [model.headerData(i, QtCore.Qt.Orientation.Horizontal) for i in range(3)] == [
        "Name", "Type", "Payload summary (stats: min, max, mean, median)"
    ]
    assert model.data(data_index.siblingAtColumn(2)) == "stats: 0, 11, 5.5, 5.5"
    icons = [model.data(index, QtCore.Qt.ItemDataRole.DecorationRole).cacheKey()
             for index in (root_index, base_index, zone_index)]
    assert len(set(icons)) == 3


def test_payload_table_shows_loaded_values(qapp):
    root = Node("CGNSTree", "CGNSTree_t")
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.arange(6, dtype=np.float64).reshape(2, 3))
    root.add_child(payload)
    window = MainWindow([])
    window.show_node(payload)
    assert window.payload_table.item(0, 0).text() == "0"
    assert window.payload_table.item(1, 2).text() == "5"
    window.close()


def test_payload_view_shows_sibling_count(qapp):
    window = MainWindow([])
    nodes = [Node(name, "UserDefinedData_t") for name in ("One", "Two", "Three")]
    for node in nodes:
        window.current_document().root.add_child(node)

    window.show_node(nodes[1])

    assert window.siblings_info.text() == "Number of siblings: 2"
    window.close()


def test_root_level_sibling_count_excludes_hidden_library_version(tmp_path, qapp):
    filename = tmp_path / "root-siblings.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    root.add_child(Node("BaseA", "CGNSBase_t"))
    root.add_child(Node("BaseB", "CGNSBase_t"))
    root.write(str(filename))

    window = MainWindow([str(filename)])
    document = window.current_document()
    window.show_node(document.root.get_at_path("BaseA"))

    assert window.siblings_info.text() == "Number of siblings: 1"
    document.dirty = False
    window.close()


def test_expanding_large_branch_shows_progress_and_loads_all_children(
    tmp_path, qapp
):
    filename = tmp_path / "large-branch.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    branch = Node("Branch", "UserDefinedData_t")
    for index in range(300):
        branch.add_child(Node(f"Child{index}", "UserDefinedData_t"))
    root.add_child(branch)
    root.write(str(filename))
    window = MainWindow([str(filename)])
    document = window.current_document()
    tree = window.current_view().tree
    branch_index = document.model.index_for_node(document.root.get_at_path("Branch"))
    assert document.model.canFetchMore(branch_index)
    progress_titles = []
    original_progress = window._progress

    def tracked_progress(title, label):
        progress_titles.append(title)
        return original_progress(title, label)

    window._progress = tracked_progress
    tree.expand(branch_index)
    qapp.processEvents()

    assert "Loading children" in progress_titles
    assert document.model.rowCount(branch_index) == 300
    assert document.root.get_at_path("Branch").children_load_state() == "complete"
    window.close()


def test_read_link_expands_and_displays_recursively_copied_children(
    tmp_path, qapp
):
    target_filename = tmp_path / "link-target.cgns"
    source_filename = tmp_path / "link-source.cgns"
    target_root = Node("CGNSTree", "CGNSTree_t")
    target = Node("Ap", "UserDefinedData_t")
    child = Node("Child", "UserDefinedData_t")
    grandchild = Node("Grandchild", "DataArray_t")
    grandchild.set_data(np.array([4.0, 5.0]))
    child.add_child(grandchild)
    target.add_child(child)
    target_root.add_child(target)
    target_root.write(str(target_filename))

    source_root = Node("CGNSTree", "CGNSTree_t")
    link = Node("A", "Link_t")
    link.set_link_target(str(target_filename), "/CGNSTree/Ap")
    source_root.add_child(link)
    source_root.write(str(source_filename))

    window = MainWindow([str(source_filename)])
    document = window.current_document()
    tree = window.current_view().tree
    root_index = document.model.index(0, 0)
    link_index = document.model.index(0, 0, root_index)
    tree.selectionModel().select(
        link_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QtCore.QItemSelectionModel.SelectionFlag.Rows,
    )

    window.read_current_links()

    loaded = document.root.get_at_path("A")
    assert not loaded.has_link_target()
    loaded_child = loaded.children()[0]
    assert loaded_child.name() == "Child"
    loaded_grandchild = loaded_child.children()[0]
    assert loaded_grandchild.name() == "Grandchild"
    assert loaded_grandchild.numpy().tolist() == [4.0, 5.0]
    loaded_index = document.model.index_for_node(loaded)
    assert tree.isExpanded(loaded_index)
    assert document.model.rowCount(loaded_index) == 1
    document.dirty = False
    window.close()


def test_new_tab_action_and_permanent_plus_tab(qapp):
    window = MainWindow([])

    assert window.action_new_tab.shortcut().toString() == "Ctrl+Shift+T"
    assert not hasattr(window, "action_new")
    toolbar = window.findChild(QtWidgets.QToolBar, "treeToolsToolbar")
    assert toolbar is not None
    assert window.action_new_tab not in toolbar.actions()
    assert window.tabs.count() == len(window.documents) + 1
    plus_index = window._plus_tab_index()
    assert not window.tabs.tabIcon(plus_index).isNull()

    window._tab_bar_clicked(plus_index)
    assert len(window.documents) == 2
    assert window.tabs.count() == len(window.documents) + 1
    assert window.tabs.currentIndex() == len(window.documents) - 1
    window.close()


def test_payload_path_is_copyable_and_dump_data(tmp_path, monkeypatch, qapp):
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.array([1.0, 2.0, 3.0]))
    base.add_child(payload)
    root.add_child(base)

    window = MainWindow([])
    window.current_document().root = root
    output = tmp_path / "density.txt"
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(output), "Text files (*.txt)"),
    )
    window.show_node(payload)
    window.dump_current_node_data()

    assert window.node_path_edit.isReadOnly()
    assert window.node_path_edit.text() == "Base/Density"
    assert not hasattr(window, "plot_button")
    assert window.new_payload_button.text() == "New payload"
    assert output.read_text(encoding="utf-8") == "1 2 3\n"
    window.close()


def test_new_payload_reference_resolves_an_open_tab_read_only(qapp):
    window = MainWindow([])
    source = Node("Source", "DataArray_t")
    source.set_data(np.arange(4, dtype=float))
    window.current_document().root.add_child(source)

    values = window._resolve_payload_reference("Untitled", "Source")

    np.testing.assert_array_equal(values, np.arange(4, dtype=float))
    assert not values.flags.writeable
    window.close()


def test_selected_payload_cells_can_be_registered_for_plotting(qapp):
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.arange(6, dtype=float).reshape(2, 3))
    window = MainWindow([])
    window.show_node(payload)
    table = window.payload_table
    table.setRangeSelected(QtWidgets.QTableWidgetSelectionRange(0, 0, 1, 1), True)

    window.add_selected_to_plot_x()

    source = window.plot_window.session.x_sources[0]
    np.testing.assert_array_equal(source.values, np.array([[0.0, 1.0], [3.0, 4.0]]))
    assert " from selected cells of table" in window.statusBar().currentMessage()
    window.close()


def test_lazy_payload_marker_does_not_load_data(tmp_path, qapp):
    filename = tmp_path / "lazy-marker.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    base = Node("Base", "CGNSBase_t")
    zone = Node("Zone", "Zone_t")
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.arange(4, dtype=np.float64))
    zone.add_child(payload)
    base.add_child(zone)
    root.add_child(base)
    root.write(str(filename))

    document = TreeDocument(str(filename), parent=qapp)
    root_index = document.model.index(0, 0)
    base_index = document.model.index(0, 0, root_index)
    document.model.fetchMore(base_index)
    zone_index = document.model.index(0, 0, base_index)
    document.model.fetchMore(zone_index)
    data_index = document.model.index(0, 0, zone_index)
    node = document.model.node(data_index)
    assert not node.data_is_loaded()
    assert document.model.data(data_index.siblingAtColumn(2)) == UNLOADED_MARKER
    assert not node.data_is_loaded()
    document.close()


def test_lazy_payload_can_be_unloaded_and_reloaded(tmp_path, qapp):
    filename = tmp_path / "lazy-unload.cgns"
    root = Node("CGNSTree", "CGNSTree_t")
    payload = Node("Density", "DataArray_t")
    payload.set_data(np.arange(4, dtype=np.float64))
    root.add_child(payload)
    root.write(str(filename))

    document = TreeDocument(str(filename), parent=qapp)
    node = document.root.get_at_path("Density")
    assert not node.data_is_loaded()
    assert node.numpy().tolist() == [0.0, 1.0, 2.0, 3.0]
    node.unload_data()
    assert not node.data_is_loaded()
    assert node.numpy().tolist() == [0.0, 1.0, 2.0, 3.0]
    document.close()
