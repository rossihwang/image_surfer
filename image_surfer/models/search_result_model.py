from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class SearchResultModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[tuple[float, str]] = []

    def set_results(self, results: list[tuple[float, str]]):
        self.beginResetModel()
        self._results = results
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._results)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._results):
            return None
        score, path = self._results[index.row()]
        if role == Qt.DisplayRole:
            return f"#{index.row() + 1}  {Path(path).name}  ({score:.3f})"
        if role == Qt.UserRole:
            return path
        return None

    def file_at(self, row: int) -> str | None:
        if 0 <= row < len(self._results):
            return self._results[row][1]
        return None

    def clear(self):
        self.beginResetModel()
        self._results.clear()
        self.endResetModel()