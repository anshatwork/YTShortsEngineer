# Future Spec — Training / Learning Agent

> Status: **Design only.** Not implemented.

## Problem

The pipeline currently turns long-form video into short clips. The same transcript +
analysis is a rich source for **educational artifacts**: chapters, summaries, quizzes,
flashcards, and learning objectives. This agent repurposes existing analysis (transcript,
`timed_transcript`, hook segments) into a study pack — a distinct product surface with no
video rendering.

## Goals

From a long-form video + transcript, generate:

- **Chapters** — titled, timestamped sections (navigable).
- **Summary** — layered (TL;DR, section summaries, full outline).
- **Quiz** — MCQ + short-answer with answer keys, difficulty tags.
- **Flashcards** — Q/A pairs (Anki-exportable).
- **Learning objectives** — Bloom's-taxonomy-aligned outcomes.

## Non-goals

- Video editing/rendering.
- Grading student responses (a later interactive layer).

## Proposed architecture

A standalone LangGraph sub-graph mirroring `agents/long_to_shorts/`:

```
agents/training/
  graph.py                 # StateGraph(TrainingState)
  chapterize_node.py       # transcript → timestamped chapters
  summarize_node.py        # layered summaries (map-reduce over chapters)
  objectives_node.py       # learning objectives per chapter
  quiz_node.py             # MCQ + short-answer from chapters
  flashcards_node.py       # Q/A pairs
  state.py                 # TrainingState (TypedDict, total=False)
```

Topology (linear, fan-out where safe):
`START → chapterize → summarize → objectives → (quiz ∥ flashcards) → END`

Each node uses `tools.llm.get_llm()` + `llm.parse(prompt, Schema, system=...)` for
structured output, and `cached_llm_text`-style caching (`core/cache`) keyed on
`(transcript_hash, node, model, version)` — same pattern as `analyze_video_node`.

### State (sketch)

```python
class Chapter(TypedDict):
    index: int; title: str; start: float; end: float; summary: str

class QuizItem(TypedDict):
    kind: Literal["mcq","short"]; question: str
    choices: Optional[list[str]]; answer: str; difficulty: str; chapter_index: int

class Flashcard(TypedDict):
    front: str; back: str; chapter_index: int

class TrainingState(TypedDict, total=False):
    source_video_path: str
    transcript: str
    timed_transcript: Optional[list[dict]]
    chapters: list[Chapter]
    tldr: str; outline: str
    objectives: list[str]
    quiz: list[QuizItem]
    flashcards: list[Flashcard]
    current_step: str; error: Optional[str]
```

### Chapterization

Prefer `timed_transcript` for real timestamps (as `subtitles_node` does); fall back to
char-offset chunking (`analyze_video_node._chunk_from_text` pattern). Chapter boundaries
from topic-shift detection in the LLM prompt; validate monotonic, non-overlapping ranges.

## Integration points

- Reuses transcript acquisition (`tools/youtube/transcript.py`) and the same caching/LLM
  plumbing — no new provider work.
- New REST surface `/api/v1/training` following the router pattern; a runner mirroring
  `api/runner.py` (task queue + SSE progress).
- Credits: add a per-artifact credit cost in `credits.py`.
- Exports: Anki `.apkg` (flashcards), Markdown/PDF (summary + quiz).

## Phased plan

1. **P1** — `chapterize` + `summarize` nodes; CLI runner; cached.
2. **P2** — `objectives` + `quiz` + `flashcards`; `TrainingState`; graph.
3. **P3** — `/api/v1/training` + SSE + credits; Anki/Markdown export.
4. **P4** — Quality gating via `llm-judge.md`; personalization via `memory-system.md`.

## Open questions

- Quiz answer verifiability — ground answers with transcript citations to reduce
  hallucination; have `llm-judge` verify answer-key correctness.
- Long videos exceed context — map-reduce per chapter, then a reduce pass for global
  outline/objectives.
