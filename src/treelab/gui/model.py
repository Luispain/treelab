"""Qt model for a lazily loaded noder tree.

The model deliberately owns no CGNS-specific Python object model.  A Qt
index points directly at a :class:`noder.core.Node`, while the noder lazy
reader remains responsible for materialising children and payloads.
"""

from __future__ import annotations

from typing import Iterable
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .payload import payload_marker
from .style import palette_is_dark


_DRAG_NODES: dict[int, tuple[object, object]] = {}
_NEXT_DRAG_ID = 1
_ICON_CACHE: dict[tuple[str, bool], QtGui.QIcon] = {}
_ICON_ROOT = Path(__file__).resolve().parent / "icons"


def _brighten_icon(icon: QtGui.QIcon) -> QtGui.QIcon:
    pixmap = icon.pixmap(QtCore.QSize(64, 64))
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            hue, saturation, value, alpha = color.getHsv()
            if value < 190:
                value = 190 + int(value * 65 / 190)
                saturation = min(saturation, 230)
                color.setHsv(0 if hue < 0 else hue, saturation, value, alpha)
                image.setPixelColor(x, y, color)
    return QtGui.QIcon(QtGui.QPixmap.fromImage(image))


def _icon(relative_path: str) -> QtGui.QIcon:
    app = QtWidgets.QApplication.instance()
    dark = bool(app is not None and palette_is_dark(app))
    key = (relative_path, dark)
    icon = _ICON_CACHE.get(key)
    if icon is None:
        source = QtGui.QIcon(str(_ICON_ROOT / relative_path))
        icon = _brighten_icon(source) if dark and relative_path.startswith("icons8/") else source
        _ICON_CACHE[key] = icon
    return icon


def _node_icon(node) -> QtGui.QIcon:
    """Return the legacy CGNS icon associated with a node kind."""
    node_type = node.type()
    name = node.name()
    if node_type == "Root Node of HDF5 File":
        return _icon("fugue-icons-3.5.6/tree.png")
    if node_type == "Corrupted_t":
        return _icon("fugue-icons-3.5.6/tree-red.png")
    if node.parent() is None or node_type == "CGNSTree_t":
        return _icon("fugue-icons-3.5.6/tree.png")
    if node_type == "CGNSBase_t":
        return _icon("icons8/icons8-box-32.png")
    if node_type == "Zone_t":
        return _icon("icons8/zone-2D.png")
    if node_type == "GridCoordinates_t":
        return _icon("icons8/icons8-coordinate-system-16.png")
    if node_type == "FlowSolution_t":
        return _icon("OwnIcons/field-16.png")
    if node_type in {"Family_t", "FamilyName_t", "FamilyBC_t", "AdditionalFamilyName_t"}:
        return _icon("icons8/icons8-famille-homme-femme-26.png")
    if node_type == "ConvergenceHistory_t":
        return _icon("fugue-icons-3.5.6/system-monitor.png")
    if node_type == "ZoneGridConnectivity_t":
        return _icon("fugue-icons-3.5.6/plug-disconnect.png")
    if node_type == "ReferenceState_t":
        return _icon("fugue-icons-3.5.6/script-attribute-r.png")
    if node_type == "FlowEquationSet_t":
        return _icon("icons8/Sigma.png")
    if node_type == "UserDefinedData_t":
        return _icon("fugue-icons-3.5.6/user-silhouette.png")
    if node_type == "ZoneBC_t":
        return _icon("fugue-icons-3.5.6/border-left.png")
    if node_type == "Link_t" or getattr(node, "has_link_target", lambda: False)():
        return _icon("fugue-icons-3.5.6/external.png")
    if node_type == "DataArray_t":
        if not getattr(node, "data_is_loaded", lambda: True)():
            return _icon("fugue-icons-3.5.6/lightning.png")
        coordinate_icons = {
            "CoordinateX": "icons8/icons8-x-coordinate-16.png",
            "CoordinateY": "icons8/icons8-y-coordinate-16.png",
            "CoordinateZ": "icons8/icons8-z-coordinate-16.png",
        }
        if name in coordinate_icons:
            return _icon(coordinate_icons[name])
        return _icon("fugue-icons-3.5.6/blue-document-binary.png")
    return _icon("fugue-icons-3.5.6/blue-document-binary.png")


def _node_children(node, *, loaded_only: bool = True) -> list:
    if node is None:
        return []
    children = node.loaded_children() if loaded_only else node.children()
    return [child for child in children if child.name() != "CGNSLibraryVersion"]


def unique_sibling_name(parent, requested_name: str, *, exclude=None) -> str:
    """Return a name that is unique among ``parent``'s children.

    Noder deliberately allows callers to choose how duplicate sibling names
    are handled.  TreeLab's editing contract is to preserve the requested
    name when possible and otherwise append ``.0``, ``.1``, ... .  Loading all
    sibling metadata here is intentional: a partially loaded lazy parent must
    not make a valid existing name appear available.
    """
    requested_name = str(requested_name).strip()
    if parent is None or not requested_name:
        return requested_name
    parent.ensure_children_loaded()
    names = {
        child.name()
        for child in parent.loaded_children()
        if child is not exclude
    }
    if requested_name not in names:
        return requested_name
    suffix = 0
    while f"{requested_name}.{suffix}" in names:
        suffix += 1
    return f"{requested_name}.{suffix}"


def rename_node_unique(node, requested_name: str) -> str:
    """Rename one node using TreeLab's duplicate-sibling policy."""
    parent = node.parent()
    name = unique_sibling_name(parent, requested_name, exclude=node)
    node.set_name(name)
    return name


class NoderTreeModel(QtCore.QAbstractItemModel):
    """Paged, editable Qt model backed directly by noder nodes."""

    PAGE_SIZE = 128
    MIME_TYPE = "application/x-treelab-noder-node"

    def __init__(self, root, *, read_only: bool = False, parent=None):
        if not callable(getattr(root, "child_count", None)):
            raise RuntimeError(
                "TreeLab requires the current noder build exposing Node.child_count(). "
                "Update PYTHONPATH to the matching noder build/install directory."
            )
        super().__init__(parent)
        self.root = root
        self.read_only = read_only
        self._nodes: dict[int, object] = {}
        self._register(root)

    def _register(self, node):
        self._nodes[id(node)] = node
        return id(node)

    def set_root(self, root) -> None:
        self.beginResetModel()
        self.root = root
        self._nodes.clear()
        self._register(root)
        self.endResetModel()

    def _node(self, index: QtCore.QModelIndex):
        return self._nodes.get(index.internalId()) if index.isValid() else None

    def node(self, index: QtCore.QModelIndex):
        """Return the noder node represented by a Qt index."""
        return self._node(index)

    def index_for_node(self, node, column: int = 0) -> QtCore.QModelIndex:
        """Return an index for a node, loading only its ancestor metadata."""
        if node is None:
            return QtCore.QModelIndex()
        try:
            if node.root() is not self.root:
                return QtCore.QModelIndex()
        except Exception:
            return QtCore.QModelIndex()
        if node is not self.root:
            parent = node.parent()
            if parent is None:
                return QtCore.QModelIndex()
            parent.ensure_children_loaded()
            if node not in self._visible_loaded_children(parent):
                return QtCore.QModelIndex()
        return self._index_of(node, column)

    def _visible_loaded_children(self, node) -> list:
        return _node_children(node, loaded_only=True)

    def _row_of(self, node) -> int:
        parent = node.parent()
        if parent is None:
            return 0
        return self._visible_loaded_children(parent).index(node)

    def _index_of(self, node, column: int = 0) -> QtCore.QModelIndex:
        if node is self.root:
            return self.createIndex(0, column, self._register(node))
        return self.createIndex(self._row_of(node), column, self._register(node))

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 3

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return ("Name", "Type", "Payload summary (stats: min, max, mean, median)")[section] if section < 3 else None
        return None

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        if not parent.isValid():
            return 1
        node = self._node(parent)
        if node is None:
            return 0
        return len(self._visible_loaded_children(node))

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if row < 0 or column < 0 or column >= self.columnCount(parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            return self.createIndex(0, column, self._register(self.root)) if row == 0 else QtCore.QModelIndex()
        children = self._visible_loaded_children(self._node(parent))
        if row >= len(children):
            return QtCore.QModelIndex()
        return self.createIndex(row, column, self._register(children[row]))

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        node = self._node(index)
        if node is None:
            return QtCore.QModelIndex()
        if node is self.root:
            return QtCore.QModelIndex()
        parent = node.parent()
        if parent is self.root:
            return self._index_of(self.root)
        if parent is None:
            return QtCore.QModelIndex()
        return self._index_of(parent)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._node(index)
        if node is None:
            return None
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            if index.column() == 0:
                return node.name()
            if index.column() == 1:
                return node.type()
            if index.column() == 2:
                return payload_marker(node)
            return None
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return node.path()
        if role == QtCore.Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return _node_icon(node)
        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        node = self._node(index)
        if node is None:
            return QtCore.Qt.ItemFlag.NoItemFlags
        if not self.read_only and node is not self.root:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
            flags |= QtCore.Qt.ItemFlag.ItemIsDragEnabled
        if not self.read_only:
            flags |= QtCore.Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole):
        if self.read_only or role != QtCore.Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        node = self._node(index)
        text = str(value).strip()
        if not text:
            return False
        if index.column() == 0:
            parent = node.parent()
            self._prepare_parent_for_edit(parent)
            rename_node_unique(node, text)
        elif index.column() == 1:
            node.set_type(text)
        else:
            return False
        self.dataChanged.emit(index, index, [role, QtCore.Qt.ItemDataRole.DisplayRole])
        # A type is stored as an HDF5 attribute at the existing group path,
        # so it can use targeted save_this_node_only. A name changes that
        # path and therefore still requires the complete writer.
        self._document_changed(
            full=index.column() == 0,
            node=node if index.column() == 1 else None,
        )
        return True

    def hasChildren(self, parent=QtCore.QModelIndex()) -> bool:
        if not parent.isValid():
            return True
        node = self._node(parent)
        return node is not None and node.child_count() > 0

    def canFetchMore(self, parent):
        if not parent.isValid():
            return False
        node = self._node(parent)
        if node is None:
            return False
        return node.children_load_state() != "complete" and len(self._visible_loaded_children(node)) < node.child_count()

    def fetchMore(self, parent):
        if not self.canFetchMore(parent):
            return
        node = self._node(parent)
        before = len(self._visible_loaded_children(node))
        total = node.child_count()
        after = min(total, before + self.PAGE_SIZE)
        if after <= before:
            return
        self.beginInsertRows(parent, before, after - 1)
        node.ensure_children_loaded(before + self.PAGE_SIZE)
        self.endInsertRows()

    def ensure_visible_children(self, node) -> None:
        """Load one page, or all root children, without loading payloads."""
        if node is self.root:
            node.ensure_children_loaded()
        elif node.children_load_state() == "unloaded":
            node.ensure_children_loaded(self.PAGE_SIZE)

    @staticmethod
    def _is_ancestor(ancestor, node) -> bool:
        current = node
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent()
        return False

    @staticmethod
    def _prepare_parent_for_edit(node) -> None:
        """Detach lazy metadata only after every child has been loaded.

        Noder's expansion owns the unseen children of a partially loaded node.
        Clearing that expansion before loading the remainder would make a
        structural save omit those children.  Structural edits are already on
        the full-write path, so paying the metadata-only load here is the safe
        trade-off; payloads remain lazy until the full writer materialises them.
        """
        if node is None:
            return
        node.ensure_children_loaded()
        node.clear_expansion()

    def prepare_for_structural_edit(self, node) -> None:
        if not self.read_only:
            self._prepare_parent_for_edit(node)

    @staticmethod
    def _materialise_for_transfer(node) -> None:
        """Make a moved subtree independent of its source reader."""
        node.ensure_children_loaded()
        if node.has_data():
            node.data()
        for child in node.loaded_children():
            NoderTreeModel._materialise_for_transfer(child)
        node.clear_expansion()

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, indexes):
        global _NEXT_DRAG_ID
        nodes = []
        seen = set()
        for index in indexes:
            if index.column() != 0 or not index.isValid():
                continue
            node = self._node(index)
            if id(node) not in seen and node is not self.root:
                seen.add(id(node))
                nodes.append(node)
        ids = []
        for node in nodes:
            token = _NEXT_DRAG_ID
            _NEXT_DRAG_ID += 1
            _DRAG_NODES[token] = (self, node)
            ids.append(str(token))
        mime = QtCore.QMimeData()
        mime.setData(self.MIME_TYPE, ",".join(ids).encode("ascii"))
        return mime

    def supportedDropActions(self):
        return QtCore.Qt.DropAction.CopyAction | QtCore.Qt.DropAction.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if (self.read_only or action not in (QtCore.Qt.DropAction.CopyAction,
                                             QtCore.Qt.DropAction.MoveAction)
                or not data.hasFormat(self.MIME_TYPE)):
            return False
        target = self.root if not parent.isValid() else self._node(parent)
        if target is None:
            return False
        try:
            tokens = [int(item) for item in bytes(data.data(self.MIME_TYPE)).decode("ascii").split(",") if item]
            drag_entries = [_DRAG_NODES[token] for token in tokens]
        except (KeyError, ValueError, UnicodeDecodeError):
            return False
        if not drag_entries:
            return False
        source_models = [entry[0] for entry in drag_entries]
        source_nodes = [entry[1] for entry in drag_entries]
        if any(node.parent() is None for node in source_nodes):
            return False
        if any(source_model.read_only for source_model in source_models
               if action == QtCore.Qt.DropAction.MoveAction):
            return False
        if any(source_model is self and self._is_ancestor(source, target)
               for source_model, source in zip(source_models, source_nodes)):
            return False

        is_move = action == QtCore.Qt.DropAction.MoveAction
        reset_models = []
        for source_model in source_models:
            if is_move and not any(source_model is item for item in reset_models):
                reset_models.append(source_model)
        if not any(self is item for item in reset_models):
            reset_models.append(self)
        for model in reset_models:
            model.beginResetModel()
        try:
            parents = []
            for source in source_nodes:
                old_parent = source.parent()
                if old_parent is not None and not any(old_parent is item for item in parents):
                    parents.append(old_parent)
            if not any(target is item for item in parents):
                parents.append(target)
            for node in parents:
                self._prepare_parent_for_edit(node)

            if is_move:
                for source_model, source in zip(source_models, source_nodes):
                    if source_model is not self:
                        self._materialise_for_transfer(source)

            for source in source_nodes:
                node = source if is_move else source.copy(deep=True)
                if is_move:
                    node.detach()
                node.set_name(unique_sibling_name(target, node.name()))
                node.attach_to(
                    target,
                    position=row if row >= 0 else -1,
                    override_sibling_by_name=False,
                )
                if row >= 0:
                    row += 1
        finally:
            for model in reversed(reset_models):
                model.endResetModel()
        for source_model in source_models:
            if is_move and source_model is not self:
                source_model._document_changed(full=True)
        self._document_changed(full=True)
        for token in tokens:
            _DRAG_NODES.pop(token, None)
        return True

    def remove_nodes(self, nodes: Iterable) -> None:
        if self.read_only:
            return
        nodes = [node for node in nodes if node is not self.root and node.parent() is not None]
        if not nodes:
            return
        parents = []
        for node in nodes:
            parent = node.parent()
            if parent is not None and not any(parent is item for item in parents):
                parents.append(parent)
        self.beginResetModel()
        try:
            for parent in parents:
                self._prepare_parent_for_edit(parent)
            for node in nodes:
                node.detach()
        finally:
            self.endResetModel()
        self._document_changed(full=True)

    def _document_changed(self, *, full: bool, node=None) -> None:
        document = QtCore.QObject.parent(self)
        if document is not None and hasattr(document, "mark_changed"):
            document.mark_changed(full=full, node=node)
