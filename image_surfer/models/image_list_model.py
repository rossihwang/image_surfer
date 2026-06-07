from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QImageReader


SUPPORTED_FORMATS = {fmt.data().decode() for fmt in QImageReader.supportedImageFormats()}


def _is_image_file(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in SUPPORTED_FORMATS


class ImageListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[Path] = []

    def load_directory(self, directory: Path):
        self.beginResetModel()
        self._files = sorted(
            [p for p in directory.iterdir() if p.is_file() and _is_image_file(p)],
            key=lambda p: p.name.lower(),
        )
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._files)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._files):
            return None
        if role == Qt.DisplayRole:
            return self._files[index.row()].name
        return None

    def file_at(self, row: int) -> Path | None:
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def file_paths(self) -> list[str]:
        return [str(p) for p in self._files]