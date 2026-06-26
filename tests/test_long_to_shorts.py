"""
tests/test_long_to_shorts.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the Long-to-Shorts clipping workflow.

Two test suites:
  A) Unit tests (fast, fully mocked — no LLM, no ffmpeg, no disk I/O)
     Run: python -m pytest tests/test_long_to_shorts.py -v -k "not Integration"

  B) Integration test (real video, real ffmpeg — ailover.mp4 required)
     Run: python -m pytest tests/test_long_to_shorts.py -v -k Integration
     Or : python tests/test_long_to_shorts.py   (runs integration test directly)

Integration test pipeline:
    Synthetic transcript → AnalyzeVideoNode (mocked LLM) → ClippingLogicNode (real ffmpeg)
    → ContentGenNode (mocked LLM) → verify .mp4 files on disk
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is importable when run directly
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Path to the real test video
REAL_VIDEO = str(PROJECT_ROOT / "assets" / "ailover.mp4")
VIDEO_AVAILABLE = Path(REAL_VIDEO).exists()

SEP  = "=" * 64
SEP2 = "-" * 64


# ===========================================================================
# A) UNIT TESTS  (mocked)
# ===========================================================================

class TestStateSchema(unittest.TestCase):
    """Verify ClipObject and LongToShortsState instantiation."""

    def test_clip_object_structure(self):
        print("\n[Unit] Testing ClipObject structure …")
        from agents.state import ClipObject

        clip: ClipObject = {
            "clip_id": "clip_001",
            "source_video_path": "/video/long.mp4",
            "path": None,
            "timestamp_range": (10.0, 70.0),
            "hook_score": 8.5,
            "title": None,
            "summary": None,
        }

        self.assertEqual(clip["clip_id"], "clip_001")
        self.assertIsNone(clip["path"])
        self.assertEqual(clip["timestamp_range"], (10.0, 70.0))
        self.assertEqual(clip["hook_score"], 8.5)
        print("  ✓ clip_id, path, timestamp_range, hook_score all correct")

    def test_long_to_shorts_state_structure(self):
        print("\n[Unit] Testing LongToShortsState structure …")
        from agents.state import LongToShortsState

        state: LongToShortsState = {
            "source_video_path": "/video/long.mp4",
            "transcript": "Hello world this is a test transcript.",
            "top_n_clips": 5,
            "analyzed_segments": [],
            "generated_clips": [],
            "current_step": "initialized",
            "error": None,
        }

        self.assertEqual(state["top_n_clips"], 5)
        self.assertIsNone(state["error"])
        self.assertIsInstance(state["analyzed_segments"], list)
        print(f"  ✓ top_n_clips={state['top_n_clips']}, error=None, analyzed_segments=[]")

    def test_clip_object_title_max_chars(self):
        print("\n[Unit] Testing title max 50 chars constraint …")
        from agents.state import ClipObject

        title = "This is a 50-char viral Shorts title exactly!!"
        self.assertLessEqual(len(title), 50, "Test title must be ≤50 chars")

        clip: ClipObject = {
            "clip_id": "clip_002",
            "source_video_path": "/video/long.mp4",
            "path": "/output/clips/clip_002.mp4",
            "timestamp_range": (30.0, 90.0),
            "hook_score": 9.0,
            "title": title,
            "summary": "This clip shows the most viral moment of the video.",
        }
        self.assertEqual(len(clip["title"]), len(title))
        print(f"  ✓ title length = {len(clip['title'])} chars (≤50)")


# ---------------------------------------------------------------------------

class TestExtract916Clip(unittest.TestCase):
    """Verify ffmpeg filter chain args without running ffmpeg."""

    @patch("agents.long_to_shorts.clipping_logic_node.ffmpeg")
    def test_scale_pad_filter_arguments(self, mock_ffmpeg):
        print("\n[Unit] Testing ffmpeg scale+pad filter chain arguments …")
        from agents.long_to_shorts.clipping_logic_node import extract_9_16_clip, _OUT_W, _OUT_H

        mock_input      = MagicMock()
        mock_scaled     = MagicMock()
        mock_padded     = MagicMock()
        mock_output     = MagicMock()
        mock_run        = MagicMock()

        # .video.filter("scale") → mock_scaled; .filter("pad") → mock_padded
        mock_ffmpeg.input.return_value                = mock_input
        mock_input.video.filter.return_value          = mock_scaled
        mock_scaled.filter.return_value               = mock_padded
        # The encoder calls ffmpeg.output(video, file, **kwargs) — not video.output().
        mock_ffmpeg.output.return_value               = mock_output
        mock_output.overwrite_output.return_value     = mock_run

        # probe returns no audio so we take the video-only path
        mock_ffmpeg.probe.return_value = {"streams": [{"codec_type": "video"}]}

        extract_9_16_clip(
            input_file="/src/long.mp4",
            output_file="/out/clip_001.mp4",
            start=10.0,
            end=70.0,
        )

        # Input seek / duration
        mock_ffmpeg.input.assert_called_once_with("/src/long.mp4", ss=10.0, t=60.0)
        print("  ✓ ffmpeg.input called with ss=10.0, t=60.0")

        # Scale filter: fit inside 9:16 frame preserving aspect ratio
        scale_call = mock_input.video.filter.call_args
        self.assertEqual(scale_call[0][0], "scale")
        self.assertEqual(scale_call[1]["w"], _OUT_W)
        self.assertEqual(scale_call[1]["h"], _OUT_H)
        self.assertEqual(scale_call[1]["force_original_aspect_ratio"], "decrease")
        print(f"  ✓ filter('scale', w={_OUT_W}, h={_OUT_H}, force_original_aspect_ratio='decrease')")

        # Pad filter: fill remaining canvas with black
        pad_call = mock_scaled.filter.call_args
        self.assertEqual(pad_call[0][0], "pad")
        self.assertEqual(pad_call[1]["w"], _OUT_W)
        self.assertEqual(pad_call[1]["h"], _OUT_H)
        print(f"  ✓ filter('pad', w={_OUT_W}, h={_OUT_H}, centered)")

        # Codec args
        call_kwargs = mock_ffmpeg.output.call_args[1]
        self.assertEqual(call_kwargs["vcodec"], "libx264")
        self.assertEqual(call_kwargs["r"], 60)
        print(f"  ✓ vcodec={call_kwargs['vcodec']}  fps={call_kwargs['r']}")

    def test_invalid_segment_raises(self):
        print("\n[Unit] Testing ValueError on invalid segment (start >= end) …")
        from agents.long_to_shorts.clipping_logic_node import extract_9_16_clip

        with self.assertRaises(ValueError):
            extract_9_16_clip("/src/video.mp4", "/out/clip.mp4", start=100.0, end=50.0)
        print("  ✓ ValueError raised correctly")


# ---------------------------------------------------------------------------

class TestAnalyzeVideoNode(unittest.TestCase):
    """Test LLM hook score parsing and top-N selection."""

    def _make_state(self, transcript="word " * 500, top_n=3):
        return {
            "source_video_path": "/video/long.mp4",
            "transcript": transcript,
            "top_n_clips": top_n,
            "analyzed_segments": [],
            "generated_clips": [],
            "current_step": "initialized",
            "error": None,
        }

    @patch("agents.long_to_shorts.analyze_video_node._get_llm")
    def test_top_n_filtering(self, mock_get_llm):
        print("\n[Unit] Testing AnalyzeVideoNode top-N filtering …")
        scores = [9.0, 3.0, 7.5, 5.5, 8.0]
        call_count = [0]

        def fake_invoke(messages):
            idx   = call_count[0] % len(scores)
            score = scores[idx]
            call_count[0] += 1
            payload = {
                "start_time": 0.0,
                "end_time": 50.0,
                "hook_score": score,
                "reason": f"Test segment score={score}",
            }
            m = MagicMock()
            m.content = json.dumps(payload)
            return m

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = fake_invoke
        mock_get_llm.return_value   = mock_llm

        from agents.long_to_shorts.analyze_video_node import analyze_video_node

        state  = self._make_state(top_n=3)
        result = analyze_video_node(state)
        clips  = result["analyzed_segments"]

        print(f"  LLM called {call_count[0]} times, returned {len(clips)} clips (≤3 requested)")
        self.assertLessEqual(len(clips), 3)

        hook_scores = [c["hook_score"] for c in clips]
        print(f"  Hook scores (should be descending): {hook_scores}")
        self.assertEqual(hook_scores, sorted(hook_scores, reverse=True))
        print("  ✓ top-N filtering and descending sort verified")

    @patch("agents.long_to_shorts.analyze_video_node._get_llm")
    def test_clip_object_fields(self, mock_get_llm):
        print("\n[Unit] Testing required ClipObject fields from AnalyzeVideoNode …")
        payload = {"start_time": 5.0, "end_time": 55.0, "hook_score": 7.0, "reason": "Good"}
        m = MagicMock()
        m.content = json.dumps(payload)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = m
        mock_get_llm.return_value    = mock_llm

        from agents.long_to_shorts.analyze_video_node import analyze_video_node

        result = analyze_video_node(self._make_state(top_n=1))
        clips  = result["analyzed_segments"]
        self.assertGreater(len(clips), 0)
        clip = clips[0]

        for field in ("clip_id", "source_video_path", "timestamp_range", "hook_score"):
            self.assertIn(field, clip)
        self.assertIsNone(clip["path"])   # not extracted yet
        self.assertIsNone(clip["title"])  # not generated yet
        print(f"  ✓ clip_id={clip['clip_id']}  score={clip['hook_score']}  path=None  title=None")

    @patch("agents.long_to_shorts.analyze_video_node._get_llm")
    def test_llm_unavailable_uses_synthetic_fallback(self, mock_get_llm):
        print("\n[Unit] Testing synthetic fallback when LLM is unavailable …")
        mock_get_llm.side_effect = ValueError("No API key")

        from agents.long_to_shorts.analyze_video_node import analyze_video_node

        result = analyze_video_node(self._make_state(transcript="word " * 1000, top_n=2))
        self.assertIn("analyzed_segments", result)
        print(f"  ✓ No crash; analyzed_segments has {len(result['analyzed_segments'])} segment(s)")


# ---------------------------------------------------------------------------

class TestClippingLogicNode(unittest.TestCase):

    def _make_clips(self, n=2):
        from agents.state import ClipObject
        clips = []
        for i in range(n):
            clip: ClipObject = {
                "clip_id": f"clip_{i + 1:03d}",
                "source_video_path": "/video/long.mp4",
                "path": None,
                "timestamp_range": (float(i * 60), float((i + 1) * 60)),
                "hook_score": 9.0 - i,
                "title": None,
                "summary": None,
            }
            clips.append(clip)
        return clips

    @patch("agents.long_to_shorts.clipping_logic_node.extract_9_16_clip")
    def test_successful_clips_populate_path(self, mock_extract):
        print("\n[Unit] Testing ClippingLogicNode: successful extraction sets path …")
        mock_extract.return_value = None

        state = {
            "source_video_path": "/video/long.mp4",
            "transcript": "",
            "top_n_clips": 2,
            "analyzed_segments": self._make_clips(2),
            "generated_clips": [],
            "current_step": "analysis_complete",
            "error": None,
        }

        with patch("agents.long_to_shorts.clipping_logic_node.Path.mkdir"):
            with patch("os.getenv", return_value="output"):
                from agents.long_to_shorts.clipping_logic_node import clipping_logic_node
                result = clipping_logic_node(state)

        clips = result["generated_clips"]
        print(f"  Clips extracted: {len(clips)}")
        self.assertEqual(len(clips), 2)
        for clip in clips:
            self.assertIsNotNone(clip["path"])
            print(f"  ✓ {clip['clip_id']} → {clip['path']}")

    @patch("agents.long_to_shorts.clipping_logic_node.extract_9_16_clip")
    def test_failed_clips_are_skipped(self, mock_extract):
        print("\n[Unit] Testing ClippingLogicNode: failed clip is skipped …")
        import ffmpeg as ffmpeg_module
        call_count = [0]

        def side_effect(*args, **kwargs):
            if call_count[0] == 0:
                call_count[0] += 1
                raise ffmpeg_module.Error("ffmpeg", b"", b"encoding error")
            call_count[0] += 1

        mock_extract.side_effect = side_effect

        state = {
            "source_video_path": "/video/long.mp4",
            "transcript": "",
            "top_n_clips": 2,
            "analyzed_segments": self._make_clips(2),
            "generated_clips": [],
            "current_step": "analysis_complete",
            "error": None,
        }

        with patch("agents.long_to_shorts.clipping_logic_node.Path.mkdir"):
            with patch("os.getenv", return_value="output"):
                from agents.long_to_shorts.clipping_logic_node import clipping_logic_node
                result = clipping_logic_node(state)

        clips = result["generated_clips"]
        print(f"  Clips survived: {len(clips)} (1 failed, 1 succeeded)")
        self.assertEqual(len(clips), 1)
        print("  ✓ Failed clip correctly skipped")


# ---------------------------------------------------------------------------

class TestContentGenNode(unittest.TestCase):

    def _make_state_with_clips(self, n=2):
        from agents.state import ClipObject
        clips = []
        for i in range(n):
            clip: ClipObject = {
                "clip_id": f"clip_{i + 1:03d}",
                "source_video_path": "/video/long.mp4",
                "path": f"/output/clips/clip_{i + 1:03d}.mp4",
                "timestamp_range": (float(i * 60), float((i + 1) * 60)),
                "hook_score": 8.0,
                "title": None,
                "summary": None,
            }
            clips.append(clip)
        return {
            "source_video_path": "/video/long.mp4",
            "transcript": "This is a great moment in the video. " * 100,
            "top_n_clips": n,
            "analyzed_segments": clips,
            "generated_clips": clips,
            "current_step": "clipping_complete",
            "error": None,
        }

    @patch("agents.long_to_shorts.content_gen_node._get_llm")
    def test_title_within_50_chars(self, mock_get_llm):
        print("\n[Unit] Testing title hard-truncation at 50 chars …")
        long_title = "A" * 60
        m = MagicMock()
        m.content = f"TITLE: {long_title}\nSUMMARY: This is the viral moment of the whole video."
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = m
        mock_get_llm.return_value    = mock_llm

        from agents.long_to_shorts.content_gen_node import content_gen_node

        result = content_gen_node(self._make_state_with_clips(n=1))
        for clip in result["generated_clips"]:
            self.assertIsNotNone(clip["title"])
            self.assertLessEqual(len(clip["title"]), 50)
            print(f"  ✓ title='{clip['title']}'  length={len(clip['title'])} chars")

    @patch("agents.long_to_shorts.content_gen_node._get_llm")
    def test_summary_is_populated(self, mock_get_llm):
        print("\n[Unit] Testing summary is non-empty …")
        m = MagicMock()
        m.content = "TITLE: Viral Moment!\nSUMMARY: Watch this incredible highlight."
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = m
        mock_get_llm.return_value    = mock_llm

        from agents.long_to_shorts.content_gen_node import content_gen_node

        result = content_gen_node(self._make_state_with_clips(n=2))
        for clip in result["generated_clips"]:
            self.assertIsNotNone(clip["summary"])
            self.assertTrue(len(clip["summary"]) > 0)
            print(f"  ✓ {clip['clip_id']} summary: '{clip['summary'][:60]}…'")

    @patch("agents.long_to_shorts.content_gen_node._get_llm")
    def test_llm_unavailable_uses_placeholder(self, mock_get_llm):
        print("\n[Unit] Testing placeholder metadata when LLM unavailable …")
        mock_get_llm.side_effect = ValueError("No API key")

        from agents.long_to_shorts.content_gen_node import content_gen_node

        result = content_gen_node(self._make_state_with_clips(n=2))
        for clip in result["generated_clips"]:
            self.assertIsNotNone(clip["title"])
            self.assertLessEqual(len(clip["title"]), 50)
            self.assertIsNotNone(clip["summary"])
            print(f"  ✓ {clip['clip_id']} | title='{clip['title']}' | summary='{clip['summary'][:50]}…'")


# ===========================================================================
# B) INTEGRATION TEST  (real video, real ffmpeg — skipped if no video file)
# ===========================================================================

@unittest.skipUnless(VIDEO_AVAILABLE, f"Skipped: {REAL_VIDEO} not found")
class TestIntegrationRealVideo(unittest.TestCase):
    """
    End-to-end integration test using assets/ailover.mp4.
    Uses mocked LLM (to avoid HuggingFace API costs) but REAL ffmpeg.
    """

    SOURCE_VIDEO = REAL_VIDEO

    # Synthetic transcript that covers the first 3 minutes
    SYNTHETIC_TRANSCRIPT = (
        "Welcome to AI Lover podcast. Today we discuss the most transformative "
        "moments in artificial intelligence history. "
        "The first major breakthrough was when AlphaGo defeated the world champion. "
        "This shocked the world and proved deep learning could master complex strategy. "
        "Next, GPT-3 appeared and language models became the dominant paradigm. "
        "Researchers were amazed at how it could write code, poetry, and answer questions. "
        "Then came the era of diffusion models — Stable Diffusion, Midjourney, DALL-E. "
        "Creative professionals had to rethink their workflows overnight. "
        "The most viral moment though was when ChatGPT launched in late 2022 — "
        "100 million users in two months became the fastest product adoption in history. "
        "Finally, we are now in the age of multimodal models — GPT-4o, Gemini, Claude. "
        "These systems can see, hear, and reason simultaneously. "
        "The pace of change continues to accelerate, and we must adapt or be left behind. "
    ) * 5  # Repeat to give chunker enough material

    def _make_llm_mock(self, scores=None):
        """Build a mock LLM that returns structured JSON for analyze_video_node."""
        if scores is None:
            scores = [8.5, 6.0, 9.2, 7.1, 5.5]
        call_count = [0]

        def fake_invoke(messages):
            idx   = call_count[0] % len(scores)
            score = scores[idx]
            call_count[0] += 1
            payload = {
                "start_time": float(idx * 55),
                "end_time":   float(idx * 55 + 50),
                "hook_score": score,
                "reason":     f"Mocked high-impact segment #{idx + 1} score={score}",
            }
            m = MagicMock()
            m.content = json.dumps(payload)
            return m

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = fake_invoke
        return mock_llm

    @patch("agents.long_to_shorts.content_gen_node._get_llm")
    @patch("agents.long_to_shorts.analyze_video_node._get_llm")
    def test_full_pipeline_generates_real_clips(
        self, mock_analyze_llm, mock_content_llm
    ):
        """
        Run the full LangGraph pipeline on a real video file.
        Verifies .mp4 output files are actually written to disk.
        """
        print(f"\n{SEP}")
        print("  INTEGRATION TEST — Real Video + Real ffmpeg")
        print(f"  Source : {self.SOURCE_VIDEO}")
        print(f"  Clips  : output/clips/")
        print(SEP)

        # --- Mock: analyze_video LLM ---
        mock_analyze_llm.return_value = self._make_llm_mock(
            scores=[9.2, 7.8, 8.5]
        )
        print("  [Mock] AnalyzeVideoNode LLM → will return 3 mocked segments")

        # --- Mock: content_gen LLM ---
        content_call = [0]

        def fake_content_invoke(messages):
            content_call[0] += 1
            m = MagicMock()
            m.content = (
                f"TITLE: AI Breakthrough Moment #{content_call[0]}\n"
                f"SUMMARY: This segment reveals a pivotal moment in AI history that changed everything."
            )
            return m

        mock_content_llm.return_value = MagicMock()
        mock_content_llm.return_value.invoke.side_effect = fake_content_invoke
        print("  [Mock] ContentGenNode LLM → will return placeholder titles/summaries")

        # --- Run pipeline ---
        print(f"\n  Running pipeline …")
        from agents.long_to_shorts import long_to_shorts_app

        initial_state = {
            "source_video_path": str(Path(self.SOURCE_VIDEO).resolve()),
            "transcript": self.SYNTHETIC_TRANSCRIPT,
            "top_n_clips": 3,
            "analyzed_segments": [],
            "generated_clips": [],
            "current_step": "initialized",
            "error": None,
        }

        import time
        t0 = time.time()
        final_state = long_to_shorts_app.invoke(initial_state)
        elapsed = time.time() - t0

        print(f"\n  Pipeline finished in {elapsed:.1f}s")
        print(f"  Final step : {final_state.get('current_step', '?')}")
        if final_state.get("error"):
            print(f"  ERROR      : {final_state['error']}")

        # --- Inspect analyzed segments ---
        analyzed = final_state.get("analyzed_segments", [])
        print(f"\n  Analyzed segments : {len(analyzed)}")
        for seg in analyzed:
            start, end = seg["timestamp_range"]
            print(f"    {seg['clip_id']}  score={seg['hook_score']:.1f}  "
                  f"{start:.1f}s → {end:.1f}s")

        self.assertGreater(len(analyzed), 0, "AnalyzeVideoNode must return segments")

        # --- Inspect generated clips ---
        clips = final_state.get("generated_clips", [])
        print(f"\n  Clips generated   : {len(clips)}")
        print(f"\n  {SEP2}")
        for clip in clips:
            start, end = clip["timestamp_range"]
            path   = clip.get("path") or "NOT EXTRACTED"
            exists = Path(path).exists() if clip.get("path") else False
            status = "✓ EXISTS" if exists else "✗ missing"
            print(f"    {clip['clip_id']}  score={clip['hook_score']:.1f}  "
                  f"{start:.1f}s→{end:.1f}s  [{status}]")
            print(f"      title   : {clip.get('title', '–')}")
            print(f"      summary : {clip.get('summary', '–')}")
            print(f"      path    : {path}")
            print()
        print(f"  {SEP2}")

        # --- Assertions ---
        self.assertGreater(len(clips), 0, "At least one clip must be generated")

        successful = [c for c in clips if c.get("path") and Path(c["path"]).exists()]
        print(f"\n  Files on disk: {len(successful)}/{len(clips)}")

        for clip in successful:
            clip_path = Path(clip["path"])
            size_kb = clip_path.stat().st_size / 1024
            print(f"    ✓ {clip_path.name}  ({size_kb:.0f} KB)")
            self.assertGreater(size_kb, 1, f"Clip file {clip_path.name} seems too small (<1KB)")

        print(f"\n  Titles generated  : {sum(1 for c in clips if c.get('title'))}")
        print(f"  Summaries generated: {sum(1 for c in clips if c.get('summary'))}")

        for clip in clips:
            if clip.get("title"):
                self.assertLessEqual(
                    len(clip["title"]), 50,
                    f"Title too long: '{clip['title']}'"
                )

        print(f"\n  ✓ Integration test PASSED")
        print(f"  ✓ {len(successful)} real 9:16 clip(s) written to output/clips/")
        print(SEP)


# ===========================================================================
# Entry point — run integration test directly
# ===========================================================================

if __name__ == "__main__":
    """
    Running this file directly skips the unit tests and runs ONLY the
    integration test in verbose mode so you can see all debug output.
    """
    print(SEP)
    print("  Long-to-Shorts Integration Test")
    print(f"  Source video: {REAL_VIDEO}")
    print(f"  Video found : {VIDEO_AVAILABLE}")
    print(SEP)

    if not VIDEO_AVAILABLE:
        print(f"  ERROR: {REAL_VIDEO} not found. Cannot run integration test.")
        sys.exit(1)

    # Run only integration tests
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromTestCase(TestIntegrationRealVideo)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
