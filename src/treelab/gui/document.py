"""Document lifecycle and persistence for the treelab GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from noder.core import Node
import noder.core.io as noder_io

from .model import NoderTreeModel


class TreeDocument(QtCore.QObject):
    """One tab's noder tree, reader and dirty-state policy."""

    changed = QtCore.Signal()

    def __init__(self, filename: str | None = None, *, read_only: bool = False, parent=None):
        super().__init__(parent)
        self.filename = str(filename) if filename else None
        self.read_only = read_only
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
        self.reader = noder_io.LazyHdf5Reader(filename)
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

    def mark_changed(self, *, full: bool, node=None) -> None:
        self.dirty = True
        self.requires_full_write |= full
        if node is not None:
            self._payload_dirty[id(node)] = node
        self.changed.emit()

    def edit_node_data(self, node, value) -> None:
        if self.read_only:
            return
        node.set_data(value)
        self.mark_changed(full=False, node=node)
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
                node.save_this_node_only(self.filename)
        else:
            self._write_full_file()
        self.dirty = False
        self.requires_full_write = False
        self._payload_dirty.clear()
        self.changed.emit()

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
