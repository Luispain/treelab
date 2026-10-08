from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

from noder.core import Node

from treelab.gui.document import TreeDocument
from treelab.gui.plotter import (
    PlotSession,
    PlotWindow,
    expand_matching_axes,
    expanded_curve_color,
)
from treelab.gui.style import apply_fixed_dark_palette, apply_fixed_light_palette
from treelab.gui.window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication(["treelab-plot-tests"])


def _node(name: str, values) -> Node:
    node = Node(name, "DataArray_t")
    node.set_data(np.asarray(values, dtype=float))
    return node


def test_plot_session_keeps_cross_tab_sources_and_curves(qapp):
    first = TreeDocument(parent=qapp)
    second = TreeDocument(parent=qapp)
    x = _node("Iteration", range(4))
    y = _node("Lift", [0.1, 0.2, 0.3, 0.4])
    first.root.add_child(x)
    second.root.add_child(y)

    session = PlotSession()
    x_source = session.add_x(first, [x])[0]
    y_source = session.add_y(second, [y])[0]
    curve = session.add_curve(x=x_source, y=y_source)

    assert curve.x is x_source
    assert curve.y is y_source
    assert x_source.display_label(0).startswith("tab0@")
    assert y_source.display_label(1).startswith("tab1@")

    session.remove_document(first)
    assert session.x_sources == []
    assert session.y_sources == [y_source]
    assert session.curves == []


def test_expand_one_dimensional_x_against_two_dimensional_y():
    x = np.arange(15, dtype=float)
    y = np.arange(75, dtype=float).reshape(15, 5)

    pairs = expand_matching_axes(x, y)

    assert len(pairs) == 5
    assert all(pair_x.shape == (15,) for pair_x, _ in pairs)
    assert all(pair_y.shape == (15,) for _, pair_y in pairs)
    np.testing.assert_array_equal(pairs[0][0], x)
    np.testing.assert_array_equal(pairs[0][1], y[:, 0])
    np.testing.assert_array_equal(pairs[4][1], y[:, 4])


def test_expand_two_dimensional_arrays_slices_along_first_matching_axis():
    x = np.arange(75, dtype=float).reshape(15, 5)
    y = 100.0 + x

    pairs = expand_matching_axes(x, y)

    assert len(pairs) == 5
    for column, (pair_x, pair_y) in enumerate(pairs):
        np.testing.assert_array_equal(pair_x, x[:, column])
        np.testing.assert_array_equal(pair_y, y[:, column])


def test_expanded_curve_colors_are_distinct():
    base = "#1f77b4"
    colors = [expanded_curve_color(base, index, 5) for index in range(5)]

    assert len(set(colors)) == 5
    assert expanded_curve_color(base, 0, 1) == base


def test_plot_source_recovers_after_document_root_reload(qapp):
    document = TreeDocument(parent=qapp)
    old = _node("Signal", [1, 2, 3])
    document.root.add_child(old)
    session = PlotSession()
    source = session.add_y(document, [old])[0]

    replacement_root = Node("CGNSTree", "CGNSTree_t")
    replacement = _node("Signal", [4, 5, 6])
    replacement_root.add_child(replacement)
    document.root = replacement_root

    assert source.resolve() is replacement
    assert source.resolve().numpy().tolist() == [4.0, 5.0, 6.0]


def test_plot_window_draws_multiple_curves_and_secondary_axis(qapp):
    window = MainWindow()
    document = window.current_document()
    x = _node("Iteration", range(100))
    y1 = _node("Lift", np.sin(np.arange(100) / 10))
    y2 = _node("Drag", 10 * np.cos(np.arange(100) / 10))
    for node in (x, y1, y2):
        document.root.add_child(node)

    plot = PlotWindow(window, window)
    assert plot.parent() is None
    assert plot.windowType() == QtCore.Qt.WindowType.Window
    assert not plot.testAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose)
    plot.plot_selected(document, [x, y1, y2])
    qapp.processEvents()

    assert len(plot.session.curves) == 2
    assert len(plot._hover_entries) == 2
    assert plot.status_label.text().startswith("2 curve(s) drawn")

    plot.session.curves[0].line_style = "--"
    plot.draw()
    assert plot._hover_entries[0]["item"].opts["pen"].style() == QtCore.Qt.PenStyle.DashLine

    plot.session.curves[0].axis = 1
    plot.draw()
    qapp.processEvents()
    assert plot.y2_view.isVisible()
    assert plot.main_item.getAxis("right").isVisible()

    plot.shutdown()
    window.close()
    qapp.processEvents()


def test_plot_window_follows_dark_theme(qapp):
    apply_fixed_dark_palette(qapp)
    window = MainWindow()
    plot = PlotWindow(window, window)
    try:
        assert plot.dark_mode
        assert plot.main_plot.backgroundBrush().color().name() == "#17181a"
        apply_fixed_light_palette(qapp)
        plot.apply_theme()
        assert not plot.dark_mode
        assert plot.main_plot.backgroundBrush().color().name() == "#ffffff"
    finally:
        plot.shutdown()
        window.close()
        apply_fixed_light_palette(qapp)
        qapp.processEvents()


def test_plot_window_renders_1d_x_against_2d_y(qapp):
    window = MainWindow()
    document = window.current_document()
    x = _node("AngleOfAttack", np.arange(15))
    y = _node("CL", np.arange(75).reshape(15, 5))
    document.root.add_child(x)
    document.root.add_child(y)

    plot = PlotWindow(window, window)
    x_source = plot.session.add_x(document, [x])[0]
    y_source = plot.session.add_y(document, [y])[0]
    plot.session.add_curve(x=x_source, y=y_source)
    plot.draw()
    qapp.processEvents()

    assert len(plot._hover_entries) == 5
    assert plot.status_label.text().startswith("5 curve(s) drawn")
    assert all(entry["x"].shape == (15,) for entry in plot._hover_entries)
    assert all(entry["y"].shape == (15,) for entry in plot._hover_entries)
    assert len({entry["color"] for entry in plot._hover_entries}) == 5

    plot.shutdown()
    window.close()
    qapp.processEvents()


def test_registering_x_or_y_does_not_show_plot_window(qapp):
    window = MainWindow()
    document = window.current_document()
    node = _node("Signal", [1, 2, 3])
    document.root.add_child(node)
    window._current_nodes = lambda: [node]

    window.add_selected_to_plot_x()

    assert window.plot_window is not None
    assert not window.plot_window.isVisible()
    assert window.plot_window.session.x_sources[0].node is node
    assert window.statusBar().currentMessage() == (
        "data of node CGNSTree/Signal added to X"
    )

    window.draw_plot_curves()
    qapp.processEvents()
    assert window.plot_window.isVisible()
    window.close()
    qapp.processEvents()


def test_registering_x_then_y_binds_the_pending_curve(qapp):
    window = MainWindow()
    document = window.current_document()
    x = _node("Iteration", range(3))
    y = _node("Lift", [0.1, 0.2, 0.3])
    document.root.add_child(x)
    document.root.add_child(y)
    selected = [x]
    window._current_nodes = lambda: selected

    window.add_selected_to_plot_x()
    selected[:] = [y]
    window.add_selected_to_plot_y()

    plot = window.plot_window
    assert plot is not None
    assert plot.session.curves[0].x.node is x
    assert plot.session.curves[0].y.node is y
    assert plot.rows[0].y_combo.currentData().node is y

    window.close()
    qapp.processEvents()
