"""Expression parsing and dialog support for creating node payloads."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets


class PayloadExpressionError(ValueError):
    """Raised when a new-payload expression is invalid or unsafe."""


def _reference_parts(value: str) -> tuple[str, str] | None:
    """Parse both the compact and documented brace forms of a reference."""
    if value.startswith("{{") and value.endswith("}}"):
        inner = value[2:-2]
        if "}@{" in inner:
            filename, path = inner.split("}@{", 1)
            return filename, path
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1]
        if "@" in inner:
            filename, path = inner.split("@", 1)
            return filename, path
        if inner:
            # A one-part reference is resolved as a direct sibling of the
            # node being edited.  An empty filename keeps the evaluator's
            # resolver interface unchanged for full cross-tab references.
            return "", inner
    return None


@dataclass
class _ReferenceTransformer(ast.NodeTransformer):
    resolver: Callable[[str, str], np.ndarray]
    environment: dict[str, object]

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            parts = _reference_parts(node.value)
            if parts is not None:
                filename, path = parts
                try:
                    value = self.resolver(filename, path)
                except Exception as error:
                    raise PayloadExpressionError(str(error)) from error
                name = f"__payload_reference_{len(self.environment)}"
                self.environment[name] = value
                return ast.copy_location(
                    ast.Name(id=name, ctx=ast.Load()),
                    node,
                )
        return node


class _SafeExpressionValidator(ast.NodeVisitor):
    """Permit NumPy expressions, literals, operators, and array slicing only."""

    _allowed = {
        ast.Expression,
        ast.Constant,
        ast.Name,
        ast.Attribute,
        ast.Call,
        ast.keyword,
        ast.Subscript,
        ast.Index,
        ast.Slice,
        ast.Tuple,
        ast.List,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.IfExp,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.MatMult,
        ast.UAdd,
        ast.USub,
        ast.And,
        ast.Or,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    }

    def __init__(self, names: set[str]):
        self.names = names

    def generic_visit(self, node):
        if type(node) not in self._allowed:
            raise PayloadExpressionError(
                f"Expression element {type(node).__name__} is not allowed"
            )
        super().generic_visit(node)

    def visit_Name(self, node):
        if node.id not in self.names:
            raise PayloadExpressionError(f"Unknown name {node.id!r}")

    def visit_Attribute(self, node):
        if (
            not isinstance(node.value, ast.Name)
            or node.value.id != "np"
            or node.attr.startswith("_")
        ):
            raise PayloadExpressionError("Only public np.* functions are allowed")
        self.generic_visit(node)

    def visit_Call(self, node):
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "np"
            and not node.func.attr.startswith("_")
        ):
            raise PayloadExpressionError("Only calls to public np.* functions are allowed")
        self.generic_visit(node)


def evaluate_payload_expression(
    expression: str,
    resolver: Callable[[str, str], np.ndarray],
):
    """Evaluate a restricted NumPy expression after resolving payload references."""
    expression = expression.strip()
    if not expression:
        raise PayloadExpressionError("The new payload expression is empty")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise PayloadExpressionError(f"Invalid expression: {error}") from error

    environment: dict[str, object] = {"np": np}
    tree = _ReferenceTransformer(resolver, environment).visit(tree)
    ast.fix_missing_locations(tree)
    _SafeExpressionValidator(set(environment)).visit(tree)
    try:
        return eval(compile(tree, "<treelab new payload>", "eval"),
                    {"__builtins__": {}}, environment)
    except Exception as error:
        raise PayloadExpressionError(f"Could not evaluate expression: {error}") from error


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
