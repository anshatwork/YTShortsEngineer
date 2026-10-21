# Future Spec — Vision-Language (VLM) Agent

> Status: **Design only.** Not implemented.

## Problem

The clipping pipeline scores hooks from the *transcript* only (`analyze_video_node`). It
is blind to what is on screen: it cannot tell a talking head from a demo, detect on-screen
text, or judge visual engagement. A VLM agent adds visual understanding so downstream
nodes (clip selection, thumbnails, top-text, editing suggestions) make better choices.

## Goals

- Frame/scene **captioning** and dense description.
- **OCR** of on-screen text (shared with the gallery agent).
- **Shot classification** (talking-head, screencast, b-roll, slide, action).
- **Engagement prediction** — a visual "watchability" score per segment.
- **Editing suggestions** — crop/reframe hints, punch-in moments, cut points.

## Non-goals

- Running the video edit (owned by `tools/video_editing/`).
- Being the only signal for clip selection — it augments transcript hook scoring.

## Proposed architecture

Model access goes through a **provider abstraction that mirrors `tools/llm/`**. Add
`tools/vlm/` with the same shape (base protocol + registry + per-provider adapters + BYOK):

```
tools/vlm/
  base.py          # VLMProvider protocol; VLMRequest/VLMResult models
  anthropic_vlm.py # Claude vision (default; Opus/Sonnet already used for text)
  openai_vlm.py    # optional
  local_vlm.py     # e.g. Qwen-VL / LLaVA via Ollama for offline/GPU-default
  registry.py      # provider selection (env + BYOK), mirror tools/llm/__init__.py
```

Reusing the LLM layer's conventions means the same credential/BYOK plumbing
(`tools/llm/credentials.py`, `tools/llm/byok.py`) and the same GPU-default + BYOK policy
from the SaaS plan apply. Default to **Claude vision** models for quality; allow a local
VLM for cost/offline.

### Interface

```python
class VLMRequest(TypedDict, total=False):
    frames: list[str]        # keyframe paths or timestamps to sample
    video_path: str
    tasks: list[Literal["caption","ocr","shot_class","engagement","edit_hints"]]
    context: Optional[str]   # transcript window for grounding

class ShotAnalysis(TypedDict):
    start: float; end: float
    caption: str
    ocr_text: str
    shot_type: str
    engagement: float        # 0..1
    edit_hints: list[str]

class VLMProvider(Protocol):
    name: str
    def analyze(self, req: VLMRequest) -> list[ShotAnalysis]: ...
```

### Frame sampling

Sample keyframes from scene boundaries (reuse `gallery-agent.scene_detect`) rather than
fixed intervals — fewer VLM calls, better coverage. Batch frames per request to control
cost. Cache results in `core/cache` keyed by `(file_hash, sampling_params, model)`.

## Integration points

- **New node** `vlm_analyze_node` in long-to-shorts, running after `analyze_video` and
  before `clipping_logic`. It writes `ShotAnalysis[]` onto state; `analyze_video`'s hook
  score is then blended with visual `engagement` for final clip ranking.
- `thumbnail_node` uses captions/OCR/shot_type to pick a stronger frame and prompt.
- `top_text_node` can avoid overlapping existing on-screen text (from OCR).
- Feeds the `llm-judge.md` evaluation pipeline with visual features.

## Phased plan

1. **P1** — `tools/vlm/base.py` + Claude-vision provider; captioning + OCR only; cached.
2. **P2** — Shot classification + engagement score; blend into clip ranking.
3. **P3** — Edit hints (reframe/punch-in/cut points) consumed by the editor.
4. **P4** — Local VLM provider for offline/GPU-default; BYOK.

## Open questions

- Cost governance: VLM calls are the most expensive per-job step — gate behind a feature
  flag + per-plan credit cost (see `credits.py`).
- Do engagement scores need a labeled dataset to calibrate, or is relative ranking enough?
  Start relative; calibrate later with `llm-judge` + real retention data.
