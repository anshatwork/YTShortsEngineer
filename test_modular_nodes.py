"""
Test script to verify individual nodes with flexible composition modes.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from workflows.state import ShortsState
from agents.trend_discovery import TrendDiscoveryAgent
from agents.content_sourcing import ContentSourcingAgent
from agents.script_generation import ScriptGenerationAgent
from agents.voice_synthesis import VoiceSynthesisAgent
from agents.video_assembly import VideoAssemblyAgent
from core.config import Settings
from core.logger import setup_logger

# Load environment variables
load_dotenv()

# Setup logger
logger = setup_logger("TestModularNodes")

def test_composition(audio_mode="fetched_video", video_mode="split_screen", topic="Giannis trade rumours"):
    print("\n" + "=" * 60)
    print(f"TESTING COMPOSITION: Audio={audio_mode}, Video={video_mode}")
    print("=" * 60)

    # 1. Initialize State
    state: ShortsState = {
        "broad_topic": topic,
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "audio_mode": audio_mode,
        "video_mode": video_mode,
        "background_video_path": os.getenv("BACKGROUND_VIDEO_PATH"),
        "script": "This is a test script for the flexible composition engine. We are testing how the system handles different audio and video tracks.",
        "script_prompt": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initialized",
        "final_video_path": None
    }

    # --- Trend & Content (Required if modes involve 'fetched_video') ---
    if "fetched_video" in [audio_mode, video_mode] or video_mode == "split_screen":
        print("[STEP] Sourcing content from YouTube...")
        trend_agent = TrendDiscoveryAgent()
        state.update(trend_agent.run(state))
        print("search toh chala")
        source_agent = ContentSourcingAgent()
        state.update(source_agent.run(state))
        
        if state["video_candidates"]:
            state["selected_video"] = state["video_candidates"][0]
            print(f"✓ Selected video: {state['selected_video']['title']}")
        else:
            print("✗ No videos found, skipping.")
            return

    # --- Voice Synthesis (Required if audio_mode is 'voiceover') ---
    if audio_mode == "voiceover":
        print("[STEP] Generating voiceover...")
        voice_agent = VoiceSynthesisAgent()
        state.update(voice_agent.run(state))
        print(f"✓ Voiceover: {state['voiceover_audio_path']}")

    # --- Assembly ---
    print(f"[STEP] Assembling video (Mode: {video_mode}, Audio: {audio_mode})...")
    try:
        assembly_agent = VideoAssemblyAgent()
        state.update(assembly_agent.run(state))
        print(f"✓ SUCCESS! Final Video: {state['final_video_path']}")
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test 1: Background only with Voiceover (Person just wants a voiceover for his background video)
    test_composition(audio_mode="fetched_video", video_mode="split_screen", topic="Giannis trade rumours")
    
    # Test 2: Split screen with original audio (Optional/Feature check)
    # test_composition(audio_mode="fetched_video", video_mode="split_screen")
    
    # Test 3: Fetched video only with Voiceover
    # test_composition(audio_mode="voiceover", video_mode="fetched_video")
