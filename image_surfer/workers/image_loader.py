from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImageReader, QPixmap


class ImageLoader(QObject):
    load_requested = Signal(str, int)
    image_loaded = Signal(object, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self.moveToThread(self._thread)
        self.load_requested.connect(self._do_load)
        self._thread.start()

    def load(self, path: str, seq: int):
        self.load_requested.emit(path, seq)

    def _do_load(self, path: str, seq: int):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        self.image_loaded.emit(pixmap, path, seq)

    def shutdown(self):
        self._thread.quit()
        self._thread.wait()