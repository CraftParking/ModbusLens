from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class MonitoringResultsWindow(QMainWindow):
    """Detached Excel-style view for live monitoring results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Monitoring Results")
        self.resize(1100, 560)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)

        actions_layout = QHBoxLayout()
        self.write_selected_btn = QPushButton("Write Selected")
        self.write_selected_btn.clicked.connect(parent._write_results_window_selected)
        actions_layout.addWidget(self.write_selected_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Tag Name", "Mode", "Type", "Address", "Read Value", "Write Value", "Comment", "Timestamp"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                color: #000000;
                gridline-color: #D0D0D0;
                border: 1px solid #CCCCCC;
            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 6px;
                font-weight: bold;
            }
        """)

        layout.addWidget(self.table)
        self.setCentralWidget(central_widget)

    def update_row(self, tag_name, mode, data_type, address, read_value="", write_value="", comment="", timestamp=""): 
        row = self._find_row(tag_name, data_type, address) 
        if row is None: 
            row = self.table.rowCount() 
            self.table.insertRow(row) 

        # If the user is actively typing in the Write Value cell, do not refresh the row.
        # Refreshing (setItem) cancels the editor and clears in-progress edits.
        if (
            self.table.state() == QAbstractItemView.EditingState
            and self.table.currentRow() == row
            and self.table.currentColumn() == 5
        ):
            return 
 
        current_write_item = self.table.item(row, 5) 
        current_write_value = current_write_item.text() if current_write_item else "" 
        if current_write_value and not write_value: 
            write_value = current_write_value 

        current_read_item = self.table.item(row, 4)
        current_read_value = current_read_item.text() if current_read_item else ""
        if current_read_value and not read_value:
            read_value = current_read_value

        can_write = mode == "Write"
        values_by_column = {
            0: tag_name,
            1: mode,
            2: data_type,
            3: str(address),
            4: read_value,
            5: write_value,
            6: comment,
            7: timestamp,
        }

        for column in range(8):
            if column == 5 and can_write:
                # Don't overwrite user's typed value with empty polling updates.
                if not values_by_column[5] and self.table.item(row, 5) is not None:
                    existing_item = self.table.item(row, 5)
                    existing_item.setFlags(existing_item.flags() | Qt.ItemIsEditable)
                    continue

            item = QTableWidgetItem(values_by_column[column])
            if column != 5 or not can_write:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column == 5 and not can_write:
                item.setBackground(QColor("#F0F0F0"))
                item.setForeground(QColor("#777777"))
            self.table.setItem(row, column, item)

    def clear(self):
        self.table.setRowCount(0)

    def current_values(self):
        values = {}
        for row in range(self.table.rowCount()):
            key = (self._item_text(row, 0), self._item_text(row, 2), self._item_text(row, 3))
            values[key] = {
                "read_value": self._item_text(row, 4),
                "write_value": self._item_text(row, 5),
                "timestamp": self._item_text(row, 7),
            }
        return values

    def selected_write_rows(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row not in rows:
            rows.append(current_row)

        selected = []
        for row in rows:
            mode = self._item_text(row, 1)
            if mode != "Write":
                continue
            selected.append({
                "row": row,
                "name": self._item_text(row, 0),
                "type": self._item_text(row, 2),
                "address": int(self._item_text(row, 3)),
                "write_value": self._item_text(row, 5),
            })
        return selected

    def _find_row(self, tag_name, data_type, address):
        for row in range(self.table.rowCount()):
            if (self._item_text(row, 0) == tag_name and
                self._item_text(row, 2) == data_type and
                self._item_text(row, 3) == str(address)):
                return row
        return None

    def _item_text(self, row, column):
        item = self.table.item(row, column)
        return item.text() if item else ""
