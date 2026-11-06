"""Treelab's fixed native Qt palettes."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from PySide6 import QtCore, QtGui, QtWidgets

MOLA_LIGHT = "#40e0d0"
MOLA_DARK = "#25766e"
MONOKAI_BACKGROUND = "#272822"
MONOKAI_BACKGROUND_ALT = "#2e2f29"
MONOKAI_INPUT = "#3c3d37"
MONOKAI_SURFACE = "#3e3d32"
MONOKAI_SELECTION = "#49483e"
MONOKAI_FOREGROUND = "#f8f8f2"
MONOKAI_MUTED = "#75715e"
MONOKAI_ACCENT = "#a6e22e"
MONOKAI_PINK = "#f92672"
MONOKAI_ORANGE = "#fd971f"
MONOKAI_YELLOW = "#e6db74"
MONOKAI_CYAN = "#66d9ef"
MONOKAI_PURPLE = "#ae81ff"
MONOKAI_BRANCH = "#a59f85"

_DARK_COLORS = {
    QtGui.QPalette.ColorRole.Window: MONOKAI_BACKGROUND,
    QtGui.QPalette.ColorRole.WindowText: MONOKAI_FOREGROUND,
    QtGui.QPalette.ColorRole.Base: MONOKAI_BACKGROUND,
    QtGui.QPalette.ColorRole.AlternateBase: MONOKAI_BACKGROUND_ALT,
    QtGui.QPalette.ColorRole.Text: MONOKAI_FOREGROUND,
    QtGui.QPalette.ColorRole.Button: MONOKAI_SURFACE,
    QtGui.QPalette.ColorRole.ButtonText: MONOKAI_FOREGROUND,
    QtGui.QPalette.ColorRole.BrightText: MONOKAI_PINK,
    QtGui.QPalette.ColorRole.Light: "#8a8673",
    QtGui.QPalette.ColorRole.Midlight: MONOKAI_SURFACE,
    QtGui.QPalette.ColorRole.Dark: "#1e1f1c",
    QtGui.QPalette.ColorRole.Mid: MONOKAI_SELECTION,
    QtGui.QPalette.ColorRole.Shadow: "#1a1b17",
    QtGui.QPalette.ColorRole.Highlight: MONOKAI_SELECTION,
    QtGui.QPalette.ColorRole.HighlightedText: MONOKAI_FOREGROUND,
    QtGui.QPalette.ColorRole.Link: MONOKAI_CYAN,
    QtGui.QPalette.ColorRole.LinkVisited: MONOKAI_PURPLE,
    QtGui.QPalette.ColorRole.PlaceholderText: "#a59f85",
    QtGui.QPalette.ColorRole.ToolTipBase: MONOKAI_SURFACE,
    QtGui.QPalette.ColorRole.ToolTipText: MONOKAI_FOREGROUND,
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
    color: #f8f8f2;
}
QDialog, QMessageBox, QInputDialog, QFileDialog {
    background: #272822;
    color: #f8f8f2;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    background: transparent;
    color: #f8f8f2;
}
QDialogButtonBox QPushButton, QMessageBox QPushButton {
    background: #3e3d32;
    color: #f8f8f2;
    border: 1px solid #75715e;
    padding: 3px 10px;
}
QMenuBar, QMenu, QToolBar, QStatusBar {
    background: #272822;
    color: #f8f8f2;
}
QMenuBar::item, QMenu::item {
    background: transparent;
    color: #f8f8f2;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #49483e;
    color: #f8f8f2;
}
QMenu::separator {
    height: 1px;
    background: #49483e;
    margin: 4px 8px;
}
QTabWidget::pane, QTabBar::tab {
    background: #272822;
    color: #f8f8f2;
    border: 1px solid #49483e;
}
QTabBar::tab {
    padding: 5px 8px;
    min-height: 20px;
}
QTabBar::tab:selected {
    background: #3e3d32;
    color: #f8f8f2;
}
QDockWidget::title {
    background: #3e3d32;
    color: #f8f8f2;
    padding: 4px;
}
QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    width: 16px;
    height: 16px;
}
QDockWidget::close-button {
    image: url(__TREELAB_DOCK_CLOSE_ICON__);
}
QDockWidget::float-button {
    image: url(__TREELAB_DOCK_FLOAT_ICON__);
}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {
    background: #49483e;
    border-color: #a6e22e;
}
QHeaderView, QHeaderView::section, QTableCornerButton::section {
    background: #3e3d32;
    color: #f8f8f2;
    border: 1px solid #49483e;
    padding: 3px;
}
QAbstractScrollArea, QAbstractItemView {
    background: #272822;
}
QTreeView, QTableView, QTableWidget, QListView, QPlainTextEdit, QTextEdit,
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #272822;
    color: #f8f8f2;
    selection-background-color: #49483e;
    selection-color: #f8f8f2;
}
QLineEdit, QComboBox {
    min-height: 20px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: __MONOKAI_INPUT__;
}
QSpinBox, QDoubleSpinBox {
    min-height: 18px;
}
QTreeView, QTableView, QTableWidget {
    alternate-background-color: #2e2f29;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QPushButton, QToolButton {
    border: 1px solid #75715e;
    border-radius: 2px;
}
QPushButton, QToolButton {
    background: #3e3d32;
    color: #f8f8f2;
}
QPushButton {
    min-height: 18px;
}
QToolBar QToolButton {
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 1px 1px;
    margin: 0px;
    min-width: 25px;
}
QToolBar::separator {
    background: #a59f85;
    width: 2px;
    margin: 5px 5px;
}
QPushButton:hover, QToolButton:hover {
    background: #49483e;
}
QPushButton:pressed, QToolButton:pressed {
    background: #a6e22e;
    color: #1e1f1c;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #a6e22e;
}
QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #a59f85;
    background: #2e2f29;
    border-color: #49483e;
}
QComboBox QAbstractItemView {
    background: #272822;
    color: #f8f8f2;
    selection-background-color: #49483e;
    selection-color: #f8f8f2;
}
QComboBox::drop-down {
    background: #3e3d32;
    border-left: 1px solid #75715e;
    width: 20px;
}
QComboBox::down-arrow {
    image: url(__TREELAB_DARK_COMBO_ARROW__);
    width: 10px;
    height: 6px;
}
QRadioButton, QCheckBox {
    color: #f8f8f2;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1e1f1c;
    border: 1px solid #49483e;
}
QScrollBar:vertical {
    width: 14px;
}
QScrollBar:horizontal {
    height: 14px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #a59f85;
    border: 1px solid #c5c09a;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: #f8f8f2;
}
QScrollBar::handle:pressed {
    background: #a6e22e;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QProgressBar {
    background: #272822;
    color: #f8f8f2;
    border: 1px solid #75715e;
    text-align: center;
}
QProgressBar::chunk {
    background: #a6e22e;
}
QToolTip {
    background: #3e3d32;
    color: #f8f8f2;
    border: 1px solid #a59f85;
}
"""


def _dark_stylesheet() -> str:
    arrow_path = (
        Path(__file__).resolve().parent
        / "icons"
        / "OwnIcons"
        / "combo-down-arrow-dark.svg"
    )
    close_icon_path = (
        Path(__file__).resolve().parent
        / "icons"
        / "OwnIcons"
        / "dock-close-dark.svg"
    )
    float_icon_path = (
        Path(__file__).resolve().parent
        / "icons"
        / "OwnIcons"
        / "dock-float-dark.svg"
    )
    # Qt's stylesheet image loader accepts the native absolute path here;
    # using a file:// URL is not supported consistently by all Qt styles.
    arrow_url = f'"{arrow_path.as_posix()}"'
    return (
        _DARK_STYLESHEET.replace("__TREELAB_DARK_COMBO_ARROW__", arrow_url)
        .replace("__MONOKAI_INPUT__", MONOKAI_INPUT)
        .replace("__TREELAB_DOCK_CLOSE_ICON__", f'"{close_icon_path.as_posix()}"')
        .replace("__TREELAB_DOCK_FLOAT_ICON__", f'"{float_icon_path.as_posix()}"')
    )


def palette_is_dark(widget_or_app) -> bool:
    """Return whether a Qt application's current base color is dark."""
    palette = widget_or_app.palette()
    return palette.color(QtGui.QPalette.ColorRole.Base).value() < 128


def system_prefers_dark(app: QtWidgets.QApplication) -> bool:
    """Return the operating system's preferred light/dark color scheme."""
    gtk_theme = None
    if sys.platform.startswith("linux"):
        preference = _gsettings_value("color-scheme")
        if preference in {"prefer-dark", "dark"}:
            return True
        if preference in {"prefer-light", "light"}:
            return False
        gtk_theme = _gsettings_value("gtk-theme")

    color_scheme = getattr(app.styleHints(), "colorScheme", None)
    if callable(color_scheme):
        scheme = color_scheme()
        color_scheme_enum = getattr(QtCore.Qt, "ColorScheme", None)
        dark_scheme = getattr(color_scheme_enum, "Dark", None)
        light_scheme = getattr(color_scheme_enum, "Light", None)
        if scheme == dark_scheme:
            return True
        if gtk_theme and "dark" in gtk_theme.casefold():
            return True
        if scheme == light_scheme:
            return False

    if gtk_theme:
        return "dark" in gtk_theme.casefold()
    return app.palette().color(QtGui.QPalette.ColorRole.Window).value() < 128


def _gsettings_value(key: str) -> str | None:
    """Read a GNOME interface preference when gsettings is available."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", key],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def make_theme_icon(dark: bool) -> QtGui.QIcon:
    """Create a small sun/moon icon for the light/dark mode switcher."""
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    if dark:
        color = QtGui.QColor(MONOKAI_YELLOW)
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
    """Apply TreeLab's Monokai-inspired dark palette on every platform."""
    _apply_palette(app, _DARK_COLORS, "#a59f85", _dark_stylesheet())


def apply_fixed_light_palette(app: QtWidgets.QApplication) -> None:
    """Apply the readable native light palette used by the application."""
    _apply_palette(app, _LIGHT_COLORS, "#8a8a8a")


def apply_system_palette(app: QtWidgets.QApplication) -> None:
    """Apply TreeLab's fixed palette matching the OS color-scheme setting."""
    if system_prefers_dark(app):
        apply_fixed_dark_palette(app)
    else:
        apply_fixed_light_palette(app)
