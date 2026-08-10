# Future Spec — LLM Judge (Evaluation Pipeline)

> Status: **Design only.** Not implemented. Builds on the ad-hoc comparison script
> `compare_llm_content.py` (repo root) and the provider abstraction in `tools/llm/`.

## Problem

Output quality (clip selection, titles, hooks, subtitles, captions) is only judged
manually today. `compare_llm_content.py` compares providers ad hoc. We need a repeatable
**evaluation pipeline** that scores pipeline outputs so we can:

- Catch prompt/model regressions before they ship.
- Compare LLM providers/models objectively (Claude vs GLM vs Ollama).
- Gate prompt changes in CI (see `docs/claude/testing.md` → prompt regression).

## Goals

- Score artifacts against rubrics: **clips** (hook strength, relevance), **titles**
  (scroll-stopping, length, no clickbait-penalty), **subtitles** (timing/accuracy),
  **captions/hook_text**, and overall **quality**.
- Both **reference-free** (rubric grading) and **reference-based** (vs a golden set).
- Deterministic, cached, cheap enough to run in CI on a small suite.
- Emit structured scores + rationales; aggregate to pass/fail thresholds.

## Non-goals

- Being a runtime gate inside a job (that is credit/quality control) — this is an
  offline/CI evaluator.
- Replacing human review for launch decisions — it informs them.

## Proposed architecture

```
evals/
  judge.py          # Judge protocol + rubric runner
  rubrics/          # one YAML/py per artifact type
    title.py
    clip_selection.py
    subtitles.py
    hook_text.py
  datasets/         # golden inputs + (optional) reference outputs
  runners.py        # batch a dataset through a pipeline node, collect artifacts
  report.py         # aggregate → markdown/JSON scorecard
  cli.py            # `python -m evals.cli --suite titles --model claude`
```

Judges call `tools.llm.get_llm()` with a **fixed judge model** (independent of the model
under test — avoid self-preference bias) and `llm.parse(prompt, ScoreSchema, system=...)`
for structured scores. Cache via `core/cache` keyed on `(artifact, rubric, judge_model)`
so re-runs are free.

### Score schema

```python
class Score(TypedDict):
    dimension: str        # e.g. "hook_strength"
    score: float          # 0..1 (or 1..10 normalized)
    rationale: str
    pass_: bool

class ArtifactEval(TypedDict):
    artifact_id: str
    artifact_type: str    # "title" | "clip" | "subtitles" | ...
    scores: list[Score]
    overall: float
```

### Rubric example (title)

Dimensions: scroll-stop (0..1), specificity, ≤50-char compliance (hard), no-emoji/no-caps
compliance (hard, mirrors `content_gen` rules), curiosity without clickbait. Overall =
weighted mean with hard-rule gates zeroing the score.

### Reference-based mode

For datasets with golden outputs, add pairwise preference ("is A better than golden?") and
report win-rate, alongside absolute rubric scores. Useful for A/B-ing prompt edits.

## Integration points

- **CI**: a `make evals` target runs a small suite; thresholds fail the build on
  regression (wire into `docs/claude/testing.md`).
- **Provider comparison**: supersedes `compare_llm_content.py`; can score the same inputs
  across `LLM_PROVIDER` values.
- Consumes VLM features (`vlm-agent.md`) for visual clip scoring once available.
- Feeds the memory system (`memory-system.md`) with what "good" looks like per channel.

## Phased plan

1. **P1** — `judge.py` + title & hook_text rubrics + a tiny golden dataset; CLI + report.
2. **P2** — Clip-selection + subtitles rubrics; caching; `make evals`.
3. **P3** — Reference-based pairwise mode; provider/model comparison matrix.
4. **P4** — Calibrate against real retention/CTR data; visual (VLM) scoring.

## Open questions

- Judge model choice & cost — default to a strong Claude model; allow override for cheap runs.
- Threshold calibration — start lenient, tighten as the golden set grows.
- Guard against judge non-determinism: temperature 0 + cache + report score variance.
