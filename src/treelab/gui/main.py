#    Copyright 2023 ONERA - contact luis.bernardos@onera.fr
#
#    This file is part of MOLA.
#
#    MOLA is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MOLA is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with MOLA.  If not, see <http://www.gnu.org/licenses/>.

#!/usr/bin/python3
# -*- coding : utf-8 -*-
import traceback
import sys, os, time
import numpy as np
import qtvscodestyle as qtvsc
from .. import cgns
from .. import __version__
from timeit import default_timer as toc

# import matplotlib
# matplotlib.use('Qt5Cairo')
import matplotlib.pyplot as plt
plt.ion()




window_main_title = f'TreeLab ({__version__})'
treelab_user_config = os.path.expanduser(os.path.join('~', '.treelab'))

def get_user_theme():
    user_theme = 'Native'
    try:
        with open(treelab_user_config, 'r') as f:
            lines = f.readlines()
            user_theme = lines[0]
    except:
        pass
    for theme in qtvsc.Theme:
        if theme.value['name'] == user_theme:
            return theme
    return user_theme
            
    
            


class SnappingCursor:
    """
    A cross hair cursor that snaps to the data point of a line, which is
    closest to the *x* position of the cursor.

    For simplicity, this assumes that *x* values of the data are sorted.
    """
    def __init__(self, ax, line):
        self.ax = ax
        self.horizontal_line = ax.axhline(color='silver', lw=0.8, ls='-')
        self.vertical_line = ax.axvline(color='silver', lw=0.8, ls='-')
        self.line = line
        self.x, self.y = self.line.get_data()
        self._last_index = None
        # text location in axes coords
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(20,20),
                            textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="w", color=self.get_line_color()),
                            arrowprops=dict(arrowstyle="->", color=self.get_line_color()),
                            color=self.get_line_color())
        self.annot.set_zorder(999)
        self.annot.set_visible(False)
        self.user_annotations = []

    def get_line_ylabel(self): return self.line.get_label()


    def get_line_color(self): return self.line.get_color()

    def set_cross_hair_visible(self, visible):
        need_redraw = self.horizontal_line.get_visible() != visible
        self.horizontal_line.set_visible(visible)
        self.vertical_line.set_visible(visible)
        self.annot.set_visible(visible)
        return need_redraw

    def on_mouse_move(self, event):
        if not event.inaxes:
            self._last_index = None
            need_redraw = self.set_cross_hair_visible(False)
            if need_redraw:
                self.ax.figure.canvas.draw()
        else:
            self.set_cross_hair_visible(True)
            x, y = event.xdata, event.ydata
            index = min(np.searchsorted(self.x, x), len(self.x) - 1)
            if index == self._last_index:
                return  # still on the same data point. Nothing to do.
            self._last_index = index
            x = self.x[index]
            y = self.y[index]

            self.annot.xy = [x,y]
            self.annot.set_text('%s=%g\n%s=%g'%(self.ax.xaxis.get_label().get_text(),x,
                                                self.line.get_label(),y))

            # update the line positions
            self.horizontal_line.set_ydata(y)
            self.vertical_line.set_xdata(x)
            self.ax.figure.canvas.draw()

    def on_double_click(self, event):
        if event.dblclick:
            user_annot = self.ax.annotate("", xy=(0,0), xytext=(20,20),
                                textcoords="offset points",
                                bbox=dict(boxstyle="round", fc="w", color=self.get_line_color()),
                                arrowprops=dict(arrowstyle="->", color=self.get_line_color()),
                                color=self.get_line_color())
            x = self.x[self._last_index]
            y = self.y[self._last_index]
            user_annot.xy = [x,y]
            user_annot.set_text('%s=%g\n%s=%g'%(self.ax.xaxis.get_label().get_text(),x,
                                                self.line.get_label(),y))
            user_annot.set_zorder(999)
            user_annot.set_visible(True)
            self.ax.plot(x,y,'x',color='red')
            self.user_annotations += [ user_annot ]
            self.ax.figure.canvas.draw()


from PySide6 import QtGui, QtWidgets, QtCore

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QToolBar,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QDockWidget,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QAbstractItemView,
    QAbstractButton,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QTreeView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QRadioButton,
    QMessageBox,
    QCheckBox,
)


GUIpath = os.path.dirname(os.path.realpath(__file__))
QTVSCpath = os.path.join(qtvsc.__file__.replace('__init__.py',''),'vscode','icons')


class MyTreeView(QTreeView):
    def __init__(self, parent=None ):
        super(MyTreeView, self).__init__(parent)
        self.model = QtGui.QStandardItemModel()
        self.setModel(self.model)
        self.setHeaderHidden(True)
        self.setStyleSheet(parent.treestyle)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)

    def dropEvent(self, event):
        # verify if selected nodes have any skeleton
        has_skeleton = False
        indices = self.selectionModel().selectedIndexes()
        for index in indices:
            item = self.model.itemFromIndex(index)
            if item.node_cgns.hasAnySkeletonAmongDescendants():
                has_skeleton = True
                break

        index = self.indexAt(event.pos())
        item = self.model.itemFromIndex(index)
        if has_skeleton:
            err_msg = 'Cannot move the selected nodes, since they '
            err_msg+= 'and/or their children contains skeleton '
            err_msg+= '(unloaded) data. Please load data before '
            err_msg+= 'moving the nodes (hint: use key touch F5).'
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Forbidden opeation")
            msg.setInformativeText(err_msg)
            msg.setWindowTitle("Forbidden")
            msg.exec_()
            event.ignore()
        
        elif not index.isValid() and not index.parent().isValid():
            # ignore if item is being dragged outside of main tree
            event.ignore()

        elif not hasattr(item, "node_cgns"):
            event.ignore()

        else:
            super(MyTreeView, self).dropEvent(event)
            
    def dragEnterEvent(self, event):
        index = self.indexAt(event.pos())
        item = self.model.itemFromIndex(index)
        if not hasattr(item, "node_cgns"):
            event.ignore()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        index = self.indexAt(event.pos())
        item = self.model.itemFromIndex(index)
        if not hasattr(item, "node_cgns"):
            event.ignore()
        else:
            super().dragMoveEvent(event)

class CustomStandardItemModel(QtGui.QStandardItemModel):
    def flags(self, index):
        flags = super().flags(index)
        if not index.parent().isValid():
            # Disable dragging for items at root level
            flags &= ~QtGui.Qt.ItemIsDragEnabled
        return flags

class MainWindow(QMainWindow):
    def __init__(self, filenames=[], only_skeleton=False, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle(window_main_title)
        self.setWindowIcon(QtGui.QIcon(os.path.join(GUIpath,"icons","fugue-icons-3.5.6","tree")))
        self.fontPointSize = 12.
        self.only_skeleton = only_skeleton
        self.max_nb_table_items = 2e4

        self.dock = QDockWidget('Please select a node...')
        self.dock.setFeatures(QDockWidget.DockWidgetFloatable |
                              QDockWidget.DockWidgetMovable)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dock)
        self.dock.VLayout = QWidget(self)
        self.dock.setWidget(self.dock.VLayout)
        self.dock.VLayout.setLayout(QVBoxLayout())

        self.dock.node_toolbar = QToolBar("Node toolbar")
        self.dock.VLayout.layout().addWidget(self.dock.node_toolbar)


        self.dock.node_toolbar.button_update_node_data = QtGui.QAction(None,
             "upload node(s) data from file to memory (F5)", self)
        self.dock.node_toolbar.button_update_node_data.setStatusTip(
            "upload node(s) and their children data from file (F5) of type DataArray_t from file (F5)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_update_node_data)
        key_update_node_data = QtGui.QShortcut(QtGui.QKeySequence('F5'), self)
        key_update_node_data.activated.connect(self.update_node_data)
        self.dock.node_toolbar.button_update_node_data.triggered.connect(self.update_node_data)

        self.dock.node_toolbar.button_unload_node_data_recursively = QtGui.QAction(None,
            "free-up memory from data of node(s) (F6)", self)
        self.dock.node_toolbar.button_unload_node_data_recursively.setStatusTip(
            "free-up memory from data of selected node(s) and their children of type DataArray_t (F6)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_unload_node_data_recursively)
        key_unload_node_data = QtGui.QShortcut(QtGui.QKeySequence('F6'), self)
        key_unload_node_data.activated.connect(self.unload_node_data_recursively)
        self.dock.node_toolbar.button_unload_node_data_recursively.triggered.connect(self.unload_node_data_recursively)

        self.dock.node_toolbar.button_replace_link = QtGui.QAction(None, "read link", self)
        self.dock.node_toolbar.button_replace_link.setStatusTip("Read link of selected node(s) from file (must be Link_t)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_replace_link)
        self.dock.node_toolbar.button_replace_link.triggered.connect(self.replace_link)

        self.dock.node_toolbar.button_modify_node_data = QtGui.QAction(None,
            "write selected node(s) in file (F8)", self)
        self.dock.node_toolbar.button_modify_node_data.setStatusTip("write selected node(s) in file (F8)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_modify_node_data)
        key_modify_node_data = QtGui.QShortcut(QtGui.QKeySequence('F8'), self)
        key_modify_node_data.activated.connect(self.modify_node_data)
        self.dock.node_toolbar.button_modify_node_data.triggered.connect(self.modify_node_data)

        self.dock.node_toolbar.addSeparator()

        self.dock.node_toolbar.button_add_plot_x_container = QtGui.QAction(
            QtGui.QIcon(GUIpath+"/icons/OwnIcons/x-16.png"),
            "add node(s) data to X plotter container (X)", self)
        self.dock.node_toolbar.button_add_plot_x_container.setStatusTip(
            "add node(s) data to X plotter container (key X)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_add_plot_x_container)
        key_add_plot_x_container = QtGui.QShortcut(QtGui.QKeySequence('X'), self)
        key_add_plot_x_container.activated.connect(self.add_selected_nodes_to_plot_x_container)
        self.dock.node_toolbar.button_add_plot_x_container.triggered.connect(self.add_selected_nodes_to_plot_x_container)

        self.dock.node_toolbar.button_add_plot_y_container = QtGui.QAction(
            QtGui.QIcon(GUIpath+"/icons/OwnIcons/y-16.png"),
            "add node(s) data to Y plotter container (Y)", self)
        self.dock.node_toolbar.button_add_plot_y_container.setStatusTip(
            "add node(s) data to Y plotter container (key Y)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_add_plot_y_container)
        key_add_plot_y_container = QtGui.QShortcut(QtGui.QKeySequence('Y'), self)
        key_add_plot_y_container.activated.connect(self.add_selected_nodes_to_plot_y_container)
        self.dock.node_toolbar.button_add_plot_y_container.triggered.connect(self.add_selected_nodes_to_plot_y_container)

        # own: QtGui.QIcon(GUIpath+"/icons/OwnIcons/add-curve-16.png")
        self.dock.node_toolbar.button_add_curve = QtGui.QAction(None,
            "add curve to plotter", self)
        self.dock.node_toolbar.button_add_curve.setStatusTip("add curve to plotter")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_add_curve)
        self.dock.node_toolbar.button_add_curve.triggered.connect(self.add_curve)

        self.dock.node_toolbar.button_draw_curves = QtGui.QAction(None,
            "draw all curves (P)", self)
        self.dock.node_toolbar.button_draw_curves.setStatusTip("draw all curves (key P)")
        self.dock.node_toolbar.addAction(self.dock.node_toolbar.button_draw_curves)
        key_add_draw_curves = QtGui.QShortcut(QtGui.QKeySequence('P'), self)
        key_add_draw_curves.activated.connect(self.draw_curves)
        self.dock.node_toolbar.button_draw_curves.triggered.connect(self.draw_curves)

        self.dock.node_toolbar.setVisible(False)


        self.dock.plotter = QWidget(self)
        self.dock.plotter.setLayout(QVBoxLayout())
        self.dock.VLayout.layout().addWidget(self.dock.plotter)
        self.dock.plotter.setVisible(False)

        self.dock.pathLabel = QWidget(self)
        self.dock.pathLabel.setLayout(QHBoxLayout())
        self.dock.pathLabel.layout().addWidget(QLabel('Path:'))
        self.dock.pathLabel.label = QLineEdit("please select a node...")
        self.dock.pathLabel.label.setReadOnly(True)
        self.dock.pathLabel.layout().addWidget(self.dock.pathLabel.label)
        self.dock.VLayout.layout().addWidget(self.dock.pathLabel)
        self.dock.pathLabel.setVisible(False)


        self.dock.typeEditor = QWidget(self)
        self.dock.typeEditor.setLayout(QHBoxLayout())
        self.dock.typeEditor.layout().addWidget(QLabel('CGNS Type:'))
        self.dock.typeEditor.lineEditor = QLineEdit("please select a node...")
        self.dock.typeEditor.lineEditor.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.dock.typeEditor.lineEditor.editingFinished.connect(self.updateTypeOfNodeCGNS)
        self.dock.typeEditor.layout().addWidget(self.dock.typeEditor.lineEditor)
        self.dock.VLayout.layout().addWidget(self.dock.typeEditor)
        self.dock.typeEditor.setVisible(False)



        self.dock.dataDimensionsLabel = QLabel('Class: toto | Dims: tata')
        self.dock.VLayout.layout().addWidget(self.dock.dataDimensionsLabel)
        self.dock.dataDimensionsLabel.setVisible(False)


        self.dock.dataSlicer = QWidget(self)
        self.dock.dataSlicer.setLayout(QHBoxLayout())
        self.dock.dataSlicer.ijkSelector = QComboBox()
        self.dock.dataSlicer.ijkSelector.insertItems(0,['k','j','i'])
        self.dock.dataSlicer.ijkSelector.currentTextChanged.connect(self.updateTable)
        self.dock.dataSlicer.layout().addWidget(QLabel('Showing data at index:'))
        self.dock.dataSlicer.layout().addWidget(self.dock.dataSlicer.ijkSelector)
        self.dock.dataSlicer.sliceSelector = QSpinBox()
        self.dock.dataSlicer.sliceSelector.setValue(0)
        self.dock.dataSlicer.sliceSelector.valueChanged.connect(self.updateTable)
        self.dock.dataSlicer.layout().addWidget(self.dock.dataSlicer.sliceSelector)
        self.dock.VLayout.layout().addWidget(self.dock.dataSlicer)
        self.dock.dataSlicer.setVisible(False)

        self.createTable()
        self.dock.VLayout.layout().addWidget(self.table)

        self.dock.tableShow = QWidget(self)
        self.dock.tableShow.setLayout(QHBoxLayout())
        self.dock.tableShow.layout().addWidget(QLabel('Always show data in table'))
        self.dock.tableShow.check_box = QCheckBox()
        self.dock.tableShow.check_box.setChecked(False)
        self.dock.tableShow.check_box.stateChanged.connect(self.updateTable)
        self.dock.tableShow.layout().addWidget(self.dock.tableShow.check_box)
        self.dock.VLayout.layout().addWidget(self.dock.tableShow)
        self.dock.tableShow.setVisible(False)


        # Create tab widget
        self.tab_widget = QTabWidget()
        self.TabBar = QtWidgets.QTabBar()
        self.tab_widget.setTabBar(self.TabBar)
        self.TabBar.setTabsClosable(True)
        self.TabBar.setMovable(True)
        self.TabBar.tabCloseRequested.connect(self.closeTab)
        self.TabBar.tabBarDoubleClicked.connect(self.tabDoubleClicked)
        self.TabBar.currentChanged.connect(self.handle_tab_changed)

        # TODO uncomment this when able to share node_cgns between tabs (or windows)
        # hint: https://gist.github.com/eyllanesc/42bcda52a14244445153153a33e7c0dd
        # self.TabBar.setChangeCurrentOnDrag(True)
        # self.TabBar.setAcceptDrops(True)
        # self.setAcceptDrops(True)
        
        self.setCentralWidget(self.tab_widget)
     
        self.toolbar = QToolBar("Main toolbar")
        self.addToolBar(QtCore.Qt.LeftToolBarArea, self.toolbar)

        # icon saver: (python -m qtvscodestyle.examples.icon_browser)
        # icon = qtvsc.theme_icon(qtvsc.FaRegular.MINUS_SQUARE, "icon.foreground")
        # button_toto = QtGui.QAction(icon ,"toto", self)
        # self.toolbar.addAction(button_toto)
        # pixmap = icon.pixmap(QtCore.QSize(64, 64))
        # pixmap.save('minus_square.png')

        # icon = self.getColoredIcon(GUIpath+'/icons/icons8/icons8-coordinate-system-16.png',
        #                                   self.colors['focusBorder'])
        # button_toto = QtGui.QAction(icon ,"toto", self)
        # self.toolbar.addAction(button_toto)


        self.toolbar.button_new = QtGui.QAction(None, "new tab", self)
        self.toolbar.button_new.setStatusTip("Open a new tab with empty tree")
        self.toolbar.button_new.triggered.connect(self.newTab)
        key_newTab = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+T'), self)
        key_newTab.activated.connect(self.newTab)
        self.toolbar.addAction(self.toolbar.button_new)
        key_closeTab = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+W'), self)
        key_closeTab.activated.connect(self.closeTab)


        self.toolbar.button_open = QtGui.QAction(None,"open (Ctrl+O)", self)
        self.toolbar.button_open.setStatusTip("Open a tree from a file")
        self.toolbar.button_open.triggered.connect(self.openTree)
        key_openTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+O'), self)
        key_openTree.activated.connect(self.openTree)
        self.toolbar.addAction(self.toolbar.button_open)

        self.toolbar.button_reopen = QtGui.QAction(None,
            "Open again (Shift + F5)", self)
        self.toolbar.button_reopen.setStatusTip("Open again the current tree from file (Shift + F5)")
        self.toolbar.button_reopen.triggered.connect(self.reopenTree)
        key_reopen = QtGui.QShortcut(QtGui.QKeySequence('Shift+F5'), self)
        key_reopen.activated.connect(self.reopenTree)
        self.toolbar.addAction(self.toolbar.button_reopen)

        self.toolbar.button_save = QtGui.QAction(None,
                                    "save (Ctrl+S)", self)
        self.toolbar.button_save.setStatusTip("Save the current tree")
        self.toolbar.button_save.triggered.connect(self.saveTree)
        key_saveTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+S'), self)
        key_saveTree.activated.connect(self.saveTree)
        self.toolbar.addAction(self.toolbar.button_save)

        self.toolbar.button_saveAs = QtGui.QAction(None,
                                      "save as (Ctrl+Shift+S)", self)
        self.toolbar.button_saveAs.setStatusTip("Save the current tree as new file")
        self.toolbar.button_saveAs.triggered.connect(self.saveTreeAs)
        key_saveTreeAs = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Shift+S'), self)
        key_saveTreeAs.activated.connect(self.saveTreeAs)
        self.toolbar.addAction(self.toolbar.button_saveAs)

        self.toolbar.addSeparator()

        # TODO implement this more efficiently
        # button_zoomIn = QtGui.QAction(QtGui.QIcon(GUIpath+"/icons/fugue-icons-3.5.6/magnifier-zoom-in.png") ,"zoom in (+)", self)
        # button_zoomIn.setStatusTip("Zoom in the tree (+)")
        # button_zoomIn.triggered.connect(self.zoomInTree)
        # key_zoomInTree = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Plus), self)
        # key_zoomInTree.activated.connect(self.zoomInTree)
        # self.toolbar.addAction(button_zoomIn)

        # button_zoomOut = QtGui.QAction(QtGui.QIcon(GUIpath+"/icons/fugue-icons-3.5.6/magnifier-zoom-out.png") ,"zoom out (-)", self)
        # button_zoomOut.setStatusTip("Zoom out the tree (-)")
        # button_zoomOut.triggered.connect(self.zoomOutTree)
        # key_zoomOutTree = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Minus), self)
        # key_zoomOutTree.activated.connect(self.zoomOutTree)
        # self.toolbar.addAction(button_zoomOut)

        self.toolbar.button_expandAll = QtGui.QAction(None,
            "expand all nodes", self)
        self.toolbar.button_expandAll.setStatusTip("Expand all the nodes of the tree")
        self.toolbar.button_expandAll.triggered.connect(self.expandAll)
        self.toolbar.addAction(self.toolbar.button_expandAll)

        # button_expandZones = QtGui.QAction(QtGui.QIcon(GUIpath+"/icons/icons8/icons8-expand3-48") ,"expand to depth 3", self)
        # button_expandZones.setStatusTip("Expand up to three levels of the tree")
        # button_expandZones.triggered.connect(self.expandToZones)
        # self.toolbar.addAction(button_expandZones)

        self.toolbar.button_collapseAll = QtGui.QAction(None,
            "collapse all nodes", self)
        self.toolbar.button_collapseAll.setStatusTip("Collapse all the nodes of the tree")
        self.toolbar.button_collapseAll.triggered.connect(self.collapseAll)
        self.toolbar.addAction(self.toolbar.button_collapseAll)

        self.toolbar.addSeparator()

        self.toolbar.button_findNode = QtGui.QAction(None,
            "find node (Ctrl+F)", self)
        self.toolbar.button_findNode.setStatusTip("Find node using criteria based on Name, Value and Type (Ctrl+F)")
        self.toolbar.button_findNode.triggered.connect(self.findNodesTree)
        self.toolbar.addAction(self.toolbar.button_findNode)
        self.NameToBeFound = None
        self.ValueToBeFound = None
        self.TypeToBeFound = None
        self.DepthToBeFound = 100
        self.FoundNodes = []
        self.CurrentFoundNodeIndex = -1

        self.toolbar.button_findNextNode = QtGui.QAction(None,
            "find next node (F3)", self)
        self.toolbar.button_findNextNode.setStatusTip("Find next node (F3)")
        self.toolbar.button_findNextNode.triggered.connect(self.findNextNodeTree)
        key_findNextNodeTree = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F3), self)
        key_findNextNodeTree.activated.connect(self.findNextNodeTree)
        self.toolbar.addAction(self.toolbar.button_findNextNode)

        self.toolbar.addSeparator()

        # green icon : QtGui.QIcon(GUIpath+"/icons/fugue-icons-3.5.6/plus") 
        self.toolbar.button_newNodeTree = QtGui.QAction(None,
            "New node (Ctrl+N)", self)
        self.toolbar.button_newNodeTree.setStatusTip("Create a new node attached to the selected node in tree (Ctrl+N)")
        self.toolbar.button_newNodeTree.triggered.connect(self.newNodeTree)
        self.toolbar.addAction(self.toolbar.button_newNodeTree)

        # red cross : QtGui.QIcon(GUIpath+"/icons/fugue-icons-3.5.6/cross") 
        self.toolbar.button_deleteNodeTree = QtGui.QAction(None,
            "remove selected nodes (Supr)", self)
        self.toolbar.button_deleteNodeTree.setStatusTip("remove selected node (Supr)")
        self.toolbar.button_deleteNodeTree.triggered.connect(self.deleteNodeTree)
        self.toolbar.addAction(self.toolbar.button_deleteNodeTree)

        # blue arrows : QtGui.QIcon(GUIpath+"/icons/fugue-icons-3.5.6/arrow-switch.png")
        self.toolbar.button_swap = QtGui.QAction(None,
            "swap selected nodes", self)
        self.toolbar.button_swap.setStatusTip("After choosing two nodes, swap their position in the tree")
        self.toolbar.button_swap.triggered.connect(self.swapNodes)
        self.toolbar.addAction(self.toolbar.button_swap)

        self.toolbar.button_copyNodeTree = QtGui.QAction(None,
            "copy selected nodes (Ctrl+C)", self)
        self.toolbar.button_copyNodeTree.setStatusTip("copy selected nodes (Ctrl+C)")
        self.toolbar.button_copyNodeTree.triggered.connect(self.copyNodeTree)
        self.toolbar.addAction(self.toolbar.button_copyNodeTree)
        self.copiedNodes = []
        
        self.toolbar.button_cutNodeTree = QtGui.QAction(None,
            "cut selected nodes (Ctrl+X)", self)
        self.toolbar.button_cutNodeTree.setStatusTip("cut selected nodes (Ctrl+X)")
        self.toolbar.button_cutNodeTree.triggered.connect(self.cutNodeTree)
        self.toolbar.addAction(self.toolbar.button_cutNodeTree)

        self.toolbar.button_pasteNodeTree = QtGui.QAction(None,
            "paste nodes (Ctrl+V)", self)
        self.toolbar.button_pasteNodeTree.setStatusTip("Paste previously copied nodes at currently selected parent nodes (Ctrl+V)")
        self.toolbar.button_pasteNodeTree.triggered.connect(self.pasteNodeTree)
        self.toolbar.addAction(self.toolbar.button_pasteNodeTree)

        self.toolbar.addSeparator()
        self.toolbar.button_theme = QtGui.QAction(None,
            "change interface color theme", self)
        self.toolbar.button_theme.setStatusTip("change interface color theme (will persist on next open of treelab)")
        self.toolbar.button_theme.triggered.connect(self.changeTheme)
        self.toolbar.addAction(self.toolbar.button_theme)


        self.plot_x_container = []
        self.plot_y_container = []
        self.curves_container = []

        self.setTheme()
        self.registerTreestyle()
        self.setStatusBar(QStatusBar(self))
        self.center_window()
        for fn in filenames: self.newTab(fn)

    def handle_tab_changed(self):
        self.selectionInfo()

    def getColoredIcon(self, filepath, color=''):
        img = QtGui.QPixmap(filepath)
        qp = QtGui.QPainter(img)
        qp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        if not color: color = self.colors['icon.foreground']
        qp.fillRect( img.rect(), color )
        qp.end()
        return QtGui.QIcon(img)

    def getColoredQtvscIcon(self, qtvsc_id, color=''):
        # Create a pixmap to draw the colored icon
        qtvsc_icon = qtvsc.theme_icon(qtvsc_id, 'icon.foreground')
        img = qtvsc_icon.pixmap(QtCore.QSize(64, 64))  # Adjust size as needed
        qp = QtGui.QPainter(img)
        qp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        if not color: color = self.colors['icon.foreground']
        qp.fillRect( img.rect(), color )
        qp.end()
        return QtGui.QIcon(img)



    def tabDoubleClicked(self, index):
        dlg = TabEditionDialog(index, self.tab_widget)
        if dlg.exec():
            self.tab_widget.setTabText(index, dlg.NameWidget.text()) 

    def newTab(self, filename=None):
        tab = QWidget()

        # load tree from file or create empty
        if filename:
            onlyFileName = filename.split(os.sep)[-1]
            QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            print(f'building CGNS structure of {filename}...')
            tic = toc()
            tab.t = cgns.load(filename, only_skeleton=self.only_skeleton)
            tab.t.file = filename
            QApplication.restoreOverrideCursor()
            print('done (%g s)'%(toc()-tic))
        else:
            onlyFileName = 'untitled'
            tab.t = cgns.Tree()
            tab.t.file = None

        self.tab_widget.addTab(tab, onlyFileName)
        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)


        tab.tree = MyTreeView(self)
        tab.tree.selectionModel().selectionChanged.connect(self.selectionInfo)
        tab.tree.model.itemChanged.connect(self.updateNameOfNodeCGNS)

        print('building Qt model...')
        tic = toc()
        self.updateModel(tab)
        print('done (%g s)'%(toc()-tic))

        # add tree view model to tab layout
        tab_layout.addWidget(tab.tree)
        tab.tree.setFocus()
        new_index = self.tab_widget.count()-1
        self.tab_widget.setCurrentIndex(new_index)
        self.tab_widget.currentChanged.connect(self.updateTable)

        # add tree-specific keyboard controls
        key_newNodeTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+N'), tab.tree)
        key_newNodeTree.setContext(QtCore.Qt.WidgetShortcut)
        key_newNodeTree.activated.connect(self.newNodeTree)

        key_deleteNodeTree = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), tab.tree)
        key_deleteNodeTree.setContext(QtCore.Qt.WidgetShortcut)
        key_deleteNodeTree.activated.connect(self.deleteNodeTree)

        key_copyNodeTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+C'), tab.tree)
        key_copyNodeTree.setContext(QtCore.Qt.WidgetShortcut)
        key_copyNodeTree.activated.connect(self.copyNodeTree)

        key_cutNodeTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+X'), tab.tree)
        key_cutNodeTree.setContext(QtCore.Qt.WidgetShortcut)
        key_cutNodeTree.activated.connect(self.cutNodeTree)

        key_pasteNodeTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+V'), tab.tree)
        key_pasteNodeTree.setContext(QtCore.Qt.WidgetShortcut)
        key_pasteNodeTree.activated.connect(self.pasteNodeTree)

        key_findNodesTree = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+F'), tab.tree)
        key_findNodesTree.setContext(QtCore.Qt.WidgetShortcut)
        key_findNodesTree.activated.connect(self.findNodesTree)


    def closeTab(self, index=None):
        # Get the widget associated with the tab
        if index is None: index = self.getTabIndex()
        tab = self.tab_widget.widget(index)

        # removes data associated to tab
        del tab.t
        del tab.tree

        # Remove the tab from the tab widget
        self.tab_widget.removeTab(index)



    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.modifiers() & QtCore.Qt.ControlModifier:
            if event.key() == QtCore.Qt.Key_PageUp:
                current_index = self.tab_widget.currentIndex()
                new_index = (current_index - 1) % self.tab_widget.count()
                self.tab_widget.setCurrentIndex(new_index)
            elif event.key() == QtCore.Qt.Key_PageDown:
                current_index = self.tab_widget.currentIndex()
                new_index = (current_index + 1) % self.tab_widget.count()
                self.tab_widget.setCurrentIndex(new_index)


    def center_window(self):
        # Get the primary screen's geometry
        screen_geometry = QtGui.QGuiApplication.primaryScreen().availableGeometry()

        # Calculate the center point of the screen
        center_point = screen_geometry.center()

        # Calculate the top-left point of the window to center it
        window_position = self.frameGeometry()
        window_position.moveCenter(center_point)

        # Set the window's top-left position to the calculated center
        self.move(window_position.topLeft())

    def changeTheme(self):

        try: current_theme = self.theme.value['name']
        except: current_theme = 'Native'

        def previewTheme():
            previous_theme = get_user_theme()
            new_theme = dlg.combo_box.currentText()
            self.saveTheme(new_theme)
            self.setTheme()
            self.saveTheme(previous_theme)

        dlg = ChangeThemeDialog(currently_selected=current_theme)
        dlg.combo_box.currentIndexChanged.connect(previewTheme)
        if dlg.exec():
            new_theme = dlg.combo_box.currentText()
            for theme in qtvsc.Theme:
                if theme.value['name'] == new_theme:
                    print(f'changing theme to {new_theme}')
                    self.saveTheme(new_theme)
                    self.setTheme()
                    self.updateAllTreesStyles()
                    return

            # did not find a qtvsc theme, switching to Native
            new_theme = 'Native'
            warning_box = QMessageBox()
            warning_box.setIcon(QMessageBox.Warning)
            warning_box.setWindowTitle("Warning")
            warning_box.setText("Reverting to Native style requires restarting treelab")
            warning_box.setStandardButtons(QMessageBox.Ok)
            warning_box.exec()
            print(f'changing theme to {new_theme} on next restart')
            self.saveTheme(new_theme)
        self.setTheme()


    def get_x_from_curve_item(self, curve):
        index = int(curve.Xchoser.currentText().split('@')[0].replace('tab',''))
        tab = self.getTabFromIndex(index)
        path = 'CGNSTree/'+'@'.join(curve.Xchoser.currentText().split('@')[1:])
        node = tab.t.getAtPath(path)
        node_value = node.value()
        if isinstance(node_value, str) and node_value == '_skeleton':
            self.update_node_data_and_children(node)
        return node.value(), node.name()

    def get_y_from_curve_item(self, curve):
        index = int(curve.Ychoser.currentText().split('@')[0].replace('tab',''))
        tab = self.getTabFromIndex(index)
        path = 'CGNSTree/'+'@'.join(curve.Ychoser.currentText().split('@')[1:])
        node = tab.t.getAtPath(path)
        node_value = node.value()
        if isinstance(node_value, str) and node_value == '_skeleton':
            self.update_node_data_and_children(node)
        return node.value(), node.name()

    def draw_curves(self):
        if not self.curves_container: self.add_curve()

        self.fig, ax = plt.subplots(1,1,dpi=150)

        # NOTE this lines may break matplotlib Qt backend:
        # TypeError: setFocusPolicy(self, policy: Qt.FocusPolicy):
        #       argument 1 has unexpected type 'PySide6.QtCore.Qt.FocusPolicy'
        # self.fig.canvas.setFocusPolicy( QtCore.Qt.ClickFocus )
        # self.fig.canvas.setFocus()
        
        xlabels = []
        ylabels = []
        self.snap_cursors = []
        for c in self.curves_container:
            try:
                x, xlabel = self.get_x_from_curve_item(c)
                y, ylabel = self.get_y_from_curve_item(c)
                xlabels += [ xlabel ]
                ylabels += [ ylabel ]
                line, = ax.plot(x,y, label=ylabel)
                snap_cursor = SnappingCursor(ax, line)
                self.snap_cursors += [ snap_cursor ]
                self.fig.canvas.mpl_connect('motion_notify_event', snap_cursor.on_mouse_move)
                self.fig.canvas.mpl_connect('button_press_event', snap_cursor.on_double_click)


            except BaseException as e:
                err_msg = ''.join(traceback.format_exception(type(e),e, e.__traceback__))

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Error")
                msg.setInformativeText(err_msg)
                msg.setWindowTitle("Error")
                msg.exec_()
        ax.set_xlabel(xlabels[0])
        ax.set_ylabel(ylabels[0])
        ax.legend(loc='best')
        plt.tight_layout()
        plt.show()



    def add_curve(self):
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                            QtWidgets.QSizePolicy.Fixed)

        curve = QWidget(self)
        curve.setLayout(QHBoxLayout())
        Xlabel = QLabel('X=')
        Xlabel.setSizePolicy(size_policy)
        curve.layout().addWidget(Xlabel)
        curve.Xchoser = QComboBox()
        curve.Xchoser.addItems( self.plot_x_container )
        curve.Xchoser.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        curve.layout().addWidget(curve.Xchoser)


        Ylabel = QLabel('Y=')
        Ylabel.setSizePolicy(size_policy)
        curve.layout().addWidget(Ylabel)
        curve.Ychoser = QComboBox()
        curve.Ychoser.addItems( self.plot_y_container )
        curve.Ychoser.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        curve.layout().addWidget(curve.Ychoser)

        button_remove_curve = QPushButton()
        button_remove_curve.setSizePolicy(size_policy)
        pixmap = QtGui.QPixmap(GUIpath+"/icons/OwnIcons/remove-curve-16.png")
        ButtonIcon = QtGui.QIcon(pixmap)
        button_remove_curve.setIcon(ButtonIcon)
        button_remove_curve.setIconSize(pixmap.rect().size())
        button_remove_curve.clicked.connect(lambda: self.remove_curve(curve) )
        curve.layout().addWidget(button_remove_curve)


        self.dock.plotter.layout().addWidget(curve)

        self.curves_container += [ curve ]

    def remove_curve(self, curve):
        for i, c in enumerate(self.curves_container):
            if c is curve:
                c.setParent(None)
                del self.curves_container[i]
                return


    def add_selected_nodes_to_plot_x_container(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for node in self.getSelectedNodes():
            path = 'tab%d@'%self.getTabIndex()+node.path().replace('CGNSTree/','')
            if path not in self.plot_x_container:
                self.plot_x_container += [ path ]
        for c in self.curves_container:
            AllItems = [c.Xchoser.itemText(i) for i in range(c.Xchoser.count())]
            for p in self.plot_x_container:
                if p not in AllItems:
                    c.Xchoser.addItem( p )
        QApplication.restoreOverrideCursor()


    def add_selected_nodes_to_plot_y_container(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for node in self.getSelectedNodes():
            path = 'tab%d@'%self.getTabIndex()+node.path().replace('CGNSTree/','')
            if path not in self.plot_y_container:
                self.plot_y_container += [ path ]
        for c in self.curves_container:
            AllItems = [c.Ychoser.itemText(i) for i in range(c.Ychoser.count())]
            for p in self.plot_y_container:
                if p not in AllItems:
                    c.Ychoser.addItem( p )
        QApplication.restoreOverrideCursor()


    def modify_node_data(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        t = self.getCGNSTree()

        if t.file is None or not os.path.exists( t.file):
            QApplication.restoreOverrideCursor()
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error")
            err_msg = ('Cannot save individual node into file, since there is no existing file.\n'
                       'Maybe you never saved the current tree ?\n')
            msg.setInformativeText(err_msg)
            msg.setWindowTitle("Error")
            msg.exec_()
            return

        for node in self.getSelectedNodes():
            try:
                node.saveThisNodeOnly( t.file )
            except TypeError as e:
                e_str = str(e)
                if e_str == 'Only chunked datasets can be resized':
                    err_msg = ('cannot save selected nodes since file:\n\n   %s\n\n'
                        'was not generated using chunks.\n\nTo save modifications, '
                        'please save the entire file')%t.file
                else:
                    err_msg = e_str
                # except BaseException as e:
                #     err_msg = ''.join(traceback.format_exception(etype=type(e),
                #                           value=e, tb=e.__traceback__))
                # finally:
                QApplication.restoreOverrideCursor()

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Error")
                msg.setInformativeText(err_msg)
                msg.setWindowTitle("Error")
                msg.exec_()
                break

        self.selectionInfo()
        QApplication.restoreOverrideCursor()

    def update_node_data_and_children(self, node):
        if node.type() == 'DataArray_t':

            try:
                node.reloadNodeData( self.getCGNSTree().file )
            except BaseException as e:
                err_msg = ''.join(traceback.format_exception(type(e),e, e.__traceback__))
                QApplication.restoreOverrideCursor()

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Error")
                msg.setInformativeText(err_msg)
                msg.setWindowTitle("Error")
                msg.exec_()
                return
            
            item = node.QStandardItem
            item.isStyleCGNSbeingModified = True
            self.setStyleCGNS( item )
            item.isStyleCGNSbeingModified = False
        for child in node[2]: self.update_node_data_and_children(child)

    def update_node_data(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for node in self.getSelectedNodes():
            self.update_node_data_and_children(node)
        self.selectionInfo()
        QApplication.restoreOverrideCursor()

    def unload_data(self, node):
        if node.type() == 'DataArray_t':
            node.setValue('_skeleton')
            # item = node.QStandardItem
            # item.isStyleCGNSbeingModified = True
            # self.setStyleCGNS( item )
            # item.isStyleCGNSbeingModified = False

    def unload_data_and_children(self, node):
        self.unload_data(node)
        for child in node[2]:
            self.unload_data_and_children(child)

    def unload_node_data_recursively(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for node in self.getSelectedNodes():
            self.unload_data_and_children(node)
        tree = self.getQtTree()
        indices = tree.selectionModel().selectedIndexes()
        for index in indices:
            item = tree.model.itemFromIndex(index)
            self.setStyleCGNSrecursively(item)
        self.selectionInfo()
        QApplication.restoreOverrideCursor()

    def replace_link(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for node in self.getSelectedNodes():
            if node.type() != 'Link_t': continue
            item = node.QStandardItem
            path = node.path()
            try:
                node.replaceLink()
            except BaseException as e:
                err_msg = ''.join(traceback.format_exception(type(e),e,e.__traceback__))
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Error")
                msg.setInformativeText(err_msg)
                msg.setWindowTitle("Error")
                msg.exec_()
                break

            node = self.getCGNSTree().getAtPath( path )
            item.node_cgns = node
            item.node_cgns.QStandardItem = item
            item.isStyleCGNSbeingModified = True
            self.setStyleCGNS( item )
            item.isStyleCGNSbeingModified = False
            self.addTreeModelChildrenFromCGNSNode(item.node_cgns)
        self.selectionInfo()
        QApplication.restoreOverrideCursor()


    def pasteNodeTree(self):
        if not self.copiedNodes: return
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for parentitem in self.getSelectedItems():
            node = parentitem.node_cgns
            for paste_node in self.copiedNodes:
                paste_node = paste_node.copy(deep=True)
                node.addChild(paste_node, override_sibling_by_name=False)
                paste_node = node.get(paste_node.name(),Depth=1)
                item = QtGui.QStandardItem(paste_node.name())
                paste_node.QStandardItem = item
                item.node_cgns = paste_node
                item.node_cgns.QStandardItem = item
                item.isStyleCGNSbeingModified = True
                parentitem.appendRow([item])
                self.setStyleCGNS(item)
                item.isStyleCGNSbeingModified = False
                self.addTreeModelChildrenFromCGNSNode(paste_node)
        QApplication.restoreOverrideCursor()

    def addTreeModelChildrenFromCGNSNode(self, node):
        for c in node.children():
            item = QtGui.QStandardItem(c.name())
            item.node_cgns = c
            c.QStandardItem = item
            item.isStyleCGNSbeingModified = True
            node.QStandardItem.appendRow([item])
            self.setStyleCGNS(item)
            item.isStyleCGNSbeingModified = False
            self.addTreeModelChildrenFromCGNSNode(c)



    def copyNodeTree(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.copiedNodes = []
        will_copy = True
        for n in self.getSelectedNodes(): 
            if n.hasAnySkeletonAmongDescendants():
                err_msg = 'Cannot copy the selected nodes, since they '
                err_msg+= 'and/or their children contains skeleton '
                err_msg+= '(unloaded) data. Please load data before '
                err_msg+= 'copying the nodes (hint: use key touch F5).'
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Forbidden opeation")
                msg.setInformativeText(err_msg)
                msg.setWindowTitle("Forbidden")
                msg.exec_()
                will_copy = False
                break
        if will_copy:
            self.copiedNodes = [n.copy(deep=True) for n in self.getSelectedNodes()]
        QApplication.restoreOverrideCursor()


    def cutNodeTree(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.copyNodeTree()
        if self.copiedNodes: self.deleteNodeTree()
        QApplication.restoreOverrideCursor()


    def newNodeTree(self):
        index = self.getTreeSelectedIndexes()
        if len(index) < 1: return
        index = index[0]
        item = self.getTreeItemFromIndex(index)
        tree = self.getQtTree()

        dlg = NewNodeDialog(item.node_cgns.Path)
        if dlg.exec():
            NewName = dlg.NameWidget.text()
            if NewName == '': NewName = 'Node'

            NewType = dlg.TypeWidget.text()
            if NewType == '': NewType = 'UserDefinedData_t'

            NewValue = dlg.ValueWidget.text().strip()
            if NewValue in ['',  '{}', '[]', 'None']:
                NewValue = None

            elif (NewValue.startswith('{') and NewValue.endswith('}')) or \
                 (NewValue.startswith('[') and NewValue.endswith(']')):

                if NewValue.startswith('{'): NewValue = NewValue[1:-1]

                try:
                    NewValue = np.array(eval(NewValue,globals(),{}),order='F')
                    if len(NewValue.shape) == 0: NewValue == eval(NewValue,globals(),{})
                except BaseException as e:
                    err_msg = ''.join(traceback.format_exception(type(e),e,e.__traceback__))

                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText("Error")
                    msg.setInformativeText(err_msg)
                    msg.setWindowTitle("Error")
                    msg.exec_()
                    return



            elif NewValue[0].isdigit():
                if '.' in NewValue:
                    NewValue = np.array([NewValue],dtype=np.float64,order='F')
                else:
                    NewValue = np.array([NewValue],dtype=np.int32,order='F')

            
            indices = tree.selectionModel().selectedIndexes()
            tree.clearSelection()
            tree.setSelectionMode(QAbstractItemView.MultiSelection)
            for index in indices:
                item = tree.model.itemFromIndex(index)

                parentnode = item.node_cgns
                newnode = cgns.castNode([NewName, NewValue, [], NewType])
                newnode.attachTo(parentnode, override_sibling_by_name=False)

                newitem = newnode.QStandardItem = QtGui.QStandardItem(newnode.name())
                item.isStyleCGNSbeingModified = True
                item.appendRow([newitem])
                newitem.node_cgns = newnode
                newitem.QStandardItem = newitem
                newitem.isStyleCGNSbeingModified = True
                self.setStyleCGNS(newitem)
                newitem.isStyleCGNSbeingModified = False
                item.isStyleCGNSbeingModified = False
                newindex = tree.model.indexFromItem(newitem)

                tree.setCurrentIndex(newindex)
            tree.setSelectionMode(QAbstractItemView.ExtendedSelection)


    def deleteNodeTree(self):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        index = self.getTreeSelectedIndexes()
        while len(index)>0:
            index=index[0]
            item = self.getTreeItemFromIndex(index)
            if item.parent():
                item.parent().removeRow(item.row())
            else:
                self.getTreeModel().invisibleRootItem().removeRow(item.row())
            if item.node_cgns.Parent: item.node_cgns.remove()
            index = self.getTreeSelectedIndexes()
        QApplication.restoreOverrideCursor()


    def findNodesTree(self):

        dlg = FindNodeDialog(self.NameToBeFound,
                             self.ValueToBeFound,
                             self.TypeToBeFound,
                             self.DepthToBeFound)
        if dlg.exec():
            # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            RequestedName = dlg.NameWidget.text()
            if RequestedName == '':
                RequestedName = None
            self.NameToBeFound = RequestedName

            RequestedValue = dlg.ValueWidget.text()
            if RequestedValue == '':
                RequestedValue = None
            elif RequestedValue[0].isdigit():
                if '.' in RequestedValue or 'e-' in RequestedValue:
                    try: RequestedValue = float(RequestedValue)
                    except: pass
                else:
                    try: RequestedValue = int(RequestedValue)
                    except: pass
            self.ValueToBeFound = RequestedValue

            RequestedType = dlg.TypeWidget.text()
            if RequestedType == '':
                RequestedType = None
            self.TypeToBeFound = RequestedType

            RequestedDepth = dlg.DepthWidget.text()
            if RequestedDepth == '':
                RequestedDepth = 100
            self.DepthToBeFound = int(RequestedDepth)


            if dlg.searchFromSelection.isChecked():
                self.FoundNodes = []
                indices = self.getTreeSelectedIndexes()
                for index in indices:
                    item = self.getTreeItemFromIndex(index)
                    self.FoundNodes.extend(item.node_cgns.group(
                                                Name=self.NameToBeFound,
                                                Value=self.ValueToBeFound,
                                                Type=self.TypeToBeFound,
                                                Depth=self.DepthToBeFound))

            else:
                self.FoundNodes = self.getCGNSTree().group(Name=self.NameToBeFound,
                                               Value=self.ValueToBeFound,
                                               Type=self.TypeToBeFound,
                                               Depth=self.DepthToBeFound)

            tree = self.getQtTree()
            tree.clearSelection()
            tree.setSelectionMode(QAbstractItemView.MultiSelection)
            for node in self.FoundNodes:
                index = tree.model.indexFromItem(node.QStandardItem)
                tree.setCurrentIndex(index)
            tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.selectionInfo()
            self.CurrentFoundNodeIndex = -1
            # QApplication.restoreOverrideCursor()

    def findNextNodeTree(self):
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.CurrentFoundNodeIndex += 1
        try:
            node = self.FoundNodes[self.CurrentFoundNodeIndex]
        except IndexError:
            self.CurrentFoundNodeIndex = 0

        try:
            node = self.FoundNodes[self.CurrentFoundNodeIndex]
        except IndexError:
            self.CurrentFoundNodeIndex = 0
            return

        tree = self.getQtTree()
        index = tree.model.indexFromItem(node.QStandardItem)
        tree.setCurrentIndex(index)
        # QApplication.restoreOverrideCursor()

    def expandAll(self):
        self.getQtTree().expandAll()

    def expandToZones(self):
        self.getQtTree().expandToDepth(1)

    def collapseAll(self):
        self.getQtTree().collapseAll()

    def zoomInTree(self):
        print('to be reimplemented more efficiently')
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        # root = self.t.QStandardItem
        # self.fontPointSize += 1
        # self.setStyleCGNS(root)
        # for item in self.iterItems(root):
        #     self.setStyleCGNS(item)
        # QApplication.restoreOverrideCursor()

    def zoomOutTree(self):
        print('to be reimplemented more efficiently')
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        # root = self.t.QStandardItem
        # self.fontPointSize -= 1
        # self.setStyleCGNS(root)
        # for item in self.iterItems(root):
        #     self.setStyleCGNS(item)
        # QApplication.restoreOverrideCursor()

    def iterItems(self, root):
        stack = [root]
        while stack:
            parent = stack.pop(0)
            for row in range(parent.rowCount()):
                for column in range(parent.columnCount()):
                    child = parent.child(row, column)
                    yield child
                    if child.hasChildren():
                        stack.append(child)

    def openTree(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file', '.',"CGNS files (*.cgns *.hdf *.hdf5)")
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        onlyFileName = fname[0].split(os.sep)[-1]
        if not onlyFileName: return
        self.newTab(fname[0])

    def reopenTree(self):
        t = self.getCGNSTree()
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        print(f'rebuilding CGNS structure of {t.file}...')
        tic = toc()
        tab = self.getTab()
        tab.t = cgns.load(t.file, only_skeleton=self.only_skeleton)
        tab.t.file = t.file
        QApplication.restoreOverrideCursor()
        print('done (%g s)'%(toc()-tic))
        print('building Qt model...')
        tic = toc()
        self.updateModel(self.getTab())
        print('done (%g s)'%(toc()-tic))

    def saveTree(self):
        t = self.getCGNSTree()
        if t.file:
            print('will write: '+t.file)
            QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            t.replaceSkeletonWithDataRecursively(t.file)
            t.save(t.file)
            print('done')
            QApplication.restoreOverrideCursor()
        else:
            self.saveTreeAs()

    def saveTreeAs(self):
        fname = QFileDialog.getSaveFileName(self, 'Save file', '.',"CGNS files (*.cgns)")
        onlyFileName = fname[0].split(os.sep)[-1]
        t = self.getCGNSTree()
        if onlyFileName:
            QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            print('will write: '+onlyFileName)
            t.replaceSkeletonWithDataRecursively(t.file)
            t.save(fname[0])
            print('done')
            t.file = fname[0]
            self.tab_widget.setTabText(self.getTabIndex(), onlyFileName) 
            QApplication.restoreOverrideCursor()


    def updateNameOfNodeCGNS(self, item):
        try:
            if item.isStyleCGNSbeingModified: return
        except AttributeError:
            item.isStyleCGNSbeingModified = False
        if hasattr(item, "node_cgns"):
            item.node_cgns.setName(item.text())
            return

        try:
            node = [n for n in self.getSelectedNodes() if n.name() == item.text()][0]
        except IndexError:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error")
            msg.setInformativeText(('CGNS data was not migrated. '
                'This will cause unexpected behavior'))
            msg.setWindowTitle("Error")
            msg.exec_()
            return

        item.node_cgns = node
        parentItem = item.parent()
        if parentItem:
            item.node_cgns.moveTo(parentItem.node_cgns, position=item.row(),
                                  override_sibling_by_name=False)
        elif item.node_cgns.Parent:
            item.node_cgns.dettach()

        item.setText(item.node_cgns.name())
        item.node_cgns.item = item
        self.setStyleCGNS(item)
        self.updateModelChildrenFromItem(item)

    def updateTypeOfNodeCGNS(self):
        for index in self.getTreeSelectedIndexes():
            item = self.getTreeItemFromIndex(index)
            newType = self.dock.typeEditor.lineEditor.text()
            item.node_cgns.setType(newType)
            item.isStyleCGNSbeingModified = True
            self.setStyleCGNS(item)
            item.isStyleCGNSbeingModified = False

    def getTabIndex(self): return self.tab_widget.currentIndex()
    
    def getTab(self): return self.tab_widget.widget(self.getTabIndex())

    def getTabFromIndex(self, index): return self.tab_widget.widget(index)
    
    def getTabs(self):
        return [self.tab_widget.widget(i) for i in range(self.tab_widget.count())]

    def getQtTree(self): return self.getTab().tree

    def getQtTrees(self): return [tab.tree for tab in self.getTabs()]

    def getCGNSTree(self): return self.getTab().t

    def getCGNSTrees(self): return [tab.t for tab in self.getTabs()]

    def getTreeModel(self): return self.getQtTree().model

    def getTreeItemFromIndex(self, index):
        return self.getTreeModel().itemFromIndex(index)

    def getTreeSelectionModel(self): return self.getQtTree().selectionModel()

    def getTreeSelectedIndexes(self): return self.getTreeSelectionModel().selectedIndexes()

    def getSelectedItems(self):
        return [self.getTreeItemFromIndex(i) for i in self.getTreeSelectedIndexes()]

    def getSelectedNodes(self):
        return [self.getTreeItemFromIndex(i).node_cgns for i in self.getTreeSelectedIndexes()]

    def selectionInfo(self):
        try:
            indexes = self.getTreeSelectedIndexes()
        except:
            return
        if isinstance(indexes, QtCore.QModelIndex): indexes = [indexes]
        MSG = '%d nodes selected'%len(indexes)
        self.setStatusTip( MSG )
        self.statusBar().showMessage( MSG )

        if indexes:
            self.dock.node_toolbar.setVisible(True)
            self.dock.pathLabel.setVisible(True)
            self.dock.typeEditor.setVisible(True)
            self.dock.tableShow.setVisible(True)
            self.dock.plotter.setVisible(True)
            self.dock.dataDimensionsLabel.setVisible(True)
            self.dock.dataSlicer.setVisible(True)
            self.table.setVisible(True)
        else:
            self.dock.node_toolbar.setVisible(False)
            self.dock.pathLabel.setVisible(False)
            self.dock.typeEditor.setVisible(False)
            self.dock.tableShow.setVisible(False)
            self.dock.plotter.setVisible(False)
            self.dock.dataDimensionsLabel.setVisible(False)
            self.dock.dataSlicer.setVisible(False)
            self.table.setVisible(False)

        self.updateTable()


    def updateTable(self):
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.table.isBeingUpdated = True
        try: node = self.getSelectedNodes()[0]
        except IndexError: node = None


        if node is None:
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setItem(0,0, QTableWidgetItem('please select a node'))
            self.table.resizeColumnsToContents()
            self.dock.setWindowTitle('please select a node')
            self.table.isBeingUpdated = False
            return
        
        def show_big_array_warning():
            msg_bigarray = 'Too big array for efficient table creation.\n'
            msg_bigarray+= 'If you still want to show it, please\n'
            msg_bigarray+= 'check the option "Always show data in table"\n'
            msg_bigarray+= 'shown below. But beware, creating\n'
            msg_bigarray+= 'the table may take a while\n'

            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            tableItem = QTableWidgetItem(msg_bigarray)
            self.table.setItem(0,0, tableItem)

            self.table.resizeColumnsToContents()
            self.table.resizeRowsToContents()
            self.table.isBeingUpdated = False


            


        self.dock.setWindowTitle(node.name())
        self.dock.pathLabel.label.setText(node.path())
        self.dock.typeEditor.lineEditor.setText(node.type())
        value = node.value()
        if isinstance(value, np.ndarray):
            msg = '%s dims %s'%(str(type(value))[1:-1],str(value.shape))
            msg += ' %s'%(str(value.dtype))
            msg += '  F=%s'%str(value.flags['F_CONTIGUOUS'])
            self.dock.dataDimensionsLabel.setText(msg)
            dim = len(value.shape)
            Ni = value.shape[0]
            Nj = value.shape[1] if dim > 1 else 1
            Nk = value.shape[2] if dim > 2 else 1


            if dim == 1:
                self.dock.dataSlicer.setVisible(False)
                if Ni > self.max_nb_table_items and not self.dock.tableShow.check_box.isChecked():
                    show_big_array_warning()
                    return
                
                self.table.setRowCount(Ni)
                self.table.setColumnCount(1)
                for i in range(Ni):
                    self.table.setItem(i, 0, QTableWidgetItem('{}'.format(value[i])))

            elif dim == 2:
                self.dock.dataSlicer.setVisible(False)
                if Ni*Nj > self.max_nb_table_items and not self.dock.tableShow.check_box.isChecked():
                    show_big_array_warning()
                    return


                self.table.setRowCount(Ni)
                self.table.setColumnCount(Nj)

                for i in range(Ni):
                    for j in range(Nj):
                        self.table.setItem(i,j, QTableWidgetItem("%g"%value[i,j]))

            elif dim == 3:
                planeIndex = self.dock.dataSlicer.ijkSelector.currentText()
                planeValue = self.dock.dataSlicer.sliceSelector.value()

                if planeIndex == 'k':
                    self.dock.dataSlicer.sliceSelector.setMaximum(Nk-1)
                    self.dock.dataSlicer.sliceSelector.setMinimum(-Nk)
                    if Ni*Nj > self.max_nb_table_items and not self.dock.tableShow.check_box.isChecked():
                        show_big_array_warning()
                        return

                    self.table.setRowCount(Ni)
                    self.table.setColumnCount(Nj)

                elif planeIndex == 'j':
                    self.dock.dataSlicer.sliceSelector.setMaximum(Nj-1)
                    self.dock.dataSlicer.sliceSelector.setMinimum(-Nj)
                    if Ni*Nk > self.max_nb_table_items and not self.dock.tableShow.check_box.isChecked():
                        show_big_array_warning()
                        return


                    self.table.setRowCount(Ni)
                    self.table.setColumnCount(Nk)

                else:
                    self.dock.dataSlicer.sliceSelector.setMaximum(Ni-1)
                    self.dock.dataSlicer.sliceSelector.setMinimum(-Ni)

                    if Nk*Nj > self.max_nb_table_items and not self.dock.tableShow.check_box.isChecked():
                        show_big_array_warning()
                        return

                    self.table.setRowCount(Nj)
                    self.table.setColumnCount(Nk)


                if planeValue > self.dock.dataSlicer.sliceSelector.maximum() or \
                    planeValue < self.dock.dataSlicer.sliceSelector.minimum():
                    planeValue = 0
                    self.dock.dataSlicer.sliceSelector.setValue(planeValue)

                if planeIndex == 'k':
                    for i in range(Ni):
                        for j in range(Nj):
                            self.table.setItem(i,j, QTableWidgetItem("%g"%value[i,j,planeValue]))
                elif planeIndex == 'j':
                    for i in range(Ni):
                        for k in range(Nk):
                            self.table.setItem(i,k, QTableWidgetItem("%g"%value[i,planeValue,k]))
                else:
                    for j in range(Nj):
                        for k in range(Nk):
                            self.table.setItem(j,k, QTableWidgetItem("%g"%value[planeValue,j,k]))
                self.dock.dataSlicer.setVisible(True)


        elif isinstance(value,str):
            self.dock.dataDimensionsLabel.setText('%s with dims %d'%(str(type(value))[1:-1],len(value)))
            self.dock.dataSlicer.setVisible(False)
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            if value == '_skeleton':
                tableItem = QTableWidgetItem('_skeleton\n(press F5 keytouch to load data)')
                font = tableItem.font()
                font.setItalic(True)
                brush = QtGui.QBrush()
                brush.setColor(QtGui.QColor("#BD3809"))
                tableItem.setForeground(brush)
                tableItem.setFont(font)
                self.table.setItem(0,0, tableItem)
            else:
                self.table.setItem(0,0, QTableWidgetItem(value))

        elif isinstance(value,list):
            self.dock.dataSlicer.setVisible(False)
            if not all([isinstance(v,str) for v in value]):
                raise ValueError('cannot show value of node %s'%node.name())
            Ni = len(value)
            self.dock.dataDimensionsLabel.setText('class list of str with dims %d'%Ni)
            self.table.setRowCount(Ni)
            self.table.setColumnCount(1)
            for i in range(Ni):
                self.table.setItem(i, 0, QTableWidgetItem('{}'.format(value[i])))

        elif value is None:
            self.dock.dataDimensionsLabel.setText('class None')
            self.dock.dataSlicer.setVisible(False)
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            tableItem = QTableWidgetItem('None')
            font = tableItem.font()
            font.setBold(True)
            brush = QtGui.QBrush()
            brush.setColor(QtGui.QColor("#8049d8"))
            tableItem.setForeground(brush)
            tableItem.setFont(font)
            self.table.setItem(0,0, tableItem)

        else:
            self.dock.dataSlicer.setVisible(False)
            self.dock.dataDimensionsLabel.setVisible(False)
            self.table.isBeingUpdated = False
            raise ValueError('type of value of node %s was "%s" and is not supported'%(node.name(),type(value)))

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        self.table.isBeingUpdated = False
        # QApplication.restoreOverrideCursor()


    def createTable(self):
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.table = TableWithCopy()
        self.table.isBeingUpdated = True
        self.table.setAlternatingRowColors(True)
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setItem(0,0, QTableWidgetItem("... and its data will be shown here"))
        self.table.move(0,0)
        self.table.horizontalHeader().setMinimumSectionSize(20)
        self.table.verticalHeader().setMinimumSectionSize(20)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        self.table.isBeingUpdated = False
        self.table.corner = self.table.findChild(QAbstractButton)
        self.table.corner.setToolTip('select all (Ctrl+A)')
        self.table.setVisible(False)

        self.table.itemChanged.connect(self.updateValueOfNodeCGNS)
        # QApplication.restoreOverrideCursor()


    def updateValueOfNodeCGNS(self, item):
        if self.table.isBeingUpdated: return
        # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        tree = self.getQtTree()
        for index in tree.selectionModel().selectedIndexes():
            treeitem = tree.model.itemFromIndex(index)

        node_cgns = treeitem.node_cgns
        value = node_cgns.value()
        print('actual value is : '+str(value))
        new_value = item.text().strip()

        i = item.row()
        j = item.column()

        newlocals = {'array':value}

        try:
            if new_value == 'None':
                node_cgns.setValue(None)

            elif new_value in ['{}' , '[]']:
                node_cgns.setValue(value)

            elif new_value.startswith('[') and new_value.endswith(']'):
                newNumpyArray = np.array(eval(new_value,globals(),newlocals), order='F')
                node_cgns.setValue(newNumpyArray)

            elif new_value.startswith('{') and new_value.endswith('}'):
                expr = new_value[1:-1]
                if expr.startswith('this:'):
                    expr = expr.replace('this:','')
                    newNumpyValue = eval(expr,globals(),newlocals)
                    if isinstance(value,np.ndarray):
                        dim = len(value.shape)
                        if dim == 1:
                            value[i] = newNumpyValue
                        elif dim == 2:
                            value[i,j] = newNumpyValue
                        elif dim == 3:
                            planeIndex = self.dock.dataSlicer.ijkSelector.currentText()
                            planeValue = self.dock.dataSlicer.sliceSelector.value()
                            if planeIndex == 'k':
                                value[i,j,planeValue] = newNumpyValue
                            if planeIndex == 'j':
                                value[i,planeValue,j] = newNumpyValue
                            else:
                                value[planeValue,i,j] = newNumpyValue

                    elif isinstance(value, str) or value is None:
                        node_cgns.setValue(newNumpyArray)

                    elif isinstance(value, list):
                        value[i] = newNumpyValue

                else:
                    newNumpyArray = np.array(eval(expr,globals(),newlocals), order='F')
                    if isinstance(value, np.ndarray) and len(newNumpyArray.shape) == 0:
                        value[:] = newNumpyArray
                    else:
                        node_cgns.setValue(newNumpyArray)

            elif isinstance(value, np.ndarray):
                dim = len(value.shape)

                if dim == 1:
                    i = item.row()
                    if new_value == '':
                        value[i] = 0
                    else:
                        try:
                            value[i] = new_value
                        except ValueError:
                            node_cgns.setValue(new_value)

                elif dim == 2:
                    i = item.row()
                    j = item.column()

                    if new_value == '':
                        value[i,j] = 0
                    else:
                        try:
                            value[i,j] = new_value
                        except ValueError:
                            node_cgns.setValue(new_value)

                elif dim == 3:
                    i = item.row()
                    j = item.column()

                    planeIndex = self.dock.dataSlicer.ijkSelector.currentText()
                    planeValue = self.dock.dataSlicer.sliceSelector.value()
                    if planeIndex == 'k':
                        if new_value == '':
                            value[i,j,planeValue] = 0
                        else:
                            try:
                                value[i,j,planeValue] = new_value
                            except ValueError:
                                node_cgns.setValue(new_value)
                    elif planeIndex == 'j':
                        if new_value == '':
                            value[i,planeValue,j] = 0
                        else:
                            try:
                                value[i,planeValue,j] = new_value
                            except ValueError:
                                node_cgns.setValue(new_value)
                    else:
                        if new_value == '':
                            value[planeValue,i,j] = 0
                        else:
                            try:
                                value[planeValue,i,j] = new_value
                            except ValueError:
                                node_cgns.setValue(new_value)


            elif isinstance(value,str) or value is None:
                if new_value == '':
                    node_cgns.setValue(None)
                elif new_value[0].isdigit():
                    if '.' in new_value:
                        new_value = np.array([new_value],dtype=np.float64,order='F')
                    else:
                        new_value = np.array([new_value],dtype=np.int32,order='F')
                node_cgns.setValue(new_value)

            elif isinstance(value,list):
                i = item.row()
                if new_value == '':
                    if len(value) > 1:
                        del value[i]
                    else:
                        value = None
                else:
                    value[i] = new_value
                node_cgns.setValue(value)


        except BaseException as e:
            err_msg = ''.join(traceback.format_exception(type(e),e, e.__traceback__))

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error")
            msg.setInformativeText(err_msg)
            msg.setWindowTitle("Error")
            msg.exec_()
            new_value = value
            node_cgns.setValue(new_value)

        self.updateTable()
        if isinstance(new_value, str) and new_value == '_skeleton':
            treeitem.isStyleCGNSbeingModified = True
            self.setStyleCGNS( treeitem )
            treeitem.isStyleCGNSbeingModified = False
        # QApplication.restoreOverrideCursor()


    def swapNodes(self, s):
        indices = self.getTreeSelectedIndexes()
        if len(indices) != 2:
            print('requires selecting 2 nodes for swapping')
            return
        else:
            # QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            item1 = self.getTreeItemFromIndex(indices[0])
            item2 = self.getTreeItemFromIndex(indices[1])

            for item in [item1, item2]:
                item.isStyleCGNSbeingModified = True

            node1 = item1.node_cgns
            node2 = item2.node_cgns


            item1Row = item1.row()
            item1Parent = item1.parent()
            if item1Parent:
                row1 = item1Parent.takeRow(item1Row)

            item2Row = item2.row()
            item2Parent = item2.parent()
            if item2Parent:
                row2 = item2Parent.takeRow(item2Row)

            if item1Parent and item2Parent:
                item2Parent.insertRow(item2Row, row1[0])
                item1Parent.insertRow(item1Row, row2[0])

            node1.QStandardItem = item1
            node2.QStandardItem = item2

            node1.swap(node2)

            tree = self.getQtTree()
            tree.setSelectionMode(QAbstractItemView.MultiSelection)
            for item in [item1, item2]:
                self.setStyleCGNS(item)
                self.updateModelChildrenFromItem(item)
                index = tree.model.indexFromItem(item)
                tree.setCurrentIndex(index)
            tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

            for item in [item1, item2]:
                item.isStyleCGNSbeingModified = False
        # QApplication.restoreOverrideCursor()

    def setStyleCGNSrecursively(self,MainItem):
        self.setStyleCGNS(MainItem)
        node = MainItem.node_cgns
        for child in node.children():
            item = child.QStandardItem
            self.setStyleCGNSrecursively(item)

    def setStyleCGNS(self, MainItem):

        def putIcon(pathToIconImage):
            Icon = QtGui.QIcon(pathToIconImage)
            MainItem.setIcon(Icon)

        node = MainItem.node_cgns
        MainItem.isStyleCGNSbeingModified = True

        font = MainItem.font()
        font.setPointSize( int(self.fontPointSize) )
        font.setBold(False)
        font.setItalic(False)
        brush = QtGui.QBrush()
        iconSize = int(self.fontPointSize*1.333)
        # self.tree.setIconSize(QtCore.QSize(iconSize,iconSize))
        MainItem.setSizeHint(QtCore.QSize(int(iconSize*1.75),int(iconSize*1.75)))
        MainItem.setIcon(QtGui.QIcon())

        node_value = node.value()
        node_type = node.type()

        if node_type == 'CGNSTree_t':
            putIcon(GUIpath+"/icons/fugue-icons-3.5.6/tree")
            font.setBold(True)
        elif not MainItem.parent():
            putIcon(GUIpath+"/icons/fugue-icons-3.5.6/tree-red")
            font.setBold(True)
            # brush.setColor(QtGui.QColor("red"))
        elif node_type == 'Zone_t':
            putIcon(GUIpath+"/icons/icons8/zone-2D.png")
            font.setBold(True)
            brush = QtGui.QBrush()
            brush.setColor(QtGui.QColor("#5d8bb6"))
            MainItem.setForeground(brush)
        elif node_type == 'CGNSBase_t':
            color = '#6cb369' if self.isDark else '#1d6419'
            MainItem.setIcon(self.getColoredIcon(
                GUIpath+"/icons/icons8/icons8-box-32.png", color))
            font.setBold(True)
            font.setItalic(True)
            brush.setColor(QtGui.QColor(color))
            MainItem.setForeground(brush)

        elif node_type == 'GridCoordinates_t':
            MainItem.setIcon(self.getColoredIcon(GUIpath+'/icons/icons8/icons8-coordinate-system-16.png'))
        elif node.name() == 'CoordinateX':
            MainItem.setIcon(self.getColoredIcon(GUIpath+"/icons/icons8/icons8-x-coordinate-16"))
        elif node.name() == 'CoordinateY':
            MainItem.setIcon(self.getColoredIcon(GUIpath+"/icons/icons8/icons8-y-coordinate-16"))
        elif node.name() == 'CoordinateZ':
            MainItem.setIcon(self.getColoredIcon(GUIpath+"/icons/icons8/icons8-z-coordinate-16"))
        elif node_type == 'FlowSolution_t':
            putIcon(GUIpath+"/icons/OwnIcons/field-16")
        elif node_type in ('CGNSLibraryVersion_t','ZoneType_t'):
            font.setItalic(True)
        elif node_type == 'Link_t':
            putIcon(GUIpath+"/icons/fugue-icons-3.5.6/external.png")
            font.setBold(True)
            font.setItalic(True)
            # brush.setColor(QtGui.QColor("blue"))
            
        elif node_type in ('Family_t','FamilyName_t','FamilyBC_t','AdditionalFamilyName_t'):
            color = '#c5702a' if self.isDark else '#773804'
            MainItem.setIcon(self.getColoredIcon(
                GUIpath+"/icons/icons8/icons8-famille-homme-femme-26.png", color))
            font.setItalic(True)
            brush.setColor(QtGui.QColor(color))
            MainItem.setForeground(brush)
        elif node_type == 'ConvergenceHistory_t':
            putIcon(GUIpath+"/icons/fugue-icons-3.5.6/system-monitor.png")
            font.setItalic(True)
        elif node_type == 'ZoneGridConnectivity_t':
            MainItem.setIcon(self.getColoredIcon(GUIpath+"/icons/fugue-icons-3.5.6/plug-disconnect.png"))
        elif node_type == 'ReferenceState_t':
            putIcon(GUIpath+"/icons/fugue-icons-3.5.6/script-attribute-r.png")
            font.setItalic(True)
        elif node_type == 'FlowEquationSet_t':
            putIcon(GUIpath+"/icons/icons8/Sigma.png")
            font.setItalic(True)
        elif node_type == 'UserDefinedData_t':
            MainItem.setIcon(self.getColoredIcon(GUIpath+"/icons/fugue-icons-3.5.6/user-silhouette.png"))
            font.setItalic(True)
            color = QtGui.QColor(self.colors['icon.foreground'])
            color.setAlphaF(0.5)
            brush.setColor(color)
            MainItem.setForeground(brush)
        elif node_type == 'ZoneBC_t':
            MainItem.setIcon(self.getColoredQtvscIcon(qtvsc.FaSolid.BORDER_STYLE))

        if isinstance(node_value,str) and node_value == '_skeleton':
            MainItem.setIcon(self.getColoredQtvscIcon(qtvsc.FaSolid.UPLOAD))
            font.setBold(True)
            font.setItalic(True)


        # MainItem.setForeground(brush)
        MainItem.setFont(font)
        MainItem.isStyleCGNSbeingModified = False


    def registerTreestyle(self):
        path_vline = os.path.join(GUIpath,'style','stylesheet-vline.png')
        path_more = os.path.join(GUIpath,'style','stylesheet-branch-more.png')
        path_end = os.path.join(GUIpath,'style','stylesheet-branch-end.png')
        path_closed = os.path.join(GUIpath,'icons','qtvsc','plus_square.png')
        path_open = os.path.join(GUIpath,'icons','qtvsc','minus_square.png')
        # QTreeView::branch:has-siblings:!adjoins-item {{
        #     border-image: url({path_vline}) 0;
        # }}
        style = f"""

        QTreeView::branch:has-siblings:adjoins-item {{
            border-image: url({path_more}) 0;
        }}

        QTreeView::branch:!has-children:!has-siblings:adjoins-item {{
            border-image: url({path_end}) 0;
        }}
        
        QTreeView::branch:has-children:!has-siblings:closed,
        QTreeView::branch:closed:has-children:has-siblings {{
                border-image: none;
                image: url({path_closed});
        }}

        QTreeView::branch:open:has-children:!has-siblings,
        QTreeView::branch:open:has-children:has-siblings  {{
                border-image: none;
                image: url({path_open});
        }}
        """
        style = style.replace('\\','/') # curiously required by Windows
        # gradient color for background
        # QTreeView {{
        #     background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #4a4a4a, stop: 1 #2e2e2e);
        # }}
        self.treestyle = style

    def updateAllTreesStyles(self):
        self.registerTreestyle()
        def iterate_tree(index):
            item = model.itemFromIndex(index)
            self.setStyleCGNS(item)
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                iterate_tree(child_index)
        
        for tab in self.getTabs():
            model = tab.tree.model
            root_index = model.indexFromItem(tab.t.QStandardItem)
            iterate_tree(root_index)
            tab.setStyleSheet(self.treestyle)

    def updateModel(self, tab):
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        nodes = tab.t.group()

        tab.tree.model.setRowCount(0)
        root = tab.tree.model.invisibleRootItem()

        tab.t.QStandardItem = QtGui.QStandardItem(tab.t.name())
        tab.t.QStandardItem.node_cgns = tab.t
        root.appendRow([tab.t.QStandardItem])
        self.setStyleCGNS(tab.t.QStandardItem)

        for node in nodes:
            MainItem = node.QStandardItem = QtGui.QStandardItem(node.name())
            MainItem.node_cgns = node
            node.Parent.QStandardItem.appendRow([MainItem])
            self.setStyleCGNS(MainItem)
        tab.tree.expandToDepth(1)
        QApplication.restoreOverrideCursor()

    def updateModelChildrenFromItem(self, item):
        if item.hasChildren():
            node = item.node_cgns
            CGNSchildren = node.children()
            for row in range(item.rowCount()):
                for col in range(item.columnCount()):
                    child = item.child(row, col)
                    try:
                        child.node_cgns = CGNSchildren[row]
                    except IndexError:
                        raise ValueError('could not retrieve child %s (%d) for node %s '%(child.text(),row,node.name()))
                    child.node_cgns.item = child
                    self.updateModelChildrenFromItem(child)

    def updateColorsBasedOnTheme(self):
        try:
            native_theme = self.theme == 'Native'
        except:
            native_theme = False
        if native_theme:
            palette = self.palette()
            default_fg_color = palette.color(palette.ColorGroup.Normal, palette.ColorRole.WindowText)
            self.colors = {'icon.foreground':default_fg_color}
        else:
            # icon color picker
            # possible colors are in qtvsc.list_color_id()
            icon = qtvsc.theme_icon(qtvsc.FaSolid.SQUARE_FULL, 'icon.foreground')
            pixmap = icon.pixmap(QtCore.QSize(12, 12))
            image = pixmap.toImage()
            self.colors = {'icon.foreground':image.pixelColor(6, 6)}
        if self.colors['icon.foreground'].lightnessF() > 0.5:
            self.isDark = True
        else:
            self.isDark = False

    def saveTheme(self, new_theme):
        try: theme_name = new_theme.value['name']
        except: theme_name = new_theme

        try:
            with open(treelab_user_config,'w') as f:
                f.write(theme_name)
        except:
            print('WARNING: could not edit treelab user config')

    def setTheme(self):
        self.theme = get_user_theme()
        if self.theme != 'Native': self.setStyleSheet(qtvsc.load_stylesheet(self.theme))
        self.updateColorsBasedOnTheme()
        self.createIconsOfButtons()

    def createIconsOfButtons(self):
        # node_toolbar dockable buttons
        self.dock.node_toolbar.button_update_node_data.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.UPLOAD))
        self.dock.node_toolbar.button_unload_node_data_recursively.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.SORT_AMOUNT_DOWN))
        
        original_icon = self.getColoredQtvscIcon(qtvsc.FaSolid.EXTERNAL_LINK_ALT)
        pixmap = original_icon.pixmap(QtCore.QSize(64, 64))
        transformed_pixmap = pixmap.transformed(QtGui.QTransform().rotate(180))
        self.dock.node_toolbar.button_replace_link.setIcon(
            QtGui.QIcon(transformed_pixmap))
        
        self.dock.node_toolbar.button_modify_node_data.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.DOWNLOAD))

        self.dock.node_toolbar.button_add_curve.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.GRAPH_LINE))
        self.dock.node_toolbar.button_draw_curves.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaRegular.EYE))
        
        # toolbar buttons
        self.toolbar.button_new.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.NEW_FILE))
        self.toolbar.button_open.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.NEW_FOLDER))
        self.toolbar.button_reopen.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.ISSUE_REOPENED))
        self.toolbar.button_save.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.SAVE))
        self.toolbar.button_saveAs.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.SAVE_AS))
        self.toolbar.button_expandAll.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.EXPAND_ALL))
        self.toolbar.button_collapseAll.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.COLLAPSE_ALL))
        self.toolbar.button_findNode.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.SEARCH))
        self.toolbar.button_findNextNode.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.SHARE))
        self.toolbar.button_newNodeTree.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.PLUS))
        self.toolbar.button_deleteNodeTree.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.TIMES))
        self.toolbar.button_swap.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.RANDOM))
        self.toolbar.button_copyNodeTree.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.COPY))
        self.toolbar.button_cutNodeTree.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.CUT))
        self.toolbar.button_pasteNodeTree.setIcon(
            self.getColoredQtvscIcon(qtvsc.FaSolid.PASTE))
        self.toolbar.button_theme.setIcon(
            self.getColoredQtvscIcon(qtvsc.Vsc.COLOR_MODE))
        
class TableWithCopy(QTableWidget):
    """
    this class extends QTableWidget
    * supports copying multiple cell's text onto the clipboard
    * formatted specifically to work with multiple-cell paste into programs
      like google sheets, excel, or numbers
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

        if event.key() == QtCore.Qt.Key_C and (event.modifiers() & QtCore.Qt.ControlModifier):
            copied_cells = self.selectedIndexes()
            self.copied_data = []

            copy_text = ''
            max_column = copied_cells[-1].column()
            for elt, c in enumerate(copied_cells):
                i = c.row()
                j = c.column()
                item = self.item(i,j)
                self.copied_data.append( item.text() )
                copy_text += item.text()
                if c.column() == max_column:
                    copy_text += '\n'
                else:
                    copy_text += '\t'
            QApplication.clipboard().setText(copy_text)

        elif event.key() == QtCore.Qt.Key_V and (event.modifiers() & QtCore.Qt.ControlModifier):
            pasting_cells = self.selectedIndexes()
            for copy, paste in zip(self.copied_data, pasting_cells):
                self.setItem(paste.row(), paste.column(), QTableWidgetItem(copy))


        elif event.key() == QtCore.Qt.Key_Delete:
            deleting_cells = sorted(self.selectedIndexes())
            for delete in deleting_cells[::-1]:
                self.setItem(delete.row(), delete.column(), QTableWidgetItem(''))

        elif event.key() == QtCore.Qt.Key_A and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.selectAll()




class FindNodeDialog(QDialog):
    def __init__(self, PreviousName, PreviousValue, PreviousType, DepthToBeFound):
        super().__init__()

        self.setWindowTitle("Find Node...")

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QFormLayout()
        self.searchFromTop = QRadioButton('Top')
        self.searchFromTop.setChecked(True)
        self.searchFromSelection = QRadioButton('Selection')
        self.searchLayout = QHBoxLayout()
        self.searchLayout.layout().addWidget(self.searchFromTop)
        self.searchLayout.layout().addWidget(self.searchFromSelection)
        self.layout.addRow(QLabel("search from:"), self.searchLayout)
        self.NameWidget = QLineEdit(PreviousName)
        if PreviousValue is not None:
            self.ValueWidget = QLineEdit(str(PreviousValue))
        else:
            self.ValueWidget = QLineEdit()
        self.TypeWidget = QLineEdit(PreviousType)
        self.DepthWidget = QSpinBox()
        self.DepthWidget.setValue(DepthToBeFound)
        self.layout.addRow(QLabel("Name:"),  self.NameWidget)
        self.layout.addRow(QLabel("Value:"), self.ValueWidget)
        self.layout.addRow(QLabel("Type:"),  self.TypeWidget)
        self.layout.addRow(QLabel("Depth:"),  self.DepthWidget)
        self.layout.addWidget(self.buttonBox)

        self.setLayout(self.layout)

class ChangeThemeDialog(QDialog):
    def __init__(self, currently_selected='(select a theme)'):
        super().__init__()

        self.setWindowTitle("Change color theme ")
        self.setGeometry(100, 100, 300, 150)

        # Create a layout for the dialog
        self.layout = QVBoxLayout(self)

        # Create a label
        self.label = QLabel("Select an option:\n(full theme changes requires restart)")

        # Create a combobox
        self.combo_box = QComboBox()
        self.combo_box.addItem('Native')
        for theme in qtvsc.Theme:
            self.combo_box.addItem(theme.value['name'])

        self.combo_box.setCurrentText(currently_selected)
        # self.combo_box.currentIndexChanged.connect(self.previewTheme)

        # Add the label and combobox to the layout
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.combo_box)

        # Create a button box to hold OK and Cancel buttons
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        button_box = QDialogButtonBox(QBtn)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

    def get_selected_option(self):
        # Get the selected option from the combobox
        return self.combo_box.currentText()
    
    # def previewTheme(self):
    #     new_theme=self.get_selected_option()
    #     for theme in qtvsc.Theme:
    #         if theme.value['name'] == new_theme:
    #             print(f'changing theme to {new_theme}')
    #             ?.saveTheme(new_theme)
    #             ?.setTheme()
    #             return



class NewNodeDialog(QDialog):
    def __init__(self, NodeParentLabel):
        super().__init__()

        self.setWindowTitle("New Node...")

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel


        self.layout = QFormLayout()
        NodeParentQ = QLineEdit(NodeParentLabel)
        NodeParentQ.setReadOnly(True)
        NodeParentQ.setStyleSheet("QLineEdit {background : rgb(220, 224, 230); color : rgb(41, 43, 46);}")
        self.layout.addRow(QLabel("Parent:"), NodeParentQ)
        self.NameWidget = QLineEdit('NodeName')
        self.ValueWidget = QLineEdit('None')
        self.TypeWidget = QLineEdit('DataArray_t')
        self.layout.addRow(QLabel("Name:"),  self.NameWidget)
        self.layout.addRow(QLabel("Value:"), self.ValueWidget)
        self.layout.addRow(QLabel("Type:"),  self.TypeWidget)

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

        self.setLayout(self.layout)


class TabEditionDialog(QDialog):
    def __init__(self, index, tab_widget):
        super().__init__()

        self.setWindowTitle("Set new tab name")
        tab = tab_widget.widget(index)
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.layout = QFormLayout()
        self.FilePath = QLineEdit(str(tab.t.file))
        self.FilePath.setReadOnly(True)
        self.layout.addRow(QLabel("File path:"),  self.FilePath)

        self.NameWidget = QLineEdit(tab_widget.tabText(index))
        self.layout.addRow(QLabel("Tab name:"),  self.NameWidget)


        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

        self.setLayout(self.layout)


def launch():
    
    # print(sys.argv)
    args = sys.argv[1:] 

    filenames = [f for f in args if f.endswith('.cgns') or \
                                   f.endswith('.hdf')]
    
    only_skeleton = any([f for f in args if f=='-s'])

    app = QApplication( sys.argv )
    app.setWindowIcon(QtGui.QIcon(os.path.join(GUIpath,"icons","fugue-icons-3.5.6","tree")))
    print('only_skeleton =',only_skeleton, " (use -s to set to True)")
    MW = MainWindow( filenames, only_skeleton )
    MW.resize(650, 815)    
    MW.show()
    sys.exit( app.exec_() )



if __name__ == "__main__" :
    launch( sys.argv )
