"""Treelab's fixed native Qt palettes."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


_DARK_COLORS = {
    QtGui.QPalette.ColorRole.Window: "#202124",
    QtGui.QPalette.ColorRole.WindowText: "#f1f3f4",
    QtGui.QPalette.ColorRole.Base: "#17181a",
    QtGui.QPalette.ColorRole.AlternateBase: "#242528",
    QtGui.QPalette.ColorRole.Text: "#f1f3f4",
    QtGui.QPalette.ColorRole.Button: "#2b2d30",
    QtGui.QPalette.ColorRole.ButtonText: "#f1f3f4",
    QtGui.QPalette.ColorRole.BrightText: "#ffffff",
    QtGui.QPalette.ColorRole.Light: "#777c83",
    QtGui.QPalette.ColorRole.Midlight: "#5a6066",
    QtGui.QPalette.ColorRole.Dark: "#151619",
    QtGui.QPalette.ColorRole.Mid: "#4b5056",
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


_DARK_STYLESHEET = """
QMainWindow, QDialog, QDockWidget, QWidget {
    color: #f1f3f4;
}
QDialog, QMessageBox, QInputDialog, QFileDialog {
    background: #202124;
    color: #f1f3f4;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    background: transparent;
    color: #f1f3f4;
}
QDialogButtonBox QPushButton, QMessageBox QPushButton {
    background: #2b2d30;
    color: #f1f3f4;
    border: 1px solid #5a5f66;
    padding: 3px 10px;
}
QMenuBar, QMenu, QToolBar, QStatusBar {
    background: #202124;
    color: #f1f3f4;
}
QMenuBar::item, QMenu::item {
    background: transparent;
    color: #f1f3f4;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #3d6ea8;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #4b5056;
    margin: 4px 8px;
}
QTabWidget::pane, QTabBar::tab {
    background: #202124;
    color: #f1f3f4;
    border: 1px solid #4b5056;
}
QTabBar::tab {
    padding: 5px 8px;
    min-height: 20px;
}
QTabBar::tab:selected {
    background: #2b2d30;
    color: #ffffff;
}
QHeaderView, QHeaderView::section, QTableCornerButton::section {
    background: #2b2d30;
    color: #f1f3f4;
    border: 1px solid #4b5056;
    padding: 3px;
}
QAbstractScrollArea, QAbstractItemView {
    background: #17181a;
}
QTreeView, QTableView, QTableWidget, QListView, QPlainTextEdit, QTextEdit,
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #17181a;
    color: #f1f3f4;
    selection-background-color: #3d6ea8;
    selection-color: #ffffff;
}
QLineEdit, QComboBox {
    min-height: 20px;
}
QSpinBox, QDoubleSpinBox {
    min-height: 18px;
}
QTreeView, QTableView, QTableWidget {
    alternate-background-color: #242528;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QPushButton, QToolButton {
    border: 1px solid #5a5f66;
    border-radius: 2px;
}
QPushButton, QToolButton {
    background: #2b2d30;
    color: #f1f3f4;
}
QPushButton {
    min-height: 18px;
}
QToolBar QToolButton {
    padding: 1px 1px;
    margin: 0px;
    min-width: 25px;
}
QPushButton:hover, QToolButton:hover {
    background: #3a3d41;
}
QPushButton:pressed, QToolButton:pressed {
    background: #3d6ea8;
}
QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #85888c;
    background: #242528;
    border-color: #3a3d41;
}
QComboBox QAbstractItemView {
    background: #17181a;
    color: #f1f3f4;
    selection-background-color: #3d6ea8;
    selection-color: #ffffff;
}
QComboBox::drop-down {
    background: #2b2d30;
    border-left: 1px solid #5a5f66;
    width: 20px;
}
QComboBox::down-arrow {
    image: url(__TREELAB_DARK_COMBO_ARROW__);
    width: 10px;
    height: 6px;
}
QRadioButton, QCheckBox {
    color: #f1f3f4;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #17181a;
    border: 1px solid #3a3d41;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #5a5f66;
    min-height: 18px;
    min-width: 18px;
}
QScrollBar::handle:hover {
    background: #777c83;
}
QProgressBar {
    background: #17181a;
    color: #f1f3f4;
    border: 1px solid #5a5f66;
    text-align: center;
}
QProgressBar::chunk {
    background: #3d6ea8;
}
QToolTip {
    background: #2b2d30;
    color: #ffffff;
    border: 1px solid #777c83;
}
"""


def _dark_stylesheet() -> str:
    arrow_path = (
        Path(__file__).resolve().parent
        / "icons"
        / "OwnIcons"
        / "combo-down-arrow-dark.svg"
    )
    # Qt's stylesheet image loader accepts the native absolute path here;
    # using a file:// URL is not supported consistently by all Qt styles.
    arrow_url = f'"{arrow_path.as_posix()}"'
    return _DARK_STYLESHEET.replace("__TREELAB_DARK_COMBO_ARROW__", arrow_url)


def palette_is_dark(widget_or_app) -> bool:
    """Return whether a Qt application's current base color is dark."""
    palette = widget_or_app.palette()
    return palette.color(QtGui.QPalette.ColorRole.Base).value() < 128


def system_prefers_dark(app: QtWidgets.QApplication) -> bool:
    """Return the operating system's preferred light/dark color scheme."""
    color_scheme = getattr(app.styleHints(), "colorScheme", None)
    if callable(color_scheme):
        scheme = color_scheme()
        color_scheme_enum = getattr(QtCore.Qt, "ColorScheme", None)
        dark_scheme = getattr(color_scheme_enum, "Dark", None)
        light_scheme = getattr(color_scheme_enum, "Light", None)
        if scheme == dark_scheme:
            return True
        if scheme == light_scheme:
            return False
    return app.palette().color(QtGui.QPalette.ColorRole.Window).value() < 128


def make_theme_icon(dark: bool) -> QtGui.QIcon:
    """Create a small sun/moon icon for the light/dark mode switcher."""
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    if dark:
        color = QtGui.QColor("#f6c453")
        painter.setPen(QtGui.QPen(color, 2))
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QRectF(7, 7, 10, 10))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(12, 12)
            painter.rotate(angle)
            painter.drawLine(0, -9, 0, -6)
            painter.restore()
    else:
        color = QtGui.QColor("#3d6ea8")
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QRectF(5, 5, 14, 14))
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Clear)
        painter.drawEllipse(QtCore.QRectF(10, 3, 14, 14))
    painter.end()
    return QtGui.QIcon(pixmap)


def _apply_palette(
    app: QtWidgets.QApplication,
    colors: dict,
    disabled_text: str,
    stylesheet: str = "",
) -> None:
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
    app.setStyleSheet(stylesheet)


def apply_fixed_dark_palette(app: QtWidgets.QApplication) -> None:
    """Apply TreeLab's retained dark palette using the native Qt style."""
    _apply_palette(app, _DARK_COLORS, "#85888c", _dark_stylesheet())


def apply_fixed_light_palette(app: QtWidgets.QApplication) -> None:
    """Apply the readable native light palette used by the application."""
    _apply_palette(app, _LIGHT_COLORS, "#8a8a8a")


def apply_system_palette(app: QtWidgets.QApplication) -> None:
    """Apply TreeLab's fixed palette matching the OS color-scheme setting."""
    if system_prefers_dark(app):
        apply_fixed_dark_palette(app)
    else:
        apply_fixed_light_palette(app)
