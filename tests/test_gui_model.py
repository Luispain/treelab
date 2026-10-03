from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from noder.core import Node
import noder.core.io as noder_io

from treelab.gui.document import TreeDocument
from treelab.gui.main import MainWindow
from treelab.gui.model import NoderTreeModel
from treelab.gui.payload import UNLOADED_MARKER
from treelab.gui.style import apply_fixed_light_palette


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
    window.close()
    qapp.processEvents()


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
        "Name", "Type", "Payload summary"
    ]
    assert model.data(data_index.siblingAtColumn(2)) == "min=0, max=11, mean=5.5, median=5.5"
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
