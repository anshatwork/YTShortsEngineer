"""
Test script to verify the complete workflow including Hook Generation and Intent-based Video Selection.
This script runs actual agents without mocking.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from workflows.state import ShortsState
from agents.voice_synthesis import VoiceSynthesisAgent
from agents.video_assembly import VideoAssemblyAgent
from agents.trend_discovery import TrendDiscoveryAgent
from agents.content_sourcing import ContentSourcingAgent
from agents.script_generation import ScriptGenerationAgent
from agents.video_selection import VideoSelectionAgent
from core.logger import setup_logger

# Load environment variables
load_dotenv()

# Setup logger
logger = setup_logger("TestHookWorkflow")

def test_hook_and_selection_workflow(topic="Why coffee is better than tea"):
    print("\n" + "=" * 60)
    print(f"TESTING WORKFLOW FOR TOPIC: {topic}")
    print("=" * 60)

    # 1. Initialize State
    state: ShortsState = {
        "broad_topic": topic,
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "audio_mode": "voiceover",
        "video_mode": "fetched_video",
        "background_video_path": None,
        "script": None,
        "script_prompt": None,
        "hook_style": None,
        "visual_intent": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initialized",
        "final_video_path": None
    }

    try:
        # 1. Script Generation (First Step - Defines Intent)
        print("\n[STEP 1] Generating script (Hooks + Intent)...")
        script_agent = ScriptGenerationAgent()
        result = script_agent.run(state)
        state.update(result)
        print(f"✓ Hook Style: {state.get('hook_style')}")
        print(f"✓ Visual Intent: {state.get('visual_intent')}")
        print("-" * 30)
        print(f"Script Preview:\n{state['script'][:200]}...")
        print("-" * 30)

        # 2. Video Selection (Search + Select based on Intent)
        print("\n[STEP 2] Searching & Selecting video via Intent...")
        selection_agent = VideoSelectionAgent()
        result = selection_agent.run(state)
        state.update(result)
        
        if state["selected_video"]:
            print(f"✓ Selected Video: {state['selected_video']['title']}")
            print(f"✓ Video URL: {state['selected_video']['url']}")
        else:
            print("✗ No video selected.")

        # 3. Voice Over Generation (TTS)
        print("\n[STEP 3] Generating Voiceover (Chatterbox/Fallback)...")
        # Ensure audio_mode is set to voiceover
        state["audio_mode"] = "voiceover"
        tts_agent = VoiceSynthesisAgent()
        result = tts_agent.run(state)
        state.update(result)
        print(f"✓ Voiceover: {state.get('voiceover_audio_path')}")

        # 4. Video Assembly
        print("\n[STEP 4] Assembling Final Video...")
        # Ensure we have a background video for split screen if needed, 
        # but here we might just be using the 'fetched_video' as the main video depending on mode.
        # User requested 'fetched_video' mode earlier in python ..\test_hook_workflow.py
        
        # If video_mode is 'fetched_video', we use the downloaded video as the visual.
        # If 'split_screen', we need a background path too (usually).
        # Let's check what mode is set in state init.
        
        assembly_agent = VideoAssemblyAgent()
        result = assembly_agent.run(state)
        state.update(result)
        
        print("\n" + "=" * 60)
        print(f"WORKFLOW SUCCESS! Output: {state.get('final_video_path')}")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ WORKFLOW FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # You can change the topic here
    test_topic = "Benefits of Fascia release"
    test_hook_and_selection_workflow(topic=test_topic)
