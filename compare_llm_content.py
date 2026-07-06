#!/usr/bin/env python
"""
compare_llm_content.py — GLM vs Ollama content quality, with Ollama as the judge.

For ONE YouTube clip, this generates the real per-clip metadata
(title / description / hook text) with two providers — **GLM** (OpenRouter/Z.ai)
and **Ollama** (local) — using the *production* prompt + schema from
``content_gen_node`` (so the comparison reflects the actual pipeline). It then has
an **Ollama model act as a blind judge**, scoring each candidate 1–10 on title
relevance, description quality, and hook strength, and picking a winner. Results
are printed side-by-side; ``--runs`` repeats to average out variance.

Input (choose one):
    --text "<transcript excerpt>"
    --transcript-file PATH
    --youtube-url URL [--start SECONDS --end SECONDS]   (fetches captions; window optional)

Examples:
    python compare_llm_content.py --youtube-url https://youtu.be/ID --start 30 --end 90
    python compare_llm_content.py --transcript-file clip.txt --runs 3 --json result.json

Setup:
    GLM (already in .env): GLM_API_KEY / GLM_BASE_URL / GLM_MODEL
    Ollama: a running daemon (OLLAMA_BASE_URL) with the candidate + judge models pulled.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env so GLM_*/OLLAMA_* are available exactly like the running app.
load_dotenv()

# Reuse the production prompt, user template, schema, and excerpt helpers so the
# generated content is identical to what the pipeline would produce.
from agents.long_to_shorts.content_gen_node import (  # noqa: E402
    ClipMeta,
    _CONTENT_SYSTEM_FILLED,
    _CONTENT_USER,
    _get_excerpt,
    _get_excerpt_timed,
)
from tools.llm.glm import GLMLLM, check_available as glm_check  # noqa: E402
from tools.llm.ollama import OllamaLLM, check_available as ollama_check  # noqa: E402

_EXCERPT_CHAR_CAP = 6000  # keep judge/gen prompts sane for local models


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Candidate(BaseModel):
    """Relaxed generation schema (no mood enum) used as a fallback so a small
    model returning an invalid `mood` doesn't sink the whole comparison."""

    title: str
    summary: str
    hook_text: str
    hashtags: List[str] = []


class DimScores(BaseModel):
    title_relevance: int       # 1–10: does the title accurately + compellingly capture the clip?
    description_quality: int   # 1–10: clear one-sentence description that teases value
    hook_strength: int         # 1–10: scroll-stopping on-screen hook


class Judgement(BaseModel):
    candidate_a: DimScores
    candidate_b: DimScores
    winner: str   # "A" | "B" | "tie"
    reasoning: str


# ---------------------------------------------------------------------------
# Generation (reuses the production prompt + schema)
# ---------------------------------------------------------------------------

def generate_content(llm, excerpt: str) -> Candidate:
    """Generate clip metadata with *llm* using the real content-gen prompt."""
    user_prompt = _CONTENT_USER.format(transcript_excerpt=excerpt)
    try:
        meta = llm.parse(user_prompt, ClipMeta, system=_CONTENT_SYSTEM_FILLED)
        return Candidate(
            title=meta.title, summary=meta.summary,
            hook_text=meta.hook_text, hashtags=list(meta.hashtags),
        )
    except Exception:
        # Fallback: drop the mood enum (common failure for small local models).
        return llm.parse(user_prompt, Candidate, system=_CONTENT_SYSTEM_FILLED)


# ---------------------------------------------------------------------------
# Judge (Ollama)
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """\
You are a strict, experienced YouTube Shorts editor. You are given a transcript
excerpt from ONE clip and two AI-generated metadata sets (Candidate A and B) for
that SAME clip. Judge them independently and impartially — you do not know which
model produced which.

Score EACH candidate from 1 to 10 on three dimensions:
- title_relevance: does the title accurately AND compellingly capture this clip?
- description_quality: is the one-sentence description clear and does it tease the
  value without being clickbait or generic?
- hook_strength: is the on-screen hook_text genuinely scroll-stopping and distinct
  from the title?

Be discerning: reserve 9–10 for excellent, use the full range, penalize generic,
vague, or off-topic copy. Then choose the overall winner ("A", "B", or "tie") and
give a one-sentence reason."""

_JUDGE_USER = """\
Transcript excerpt:
\"\"\"
{excerpt}
\"\"\"

Candidate A:
  title: {a_title}
  description: {a_summary}
  hook_text: {a_hook}

Candidate B:
  title: {b_title}
  description: {b_summary}
  hook_text: {b_hook}

Score both candidates and pick the winner."""


def judge(judge_llm, excerpt: str, a: Candidate, b: Candidate) -> Judgement:
    user_prompt = _JUDGE_USER.format(
        excerpt=excerpt,
        a_title=a.title, a_summary=a.summary, a_hook=a.hook_text,
        b_title=b.title, b_summary=b.summary, b_hook=b.hook_text,
    )
    return judge_llm.parse(user_prompt, Judgement, system=_JUDGE_SYSTEM)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

_DIMS = ("title_relevance", "description_quality", "hook_strength")


@dataclass
class Tally:
    scores: Dict[str, Dict[str, List[int]]] = field(default_factory=dict)
    wins: Dict[str, int] = field(default_factory=lambda: {"GLM": 0, "Ollama": 0, "tie": 0})
    candidates: Dict[str, Candidate] = field(default_factory=dict)

    def add(self, provider: str, dim: str, value: int) -> None:
        self.scores.setdefault(provider, {d: [] for d in _DIMS})[dim].append(value)

    def mean(self, provider: str, dim: str) -> float:
        vals = self.scores.get(provider, {}).get(dim, [])
        return statistics.mean(vals) if vals else 0.0

    def total(self, provider: str) -> float:
        return sum(self.mean(provider, d) for d in _DIMS)


def _normalize_winner(raw: str) -> str:
    w = (raw or "").strip().lower()
    if "tie" in w:
        return "tie"
    if w.startswith("a") or "candidate a" in w:
        return "A"
    if w.startswith("b") or "candidate b" in w:
        return "B"
    return "tie"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def resolve_excerpt(args) -> str:
    if args.text:
        excerpt = args.text
    elif args.transcript_file:
        with open(args.transcript_file, "r", encoding="utf-8") as fh:
            excerpt = fh.read()
    elif args.youtube_url:
        from tools.youtube.transcript import fetch_timed_segments, fetch_transcript

        if args.start is not None and args.end is not None:
            segments = fetch_timed_segments(args.youtube_url)
            excerpt = _get_excerpt_timed(segments, args.start, args.end)
            if not excerpt:
                # Fall back to the char-heuristic slice of the full transcript.
                excerpt = _get_excerpt(fetch_transcript(args.youtube_url), args.start, args.end)
        else:
            excerpt = fetch_transcript(args.youtube_url)
    else:
        raise SystemExit("Provide one of --text / --transcript-file / --youtube-url")

    excerpt = excerpt.strip()
    if not excerpt:
        raise SystemExit("Resolved transcript excerpt is empty.")
    if len(excerpt) > _EXCERPT_CHAR_CAP:
        excerpt = excerpt[:_EXCERPT_CHAR_CAP]
    return excerpt


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _print_candidate(label: str, c: Candidate) -> None:
    print(f"  [{label}]")
    print(f"    title      : {c.title}")
    print(f"    description: {c.summary}")
    print(f"    hook_text  : {c.hook_text}")
    if c.hashtags:
        print(f"    hashtags   : {', '.join(c.hashtags)}")


def print_report(tally: Tally, runs: int, models: dict) -> None:
    glm, oll = tally.candidates.get("GLM"), tally.candidates.get("Ollama")
    print("\n" + "=" * 70)
    print("LLM CONTENT COMPARISON — GLM vs Ollama (judge: Ollama)")
    print("=" * 70)
    print(f"GLM model    : {models['glm']}")
    print(f"Ollama model : {models['ollama']}")
    print(f"Judge model  : {models['judge']}   |   runs: {runs}")

    if glm:
        print("\nLatest GLM output:")
        _print_candidate("GLM", glm)
    if oll:
        print("\nLatest Ollama output:")
        _print_candidate("Ollama", oll)

    print("\nAverage judge scores (1–10):")
    header = f"  {'dimension':<22}{'GLM':>8}{'Ollama':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for d in _DIMS:
        print(f"  {d:<22}{tally.mean('GLM', d):>8.2f}{tally.mean('Ollama', d):>10.2f}")
    print("  " + "-" * (len(header) - 2))
    print(f"  {'TOTAL (max 30)':<22}{tally.total('GLM'):>8.2f}{tally.total('Ollama'):>10.2f}")

    print(f"\nJudge win tally:  GLM={tally.wins['GLM']}  "
          f"Ollama={tally.wins['Ollama']}  tie={tally.wins['tie']}")

    g, o = tally.total("GLM"), tally.total("Ollama")
    overall = "GLM" if g > o else "Ollama" if o > g else "TIE"
    print(f"Overall winner (by mean total score): {overall}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group("input (choose one)")
    src.add_argument("--text", help="Transcript excerpt as a string")
    src.add_argument("--transcript-file", help="Path to a file with the excerpt")
    src.add_argument("--youtube-url", help="YouTube URL/ID to fetch captions from")
    ap.add_argument("--start", type=float, help="Clip start seconds (with --youtube-url)")
    ap.add_argument("--end", type=float, help="Clip end seconds (with --youtube-url)")
    ap.add_argument("--glm-model", help="Override GLM model (else env GLM_MODEL)")
    ap.add_argument("--ollama-model", help="Candidate Ollama model (else env OLLAMA_MODEL)")
    ap.add_argument("--judge-model", help="Judge Ollama model (default: candidate Ollama model)")
    ap.add_argument("--runs", type=int, default=1, help="Repeat gen+judge N times and average (default 1)")
    ap.add_argument("--seed", type=int, help="Seed RNG for reproducible A/B ordering")
    ap.add_argument("--json", dest="json_out", help="Write full results to this JSON file")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # Pre-flight: both providers (and the judge) must be reachable.
    ok, detail = glm_check()
    if not ok:
        raise SystemExit(f"GLM unavailable: {detail}")
    ok, detail = ollama_check()
    if not ok:
        raise SystemExit(f"Ollama unavailable: {detail}")

    excerpt = resolve_excerpt(args)
    print(f"Excerpt ({len(excerpt)} chars):\n  {excerpt[:300]}{'…' if len(excerpt) > 300 else ''}")

    glm_llm = GLMLLM(model=args.glm_model)
    ollama_llm = OllamaLLM(model=args.ollama_model)
    judge_model = args.judge_model or args.ollama_model
    judge_llm = OllamaLLM(model=judge_model)

    models = {
        "glm": getattr(glm_llm, "_model", "?"),
        "ollama": getattr(ollama_llm, "_chat", None) and ollama_llm._chat.model,
        "judge": getattr(judge_llm, "_chat", None) and judge_llm._chat.model,
    }

    tally = Tally()
    runs_log = []

    for i in range(max(1, args.runs)):
        print(f"\n--- run {i + 1}/{args.runs} ---")
        try:
            glm_cand = generate_content(glm_llm, excerpt)
            oll_cand = generate_content(ollama_llm, excerpt)
        except Exception as exc:
            print(f"  generation failed: {type(exc).__name__}: {exc}")
            continue
        tally.candidates["GLM"] = glm_cand
        tally.candidates["Ollama"] = oll_cand

        # Blind the judge: randomize which provider is A vs B this run.
        pair = [("GLM", glm_cand), ("Ollama", oll_cand)]
        random.shuffle(pair)
        (prov_a, cand_a), (prov_b, cand_b) = pair

        try:
            verdict = judge(judge_llm, excerpt, cand_a, cand_b)
        except Exception as exc:
            print(f"  judge failed: {type(exc).__name__}: {exc}")
            continue

        # Map A/B scores back to providers.
        for dim in _DIMS:
            tally.add(prov_a, dim, getattr(verdict.candidate_a, dim))
            tally.add(prov_b, dim, getattr(verdict.candidate_b, dim))
        win = _normalize_winner(verdict.winner)
        winner_provider = prov_a if win == "A" else prov_b if win == "B" else "tie"
        tally.wins[winner_provider] += 1
        print(f"  judge: A={prov_a} B={prov_b} -> winner={winner_provider}  ({verdict.reasoning})")

        runs_log.append({
            "a_provider": prov_a, "b_provider": prov_b,
            "scores_a": verdict.candidate_a.model_dump(),
            "scores_b": verdict.candidate_b.model_dump(),
            "winner": winner_provider, "reasoning": verdict.reasoning,
        })

    print_report(tally, args.runs, models)

    if args.json_out:
        out = {
            "models": models,
            "excerpt": excerpt,
            "candidates": {k: v.model_dump() for k, v in tally.candidates.items()},
            "means": {p: {d: tally.mean(p, d) for d in _DIMS} for p in ("GLM", "Ollama")},
            "totals": {p: tally.total(p) for p in ("GLM", "Ollama")},
            "wins": tally.wins,
            "runs": runs_log,
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    sys.exit(main())
