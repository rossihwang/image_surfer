import json
import pickle
from pathlib import Path

import faiss
import numpy as np
import torch
from PIL import Image
from PySide6.QtCore import QObject, Signal


_MODEL = None
_PREPROCESS = None
_TOKENIZER = None
_DEVICE = None


def _load_model():
    global _MODEL, _PREPROCESS, _TOKENIZER, _DEVICE
    if _MODEL is not None:
        return _MODEL, _PREPROCESS, _DEVICE, _TOKENIZER

    import open_clip

    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        "MobileCLIP2-S0", pretrained="dfndr2b"
    )
    model = model.to(_DEVICE)
    model.eval()
    _TOKENIZER = open_clip.get_tokenizer("MobileCLIP2-S0")

    _MODEL = model
    _PREPROCESS = preprocess
    return _MODEL, _PREPROCESS, _DEVICE, _TOKENIZER


class IndexWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(str, str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def build_index(self, directory: str, image_files: list):
        self._cancelled = False
        cache_dir = Path(directory) / ".imagesurfer"
        cache_dir.mkdir(parents=True, exist_ok=True)

        total = len(image_files)
        if total == 0:
            self.error.emit("No image files found")
            return

        try:
            model, preprocess, device, _ = _load_model()
        except Exception as e:
            self.error.emit(f"Failed to load model: {e}")
            return

        embeddings = []
        valid_paths = []

        for i, img_path in enumerate(image_files):
            if self._cancelled:
                return

            if i % 10 == 0:
                self.progress.emit(i, total, Path(img_path).name)

            try:
                image = preprocess(Image.open(img_path).convert("RGB")).unsqueeze(0).to(device)
                with torch.no_grad():
                    emb = model.encode_image(image)
                    emb /= emb.norm(dim=-1, keepdim=True)
                embeddings.append(emb.cpu().numpy()[0])
                valid_paths.append(img_path)
            except Exception:
                continue

        if len(embeddings) == 0:
            self.error.emit("Could not generate embeddings for any image")
            return

        embeddings_np = np.array(embeddings).astype("float32")
        dimension = embeddings_np.shape[1]

        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings_np)

        index_path = str(cache_dir / "index.faiss")
        paths_path = str(cache_dir / "paths.pkl")
        meta_path = cache_dir / "meta.json"

        faiss.write_index(index, index_path)
        with open(paths_path, "wb") as f:
            pickle.dump(valid_paths, f)
        with open(meta_path, "w") as f:
            json.dump(
                {"image_count": len(valid_paths), "format": "MobileCLIP2-S0", "dim": dimension},
                f,
            )

        self.progress.emit(len(valid_paths), total, "Done")
        self.finished.emit(index_path, paths_path)