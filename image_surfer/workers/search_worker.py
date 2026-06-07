import pickle
from pathlib import Path

import faiss
import torch
from PIL import Image
from PySide6.QtCore import QObject, Signal

from image_surfer.workers.index_worker import _load_model


class SearchWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def search(self, directory: str, query_path: str, n: int):
        self._cancelled = False
        cache_dir = Path(directory) / ".imagesurfer"
        index_path = cache_dir / "index.faiss"
        paths_path = cache_dir / "paths.pkl"

        if not index_path.exists() or not paths_path.exists():
            self.error.emit("Index not found. Build index first.")
            return

        index = faiss.read_index(str(index_path))
        with open(paths_path, "rb") as f:
            all_paths: list[str] = pickle.load(f)

        if self._cancelled:
            return

        try:
            model, preprocess, device = _load_model()
        except Exception as e:
            self.error.emit(f"Failed to load model: {e}")
            return

        try:
            image = preprocess(Image.open(query_path).convert("RGB")).unsqueeze(0).to(device)
            with torch.no_grad():
                emb = model.encode_image(image)
                emb /= emb.norm(dim=-1, keepdim=True)
            query_vec = emb.cpu().numpy().astype("float32")
        except Exception as e:
            self.error.emit(f"Failed to encode query image: {e}")
            return

        if self._cancelled:
            return

        n_search = min(n + 1, len(all_paths))
        scores, indices = index.search(query_vec, n_search)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            path = all_paths[idx]
            if path == query_path:
                continue
            results.append((float(score), path))
            if len(results) >= n:
                break

        if self._cancelled:
            return

        self.finished.emit(results)