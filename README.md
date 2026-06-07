# Image Surfer

Image preview and search tool with CLIP-based semantic search. Browse image folders, build FAISS indexes with MobileCLIP2-S0 embeddings, find similar images by example or natural language.

## Features

- **Image preview** — Browse image folders with arrow-key navigation, scroll-wheel zoom (10%–500%), fit-to-window display
- **FAISS index** — Build a cosine-similarity index with MobileCLIP2-S0 embeddings; index is cached locally per folder
- **Find Similar** — Right-click any image → "Find Similar 10" or "Find Similar N…" to search the index by image similarity
- **Text search** — Type a description in the search bar → Enter to filter the image list by semantic content (top 50 matches)

## Requirements

- Python ≥ 3.10
- PySide6 ≥ 6.5
- open_clip_torch
- faiss-cpu ≥ 1.10
- torch ≥ 2.0 (CUDA or CPU), huggingface_hub

Model weights are auto-downloaded from Hugging Face on first index build.

## Installation

```bash
pip install PySide6 open_clip_torch faiss-cpu
```

Or with a conda environment:

```bash
conda create -n image_surfer python=3.10
conda activate image_surfer
pip install PySide6 open_clip_torch faiss-cpu
```

## Usage

```bash
python -m image_surfer.main
```

1. **Open a folder** — `Open` and select a directory with images
2. **Build index** — Click `Build Index` (required for search features)
3. **Browse** — Arrow keys to navigate, scroll wheel to zoom, right-click → "Open with system viewer"
4. **Image search** — Right-click any image → Find Similar 10 / Find Similar N…
5. **Text search** — Type in the search bar below the image list → Enter to filter results; ESC or × to clear

> If behind a firewall, set a proxy before the first run for model download

## Project layout

```
image_surfer/
  main.py              # Entry point
  widgets/             # MainWindow, PreviewPane
  models/              # ImageListModel, SearchResultModel
  workers/             # ImageLoader, IndexWorker, SearchWorker
```

## Lint

```bash
ruff check image_surfer/
```