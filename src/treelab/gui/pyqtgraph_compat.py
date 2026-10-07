"""Small compatibility helpers for the supported PyQtGraph versions.

TreeLab uses the current PyQtGraph feature set on Python 3.10 and newer.  The
Python 3.8/3.9 dependency range intentionally selects the last compatible
PyQtGraph line, so optional performance/UI methods are guarded here instead of
spreading version checks throughout the plotter.
"""

from __future__ import annotations

import pyqtgraph as pg


def make_view_box():
    """Create a menu-less view box where the installed version supports it."""

    try:
        return pg.ViewBox(enableMenu=False)
    except TypeError:
        return pg.ViewBox()


def make_plot_data_item(*args, **kwargs):
    """Create a PlotDataItem, retrying without newer optional arguments."""

    try:
        return pg.PlotDataItem(*args, **kwargs)
    except TypeError:
        # ``antialias`` is optional for plotting correctness and was not
        # accepted by some older PyQtGraph constructors.
        kwargs.pop("antialias", None)
        return pg.PlotDataItem(*args, **kwargs)


def configure_downsampling(item) -> None:
    """Enable peak downsampling when the installed API exposes it."""

    try:
        item.setDownsampling(auto=True, method="peak")
    except (AttributeError, TypeError):
        try:
            item.setDownsampling(auto=True)
        except (AttributeError, TypeError):
            pass


def set_clip_to_view(item) -> None:
    """Use view clipping when available; it is only an optimization."""

    try:
        item.setClipToView(True)
    except (AttributeError, TypeError):
        pass


def set_menu_enabled(plot, enabled: bool) -> None:
    """Disable the context menu when supported by the plot widget."""

    try:
        plot.setMenuEnabled(enabled)
    except AttributeError:
        pass
