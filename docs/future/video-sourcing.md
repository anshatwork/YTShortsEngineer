# Future Spec — Unified Video Sourcing

> Status: **Design only.** Not implemented. This document proposes an abstraction; it
> does not describe current behaviour. See `docs/claude/tools.md` for what exists today.

## Problem

Video/asset acquisition is currently scattered:

- `tools/youtube/` (downloader, search, transcript) is YouTube-specific.
- `tools/assets/sources/` implements the *music* source pattern (Pixabay, Freesound,
  Jamendo, YouTube) behind a registry, but there is no equivalent for **video** B-roll /
  stock footage.
- The long-form clipping pipeline assumes a single local `source_video_path`.

As we add stock providers (Pexels, Pixabay video), local folders, Google Drive, and S3,
we need one abstraction so nodes can request footage by *intent* without knowing the
provider. The music-sourcing layer (`tools/assets/`) is the proven template to mirror.

## Goals

- One `VideoSource` protocol covering search, fetch, and metadata for any provider.
- Normalized metadata (`VideoAsset`) regardless of origin.
- Provider-agnostic **ranking** by relevance + quality + license.
- **Deduplication** across providers (perceptual hash + embedding).
- **Caching** through the existing content-addressable store (`core/cache`).
- Opt-in **embeddings** for semantic retrieval (shared with `gallery-agent.md`).

## Non-goals

- Editing/transformation (owned by `tools/video_editing/`).
- The VLM analysis of fetched clips (see `vlm-agent.md`).
- Replacing the music sourcing layer — this parallels it.

## Proposed architecture

Mirror `tools/assets/` structure under `tools/video_sources/`:

```
tools/video_sources/
  base.py          # VideoSource protocol + VideoQuery/VideoAsset models
  registry.py      # name -> factory, env-driven enable/disable (mirror assets/registry.py)
  retrieval.py     # multi-source fan-out + ranking + dedup
  store.py         # metadata index over core/cache CAS
  sources/
    youtube.py     # wraps existing tools/youtube/
    pexels.py
    pixabay_video.py
    local_folder.py
    gdrive.py
    s3.py
```

### Core interfaces

```python
class VideoQuery(TypedDict, total=False):
    text: str                    # natural-language intent, e.g. "aerial city at night"
    duration_range: tuple[float, float]
    orientation: Literal["portrait", "landscape", "square"]
    min_resolution: tuple[int, int]
    license: Literal["any", "cc", "commercial"]
    top_k: int

class VideoAsset(TypedDict):
    asset_id: str                # content hash (CAS key) once fetched
    source: str                  # "pexels" | "youtube" | "local" | ...
    source_id: str               # provider-native id
    url: Optional[str]
    local_path: Optional[str]    # populated after fetch()
    title: str
    duration: float
    width: int
    height: int
    fps: Optional[float]
    license: str
    attribution: Optional[str]
    tags: list[str]
    phash: Optional[str]         # perceptual hash for dedup
    embedding: Optional[list[float]]  # CLIP embedding for semantic rank/dedup

class VideoSource(Protocol):
    name: str
    def is_enabled(self) -> bool: ...          # env-gated, mirror music sources
    def search(self, q: VideoQuery) -> list[VideoAsset]: ...
    def fetch(self, asset: VideoAsset) -> VideoAsset: ...  # download → CAS, set local_path
```

### Ranking

`retrieval.rank(query, candidates)` combines:

1. **Relevance** — cosine similarity of query embedding vs asset embedding (or tag
   overlap fallback when embeddings are off).
2. **Quality** — resolution, fps, bitrate normalized to [0,1].
3. **License fit** — hard filter first, then a small preference weight.
4. **Freshness / popularity** — provider signal when available.

Weights live in `core/config.py` so they are tunable without code changes.

### Deduplication

Two-stage, cheapest first:
1. **Exact**: CAS content hash (identical downloads collapse for free).
2. **Near-dup**: perceptual hash (pHash) Hamming distance below a threshold, then
   CLIP-embedding cosine as a tiebreak. Keep the highest-quality/most-permissive copy.

### Caching

Reuse `core/cache` (CAS + index). `fetch()` stores bytes under their content hash and
records normalized metadata in `store.py`'s index. This is exactly how music tracks are
cached today (`tools/assets/store.py`), so serving/eviction semantics carry over.

## Integration points

- **New LangGraph node** `source_broll_node` (long-to-shorts) that, given a clip's
  intent, calls `retrieval.search()` and attaches ranked `VideoAsset`s to state.
- The legacy shorts graph's `fetch_assets`/`select_video` can be reimplemented on top of
  this instead of calling `tools/youtube_api` directly.
- Embeddings shared with `gallery-agent.md` (same CLIP model + vector index).

## Phased plan

1. **P1** — `base.py` + `registry.py` + `youtube.py` (wrap existing) + `local_folder.py`.
   No embeddings; tag-overlap ranking; exact-hash dedup only.
2. **P2** — Add Pexels + Pixabay video; CAS caching + metadata index.
3. **P3** — CLIP embeddings, semantic ranking, pHash near-dup.
4. **P4** — Drive/S3 sources; shared vector index with the gallery agent.

## Open questions

- Vector index backend: reuse Supabase `pgvector` (already a Supabase shop) vs a local
  FAISS/Chroma sidecar? Recommend `pgvector` to avoid new infra.
- Do we normalize all footage to a canonical codec on fetch, or lazily at edit time?
  Lazy is cheaper and keeps the CAS provider-faithful.
