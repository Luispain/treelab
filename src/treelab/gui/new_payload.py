"""Expression parsing and dialog support for creating node payloads."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from noder.payload_expression import PayloadExpressionError, evaluate_payload_expression


class NewPayloadDialog(QtWidgets.QDialog):
    """Large editor dialog for a new payload expression."""

    _last_expression = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New payload")
        self.resize(760, 460)

        layout = QtWidgets.QVBoxLayout(self)
        help_label = QtWidgets.QLabel(
            "Enter a NumPy expression. Existing payloads use "
            "{filename@path/without/root}; for example:\n"
            '"{file.cgns@Base/Zone/FlowSolution/CL}"[:, 2]\n'
            "Use {SiblingName} for a direct sibling of the selected node.\n"
            "Use None to remove the current payload.",
            self,
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.editor = QtWidgets.QPlainTextEdit(self)
        self.editor.setPlaceholderText("np.linspace(0, 1, 11)")
        self.editor.setTabChangesFocus(False)
        self.editor.setPlainText(type(self)._last_expression)
        self.editor.textChanged.connect(self._remember_expression)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor, 1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.set_payload_button = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        self.set_payload_button.setText("Set payload")
        self.set_payload_button.setToolTip("Set payload (Shift+Enter)")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.set_payload_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Shift+Enter"), self
        )
        self.set_payload_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.set_payload_shortcut.activated.connect(self.accept)

    def _remember_expression(self) -> None:
        type(self)._last_expression = self.editor.toPlainText()

    def eventFilter(self, watched, event):
        if watched is self.editor and event.type() == QtCore.QEvent.Type.KeyPress:
            modifiers = event.modifiers()
            shift_enter = (
                event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter)
                and modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
                and not modifiers & (
                    QtCore.Qt.KeyboardModifier.ControlModifier
                    | QtCore.Qt.KeyboardModifier.AltModifier
                    | QtCore.Qt.KeyboardModifier.MetaModifier
                )
            )
            if shift_enter:
                self.accept()
                return True
        return super().eventFilter(watched, event)

    def expression(self) -> str:
        self._remember_expression()
        return type(self)._last_expression
