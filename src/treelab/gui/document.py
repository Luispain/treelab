"""Document lifecycle and persistence for the treelab GUI."""

from __future__ import annotations

from pathlib import Path
import threading
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
        self._linked_readers = []
        self._linked_reader_files = []
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
        # CGNS/HDF5 has few root-level children in normal files. Load their
        # metadata so all direct root nodes are visible without loading zones.
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

    def cgns_type_attribute(self, node) -> str | None:
        """Return a node's source CGNS ``type`` attribute when available."""
        readers = ([self.reader] if self.reader is not None else []) + self._linked_readers
        for reader in readers:
            try:
                return reader.cgns_type_attribute(node)
            except (RuntimeError, ValueError):
                continue
        return None

    def find_nodes_by_cgns_type(self, cgns_type: str) -> list:
        """Find source-file nodes by the CGNS ``type`` attribute value."""
        if self.reader is None:
            return []
        return self.reader.find_nodes_by_cgns_type(cgns_type)

    def mark_changed(self, *, full: bool, node=None) -> None:
        self.dirty = True
        self.requires_full_write |= full
        if node is not None:
            self._payload_dirty[id(node)] = node
        self.changed.emit()

    def edit_node_data(self, node, value, *, store_strings_as_S1: bool = False) -> None:
        self.edit_nodes_data([node], value, store_strings_as_S1=store_strings_as_S1)

    def edit_nodes_data(self, nodes, value, *, store_strings_as_S1: bool = False) -> None:
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
            node.set_data(node_value, store_strings_as_S1=store_strings_as_S1)
            self._payload_dirty[id(node)] = node
        if not nodes:
            return
        self.dirty = True
        self.changed.emit()
        self.model.layoutChanged.emit()

    def save(self, filename: str | None = None, *, progress_callback=None) -> None:
        if self.read_only:
            raise PermissionError("This tree was opened read-only")
        if filename:
            self.filename = str(filename)
            self.requires_full_write = True
        if not self.filename:
            raise ValueError("No output filename was selected")

        if not self.requires_full_write and self._payload_dirty:
            nodes = list(self._payload_dirty.values())
            for index, node in enumerate(nodes, start=1):
                if progress_callback is not None:
                    progress_callback(f"Saving changed payloads ({index}/{len(nodes)})…")
                self._save_targeted_node(node)
        else:
            self._write_full_file(progress_callback=progress_callback)
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

    def _write_full_file(self, *, progress_callback=None) -> None:
        model = self.model
        # Materialise before closing the reader; otherwise lazy nodes would
        # quite correctly reject payload access after their file is closed.
        self._materialise(self.root, progress_callback=progress_callback)
        self._detach_expansions(self.root, progress_callback=progress_callback)
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self._close_linked_readers()
        if progress_callback is not None:
            progress_callback("Writing the CGNS/HDF5 file…")
        self._write_root_in_background(progress_callback)
        if progress_callback is not None:
            progress_callback("Reopening the saved tree…")
        self._load_file(self.filename)
        if model is not None:
            self.model = model
            model.set_root(self.root)

    def _write_root_in_background(self, progress_callback=None) -> None:
        root = self.root
        filename = self.filename
        if progress_callback is None:
            root.write(filename)
            return

        errors = []

        def write_tree() -> None:
            try:
                root.write(filename)
            except BaseException as error:
                errors.append(error)

        writer = threading.Thread(
            target=write_tree,
            name="treelab-cgns-writer",
        )
        writer.start()
        try:
            while writer.is_alive():
                progress_callback("Writing the CGNS/HDF5 file…")
                writer.join(timeout=0.1)
        finally:
            writer.join()
        if errors:
            raise errors[0]

    def _materialise(self, node, *, progress_callback=None, state=None) -> None:
        if state is None:
            state = {"visited": 0, "metadata_batches": 0}
        state["visited"] += 1
        if progress_callback is not None and state["visited"] % 32 == 0:
            progress_callback(
                f"Preparing tree for save… {state['visited']:,} nodes inspected"
            )

        if node.has_link_target():
            # Children exposed by the lazy reader belong to the remote target,
            # not to the link node in this file. Discard loaded target rows so
            # a full write can preserve the link without copying that subtree.
            for child in list(node.loaded_children()):
                child.detach()
            node.clear_expansion()
            return

        while node.children_load_state() != "complete":
            previous_count = len(node.loaded_children())
            node.ensure_children_loaded(previous_count + self.model.PAGE_SIZE)
            state["metadata_batches"] += 1
            loaded_count = len(node.loaded_children())
            if progress_callback is not None and (
                state["metadata_batches"] % 16 == 0
                or loaded_count - previous_count >= self.model.PAGE_SIZE
            ):
                progress_callback(
                    f"Loading children of {node.name()}… "
                    f"{loaded_count:,} loaded"
                )
        if node.has_data():
            node.data()
        for child in node.loaded_children():
            self._materialise(
                child,
                progress_callback=progress_callback,
                state=state,
            )

    def _detach_expansions(self, node, *, progress_callback=None, state=None) -> None:
        if state is None:
            state = {"visited": 0}
        state["visited"] += 1
        if progress_callback is not None and state["visited"] % 32 == 0:
            progress_callback(
                f"Finalizing tree metadata… {state['visited']:,} nodes"
            )
        for child in node.loaded_children():
            self._detach_expansions(
                child,
                progress_callback=progress_callback,
                state=state,
            )
        node.clear_expansion()

    def close(self) -> None:
        if self.model is not None:
            self.model.set_fetching_enabled(False)
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self._close_linked_readers()

    def retain_link_reader(self, reader, *, cleanup_filename: str | None = None) -> None:
        """Keep an external lazy reader alive while imported nodes use it."""
        self._linked_readers.append(reader)
        if cleanup_filename and cleanup_filename not in self._linked_reader_files:
            self._linked_reader_files.append(cleanup_filename)

    def _close_linked_readers(self) -> None:
        readers, self._linked_readers = self._linked_readers, []
        for reader in readers:
            reader.close()
        filenames, self._linked_reader_files = self._linked_reader_files, []
        for filename in filenames:
            try:
                Path(filename).unlink(missing_ok=True)
            except OSError:
                pass
