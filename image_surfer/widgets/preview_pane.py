from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

QUERY_THUMB_HEIGHT = 150
QUERY_LABEL_HEIGHT = 24
SEPARATOR_HEIGHT = 1
RESULT_LABEL_HEIGHT = 24
PADDING = 8


class PreviewPane(QWidget):
    MIN_ZOOM = 10
    MAX_ZOOM = 500
    ZOOM_STEP = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._zoom_percent: int | None = None
        self._query_pixmap: QPixmap | None = None
        self._result_name: str | None = None

        self._image_label = QLabel("No image selected")
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(
            "background-color: #1e1e1e; color: #888; font-size: 16px;"
        )

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(self._image_label)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll_area)

    @property
    def current_pixmap(self) -> QPixmap | None:
        return self._pixmap

    def set_pixmap(self, pixmap: QPixmap):
        self._query_pixmap = None
        self._result_name = None
        self._pixmap = pixmap
        self._zoom_percent = None
        self._update_display()

    def set_search_result(self, query_pixmap: QPixmap, result_pixmap: QPixmap, name: str):
        self._query_pixmap = query_pixmap
        self._result_name = name
        self._pixmap = result_pixmap
        self._zoom_percent = None
        self._pixmap = self._compose()
        self._update_display()

    def _compose(self) -> QPixmap:
        q_thumb = self._query_pixmap.scaled(
            self._pixmap.width(),
            QUERY_THUMB_HEIGHT,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        q_h = QUERY_LABEL_HEIGHT + q_thumb.height() + SEPARATOR_HEIGHT + RESULT_LABEL_HEIGHT
        total_w = max(q_thumb.width(), self._pixmap.width())
        total_h = q_h + self._pixmap.height() + PADDING

        pix = QPixmap(total_w, total_h)
        pix.fill(QColor("#1e1e1e"))

        painter = QPainter(pix)
        painter.setPen(Qt.white)
        painter.drawText(PADDING, QUERY_LABEL_HEIGHT - 6, "Query")
        painter.drawPixmap(0, QUERY_LABEL_HEIGHT, q_thumb)

        y = QUERY_LABEL_HEIGHT + q_thumb.height() + SEPARATOR_HEIGHT
        painter.drawText(PADDING, y + RESULT_LABEL_HEIGHT - 6, self._result_name)
        painter.drawPixmap(0, y + RESULT_LABEL_HEIGHT, self._pixmap)
        painter.end()

        return pix

    def _update_display(self):
        if self._pixmap is None or self._pixmap.isNull():
            self._image_label.setText("No image selected")
            self._image_label.setPixmap(QPixmap())
            return

        if self._zoom_percent is None:
            viewport_size = self._scroll_area.viewport().size()
            scaled = self._pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)
        else:
            factor = self._zoom_percent / 100.0
            scaled = self._pixmap.scaled(
                self._pixmap.size() * factor,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)

    def wheelEvent(self, event: QWheelEvent):
        if self._pixmap is None or self._pixmap.isNull():
            super().wheelEvent(event)
            return

        if self._zoom_percent is None:
            self._zoom_percent = 100

        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom_percent = min(self.MAX_ZOOM, self._zoom_percent + self.ZOOM_STEP)
        else:
            self._zoom_percent -= self.ZOOM_STEP
            if self._zoom_percent < self.MIN_ZOOM:
                self._zoom_percent = None
            self._zoom_percent = (
                max(self.MIN_ZOOM, self._zoom_percent) if self._zoom_percent else None
            )

        self._update_display()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_percent is None:
            self._update_display()