import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QSettings, Qt, QSortFilterProxyModel, QThread
from PySide6.QtGui import QAction, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_surfer.models.image_list_model import ImageListModel
from image_surfer.models.search_result_model import SearchResultModel
from image_surfer.workers.image_loader import ImageLoader
from image_surfer.workers.index_worker import IndexWorker
from image_surfer.workers.search_worker import SearchWorker
from image_surfer.widgets.preview_pane import PreviewPane


def _open_system_viewer(path: str):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        subprocess.Popen(["start", path], shell=True)
    else:
        subprocess.Popen(["xdg-open", path])


class _WrappingListView(QListView):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Down:
            m = self.model()
            idx = self.currentIndex()
            if idx.isValid() and m and idx.row() == m.rowCount() - 1 and m.rowCount() > 0:
                self.setCurrentIndex(m.index(0, 0))
                return
        elif event.key() == Qt.Key_Up:
            m = self.model()
            idx = self.currentIndex()
            if idx.isValid() and m and idx.row() == 0 and m.rowCount() > 0:
                self.setCurrentIndex(m.index(m.rowCount() - 1, 0))
                return
        super().keyPressEvent(event)


class _TextFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._allowed: set[str] | None = None

    def set_allowed(self, paths: list[str] | None):
        self._allowed = set(paths) if paths else None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if self._allowed is None:
            return True
        m = self.sourceModel()
        if hasattr(m, "file_at"):
            p = m.file_at(source_row)
            return str(p) in self._allowed if p else False
        return True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Surfer")
        self.resize(1200, 800)

        self._current_directory: Path | None = None
        self._current_seq = 0
        self._index_thread: QThread | None = None
        self._index_worker: IndexWorker | None = None
        self._search_thread: QThread | None = None
        self._search_worker: SearchWorker | None = None
        self._query_pixmap: QPixmap | None = None
        self._query_path: str | None = None
        self._settings = QSettings("ImageSurfer", "ImageSurfer")

        self._model = ImageListModel()
        self._proxy = _TextFilterProxy()
        self._proxy.setSourceModel(self._model)

        self._list_view = QListView()
        self._list_view.setModel(self._proxy)
        self._list_view.setSelectionMode(QListView.SingleSelection)
        self._list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list_view.customContextMenuRequested.connect(self._show_context_menu)
        self._list_view.selectionModel().currentChanged.connect(self._on_selection_changed)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search images by text\u2026")
        self._search_input.returnPressed.connect(self._on_search_return)

        self._search_input.installEventFilter(self)

        search_clear_btn = QToolButton()
        search_clear_btn.setText("\u00d7")
        search_clear_btn.setStyleSheet("border: none; padding: 2px 6px;")
        search_clear_btn.clicked.connect(self._clear_text_search)

        search_bar = QWidget()
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(4, 0, 4, 0)
        search_layout.addWidget(self._search_input)
        search_layout.addWidget(search_clear_btn)

        refresh_btn = QToolButton()
        refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh_btn.setIconSize(refresh_btn.icon().actualSize(refresh_btn.iconSize()))
        refresh_btn.clicked.connect(self._refresh)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._list_view)
        left_layout.addWidget(search_bar)
        left_layout.addWidget(refresh_btn)

        self._result_model = SearchResultModel()

        self._result_view = _WrappingListView()
        self._result_view.setModel(self._result_model)
        self._result_view.setSelectionMode(QListView.SingleSelection)
        self._result_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._result_view.customContextMenuRequested.connect(self._show_result_context_menu)
        self._result_view.selectionModel().currentChanged.connect(self._on_result_selection_changed)

        close_btn = QToolButton()
        close_btn.setText("\u00d7 Close Results")
        close_btn.setStyleSheet("border: none; text-align: left; padding: 4px 8px;")
        close_btn.clicked.connect(self._close_results)

        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(0)
        result_layout.addWidget(close_btn)
        result_layout.addWidget(self._result_view)
        result_panel.setVisible(False)

        self._preview = PreviewPane()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(result_panel)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 5)

        self.setCentralWidget(splitter)
        self._splitter = splitter

        self._status_bar = QStatusBar()
        self._index_status_label = QLabel()
        self._status_bar.addPermanentWidget(self._index_status_label)
        self.setStatusBar(self._status_bar)

        self._setup_toolbar()

        self._loader = ImageLoader()
        self._loader.image_loaded.connect(self._on_image_loaded)

        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self._open_folder)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        index_action = QAction("Build Index", self)
        index_action.triggered.connect(self._build_index)
        toolbar.addAction(index_action)

        toolbar.addSeparator()

        help_action = QAction("Help", self)
        help_action.triggered.connect(self._show_help)
        toolbar.addAction(help_action)

        self.addToolBar(toolbar)

    def _source_path(self, proxy_index: QModelIndex) -> Path | None:
        if not proxy_index.isValid():
            return None
        src = self._proxy.mapToSource(proxy_index)
        return self._model.file_at(src.row())

    def _open_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Open Image Folder")
        if dir_path:
            self._current_directory = Path(dir_path)
            self._model.load_directory(self._current_directory)
            self._update_index_status()
            self._close_results()
            self._clear_text_search()
            if self._model.rowCount() > 0:
                self._list_view.setCurrentIndex(self._proxy.index(0, 0))

    def _refresh(self):
        if self._current_directory:
            self._model.load_directory(self._current_directory)
            self._update_index_status()

    def _on_search_return(self):
        text = self._search_input.text().strip()
        if not text:
            return
        if not self._current_directory:
            return

        cache_dir = self._current_directory / ".imagesurfer"
        if not (cache_dir / "index.faiss").exists():
            self._status_bar.showMessage("Index not found. Build index first.")
            return

        self._search_thread = QThread()
        self._search_worker = SearchWorker()
        self._search_worker.moveToThread(self._search_thread)

        self._search_worker.finished.connect(self._on_text_search_finished)
        self._search_worker.error.connect(self._on_search_error)
        self._search_thread.finished.connect(self._cleanup_search)

        self._search_thread.started.connect(
            lambda: self._search_worker.text_search(
                str(self._current_directory), text, 50
            )
        )

        self._status_bar.showMessage("Searching\u2026")
        self._search_thread.start()

    def _clear_text_search(self):
        self._search_input.clear()
        self._proxy.set_allowed(None)

    def _build_index(self):
        if not self._current_directory:
            QMessageBox.warning(self, "No Folder", "Open a folder first")
            return

        total = self._model.rowCount()
        if total == 0:
            QMessageBox.warning(self, "No Images", "No image files in this folder")
            return

        cache_dir = self._current_directory / ".imagesurfer"
        if (cache_dir / "index.faiss").exists() and (cache_dir / "meta.json").exists():
            with open(cache_dir / "meta.json") as f:
                meta = json.load(f)
            if meta.get("image_count") == total:
                self._status_bar.showMessage(f"Index ready ({total} images)")
                return

        self._progress = QProgressDialog("Building index...", "Cancel", 0, total, self)
        self._progress.setWindowTitle("Indexing")
        self._progress.setWindowModality(Qt.WindowModal)

        self._index_thread = QThread()
        self._index_worker = IndexWorker()
        self._index_worker.moveToThread(self._index_thread)

        self._index_worker.progress.connect(self._on_index_progress)
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.error.connect(self._on_index_error)
        self._index_thread.finished.connect(self._cleanup_index)
        self._progress.canceled.connect(self._cancel_index)

        self._index_thread.started.connect(
            lambda: self._index_worker.build_index(
                str(self._current_directory),
                [str(self._model.file_at(i)) for i in range(total)],
            )
        )

        self._index_thread.start()
        self._progress.exec()

    def _on_index_progress(self, current: int, total: int, filename: str):
        self._progress.setLabelText(f"[{current}/{total}] {filename}")
        self._progress.setValue(current)

    def _on_index_finished(self, index_path: str, paths_path: str):
        self._progress.close()
        self._update_index_status()
        self._status_bar.showMessage(f"Index ready \u2014 {Path(index_path).parent.name}")

    def _on_index_error(self, msg: str):
        self._progress.close()
        self._update_index_status()
        self._status_bar.showMessage(f"Index failed: {msg}")

    def _cancel_index(self):
        if self._index_worker:
            self._index_worker.cancel()
        self._index_thread.quit()
        self._progress.close()

    def _cleanup_index(self):
        self._index_thread.wait()
        self._index_thread.deleteLater()
        self._index_worker.deleteLater()
        self._index_thread = None
        self._index_worker = None

    def _show_help(self):
        QMessageBox.information(
            self,
            "Help",
            "Image Surfer\n\n"
            "\u2022 Arrow keys to navigate images\n"
            "\u2022 Scroll wheel to zoom in/out\n"
            "\u2022 Right-click to open with system viewer\n"
            "\u2022 Right-click \u2192 Find Similar for image search\n"
            "\u2022 Type in the search bar \u2192 Enter for text search\n"
            "\u2022 File > Open to browse images",
        )

    def _show_context_menu(self, pos):
        index = self._list_view.indexAt(pos)
        if not index.isValid():
            return
        file_path = self._source_path(index)
        if not file_path:
            return

        cache_dir = (self._current_directory / ".imagesurfer") if self._current_directory else None
        index_exists = cache_dir and (cache_dir / "index.faiss").exists()

        menu = QMenu(self)
        act_open = menu.addAction("Open with system viewer")

        if index_exists:
            menu.addSeparator()
            act_sim10 = menu.addAction("Find Similar 10")
            act_simN = menu.addAction("Find Similar N\u2026")

        action = menu.exec(self._list_view.viewport().mapToGlobal(pos))

        if action is None:
            return
        if action == act_open:
            _open_system_viewer(str(file_path))
        elif index_exists and action == act_sim10:
            self._start_search(str(file_path), 10)
        elif index_exists and action == act_simN:
            n, ok = QInputDialog.getInt(
                self, "Find Similar", "Number of results:", value=10, minValue=1, maxValue=100
            )
            if ok:
                self._start_search(str(file_path), n)

    def _show_result_context_menu(self, pos):
        index = self._result_view.indexAt(pos)
        if not index.isValid():
            return
        file_path = self._result_model.file_at(index.row())
        if not file_path:
            return

        menu = QMenu(self)
        menu.addAction("Open with system viewer")
        action = menu.exec(self._result_view.viewport().mapToGlobal(pos))
        if action and action.text() == "Open with system viewer":
            _open_system_viewer(str(file_path))

    def _start_search(self, query_path: str, n: int):
        if not self._current_directory:
            return

        self._query_path = query_path
        self._query_pixmap = self._preview.current_pixmap

        self._search_thread = QThread()
        self._search_worker = SearchWorker()
        self._search_worker.moveToThread(self._search_thread)

        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.error.connect(self._on_search_error)
        self._search_thread.finished.connect(self._cleanup_search)

        self._search_thread.started.connect(
            lambda: self._search_worker.search(
                str(self._current_directory), query_path, n
            )
        )

        self._status_bar.showMessage("Searching\u2026")
        self._search_thread.start()

    def _on_search_finished(self, results: list[tuple[float, str]]):
        self._search_thread.quit()
        self._result_model.set_results(results)
        self._result_view.parent().setVisible(True)
        self._splitter.setSizes([250, 250, max(400, self._splitter.width() - 500)])
        self._status_bar.showMessage(f"Found {len(results)} similar images")

    def _on_search_error(self, msg: str):
        self._search_thread.quit()
        self._status_bar.showMessage(f"Search failed: {msg}")

    def _on_text_search_finished(self, results):
        self._search_thread.quit()
        paths = [p for _, p in results]
        self._proxy.set_allowed(paths)
        self._status_bar.showMessage(
            f"Text search: {len(results)} results \u2014 ESC to clear"
        )
        if self._proxy.rowCount() > 0:
            self._list_view.setCurrentIndex(self._proxy.index(0, 0))

    def _cleanup_search(self):
        self._search_thread.wait()
        self._search_thread.deleteLater()
        self._search_worker.deleteLater()
        self._search_thread = None
        self._search_worker = None

    def _close_results(self):
        self._result_model.clear()
        self._result_view.parent().setVisible(False)
        self._query_pixmap = None
        self._query_path = None

    def _on_result_selection_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            return
        file_path = self._result_model.file_at(current.row())
        if file_path:
            self._current_seq += 1
            self._loader.load(str(file_path), self._current_seq)

    def _on_selection_changed(self, current: QModelIndex, previous: QModelIndex):
        self._close_results()
        if not current.isValid():
            return
        file_path = self._source_path(current)
        if file_path:
            self._current_seq += 1
            self._loader.load(str(file_path), self._current_seq)
            self._update_status(current)

    def _on_image_loaded(self, pixmap, path, seq):
        if seq != self._current_seq:
            return
        if self._query_pixmap is not None and self._query_path is not None and path != self._query_path:
            self._preview.set_search_result(self._query_pixmap, pixmap, Path(path).name)
        else:
            self._preview.set_pixmap(pixmap)

    def _update_index_status(self):
        if not self._current_directory:
            self._index_status_label.setText("No folder")
            return
        cache_dir = self._current_directory / ".imagesurfer"
        meta_path = cache_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            if meta.get("image_count") == self._model.rowCount():
                self._index_status_label.setText(
                    '<span style="color:green;font-weight:bold;">\u2713 Indexed</span>'
                )
                return
        self._index_status_label.setText(
            '<span style="color:#cc6600;font-weight:bold;">\u2717 Not indexed</span>'
        )

    def _update_status(self, proxy_index: QModelIndex):
        total = self._model.rowCount()
        file_path = self._source_path(proxy_index)
        if file_path:
            self._status_bar.showMessage(
                f"{proxy_index.row() + 1} / {total} \u2014 {file_path.name}"
            )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Down:
            self._navigate(1)
        elif event.key() == Qt.Key_Up:
            self._navigate(-1)
        else:
            super().keyPressEvent(event)

    def _navigate(self, delta: int):
        current = self._list_view.currentIndex()
        if not current.isValid():
            return
        new_row = current.row() + delta
        if 0 <= new_row < self._proxy.rowCount():
            self._list_view.setCurrentIndex(self._proxy.index(new_row, 0))

    def eventFilter(self, obj, event):
        if obj is self._search_input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._clear_text_search()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self._settings.setValue("geometry", self.saveGeometry())
        self._loader.shutdown()
        super().closeEvent(event)