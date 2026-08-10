# Future Spec — Gallery Agent (Local Media Indexing)

> Status: **Design only.** Not implemented.

## Problem

Creators have large local libraries (uploads under `assets/uploads/`, downloaded footage
in `cache/cas/`). There is no way to search that library semantically ("find the clip of
the whiteboard drawing") or to reuse footage across jobs. We want a background agent that
indexes local media once and serves fast semantic + metadata search.

## Goals

- Index arbitrary local folders (and later Drive/S3 via `video-sourcing.md`).
- Extract: scene boundaries, keyframes, OCR text, CLIP embeddings, EXIF/technical metadata.
- Duplicate & near-duplicate detection.
- Semantic search ("query text → ranked local clips/segments").
- Incremental / idempotent: re-indexing only touches changed files.

## Non-goals

- Editing (owned by `tools/video_editing/`).
- High-level "what's interesting" scoring — that is the VLM agent (`vlm-agent.md`).

## Proposed architecture

```
agents/gallery/
  indexer.py       # walk folders → per-file pipeline → write to index
  scene_detect.py  # shot boundary detection (PySceneDetect or ffmpeg scene filter)
  keyframes.py     # extract representative frames per scene
  ocr.py           # text-in-frame extraction (see "OCR" below)
  embed.py         # CLIP image/text embeddings (shared with video-sourcing)
  dedup.py         # pHash + embedding near-dup
  search.py        # query → ranked MediaSegment[]
  store.py         # index persistence (pgvector)
```

Run as a **background task** on the existing task queue (`core/execution/taskqueue.py`),
the same mechanism that warms the music cache and trending pool in `api/app.py`'s
lifespan. A new `_gallery_index_loop` there would enqueue incremental scans.

### Data model

```python
class MediaSegment(TypedDict):
    segment_id: str          # f"{file_hash}:{scene_index}"
    file_path: str
    file_hash: str           # CAS-style content hash for change detection
    start: float
    end: float
    keyframe_path: str       # cached thumbnail
    ocr_text: str
    tags: list[str]
    embedding: list[float]   # CLIP
    phash: str
    width: int; height: int; fps: float
    indexed_at: str          # ISO8601
```

### Per-file pipeline

1. Hash file (skip if unchanged since last index — idempotency).
2. Scene detection → segment list.
3. Per scene: extract keyframe → CLIP embed + pHash + OCR.
4. Upsert `MediaSegment`s into the vector index.

### OCR options

- Start with `easyocr`/`tesseract` on keyframes only (cheap, offline).
- Later route keyframes through the VLM agent for OCR + captioning in one call.

### Search

`search(query_text, filters) -> list[MediaSegment]`:
- Embed query text (CLIP text encoder).
- Vector top-k over segment embeddings; optional metadata filters (duration, resolution,
  has-OCR-text).
- Blend in lexical match on `ocr_text` + `tags` for exact-term queries.

## Integration points

- Exposes a retrieval function usable by a `source_broll_node` and by the editor
  (`tools/editor_engine.py`) as a "local" source in the unified `video-sourcing` registry.
- Shares the CLIP model + `pgvector` index with `video-sourcing.md` and `vlm-agent.md`.
- New REST surface under `/api/v1/gallery` (search, reindex, stats) following the existing
  router pattern.

## Phased plan

1. **P1** — Indexer + scene detect + keyframes + pHash dedup; SQLite/JSON index.
2. **P2** — CLIP embeddings + pgvector semantic search + `/api/v1/gallery`.
3. **P3** — OCR + lexical/semantic blend.
4. **P4** — Background incremental loop; VLM-powered captioning.

## Open questions

- Scene-detection cost on large libraries — cap concurrency via the task queue worker count.
- Where do keyframes live? Reuse `core/cache` CAS to avoid a parallel store.
