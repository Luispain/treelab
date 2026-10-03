"""TreeLab command-line entry point."""

from __future__ import annotations

import argparse
import sys

from PySide6 import QtWidgets

from .style import apply_fixed_light_palette
from .window import MainWindow


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
        "files", nargs="*", metavar="FILE",
        help="CGNS/HDF5 files to open",
    )
    return parser


def launch(argv=None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    apply_fixed_light_palette(app)
    window = MainWindow(args.files, read_only=args.read_only)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
