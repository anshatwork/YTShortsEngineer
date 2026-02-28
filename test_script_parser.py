"""
End-to-End Integration Test for YouTube Shorts Engine
Tests the complete workflow: Script Parser → Audio Selection → Workflow Integration
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file
load_dotenv()

from agents.script_parser import ScriptParserAgent
from agents.state import ShortsState
from tools.audio_api import AudioFetcher
from core.audio_theme_map import get_audio_theme_for_intent
from core.visual_intents import VisualIntent



# Sample content: True crime case
SAMPLE_CONTENT = """
From a market perspective, here is how the Uranium ETFs (like $URA and $URNM) in 2026 are repeating the "Silver in '25" playbook:

1. The "Structural Deficit" Script
Just as Silver entered 2025 in a massive multi-year supply deficit (driven by solar and EV demand), Uranium is hitting a critical wall in 2026. With major producers like Kazatomprom and Cameco struggling to meet targets and utilities facing depleted buffers, the "shortage" narrative has shifted from theory to a full-blown price squeeze.

2. The AI & Data Center Catalyst
In 2025, Silver was the "industrial darling" for green tech. In 2026, Uranium has become the "AI fuel." The massive energy demands of global AI data centers have forced tech giants to sign direct nuclear power contracts, effectively "locking up" future supply and sending the Global X Uranium ETF ($URA) soaring—reaching highs above $60 earlier this year.

3. Parabolic Breakouts & "Silver-Style" Volatility
The phrase "Uranium in '26 ending up like Silver in '25" refers to that specific vertical price action.

Silver in 2025: Broke a 13-year resistance at $30 and never looked back, gaining over 120% in a single year.

Uranium in 2026: Having finally breached its long-term "toppy" levels, it’s now in a price-discovery phase. However, as we saw with the recent Silver "flash crash" this week (Feb 2026), these parabolic moves often end in sharp, gut-wrenching corrections when profit-booking hits."""


def test_end_to_end_workflow():
    """Test the complete end-to-end workflow."""
    print("=" * 80)
    print("END-TO-END INTEGRATION TEST")
    print("=" * 80)
    
    # ========================================================================
    # PHASE 1: SCRIPT PARSING
    # ========================================================================
    print("\n" + "=" * 80)
    print("PHASE 1: SCRIPT PARSING")
    print("=" * 80)
    
    state: ShortsState = {
        "broad_topic": "Uranium price",
        "source_content": SAMPLE_CONTENT,
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "overlay_style": "background_only",
        "background_video_path": "assets\\op_bg1.mp4",
        "script": None,
        "script_prompt": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initial",
        "final_video_path": None,
        "audio_theme": None,
        "audio_file_path": None,
        "batch_index": 0
    }
    
    print(f"\nSource content: {len(SAMPLE_CONTENT)} characters")
    print(f"Topic: {state['broad_topic']}")
    
    try:
        parser = ScriptParserAgent()
        result = parser.run(state)
        
        scripts = result.get("parsed_script_list", [])
        print(f"\n✓ Successfully parsed {len(scripts)} script(s)")
        
        if not scripts:
            print("✗ No scripts extracted, test failed")
            return False
        
        # Display first script
        first_script = scripts[0]
        print(f"\n--- EXTRACTED SCRIPT ---")
        print(f"Key Point: {first_script.get('key_point')}")
        print(f"Word Count: {first_script.get('word_count')}")
        print(f"Hook: {first_script.get('hook')[:100]}...")
        print(f"\nFull Script Preview:")
        print(first_script.get('script')[:300] + "...")
        
    except Exception as e:
        print(f"\n✗ Script parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ========================================================================
    # PHASE 2: INTENT CLASSIFICATION & AUDIO SELECTION
    # ========================================================================
    print("\n" + "=" * 80)
    print("PHASE 2: INTENT CLASSIFICATION & AUDIO SELECTION")
    print("=" * 80)
    
    # Simulate intent classification (normally done by ScriptGenerationAgent)
    # For a true crime case, the intent should be TENSION
    expected_intent = VisualIntent.FINANCIAL    
    print(f"\nExpected Visual Intent: {expected_intent.value}")
    print(f"Description: {VisualIntent.get_description(expected_intent)}")
    
    # Map to audio theme
    audio_theme = get_audio_theme_for_intent(expected_intent)
    print(f"\nMapped Audio Theme: {audio_theme.value}")
    print(f"Description: {audio_theme.get_description(audio_theme)}")
    
    # Test audio fetching
    print(f"\n--- TESTING AUDIO FETCHER ---")
    try:
        fetcher = AudioFetcher()
        audio_path = fetcher.fetch_audio_for_theme(audio_theme)
        
        if audio_path:
            print(f"✓ Audio fetched successfully: {audio_path}")
            print(f"  Source: {'Cache' if 'audio_cache' in audio_path else 'Downloaded'}")
        else:
            print(f"⚠ No audio found (proceeding without background music)")
            print(f"  This is expected if API keys are not configured")
        
    except Exception as e:
        print(f"⚠ Audio fetching failed: {e}")
        print(f"  This is expected if API keys are not configured")
        audio_path = None
    
    # ========================================================================
    # PHASE 3: ACTUAL WORKFLOW EXECUTION
    # ========================================================================
    print("\n" + "=" * 80)
    print("PHASE 3: EXECUTING COMPLETE WORKFLOW")
    print("=" * 80)
    
    # Use the first parsed script for the workflow
    test_script = scripts[0]
    print(f"\nUsing script: {test_script.get('key_point')}")
    
    # Update state with the script
    state["script"] = test_script["script"]
    state["visual_intent"] = expected_intent.value
    state["audio_file_path"] = audio_path
    
    # Step 5: Video Selection - SKIPPED (using background video)
    print(f"\n--- STEP 5: VIDEO SELECTION ---")
    print(f"✓ Using pre-configured background video: {state['background_video_path']}")
    print(f"  Skipping content sourcing (background video already provided)")
    state["selected_video"] = None  # No fetched video, using background only
    
    
    # Step 6: Voiceover Generation
    print(f"\n--- STEP 6: VOICEOVER GENERATION ---")
    try:
        from agents.voice_synthesis import VoiceSynthesisAgent
        
        voice_agent = VoiceSynthesisAgent()
        voice_result = voice_agent.run(state)
        
        state.update(voice_result)
        voiceover_path = state.get("voiceover_audio_path")
        
        if voiceover_path:
            print(f"✓ Voiceover generated: {voiceover_path}")
        else:
            print(f"⚠ Voiceover generation failed")
            
    except Exception as e:
        print(f"⚠ Voiceover generation failed: {e}")
        print(f"  This is expected if ElevenLabs/Chatterbox is not configured")
        state["voiceover_audio_path"] = None
    
    # Step 7: Video Assembly
    print(f"\n--- STEP 7: VIDEO ASSEMBLY ---")
    try:
        from agents.video_assembly import VideoAssemblyAgent
        
        # The agent will handle overlay_style automatically
        print(f"Overlay style: {state.get('overlay_style', 'default')}")
        print(f"Background video: {state.get('background_video_path')}")
        print(f"Voiceover: {state.get('voiceover_audio_path')}")
        
        assembly_agent = VideoAssemblyAgent()
        assembly_result = assembly_agent.run(state)
        
        state.update(assembly_result)
        final_video = state.get("final_video_path")
        
        if final_video:
            print(f"✓ Video assembled: {final_video}")
            from pathlib import Path
            if Path(final_video).exists():
                file_size = Path(final_video).stat().st_size / (1024 * 1024)  # MB
                print(f"  File size: {file_size:.2f} MB")
        else:
            print(f"⚠ Video assembly failed")
            
    except Exception as e:
        print(f"⚠ Video assembly failed: {e}")
        print(f"  This is expected if dependencies (FFmpeg, MoviePy) are not configured")
        import traceback
        traceback.print_exc()
        state["final_video_path"] = None
    
    # # ========================================================================
    # # PHASE 4: BATCH PROCESSING SIMULATION
    # # ========================================================================
    # print("\n" + "=" * 80)
    # print("PHASE 4: BATCH PROCESSING SIMULATION")
    # print("=" * 80)
    
    # print(f"\nBatch processing would handle {len(scripts)} script(s):")
    # for idx, script_data in enumerate(scripts):
    #     print(f"\nScript {idx + 1}:")
    #     print(f"  - Key Point: {script_data.get('key_point')}")
    #     print(f"  - Word Count: {script_data.get('word_count')}")
    #     print(f"  - Status: Ready for processing")
    
    # # ========================================================================
    # # VALIDATION SUMMARY
    # # ========================================================================
    # print("\n" + "=" * 80)
    # print("VALIDATION SUMMARY")
    # print("=" * 80)
    
    # validations = {
    #     "Script Parser": len(scripts) > 0,
    #     "Script Structure": all('[HOOK]' in s.get('script', '') for s in scripts),
    #     "Word Count Range": all(50 <= s.get('word_count', 0) <= 400 for s in scripts),
    #     "Intent Mapping": audio_theme is not None,
    #     "Audio System": True,  # Always passes (graceful degradation)
    #     "Video Selection": state.get("video_candidates") is not None,
    #     "Voiceover Generation": state.get("voiceover_audio_path") is not None,
    #     "Video Assembly": state.get("final_video_path") is not None
    # }
    
    # print()
    # for check, passed in validations.items():
    #     status = "✓ PASS" if passed else "⚠ SKIP" if check in ["Video Selection", "Voiceover Generation", "Video Assembly"] else "✗ FAIL"
    #     print(f"{status}: {check}")
    
    # # Core validations (must pass)
    # core_validations = {k: v for k, v in validations.items() if k in ["Script Parser", "Script Structure", "Word Count Range", "Intent Mapping", "Audio System"]}
    # all_core_passed = all(core_validations.values())
    
    # # Optional validations (nice to have)
    # optional_validations = {k: v for k, v in validations.items() if k not in core_validations}
    # optional_passed = sum(optional_validations.values())
    
    # print(f"\nCore Features: {sum(core_validations.values())}/{len(core_validations)} passed")
    # print(f"Optional Features: {optional_passed}/{len(optional_validations)} passed")
    
    
    # For now, check if core workflow completed
    all_core_passed = (
        len(scripts) > 0 and 
        state.get("voiceover_audio_path") is not None and
        state.get("final_video_path") is not None
    )
    
    print("\n" + "=" * 80)
    if all_core_passed:
        print("🎉 END-TO-END WORKFLOW TEST PASSED!")
        print("=" * 80)
        print(f"\n✓ Scripts parsed: {len(scripts)}")
        print(f"✓ Voiceover generated: {state.get('voiceover_audio_path')}")
        print(f"✓ Video assembled: {state.get('final_video_path')}")
        print(f"✓ Background video used: {state.get('background_video_path')}")
    else:
        print("⚠ WORKFLOW INCOMPLETE")
        print("=" * 80)
        print(f"\nScripts parsed: {'✓' if len(scripts) > 0 else '✗'}")
        print(f"Voiceover generated: {'✓' if state.get('voiceover_audio_path') else '✗'}")
        print(f"Video assembled: {'✓' if state.get('final_video_path') else '✗'}")
    
    return all_core_passed


if __name__ == "__main__":
    success = test_end_to_end_workflow()
    sys.exit(0 if success else 1)
