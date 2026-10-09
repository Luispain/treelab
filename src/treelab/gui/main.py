"""TreeLab command-line entry point."""

from __future__ import annotations

import argparse
import ctypes
import sys

from PySide6 import QtGui, QtWidgets

from .style import apply_system_palette
from .window import MOLA_ICON, MainWindow


def _set_windows_app_identity() -> None:
    """Give a ``python -m treelab`` process its own taskbar identity."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MOLA.TreeLab"
        )
    except (AttributeError, OSError):
        # The Qt window icon still works on Windows versions where this API is
        # unavailable, and this is intentionally a best-effort shell detail.
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="treelab",
        description="Navigate and edit CGNS/HDF5 trees using noder.",
    )
    parser.add_argument(
        "-r", "--read-only", action="store_true",
        help="open input trees read-only; editing and saving are disabled",
    )
    parser.add_argument(
        "-f", "--full", action="store_true",
        help="load all tree metadata and payloads before showing the editor",
    )
    parser.add_argument(
        "-s", "--safe-mode", action="store_true",
        help="tolerate malformed HDF5/CGNS nodes and add Corrupted_t markers",
    )
    parser.add_argument(
        "files", nargs="*", metavar="FILE",
        help="CGNS/HDF5 files to open",
    )
    return parser


def launch(argv=None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    _set_windows_app_identity()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    apply_system_palette(app)
    if MOLA_ICON.exists():
        app.setWindowIcon(QtGui.QIcon(str(MOLA_ICON)))
    window = MainWindow(
        args.files,
        read_only=args.read_only,
        full_load=args.full,
        safe_mode=args.safe_mode,
    )
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
