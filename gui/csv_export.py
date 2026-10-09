"""Shared "Export CSV..." helper for the scanner result views."""
import csv
import time

from PySide6.QtWidgets import QFileDialog, QMessageBox


def export_rows_csv(parent, title, default_stem, header, rows, log=None):
    """Ask for a file and write `header` + `rows` to it as CSV (UTF-8 with a BOM so
    Excel opens it correctly). Returns the path written, or None if cancelled/failed."""
    default_name = f"{default_stem}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    file_path, _ = QFileDialog.getSaveFileName(parent, title, default_name, "CSV Files (*.csv)")
    if not file_path:
        return None
    try:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    except OSError as e:
        QMessageBox.critical(parent, "Export Failed", f"Could not write {file_path}: {e}")
        return None
    if log is not None:
        log(f"Exported {len(rows)} row(s) to {file_path}")
    return file_path
