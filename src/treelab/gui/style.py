"""Treelab's fixed native Qt palettes."""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets


_DARK_COLORS = {
    QtGui.QPalette.ColorRole.Window: "#202124",
    QtGui.QPalette.ColorRole.WindowText: "#f1f3f4",
    QtGui.QPalette.ColorRole.Base: "#17181a",
    QtGui.QPalette.ColorRole.AlternateBase: "#242528",
    QtGui.QPalette.ColorRole.Text: "#f1f3f4",
    QtGui.QPalette.ColorRole.Button: "#2b2d30",
    QtGui.QPalette.ColorRole.ButtonText: "#f1f3f4",
    QtGui.QPalette.ColorRole.BrightText: "#ffffff",
    QtGui.QPalette.ColorRole.Light: "#3a3d41",
    QtGui.QPalette.ColorRole.Midlight: "#32353a",
    QtGui.QPalette.ColorRole.Dark: "#151619",
    QtGui.QPalette.ColorRole.Mid: "#27292d",
    QtGui.QPalette.ColorRole.Shadow: "#0c0d0f",
    QtGui.QPalette.ColorRole.Highlight: "#3d6ea8",
    QtGui.QPalette.ColorRole.HighlightedText: "#ffffff",
    QtGui.QPalette.ColorRole.Link: "#75bfff",
    QtGui.QPalette.ColorRole.LinkVisited: "#b58cff",
    QtGui.QPalette.ColorRole.PlaceholderText: "#8b8d92",
    QtGui.QPalette.ColorRole.ToolTipBase: "#2b2d30",
    QtGui.QPalette.ColorRole.ToolTipText: "#ffffff",
}

_LIGHT_COLORS = {
    QtGui.QPalette.ColorRole.Window: "#f2f2f2",
    QtGui.QPalette.ColorRole.WindowText: "#202124",
    QtGui.QPalette.ColorRole.Base: "#ffffff",
    QtGui.QPalette.ColorRole.AlternateBase: "#f5f5f5",
    QtGui.QPalette.ColorRole.Text: "#202124",
    QtGui.QPalette.ColorRole.Button: "#eeeeee",
    QtGui.QPalette.ColorRole.ButtonText: "#202124",
    QtGui.QPalette.ColorRole.BrightText: "#ffffff",
    QtGui.QPalette.ColorRole.Light: "#ffffff",
    QtGui.QPalette.ColorRole.Midlight: "#fafafa",
    QtGui.QPalette.ColorRole.Dark: "#c4c4c4",
    QtGui.QPalette.ColorRole.Mid: "#d6d6d6",
    QtGui.QPalette.ColorRole.Shadow: "#8a8a8a",
    QtGui.QPalette.ColorRole.Highlight: "#2d6cdf",
    QtGui.QPalette.ColorRole.HighlightedText: "#ffffff",
    QtGui.QPalette.ColorRole.Link: "#1b5eb7",
    QtGui.QPalette.ColorRole.LinkVisited: "#6a3da5",
    QtGui.QPalette.ColorRole.PlaceholderText: "#707070",
    QtGui.QPalette.ColorRole.ToolTipBase: "#ffffdc",
    QtGui.QPalette.ColorRole.ToolTipText: "#202124",
}


def _apply_palette(app: QtWidgets.QApplication, colors: dict, disabled_text: str) -> None:
    palette = app.palette()
    for group in (
        QtGui.QPalette.ColorGroup.Active,
        QtGui.QPalette.ColorGroup.Inactive,
    ):
        for role, color in colors.items():
            palette.setColor(group, role, QtGui.QColor(color))
    for role, color in colors.items():
        palette.setColor(QtGui.QPalette.ColorGroup.Disabled, role, QtGui.QColor(color))
    for role in (
        QtGui.QPalette.ColorRole.WindowText,
        QtGui.QPalette.ColorRole.Text,
        QtGui.QPalette.ColorRole.ButtonText,
        QtGui.QPalette.ColorRole.HighlightedText,
    ):
        palette.setColor(QtGui.QPalette.ColorGroup.Disabled, role, QtGui.QColor(disabled_text))
    app.setPalette(palette)


def apply_fixed_dark_palette(app: QtWidgets.QApplication) -> None:
    """Apply TreeLab's retained dark palette using the native Qt style."""
    _apply_palette(app, _DARK_COLORS, "#85888c")


def apply_fixed_light_palette(app: QtWidgets.QApplication) -> None:
    """Apply the readable native light palette used by the application."""
    _apply_palette(app, _LIGHT_COLORS, "#8a8a8a")
