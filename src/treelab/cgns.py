"""Removed legacy module marker.

The former pure-Python treelab CGNS object model was intentionally removed.
"""

raise ModuleNotFoundError(
    "treelab cgns internals have migrated to noder. Use noder instead"
)
