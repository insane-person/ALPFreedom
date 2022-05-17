import PyQt5

from PyQt5 import uic
from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QDialog, QApplication, QHBoxLayout, QCheckBox, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt, pyqtSlot


import os
import sys

import jmespath
import api
import re

from threading import Thread, Lock


class NaturalStandardItem(QtGui.QStandardItem):
    @staticmethod
    def _human_key(key):
        parts = re.split('(\d+)', key)
        return tuple((e.swapcase() if i % 2 == 0 else int(e)) for i, e in enumerate(parts))

    def __lt__(self, other):
        return self._human_key(self.text()) < self._human_key(other.text())


class QTableWidgetFixedItem(QTableWidgetItem):
    def __init__(self, *args, **kwargs):
        super(QTableWidgetFixedItem, self).__init__(*args, **kwargs)
        flags = self.flags()
        flags ^= Qt.ItemIsSelectable
        flags ^= Qt.ItemIsEditable
        self.setFlags(flags)


class MainWindow(QDialog):
    def __init__(self):
        super(QDialog, self).__init__()
        uic.loadUi('gui.ui', self)

        # Download thread control lock
        self.th_lock = Lock()

        # TODO update filter parameters
        self.clear_layout(self.horizontalLayout)

        self.setWindowTitle('AlpFreedom')
        self.setWindowIcon(QtGui.QIcon('./images/logo.png'))

        self.connection = api.Connection('https://alpfederation.ru')
        self.connection.get_mountain_ranges()
        self.connection.get_all_regions()

        self.MountainRanges.currentIndexChanged[int].connect(self.choose_range)
        self.MountainAreas.currentIndexChanged[int].connect(self.choose_area)

        model = QtGui.QStandardItemModel()
        for mountain_range in self.connection.mountain_ranges:
            it = NaturalStandardItem(mountain_range['name'])
            it.setData(mountain_range['id'])
            model.appendRow(it)
        model.sort(0)
        self.MountainRanges.setModel(model)

        self.tableWidget.setColumnCount(4)
        self.tableWidget.setRowCount(0)

        self.tableWidget.setHorizontalHeaderLabels(["+", "Вершина", "Высота"])

        hheader = self.tableWidget.horizontalHeader()
        hheader.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(1, QHeaderView.Stretch)
        hheader.setSectionResizeMode(2, QHeaderView.Fixed)

        self.tableWidget.horizontalHeaderItem(0).setTextAlignment(Qt.AlignCenter)
        self.tableWidget.horizontalHeaderItem(1).setTextAlignment(Qt.AlignLeft)
        self.tableWidget.horizontalHeaderItem(2).setTextAlignment(Qt.AlignLeft)

        self.tableWidget.setColumnHidden(3, True)
        self.pushButton.clicked.connect(self.prepare_routes)

        self.routes_for_download = []

        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(0)

        self.show()

    @pyqtSlot(int)
    def choose_range(self, row):
        ranges_model = self.MountainRanges.model()
        it = ranges_model.item(row)
        id = it.data()

        mountain_areas = self.connection.get_mountain_regions(id)

        self.current_mountai_range = id

        model = QtGui.QStandardItemModel()
        for area in mountain_areas:
            it = NaturalStandardItem(area['name'])
            it.setData(area['id'])
            model.appendRow(it)
        model.sort(0)
        self.MountainAreas.setModel(model)

    @pyqtSlot(int)
    def choose_area(self, row):
        ranges_model = self.MountainAreas.model()
        it = ranges_model.item(row)
        id = it.data()

        self.current_mountai_region = id
        summits = self.connection.get_region_summits(id)

        while self.tableWidget.rowCount() > 0:
            self.tableWidget.removeRow(0)

        for i, summit in enumerate(summits):
            self.tableWidget.insertRow(i)

            check_box = QCheckBox()
            checkBoxWidget = QWidget()
            layoutCheckBox = QHBoxLayout(checkBoxWidget)
            layoutCheckBox.addWidget(check_box)
            layoutCheckBox.setAlignment(Qt.AlignCenter)
            layoutCheckBox.setContentsMargins(0, 0, 0, 0)

            self.tableWidget.setCellWidget(i, 0, checkBoxWidget)

            name_widget = QTableWidgetFixedItem(str(summit['name']))
            name_widget.setTextAlignment(Qt.AlignLeft)
            self.tableWidget.setItem(i, 1, name_widget)

            height_widget = QTableWidgetFixedItem(str(summit['height']))
            height_widget.setTextAlignment(Qt.AlignCenter)
            self.tableWidget.setItem(i, 2, height_widget)

            id_widget = QTableWidgetFixedItem(str(summit['id']))
            self.tableWidget.setItem(i, 3, id_widget)

    def prepare_routes(self):
        self.routes_for_download.clear()
        self.progressBar.setValue(0)

        # If we stop downloading
        if self.th_lock.locked():
            try:
                self.th_lock.release()
            except:
                pass
            self.pushButton.setText('Скачать')
        # if we start downloading
        else:
            self.pushButton.setText('Отмена')
            self.th = Thread(target=self.download)
            self.th.start()

    def download(self):
        self.th_lock.acquire()
        for i in range(self.tableWidget.rowCount()):
            #  stop downloading
            if not self.th_lock.locked():
                break

            checkbox_widget = self.tableWidget.cellWidget(i, 0)
            if checkbox_widget.findChild(type(QCheckBox())).isChecked():
                id_item = self.tableWidget.item(i, 3)
                id = id_item.text()
                routes = self.connection.get_routes(region_id=self.current_mountai_range,
                                                    area_id=self.current_mountai_region,
                                                    mountain_id=id)

                self.routes_for_download.extend(routes)
        self.progressBar.setMaximum(len(self.routes_for_download))

        for i, route in enumerate(self.routes_for_download):
            #  stop downloading
            if not self.th_lock.locked():
                break

            # Path to route directory
            route_location = jmespath.search('"0".mountain_peaks[0].[mountain_region_name, mountain_area_name, name, height]', route)
            path_parts = route_location[:2 + 1]
            path_parts[-1] += " " + str(route_location[3])

            # Route name
            complexity = jmespath.search('"0".mountain_route_complexity.name', route)
            route_type = jmespath.search('"0".mountain_route_type.name', route)
            route_name = jmespath.search('"0".name', route)
            route_name = f"{complexity} {route_name} {route_type}"
            route_name = re.sub('[\<\>\:"\/\\\|\?\*]', ' ', route_name)

            path = os.path.join('.', 'downloads', *path_parts, route_name)
            path = os.path.abspath(path)

            import pathlib
            pathlib.Path(path).mkdir(parents=True, exist_ok=True)

            route_documents = jmespath.search('"0".documents_files[*]', route)
            for document in route_documents:
                self.connection.get_description_file(file_id=document['id'], path=path, filename=document['original_name'])
                # TODO add description .txt file
            self.progressBar.setValue(i + 1)

        try:
            self.th_lock.release()
        except:
            pass
        self.pushButton.setText('Скачать')

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def closeEvent(self, event):
        try:
            self.th_lock.release()
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    sys.exit(app.exec_())

