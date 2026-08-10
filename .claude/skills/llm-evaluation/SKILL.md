---
name: llm-evaluation
description: Guide for evaluating LLM outputs in this repo — rubric judges, golden datasets, provider comparison, prompt-regression gating in CI. Use when implementing docs/future/llm-judge.md or validating a prompt/model change.
---

# LLM Evaluation

Design spec: `docs/future/llm-judge.md`. Supersedes the ad-hoc `compare_llm_content.py`. Use this to
build the eval harness or to validate a prompt/model change before it ships.

## What to evaluate
Artifacts produced by the pipeline: **clip selection** (hook strength/relevance), **titles**
(scroll-stop, ≤50 chars, no emoji/caps), **hook_text** (≤55 chars), **subtitles** (timing),
**summaries/captions**, and overall quality.

## Principles
- **Separate judge model from the model under test** (avoid self-preference bias). Use a fixed
  strong Claude judge via `get_llm()`; the test model varies by `LLM_PROVIDER`.
- **Structured scores**: `llm.parse(prompt, Score, system=...)` → `{dimension, score, rationale,
  pass_}`. Deterministic: temperature 0 + CAS cache keyed on `(artifact, rubric, judge_model)`.
- **Hard rules gate**: length/format violations (title ≤50, no emoji) zero the score regardless of
  the soft dimensions — mirror the prompt constraints in `content_gen`.

## Two modes
1. **Reference-free** — rubric grading against a checklist. Good default.
2. **Reference-based** — pairwise preference vs a golden output; report win-rate. Best for A/B-ing a
   prompt edit.

## Workflow
- [ ] Keep a small golden dataset (`evals/datasets/`) of representative transcripts.
- [ ] Run the artifact through the target node with mocked I/O to collect outputs.
- [ ] Score with the judge; aggregate to a scorecard (`evals/report.py`).
- [ ] Gate in CI via `make evals` with per-dimension thresholds; fail on regression.

## When validating a prompt change
- [ ] Run the suite before/after; a `version` bump means the cache won't mask the change.
- [ ] Report score deltas per dimension + variance across runs (guard judge non-determinism).
- [ ] Check parity across providers if the prompt must run on Ollama/GLM (base `parse` path).

## Guardrails
- Don't let eval scores be the *only* launch signal — calibrate against real retention/CTR
  (`docs/future/memory-system.md`) over time.
- Keep the suite cheap enough to run on every push.
