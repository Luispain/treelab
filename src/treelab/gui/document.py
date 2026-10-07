"""Document lifecycle and persistence for the treelab GUI."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from PySide6 import QtCore

from noder.core import Node
import noder.core.io as noder_io

from .model import NoderTreeModel


class TreeDocument(QtCore.QObject):
    """One tab's noder tree, reader and dirty-state policy."""

    changed = QtCore.Signal()

    def __init__(
        self,
        filename: str | None = None,
        *,
        read_only: bool = False,
        safe_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.filename = str(filename) if filename else None
        self.read_only = read_only
        self.safe_mode = safe_mode
        self.reader = None
        self.root = None
        self.model = None
        self.dirty = False
        self.requires_full_write = False
        self._payload_dirty: dict[int, object] = {}
        if filename:
            self._load_file(str(filename))
        else:
            self.root = Node("CGNSTree", "CGNSTree_t")
            self.model = NoderTreeModel(self.root, read_only=read_only, parent=self)

    def _load_file(self, filename: str) -> None:
        self.reader = noder_io.LazyHdf5Reader(filename, safe_mode=self.safe_mode)
        self.root = self.reader.root()
        # CGNS/HDF5 has very few root-level children in normal files.  Load
        # only their metadata so the initial view contains bases, never zones.
        self.reader.ensure_children_loaded(self.root)
        try:
            self.model = NoderTreeModel(self.root, read_only=self.read_only, parent=self)
        except Exception:
            self.reader.close()
            self.reader = None
            raise

    @property
    def title(self) -> str:
        return Path(self.filename).name if self.filename else "Untitled"

    @property
    def has_read_warnings(self) -> bool:
        return bool(self.reader is not None and self.reader.has_warnings())

    def mark_changed(self, *, full: bool, node=None) -> None:
        self.dirty = True
        self.requires_full_write |= full
        if node is not None:
            self._payload_dirty[id(node)] = node
        self.changed.emit()

    def edit_node_data(self, node, value) -> None:
        self.edit_nodes_data([node], value)

    def edit_nodes_data(self, nodes, value) -> None:
        """Set one payload value on several nodes in one document update.

        Array values are copied for each node so subsequent table edits to one
        node cannot accidentally mutate the payload of another selected node.
        """
        if self.read_only:
            return
        unique_nodes = []
        seen = set()
        for node in nodes:
            if id(node) not in seen:
                seen.add(id(node))
                unique_nodes.append(node)
        nodes = unique_nodes
        for node in nodes:
            node_value = np.array(value, copy=True) if isinstance(value, np.ndarray) else value
            node.set_data(node_value)
            self._payload_dirty[id(node)] = node
        if not nodes:
            return
        self.dirty = True
        self.changed.emit()
        self.model.layoutChanged.emit()

    def save(self, filename: str | None = None) -> None:
        if self.read_only:
            raise PermissionError("This tree was opened read-only")
        if filename:
            self.filename = str(filename)
            self.requires_full_write = True
        if not self.filename:
            raise ValueError("No output filename was selected")

        if not self.requires_full_write and self._payload_dirty:
            for node in self._payload_dirty.values():
                self._save_targeted_node(node)
        else:
            self._write_full_file()
        self.dirty = False
        self.requires_full_write = False
        self._payload_dirty.clear()
        self.changed.emit()

    def save_node_only(self, node) -> None:
        """Persist one edited node without rewriting the complete tree."""
        if self.read_only:
            raise PermissionError("This tree was opened read-only")
        if not self.filename:
            raise ValueError("Save Node requires a file-backed document")
        if self.requires_full_write:
            raise RuntimeError(
                "Save Node is unavailable after structural edits; use Save for the complete tree"
            )
        self._save_targeted_node(node)
        self._payload_dirty.pop(id(node), None)
        if not self._payload_dirty:
            self.dirty = False
        self.changed.emit()

    def _save_targeted_node(self, node) -> None:
        """Write one node without materialising unrelated lazy payloads."""
        # Noder's focused HDF5 writer updates node attributes and rewrites
        # that node's payload dataset. Materialise only this payload first;
        # otherwise a type-only edit on a lazy node cannot be written while
        # its lazy reader is in external-write mode.
        if node.has_data() and not getattr(node, "data_is_loaded", lambda: True)():
            node.data()
        node.save_this_node_only(self.filename)

    def _write_full_file(self) -> None:
        model = self.model
        # Materialise before closing the reader; otherwise lazy nodes would
        # quite correctly reject payload access after their file is closed.
        self._materialise(self.root)
        self._detach_expansions(self.root)
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.root.write(self.filename)
        self._load_file(self.filename)
        if model is not None:
            self.model = model
            model.set_root(self.root)

    def _materialise(self, node) -> None:
        node.ensure_children_loaded()
        if node.has_data():
            node.data()
        for child in node.loaded_children():
            self._materialise(child)

    def _detach_expansions(self, node) -> None:
        for child in node.loaded_children():
            self._detach_expansions(child)
        node.clear_expansion()

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
            self.reader = None
