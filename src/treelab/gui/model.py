"""Qt model for a lazily loaded noder tree.

The model deliberately owns no CGNS-specific Python object model.  A Qt
index points directly at a :class:`noder.core.Node`, while the noder lazy
reader remains responsible for materialising children and payloads.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Iterable
import uuid

from PySide6 import QtCore, QtGui, QtWidgets
from noder.core import Node
import noder.core.io as noder_io

from .payload import payload_marker
from .style import palette_is_dark


_DRAG_NODES: dict[str, tuple[object, object]] = {}
_LOGGER = logging.getLogger(__name__)
_ICON_CACHE: dict[tuple[str, bool], QtGui.QIcon] = {}
_ICON_ROOT = Path(__file__).resolve().parent / "icons"
_DARK_TREE_ICONS = {
    "fugue-icons-3.5.6/plug-disconnect.png",
    "fugue-icons-3.5.6/border-left.png",
    "fugue-icons-3.5.6/chain.png",
}


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
        needs_brightening = (
            relative_path.startswith("icons8/")
            or relative_path in _DARK_TREE_ICONS
        )
        icon = _brighten_icon(source) if dark and needs_brightening else source
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
    if node_type == "CGNSLibraryVersion_t":
        return _icon("CGNS_logo_nobckgrnd.svg")
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
        return _icon("fugue-icons-3.5.6/chain.png")
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
    return node.loaded_children() if loaded_only else node.children()


def _is_link_node(node) -> bool:
    return node.type() == "Link_t" or bool(
        getattr(node, "has_link_target", lambda: False)()
    )


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

    children_page_loaded = QtCore.Signal(object, int)

    PAGE_SIZE = 128
    MIME_TYPE = "application/x-treelab-noder-node"
    TRANSFER_DATA_MIME_TYPE = "application/x-treelab-noder-bundle"
    TRANSFER_METADATA_MIME_TYPE = "application/x-treelab-noder-metadata+json"

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
        self._revealed_links: dict[int, object] = {}
        self._bulk_loading: set[int] = set()
        self._transfer_progress_callback = None
        self._drag_progress_callback = None
        self._automatic_fetch_nodes: dict[int, object] = {}
        self._defer_fetch_predicate = None
        self._fetching_enabled = True
        self._visible_children_cache: dict[int, tuple[str, int, list]] = {}
        self._register(root)

    def _register(self, node):
        self._nodes[id(node)] = node
        return id(node)

    def _clear_visible_children_cache(self) -> None:
        self._visible_children_cache.clear()

    @contextmanager
    def external_tree_traversal(self):
        """Notify Qt around noder traversals that may load child metadata.

        Navigation helpers such as ``all_by_predicate`` can materialize lazy
        children without going through this model's paged fetch methods. Keep
        the view's row counts and scroll range in sync when that happens.
        """
        self.layoutAboutToBeChanged.emit()
        try:
            yield
        finally:
            self._clear_visible_children_cache()
            self.layoutChanged.emit()

    def set_root(self, root) -> None:
        self.beginResetModel()
        self.root = root
        self._nodes.clear()
        self._revealed_links.clear()
        self._automatic_fetch_nodes.clear()
        self._clear_visible_children_cache()
        self._register(root)
        self.endResetModel()

    def reveal_link_ancestors(self, nodes: Iterable[object]) -> None:
        """Expose link descendants needed to show selected search results."""
        revealed = {}
        for node in nodes:
            parent = node.parent() if node is not None else None
            while parent is not None:
                if _is_link_node(parent):
                    revealed[id(parent)] = parent
                parent = parent.parent()

        if revealed.keys() == self._revealed_links.keys():
            return
        self.beginResetModel()
        self._revealed_links = revealed
        self._nodes.clear()
        self._automatic_fetch_nodes.clear()
        self._clear_visible_children_cache()
        self._register(self.root)
        self.endResetModel()

    def _node(self, index: QtCore.QModelIndex):
        return self._nodes.get(index.internalId()) if index.isValid() else None

    def node(self, index: QtCore.QModelIndex):
        """Return the noder node represented by a Qt index."""
        return self._node(index)

    def set_defer_fetch_predicate(self, predicate) -> None:
        """Let a view defer automatic expansion fetches to its progress UI."""
        self._defer_fetch_predicate = predicate

    def enable_automatic_fetch(self, node) -> None:
        """Allow a tree view to request later pages as the user scrolls."""
        if node is not None:
            self._automatic_fetch_nodes[id(node)] = node

    def set_fetching_enabled(self, enabled: bool) -> None:
        """Disable lazy reads after the owning document closes."""
        self._fetching_enabled = bool(enabled)
        if not self._fetching_enabled:
            self._automatic_fetch_nodes.clear()

    def has_more_children(self, index: QtCore.QModelIndex) -> bool:
        """Return whether a node has lazy children, without counting them."""
        if (
            not self._fetching_enabled
            or not index.isValid()
        ):
            return False
        node = self._node(index)
        if node is None or id(node) in self._bulk_loading:
            return False
        if _is_link_node(node) and id(node) not in self._revealed_links:
            return False
        return (
            node.children_load_state() != "complete"
            and (
                bool(self._visible_loaded_children(node))
                or self._node_has_children(node)
            )
        )

    def _node_has_children(self, node) -> bool:
        """Probe only the first child instead of counting a whole HDF5 group."""
        if self._visible_loaded_children(node):
            return True
        if node.children_load_state() == "complete" or not self._fetching_enabled:
            return False
        ensure_children_loaded = getattr(node, "ensure_children_loaded", None)
        if not callable(ensure_children_loaded):
            return False

        try:
            # Node.child_count() asks the lazy HDF5 reader to inspect every
            # group entry. Loading one node stops at the first actual group,
            # so large branches keep their expander without a full scan.
            with self.external_tree_traversal():
                ensure_children_loaded(1)
        except Exception:
            # Keep an expander so opening the branch can surface the read error.
            return node.children_load_state() != "complete"
        return bool(self._visible_loaded_children(node))

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
            if node not in self._visible_loaded_children(parent):
                parent.ensure_children_loaded()
                self._visible_children_cache.pop(id(parent), None)
                if node not in self._visible_loaded_children(parent):
                    return QtCore.QModelIndex()
        return self._index_of(node, column)

    def _visible_loaded_children(self, node) -> list:
        # Keep a link atomic unless a search result needs its target path shown.
        if (
            node is not None
            and _is_link_node(node)
            and id(node) not in self._revealed_links
        ):
            return []
        state = node.children_load_state()
        cached = self._visible_children_cache.get(id(node))
        if cached is not None and cached[0] == state:
            # A completed lazy HDF5 node may not have a cached total yet, so
            # child_count() can still scan the entire group. Large snapshots
            # are invalidated by model mutations/page loads; reuse them here.
            if state != "complete" or cached[1] > self.PAGE_SIZE:
                return cached[2]
        children = _node_children(node, loaded_only=True)
        self._visible_children_cache[id(node)] = (state, len(children), children)
        return children

    def _row_of(self, node) -> int:
        parent = node.parent()
        if parent is None:
            return 0
        return self._visible_loaded_children(parent).index(node)

    def _index_of(self, node, column: int = 0) -> QtCore.QModelIndex:
        if node is self.root:
            return self.createIndex(0, column, self._register(node))
        try:
            row = self._row_of(node)
        except ValueError:
            return QtCore.QModelIndex()
        return self.createIndex(row, column, self._register(node))

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
        if (
            node is not None
            and _is_link_node(node)
            and id(node) not in self._revealed_links
        ):
            return False
        if node is None:
            return False
        if self._visible_loaded_children(node):
            return True
        return self._node_has_children(node)

    def canFetchMore(self, parent):
        # The lazy reader's exact child count may require scanning thousands
        # of HDF5 links. Its load state is enough to tell Qt whether a branch
        # may have more children; page loading determines the actual count.
        return self.has_more_children(parent)

    def fetchMore(self, parent):
        node = self._node(parent)
        if (
            self._defer_fetch_predicate is not None
            and self._defer_fetch_predicate(parent)
            and self._automatic_fetch_nodes.get(id(node)) is not node
        ):
            return
        if not self.canFetchMore(parent):
            return
        self.load_next_children_page(node)

    def load_next_children_page(self, node) -> int:
        """Load at most one metadata page and return its cumulative size."""
        if node is None or node.children_load_state() == "complete":
            return len(node.loaded_children()) if node is not None else 0
        before = len(self._visible_loaded_children(node))
        self._bulk_loading.add(id(node))
        self.layoutAboutToBeChanged.emit()
        try:
            node.ensure_children_loaded(before + self.PAGE_SIZE)
        finally:
            self._clear_visible_children_cache()
            try:
                self.layoutChanged.emit()
            finally:
                self._bulk_loading.discard(id(node))
        count = len(node.loaded_children())
        self.children_page_loaded.emit(node, count)
        return count

    def ensure_visible_children(self, node) -> None:
        """Load one page, or all root children, without loading payloads."""
        if node is self.root:
            node.ensure_children_loaded()
            self._visible_children_cache.pop(id(node), None)
        elif node.children_load_state() == "unloaded":
            node.ensure_children_loaded(self.PAGE_SIZE)
            self._visible_children_cache.pop(id(node), None)

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
    def _materialise_for_transfer(node, progress_callback=None) -> None:
        """Load a subtree for serialization, reporting progress in batches."""
        pending = [node]
        visited = 0
        while pending:
            current = pending.pop()
            if _is_link_node(current):
                continue
            current.ensure_children_loaded()
            if current.has_data():
                current.data()
            children = list(current.loaded_children())
            current.clear_expansion()
            pending.extend(reversed(children))
            visited += 1
            if progress_callback is not None and visited % 64 == 0:
                progress_callback(f"Preparing subtree… {visited:,} nodes loaded")

    @staticmethod
    def _encode_nodes(
        nodes, source_filename: str | None, progress_callback=None
    ) -> tuple[bytes, bytes]:
        """Serialize node subtrees into a self-contained CGNS clipboard bundle."""
        container = Node("CGNSTree", "CGNSTree_t")
        transfer_root = Node("TreeLabClipboard", "UserDefinedData_t")
        container.add_child(transfer_root)

        def drop_link_expansions(node) -> None:
            if _is_link_node(node):
                for child in list(node.loaded_children()):
                    child.detach()
                node.clear_expansion()
                return
            for child in node.loaded_children():
                drop_link_expansions(child)

        link_base = source_filename or str(Path.cwd() / "untitled.cgns")
        for index, original in enumerate(nodes):
            NoderTreeModel._materialise_for_transfer(
                original, progress_callback=progress_callback
            )
            clone = original.copy(deep=True)
            NoderTreeModel.rebase_link_targets(clone, link_base, None)
            drop_link_expansions(clone)
            entry = Node(f"TransferNode{index:08d}", "UserDefinedData_t")
            entry.add_child(clone)
            transfer_root.add_child(entry, override_sibling_by_name=False)
            if progress_callback is not None:
                progress_callback(f"Bundled {index + 1:,} of {len(nodes):,} nodes")

        if progress_callback is not None:
            progress_callback("Writing transfer bundle…")
        with tempfile.TemporaryDirectory(prefix="treelab-transfer-") as folder:
            filename = Path(folder) / "nodes.cgns"
            container.write(str(filename), strict_types=False)
            payload = filename.read_bytes()

        metadata = json.dumps({
            "version": 2,
            "source_filename": (
                str(Path(source_filename).resolve()) if source_filename else None
            ),
            "node_count": len(nodes),
        }).encode("utf-8")
        if progress_callback is not None:
            progress_callback("Transfer bundle ready")
        return payload, metadata

    @staticmethod
    def _open_transfer_bundle(
        payload: bytes,
        metadata_payload: bytes,
        progress_callback=None,
    ) -> tuple[list, dict, object, str]:
        """Open a transfer file lazily and return its reader with the nodes."""
        if not payload:
            raise ValueError("The clipboard does not contain TreeLab nodes")
        try:
            metadata = json.loads(metadata_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("The TreeLab clipboard metadata is invalid") from error
        if not isinstance(metadata, dict) or metadata.get("version") != 2:
            raise ValueError("This TreeLab clipboard version is not supported")

        descriptor, filename = tempfile.mkstemp(
            prefix="treelab-transfer-", suffix=".cgns"
        )
        reader = None
        try:
            with os.fdopen(descriptor, "wb") as transfer_file:
                transfer_file.write(payload)
            if progress_callback is not None:
                progress_callback("Opening transferred tree…")
            reader = noder_io.LazyHdf5Reader(filename)
            nodes = NoderTreeModel._nodes_from_transfer_reader(
                reader, metadata, progress_callback=progress_callback
            )
            return nodes, metadata, reader, filename
        except Exception:
            if reader is not None:
                reader.close()
            try:
                Path(filename).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _nodes_from_transfer_reader(reader, metadata, progress_callback=None):
        """Return detached bundle entries while retaining their lazy reader."""
        pending = [reader.root()]
        transfer_root = None
        for _depth in range(3):
            next_level = []
            for candidate in pending:
                if candidate.name() == "TreeLabClipboard":
                    transfer_root = candidate
                    break
                reader.ensure_children_loaded(candidate)
                next_level.extend(candidate.loaded_children())
            if transfer_root is not None:
                break
            pending = next_level
        if transfer_root is None:
            raise ValueError("The clipboard CGNS file has no TreeLab node bundle")

        if progress_callback is not None:
            progress_callback("Reading transferred node headers…")
        reader.ensure_children_loaded(transfer_root)
        entries = list(transfer_root.loaded_children())
        expected_count = metadata.get("node_count")
        if expected_count != len(entries):
            raise ValueError("The clipboard node count does not match its bundle")

        nodes = []
        for index, entry in enumerate(entries, start=1):
            reader.ensure_children_loaded(entry)
            children = list(entry.loaded_children())
            if len(children) != 1:
                raise ValueError("The clipboard contains an invalid node entry")
            node = children[0]
            node.detach()
            nodes.append(node)
            if progress_callback is not None and index % 64 == 0:
                progress_callback(
                    f"Reading node headers… {index:,} of {len(entries):,}"
                )
        return nodes

    @staticmethod
    def _open_existing_transfer_bundle(filename, metadata, progress_callback=None):
        """Open another lazy reader for a second paste destination."""
        reader = noder_io.LazyHdf5Reader(filename)
        try:
            nodes = NoderTreeModel._nodes_from_transfer_reader(
                reader, metadata, progress_callback=progress_callback
            )
            return nodes, reader
        except Exception:
            reader.close()
            raise

    @staticmethod
    def rebase_link_targets(node, source_filename: str | None,
                            destination_filename: str | None) -> None:
        """Keep relative links pointing at the same file after a transfer."""
        if not source_filename:
            return
        source_directory = Path(source_filename).resolve().parent
        destination_directory = (
            Path(destination_filename).resolve().parent
            if destination_filename
            else None
        )

        def visit(current) -> None:
            if _is_link_node(current):
                if current.has_link_target():
                    target_file = current.link_target_file()
                    if target_file and not Path(target_file).is_absolute():
                        absolute_target = (source_directory / target_file).resolve()
                        if destination_directory is None:
                            stored_target = absolute_target.as_posix()
                        else:
                            try:
                                stored_target = Path(os.path.relpath(
                                    absolute_target, destination_directory
                                )).as_posix()
                            except ValueError:
                                # Windows cannot make a relative path between
                                # separate drive letters.
                                stored_target = absolute_target.as_posix()
                        current.set_link_target(
                            stored_target, current.link_target_path()
                        )
                return
            for child in current.loaded_children():
                visit(child)

        visit(node)

    def transfer_mime_data(self, nodes, *, progress_callback=None) -> QtCore.QMimeData:
        """Build clipboard MIME data usable by this or another TreeLab process."""
        mime = QtCore.QMimeData()
        if not nodes:
            return mime
        document = QtCore.QObject.parent(self)
        source_filename = getattr(document, "filename", None)
        with self.external_tree_traversal():
            payload, metadata = self._encode_nodes(
                nodes, source_filename, progress_callback=progress_callback
            )
        mime.setData(self.TRANSFER_DATA_MIME_TYPE, payload)
        mime.setData(self.TRANSFER_METADATA_MIME_TYPE, metadata)
        return mime

    @classmethod
    def has_registered_drag(cls, data) -> bool:
        """Whether a drag token belongs to a live TreeLab model in this process."""
        if not data.hasFormat(cls.MIME_TYPE):
            return False
        try:
            tokens = [
                item
                for item in bytes(data.data(cls.MIME_TYPE))
                .decode("ascii")
                .split(",")
                if item
            ]
            return bool(tokens) and all(token in _DRAG_NODES for token in tokens)
        except (ValueError, UnicodeDecodeError):
            return False

    def registered_drag_tokens(self) -> set[str]:
        return {
            token
            for token, (source_model, _node) in _DRAG_NODES.items()
            if source_model is self
        }

    def release_drag_tokens(self, tokens) -> None:
        for token in tokens:
            entry = _DRAG_NODES.get(token)
            if entry is not None and entry[0] is self:
                _DRAG_NODES.pop(token, None)

    def mimeTypes(self):
        return [
            self.MIME_TYPE,
            self.TRANSFER_DATA_MIME_TYPE,
            self.TRANSFER_METADATA_MIME_TYPE,
        ]

    def mimeData(self, indexes):
        nodes = []
        seen = set()
        for index in indexes:
            if index.column() != 0 or not index.isValid():
                continue
            node = self._node(index)
            if id(node) not in seen and node is not self.root:
                seen.add(id(node))
                nodes.append(node)
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                mime = self.transfer_mime_data(
                    nodes, progress_callback=self._drag_progress_callback
                )
            finally:
                if app is not None:
                    app.restoreOverrideCursor()
        except Exception:
            # Keep same-process dragging available if the portable bundle
            # cannot be written; external windows will ignore the missing data.
            _LOGGER.exception("Could not serialize drag-and-drop nodes")
            mime = QtCore.QMimeData()
        ids = []
        for node in nodes:
            token = uuid.uuid4().hex
            _DRAG_NODES[token] = (self, node)
            ids.append(str(token))
        mime.setData(self.MIME_TYPE, ",".join(ids).encode("ascii"))
        if self._drag_progress_callback is not None:
            self._drag_progress_callback("Drag ready")
        return mime

    def supportedDropActions(self):
        return QtCore.Qt.DropAction.CopyAction | QtCore.Qt.DropAction.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if (self.read_only or action not in (QtCore.Qt.DropAction.CopyAction,
                                             QtCore.Qt.DropAction.MoveAction)
                or not (
                    data.hasFormat(self.MIME_TYPE)
                    or data.hasFormat(self.TRANSFER_DATA_MIME_TYPE)
                )):
            return False
        target = self.root if not parent.isValid() else self._node(parent)
        if target is None:
            return False
        tokens = []
        drag_entries = []
        try:
            if data.hasFormat(self.MIME_TYPE):
                tokens = [
                    item
                    for item in bytes(data.data(self.MIME_TYPE))
                    .decode("ascii")
                    .split(",")
                    if item
                ]
                drag_entries = [_DRAG_NODES[token] for token in tokens]
        except (KeyError, ValueError, UnicodeDecodeError):
            drag_entries = []

        registered_drag = bool(drag_entries)
        local_drag = bool(drag_entries)
        is_move = local_drag and action == QtCore.Qt.DropAction.MoveAction
        transfer_reader = None
        transfer_filename = None
        if is_move:
            source_models = [entry[0] for entry in drag_entries]
            source_nodes = [entry[1] for entry in drag_entries]
            source_filenames = [
                getattr(QtCore.QObject.parent(model), "filename", None)
                for model in source_models
            ]
        elif data.hasFormat(self.TRANSFER_DATA_MIME_TYPE):
            try:
                source_nodes, metadata, transfer_reader, transfer_filename = (
                    self._open_transfer_bundle(
                        bytes(data.data(self.TRANSFER_DATA_MIME_TYPE)),
                        bytes(data.data(self.TRANSFER_METADATA_MIME_TYPE)),
                        progress_callback=self._transfer_progress_callback,
                    )
                )
            except Exception:
                _LOGGER.exception("Could not read dropped TreeLab nodes")
                return False
            if not source_nodes:
                transfer_reader.close()
                Path(transfer_filename).unlink(missing_ok=True)
                return False
            source_models = [None] * len(source_nodes)
            source_filenames = [metadata.get("source_filename")] * len(source_nodes)
            local_drag = False
        elif local_drag:
            source_models = [entry[0] for entry in drag_entries]
            source_nodes = [entry[1] for entry in drag_entries]
            source_filenames = [
                getattr(QtCore.QObject.parent(model), "filename", None)
                for model in source_models
            ]
        else:
            return False

        if local_drag and any(node.parent() is None for node in source_nodes):
            return False
        if local_drag and any(
            source_model.read_only
            for source_model in source_models
            if action == QtCore.Qt.DropAction.MoveAction
        ):
            return False
        if local_drag and any(
            source_model is self and self._is_ancestor(source, target)
            for source_model, source in zip(source_models, source_nodes)
        ):
            return False

        # Only live in-process models can safely participate in a move and
        # update their source document. Copies use lazy nodes from the bundle.
        reset_models = []
        for source_model in source_models:
            if (
                is_move
                and source_model is not None
                and not any(source_model is item for item in reset_models)
            ):
                reset_models.append(source_model)
        if not any(self is item for item in reset_models):
            reset_models.append(self)
        for model in reset_models:
            model.beginResetModel()
        inserted = []
        try:
            parents = []
            if local_drag:
                for source in source_nodes:
                    old_parent = source.parent()
                    if old_parent is not None and not any(
                        old_parent is item for item in parents
                    ):
                        parents.append(old_parent)
            if not any(target is item for item in parents):
                parents.append(target)
            for node in parents:
                self._prepare_parent_for_edit(node)

            if is_move:
                for source_model, source in zip(source_models, source_nodes):
                    if source_model is not self:
                        self._materialise_for_transfer(source)

            for node_index, source in enumerate(source_nodes):
                node = (
                    source
                    if is_move or transfer_reader is not None
                    else source.copy(deep=True)
                )
                if is_move:
                    node.detach()
                self.rebase_link_targets(
                    node,
                    source_filenames[node_index],
                    getattr(QtCore.QObject.parent(self), "filename", None),
                )
                node.set_name(unique_sibling_name(target, node.name()))
                node.attach_to(
                    target,
                    position=row if row >= 0 else -1,
                    override_sibling_by_name=False,
                )
                inserted.append(node)
                if row >= 0:
                    row += 1
        except Exception:
            _LOGGER.exception("Could not insert dropped TreeLab nodes")
            for node in reversed(inserted):
                node.detach()
            if transfer_reader is not None:
                transfer_reader.close()
                Path(transfer_filename).unlink(missing_ok=True)
            return False
        finally:
            for model in reset_models:
                model._clear_visible_children_cache()
                model._automatic_fetch_nodes.clear()
            for model in reversed(reset_models):
                model.endResetModel()
        for source_model in source_models:
            if is_move and source_model is not None and source_model is not self:
                source_model._document_changed(full=True)
        self._document_changed(full=True)
        if transfer_reader is not None:
            document = QtCore.QObject.parent(self)
            if document is not None and hasattr(document, "retain_link_reader"):
                document.retain_link_reader(
                    transfer_reader, cleanup_filename=transfer_filename
                )
        if registered_drag:
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
            self._clear_visible_children_cache()
            self._automatic_fetch_nodes.clear()
            self.endResetModel()
        self._document_changed(full=True)

    def _document_changed(self, *, full: bool, node=None) -> None:
        document = QtCore.QObject.parent(self)
        if document is not None and hasattr(document, "mark_changed"):
            document.mark_changed(full=full, node=node)
